"""Pure conversion from local order snapshots to MasterShop's request body."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from typing import Any


class MastershopPayloadError(ValueError):
    """A local order cannot be represented safely for MasterShop."""


def selection_key(selection: dict[str, str]) -> str:
    """Return the stable key shared by catalog mappings and order selections."""
    return json.dumps(selection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _mapping_by_key(mappings: list[Any]) -> dict[str, Any]:
    return {mapping.selectionKey: mapping for mapping in mappings}


def _mastershop_location(department: str, city: str) -> tuple[str, str]:
    """Translate the one Bogotá location pair MasterShop represents differently."""
    if department == "BOGOTÁ D.C." and city == "BOGOTÁ D.C.":
        return "CUNDINAMARCA", "BOGOTA"
    return department.title(), city.title()


def build_order_payload(
    *,
    order: Any,
    details: Any,
    mappings: list[Any],
) -> dict[str, Any]:
    """Build a stable MasterShop order payload from persisted snapshots."""
    first_name = details.firstName.strip()
    last_name = details.lastName.strip()
    if not first_name or not last_name:
        raise MastershopPayloadError(
            "The order needs separate first and last names before synchronization."
        )

    mapping_by_key = _mapping_by_key(mappings)
    selections = order.variantSelections if isinstance(order.variantSelections, list) else []
    unit_selections = selections or [{} for _ in range(order.quantity)]
    counts = Counter(selection_key(selection) for selection in unit_selections)
    selection_values = {selection_key(selection): selection for selection in unit_selections}
    product = order.product
    effective_unit_price = Decimal(order.totalPrice) / Decimal(order.quantity)

    items: list[dict[str, Any]] = []
    for key, quantity in counts.items():
        mapping = mapping_by_key.get(key)
        if mapping is None:
            selection = selection_values[key]
            description = ", ".join(f"{name}: {value}" for name, value in selection.items())
            raise MastershopPayloadError(
                "Missing MasterShop mapping"
                + (f" for {description}." if description else " for this product.")
            )
        if selection_values[key] and mapping.mastershopVariantId is None:
            raise MastershopPayloadError("A variant product mapping needs id_variant.")
        items.append(
            {
                "id_variant": (
                    int(mapping.mastershopVariantId)
                    if mapping.mastershopVariantId is not None
                    else None
                ),
                "id_product": int(mapping.mastershopProductId),
                "quantity": quantity,
                "sku": product.sku,
                "name": product.name,
                "weight": _number(Decimal(mapping.weight)),
                "price": _number(effective_unit_price),
            }
        )

    full_name = f"{first_name} {last_name}"
    national_phone = order.phoneNormalizedKey
    shipping_phone = order.phoneE164.lstrip("+")
    address2 = details.address2.strip() if details.address2 else None
    state, city = _mastershop_location(order.department, order.city)

    address = {
        "country": "CO",
        "state": state,
        "city": city,
        "address1": details.address1,
        "address2": address2 or None,
        "company": None,
        "zip": None,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
    }
    return {
        "id_order": f"bp_{order.id}",
        "notes": [],
        "tags": [],
        "shipping_address": {**address, "phone": shipping_phone},
        "billing_address": {**address, "phone": national_phone},
        "order_transaction": {
            "total": _number(Decimal(order.totalPrice)),
            "currency": "COP",
            "payment_method": "cod",
            "payment_gateway": "COD",
        },
        "customer": {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": None,
            "phone": national_phone,
            "tags": [],
            "documentType": None,
            "documentNumber": None,
        },
        "order_items": items,
    }
