"""Unit tests for the per-CTA-position text override.

Covers `app.domains.landings.cta_text_overrides`: the merchant-submitted map
has to survive JSON's string-keyed-object round trip (an int position coerced
to a string key and back), reject anything that would corrupt the column or
render blank, and `resolve_cta_text` has to apply the documented precedence
(override -> landing default -> None).
"""

from __future__ import annotations

import pytest
from app.domains.landings.cta_text_overrides import (
    OVERRIDE_TEXT_MAX,
    resolve_cta_text,
    validate_cta_text_overrides,
)
from app.domains.landings.errors import LandingValidationError


class TestValidateCtaTextOverrides:
    def test_empty_map_is_valid(self) -> None:
        assert validate_cta_text_overrides({}) == {}

    def test_int_keys_are_restringified(self) -> None:
        assert validate_cta_text_overrides({2: "Lo quiero ahora"}) == {"2": "Lo quiero ahora"}

    def test_string_keys_round_trip(self) -> None:
        assert validate_cta_text_overrides({"2": "Lo quiero ahora"}) == {
            "2": "Lo quiero ahora"
        }

    def test_values_are_trimmed(self) -> None:
        assert validate_cta_text_overrides({"1": "  Cómpralo ya  "}) == {"1": "Cómpralo ya"}

    def test_multiple_positions_are_all_kept(self) -> None:
        result = validate_cta_text_overrides({"1": "Uno", "3": "Tres"})
        assert result == {"1": "Uno", "3": "Tres"}

    def test_non_dict_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_text_overrides(["not", "a", "dict"])  # type: ignore[arg-type]
        assert exc_info.value.field == "cta_text_overrides"

    @pytest.mark.parametrize("bad_key", ["not-a-number", "1.5", "", None])
    def test_non_integer_key_is_rejected(self, bad_key: object) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_text_overrides({bad_key: "text"})
        assert exc_info.value.field == "cta_text_overrides"

    @pytest.mark.parametrize("position", [0, -1, -100])
    def test_non_positive_position_is_rejected(self, position: int) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_text_overrides({position: "text"})
        assert exc_info.value.field == "cta_text_overrides"

    def test_non_string_value_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_text_overrides({"1": 123})  # type: ignore[dict-item]
        assert exc_info.value.field == "cta_text_overrides"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_value_is_rejected(self, blank: str) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_text_overrides({"1": blank})
        assert exc_info.value.field == "cta_text_overrides"

    def test_value_at_the_maximum_length_is_accepted(self) -> None:
        text = "x" * OVERRIDE_TEXT_MAX
        assert validate_cta_text_overrides({"1": text}) == {"1": text}

    def test_value_over_the_maximum_length_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_text_overrides({"1": "x" * (OVERRIDE_TEXT_MAX + 1)})
        assert exc_info.value.field == "cta_text_overrides"


class TestResolveCtaText:
    def test_an_overridden_position_uses_its_override(self) -> None:
        assert (
            resolve_cta_text(2, overrides={"2": "Lo quiero ahora"}, default_text="Comprar ya")
            == "Lo quiero ahora"
        )

    def test_a_position_without_an_override_uses_the_default(self) -> None:
        assert (
            resolve_cta_text(1, overrides={"2": "Lo quiero ahora"}, default_text="Comprar ya")
            == "Comprar ya"
        )

    def test_no_overrides_at_all_uses_the_default(self) -> None:
        assert resolve_cta_text(1, overrides=None, default_text="Comprar ya") == "Comprar ya"
        assert resolve_cta_text(1, overrides={}, default_text="Comprar ya") == "Comprar ya"

    def test_no_default_and_no_override_returns_none(self) -> None:
        assert resolve_cta_text(1, overrides=None, default_text=None) is None

    def test_only_the_exact_position_is_matched(self) -> None:
        overrides = {"2": "Lo quiero ahora"}
        assert resolve_cta_text(20, overrides=overrides, default_text="Comprar ya") == "Comprar ya"
