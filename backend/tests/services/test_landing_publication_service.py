"""Integration tests for LandingPublicationService (Requirements 3.16-3.24).

Requires a real database (see tests/conftest.py).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.db.client import utcnow
from app.domains.landings.errors import LandingNotFoundError, PublicationValidationError
from app.services.landing_publication_service import LandingPublicationService
from app.services.product_lifecycle_service import ProductLifecycleService
from prisma import Prisma

from tests.db.conftest import requires_database


async def _create_product_with_landing(db: Prisma, sku: str, *, active: bool = True) -> tuple:
    lifecycle = ProductLifecycleService(db)
    result = await lifecycle.create_product(
        name="Producto de Publicacion",
        sku=sku,
        price=Decimal("10.00"),
        status="active" if active else "paused",
        actor="admin",
    )
    return result.product, result.landing


async def _add_banner(db: Prisma, landing_id: int, order_index: int, opaque_key: str) -> None:
    asset = await db.imageasset.create(
        data={
            "opaqueKey": opaque_key,
            "sourceObjectKey": f"originals/{opaque_key}.jpg",
            "sourceWidth": 1200,
            "sourceHeight": 800,
            "sourceFormat": "jpeg",
            "status": "complete",
        }
    )
    await db.banner.create(
        data={
            "landingId": landing_id,
            "orderIndex": order_index,
            "altText": f"Banner {order_index}",
            "imageAssetId": asset.id,
        }
    )


@requires_database
class TestPublish:
    async def test_publish_succeeds_with_one_valid_banner_and_valid_cta_config(
        self, db: Prisma
    ) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-PUB-1")
        await _add_banner(db, landing.id, 0, "pub-1-banner-0")
        service = LandingPublicationService(db)

        published = await service.publish(landing.id, actor="admin")

        assert published.status == "published"

    async def test_publish_rejects_zero_banners_without_mutation(self, db: Prisma) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-PUB-2")
        service = LandingPublicationService(db)

        with pytest.raises(PublicationValidationError):
            await service.publish(landing.id, actor="admin")

        unchanged = await db.landing.find_unique(where={"id": landing.id})
        assert unchanged is not None
        assert unchanged.status == "draft"

    async def test_publish_rejects_invalid_cta_config_without_mutation(self, db: Prisma) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-PUB-3")
        await _add_banner(db, landing.id, 0, "pub-3-banner-0")
        # Force an invalid stored config: every_n mode with no interval.
        await db.landing.update(where={"id": landing.id}, data={"ctaMode": "every_n"})
        service = LandingPublicationService(db)

        with pytest.raises(PublicationValidationError):
            await service.publish(landing.id, actor="admin")

        unchanged = await db.landing.find_unique(where={"id": landing.id})
        assert unchanged is not None
        assert unchanged.status == "draft"

    async def test_publish_unknown_landing_raises_not_found(self, db: Prisma) -> None:
        service = LandingPublicationService(db)

        with pytest.raises(LandingNotFoundError):
            await service.publish(999_999_999, actor="admin")

    async def test_publish_is_audited(self, db: Prisma) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-PUB-AUDIT")
        await _add_banner(db, landing.id, 0, "pub-audit-banner-0")
        service = LandingPublicationService(db)

        await service.publish(landing.id, actor="admin-pub")

        entries = await db.auditlog.find_many(
            where={"targetType": "landing", "targetId": str(landing.id)}
        )
        assert any(e.action == "landing.publish" for e in entries)


@requires_database
class TestUnpublish:
    async def test_unpublish_returns_landing_to_draft(self, db: Prisma) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-UNPUB-1")
        await _add_banner(db, landing.id, 0, "unpub-1-banner-0")
        service = LandingPublicationService(db)
        await service.publish(landing.id, actor="admin")

        unpublished = await service.unpublish(landing.id, actor="admin")

        assert unpublished.status == "draft"


@requires_database
class TestResolvePublicLanding:
    async def test_active_product_and_published_landing_resolves(self, db: Prisma) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-RESOLVE-1")
        await _add_banner(db, landing.id, 0, "resolve-1-banner-0")
        service = LandingPublicationService(db)
        await service.publish(landing.id, actor="admin")

        view = await service.resolve_public_landing(landing.slug)

        assert view is not None
        assert view.landing.id == landing.id
        assert len(view.banners) == 1

    async def test_unknown_slug_resolves_to_none(self, db: Prisma) -> None:
        service = LandingPublicationService(db)

        view = await service.resolve_public_landing("does-not-exist-at-all")

        assert view is None

    async def test_draft_landing_resolves_to_none(self, db: Prisma) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-RESOLVE-DRAFT")
        service = LandingPublicationService(db)

        view = await service.resolve_public_landing(landing.slug)

        assert view is None

    async def test_paused_product_resolves_to_none_even_when_published(self, db: Prisma) -> None:
        product, landing = await _create_product_with_landing(
            db, "SKU-RESOLVE-PAUSED", active=False
        )
        await _add_banner(db, landing.id, 0, "resolve-paused-banner-0")
        service = LandingPublicationService(db)
        # Directly force-publish via repository since publish() only checks
        # banner/CTA validity, not product status (product status is an
        # orthogonal gate enforced by resolve_public_landing).
        await db.landing.update(where={"id": landing.id}, data={"status": "published"})

        view = await service.resolve_public_landing(landing.slug)

        assert view is None
        assert product.status == "paused"

    async def test_retired_landing_resolves_to_none(self, db: Prisma) -> None:
        _, landing = await _create_product_with_landing(db, "SKU-RESOLVE-RETIRED")
        await _add_banner(db, landing.id, 0, "resolve-retired-banner-0")
        service = LandingPublicationService(db)
        await service.publish(landing.id, actor="admin")
        await db.landing.update(where={"id": landing.id}, data={"retiredAt": utcnow()})

        view = await service.resolve_public_landing(landing.slug)

        assert view is None

    async def test_all_denied_states_yield_the_identical_none_outcome(self, db: Prisma) -> None:
        # Requirement 3.24: unknown/draft/paused/retired must be
        # indistinguishable to the caller — all resolve to the same `None`.
        service = LandingPublicationService(db)
        _, draft_landing = await _create_product_with_landing(db, "SKU-IDENTICAL-DRAFT")
        _, paused_landing = await _create_product_with_landing(
            db, "SKU-IDENTICAL-PAUSED", active=False
        )
        await _add_banner(db, paused_landing.id, 0, "identical-paused-banner-0")
        await db.landing.update(where={"id": paused_landing.id}, data={"status": "published"})

        outcomes = [
            await service.resolve_public_landing("unknown-slug-entirely"),
            await service.resolve_public_landing(draft_landing.slug),
            await service.resolve_public_landing(paused_landing.slug),
        ]

        assert all(outcome is None for outcome in outcomes)
