"""Validation for local variant-combination to MasterShop catalog mappings."""

from __future__ import annotations

from itertools import product
from math import isfinite
from typing import Any

from app.domains.products.errors import ProductValidationError
from app.integrations.mastershop.payload import selection_key


def expected_selections(options: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not options:
        return [{}]
    names = [option["name"] for option in options]
    return [
        dict(zip(names, values, strict=True))
        for values in product(*(option["values"] for option in options))
    ]


def validate_mastershop_mappings(
    raw_mappings: list[dict[str, Any]], *, options: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    expected = {selection_key(value): value for value in expected_selections(options)}
    if len(raw_mappings) != len(expected):
        raise ProductValidationError(
            "mastershop_mappings", "Configure every product variant combination."
        )

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_mappings:
        selection = raw.get("variant_selection")
        if not isinstance(selection, dict):
            raise ProductValidationError(
                "mastershop_mappings", "Each mapping needs a variant selection."
            )
        normalized = {str(key): str(value) for key, value in selection.items()}
        key = selection_key(normalized)
        if key not in expected or key in seen:
            raise ProductValidationError(
                "mastershop_mappings", "Mappings must match the product variants exactly."
            )
        product_id = raw.get("mastershop_product_id")
        variant_id = raw.get("mastershop_variant_id")
        weight = raw.get("weight", 1)
        if not isinstance(product_id, int) or isinstance(product_id, bool) or product_id <= 0:
            raise ProductValidationError(
                "mastershop_product_id", "MasterShop product ID must be positive."
            )
        if options and (
            not isinstance(variant_id, int) or isinstance(variant_id, bool) or variant_id <= 0
        ):
            raise ProductValidationError(
                "mastershop_variant_id", "Every product variant needs a MasterShop variant ID."
            )
        if variant_id is not None and (
            not isinstance(variant_id, int) or isinstance(variant_id, bool) or variant_id <= 0
        ):
            raise ProductValidationError(
                "mastershop_variant_id", "MasterShop variant ID must be positive."
            )
        try:
            numeric_weight = float(weight)
        except (TypeError, ValueError) as exc:
            raise ProductValidationError("weight", "Weight must be positive.") from exc
        if not isfinite(numeric_weight) or numeric_weight <= 0 or numeric_weight > 99999:
            raise ProductValidationError("weight", "Weight must be positive.")
        seen.add(key)
        result.append(
            {
                "selection_key": key,
                "variant_selection": expected[key],
                "mastershop_product_id": product_id,
                "mastershop_variant_id": variant_id,
                "weight": numeric_weight,
            }
        )
    return result
