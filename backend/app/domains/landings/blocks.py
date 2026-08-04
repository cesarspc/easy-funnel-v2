"""Conversion components ("blocks") a Landing can place between its rendered
elements (Requirements 3.27-3.31).

Two ideas own this module:

**A fixed vocabulary, not a page builder.** Seven component types exist,
each one a device that measurably moves cold cash-on-delivery traffic in this
market: the COD assurance strip, benefit bullets, the price/saving statement,
the three-step "how it works" explainer, customer reviews, the FAQ objection
handler, and the guarantee. A merchant chooses a type, writes its content, and
places it. Nothing else is configurable, because everything else — spacing,
type scale, color, order of elements inside the component, mobile behavior —
is already decided in the Landing chrome for conversion. `config` therefore
carries content only; a key that would change presentation is rejected here
rather than quietly stored.

Deliberately absent: countdown timers and "only N left" counters. Both are
unverifiable by this platform, and against cold traffic that is being asked to
hand over a real address they cost more trust than they buy.

**Slots count rendered elements, not banners.** The public page renders a flat
sequence: banner 1, then a CTA band if position 1 is a CTA position, then
banner 2, and so on. `slot_index` is how many of those elements the block
follows, so slot 0 is above everything, slot 1 is between element 1 and element
2 (the dashboard's "1-2"), and slot `len(sequence)` is after the last element.
A slot beyond the current sequence still renders — at the end — so shortening a
banner sequence can never silently drop a component the merchant placed.

Pure functions only: no I/O, no Prisma. `LandingBlockService` composes these
with repositories.
"""

from __future__ import annotations

from typing import Any

from app.domains.landings.errors import LandingValidationError

BLOCK_COD_ASSURANCE = "cod_assurance"
BLOCK_BENEFITS = "benefits"
BLOCK_OFFER_PRICE = "offer_price"
BLOCK_HOW_IT_WORKS = "how_it_works"
BLOCK_REVIEWS = "reviews"
BLOCK_FAQ = "faq"
BLOCK_GUARANTEE = "guarantee"

# Mirrors the `landing_blocks_type_allowed` database check.
ALLOWED_BLOCK_TYPES = (
    BLOCK_COD_ASSURANCE,
    BLOCK_BENEFITS,
    BLOCK_OFFER_PRICE,
    BLOCK_HOW_IT_WORKS,
    BLOCK_REVIEWS,
    BLOCK_FAQ,
    BLOCK_GUARANTEE,
)

# 15 banners + one CTA band each is the longest sequence the page can render,
# and one slot past the end is a legal placement ("after everything").
MAX_SLOT_INDEX = 30
MAX_ORDER_INDEX = 9
MAX_BLOCKS_PER_LANDING = 12

_NOTE_MAX = 140
_ITEM_MAX = 90
_STEP_MAX = 110
_NAME_MAX = 60
_CITY_MAX = 60
_REVIEW_MAX = 280
_QUESTION_MAX = 140
_ANSWER_MAX = 500
_TITLE_MAX = 80
_TEXT_MAX = 320

MAX_BENEFITS = 5
MIN_BENEFITS = 2
HOW_IT_WORKS_STEPS = 3
MAX_REVIEWS = 4
MAX_FAQ_ITEMS = 6
MAX_GUARANTEE_DAYS = 365


def validate_block_type(raw_type: str) -> str:
    """Return the block type unchanged, or raise for one outside the vocabulary."""
    if raw_type not in ALLOWED_BLOCK_TYPES:
        raise LandingValidationError(
            "block_type",
            "Component type must be one of: " + ", ".join(ALLOWED_BLOCK_TYPES) + ".",
        )
    return raw_type


def validate_slot_index(raw_slot: int) -> int:
    """Return the slot index unchanged, or raise when outside the sequence bounds.

    The bound is the longest sequence the page can render, not the landing's
    current one: a merchant may place a component in slot 6 while building
    toward six elements, and publication does not depend on the slot being
    occupied.
    """
    if (
        not isinstance(raw_slot, bool)
        and isinstance(raw_slot, int)
        and 0 <= raw_slot <= MAX_SLOT_INDEX
    ):
        return raw_slot
    raise LandingValidationError(
        "slot_index",
        f"Position must be a whole number between 0 and {MAX_SLOT_INDEX}.",
    )


def validate_order_index(raw_order: int) -> int:
    """Return the within-slot order unchanged, or raise when out of range."""
    if (
        not isinstance(raw_order, bool)
        and isinstance(raw_order, int)
        and 0 <= raw_order <= MAX_ORDER_INDEX
    ):
        return raw_order
    raise LandingValidationError(
        "order_index",
        f"Order within a position must be a whole number between 0 and {MAX_ORDER_INDEX}.",
    )


def validate_can_add_block(existing_count: int) -> None:
    """Raise when a landing already holds the maximum number of components."""
    if existing_count >= MAX_BLOCKS_PER_LANDING:
        raise LandingValidationError(
            "block_type",
            f"A landing can hold at most {MAX_BLOCKS_PER_LANDING} conversion components.",
        )


def slot_labels(banner_count: int, cta_positions: list[int] | tuple[int, ...]) -> list[str]:
    """Describe every placement slot of a rendered sequence, in render order.

    Returns one label per slot, index 0 first. The labels name the two elements
    a slot sits between the way the dashboard shows them ("1-2"), so the
    Administrator picks a position without having to reconstruct where CTA
    bands land.

    This mirrors the public page's own sequence construction: a CTA band is
    rendered after banner `n` when `n` is a CTA position, and after the last
    banner when the last position is not already a CTA position.
    """
    elements: list[str] = []
    positions = set(cta_positions)
    for banner_number in range(1, banner_count + 1):
        elements.append(f"banner {banner_number}")
        if banner_number in positions:
            elements.append(f"CTA {len([e for e in elements if e.startswith('CTA')]) + 1}")
    if banner_count > 0 and banner_count not in positions:
        elements.append(f"CTA {len([e for e in elements if e.startswith('CTA')]) + 1}")

    labels = ["0-1 · antes de " + (elements[0] if elements else "el primer elemento")]
    for index, element in enumerate(elements, start=1):
        following = elements[index] if index < len(elements) else "el final"
        labels.append(f"{index}-{index + 1} · entre {element} y {following}")
    return labels


def _require_text(value: Any, *, field: str, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise LandingValidationError(field, f"{label} is required.")
    text = value.strip()
    if not text:
        raise LandingValidationError(field, f"{label} is required.")
    if len(text) > maximum:
        raise LandingValidationError(field, f"{label} must be at most {maximum} characters.")
    return text


def _optional_text(value: Any, *, field: str, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LandingValidationError(field, f"{label} must be text.")
    text = value.strip()
    if not text:
        return None
    if len(text) > maximum:
        raise LandingValidationError(field, f"{label} must be at most {maximum} characters.")
    return text


def _require_list(value: Any, *, field: str, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise LandingValidationError(field, f"{label} needs at least one entry.")
    return value


def _validate_cod_assurance(config: dict[str, Any]) -> dict[str, Any]:
    """COD assurance strip: the three assurances are fixed copy in the chrome.

    Only an optional merchant note is configurable, because the three points
    that carry this block (pay on delivery, check before paying, no card) are
    facts about the platform, not claims a merchant should be able to reword
    into something the platform does not do.
    """
    return {
        "note": _optional_text(config.get("note"), field="note", label="Note", maximum=_NOTE_MAX)
    }


def _validate_benefits(config: dict[str, Any]) -> dict[str, Any]:
    raw_items = _require_list(config.get("items"), field="items", label="Benefits")
    if len(raw_items) < MIN_BENEFITS or len(raw_items) > MAX_BENEFITS:
        raise LandingValidationError(
            "items", f"Add between {MIN_BENEFITS} and {MAX_BENEFITS} benefits."
        )
    items = [
        _require_text(item, field="items", label=f"Benefit {index + 1}", maximum=_ITEM_MAX)
        for index, item in enumerate(raw_items)
    ]
    return {
        "title": _optional_text(
            config.get("title"), field="title", label="Title", maximum=_TITLE_MAX
        ),
        "items": items,
    }


def _validate_offer_price(config: dict[str, Any]) -> dict[str, Any]:
    """Price statement. The selling price always comes from the Product, so it
    cannot drift from what the order is charged; only the merchant's own
    reference ("was") price and an optional note live here.
    """
    raw_compare = config.get("compare_at_price")
    compare_at_price: float | None = None
    if raw_compare is not None and raw_compare != "":
        try:
            compare_at_price = float(raw_compare)
        except (TypeError, ValueError) as exc:
            raise LandingValidationError(
                "compare_at_price", "Reference price must be a number."
            ) from exc
        if compare_at_price <= 0:
            raise LandingValidationError(
                "compare_at_price", "Reference price must be greater than zero."
            )
    return {
        "compare_at_price": compare_at_price,
        "note": _optional_text(config.get("note"), field="note", label="Note", maximum=_NOTE_MAX),
    }


def _validate_how_it_works(config: dict[str, Any]) -> dict[str, Any]:
    raw_steps = _require_list(config.get("steps"), field="steps", label="Steps")
    if len(raw_steps) != HOW_IT_WORKS_STEPS:
        raise LandingValidationError("steps", f"Describe exactly {HOW_IT_WORKS_STEPS} steps.")
    steps = [
        _require_text(step, field="steps", label=f"Step {index + 1}", maximum=_STEP_MAX)
        for index, step in enumerate(raw_steps)
    ]
    return {
        "title": _optional_text(
            config.get("title"), field="title", label="Title", maximum=_TITLE_MAX
        ),
        "steps": steps,
    }


def _validate_reviews(config: dict[str, Any]) -> dict[str, Any]:
    raw_items = _require_list(config.get("items"), field="items", label="Reviews")
    if len(raw_items) > MAX_REVIEWS:
        raise LandingValidationError("items", f"Add at most {MAX_REVIEWS} reviews.")

    items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise LandingValidationError("items", f"Review {index + 1} is incomplete.")
        rating_raw = raw_item.get("rating")
        rating: int | None = None
        if rating_raw is not None and rating_raw != "":
            try:
                rating = int(rating_raw)
            except (TypeError, ValueError) as exc:
                raise LandingValidationError(
                    "items", f"Review {index + 1}: rating must be a whole number from 1 to 5."
                ) from exc
            if rating < 1 or rating > 5:
                raise LandingValidationError(
                    "items", f"Review {index + 1}: rating must be from 1 to 5."
                )
        items.append(
            {
                "name": _require_text(
                    raw_item.get("name"),
                    field="items",
                    label=f"Review {index + 1}: name",
                    maximum=_NAME_MAX,
                ),
                "city": _optional_text(
                    raw_item.get("city"),
                    field="items",
                    label=f"Review {index + 1}: city",
                    maximum=_CITY_MAX,
                ),
                "text": _require_text(
                    raw_item.get("text"),
                    field="items",
                    label=f"Review {index + 1}: text",
                    maximum=_REVIEW_MAX,
                ),
                "rating": rating,
            }
        )
    return {
        "title": _optional_text(
            config.get("title"), field="title", label="Title", maximum=_TITLE_MAX
        ),
        "items": items,
    }


def _validate_faq(config: dict[str, Any]) -> dict[str, Any]:
    raw_items = _require_list(config.get("items"), field="items", label="Questions")
    if len(raw_items) > MAX_FAQ_ITEMS:
        raise LandingValidationError("items", f"Add at most {MAX_FAQ_ITEMS} questions.")

    items: list[dict[str, str]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise LandingValidationError("items", f"Question {index + 1} is incomplete.")
        items.append(
            {
                "question": _require_text(
                    raw_item.get("question"),
                    field="items",
                    label=f"Question {index + 1}",
                    maximum=_QUESTION_MAX,
                ),
                "answer": _require_text(
                    raw_item.get("answer"),
                    field="items",
                    label=f"Answer {index + 1}",
                    maximum=_ANSWER_MAX,
                ),
            }
        )
    return {
        "title": _optional_text(
            config.get("title"), field="title", label="Title", maximum=_TITLE_MAX
        ),
        "items": items,
    }


def _validate_guarantee(config: dict[str, Any]) -> dict[str, Any]:
    raw_days = config.get("days")
    days: int | None = None
    if raw_days is not None and raw_days != "":
        try:
            days = int(raw_days)
        except (TypeError, ValueError) as exc:
            raise LandingValidationError("days", "Days must be a whole number.") from exc
        if days < 1 or days > MAX_GUARANTEE_DAYS:
            raise LandingValidationError(
                "days", f"Days must be between 1 and {MAX_GUARANTEE_DAYS}."
            )
    return {
        "title": _require_text(
            config.get("title"), field="title", label="Title", maximum=_TITLE_MAX
        ),
        "text": _require_text(config.get("text"), field="text", label="Text", maximum=_TEXT_MAX),
        "days": days,
    }


_VALIDATORS = {
    BLOCK_COD_ASSURANCE: _validate_cod_assurance,
    BLOCK_BENEFITS: _validate_benefits,
    BLOCK_OFFER_PRICE: _validate_offer_price,
    BLOCK_HOW_IT_WORKS: _validate_how_it_works,
    BLOCK_REVIEWS: _validate_reviews,
    BLOCK_FAQ: _validate_faq,
    BLOCK_GUARANTEE: _validate_guarantee,
}


def validate_block_config(block_type: str, raw_config: Any) -> dict[str, Any]:
    """Normalize and validate one component's content for `block_type`.

    Returns a dict containing exactly the keys that type supports, with text
    trimmed and numbers coerced — so what is stored is what the renderer reads,
    and an unknown key (including any attempt to pass presentation) is dropped
    rather than persisted. Raises `LandingValidationError` with the offending
    field so the dashboard can bind the message to its control
    (Requirement 8.19).
    """
    validate_block_type(block_type)
    if raw_config is None:
        config: dict[str, Any] = {}
    elif isinstance(raw_config, dict):
        config = raw_config
    else:
        raise LandingValidationError("config", "Component content must be an object.")

    return _VALIDATORS[block_type](config)
