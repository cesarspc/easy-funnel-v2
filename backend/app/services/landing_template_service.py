"""LandingTemplateService: save a Landing's configuration by name, apply it to another.

Composes `app.domains.landings.templates` (what a template carries, and the
banner-count gate that decides whether it may be applied) with
`LandingTemplateRepository`, `LandingRepository`, `LandingBlockRepository`, and
`AuditLogRepository` inside Prisma transactions.

Three invariants this service owns:

- **A template never carries identity.** Slug, product, publication status, and
  banners stay with the landing. Applying a template configures a funnel; it
  cannot rename a page, move it to another product, or publish it.
- **Loading is all-or-nothing.** Config and components are validated in full
  before the first write, and the write happens in one transaction, so a
  template that turns out to be unapplicable leaves the target landing exactly
  as it was rather than half-converted.
- **Loading replaces components, it does not merge them.** `landing_blocks` is
  unique on `(landing_id, slot_index, order_index)`, so merging would collide
  on every position the template also claims — and a merchant applying a
  template wants that template's page, not their old components interleaved
  into it.
"""

from __future__ import annotations

from prisma import Json, Prisma
from prisma.models import LandingTemplate
from prisma.types import LandingUpdateInput

from app.db.repositories import (
    AuditLogRepository,
    BannerRepository,
    LandingBlockRepository,
    LandingRepository,
    LandingTemplateRepository,
)
from app.domains.landings.errors import LandingNotFoundError, LandingValidationError
from app.domains.landings.templates import (
    ensure_banner_count_matches,
    parse_template_blocks,
    parse_template_config,
    snapshot_blocks,
    snapshot_config,
    validate_template_name,
)


class TemplateNotFoundError(Exception):
    """Raised when a template id does not exist. Maps to 404."""

    def __init__(self, template_id: int) -> None:
        super().__init__(f"Landing template {template_id} was not found.")
        self.template_id = template_id


class DuplicateTemplateNameError(Exception):
    """Raised when saving under a name another template already holds.

    Maps to 409 rather than 422 so the dashboard can tell "you have to pick a
    different name" apart from "you may overwrite the one that exists", and ask
    before replacing work the merchant may still want.
    """

    def __init__(self, name: str, template_id: int) -> None:
        super().__init__(f"A landing template named '{name}' already exists.")
        self.name = name
        self.template_id = template_id


class LandingTemplateService:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_templates(self) -> list[LandingTemplate]:
        return await LandingTemplateRepository(self._db).list_all()

    async def save_template(
        self,
        landing_id: int,
        *,
        name: str,
        overwrite: bool = False,
        actor: str,
    ) -> LandingTemplate:
        """Snapshot `landing_id`'s configuration and components under `name`.

        `overwrite` is required to replace an existing template of the same
        name: the merchant has to have been asked first, because a template is
        deliberate work and the name collision may well be a typo.
        """
        validated_name = validate_template_name(name)

        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            banners = BannerRepository(tx)
            blocks = LandingBlockRepository(tx)
            templates = LandingTemplateRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            banner_count = len(await banners.list_for_landing(landing_id))
            config = snapshot_config(landing)
            block_payload = snapshot_blocks(await blocks.list_for_landing(landing_id))

            existing = await templates.get_by_name(validated_name)
            if existing is not None and not overwrite:
                raise DuplicateTemplateNameError(validated_name, existing.id)

            if existing is not None:
                saved = await templates.update(
                    existing.id,
                    {
                        "bannerCount": banner_count,
                        "config": Json(config),
                        "blocks": Json(block_payload),
                    },
                )
                if saved is None:
                    raise TemplateNotFoundError(existing.id)
                action = "landing_template.update"
            else:
                saved = await templates.create(
                    {
                        "name": validated_name,
                        "bannerCount": banner_count,
                        "config": Json(config),
                        "blocks": Json(block_payload),
                    }
                )
                action = "landing_template.create"

            await audit_log.record(
                actor=actor,
                action=action,
                target_type="landing_template",
                target_id=str(saved.id),
                result="success",
            )
            return saved

    async def load_template(self, landing_id: int, template_id: int, *, actor: str) -> None:
        """Apply a template's configuration and components to `landing_id`.

        Refused unless the target landing has exactly the template's banner
        count. Both the stored CTA positions and the components' slot indices
        address positions in the rendered sequence (banners with CTA bands
        interleaved), so a different banner count would silently relocate or
        drop components on a page the merchant is about to publish.
        """
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            banners = BannerRepository(tx)
            blocks = LandingBlockRepository(tx)
            templates = LandingTemplateRepository(tx)
            audit_log = AuditLogRepository(tx)

            landing = await landings.get_by_id(landing_id)
            if landing is None:
                raise LandingNotFoundError(landing_id)

            template = await templates.get_by_id(template_id)
            if template is None:
                raise TemplateNotFoundError(template_id)

            banner_count = len(await banners.list_for_landing(landing_id))
            ensure_banner_count_matches(required=template.bannerCount, actual=banner_count)

            # Everything is validated before the first write, so a template that
            # no longer applies leaves the landing untouched.
            config = parse_template_config(template.config, banner_count=banner_count)
            block_payload = parse_template_blocks(template.blocks)

            data: LandingUpdateInput = {
                "ctaMode": config["cta_mode"],
                "ctaInterval": config["cta_interval"],
                "ctaPositions": config["cta_positions"],
                "ctaBandStyle": config["cta_band_style"],
                "ctaText": config["cta_text"],
                "ctaAnimation": config["cta_animation"],
                "ctaTextOverrides": Json(config["cta_text_overrides"]),
                "formPresentation": config["form_presentation"],
                "accentColor": config["accent_color"],
                "formAccentColor": config["form_accent_color"],
                "blocksDarkMode": config["blocks_dark_mode"],
                "offerCount": config["offer_count"],
                "defaultOfferQuantity": config["default_offer_quantity"],
                "offers": Json(config["offers"]),
            }
            if await landings.update(landing_id, data) is None:
                raise LandingNotFoundError(landing_id)

            await blocks.delete_for_landing(landing_id)
            for entry in block_payload:
                await blocks.create(
                    {
                        "landingId": landing_id,
                        "blockType": entry["block_type"],
                        "slotIndex": entry["slot_index"],
                        "orderIndex": entry["order_index"],
                        "config": Json(entry["config"]),
                        "enabled": entry["enabled"],
                    }
                )

            await audit_log.record(
                actor=actor,
                action="landing_template.load",
                target_type="landing",
                target_id=str(landing_id),
                result="success",
            )

    async def delete_template(self, template_id: int, *, actor: str) -> None:
        async with self._db.tx() as tx:
            templates = LandingTemplateRepository(tx)
            audit_log = AuditLogRepository(tx)

            if await templates.get_by_id(template_id) is None:
                raise TemplateNotFoundError(template_id)

            await templates.delete(template_id)
            await audit_log.record(
                actor=actor,
                action="landing_template.delete",
                target_type="landing_template",
                target_id=str(template_id),
                result="success",
            )


__all__ = [
    "DuplicateTemplateNameError",
    "LandingTemplateService",
    "LandingValidationError",
    "TemplateNotFoundError",
]
