"""Conversion components ("blocks") a Landing can place between its rendered
elements (Requirements 3.27-3.31).

Two ideas own this module:

**A fixed vocabulary, not a page builder.** Thirteen component types exist,
each one a device that measurably moves cold cash-on-delivery traffic in this
market: a top-of-page announcement bar, the COD assurance strip, benefit
bullets, the price/saving statement, the included benefits list,
customer reviews, the FAQ objection handler, and the guarantee. A merchant
chooses a type, writes its content, and places it. Almost nothing else is
configurable — spacing, type scale, layout, order of elements inside the
component, mobile behavior are already decided in the Landing chrome for
conversion. The one exception is `accent_color`: every type accepts the same
optional hex field so a merchant can match (or intentionally break) a
component's buttons/lines against the rest of the page, defaulting to the
landing's form accent when unset. That single knob does not turn this into a
page builder — it is one more bounded content field, validated the same way
`compare_at_price` or `days` are. Any other key that would change presentation
is rejected here rather than quietly stored.

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

from app.domains.landings.accent_color import normalize_accent_color
from app.domains.landings.errors import LandingValidationError

BLOCK_COD_ASSURANCE = "cod_assurance"
BLOCK_BENEFITS = "benefits"
BLOCK_OFFER_PRICE = "offer_price"
BLOCK_INCLUDED_BENEFITS = "included_benefits"
BLOCK_REVIEWS = "reviews"
BLOCK_FAQ = "faq"
BLOCK_GUARANTEE = "guarantee"
BLOCK_ANNOUNCEMENT_BAR = "announcement_bar"
BLOCK_MAIN_PROBLEM = "main_problem"
BLOCK_SOLUTION_PRESENTATION = "solution_presentation"
BLOCK_HOW_IT_WORKS = "how_it_works"
BLOCK_AUDIENCE = "audience"
BLOCK_MOMENT = "moment"

# Mirrors the `landing_blocks_type_allowed` database check.
ALLOWED_BLOCK_TYPES = (
    BLOCK_COD_ASSURANCE,
    BLOCK_BENEFITS,
    BLOCK_OFFER_PRICE,
    BLOCK_INCLUDED_BENEFITS,
    BLOCK_REVIEWS,
    BLOCK_FAQ,
    BLOCK_GUARANTEE,
    BLOCK_ANNOUNCEMENT_BAR,
    BLOCK_MAIN_PROBLEM,
    BLOCK_SOLUTION_PRESENTATION,
    BLOCK_HOW_IT_WORKS,
    BLOCK_AUDIENCE,
    BLOCK_MOMENT,
)

# 15 banners + one CTA band each is the longest sequence the page can render,
# and one slot past the end is a legal placement ("after everything").
MAX_SLOT_INDEX = 30
MAX_ORDER_INDEX = 9
MAX_BLOCKS_PER_LANDING = 20

_NOTE_MAX = 140
_ITEM_MAX = 90
_NAME_MAX = 60
_CITY_MAX = 60
_REVIEW_MAX = 280
_QUESTION_MAX = 140
_ANSWER_MAX = 500
_TITLE_MAX = 80
_TEXT_MAX = 320

MAX_BENEFITS = 5
MIN_BENEFITS = 2
MIN_INCLUDED_BENEFITS = 2
MAX_INCLUDED_BENEFITS = 8
_BENEFIT_NAME_MAX = 90
_BENEFIT_VALUE_MAX = 40
_BENEFIT_TAG_MAX = 20
MAX_REVIEWS = 4
MAX_FAQ_ITEMS = 6
MAX_GUARANTEE_DAYS = 365
MAX_STORY_CARDS = 6
MAX_STEPS = 10
MAX_AUDIENCE_ITEMS = 10
MAX_GUARANTEE_BENEFITS = 4
_LONG_TITLE_MAX = 160
_CARD_TEXT_MAX = 280
_KICKER_MAX = 60


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


def _optional_accent_color(config: dict[str, Any]) -> str | None:
    """Return the component's own accent override, or `None` to inherit.

    `None` means "use the landing's form accent" — the default this feature
    exists to express — so an absent or blank value is not an error, unlike
    every other color field in this codebase which is either required or
    fully absent from the vocabulary. Reuses `normalize_accent_color` so this
    field can never disagree with the format the CTA/form accent already
    enforces (`#rrggbb`, shorthand expanded).
    """
    raw = config.get("accent_color")
    if raw is None or raw == "":
        return None
    return normalize_accent_color(raw, field="accent_color")


def _optional_dark_mode(config: dict[str, Any]) -> bool | None:
    """Return an explicit block override, or ``None`` to inherit the Landing.

    This must remain tri-state. Normalizing an absent value to ``False`` would
    make every untouched block force light mode and bypass ``blocksDarkMode``.
    """
    raw = config.get("dark_mode")
    if raw is None or raw == "":
        return None
    if raw is True or raw in ("true", "1", "dark"):
        return True
    if raw is False or raw in ("false", "0", "light"):
        return False
    raise LandingValidationError(
        "dark_mode", "Dark mode must inherit the landing, always light, or always dark."
    )


def _validate_announcement_bar(config: dict[str, Any]) -> dict[str, Any]:
    """Top-of-page announcement bar: one line of text, own accent background.

    Deliberately the smallest component in the vocabulary — a single required
    line, because a bar competing for attention with the hero banner should not
    grow into a second headline. `accent_color` here doubles as the bar's own
    background (not just its buttons/lines), since the bar has no button —
    it *is* the accent surface.
    """
    return {
        "text": _require_text(
            config.get("text"), field="text", label="Announcement text", maximum=_TITLE_MAX
        ),
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
    }


def _validate_cod_assurance(config: dict[str, Any]) -> dict[str, Any]:
    """COD assurance strip: the three assurances are fixed copy in the chrome.

    Only an optional merchant note is configurable, because the three points
    that carry this block (pay on delivery, check before paying, no card) are
    facts about the platform, not claims a merchant should be able to reword
    into something the platform does not do.
    """
    return {
        "note": _optional_text(config.get("note"), field="note", label="Note", maximum=_NOTE_MAX),
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
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
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
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
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
    }


def _validate_included_benefits(config: dict[str, Any]) -> dict[str, Any]:
    """Included benefits/items list: what the buyer gets, optionally with a
    crossed-out value and a highlight tag per item.

    Schema:
      title: optional (max 80)
      items: required list of 2-8 objects, each with:
        name: required (max 90)
        value: optional (max 40)
        tag: optional (max 20)
      accent_color: optional
    """
    raw_items = _require_list(config.get("items"), field="items", label="Items")
    if len(raw_items) < MIN_INCLUDED_BENEFITS or len(raw_items) > MAX_INCLUDED_BENEFITS:
        raise LandingValidationError(
            "items",
            f"Add between {MIN_INCLUDED_BENEFITS} and {MAX_INCLUDED_BENEFITS} items.",
        )

    items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise LandingValidationError("items", f"Item {index + 1} must be an object.")
        items.append(
            {
                "name": _require_text(
                    raw_item.get("name"),
                    field="items",
                    label=f"Item {index + 1}: name",
                    maximum=_BENEFIT_NAME_MAX,
                ),
                "value": _optional_text(
                    raw_item.get("value"),
                    field="items",
                    label=f"Item {index + 1}: value",
                    maximum=_BENEFIT_VALUE_MAX,
                ),
                "tag": _optional_text(
                    raw_item.get("tag"),
                    field="items",
                    label=f"Item {index + 1}: tag",
                    maximum=_BENEFIT_TAG_MAX,
                ),
            }
        )
    return {
        "title": _optional_text(
            config.get("title"), field="title", label="Title", maximum=_TITLE_MAX
        ),
        "items": items,
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
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
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
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
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
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
    raw_benefits = config.get("benefits")
    benefits = (
        []
        if raw_benefits in (None, [])
        else _validate_card_items(
            raw_benefits,
            field="benefits",
            label="Guarantee benefit",
            minimum=1,
            maximum=MAX_GUARANTEE_BENEFITS,
            text_required=False,
        )
    )
    return {
        "title": _require_text(
            config.get("title"), field="title", label="Title", maximum=_TITLE_MAX
        ),
        "text": _require_text(config.get("text"), field="text", label="Text", maximum=_TEXT_MAX),
        "days": days,
        "eyebrow": _optional_text(
            config.get("eyebrow"), field="eyebrow", label="Eyebrow", maximum=_KICKER_MAX
        ),
        "benefits": benefits,
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
    }


def _validate_card_items(
    raw_items: Any,
    *,
    field: str,
    label: str,
    minimum: int,
    maximum: int,
    text_required: bool = True,
    include_kicker: bool = False,
) -> list[dict[str, str | None]]:
    items = _require_list(raw_items, field=field, label=label)
    if len(items) < minimum or len(items) > maximum:
        raise LandingValidationError(
            field, f"Add between {minimum} and {maximum} {label.lower()}s."
        )
    result: list[dict[str, str | None]] = []
    for index, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            raise LandingValidationError(field, f"{label} {index + 1} is incomplete.")
        item: dict[str, str | None] = {
            "title": _require_text(
                raw_item.get("title"),
                field=field,
                label=f"{label} {index + 1}: title",
                maximum=_TITLE_MAX,
            ),
            "text": (
                _require_text(
                    raw_item.get("text"),
                    field=field,
                    label=f"{label} {index + 1}: text",
                    maximum=_CARD_TEXT_MAX,
                )
                if text_required
                else _optional_text(
                    raw_item.get("text"),
                    field=field,
                    label=f"{label} {index + 1}: text",
                    maximum=_CARD_TEXT_MAX,
                )
            ),
        }
        if include_kicker:
            item["kicker"] = _optional_text(
                raw_item.get("kicker"),
                field=field,
                label=f"{label} {index + 1}: label",
                maximum=_KICKER_MAX,
            )
        result.append(item)
    return result


def _validate_string_items(
    raw_items: Any, *, field: str, label: str, minimum: int, maximum: int
) -> list[str]:
    items = _require_list(raw_items, field=field, label=label)
    if len(items) < minimum or len(items) > maximum:
        raise LandingValidationError(
            field, f"Add between {minimum} and {maximum} {label.lower()}s."
        )
    return [
        _require_text(item, field=field, label=f"{label} {index + 1}", maximum=_ITEM_MAX)
        for index, item in enumerate(items)
    ]


def _shared_story_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "accent_color": _optional_accent_color(config),
        "dark_mode": _optional_dark_mode(config),
    }


def _validate_main_problem(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "eyebrow": _optional_text(
            config.get("eyebrow"), field="eyebrow", label="Eyebrow", maximum=_KICKER_MAX
        ),
        "title": _require_text(
            config.get("title"), field="title", label="Title", maximum=_LONG_TITLE_MAX
        ),
        "highlight": _optional_text(
            config.get("highlight"),
            field="highlight",
            label="Highlighted title",
            maximum=_LONG_TITLE_MAX,
        ),
        "subtitle": _optional_text(
            config.get("subtitle"), field="subtitle", label="Subtitle", maximum=_TEXT_MAX
        ),
        "items": _validate_card_items(
            config.get("items"),
            field="items",
            label="Problem",
            minimum=1,
            maximum=MAX_STORY_CARDS,
        ),
        **_shared_story_config(config),
    }


def _validate_solution_presentation(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "bridge_text": _optional_text(
            config.get("bridge_text"),
            field="bridge_text",
            label="Bridge text",
            maximum=_TEXT_MAX,
        ),
        "eyebrow": _optional_text(
            config.get("eyebrow"), field="eyebrow", label="Eyebrow", maximum=_KICKER_MAX
        ),
        "title": _require_text(
            config.get("title"), field="title", label="Title", maximum=_LONG_TITLE_MAX
        ),
        "highlight": _optional_text(
            config.get("highlight"),
            field="highlight",
            label="Highlighted title",
            maximum=_LONG_TITLE_MAX,
        ),
        "text": _require_text(config.get("text"), field="text", label="Description", maximum=500),
        "supporting_text": _optional_text(
            config.get("supporting_text"),
            field="supporting_text",
            label="Supporting text",
            maximum=500,
        ),
        "items": _validate_card_items(
            config.get("items"),
            field="items",
            label="Solution card",
            minimum=1,
            maximum=MAX_STORY_CARDS,
            include_kicker=True,
        ),
        "final_title": _optional_text(
            config.get("final_title"),
            field="final_title",
            label="Final title",
            maximum=_LONG_TITLE_MAX,
        ),
        "final_highlight": _optional_text(
            config.get("final_highlight"),
            field="final_highlight",
            label="Final highlight",
            maximum=_LONG_TITLE_MAX,
        ),
        **_shared_story_config(config),
    }


def _validate_how_it_works(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _require_text(
            config.get("title"), field="title", label="Title", maximum=_LONG_TITLE_MAX
        ),
        "highlight": _optional_text(
            config.get("highlight"), field="highlight", label="Highlight", maximum=_LONG_TITLE_MAX
        ),
        "subtitle": _optional_text(
            config.get("subtitle"), field="subtitle", label="Subtitle", maximum=_TEXT_MAX
        ),
        "steps": _validate_card_items(
            config.get("steps"),
            field="steps",
            label="Step",
            minimum=1,
            maximum=MAX_STEPS,
            include_kicker=True,
        ),
        **_shared_story_config(config),
    }


def _validate_audience(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _require_text(
            config.get("title"), field="title", label="Title", maximum=_LONG_TITLE_MAX
        ),
        "highlight": _optional_text(
            config.get("highlight"), field="highlight", label="Highlight", maximum=_LONG_TITLE_MAX
        ),
        "positive_title": _require_text(
            config.get("positive_title"),
            field="positive_title",
            label="Positive column title",
            maximum=_TITLE_MAX,
        ),
        "positive_subtitle": _optional_text(
            config.get("positive_subtitle"),
            field="positive_subtitle",
            label="Positive column subtitle",
            maximum=_NOTE_MAX,
        ),
        "positive_items": _validate_string_items(
            config.get("positive_items"),
            field="positive_items",
            label="Positive item",
            minimum=1,
            maximum=MAX_AUDIENCE_ITEMS,
        ),
        "negative_title": _require_text(
            config.get("negative_title"),
            field="negative_title",
            label="Negative column title",
            maximum=_TITLE_MAX,
        ),
        "negative_subtitle": _optional_text(
            config.get("negative_subtitle"),
            field="negative_subtitle",
            label="Negative column subtitle",
            maximum=_NOTE_MAX,
        ),
        "negative_items": _validate_string_items(
            config.get("negative_items"),
            field="negative_items",
            label="Negative item",
            minimum=1,
            maximum=MAX_AUDIENCE_ITEMS,
        ),
        "footer": _optional_text(
            config.get("footer"), field="footer", label="Footer", maximum=_TEXT_MAX
        ),
        **_shared_story_config(config),
    }


def _validate_moment(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _require_text(
            config.get("title"), field="title", label="Title", maximum=_LONG_TITLE_MAX
        ),
        "highlight": _require_text(
            config.get("highlight"), field="highlight", label="Highlight", maximum=_LONG_TITLE_MAX
        ),
        "text": _require_text(config.get("text"), field="text", label="Text", maximum=_TEXT_MAX),
        "emphasis": _optional_text(
            config.get("emphasis"), field="emphasis", label="Emphasis", maximum=_TEXT_MAX
        ),
        "footer": _optional_text(
            config.get("footer"), field="footer", label="Footer", maximum=_TEXT_MAX
        ),
        **_shared_story_config(config),
    }


_VALIDATORS = {
    BLOCK_COD_ASSURANCE: _validate_cod_assurance,
    BLOCK_BENEFITS: _validate_benefits,
    BLOCK_OFFER_PRICE: _validate_offer_price,
    BLOCK_INCLUDED_BENEFITS: _validate_included_benefits,
    BLOCK_REVIEWS: _validate_reviews,
    BLOCK_FAQ: _validate_faq,
    BLOCK_GUARANTEE: _validate_guarantee,
    BLOCK_ANNOUNCEMENT_BAR: _validate_announcement_bar,
    BLOCK_MAIN_PROBLEM: _validate_main_problem,
    BLOCK_SOLUTION_PRESENTATION: _validate_solution_presentation,
    BLOCK_HOW_IT_WORKS: _validate_how_it_works,
    BLOCK_AUDIENCE: _validate_audience,
    BLOCK_MOMENT: _validate_moment,
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
