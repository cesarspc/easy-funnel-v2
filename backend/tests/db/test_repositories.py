"""Repository wrapper tests.

Confirms each repository's CRUD/lookup methods work against a real database
and return Prisma model instances (never bare dicts), consistent with the
"Prisma models never cross the API boundary" rule enforced by callers using
these repositories instead of the raw client (Requirement 10.3).
"""

from __future__ import annotations

from decimal import Decimal

from app.db import (
    AdminUserRepository,
    AuditLogRepository,
    BannerRepository,
    BlacklistEntryRepository,
    FraudConfigRepository,
    GeoIpRuleRepository,
    ImageAssetRepository,
    LandingRepository,
    OrderRepository,
    ProductRepository,
)
from prisma import Prisma

from tests.db.conftest import requires_database


@requires_database
class TestProductRepository:
    async def test_create_and_get_by_sku(self, db: Prisma) -> None:
        repo = ProductRepository(db)

        created = await repo.create(
            {
                "name": "Repo Product",
                "sku": "SKU-REPO-1",
                "price": Decimal("50.00"),
                "status": "active",
            }
        )
        fetched = await repo.get_by_sku("SKU-REPO-1")

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Repo Product"

    async def test_list_non_retired_excludes_retired_products(self, db: Prisma) -> None:
        repo = ProductRepository(db)
        await repo.create(
            {
                "name": "Active One",
                "sku": "SKU-REPO-ACTIVE",
                "price": Decimal("10.00"),
                "status": "active",
            }
        )
        retired = await repo.create(
            {
                "name": "Retired One",
                "sku": "SKU-REPO-RETIRED",
                "price": Decimal("10.00"),
                "status": "paused",
            }
        )
        await repo.update(retired.id, {"status": "retired"})

        results = await repo.list_non_retired()

        assert all(p.status != "retired" for p in results)
        assert any(p.sku == "SKU-REPO-ACTIVE" for p in results)
        assert not any(p.sku == "SKU-REPO-RETIRED" for p in results)


@requires_database
class TestLandingAndBannerRepositories:
    async def test_get_by_slug_and_by_product_id(self, db: Prisma) -> None:
        product_repo = ProductRepository(db)
        landing_repo = LandingRepository(db)
        product = await product_repo.create(
            {
                "name": "Landing Product",
                "sku": "SKU-REPO-LANDING",
                "price": Decimal("30.00"),
                "status": "active",
            }
        )
        created = await landing_repo.create(
            {
                "productId": product.id,
                "slug": "repo-landing-slug",
                "ctaMode": "after_every",
                "formPresentation": "inline",
            }
        )

        by_slug = await landing_repo.get_by_slug("repo-landing-slug")
        by_product = await landing_repo.get_by_product_id(product.id)

        assert by_slug is not None and by_slug.id == created.id
        assert by_product is not None and by_product.id == created.id

    async def test_list_all_includes_draft_landings(self, db: Prisma) -> None:
        # Per-landing analytics reports one row per landing regardless of
        # publication state (Requirement 8.12), so the listing must not filter.
        product_repo = ProductRepository(db)
        landing_repo = LandingRepository(db)
        product = await product_repo.create(
            {
                "name": "Listable Product",
                "sku": "SKU-REPO-LIST-ALL",
                "price": Decimal("30.00"),
                "status": "paused",
            }
        )
        draft = await landing_repo.create(
            {
                "productId": product.id,
                "slug": "repo-list-all-slug",
                "ctaMode": "after_every",
                "formPresentation": "inline",
            }
        )

        listed = await landing_repo.list_all()

        assert draft.status == "draft"
        assert any(landing.id == draft.id for landing in listed)
        assert [landing.id for landing in listed] == sorted(landing.id for landing in listed)

    async def test_banner_repository_orders_by_index(self, db: Prisma) -> None:
        product_repo = ProductRepository(db)
        landing_repo = LandingRepository(db)
        image_repo = ImageAssetRepository(db)
        banner_repo = BannerRepository(db)

        product = await product_repo.create(
            {
                "name": "Banner Product",
                "sku": "SKU-REPO-BANNER",
                "price": Decimal("30.00"),
                "status": "active",
            }
        )
        landing = await landing_repo.create(
            {
                "productId": product.id,
                "slug": "repo-banner-slug",
                "ctaMode": "after_every",
                "formPresentation": "inline",
            }
        )
        asset = await image_repo.create(
            {
                "opaqueKey": "repo-opaque-1",
                "sourceObjectKey": "originals/repo-opaque-1.jpg",
                "sourceWidth": 1200,
                "sourceHeight": 800,
                "sourceFormat": "jpeg",
                "status": "complete",
            }
        )
        await banner_repo.create(
            {
                "landingId": landing.id,
                "orderIndex": 1,
                "altText": "Second",
                "imageAssetId": asset.id,
            }
        )
        await banner_repo.create(
            {
                "landingId": landing.id,
                "orderIndex": 0,
                "altText": "First",
                "imageAssetId": asset.id,
            }
        )

        banners = await banner_repo.list_for_landing(landing.id)

        assert [b.altText for b in banners] == ["First", "Second"]


@requires_database
class TestOrderRepository:
    async def test_get_by_id_with_flags_includes_fraud_flags(self, db: Prisma) -> None:
        product_repo = ProductRepository(db)
        landing_repo = LandingRepository(db)
        order_repo = OrderRepository(db)

        product = await product_repo.create(
            {
                "name": "Order Product",
                "sku": "SKU-REPO-ORDER",
                "price": Decimal("30.00"),
                "status": "active",
            }
        )
        landing = await landing_repo.create(
            {
                "productId": product.id,
                "slug": "repo-order-slug",
                "ctaMode": "after_every",
                "formPresentation": "inline",
            }
        )
        order = await order_repo.create(
            {
                "productId": product.id,
                "landingId": landing.id,
                "landingSlug": landing.slug,
                "customerName": "Cliente Repo",
                "phoneE164": "+573007654321",
                "phoneNormalizedKey": "3007654321",
                "department": "Antioquia",
                "city": "Medellin",
                "address": "Calle 1 # 2-3",
                "quantity": 1,
                # Money is snapshotted on the order (see the Order model): a
                # stored order carries the price it was actually agreed at.
                "unitPrice": Decimal("30.00"),
                "totalPrice": Decimal("30.00"),
                "status": "flagged_fraud",
                "ipAddress": "203.0.113.9",
                "userAgent": "pytest",
            }
        )
        await db.fraudflag.create(
            data={"orderId": order.id, "flagType": "duplicate", "detail": '{"window_hours": 24}'}
        )

        fetched = await order_repo.get_by_id_with_flags(order.id)

        assert fetched is not None
        assert fetched.fraudFlags is not None
        assert len(fetched.fraudFlags) == 1
        assert fetched.fraudFlags[0].flagType == "duplicate"


@requires_database
class TestFraudConfigRepository:
    async def test_get_returns_the_seeded_singleton(self, db: Prisma) -> None:
        repo = FraudConfigRepository(db)

        config = await repo.get()

        assert config is not None
        assert config.id == 1
        assert config.duplicateWindowHours == 24
        assert set(config.duplicateMatchFields) == {"phone", "ip"}


@requires_database
class TestBlacklistEntryRepository:
    async def test_find_returns_none_when_no_match(self, db: Prisma) -> None:
        repo = BlacklistEntryRepository(db)

        result = await repo.find("phone", "3000000000")

        assert result is None

    async def test_find_returns_the_created_entry(self, db: Prisma) -> None:
        repo = BlacklistEntryRepository(db)
        await repo.create(
            {
                "entryType": "ip",
                "valueNormalized": "198.51.100.7",
                "reason": "Reportado por fraude reiterado.",
            }
        )

        result = await repo.find("ip", "198.51.100.7")

        assert result is not None
        assert result.reason == "Reportado por fraude reiterado."


@requires_database
class TestGeoIpRuleRepository:
    async def test_list_enabled_excludes_disabled_rules(self, db: Prisma) -> None:
        repo = GeoIpRuleRepository(db)
        await repo.create({"locationCode": "XX", "action": "flag", "enabled": True})
        disabled = await repo.create({"locationCode": "YY", "action": "block", "enabled": True})
        await repo.update(disabled.id, {"enabled": False})

        enabled_rules = await repo.list_enabled()

        assert any(r.locationCode == "XX" for r in enabled_rules)
        assert not any(r.locationCode == "YY" for r in enabled_rules)


@requires_database
class TestAdminUserRepository:
    async def test_create_and_get_by_username(self, db: Prisma) -> None:
        repo = AdminUserRepository(db)
        await repo.create({"username": "repo-admin", "passwordHash": "argon2-hash-placeholder"})

        fetched = await repo.get_by_username("repo-admin")

        assert fetched is not None
        assert fetched.role == "admin"


@requires_database
class TestAuditLogRepository:
    async def test_record_and_list_recent(self, db: Prisma) -> None:
        repo = AuditLogRepository(db)
        await repo.record(actor="system", action="test.action", result="success")

        recent = await repo.list_recent(limit=5)

        assert any(entry.action == "test.action" for entry in recent)
