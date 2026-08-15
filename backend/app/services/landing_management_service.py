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

from prisma import Json, Prisma
from prisma.models import Banner, Landing
from prisma.types import LandingUpdateInput

from app.db.repositories import (
    AuditLogRepository,
    BannerRepository,
    LandingRepository,
)
from app.domains.landings.accent_color import normalize_accent_color
from app.domains.landings.alt_text import validate_alt_text
from app.domains.landings.banner_ordering import contiguous_indices, reorder
from app.domains.landings.cta_band_style import validate_cta_band_style
from app.domains.landings.cta_placement import validate_cta_config
from app.domains.landings.cta_text_overrides import validate_cta_text_overrides
from app.domains.landings.errors import (
    BannerNotFoundError,
    DuplicateSlugError,
    LandingNotFoundError,
    LandingValidationError,
)
from app.domains.landings.form_presentation import validate_form_presentation
from app.domains.landings.offers import (
    parse_stored_offers,
    resolve_offer_pricing,
    validate_default_offer_quantity,
    validate_offer_count,
    validate_offers,
)
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
        accent_color: str | None = None,
        form_accent_color: str | None = None,
        offer_count: int | None = None,
        offers: list[dict[str, object]] | None = None,
        default_offer_quantity: int | None = None,
        cta_text: str | None = None,
        cta_animation: str | None = None,
        cta_text_overrides: dict[object, object] | None = None,
        blocks_dark_mode: bool | None = None,
        actor: str,
    ) -> Landing:
        """Update the landing's slug, CTA configuration, and form presentation.

        Every supplied value is validated before a single write happens, so an
        invalid slug or CTA configuration leaves the stored configuration
        untouched (Requirements 3.2, 3.15). Omitted values are left as stored.

        `offer_count` and `offers` are validated together even when only one of
        them is supplied: the tier list has to describe exactly the number of
        tiers the form is going to render, so lowering the count with stale
        copy still in the column has to fail loudly rather than leave the public
        form asking for a quantity it has no price for.

        `form_accent_color` themes the COD form (tier tiles, focus rings,
        submit button) independently of `accent_color`, which continues to
        theme the CTA button/bands; empty string clears it back to following
        `accent_color`. `cta_text_overrides` maps a 1-based CTA position to a
        label that replaces `cta_text` for that position alone (e.g. only the
        second CTA saying "Lo quiero ahora"), leaving every other position on
        the landing's default label.
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

            if accent_color is not None:
                data["accentColor"] = normalize_accent_color(accent_color)

            if form_accent_color is not None:
                if form_accent_color == "":
                    # Empty string clears the override (form reverts to
                    # accent_color).
                    data["formAccentColor"] = None
                else:
                    data["formAccentColor"] = normalize_accent_color(
                        form_accent_color, field="form_accent_color"
                    )

            if cta_text is not None:
                if cta_text == "":
                    # Empty string clears the custom text (reverts to default).
                    data["ctaText"] = None
                elif len(cta_text) > 60:
                    raise LandingValidationError(
                        "cta_text", "CTA text must be 60 characters or fewer."
                    )
                else:
                    data["ctaText"] = cta_text

            if cta_animation is not None:
                if cta_animation == "":
                    # Empty string clears the animation.
                    data["ctaAnimation"] = None
                elif cta_animation not in ("slide", "shake"):
                    raise LandingValidationError(
                        "cta_animation",
                        "CTA animation must be 'slide', 'shake', or empty.",
                    )
                else:
                    data["ctaAnimation"] = cta_animation

            if cta_text_overrides is not None:
                validated_overrides = validate_cta_text_overrides(cta_text_overrides)
                data["ctaTextOverrides"] = Json(validated_overrides)

            if blocks_dark_mode is not None:
                data["blocksDarkMode"] = blocks_dark_mode

            effective_count = landing.offerCount
            if offer_count is not None or offers is not None:
                count = validate_offer_count(
                    offer_count if offer_count is not None else landing.offerCount
                )
                if offers is not None:
                    resolved_offers = validate_offers(offers, offer_count=count)
                else:
                    # Only the count moved. Re-validating the stored list against
                    # the new count would reject a legitimate count change, so the
                    # tiers are refitted instead: existing copy is kept for every
                    # quantity that survives, and a newly exposed quantity gets
                    # its default copy.
                    resolved_offers = parse_stored_offers(landing.offers, offer_count=count)
                product = await tx.product.find_unique(where={"id": landing.productId})
                if product is None:
                    raise LandingNotFoundError(landing_id)
                # A fixed COP discount is validated against this product's
                # concrete gross price before the JSON configuration is saved.
                # This keeps public pricing and order submission on one rule.
                for resolved_offer in resolved_offers:
                    resolve_offer_pricing(product.price, resolved_offer)
                data["offerCount"] = count
                data["offers"] = Json([offer.to_json() for offer in resolved_offers])
                effective_count = count

            if default_offer_quantity is not None:
                data["defaultOfferQuantity"] = validate_default_offer_quantity(
                    default_offer_quantity, offer_count=effective_count
                )
            elif effective_count < getattr(landing, "defaultOfferQuantity", 1):
                data["defaultOfferQuantity"] = 1

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
