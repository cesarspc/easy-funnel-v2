"""LandingManagementService: landing configuration and banner sequence edits.

Composes `app.domains.landings` (slug format, alt text, CTA placement, form
presentation, banner ordering) with `LandingRepository` / `BannerRepository`
/ `AuditLogRepository` inside Prisma transactions.

Covers the mutations the Admin Dashboard's landing screen needs that are
not upload (`BannerUploadService`) or publication
(`LandingPublicationService`):

- slug, CTA mode/interval/positions, CTA band paint style, and COD form
  presentation updates (Requirements 3.1, 3.2, 3.9-3.11, 3.15, 3.16), rejected
  without replacing the active configuration when invalid;
- banner alternative-text edits (Requirements 3.3, 3.4);
- banner repositioning and removal, always leaving unique contiguous
  ascending order indices (Requirements 3.7, 3.8).

Order indices are renumbered in two passes inside one transaction because
`banners` carries a unique `(landing_id, order_index)` constraint that is
checked per statement: every affected row is first parked on a negative
placeholder index, then written to its final position, so no intermediate
statement can collide with a row that has not moved yet.

Removing a banner deletes only the `banners` row. The image asset, its
variants, and the R2 objects stay in place for the scheduled orphan cleanup
that owns image deletion (Requirements 4.16-4.18).
"""

from __future__ import annotations

from prisma import Prisma
from prisma.models import Banner, Landing
from prisma.types import LandingUpdateInput

from app.db.repositories import (
    AuditLogRepository,
    BannerRepository,
    LandingRepository,
)
from app.domains.landings.alt_text import validate_alt_text
from app.domains.landings.banner_ordering import contiguous_indices, reorder
from app.domains.landings.cta_band_style import validate_cta_band_style
from app.domains.landings.cta_placement import validate_cta_config
from app.domains.landings.errors import (
    BannerNotFoundError,
    DuplicateSlugError,
    LandingNotFoundError,
    LandingValidationError,
)
from app.domains.landings.form_presentation import validate_form_presentation
from app.domains.landings.slug import validate_slug_format


class LandingManagementService:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def update_config(
        self,
        landing_id: int,
        *,
        slug: str | None = None,
        cta_mode: str | None = None,
        cta_interval: int | None = None,
        cta_positions: list[int] | None = None,
        form_presentation: str | None = None,
        cta_band_style: str | None = None,
        actor: str,
    ) -> Landing:
        """Update the landing's slug, CTA configuration, and form presentation.

        Every supplied value is validated before a single write happens, so an
        invalid slug or CTA configuration leaves the stored configuration
        untouched (Requirements 3.2, 3.15). Omitted values are left as stored.
        """
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            banners = BannerRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            data: LandingUpdateInput = {}

            if slug is not None and slug != landing.slug:
                validate_slug_format(slug)
                # Uniqueness covers live and retired landings alike, since a
                # retired landing keeps its slug reserved (Requirement 3.2).
                existing = await landings.get_by_slug(slug)
                if existing is not None and existing.id != landing_id:
                    raise DuplicateSlugError(slug)
                data["slug"] = slug

            if cta_mode is not None or cta_interval is not None or cta_positions is not None:
                banner_count = len(await banners.list_for_landing(landing_id))
                mode = cta_mode if cta_mode is not None else landing.ctaMode
                interval = cta_interval if cta_interval is not None else landing.ctaInterval
                if cta_positions is not None:
                    positions: list[int] | None = cta_positions
                else:
                    positions = list(landing.ctaPositions) if landing.ctaPositions else None
                config = validate_cta_config(
                    mode,
                    interval=interval,
                    positions=positions,
                    # With no banners yet there is no sequence to bound fixed
                    # positions against; publication re-validates the stored
                    # configuration against the real banner count
                    # (Requirement 3.20).
                    banner_count=banner_count if banner_count > 0 else None,
                )
                data["ctaMode"] = config.mode
                data["ctaInterval"] = config.interval
                data["ctaPositions"] = sorted(config.positions) if config.positions else []

            if form_presentation is not None:
                data["formPresentation"] = validate_form_presentation(form_presentation)

            if cta_band_style is not None:
                data["ctaBandStyle"] = validate_cta_band_style(cta_band_style)

            if not data:
                return landing

            updated = await landings.update(landing_id, data)
            if updated is None:
                raise LandingNotFoundError(landing_id)

            await audit_log.record(
                actor=actor,
                action="landing.update",
                target_type="landing",
                target_id=str(landing_id),
                result="success",
            )
            return updated

    async def update_banner(
        self,
        landing_id: int,
        banner_id: int,
        *,
        alt_text: str | None = None,
        order_index: int | None = None,
        actor: str,
    ) -> list[Banner]:
        """Update a banner's alternative text and/or position.

        Returns the landing's full banner sequence in stored order, since a
        position change renumbers siblings (Requirement 3.7).
        """
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            banners = BannerRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            stored = await banners.list_for_landing(landing_id)
            if all(banner.id != banner_id for banner in stored):
                raise BannerNotFoundError(banner_id)

            # Validate both inputs before writing either, so a rejected
            # position leaves the stored alt text unchanged too.
            validated_alt_text = None if alt_text is None else validate_alt_text(alt_text)
            ordered_ids: list[int] | None = None
            if order_index is not None:
                ids = [banner.id for banner in stored]
                ordered_ids = reorder(ids, ids.index(banner_id), order_index)

            if validated_alt_text is not None:
                await banners.update(banner_id, {"altText": validated_alt_text})
            if ordered_ids is not None:
                await self._apply_order(banners, ordered_ids)

            await audit_log.record(
                actor=actor,
                action="banner.reorder" if ordered_ids is not None else "banner.update",
                target_type="banner",
                target_id=str(banner_id),
                result="success",
            )
            return await banners.list_for_landing(landing_id)

    async def delete_banner(self, landing_id: int, banner_id: int, *, actor: str) -> list[Banner]:
        """Remove a banner and close the resulting position gap (Requirement 3.8)."""
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            banners = BannerRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            stored = await banners.list_for_landing(landing_id)
            if all(banner.id != banner_id for banner in stored):
                raise BannerNotFoundError(banner_id)

            await banners.delete(banner_id)
            remaining = [banner.id for banner in stored if banner.id != banner_id]
            await self._apply_order(banners, remaining)

            await audit_log.record(
                actor=actor,
                action="banner.delete",
                target_type="banner",
                target_id=str(banner_id),
                result="success",
            )
            return await banners.list_for_landing(landing_id)

    async def reorder_banners(
        self, landing_id: int, ordered_banner_ids: list[int], *, actor: str
    ) -> list[Banner]:
        """Apply an explicit full ordering of the landing's banners.

        `ordered_banner_ids` must be a permutation of the landing's current
        banner ids; anything else is a field-specific validation error so a
        stale dashboard sequence cannot silently drop or duplicate a banner.
        """
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            banners = BannerRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            stored = await banners.list_for_landing(landing_id)
            stored_ids = [banner.id for banner in stored]
            if sorted(ordered_banner_ids) != sorted(stored_ids):
                raise LandingValidationError(
                    "banner_ids",
                    "The submitted order must list every banner of this landing exactly once.",
                )

            await self._apply_order(banners, ordered_banner_ids)

            await audit_log.record(
                actor=actor,
                action="banner.reorder",
                target_type="landing",
                target_id=str(landing_id),
                result="success",
            )
            return await banners.list_for_landing(landing_id)

    async def _apply_order(self, banners: BannerRepository, ordered_ids: list[int]) -> None:
        """Renumber `ordered_ids` to contiguous 0-based indices.

        Two passes: negative placeholders first, final indices second. The
        unique `(landing_id, order_index)` constraint is checked per
        statement, so writing final indices directly could collide with a
        sibling that still holds the target index.
        """
        indices = contiguous_indices(ordered_ids)
        for banner_id, index in indices.items():
            await banners.update(banner_id, {"orderIndex": -(index + 1)})
        for banner_id, index in indices.items():
            await banners.update(banner_id, {"orderIndex": index})
