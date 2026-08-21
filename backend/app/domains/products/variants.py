"""Validation for optional product fulfillment characteristics."""

from __future__ import annotations

from typing import Any

from app.domains.orders.errors import OrderValidationError
from app.domains.products.errors import ProductValidationError

MAX_OPTION_GROUPS = 2
MAX_VALUES_PER_GROUP = 20
MAX_OPTION_NAME_LENGTH = 40
MAX_OPTION_VALUE_LENGTH = 60


def validate_variant_options(raw_options: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if raw_options is None:
        return []
    if len(raw_options) > MAX_OPTION_GROUPS:
        raise ProductValidationError("variant_options", "A product supports at most two options.")

    result: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for raw in raw_options:
        if not isinstance(raw, dict):
            raise ProductValidationError("variant_options", "Each option must be an object.")
        name = " ".join(str(raw.get("name", "")).split())
        values_raw = raw.get("values", [])
        if not (1 <= len(name) <= MAX_OPTION_NAME_LENGTH):
            raise ProductValidationError("variant_options", "Each option needs a valid name.")
        name_key = name.casefold()
        if name_key in used_names:
            raise ProductValidationError("variant_options", "Option names must be unique.")
        if not isinstance(values_raw, list) or not (1 <= len(values_raw) <= MAX_VALUES_PER_GROUP):
            raise ProductValidationError(
                "variant_options", "Each option needs between 1 and 20 values."
            )

        values: list[str] = []
        used_values: set[str] = set()
        for raw_value in values_raw:
            value = " ".join(str(raw_value).split())
            if not (1 <= len(value) <= MAX_OPTION_VALUE_LENGTH):
                raise ProductValidationError("variant_options", "Each option value must be valid.")
            value_key = value.casefold()
            if value_key in used_values:
                raise ProductValidationError(
                    "variant_options", f"Values for {name} must be unique."
                )
            used_values.add(value_key)
            values.append(value)

        used_names.add(name_key)
        result.append({"name": name, "values": values})
    return result


def validate_variant_selections(
    raw_selections: list[dict[str, str]] | None,
    *,
    options: list[dict[str, Any]],
    quantity: int,
) -> list[dict[str, str]]:
    selections = raw_selections or []
    if not options:
        # Rolling-deploy compatibility: the previous SPA represented a
        # variant-free unit as an empty object. Normalize those placeholders
        # away while continuing to reject any actual option selection.
        if any(selection for selection in selections):
            raise OrderValidationError("variant_selections", "This product has no options.")
        return []
    if len(selections) != quantity:
        raise OrderValidationError(
            "variant_selections", "Choose every product option for each ordered unit."
        )

    expected_names = [option["name"] for option in options]
    allowed = {option["name"]: frozenset(option["values"]) for option in options}
    normalized: list[dict[str, str]] = []
    for selection in selections:
        if not isinstance(selection, dict):
            raise OrderValidationError(
                "variant_selections", "Choose every product option for each ordered unit."
            )
        if set(selection) != set(expected_names):
            raise OrderValidationError(
                "variant_selections", "Choose every product option for each ordered unit."
            )
        unit: dict[str, str] = {}
        for name in expected_names:
            value = " ".join(str(selection[name]).split())
            if value not in allowed[name]:
                raise OrderValidationError(
                    "variant_selections", f"Select a valid value for {name}."
                )
            unit[name] = value
        normalized.append(unit)
    return normalized
