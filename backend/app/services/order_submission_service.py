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
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from prisma import Json, Prisma

from app.core.regional import PhoneRules
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
from app.domains.landings.offers import (
    find_offer,
    parse_stored_offers,
    resolve_offer_pricing,
)
from app.domains.orders import (
    DEFAULT_ORDER_STATUS,
    FLAGGED_FRAUD_STATUS,
    normalize_phone,
    normalize_phone_key,
    validate_address,
    validate_name,
    validate_quantity,
)
from app.domains.orders.errors import OrderValidationError
from app.domains.orders.locations import validate_delivery_location
from app.domains.products.variants import validate_variant_selections
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
    total_price: Decimal
    fraud_flags: list[FraudFlag]


class OrderSubmissionService:
    """Service for order submission with synchronous fraud evaluation."""

    def __init__(
        self,
        db: Prisma,
        redis_client,
        geoip_resolver: GeoIpResolver,
        *,
        phone_rules: PhoneRules,
        fulfillment_enabled: bool = True,
    ) -> None:
        self._db = db
        self._redis = redis_client
        self._geoip = geoip_resolver
        self._phone_rules = phone_rules
        self._fulfillment_enabled = fulfillment_enabled

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
        variant_selections: list[dict[str, str]] | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        address1: str | None = None,
        address2: str | None = None,
    ) -> OrderSubmissionResult:
        """Submit a COD order with fraud evaluation.

        Args:
            landing_slug: The landing page slug
            full_name: Customer's full name
            phone: Buyer phone number (validated with the configured phone rules)
            department: Customer's department
            city: Customer's city
            address: Customer's delivery address
            quantity: Order quantity
            variant_selections: One option mapping per ordered unit, when configured
            ip_address: Client IP address
            user_agent: Client user agent
            actor: Administrator or system actor

        Returns:
            OrderSubmissionResult with order ID, status, and fraud flags

        Raises:
            OrderValidationError: On validation failure (no order created)
        """
        # 1. Validate and normalize all fields
        supplied_name_parts = first_name is not None or last_name is not None
        if supplied_name_parts:
            validated_first_name = (first_name or "").strip()
            validated_last_name = (last_name or "").strip()
            if not validated_first_name:
                raise OrderValidationError("first_name", "First name is required.")
            if not validated_last_name:
                raise OrderValidationError("last_name", "Last name is required.")
            validated_name = validate_name(f"{validated_first_name} {validated_last_name}")
        else:
            validated_name = validate_name(full_name)
            legacy_name_parts = validated_name.split(" ", 1)
            validated_first_name = legacy_name_parts[0]
            validated_last_name = legacy_name_parts[1] if len(legacy_name_parts) == 2 else ""
        validated_phone = normalize_phone(phone, self._phone_rules)
        validated_phone_key = normalize_phone_key(phone, self._phone_rules)
        supplied_address_parts = address1 is not None or address2 is not None
        if supplied_address_parts:
            validated_address1 = (address1 or "").strip()
            if not validated_address1:
                raise OrderValidationError("address1", "Address is required.")
            validated_address2 = (address2 or "").strip() or None
            validated_address = validate_address(
                " ".join(part for part in [validated_address1, validated_address2] if part)
            )
        else:
            validated_address = validate_address(address)
            validated_address1 = validated_address
            validated_address2 = None
        validated_quantity = validate_quantity(quantity)

        # Truncate user agent to 512 chars (Requirement 5.11)
        validated_user_agent = user_agent[:512] if user_agent else ""

        # 2. Resolve the landing and fraud configuration without holding an
        # interactive transaction open across the external Redis calls below.
        # Prisma interactive transactions have a short timeout; keeping one
        # open here previously allowed the final order transaction to commit,
        # then made this stale outer transaction fail and return a false 503.
        landing = await self._db.landing.find_unique(
            where={"slug": landing_slug},
            include={"product": True},
        )
        if landing is None or landing.product is None:
            raise OrderValidationError("landing_slug", "Landing not found")

        product = landing.product
        if product.status != "active":
            raise OrderValidationError("landing_slug", "Product is not active")
        if landing.status != "published":
            raise OrderValidationError("landing_slug", "Landing is not published")

        config_record = await FraudConfigRepository(self._db).get()
        banned_cities = (
            list(getattr(config_record, "bannedCities", None) or []) if config_record else []
        )
        validated_department, validated_city = validate_delivery_location(
            department, city, banned_cities=banned_cities
        )
        product_options = (
            cast(list[dict[str, Any]], product.variantOptions)
            if isinstance(getattr(product, "variantOptions", None), list)
            else []
        )
        validated_variant_selections = validate_variant_selections(
            variant_selections,
            options=product_options,
            quantity=validated_quantity,
        )

        offers = parse_stored_offers(landing.offers, offer_count=landing.offerCount)
        selected_offer = find_offer(offers, validated_quantity)
        if selected_offer is None:
            available = ", ".join(str(offer.quantity) for offer in offers)
            raise OrderValidationError(
                "quantity",
                f"This landing only offers the following quantities: {available}.",
            )
        pricing = resolve_offer_pricing(product.price, selected_offer)
        config = _to_domain_fraud_config(config_record)

        # 3. External rate-limit work must finish before the database
        # transaction begins.
        phone_result = await check_rate_limit(
            self._redis,
            phone_rate_limit_key(validated_phone_key),
            max_attempts=config.rate_limit_max,
            window_seconds=config.rate_limit_window_minutes * 60,
        )
        ip_result = await check_rate_limit(
            self._redis,
            ip_rate_limit_key(ip_address),
            max_attempts=config.rate_limit_max,
            window_seconds=config.rate_limit_window_minutes * 60,
        )
        country, region, geoip_status = self._geoip.resolve(ip_address)
        geoip_result = GeoIpResult(
            country=country,
            region=region,
            available=(geoip_status in ("resolved", "unresolved")),
        )

        # 4-5. Fraud database reads, the order, flags, and audit are one atomic
        # transaction. Any exception rolls all of them back and reaches the API
        # as a real 503; a committed order always reaches the client as 201.
        async with self._db.tx() as persist_tx:
            duplicate_flags = await check_duplicate(
                persist_tx,
                phone_normalized_key=validated_phone_key,
                ip_address=ip_address,
                config=config,
            )
            blacklist_flags = await check_blacklist(
                persist_tx,
                phone_normalized_key=validated_phone_key,
                ip_address=ip_address,
            )
            geoip_rules = await persist_tx.geoiprule.find_many(where={"enabled": True})
            geoip_flags = check_geoip(geoip_result, geoip_rules)
            rate_limit_phone_flags = check_rate_limit_phone(
                phone_result,
                window_minutes=config.rate_limit_window_minutes,
            )
            rate_limit_ip_flags = check_rate_limit_ip(
                ip_result,
                window_minutes=config.rate_limit_window_minutes,
            )
            all_flags = aggregate_flags(
                duplicate_flags
                + blacklist_flags
                + rate_limit_phone_flags
                + rate_limit_ip_flags
                + geoip_flags
            )
            order_status = FLAGGED_FRAUD_STATUS if all_flags else DEFAULT_ORDER_STATUS

            order = await persist_tx.order.create(
                {
                    "productId": product.id,
                    "landingId": landing.id,
                    "landingSlug": landing_slug,
                    "customerName": validated_name,
                    "phoneE164": validated_phone,
                    "phoneNormalizedKey": validated_phone_key,
                    "department": validated_department,
                    "city": validated_city,
                    "address": validated_address,
                    "quantity": validated_quantity,
                    "variantSelections": Json(validated_variant_selections),
                    "unitPrice": pricing.unit_price,
                    "discountPercent": pricing.discount_percent,
                    "totalPrice": pricing.total,
                    "status": order_status,
                    "ipAddress": ip_address,
                    "userAgent": validated_user_agent,
                }
            )
            await persist_tx.orderfulfillmentdetails.create(
                {
                    "orderId": order.id,
                    "firstName": validated_first_name,
                    "lastName": validated_last_name,
                    "address1": validated_address1,
                    "address2": validated_address2,
                }
            )
            if self._fulfillment_enabled:
                await persist_tx.mastershopordersync.create(
                    {
                        "orderId": order.id,
                        "status": "waiting_review" if all_flags else "pending",
                    }
                )
            for flag in all_flags:
                await persist_tx.fraudflag.create(
                    {
                        "orderId": order.id,
                        "flagType": flag.flag_type,
                        "detail": Json(flag.detail),
                    }
                )
            await AuditLogRepository(persist_tx).record(
                actor=actor,
                action="order.submitted",
                target_type="order",
                target_id=str(order.id),
                result="success",
            )

        # 6. Exiting the only transaction above successfully means the exact
        # order returned here is committed and visible to the admin.
        return OrderSubmissionResult(
            order_id=order.id,
            status=order_status,
            total_price=pricing.total,
            fraud_flags=all_flags,
        )
