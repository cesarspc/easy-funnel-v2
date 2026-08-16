"""Landing configuration templates: snapshot a funnel, apply it to another product.

One merchant sells across unrelated niches, and what makes a funnel work is
almost entirely configuration: how often the CTA repeats and what it says, how
the COD form presents its quantity tiers, which accent carries the page, and
which conversion components sit between which elements. A template captures
exactly that under a name so the next product starts from a funnel that already
converts instead of a blank form.

**Why images are excluded, and why the banner count is a hard gate.**

Banners are the genuinely per-product part of a landing, so a template has no
business carrying them. But they are also what the rest of the snapshot is
addressed *against*. The public page renders banners with CTA bands interleaved
at `cta_positions`, and a component's `slot_index` counts positions in that
combined sequence. Apply a 5-banner template to a 3-banner landing and every
fixed CTA position past 3 disappears while every component past slot 6 slides
somewhere its author never chose — quietly, with no error, on a live page. So
`banner_count` travels with the template and loading is refused outright unless
the target matches it exactly. Refusing is a worse experience for exactly one
click and a better one for every page that would otherwise have shipped wrong.

**Everything is re-validated on load, never trusted.** A stored template is
data at rest that predates whatever validation rules exist when it is finally
applied: block types get renamed, bounds tighten, columns gain constraints. So
`parse_template_config` and `parse_template_blocks` push every field back
through the same domain validators a live edit goes through, and a template that
no longer validates fails loudly at load instead of writing something the
editor can no longer express.

Pure functions only: no I/O, no Prisma.
"""

from __future__ import annotations

from typing import Any

from app.domains.landings.accent_color import normalize_accent_color
from app.domains.landings.banner_ordering import MAX_BANNERS_PER_LANDING
from app.domains.landings.blocks import (
    MAX_BLOCKS_PER_LANDING,
    MAX_ORDER_INDEX,
    validate_block_config,
    validate_block_type,
    validate_slot_index,
)
from app.domains.landings.cta_band_style import validate_cta_band_style
from app.domains.landings.cta_color_modes import validate_cta_color_modes
from app.domains.landings.cta_placement import validate_cta_config
from app.domains.landings.cta_text_overrides import (
    OVERRIDE_TEXT_MAX,
    validate_cta_text_overrides,
)
from app.domains.landings.errors import LandingValidationError
from app.domains.landings.form_presentation import validate_form_presentation
from app.domains.landings.offers import (
    validate_default_offer_quantity,
    validate_offer_count,
    validate_offers,
)

#: Upper bound on a template name. Long enough for "Suplementos — 5 banners,
#: CTA agresivo", short enough to stay readable in the load dialog's list.
MAX_TEMPLATE_NAME_LENGTH = 80

#: The landing columns a template describes, in the order they appear in the
#: stored payload. Deliberately absent: `slug` and `product_id` (they identify
#: a landing, they do not configure it), `status` (loading a template must
#: never publish anything), and banners (see the module docstring).
TEMPLATE_CONFIG_FIELDS = (
    "cta_mode",
    "cta_interval",
    "cta_positions",
    "cta_band_style",
    "cta_text",
    "cta_animation",
    "cta_text_overrides",
    "cta_color_modes",
    "form_presentation",
    "accent_color",
    "form_accent_color",
    "blocks_accent_color",
    "blocks_dark_mode",
    "offer_count",
    "default_offer_quantity",
    "offers",
)

#: CTA animations the schema allows (`cta_animation` is nullable VarChar(10)).
_ALLOWED_CTA_ANIMATIONS = frozenset({"slide", "shake"})


def validate_template_name(raw_name: Any) -> str:
    """Return the trimmed template name, or raise a field error.

    Names are how the merchant recognizes a template in the load dialog, and
    they are unique in storage so re-saving a name updates that template rather
    than adding a second entry that looks identical in the list.
    """
    if not isinstance(raw_name, str):
        raise LandingValidationError("name", "El nombre de la plantilla es obligatorio.")

    name = raw_name.strip()
    if not name:
        raise LandingValidationError("name", "El nombre de la plantilla es obligatorio.")
    if len(name) > MAX_TEMPLATE_NAME_LENGTH:
        raise LandingValidationError(
            "name",
            f"El nombre no puede superar {MAX_TEMPLATE_NAME_LENGTH} caracteres.",
        )
    return name


def validate_template_banner_count(raw_count: Any) -> int:
    """Validate a snapshotted banner count against the per-landing cap."""
    if isinstance(raw_count, bool) or not isinstance(raw_count, int):
        raise LandingValidationError("banner_count", "El número de banners no es válido.")
    if raw_count < 0 or raw_count > MAX_BANNERS_PER_LANDING:
        raise LandingValidationError("banner_count", "El número de banners no es válido.")
    return raw_count


def ensure_banner_count_matches(*, required: int, actual: int) -> None:
    """Refuse a load whose target landing has a different number of banners.

    The message names both numbers because "must have 5" alone leaves the
    merchant counting rows to work out whether to add or remove.
    """
    if required == actual:
        return

    banner_word = "banner" if required == 1 else "banners"
    raise LandingValidationError(
        "banner_count",
        (
            f"No se pudo cargar: la landing debe tener {required} {banner_word} "
            f"y actualmente tiene {actual}."
        ),
    )


def snapshot_config(landing: Any) -> dict[str, Any]:
    """Build the JSON-safe `config` payload from a Landing row.

    Values are copied as stored rather than re-derived, so a template is a
    faithful record of the funnel the merchant was looking at when they saved
    it. `offers` and `cta_text_overrides` are already JSON in the column and
    are copied defensively so a later mutation of the row cannot reach into a
    stored template.
    """
    stored_offers = landing.offers if isinstance(landing.offers, list) else []
    stored_overrides = (
        landing.ctaTextOverrides if isinstance(landing.ctaTextOverrides, dict) else {}
    )
    stored_color_modes = (
        landing.ctaColorModes if isinstance(getattr(landing, "ctaColorModes", None), dict) else {}
    )
    return {
        "cta_mode": landing.ctaMode,
        "cta_interval": landing.ctaInterval,
        "cta_positions": list(landing.ctaPositions or []),
        "cta_band_style": landing.ctaBandStyle,
        "cta_text": landing.ctaText,
        "cta_animation": landing.ctaAnimation,
        "cta_text_overrides": dict(stored_overrides),
        "cta_color_modes": dict(stored_color_modes),
        "form_presentation": landing.formPresentation,
        "accent_color": landing.accentColor,
        "form_accent_color": landing.formAccentColor,
        "blocks_accent_color": getattr(landing, "blocksAccentColor", None),
        "blocks_dark_mode": bool(landing.blocksDarkMode),
        "offer_count": landing.offerCount,
        "default_offer_quantity": getattr(landing, "defaultOfferQuantity", 1),
        "offers": [dict(offer) for offer in stored_offers if isinstance(offer, dict)],
    }


def snapshot_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    """Build the JSON-safe `blocks` payload from a landing's components.

    Database ids are dropped: a template is applied by creating new rows on the
    target landing, so carrying the source's ids would only invite writing them
    somewhere. `slot_index` / `order_index` are kept because they *are* the
    placement, which is the part of a component a template exists to reuse.
    """
    payload: list[dict[str, Any]] = []
    for block in blocks:
        config = block.config if isinstance(block.config, dict) else {}
        payload.append(
            {
                "block_type": block.blockType,
                "slot_index": block.slotIndex,
                "order_index": block.orderIndex,
                "config": dict(config),
                "enabled": bool(block.enabled),
            }
        )
    return payload


def parse_template_config(raw_config: Any, *, banner_count: int) -> dict[str, Any]:
    """Re-validate a stored `config` payload for application to a landing.

    Returns snake_case keys ready to hand to `LandingManagementService.
    update_configuration`, so the load path reuses the exact validation a
    manual edit goes through instead of a second, drifting copy of it.

    `banner_count` is the *target* landing's count. Since a load only proceeds
    when it equals the template's, validating fixed CTA positions against it
    here is the same check the source landing already passed — it just also
    catches a template whose stored positions were never valid.
    """
    if not isinstance(raw_config, dict):
        raise LandingValidationError("config", "La plantilla no tiene una configuración válida.")

    cta_mode = raw_config.get("cta_mode")
    if not isinstance(cta_mode, str):
        raise LandingValidationError("cta_mode", "La plantilla no define el modo de CTA.")

    raw_positions = raw_config.get("cta_positions")
    positions = (
        [item for item in raw_positions if isinstance(item, int) and not isinstance(item, bool)]
        if isinstance(raw_positions, list)
        else None
    )
    raw_interval = raw_config.get("cta_interval")
    interval = (
        raw_interval
        if isinstance(raw_interval, int) and not isinstance(raw_interval, bool)
        else None
    )

    cta_config = validate_cta_config(
        cta_mode,
        interval=interval,
        positions=positions,
        # Fixed positions are bounded by the sequence they address. With no
        # banners on the target yet there is nothing to bound them against;
        # publication re-validates the stored configuration either way.
        banner_count=banner_count if banner_count > 0 else None,
    )

    offer_count = validate_offer_count(raw_config.get("offer_count"))
    default_offer_quantity = validate_default_offer_quantity(
        raw_config.get("default_offer_quantity", 1), offer_count=offer_count
    )
    offers = validate_offers(raw_config.get("offers"), offer_count=offer_count)

    raw_overrides = raw_config.get("cta_text_overrides")
    overrides: dict[object, object] = raw_overrides if isinstance(raw_overrides, dict) else {}
    raw_color_modes = raw_config.get("cta_color_modes")
    color_modes: dict[object, object] = raw_color_modes if isinstance(raw_color_modes, dict) else {}

    parsed: dict[str, Any] = {
        "cta_mode": cta_config.mode,
        "cta_interval": cta_config.interval,
        "cta_positions": sorted(cta_config.positions) if cta_config.positions else [],
        "cta_band_style": validate_cta_band_style(raw_config.get("cta_band_style") or "gradient"),
        "form_presentation": validate_form_presentation(
            raw_config.get("form_presentation") or "inline"
        ),
        "accent_color": normalize_accent_color(raw_config.get("accent_color") or "#1a7a4c"),
        "blocks_dark_mode": bool(raw_config.get("blocks_dark_mode")),
        "offer_count": offer_count,
        "default_offer_quantity": default_offer_quantity,
        "offers": [offer.to_json() for offer in offers],
        "cta_text_overrides": validate_cta_text_overrides(overrides),
        "cta_color_modes": validate_cta_color_modes(color_modes),
    }

    # `None` and `""` are different intentions for the nullable columns: absent
    # means "the template does not set this", empty string means "clear it".
    # Both end up as None on the landing, so they collapse here.
    form_accent = raw_config.get("form_accent_color")
    parsed["form_accent_color"] = (
        normalize_accent_color(form_accent, field="form_accent_color")
        if isinstance(form_accent, str) and form_accent.strip()
        else None
    )

    blocks_accent = raw_config.get("blocks_accent_color")
    parsed["blocks_accent_color"] = (
        normalize_accent_color(blocks_accent, field="blocks_accent_color")
        if isinstance(blocks_accent, str) and blocks_accent.strip()
        else None
    )

    cta_text = raw_config.get("cta_text")
    if isinstance(cta_text, str) and cta_text.strip():
        if len(cta_text) > OVERRIDE_TEXT_MAX:
            raise LandingValidationError(
                "cta_text",
                f"El texto del CTA no puede superar {OVERRIDE_TEXT_MAX} caracteres.",
            )
        parsed["cta_text"] = cta_text
    else:
        parsed["cta_text"] = None

    animation = raw_config.get("cta_animation")
    if isinstance(animation, str) and animation.strip():
        if animation not in _ALLOWED_CTA_ANIMATIONS:
            raise LandingValidationError(
                "cta_animation", f"Animación de CTA no soportada '{animation}'."
            )
        parsed["cta_animation"] = animation
    else:
        parsed["cta_animation"] = None

    return parsed


def parse_template_blocks(raw_blocks: Any) -> list[dict[str, Any]]:
    """Re-validate a stored `blocks` payload for application to a landing.

    Each entry is pushed back through the live block validators, so a template
    holding a component type that has since been renamed or removed fails at
    load rather than creating a row the editor cannot render. Placement
    collisions are resolved here too: the target's
    `(landing_id, slot_index, order_index)` is unique, so two template entries
    that somehow claim the same position would otherwise fail mid-write with a
    constraint error instead of a field message.
    """
    if raw_blocks is None:
        return []
    if not isinstance(raw_blocks, list):
        raise LandingValidationError("blocks", "La plantilla no tiene componentes válidos.")

    if len(raw_blocks) > MAX_BLOCKS_PER_LANDING:
        raise LandingValidationError(
            "blocks",
            f"La plantilla tiene más de {MAX_BLOCKS_PER_LANDING} componentes.",
        )

    parsed: list[dict[str, Any]] = []
    used_positions: set[tuple[int, int]] = set()

    for entry in raw_blocks:
        if not isinstance(entry, dict):
            raise LandingValidationError("blocks", "La plantilla tiene un componente inválido.")

        # Narrowed before validating so the sentinel — rather than an untyped
        # value — is what reaches the validator. Both sentinels are outside the
        # accepted set, so a missing or wrong-typed field still raises that
        # field's own error instead of a generic one.
        raw_type = entry.get("block_type")
        block_type = validate_block_type(raw_type if isinstance(raw_type, str) else "")

        raw_slot = entry.get("slot_index")
        slot_index = validate_slot_index(
            raw_slot if isinstance(raw_slot, int) and not isinstance(raw_slot, bool) else -1
        )

        config = validate_block_config(block_type, entry.get("config") or {})

        raw_order = entry.get("order_index")
        order_index = (
            raw_order if isinstance(raw_order, int) and not isinstance(raw_order, bool) else 0
        )
        order_index = max(0, min(MAX_ORDER_INDEX, order_index))

        # Two entries claiming one position is a corrupt template, not a
        # merchant mistake; take the next free order in that slot rather than
        # failing the whole load over a recoverable collision.
        while (slot_index, order_index) in used_positions:
            order_index += 1
            if order_index > MAX_ORDER_INDEX:
                raise LandingValidationError(
                    "blocks",
                    "La plantilla acumula demasiados componentes en una misma posición.",
                )

        used_positions.add((slot_index, order_index))
        parsed.append(
            {
                "block_type": block_type,
                "slot_index": slot_index,
                "order_index": order_index,
                "config": config,
                "enabled": bool(entry.get("enabled", True)),
            }
        )

    return parsed
