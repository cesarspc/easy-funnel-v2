"""Unit tests for product field validation (Requirements 2.2-2.6, 2.10, 2.22)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.domains.products.errors import ProductValidationError
from app.domains.products.validation import (
    validate_creation_status,
    validate_description,
    validate_name,
    validate_price,
    validate_sku,
)


class TestValidateName:
    def test_trims_and_accepts_a_valid_name(self) -> None:
        assert validate_name("  Producto  ") == "Producto"

    def test_minimum_length_boundary_is_accepted(self) -> None:
        assert validate_name("A") == "A"

    def test_maximum_length_boundary_is_accepted(self) -> None:
        name = "A" * 160
        assert validate_name(name) == name

    def test_empty_after_trim_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError) as exc_info:
            validate_name("   ")
        assert exc_info.value.field == "name"

    def test_over_maximum_length_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_name("A" * 161)


class TestValidateDescription:
    def test_empty_description_is_accepted(self) -> None:
        assert validate_description("") == ""

    def test_maximum_length_boundary_is_accepted(self) -> None:
        description = "A" * 5000
        assert validate_description(description) == description

    def test_over_maximum_length_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError) as exc_info:
            validate_description("A" * 5001)
        assert exc_info.value.field == "description"


class TestValidatePrice:
    def test_minimum_boundary_is_accepted(self) -> None:
        assert validate_price(Decimal("0.01")) == Decimal("0.01")

    def test_maximum_boundary_is_accepted(self) -> None:
        assert validate_price(Decimal("999999999.99")) == Decimal("999999999.99")

    def test_below_minimum_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError) as exc_info:
            validate_price(Decimal("0.00"))
        assert exc_info.value.field == "price"

    def test_above_maximum_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_price(Decimal("1000000000.00"))

    def test_more_than_two_decimal_places_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_price(Decimal("10.999"))

    def test_negative_price_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_price(Decimal("-5.00"))

    def test_non_numeric_string_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_price("not-a-number")

    def test_nan_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_price(Decimal("NaN"))

    def test_infinity_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_price(Decimal("Infinity"))


class TestValidateSku:
    def test_trims_and_accepts_a_valid_sku(self) -> None:
        assert validate_sku("  SKU-123  ") == "SKU-123"

    def test_empty_after_trim_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError) as exc_info:
            validate_sku("   ")
        assert exc_info.value.field == "sku"


class TestValidateCreationStatus:
    def test_none_defaults_to_paused(self) -> None:
        assert validate_creation_status(None) == "paused"

    def test_explicit_active_is_accepted(self) -> None:
        assert validate_creation_status("active") == "active"

    def test_explicit_paused_is_accepted(self) -> None:
        assert validate_creation_status("paused") == "paused"

    def test_retired_is_rejected_as_a_creation_status(self) -> None:
        with pytest.raises(ProductValidationError) as exc_info:
            validate_creation_status("retired")
        assert exc_info.value.field == "status"

    def test_unsupported_status_is_rejected(self) -> None:
        with pytest.raises(ProductValidationError):
            validate_creation_status("not_a_real_status")
