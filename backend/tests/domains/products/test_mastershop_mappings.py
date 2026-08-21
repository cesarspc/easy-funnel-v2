from __future__ import annotations

import pytest
from app.domains.products.errors import ProductValidationError
from app.domains.products.mastershop_mappings import (
    expected_selections,
    validate_mastershop_mappings,
)

OPTIONS = [
    {"name": "Color", "values": ["Gris", "Negro"]},
    {"name": "Talla", "values": ["M", "L"]},
]


def test_generates_and_validates_every_variant_combination() -> None:
    selections = expected_selections(OPTIONS)
    assert selections == [
        {"Color": "Gris", "Talla": "M"},
        {"Color": "Gris", "Talla": "L"},
        {"Color": "Negro", "Talla": "M"},
        {"Color": "Negro", "Talla": "L"},
    ]
    mappings = [
        {
            "variant_selection": selection,
            "mastershop_product_id": 232082,
            "mastershop_variant_id": 9000 + index,
            "weight": 1,
        }
        for index, selection in enumerate(selections)
    ]

    assert len(validate_mastershop_mappings(mappings, options=OPTIONS)) == 4


def test_rejects_partial_or_variantless_mapping_for_variant_product() -> None:
    with pytest.raises(ProductValidationError, match="every product variant"):
        validate_mastershop_mappings([], options=OPTIONS)

    mappings = [
        {
            "variant_selection": selection,
            "mastershop_product_id": 232082,
            "mastershop_variant_id": None,
            "weight": 1,
        }
        for selection in expected_selections(OPTIONS)
    ]
    with pytest.raises(ProductValidationError, match="variant ID"):
        validate_mastershop_mappings(mappings, options=OPTIONS)


def test_rejects_non_finite_weight_before_database_write() -> None:
    mapping = {
        "variant_selection": {},
        "mastershop_product_id": 232082,
        "mastershop_variant_id": None,
        "weight": float("nan"),
    }

    with pytest.raises(ProductValidationError, match="Weight must be positive"):
        validate_mastershop_mappings([mapping], options=[])
