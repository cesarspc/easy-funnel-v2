"""Database-level constraint tests for the catalog, order, and fraud models.

These exercise the Postgres constraints emitted by the Prisma schema and the
appended raw-SQL CHECK constraints directly (see
prisma/migrations/*/migration.sql), independent of any application-level
domain validation added in later tasks. Requirements: 2.5, 3.1, 3.2, 3.5,
3.6, 4.11, 5.9, 5.18, 6.3, 6.11, 2.15.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from prisma import Prisma
from prisma.errors import PrismaError

from tests.db.conftest import requires_database


async def _create_product(db: Prisma, *, sku: str, name: str = "Producto de prueba") -> object:
    return await db.product.create(
        data={
            "name": name,
            "sku": sku,
            "price": Decimal("19999.99"),
            "status": "active",
        }
    )


async def _create_landing(db: Prisma, *, product_id: int, slug: str) -> object:
    return await db.landing.create(
        data={
            "productId": product_id,
            "slug": slug,
            "ctaMode": "after_every",
            "formPresentation": "inline",
        }
    )


async def _create_image_asset(db: Prisma, *, opaque_key: str) -> object:
    return await db.imageasset.create(
        data={
            "opaqueKey": opaque_key,
            "sourceObjectKey": f"originals/{opaque_key}.jpg",
            "sourceWidth": 1200,
            "sourceHeight": 800,
            "sourceFormat": "jpeg",
            "status": "complete",
        }
    )


@requires_database
class TestProductConstraints:
    async def test_duplicate_sku_is_rejected(self, db: Prisma) -> None:
        await _create_product(db, sku="SKU-DUPE-1")

        with pytest.raises(PrismaError):
            await _create_product(db, sku="SKU-DUPE-1")

    async def test_price_is_stored_as_decimal_not_float(self, db: Prisma) -> None:
        product = await _create_product(db, sku="SKU-DECIMAL-1")

        assert isinstance(product.price, Decimal)
        assert product.price == Decimal("19999.99")

    async def test_price_below_minimum_is_rejected(self, db: Prisma) -> None:
        with pytest.raises(PrismaError):
            await db.product.create(
                data={
                    "name": "Producto barato",
                    "sku": "SKU-TOO-CHEAP",
                    "price": Decimal("0.00"),
                    "status": "active",
                }
            )

    async def test_unsupported_status_is_rejected(self, db: Prisma) -> None:
        with pytest.raises(PrismaError):
            await db.product.create(
                data={
                    "name": "Producto",
                    "sku": "SKU-BAD-STATUS",
                    "price": Decimal("10.00"),
                    "status": "not_a_real_status",
                }
            )


@requires_database
class TestLandingConstraints:
    async def test_second_landing_per_product_is_rejected(self, db: Prisma) -> None:
        product = await _create_product(db, sku="SKU-ONE-LANDING")
        await _create_landing(db, product_id=product.id, slug="landing-one")

        with pytest.raises(PrismaError):
            await _create_landing(db, product_id=product.id, slug="landing-two")

    async def test_duplicate_slug_across_products_is_rejected(self, db: Prisma) -> None:
        product_a = await _create_product(db, sku="SKU-SLUG-A")
        product_b = await _create_product(db, sku="SKU-SLUG-B")
        await _create_landing(db, product_id=product_a.id, slug="shared-slug")

        with pytest.raises(PrismaError):
            await _create_landing(db, product_id=product_b.id, slug="shared-slug")

    async def test_malformed_slug_is_rejected(self, db: Prisma) -> None:
        product = await _create_product(db, sku="SKU-BAD-SLUG")

        with pytest.raises(PrismaError):
            await _create_landing(db, product_id=product.id, slug="Not_A_Valid--Slug!")


@requires_database
class TestBannerConstraints:
    async def test_duplicate_order_index_within_a_landing_is_rejected(self, db: Prisma) -> None:
        product = await _create_product(db, sku="SKU-BANNER-ORDER")
        landing = await _create_landing(db, product_id=product.id, slug="banner-order-slug")
        asset = await _create_image_asset(db, opaque_key="opaque-order-1")

        await db.banner.create(
            data={
                "landingId": landing.id,
                "orderIndex": 0,
                "altText": "Primer banner",
                "imageAssetId": asset.id,
            }
        )

        with pytest.raises(PrismaError):
            await db.banner.create(
                data={
                    "landingId": landing.id,
                    "orderIndex": 0,
                    "altText": "Banner duplicado",
                    "imageAssetId": asset.id,
                }
            )


@requires_database
class TestOrderAndFraudConstraints:
    async def test_restrict_fk_prevents_erasing_a_referenced_product(self, db: Prisma) -> None:
        product = await _create_product(db, sku="SKU-RESTRICT-FK")
        landing = await _create_landing(db, product_id=product.id, slug="restrict-fk-slug")
        await db.order.create(
            data={
                "productId": product.id,
                "landingId": landing.id,
                "landingSlug": landing.slug,
                "customerName": "Cliente de Prueba",
                "phoneE164": "+573001234567",
                "phoneNormalizedKey": "3001234567",
                "department": "Antioquia",
                "city": "Medellin",
                "address": "Calle 1 # 2-3",
                "quantity": 1,
                "ipAddress": "203.0.113.5",
                "userAgent": "pytest",
            }
        )

        with pytest.raises(PrismaError):
            await db.product.delete(where={"id": product.id})

    async def test_unsupported_order_status_is_rejected(self, db: Prisma) -> None:
        product = await _create_product(db, sku="SKU-ORDER-STATUS")
        landing = await _create_landing(db, product_id=product.id, slug="order-status-slug")

        with pytest.raises(PrismaError):
            await db.order.create(
                data={
                    "productId": product.id,
                    "landingId": landing.id,
                    "landingSlug": landing.slug,
                    "customerName": "Cliente de Prueba",
                    "phoneE164": "+573001234567",
                    "phoneNormalizedKey": "3001234567",
                    "department": "Antioquia",
                    "city": "Medellin",
                    "address": "Calle 1 # 2-3",
                    "quantity": 1,
                    "status": "not_a_real_status",
                    "ipAddress": "203.0.113.5",
                    "userAgent": "pytest",
                }
            )

    async def test_fraud_config_singleton_guard_rejects_a_second_row(self, db: Prisma) -> None:
        # The migration seeds id=1; inserting id=2 must still be rejected by
        # the `fraud_config_singleton` CHECK (id = 1) constraint.
        with pytest.raises(PrismaError):
            await db.fraudconfig.create(data={"id": 2})

    async def test_duplicate_window_must_be_positive(self, db: Prisma) -> None:
        with pytest.raises(PrismaError):
            await db.fraudconfig.update(
                where={"id": 1},
                data={"duplicateWindowHours": 0},
            )

    async def test_blacklist_duplicate_same_type_is_rejected(self, db: Prisma) -> None:
        await db.blacklistentry.create(
            data={
                "entryType": "phone",
                "valueNormalized": "3009998888",
                "reason": "Fraude reportado por el transportista.",
            }
        )

        with pytest.raises(PrismaError):
            await db.blacklistentry.create(
                data={
                    "entryType": "phone",
                    "valueNormalized": "3009998888",
                    "reason": "Otra razon.",
                }
            )

    async def test_geoip_rule_unsupported_action_is_rejected(self, db: Prisma) -> None:
        with pytest.raises(PrismaError):
            await db.geoiprule.create(
                data={
                    "locationCode": "CO",
                    "action": "not_a_real_action",
                }
            )
