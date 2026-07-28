"""Integration tests for BannerUploadService (Requirements 4.11, 4.12, 4.20-4.22, 3.6).

Uses a real database (see tests/conftest.py) and the in-process
FakeR2Client/FakeUnavailableR2Client doubles (tests/storage/fakes.py) so no
external R2/MinIO instance is required for these tests.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from app.domains.images.errors import ImagePipelineUnavailableError, ImageValidationError
from app.domains.landings.errors import (
    BannerLimitExceededError,
    LandingNotFoundError,
    LandingValidationError,
)
from app.services.banner_upload_service import BannerUploadService
from app.services.product_lifecycle_service import ProductLifecycleService
from PIL import Image
from prisma import Prisma

from tests.db.conftest import requires_database
from tests.domains.images.conftest import make_image_bytes
from tests.storage.fakes import FakeR2Client, FakeUnavailableR2Client


async def _create_landing(db: Prisma, sku: str) -> int:
    lifecycle = ProductLifecycleService(db)
    result = await lifecycle.create_product(
        name="Producto Banner", sku=sku, price=Decimal("10.00"), actor="admin"
    )
    return result.landing.id


@requires_database
class TestUploadBanner:
    async def test_successful_upload_creates_asset_variants_and_banner(self, db: Prisma) -> None:
        landing_id = await _create_landing(db, "SKU-UPLOAD-1")
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)

        result = await service.upload_banner(
            landing_id,
            raw_bytes=make_image_bytes(1600, 900),
            alt_text="Banner de prueba",
            actor="admin",
        )

        asset = await db.imageasset.find_unique(where={"id": result.image_asset_id})
        assert asset is not None
        assert asset.status == "complete"
        variants = await db.imagevariant.find_many(where={"imageAssetId": asset.id})
        assert len(variants) > 0
        assert result.banner.altText == "Banner de prueba"
        assert result.banner.orderIndex == 0

    async def test_successful_upload_persists_precomputed_edge_colors(self, db: Prisma) -> None:
        """Edge colors are extracted once here so no request path decodes images."""
        landing_id = await _create_landing(db, "SKU-UPLOAD-EDGE")
        service = BannerUploadService(db, FakeR2Client())

        result = await service.upload_banner(
            landing_id,
            # A solid fixture: both edges must resolve to that exact color.
            raw_bytes=make_image_bytes(600, 400, format_="PNG", color=(60, 120, 180)),
            alt_text="Banner con bordes planos",
            actor="admin",
        )

        asset = await db.imageasset.find_unique(where={"id": result.image_asset_id})
        assert asset is not None
        assert asset.topEdgeColor == "#3c78b4"
        assert asset.bottomEdgeColor == "#3c78b4"
        assert asset.topEdgeFlat is True
        assert asset.bottomEdgeFlat is True

    async def test_successful_upload_uploads_source_and_every_variant_to_r2(
        self, db: Prisma
    ) -> None:
        landing_id = await _create_landing(db, "SKU-UPLOAD-2")
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)

        result = await service.upload_banner(
            landing_id,
            raw_bytes=make_image_bytes(1600, 900),
            alt_text="Banner",
            actor="admin",
        )

        asset = await db.imageasset.find_unique(where={"id": result.image_asset_id})
        variants = await db.imagevariant.find_many(where={"imageAssetId": result.image_asset_id})
        assert asset is not None
        assert asset.sourceObjectKey in r2.objects
        for variant in variants:
            assert variant.objectKey in r2.objects

    async def test_second_banner_gets_the_next_order_index(self, db: Prisma) -> None:
        landing_id = await _create_landing(db, "SKU-UPLOAD-3")
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)
        await service.upload_banner(
            landing_id, raw_bytes=make_image_bytes(600, 400), alt_text="Primero", actor="admin"
        )

        second = await service.upload_banner(
            landing_id, raw_bytes=make_image_bytes(600, 400), alt_text="Segundo", actor="admin"
        )

        assert second.banner.orderIndex == 1

    async def test_sixteenth_banner_is_rejected_without_upload(self, db: Prisma) -> None:
        landing_id = await _create_landing(db, "SKU-UPLOAD-16")
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)
        for i in range(15):
            await service.upload_banner(
                landing_id,
                raw_bytes=make_image_bytes(480, 320),
                alt_text=f"Banner {i}",
                actor="admin",
            )

        with pytest.raises(BannerLimitExceededError):
            await service.upload_banner(
                landing_id,
                raw_bytes=make_image_bytes(480, 320),
                alt_text="Banner 16",
                actor="admin",
            )

        banners = await db.banner.find_many(where={"landingId": landing_id})
        assert len(banners) == 15
        object_count_after_rejection = len(r2.objects)

        # Confirm the rejection happened before any R2 upload for the 16th
        # attempt: object count matches exactly what 15 successful uploads
        # would produce (no extra objects from a partially-attempted 16th).
        assets_for_landing = await db.imageasset.find_many(
            where={"banners": {"some": {"landingId": landing_id}}}
        )
        expected_objects_per_asset = 1 + len(
            await db.imagevariant.find_many(where={"imageAssetId": assets_for_landing[0].id})
        )
        assert object_count_after_rejection == expected_objects_per_asset * 15

    async def test_invalid_image_is_rejected_with_no_db_row_and_no_upload(self, db: Prisma) -> None:
        landing_id = await _create_landing(db, "SKU-UPLOAD-INVALID")
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)

        with pytest.raises(ImageValidationError):
            await service.upload_banner(
                landing_id, raw_bytes=b"not an image", alt_text="Banner", actor="admin"
            )

        banners = await db.banner.find_many(where={"landingId": landing_id})
        assert banners == []
        assert r2.objects == {}

    async def test_invalid_alt_text_is_rejected_with_no_upload(self, db: Prisma) -> None:
        landing_id = await _create_landing(db, "SKU-UPLOAD-ALT")
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)

        with pytest.raises(LandingValidationError):
            await service.upload_banner(
                landing_id, raw_bytes=make_image_bytes(600, 400), alt_text="   ", actor="admin"
            )

        assert r2.objects == {}

    async def test_unknown_landing_raises_not_found(self, db: Prisma) -> None:
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)

        with pytest.raises(LandingNotFoundError):
            await service.upload_banner(
                999_999_999,
                raw_bytes=make_image_bytes(600, 400),
                alt_text="Banner",
                actor="admin",
            )

    async def test_upload_is_audited(self, db: Prisma) -> None:
        landing_id = await _create_landing(db, "SKU-UPLOAD-AUDIT")
        r2 = FakeR2Client()
        service = BannerUploadService(db, r2)

        result = await service.upload_banner(
            landing_id,
            raw_bytes=make_image_bytes(600, 400),
            alt_text="Banner",
            actor="admin-upload",
        )

        entries = await db.auditlog.find_many(
            where={"targetType": "banner", "targetId": str(result.banner.id)}
        )
        assert any(e.action == "banner.upload" for e in entries)


@requires_database
class TestUploadOutage:
    async def test_r2_outage_rejects_upload_without_partial_objects_or_db_row(
        self, db: Prisma
    ) -> None:
        landing_id = await _create_landing(db, "SKU-OUTAGE-1")
        service = BannerUploadService(db, FakeUnavailableR2Client())

        with pytest.raises(ImagePipelineUnavailableError):
            await service.upload_banner(
                landing_id,
                raw_bytes=make_image_bytes(600, 400),
                alt_text="Banner",
                actor="admin",
            )

        banners = await db.banner.find_many(where={"landingId": landing_id})
        assert banners == []

    async def test_existing_variants_remain_referenced_during_a_later_outage(
        self, db: Prisma
    ) -> None:
        # Simulates: banner A uploaded successfully while R2 was healthy;
        # a later upload attempt fails during an outage. Banner A's
        # asset/variants must be untouched by the failed second attempt.
        landing_id = await _create_landing(db, "SKU-OUTAGE-2")
        healthy_r2 = FakeR2Client()
        healthy_service = BannerUploadService(db, healthy_r2)
        first = await healthy_service.upload_banner(
            landing_id, raw_bytes=make_image_bytes(600, 400), alt_text="Primero", actor="admin"
        )

        outage_service = BannerUploadService(db, FakeUnavailableR2Client())
        with pytest.raises(ImagePipelineUnavailableError):
            await outage_service.upload_banner(
                landing_id,
                raw_bytes=make_image_bytes(600, 400),
                alt_text="Segundo",
                actor="admin",
            )

        first_asset_still_complete = await db.imageasset.find_unique(
            where={"id": first.image_asset_id}
        )
        assert first_asset_still_complete is not None
        assert first_asset_still_complete.status == "complete"
        banners = await db.banner.find_many(where={"landingId": landing_id})
        assert len(banners) == 1


class TestImageDecodeSanityForFixtures:
    def test_fixture_helper_produces_decodable_images(self) -> None:
        # Sanity check the shared test-fixture helper used throughout this
        # file actually produces valid, decodable image bytes.
        data = make_image_bytes(600, 400)
        image = Image.open(io.BytesIO(data))
        image.load()
        assert image.size == (600, 400)
