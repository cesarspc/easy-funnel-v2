"""Per-position CTA color-mode validation."""

import pytest
from app.domains.landings.cta_color_modes import (
    CTA_COLOR_MODE_DEFAULT,
    resolve_cta_color_mode,
    validate_cta_color_modes,
)
from app.domains.landings.errors import LandingValidationError


def test_normalizes_positions_and_omits_explicit_defaults() -> None:
    assert validate_cta_color_modes({1: "dark", "2": "light", "3": "default"}) == {
        "1": "dark",
        "2": "light",
    }


@pytest.mark.parametrize(
    "raw",
    [
        {"0": "dark"},
        {"one": "light"},
        {"1": "blue"},
        {"1": 1},
    ],
)
def test_rejects_invalid_position_or_mode(raw: dict[object, object]) -> None:
    with pytest.raises(LandingValidationError) as exc_info:
        validate_cta_color_modes(raw)
    assert exc_info.value.field == "cta_color_modes"


def test_resolves_missing_and_known_positions() -> None:
    modes = {"2": "dark"}
    assert resolve_cta_color_mode(1, modes) == CTA_COLOR_MODE_DEFAULT
    assert resolve_cta_color_mode(2, modes) == "dark"
