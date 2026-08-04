"""Unit + property tests for a Landing's quantity offers.

Covers `app.domains.landings.offers`. The rules that matter most here are the
ones that protect money and honesty:

- `validate_offers` is the write path and must reject anything the public form
  could not render or the order could not price.
- `parse_stored_offers` is the read path and must never raise, because a stored
  list can legitimately drift from `offer_count` when a merchant changes the
  count, and both the dashboard and the public page still have to render.
- `resolve_offer_pricing` is the one place a discount becomes an amount owed, so
  its arithmetic is pinned down exactly, including rounding.
- A discount belongs to multi-unit offers and a reference price to the
  single-unit offer, never both on one tier — that combination is how a page
  advertises a discount off an invented "was" price.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.domains.landings.errors import LandingValidationError
from app.domains.landings.offers import (
    LABEL_MAX,
    MAX_DISCOUNT_PERCENT,
    MAX_OFFER_COUNT,
    SUBLABEL_MAX,
    LandingOffer,
    default_offers,
    find_offer,
    parse_stored_offers,
    resolve_offer_pricing,
    validate_offer_count,
    validate_offers,
)
from hypothesis import given
from hypothesis import strategies as st


def _offer(quantity: int, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "quantity": quantity,
        "label": f"{quantity} unidades",
        "sublabel": None,
        "discount_percent": 0,
        "compare_at_price": None,
    }
    base.update(overrides)
    return base


def _offers(count: int, **per_quantity: dict[str, object]) -> list[dict[str, object]]:
    return [
        {**_offer(quantity), **per_quantity.get(f"q{quantity}", {})}
        for quantity in range(1, count + 1)
    ]


class TestValidateOfferCount:
    @pytest.mark.parametrize("raw", [1, 2, 3, "1", "3", " 2 "])
    def test_accepts_one_through_three(self, raw: object) -> None:
        assert validate_offer_count(raw) in {1, 2, 3}

    @pytest.mark.parametrize("raw", [0, -1, 4, 99, "0", "4", "", "two", None])
    def test_rejects_anything_outside_the_range(self, raw: object) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_offer_count(raw)
        assert exc_info.value.field == "offer_count"

    def test_range_matches_the_database_check_constraint(self) -> None:
        # Fails if `landings_offer_count_range` and this module drift apart.
        assert (validate_offer_count(1), MAX_OFFER_COUNT) == (1, 3)


class TestDefaultOffers:
    @pytest.mark.parametrize("count", [1, 2, 3])
    def test_one_offer_per_quantity_in_ascending_order(self, count: int) -> None:
        offers = default_offers(count)
        assert [offer.quantity for offer in offers] == list(range(1, count + 1))

    def test_labels_match_the_wording_the_form_shipped_with(self) -> None:
        # Turning the feature on must not change what a visitor reads until the
        # merchant actually edits something.
        assert [offer.label for offer in default_offers(3)] == [
            "1 unidad",
            "2 unidades",
            "3 unidades",
        ]

    def test_defaults_carry_no_subtext_discount_or_reference_price(self) -> None:
        for offer in default_offers(3):
            assert offer.sublabel is None
            assert offer.discount_percent == 0
            assert offer.compare_at_price is None


class TestValidateOffers:
    def test_empty_or_missing_list_means_use_the_defaults(self) -> None:
        # This is how a landing created before offers existed keeps working.
        assert validate_offers([], offer_count=2) == default_offers(2)
        assert validate_offers(None, offer_count=2) == default_offers(2)

    def test_accepts_a_complete_list_and_sorts_it_by_quantity(self) -> None:
        offers = validate_offers(
            [_offer(3), _offer(1), _offer(2)],
            offer_count=3,
        )
        assert [offer.quantity for offer in offers] == [1, 2, 3]

    def test_blank_subtext_becomes_none_so_the_tile_renders_one_line(self) -> None:
        # Blank is the documented way to turn the second line off, not an error.
        offers = validate_offers(
            _offers(2, q1={"sublabel": ""}, q2={"sublabel": "   "}),
            offer_count=2,
        )
        assert [offer.sublabel for offer in offers] == [None, None]

    def test_keeps_subtext_when_present(self) -> None:
        offers = validate_offers(
            _offers(2, q2={"sublabel": "  Ahorra más  "}),
            offer_count=2,
        )
        assert offers[1].sublabel == "Ahorra más"

    @pytest.mark.parametrize("count", [1, 2, 3])
    def test_list_length_must_match_the_configured_count(self, count: int) -> None:
        wrong_length = _offers(count) + [_offer(count + 1)]
        with pytest.raises(LandingValidationError) as exc_info:
            validate_offers(wrong_length, offer_count=count)
        assert exc_info.value.field == "offers"

    def test_duplicate_quantity_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_offers([_offer(1), _offer(1)], offer_count=2)
        assert exc_info.value.field == "offers"

    def test_quantity_beyond_the_count_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_offers([_offer(1), _offer(3)], offer_count=2)

    @pytest.mark.parametrize("label", ["", "   ", None, 42])
    def test_offer_text_is_required(self, label: object) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_offers(_offers(1, q1={"label": label}), offer_count=1)
        assert exc_info.value.field == "offers"

    def test_over_long_text_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_offers(_offers(1, q1={"label": "x" * (LABEL_MAX + 1)}), offer_count=1)
        with pytest.raises(LandingValidationError):
            validate_offers(_offers(1, q1={"sublabel": "x" * (SUBLABEL_MAX + 1)}), offer_count=1)

    # --- Discounts -------------------------------------------------------

    @pytest.mark.parametrize("percent", [0, 1, 15, 50, MAX_DISCOUNT_PERCENT, "10", ""])
    def test_multi_unit_offers_accept_a_discount(self, percent: object) -> None:
        offers = validate_offers(_offers(2, q2={"discount_percent": percent}), offer_count=2)
        assert offers[1].discount_percent == (int(percent) if str(percent).strip() else 0)

    def test_a_single_unit_offer_cannot_carry_a_discount(self) -> None:
        # There is no volume saving on one unit, so a "discount" there could only
        # be off a price the buyer never saw.
        with pytest.raises(LandingValidationError) as exc_info:
            validate_offers(_offers(1, q1={"discount_percent": 10}), offer_count=1)
        assert exc_info.value.field == "offers"

    def test_a_zero_discount_on_a_single_unit_offer_is_fine(self) -> None:
        assert validate_offers(_offers(1, q1={"discount_percent": 0}), offer_count=1)

    @pytest.mark.parametrize("percent", [-1, MAX_DISCOUNT_PERCENT + 1, 100, 1000, "abc"])
    def test_out_of_range_discount_is_rejected(self, percent: object) -> None:
        with pytest.raises(LandingValidationError):
            validate_offers(_offers(2, q2={"discount_percent": percent}), offer_count=2)

    # --- Reference price -------------------------------------------------

    def test_single_unit_offer_accepts_a_reference_price(self) -> None:
        offers = validate_offers(_offers(1, q1={"compare_at_price": "99900"}), offer_count=1)
        assert offers[0].compare_at_price == Decimal("99900.00")

    def test_a_multi_unit_offer_cannot_carry_a_reference_price(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_offers(_offers(2, q2={"compare_at_price": "1000"}), offer_count=2)
        assert exc_info.value.field == "offers"

    @pytest.mark.parametrize("price", ["0", "-1", "abc", "10.999"])
    def test_invalid_reference_price_is_rejected(self, price: str) -> None:
        with pytest.raises(LandingValidationError):
            validate_offers(_offers(1, q1={"compare_at_price": price}), offer_count=1)


class TestParseStoredOffers:
    def test_falls_back_to_defaults_for_an_empty_or_bogus_column(self) -> None:
        assert parse_stored_offers([], offer_count=3) == default_offers(3)
        assert parse_stored_offers(None, offer_count=3) == default_offers(3)
        assert parse_stored_offers("nonsense", offer_count=2) == default_offers(2)

    def test_reads_a_valid_stored_list_unchanged(self) -> None:
        stored = _offers(2, q2={"discount_percent": 20, "sublabel": "Ahorra 20%"})
        offers = parse_stored_offers(stored, offer_count=2)
        assert offers[1].discount_percent == 20
        assert offers[1].sublabel == "Ahorra 20%"

    def test_lowering_the_count_keeps_the_surviving_offers_copy(self) -> None:
        # A merchant dropping from 3 offers to 2 must not lose the wording they
        # wrote for offers 1 and 2.
        stored = _offers(
            3,
            q1={"label": "Solo una"},
            q2={"label": "Llévate dos", "discount_percent": 10},
        )
        offers = parse_stored_offers(stored, offer_count=2)
        assert [offer.label for offer in offers] == ["Solo una", "Llévate dos"]
        assert offers[1].discount_percent == 10

    def test_raising_the_count_fills_the_new_offer_with_defaults(self) -> None:
        stored = _offers(1, q1={"label": "Solo una"})
        offers = parse_stored_offers(stored, offer_count=3)
        assert [offer.label for offer in offers] == ["Solo una", "2 unidades", "3 unidades"]

    def test_a_discount_stored_against_a_single_unit_offer_is_dropped(self) -> None:
        # Defense in depth: the write path rejects this, so a row carrying it is
        # already corrupt and must not start charging a reduced price.
        stored = _offers(1, q1={"discount_percent": 40})
        assert parse_stored_offers(stored, offer_count=1)[0].discount_percent == 0

    @given(st.lists(st.dictionaries(st.text(), st.text()), max_size=6))
    def test_never_raises_whatever_the_column_holds(self, raw: list[dict[str, str]]) -> None:
        offers = parse_stored_offers(raw, offer_count=3)
        assert [offer.quantity for offer in offers] == [1, 2, 3]
        # Every offer still has renderable copy, so the form cannot come out blank.
        assert all(offer.label for offer in offers)


class TestResolveOfferPricing:
    def test_an_undiscounted_offer_costs_unit_price_times_quantity(self) -> None:
        pricing = resolve_offer_pricing(Decimal("89900"), default_offers(3)[1])
        assert pricing.gross == Decimal("179800.00")
        assert pricing.total == Decimal("179800.00")
        assert pricing.savings == Decimal("0.00")

    def test_a_discount_reduces_the_total_and_reports_the_saving(self) -> None:
        offer = LandingOffer(
            quantity=2,
            label="2 unidades",
            sublabel=None,
            discount_percent=10,
            compare_at_price=None,
        )
        pricing = resolve_offer_pricing(Decimal("89900"), offer)
        assert pricing.gross == Decimal("179800.00")
        assert pricing.total == Decimal("161820.00")
        assert pricing.savings == Decimal("17980.00")

    def test_rounding_is_half_up_to_cents(self) -> None:
        # 3 x 10.00 at 15% off is 25.50 exactly; a price that lands on a half
        # cent must round up, not to even.
        offer = LandingOffer(
            quantity=3,
            label="3",
            sublabel=None,
            discount_percent=15,
            compare_at_price=None,
        )
        assert resolve_offer_pricing(Decimal("10.00"), offer).total == Decimal("25.50")

        half_cent = LandingOffer(
            quantity=1,
            label="1",
            sublabel=None,
            discount_percent=0,
            compare_at_price=None,
        )
        assert resolve_offer_pricing("0.125", half_cent).total == Decimal("0.13")

    def test_reference_price_is_carried_through_untouched(self) -> None:
        offer = LandingOffer(
            quantity=1,
            label="1 unidad",
            sublabel=None,
            discount_percent=0,
            compare_at_price=Decimal("99900.00"),
        )
        pricing = resolve_offer_pricing(Decimal("89900"), offer)
        # Informational only: it never becomes the amount owed.
        assert pricing.compare_at_price == Decimal("99900.00")
        assert pricing.total == Decimal("89900.00")

    @given(
        st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999.99"), places=2),
        st.integers(min_value=1, max_value=3),
        st.integers(min_value=0, max_value=MAX_DISCOUNT_PERCENT),
    )
    def test_total_never_exceeds_gross_and_never_goes_negative(
        self, unit_price: Decimal, quantity: int, percent: int
    ) -> None:
        offer = LandingOffer(
            quantity=quantity,
            label="x",
            sublabel=None,
            discount_percent=percent if quantity > 1 else 0,
            compare_at_price=None,
        )
        pricing = resolve_offer_pricing(unit_price, offer)
        assert Decimal("0") <= pricing.total <= pricing.gross
        assert pricing.savings == pricing.gross - pricing.total


class TestFindOffer:
    def test_returns_the_matching_offer(self) -> None:
        offers = default_offers(3)
        assert find_offer(offers, 2) is offers[1]

    def test_returns_none_for_a_quantity_the_landing_does_not_offer(self) -> None:
        # This is what stops a crafted request from ordering a quantity at a
        # price the merchant never configured.
        assert find_offer(default_offers(2), 3) is None
        assert find_offer(default_offers(2), 0) is None
