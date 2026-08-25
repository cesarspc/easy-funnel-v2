"""Repository classes owning all Prisma queries.

Every repository wraps exactly one Prisma model accessor. Domain/service
code (tasks 6+) depends on these repositories rather than importing `prisma`
directly, so Prisma models never cross the API boundary — callers pass and
receive plain Python primitives / dicts here, and map to Pydantic schemas
(task 4+) at the API layer.

Each repository is intentionally a thin wrapper at this stage: base CRUD
plus the lookups already required by a checked-in constraint or index
(e.g. unique-slug/SKU lookups). Domain-specific query methods are added by
the task that first needs them, alongside a test proving the behavior.
"""

from __future__ import annotations

from datetime import datetime

from prisma import Prisma
from prisma.models import (
    AdminUser,
    AuditLog,
    Banner,
    BlacklistEntry,
    FraudConfig,
    FraudFlag,
    GeoIpRule,
    ImageAsset,
    ImageVariant,
    Landing,
    LandingBlock,
    LandingTemplate,
    Order,
    Product,
)
from prisma.types import (
    AdminUserCreateInput,
    BannerCreateInput,
    BannerUpdateInput,
    BlacklistEntryCreateInput,
    FraudConfigUpdateInput,
    FraudFlagCreateInput,
    GeoIpRuleCreateInput,
    GeoIpRuleUpdateInput,
    ImageAssetCreateInput,
    ImageVariantCreateInput,
    LandingBlockCreateInput,
    LandingBlockUpdateInput,
    LandingCreateInput,
    LandingTemplateCreateInput,
    LandingTemplateUpdateInput,
    LandingUpdateInput,
    OrderCreateInput,
    ProductCreateInput,
    ProductUpdateInput,
)


class ProductRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def get_by_id(self, product_id: int) -> Product | None:
        return await self._db.product.find_unique(where={"id": product_id})

    async def get_by_sku(self, sku: str) -> Product | None:
        return await self._db.product.find_unique(where={"sku": sku})

    async def create(self, data: ProductCreateInput) -> Product:
        return await self._db.product.create(data=data)

    async def update(self, product_id: int, data: ProductUpdateInput) -> Product | None:
        return await self._db.product.update(where={"id": product_id}, data=data)

    async def list_non_retired(self) -> list[Product]:
        return await self._db.product.find_many(where={"status": {"not": "retired"}})

    async def list_all(self) -> list[Product]:
        return await self._db.product.find_many()


class LandingRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def get_by_id(self, landing_id: int) -> Landing | None:
        return await self._db.landing.find_unique(where={"id": landing_id})

    async def get_by_slug(self, slug: str) -> Landing | None:
        return await self._db.landing.find_unique(where={"slug": slug})

    async def get_by_product_id(self, product_id: int) -> Landing | None:
        return await self._db.landing.find_unique(where={"productId": product_id})

    async def create(self, data: LandingCreateInput) -> Landing:
        return await self._db.landing.create(data=data)

    async def update(self, landing_id: int, data: LandingUpdateInput) -> Landing | None:
        return await self._db.landing.update(where={"id": landing_id}, data=data)

    async def list_all(self) -> list[Landing]:
        """Every landing, oldest first.

        Used by per-landing analytics, which reports one row per landing for a
        date range regardless of publication state (Requirement 8.12).
        """
        return await self._db.landing.find_many(order={"id": "asc"})


class BannerRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_for_landing(self, landing_id: int) -> list[Banner]:
        return await self._db.banner.find_many(
            where={"landingId": landing_id}, order={"orderIndex": "asc"}
        )

    async def create(self, data: BannerCreateInput) -> Banner:
        return await self._db.banner.create(data=data)

    async def update(self, banner_id: int, data: BannerUpdateInput) -> Banner | None:
        return await self._db.banner.update(where={"id": banner_id}, data=data)

    async def delete(self, banner_id: int) -> Banner | None:
        return await self._db.banner.delete(where={"id": banner_id})


class LandingBlockRepository:
    """Conversion components of a Landing, in render order.

    Ordering is `(slot_index, order_index)` — the same order the public page
    renders them in — so callers never re-sort.
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_for_landing(self, landing_id: int) -> list[LandingBlock]:
        return await self._db.landingblock.find_many(
            where={"landingId": landing_id},
            order=[{"slotIndex": "asc"}, {"orderIndex": "asc"}],
        )

    async def list_enabled_for_landing(self, landing_id: int) -> list[LandingBlock]:
        return await self._db.landingblock.find_many(
            where={"landingId": landing_id, "enabled": True},
            order=[{"slotIndex": "asc"}, {"orderIndex": "asc"}],
        )

    async def get_by_id(self, block_id: int) -> LandingBlock | None:
        return await self._db.landingblock.find_unique(where={"id": block_id})

    async def create(self, data: LandingBlockCreateInput) -> LandingBlock:
        return await self._db.landingblock.create(data=data)

    async def update(self, block_id: int, data: LandingBlockUpdateInput) -> LandingBlock | None:
        return await self._db.landingblock.update(where={"id": block_id}, data=data)

    async def delete(self, block_id: int) -> LandingBlock | None:
        return await self._db.landingblock.delete(where={"id": block_id})

    async def delete_for_landing(self, landing_id: int) -> int:
        """Remove every component of a landing, returning how many were deleted.

        Used when applying a template, which replaces the landing's components
        wholesale rather than merging into them: the target's
        `(landing_id, slot_index, order_index)` is unique, so merging would
        collide on every position the template also claims.
        """
        return await self._db.landingblock.delete_many(where={"landingId": landing_id})


class LandingTemplateRepository:
    """Named, reusable snapshots of a Landing's configuration.

    Listed newest-first: the template a merchant just saved is the one they are
    most likely to apply next.
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_all(self) -> list[LandingTemplate]:
        return await self._db.landingtemplate.find_many(order={"updatedAt": "desc"})

    async def get_by_id(self, template_id: int) -> LandingTemplate | None:
        return await self._db.landingtemplate.find_unique(where={"id": template_id})

    async def get_by_name(self, name: str) -> LandingTemplate | None:
        return await self._db.landingtemplate.find_unique(where={"name": name})

    async def create(self, data: LandingTemplateCreateInput) -> LandingTemplate:
        return await self._db.landingtemplate.create(data=data)

    async def update(
        self, template_id: int, data: LandingTemplateUpdateInput
    ) -> LandingTemplate | None:
        return await self._db.landingtemplate.update(where={"id": template_id}, data=data)

    async def delete(self, template_id: int) -> LandingTemplate | None:
        return await self._db.landingtemplate.delete(where={"id": template_id})


class ImageAssetRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def get_by_opaque_key(self, opaque_key: str) -> ImageAsset | None:
        return await self._db.imageasset.find_unique(where={"opaqueKey": opaque_key})

    async def create(self, data: ImageAssetCreateInput) -> ImageAsset:
        return await self._db.imageasset.create(data=data)

    async def mark_complete(self, image_asset_id: int) -> ImageAsset | None:
        return await self._db.imageasset.update(
            where={"id": image_asset_id}, data={"status": "complete"}
        )


class ImageVariantRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_for_asset(self, image_asset_id: int) -> list[ImageVariant]:
        return await self._db.imagevariant.find_many(where={"imageAssetId": image_asset_id})

    async def create(self, data: ImageVariantCreateInput) -> ImageVariant:
        return await self._db.imagevariant.create(data=data)


class OrderRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def get_by_id(self, order_id: int) -> Order | None:
        return await self._db.order.find_unique(where={"id": order_id})

    async def get_by_id_with_flags(self, order_id: int) -> Order | None:
        return await self._db.order.find_unique(
            where={"id": order_id}, include={"fraudFlags": True}
        )

    async def create(self, data: OrderCreateInput) -> Order:
        return await self._db.order.create(data=data)

    async def update_status(self, order_id: int, status: str) -> Order | None:
        return await self._db.order.update(where={"id": order_id}, data={"status": status})

    async def find_duplicates(
        self,
        *,
        phone_normalized_key: str,
        ip_address: str,
        created_after: datetime,
    ) -> list[Order]:
        return await self._db.order.find_many(
            where={
                "phoneNormalizedKey": phone_normalized_key,
                "ipAddress": ip_address,
                "createdAt": {"gte": created_after},
            }
        )


class FraudFlagRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def create(self, data: FraudFlagCreateInput) -> FraudFlag:
        return await self._db.fraudflag.create(data=data)

    async def list_for_order(self, order_id: int) -> list[FraudFlag]:
        return await self._db.fraudflag.find_many(where={"orderId": order_id})


class FraudConfigRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def get(self) -> FraudConfig | None:
        return await self._db.fraudconfig.find_unique(where={"id": 1})

    async def update(self, data: FraudConfigUpdateInput) -> FraudConfig | None:
        return await self._db.fraudconfig.update(where={"id": 1}, data=data)


class BlacklistEntryRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_all(self) -> list[BlacklistEntry]:
        return await self._db.blacklistentry.find_many()

    async def find(self, entry_type: str, value_normalized: str) -> BlacklistEntry | None:
        return await self._db.blacklistentry.find_unique(
            where={
                "entryType_valueNormalized": {
                    "entryType": entry_type,
                    "valueNormalized": value_normalized,
                }
            }
        )

    async def create(self, data: BlacklistEntryCreateInput) -> BlacklistEntry:
        return await self._db.blacklistentry.create(data=data)

    async def delete(self, entry_id: int) -> BlacklistEntry | None:
        return await self._db.blacklistentry.delete(where={"id": entry_id})


class GeoIpRuleRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_enabled(self) -> list[GeoIpRule]:
        return await self._db.geoiprule.find_many(where={"enabled": True})

    async def list_all(self) -> list[GeoIpRule]:
        return await self._db.geoiprule.find_many()

    async def create(self, data: GeoIpRuleCreateInput) -> GeoIpRule:
        return await self._db.geoiprule.create(data=data)

    async def update(self, rule_id: int, data: GeoIpRuleUpdateInput) -> GeoIpRule | None:
        return await self._db.geoiprule.update(where={"id": rule_id}, data=data)

    async def delete(self, rule_id: int) -> GeoIpRule | None:
        return await self._db.geoiprule.delete(where={"id": rule_id})


class LandingViewRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def record_fallback(self, landing_id: int) -> int:
        """Increment the durable fallback used only while Redis is unavailable."""
        rows = await self._db.query_raw(
            """
            INSERT INTO "landing_analytics_daily" (
                "landing_id", "event_date", "view_count", "cta_click_count",
                "fallback_view_count", "fallback_cta_click_count", "updated_at"
            )
            VALUES (
                $1, (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date,
                0, 0, 1, 0, CURRENT_TIMESTAMP
            )
            ON CONFLICT ("landing_id", "event_date") DO UPDATE
            SET "fallback_view_count" =
                    "landing_analytics_daily"."fallback_view_count" + 1,
                "updated_at" = CURRENT_TIMESTAMP
            RETURNING "fallback_view_count" AS count
            """,
            landing_id,
        )
        return int(rows[0]["count"])

    async def persist_redis_snapshot(
        self,
        landing_id: int,
        *,
        event_date: str,
        views: int,
        cta_clicks: int,
    ) -> None:
        """Persist monotonic absolute Redis totals for one Colombia business day.

        `GREATEST` makes concurrent or retried snapshots idempotent: an older
        snapshot can never replace a newer one. Fallback columns are untouched.
        """
        await self._db.execute_raw(
            """
            INSERT INTO "landing_analytics_daily" (
                "landing_id", "event_date", "view_count", "cta_click_count",
                "fallback_view_count", "fallback_cta_click_count", "updated_at"
            )
            VALUES ($1, $2::date, $3, $4, 0, 0, CURRENT_TIMESTAMP)
            ON CONFLICT ("landing_id", "event_date") DO UPDATE
            SET "view_count" = GREATEST(
                    "landing_analytics_daily"."view_count", EXCLUDED."view_count"
                ),
                "cta_click_count" = GREATEST(
                    "landing_analytics_daily"."cta_click_count", EXCLUDED."cta_click_count"
                ),
                "updated_at" = CURRENT_TIMESTAMP
            """,
            landing_id,
            event_date,
            views,
            cta_clicks,
        )

    async def count_for_landing(self, landing_id: int, *, since: datetime, until: datetime) -> int:
        rows = await self._db.query_raw(
            """
            SELECT COALESCE(SUM("view_count" + "fallback_view_count"), 0) AS count
            FROM "landing_analytics_daily"
            WHERE "landing_id" = $1
              AND "event_date" BETWEEN $2::date AND $3::date
            """,
            landing_id,
            since.date().isoformat(),
            until.date().isoformat(),
        )
        return int(rows[0]["count"])


class CtaClickRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def record_fallback(self, landing_id: int) -> int:
        """Increment the durable fallback used only while Redis is unavailable."""
        rows = await self._db.query_raw(
            """
            INSERT INTO "landing_analytics_daily" (
                "landing_id", "event_date", "view_count", "cta_click_count",
                "fallback_view_count", "fallback_cta_click_count", "updated_at"
            )
            VALUES (
                $1, (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date,
                0, 0, 0, 1, CURRENT_TIMESTAMP
            )
            ON CONFLICT ("landing_id", "event_date") DO UPDATE
            SET "fallback_cta_click_count" =
                    "landing_analytics_daily"."fallback_cta_click_count" + 1,
                "updated_at" = CURRENT_TIMESTAMP
            RETURNING "fallback_cta_click_count" AS count
            """,
            landing_id,
        )
        return int(rows[0]["count"])

    async def count_for_landing(self, landing_id: int, *, since: datetime, until: datetime) -> int:
        rows = await self._db.query_raw(
            """
            SELECT COALESCE(SUM("cta_click_count" + "fallback_cta_click_count"), 0) AS count
            FROM "landing_analytics_daily"
            WHERE "landing_id" = $1
              AND "event_date" BETWEEN $2::date AND $3::date
            """,
            landing_id,
            since.date().isoformat(),
            until.date().isoformat(),
        )
        return int(rows[0]["count"])


class AdminUserRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def get_by_username(self, username: str) -> AdminUser | None:
        return await self._db.adminuser.find_unique(where={"username": username})

    async def create(self, data: AdminUserCreateInput) -> AdminUser:
        return await self._db.adminuser.create(data=data)


class AuditLogRepository:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def record(
        self,
        *,
        actor: str,
        action: str,
        result: str,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> AuditLog:
        return await self._db.auditlog.create(
            data={
                "actor": actor,
                "action": action,
                "result": result,
                "targetType": target_type,
                "targetId": target_id,
            }
        )

    async def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        return await self._db.auditlog.find_many(order={"createdAt": "desc"}, take=limit)
