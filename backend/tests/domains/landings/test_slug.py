"""Unit tests for slug format validation (Requirements 3.1, 3.2)."""

from __future__ import annotations

import pytest
from app.domains.landings.errors import LandingValidationError
from app.domains.landings.slug import validate_slug_format


class TestValidateSlugFormat:
    def test_valid_simple_slug_is_accepted(self) -> None:
        assert validate_slug_format("producto") == "producto"

    def test_valid_slug_with_digits_and_hyphens_is_accepted(self) -> None:
        assert validate_slug_format("producto-2-en-oferta") == "producto-2-en-oferta"

    def test_empty_slug_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_slug_format("")
        assert exc_info.value.field == "slug"

    def test_uppercase_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_slug_format("Producto")

    def test_leading_hyphen_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_slug_format("-producto")

    def test_trailing_hyphen_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_slug_format("producto-")

    def test_consecutive_hyphens_are_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_slug_format("producto--oferta")

    def test_underscore_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_slug_format("producto_oferta")

    def test_space_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_slug_format("producto oferta")
