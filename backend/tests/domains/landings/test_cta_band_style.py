"""Unit + property tests for the per-landing CTA band paint style.

Covers `app.domains.landings.cta_band_style`: the allowed vocabulary must stay
in lockstep with the `landings_cta_band_style_allowed` database check, and
anything outside it must surface as a field-specific validation error rather
than reaching the database.
"""

from __future__ import annotations

import pytest
from app.domains.landings.cta_band_style import (
    ALLOWED_CTA_BAND_STYLES,
    CTA_BAND_STYLE_GRADIENT,
    CTA_BAND_STYLE_SOLID,
    validate_cta_band_style,
)
from app.domains.landings.errors import LandingValidationError
from hypothesis import given
from hypothesis import strategies as st


class TestValidateCtaBandStyle:
    @pytest.mark.parametrize("style", sorted(ALLOWED_CTA_BAND_STYLES))
    def test_allowed_styles_pass_through_unchanged(self, style: str) -> None:
        assert validate_cta_band_style(style) == style

    def test_vocabulary_matches_the_database_check_constraint(self) -> None:
        # Kept literal on purpose: this is the assertion that fails if the
        # constraint in prisma/migrations and this module drift apart.
        assert set(ALLOWED_CTA_BAND_STYLES) == {"gradient", "solid"}
        assert CTA_BAND_STYLE_GRADIENT == "gradient"
        assert CTA_BAND_STYLE_SOLID == "solid"

    @pytest.mark.parametrize("style", ["", "fade", "GRADIENT", "Solid", "none", "plain"])
    def test_unsupported_style_is_a_field_specific_error(self, style: str) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_band_style(style)
        assert exc_info.value.field == "cta_band_style"

    @given(st.text())
    def test_never_returns_a_value_outside_the_vocabulary(self, style: str) -> None:
        try:
            result = validate_cta_band_style(style)
        except LandingValidationError:
            return
        assert result in ALLOWED_CTA_BAND_STYLES
