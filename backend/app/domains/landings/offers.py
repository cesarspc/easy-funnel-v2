"""Quantity offers for a Landing's COD form (offer count, copy, discounts).

The COD form asks "how many?" as a short list of price tiers rather than a
number field, because a buyer choosing between three priced options converts
better than one typing a digit. This module owns what those tiers are.

**What a merchant controls.** How many tiers appear (1, 2, or 3), the headline
and optional sub-line for each, either a percentage or exact COP discount on
the multi-unit tiers, and an informational "was" price on the single-unit tier. Nothing else: the
tiles' spacing, type, selected state, and which tier carries the "most ordered"
mark are fixed in the Landing chrome, for the same reason conversion components
are (see `blocks.py`).

**Why discounts are different from every other landing setting.** A discount is
the one merchant-editable value that changes what a buyer owes, and this is a
cash-on-delivery product: a courier arrives and collects a number. So
`resolve_offer_pricing` is not just for display — `OrderSubmissionService` calls
it at submission and snapshots the result onto the order. Editing a discount
afterwards changes future orders only, never the amount already agreed with a
buyer who has an order in the system.

**Why the single-unit tier gets `compare_at_price` and the others get a real
discount.** They answer different questions. On one unit there is no
volume saving to show, so the only honest anchor is the merchant's own reference
price ("normally $X"), which is informational and never charged. On two or three
units the saving is real and computable from the unit price, so it is expressed
as a percentage that actually reduces the total. Allowing both on the same tier
would let a landing advertise a discount off an invented "was" price, which is
exactly the pattern cold COD traffic is right to distrust.

Pure functions only: no I/O, no Prisma. `LandingManagementService` and
`OrderSubmissionService` compose these with repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.domains.landings.errors import LandingValidationError

#: The form shows at most three tiers. More than three turns a quick decision
#: into a comparison table, and the quantity field it replaces only ever
#: offered 1-3.
MIN_OFFER_COUNT = 1
MAX_OFFER_COUNT = 3

#: A tier headline ("2 unidades", "Pack x2 + envío gratis"). Short by design:
#: it sits on one line of a tile next to a price on a phone.
LABEL_MAX = 60

#: The optional second line ("Ahorra 15%", "El más pedido"). Blank means the
#: tile renders without a sub-line at all.
SUBLABEL_MAX = 80

#: Effective discounts are capped well below 100 so a rounding or typo cannot
#: produce a free or negative order. This applies to entered percentages and
#: the percentage derived from a fixed COP amount.
MIN_DISCOUNT_PERCENT = 0
MAX_DISCOUNT_PERCENT = 90

#: Quantities that may carry a discount: the multi-unit tiers only.
DISCOUNTABLE_MIN_QUANTITY = 2

_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class LandingOffer:
    """One quantity tier as the merchant configured it."""

    quantity: int
    label: str
    sublabel: str | None
    discount_percent: int
    discount_amount: Decimal | None = None
    compare_at_price: Decimal | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize for the `landings.offers` jsonb column."""
        return {
            "quantity": self.quantity,
            "label": self.label,
            "sublabel": self.sublabel,
            "discount_percent": self.discount_percent,
            "discount_amount": (
                None if self.discount_amount is None else str(self.discount_amount)
            ),
            "compare_at_price": (
                None if self.compare_at_price is None else str(self.compare_at_price)
            ),
        }


@dataclass(frozen=True)
class OfferPricing:
    """What a tier costs, resolved against a concrete unit price.

    `total` is the amount owed and the value an order snapshots. `gross` and
    `savings` exist so the page can show the discount honestly (struck-through
    original next to the real total) without recomputing it client-side.
    """

    quantity: int
    unit_price: Decimal
    discount_percent: int
    gross: Decimal
    total: Decimal
    savings: Decimal
    compare_at_price: Decimal | None


def validate_offer_count(raw_count: Any) -> int:
    """Return the tier count, or raise for anything outside 1-3."""
    if isinstance(raw_count, bool) or not isinstance(raw_count, int):
        try:
            count = int(str(raw_count).strip())
        except (TypeError, ValueError) as exc:
            raise LandingValidationError(
                "offer_count", "Number of offers must be a whole number."
            ) from exc
    else:
        count = raw_count

    if count < MIN_OFFER_COUNT or count > MAX_OFFER_COUNT:
        raise LandingValidationError(
            "offer_count",
            f"Number of offers must be between {MIN_OFFER_COUNT} and {MAX_OFFER_COUNT}.",
        )
    return count


def validate_default_offer_quantity(raw_quantity: Any, *, offer_count: int) -> int:
    """Return a default tier that is present in the configured 1..N offers."""
    if isinstance(raw_quantity, bool) or not isinstance(raw_quantity, int):
        raise LandingValidationError(
            "default_offer_quantity", "Default offer must be a whole quantity."
        )
    if raw_quantity < 1 or raw_quantity > offer_count:
        raise LandingValidationError(
            "default_offer_quantity", "Default offer must be one of the visible offers."
        )
    return raw_quantity


def default_offers(offer_count: int) -> list[LandingOffer]:
    """Build the tiers a landing gets before a merchant edits any copy.

    Matches the wording the COD form hardcoded before offers were
    configurable, so turning this feature on changes nothing a visitor sees
    until the merchant actually edits something.
    """
    count = validate_offer_count(offer_count)
    return [
        LandingOffer(
            quantity=quantity,
            label=f"{quantity} unidad" if quantity == 1 else f"{quantity} unidades",
            sublabel=None,
            discount_percent=0,
            discount_amount=None,
            compare_at_price=None,
        )
        for quantity in range(1, count + 1)
    ]


def validate_offers(raw_offers: Any, *, offer_count: int) -> list[LandingOffer]:
    """Validate the merchant's tier list against the configured count.

    An empty list is legal and means "use the defaults", which is how a landing
    created before this feature (or one that only changed its count) keeps
    working. Anything non-empty must describe every quantity from 1 to
    `offer_count` exactly once, so the form can never render a tier with no copy
    or two tiles for the same quantity.
    """
    count = validate_offer_count(offer_count)

    if raw_offers is None:
        return default_offers(count)
    if not isinstance(raw_offers, list):
        raise LandingValidationError("offers", "Offers must be a list.")
    if not raw_offers:
        return default_offers(count)

    if len(raw_offers) != count:
        raise LandingValidationError(
            "offers",
            f"Describe exactly {count} offer(s) to match the configured number of offers.",
        )

    offers: list[LandingOffer] = []
    seen: set[int] = set()
    for index, raw_offer in enumerate(raw_offers):
        position = index + 1
        if not isinstance(raw_offer, dict):
            raise LandingValidationError("offers", f"Offer {position} is incomplete.")

        quantity = _validate_quantity(raw_offer.get("quantity"), position=position, maximum=count)
        if quantity in seen:
            raise LandingValidationError(
                "offers", f"Offer {position}: quantity {quantity} is already used."
            )
        seen.add(quantity)

        discount_percent = _validate_discount_percent(
            raw_offer.get("discount_percent"), position=position, quantity=quantity
        )
        discount_amount = _validate_discount_amount(
            raw_offer.get("discount_amount"), position=position, quantity=quantity
        )
        if discount_percent and discount_amount is not None:
            raise LandingValidationError(
                "offers",
                f"Offer {position}: use either a percentage or a fixed discount, not both.",
            )

        offers.append(
            LandingOffer(
                quantity=quantity,
                label=_require_offer_text(
                    raw_offer.get("label"),
                    position=position,
                    label="Offer text",
                    maximum=LABEL_MAX,
                ),
                sublabel=_optional_offer_text(
                    raw_offer.get("sublabel"),
                    position=position,
                    label="Offer sub-text",
                    maximum=SUBLABEL_MAX,
                ),
                discount_percent=discount_percent,
                discount_amount=discount_amount,
                compare_at_price=_validate_compare_at_price(
                    raw_offer.get("compare_at_price"), position=position, quantity=quantity
                ),
            )
        )

    missing = sorted(set(range(1, count + 1)) - seen)
    if missing:
        raise LandingValidationError(
            "offers",
            "Offers must cover every quantity from 1 to "
            f"{count}; missing {', '.join(str(item) for item in missing)}.",
        )

    return sorted(offers, key=lambda offer: offer.quantity)


def parse_stored_offers(raw_offers: Any, *, offer_count: int) -> list[LandingOffer]:
    """Read the `offers` column for display, tolerating legacy/partial rows.

    Unlike `validate_offers` this never raises: a stored value that no longer
    matches the current `offer_count` (a merchant lowered the count, or the
    column predates this feature) falls back to generated defaults so the public
    page and the dashboard both still render. Writes always go through
    `validate_offers`.
    """
    try:
        count = validate_offer_count(offer_count)
    except LandingValidationError:
        count = MAX_OFFER_COUNT

    if not isinstance(raw_offers, list) or not raw_offers:
        return default_offers(count)

    try:
        return validate_offers(raw_offers, offer_count=count)
    except LandingValidationError:
        # Salvage per-tier copy where possible rather than throwing away
        # everything the merchant wrote because one field drifted.
        salvaged: list[LandingOffer] = []
        by_quantity = {item.get("quantity"): item for item in raw_offers if isinstance(item, dict)}
        for offer in default_offers(count):
            stored = by_quantity.get(offer.quantity)
            if not isinstance(stored, dict):
                salvaged.append(offer)
                continue
            salvaged.append(
                LandingOffer(
                    quantity=offer.quantity,
                    label=_safe_text(stored.get("label"), LABEL_MAX) or offer.label,
                    sublabel=_safe_text(stored.get("sublabel"), SUBLABEL_MAX),
                    discount_percent=_safe_discount(
                        stored.get("discount_percent"), quantity=offer.quantity
                    ),
                    discount_amount=_safe_discount_amount(
                        stored.get("discount_amount"), quantity=offer.quantity
                    ),
                    compare_at_price=_safe_price(stored.get("compare_at_price"))
                    if offer.quantity == 1
                    else None,
                )
            )
        return salvaged


def resolve_offer_pricing(
    unit_price: Decimal | str | int | float, offer: LandingOffer
) -> OfferPricing:
    """Price one tier against a product's unit price.

    This is the single place a discount becomes money. `total` is rounded to
    cents with `ROUND_HALF_UP` (never banker's rounding, which would surprise a
    merchant reconciling courier cash) and is what an order stores.
    """
    unit = _as_decimal(unit_price)
    gross = (unit * offer.quantity).quantize(_CENTS, rounding=ROUND_HALF_UP)

    effective_percent = offer.discount_percent
    if offer.discount_amount is not None:
        if offer.discount_amount >= gross:
            raise LandingValidationError(
                "offers", "The fixed discount must be lower than the offer's full price."
            )
        total = (gross - offer.discount_amount).quantize(_CENTS, rounding=ROUND_HALF_UP)
        effective_percent = int(
            ((offer.discount_amount / gross) * Decimal(100)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        if effective_percent > MAX_DISCOUNT_PERCENT:
            raise LandingValidationError(
                "offers", f"The fixed discount cannot exceed {MAX_DISCOUNT_PERCENT} percent."
            )
    elif offer.discount_percent:
        multiplier = (Decimal(100) - Decimal(offer.discount_percent)) / Decimal(100)
        total = (gross * multiplier).quantize(_CENTS, rounding=ROUND_HALF_UP)
    else:
        total = gross

    return OfferPricing(
        quantity=offer.quantity,
        unit_price=unit,
        discount_percent=effective_percent,
        gross=gross,
        total=total,
        savings=(gross - total).quantize(_CENTS, rounding=ROUND_HALF_UP),
        compare_at_price=offer.compare_at_price,
    )


def find_offer(offers: list[LandingOffer], quantity: int) -> LandingOffer | None:
    """Return the tier for `quantity`, or `None` when the landing has no such tier."""
    for offer in offers:
        if offer.quantity == quantity:
            return offer
    return None


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------


def _validate_quantity(raw_quantity: Any, *, position: int, maximum: int) -> int:
    try:
        quantity = int(str(raw_quantity).strip())
    except (TypeError, ValueError) as exc:
        raise LandingValidationError(
            "offers", f"Offer {position}: quantity must be a whole number."
        ) from exc
    if quantity < 1 or quantity > maximum:
        raise LandingValidationError(
            "offers", f"Offer {position}: quantity must be between 1 and {maximum}."
        )
    return quantity


def _require_offer_text(value: Any, *, position: int, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LandingValidationError("offers", f"Offer {position}: {label.lower()} is required.")
    text = value.strip()
    if len(text) > maximum:
        raise LandingValidationError(
            "offers", f"Offer {position}: {label.lower()} must be at most {maximum} characters."
        )
    return text


def _optional_offer_text(value: Any, *, position: int, label: str, maximum: int) -> str | None:
    """Return the trimmed sub-text, or `None` when it is blank.

    Blank is the documented way to render a tile with no sub-line, so an empty
    string is a valid input rather than an error.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise LandingValidationError("offers", f"Offer {position}: {label.lower()} must be text.")
    text = value.strip()
    if not text:
        return None
    if len(text) > maximum:
        raise LandingValidationError(
            "offers", f"Offer {position}: {label.lower()} must be at most {maximum} characters."
        )
    return text


def _validate_discount_percent(raw_percent: Any, *, position: int, quantity: int) -> int:
    if raw_percent is None or raw_percent == "":
        return 0
    try:
        percent = int(str(raw_percent).strip())
    except (TypeError, ValueError) as exc:
        raise LandingValidationError(
            "offers", f"Offer {position}: discount must be a whole number of percent."
        ) from exc

    if percent < MIN_DISCOUNT_PERCENT or percent > MAX_DISCOUNT_PERCENT:
        raise LandingValidationError(
            "offers",
            f"Offer {position}: discount must be between "
            f"{MIN_DISCOUNT_PERCENT} and {MAX_DISCOUNT_PERCENT} percent.",
        )
    if percent and quantity < DISCOUNTABLE_MIN_QUANTITY:
        raise LandingValidationError(
            "offers",
            f"Offer {position}: a discount needs at least "
            f"{DISCOUNTABLE_MIN_QUANTITY} units. Use the reference price for a single unit.",
        )
    return percent


def _validate_compare_at_price(raw_price: Any, *, position: int, quantity: int) -> Decimal | None:
    if raw_price is None or raw_price == "":
        return None
    if quantity != 1:
        raise LandingValidationError(
            "offers",
            f"Offer {position}: a reference price only applies to the single-unit offer. "
            "Use a discount for multi-unit offers.",
        )
    try:
        price = Decimal(str(raw_price).strip())
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise LandingValidationError(
            "offers", f"Offer {position}: reference price must be a number."
        ) from exc
    if price <= 0:
        raise LandingValidationError(
            "offers", f"Offer {position}: reference price must be greater than zero."
        )
    if price.as_tuple().exponent < -2:  # type: ignore[operator]
        raise LandingValidationError(
            "offers", f"Offer {position}: reference price must have at most 2 decimal places."
        )
    return price.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _validate_discount_amount(raw_amount: Any, *, position: int, quantity: int) -> Decimal | None:
    if raw_amount is None or raw_amount == "":
        return None
    if quantity < DISCOUNTABLE_MIN_QUANTITY:
        raise LandingValidationError(
            "offers",
            f"Offer {position}: a discount needs at least {DISCOUNTABLE_MIN_QUANTITY} units.",
        )
    try:
        amount = Decimal(str(raw_amount).strip())
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise LandingValidationError(
            "offers", f"Offer {position}: fixed discount must be a number."
        ) from exc
    if amount <= 0:
        raise LandingValidationError(
            "offers", f"Offer {position}: fixed discount must be greater than zero."
        )
    if amount.as_tuple().exponent < -2:  # type: ignore[operator]
        raise LandingValidationError(
            "offers", f"Offer {position}: fixed discount must have at most 2 decimal places."
        )
    return amount.quantize(_CENTS, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Lenient readers used only by `parse_stored_offers`
# ---------------------------------------------------------------------------


def _safe_text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:maximum]


def _safe_discount(value: Any, *, quantity: int) -> int:
    if quantity < DISCOUNTABLE_MIN_QUANTITY:
        return 0
    try:
        percent = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return min(max(percent, MIN_DISCOUNT_PERCENT), MAX_DISCOUNT_PERCENT)


def _safe_price(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        price = Decimal(str(value).strip())
    except (ArithmeticError, TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _safe_discount_amount(value: Any, *, quantity: int) -> Decimal | None:
    if quantity < DISCOUNTABLE_MIN_QUANTITY:
        return None
    return _safe_price(value)


def _as_decimal(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
