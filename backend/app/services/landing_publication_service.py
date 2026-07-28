"""LandingPublicationService: publish/unpublish gating + public availability.

Composes `app.domains.landings` validation with `LandingRepository` /
`BannerRepository` / `ProductRepository` / `AuditLogRepository`.

Publication (Requirements 3.19, 3.20): a landing may only be published when
it has 1-15 valid banners and a valid CTA configuration; publication is
rejected without mutation otherwise.

Public availability (Requirements 3.21-3.24): the resolver used by the
public `/api/public/landings/{slug}` route (task 17) must return the exact
same "not found" outcome for an unknown slug, a draft landing, a landing
whose product is paused or retired, and a retired landing — no branch may
leak which of these is true.
"""

from __future__ import annotations

from dataclasses import dataclass

from prisma import Prisma
from prisma.models import Banner, Landing, Product

from app.db.repositories import (
    AuditLogRepository,
    BannerRepository,
    LandingRepository,
    ProductRepository,
)
from app.domains.landings.cta_placement import validate_cta_config
from app.domains.landings.errors import (
    LandingNotFoundError,
    LandingValidationError,
    PublicationValidationError,
)

MIN_BANNERS_TO_PUBLISH = 1
MAX_BANNERS_TO_PUBLISH = 15


@dataclass(frozen=True)
class PublicLandingView:
    """The payload available for a genuinely active+published landing.

    A `None` return from `resolve_public_landing` (rather than this type)
    is the single "not found" outcome for every denied state.
    """

    landing: Landing
    product: Product
    banners: list[Banner]


def _validate_publishable(banners: list[Banner], landing: Landing) -> None:
    banner_count = len(banners)
    if not (MIN_BANNERS_TO_PUBLISH <= banner_count <= MAX_BANNERS_TO_PUBLISH):
        raise PublicationValidationError(
            f"A landing must have between {MIN_BANNERS_TO_PUBLISH} and "
            f"{MAX_BANNERS_TO_PUBLISH} banners to publish."
        )
    # Raises PublicationValidationError (via LandingValidationError's shared
    # shape) when the stored CTA config is invalid or inconsistent with the
    # current banner count.
    try:
        validate_cta_config(
            landing.ctaMode,
            interval=landing.ctaInterval,
            positions=list(landing.ctaPositions) if landing.ctaPositions else None,
            banner_count=banner_count,
        )
    except LandingValidationError as exc:
        raise PublicationValidationError(str(exc)) from exc


class LandingPublicationService:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def publish(self, landing_id: int, *, actor: str) -> Landing:
        """Publish a landing (Requirement 3.19); rejects without mutation
        if it lacks 1-15 valid banners or a valid CTA config (Requirement 3.20)."""
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            banners = BannerRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            landing_banners = await banners.list_for_landing(landing_id)
            _validate_publishable(landing_banners, landing)

            updated = await landings.update(landing_id, {"status": "published"})
            if updated is None:
                raise LandingNotFoundError(landing_id)

            await audit_log.record(
                actor=actor,
                action="landing.publish",
                target_type="landing",
                target_id=str(landing_id),
                result="success",
            )
            return updated

    async def unpublish(self, landing_id: int, *, actor: str) -> Landing:
        """Return a published landing to draft status (Requirement 3.16 area)."""
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            updated = await landings.update(landing_id, {"status": "draft"})
            if updated is None:
                raise LandingNotFoundError(landing_id)

            await audit_log.record(
                actor=actor,
                action="landing.unpublish",
                target_type="landing",
                target_id=str(landing_id),
                result="success",
            )
            return updated

    async def resolve_public_landing(self, slug: str) -> PublicLandingView | None:
        """Resolve a slug for public display, or `None` for every denied state.

        `None` is returned identically for: unknown slug, draft landing,
        retired landing, and a landing whose product is paused or retired
        (Requirements 3.21-3.24) — callers must render the same generic
        not-found response for all of these, never branching on which
        applied.
        """
        landings = LandingRepository(self._db)
        products = ProductRepository(self._db)
        banners = BannerRepository(self._db)

        landing = await landings.get_by_slug(slug)
        if landing is None:
            return None
        if landing.status != "published":
            return None
        if landing.retiredAt is not None:
            return None

        product = await products.get_by_id(landing.productId)
        if product is None:
            return None
        if product.status != "active":
            return None

        landing_banners = await banners.list_for_landing(landing.id)
        return PublicLandingView(landing=landing, product=product, banners=landing_banners)
