"""OrderSubmissionService: orchestration for order submission with fraud evaluation.

Implements the order submission flow (Requirements 5.9-5.18, 6.12, 6.22-6.23):
1. Validate and normalize all fields
2. Resolve active product + published landing and capture attribution
3. Atomically increment Upstash Redis rate-limit counters (include current attempt)
4. Open Prisma transaction, run all fraud checks synchronously
5. Persist exactly one pending or flagged_fraud order with fraud flags
6. Commit or roll back on persistence error (no partial order)

All fraud checks run synchronously:
- Duplicate detection (Postgres, rolling window)
- Blacklist matching (Postgres)
- Rate limit phone/IP (Upstash Redis)
- GeoIP evaluation (local GeoLite2)

The order is persisted exactly once, never partially.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from prisma import Json, Prisma

from app.db.repositories import (
    AuditLogRepository,
    FraudConfigRepository,
)
from app.domains.fraud import (
    aggregate_flags,
    check_blacklist,
    check_duplicate,
    check_geoip,
    check_rate_limit_ip,
    check_rate_limit_phone,
)
from app.domains.fraud.models import (
    DEFAULT_DUPLICATE_MATCH_FIELDS,
    DEFAULT_DUPLICATE_WINDOW_HOURS,
    DEFAULT_RATE_LIMIT_MAX,
    DEFAULT_RATE_LIMIT_WINDOW_MINUTES,
    FraudConfig,
    GeoIpResult,
)
from app.domains.orders import (
    DEFAULT_ORDER_STATUS,
    FLAGGED_FRAUD_STATUS,
    normalize_colombian_phone,
    normalize_colombian_phone_key,
    validate_address,
    validate_city,
    validate_department,
    validate_name,
    validate_quantity,
)
from app.domains.orders.errors import OrderValidationError
from app.redis.rate_limit import check_rate_limit, ip_rate_limit_key, phone_rate_limit_key
from app.services.geoip_resolver import GeoIpResolver

if TYPE_CHECKING:
    from app.domains.fraud.models import FraudFlag


def _to_domain_fraud_config(record: object | None) -> FraudConfig:
    """Map the stored fraud configuration onto the domain model.

    The repository returns the Prisma record (camelCase attributes); the fraud
    checks take the domain `FraudConfig`, so the translation happens here at
    the service boundary. A missing row falls back to the documented defaults
    (Requirements 6.3, 6.11); a stored row is applied as-is so administrator
    changes take effect without a deployment (Requirement 6.20).
    """
    if record is None:
        return FraudConfig(
            duplicate_window_hours=DEFAULT_DUPLICATE_WINDOW_HOURS,
            duplicate_match_fields=DEFAULT_DUPLICATE_MATCH_FIELDS,
            rate_limit_max=DEFAULT_RATE_LIMIT_MAX,
            rate_limit_window_minutes=DEFAULT_RATE_LIMIT_WINDOW_MINUTES,
        )
    return FraudConfig(
        duplicate_window_hours=record.duplicateWindowHours,  # type: ignore[attr-defined]
        duplicate_match_fields=frozenset(record.duplicateMatchFields),  # type: ignore[attr-defined]
        rate_limit_max=record.rateLimitMax,  # type: ignore[attr-defined]
        rate_limit_window_minutes=record.rateLimitWindowMinutes,  # type: ignore[attr-defined]
    )


@dataclass(frozen=True)
class OrderSubmissionResult:
    """Result of order submission."""

    order_id: int
    status: str
    fraud_flags: list[FraudFlag]


class OrderSubmissionService:
    """Service for order submission with synchronous fraud evaluation."""

    def __init__(
        self,
        db: Prisma,
        redis_client,
        geoip_resolver: GeoIpResolver,
    ) -> None:
        self._db = db
        self._redis = redis_client
        self._geoip = geoip_resolver

    async def submit(
        self,
        *,
        landing_slug: str,
        full_name: str,
        phone: str,
        department: str,
        city: str,
        address: str,
        quantity: int,
        ip_address: str,
        user_agent: str,
        actor: str,
    ) -> OrderSubmissionResult:
        """Submit a COD order with fraud evaluation.

        Args:
            landing_slug: The landing page slug
            full_name: Customer's full name
            phone: Colombian phone number
            department: Customer's department
            city: Customer's city
            address: Customer's delivery address
            quantity: Order quantity
            ip_address: Client IP address
            user_agent: Client user agent
            actor: Administrator or system actor

        Returns:
            OrderSubmissionResult with order ID, status, and fraud flags

        Raises:
            OrderValidationError: On validation failure (no order created)
        """
        # 1. Validate and normalize all fields
        validated_name = validate_name(full_name)
        validated_phone = normalize_colombian_phone(phone)
        validated_phone_key = normalize_colombian_phone_key(phone)
        validated_department = validate_department(department)
        validated_city = validate_city(city)
        validated_address = validate_address(address)
        validated_quantity = validate_quantity(quantity)

        # Truncate user agent to 512 chars (Requirement 5.11)
        validated_user_agent = user_agent[:512] if user_agent else ""

        # 2. Resolve active product + published landing and capture attribution
        async with self._db.tx() as tx:
            # Get landing by slug
            landing = await tx.landing.find_unique(
                where={"slug": landing_slug},
                include={"product": True},
            )

            if landing is None:
                raise OrderValidationError("landing_slug", "Landing not found")

            # Check product is active and landing is published
            if landing.product.status != "active":
                raise OrderValidationError("landing_slug", "Product is not active")
            if landing.status != "published":
                raise OrderValidationError("landing_slug", "Landing is not published")

            product_id = landing.product.id
            landing_id = landing.id

            # 3. Atomically increment Redis rate-limit counters
            config = _to_domain_fraud_config(await FraudConfigRepository(self._db).get())

            # Rate limit for phone
            phone_key = phone_rate_limit_key(validated_phone_key)
            phone_result = await check_rate_limit(
                self._redis,
                phone_key,
                max_attempts=config.rate_limit_max,
                window_seconds=config.rate_limit_window_minutes * 60,
            )

            # Rate limit for IP
            ip_key = ip_rate_limit_key(ip_address)
            ip_result = await check_rate_limit(
                self._redis,
                ip_key,
                max_attempts=config.rate_limit_max,
                window_seconds=config.rate_limit_window_minutes * 60,
            )

            # 4. Run all fraud checks synchronously within one transaction
            # Use a new transaction for fraud checks to ensure consistency
            async with self._db.tx() as fraud_tx:
                # Duplicate check
                duplicate_flags = await check_duplicate(
                    fraud_tx,
                    phone_normalized_key=validated_phone_key,
                    ip_address=ip_address,
                    config=config,
                )

                # Blacklist check
                blacklist_flags = await check_blacklist(
                    fraud_tx,
                    phone_normalized_key=validated_phone_key,
                    ip_address=ip_address,
                )

                # GeoIP check
                country, region, geoip_status = self._geoip.resolve(ip_address)
                geoip_result = GeoIpResult(
                    country=country,
                    region=region,
                    available=(geoip_status in ("resolved", "unresolved")),
                )

                geoip_rules = await fraud_tx.geoiprule.find_many(where={"enabled": True})
                geoip_flags = check_geoip(geoip_result, geoip_rules)

                # Rate limit flags from Redis results
                rate_limit_phone_flags = check_rate_limit_phone(
                    phone_result,
                    window_minutes=config.rate_limit_window_minutes,
                )
                rate_limit_ip_flags = check_rate_limit_ip(
                    ip_result,
                    window_minutes=config.rate_limit_window_minutes,
                )

                # Aggregate all flags
                all_flags = aggregate_flags(
                    duplicate_flags
                    + blacklist_flags
                    + rate_limit_phone_flags
                    + rate_limit_ip_flags
                    + geoip_flags
                )

            # Determine status based on flags
            status = FLAGGED_FRAUD_STATUS if all_flags else DEFAULT_ORDER_STATUS

            # 5. Persist exactly one order (pending or flagged_fraud)
            try:
                async with self._db.tx() as persist_tx:
                    # Create order
                    order = await persist_tx.order.create(
                        {
                            "productId": product_id,
                            "landingId": landing_id,
                            "landingSlug": landing_slug,
                            "customerName": validated_name,
                            "phoneE164": validated_phone,
                            "phoneNormalizedKey": validated_phone_key,
                            "department": validated_department,
                            "city": validated_city,
                            "address": validated_address,
                            "quantity": validated_quantity,
                            "status": status,
                            "ipAddress": ip_address,
                            "userAgent": validated_user_agent,
                        }
                    )

                    # Create fraud flags if any
                    if all_flags:
                        for flag in all_flags:
                            await persist_tx.fraudflag.create(
                                {
                                    "orderId": order.id,
                                    "flagType": flag.flag_type,
                                    # `detail` is a jsonb column: Prisma needs
                                    # the explicit Json wrapper, not a bare dict.
                                    "detail": Json(flag.detail),
                                }
                            )

                    # Record audit log
                    audit = AuditLogRepository(persist_tx)
                    await audit.record(
                        actor=actor,
                        action="order.submitted",
                        target_type="order",
                        target_id=str(order.id),
                        result="success",
                    )

            except Exception as exc:
                # Roll back on persistence error - no partial order
                raise OrderValidationError("system", f"Order persistence failed: {exc}") from exc

            # 6. Return result
            return OrderSubmissionResult(
                order_id=order.id,
                status=status,
                fraud_flags=all_flags,
            )
