from __future__ import annotations

import pytest
from app.domains.orders.errors import OrderValidationError
from app.domains.products.errors import ProductValidationError
from app.domains.products.variants import validate_variant_options, validate_variant_selections

OPTIONS = [
    {"name": "Color", "values": ["Gris", "Negro"]},
    {"name": "Talla", "values": ["M", "L"]},
]


def test_accepts_at_most_two_normalized_option_groups() -> None:
    assert validate_variant_options(OPTIONS) == OPTIONS
    with pytest.raises(ProductValidationError):
        validate_variant_options(OPTIONS + [{"name": "Material", "values": ["Algodón"]}])


def test_requires_one_complete_selection_per_ordered_unit() -> None:
    selections = [
        {"Color": "Gris", "Talla": "M"},
        {"Color": "Negro", "Talla": "L"},
    ]
    assert validate_variant_selections(selections, options=OPTIONS, quantity=2) == selections

    with pytest.raises(OrderValidationError) as exc_info:
        validate_variant_selections(selections[:1], options=OPTIONS, quantity=2)
    assert exc_info.value.field == "variant_selections"


def test_rejects_unsupported_values_and_selections_on_variant_free_products() -> None:
    with pytest.raises(OrderValidationError):
        validate_variant_selections([{"Color": "Azul", "Talla": "M"}], options=OPTIONS, quantity=1)
    with pytest.raises(OrderValidationError):
        validate_variant_selections([{"Color": "Gris"}], options=[], quantity=1)
