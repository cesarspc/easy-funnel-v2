from __future__ import annotations

import pytest
from app.domains.orders.errors import OrderValidationError
from app.domains.orders.locations import (
    location_catalog,
    public_location_catalog,
    validate_banned_cities,
    validate_delivery_location,
)


def test_catalog_contains_all_departments_and_soacha_under_cundinamarca() -> None:
    departments = location_catalog()["departments"]
    assert len(departments) == 33
    cundinamarca = next(item for item in departments if item["name"] == "CUNDINAMARCA")
    assert any(city["name"] == "SOACHA" for city in cundinamarca["cities"])


def test_delivery_location_is_normalized_and_relationship_is_enforced() -> None:
    assert validate_delivery_location(" cundinamarca ", "soacha", banned_cities=[]) == (
        "CUNDINAMARCA",
        "SOACHA",
    )

    with pytest.raises(OrderValidationError) as exc_info:
        validate_delivery_location("ANTIOQUIA", "SOACHA", banned_cities=[])
    assert exc_info.value.field == "city"


def test_banned_city_is_removed_and_rejected_by_submission_validation() -> None:
    banned = validate_banned_cities([" soacha ", "SOACHA", ""])
    assert banned == ["SOACHA"]
    catalog = public_location_catalog(banned)
    cundinamarca = next(item for item in catalog if item["name"] == "CUNDINAMARCA")
    assert all(city["name"] != "SOACHA" for city in cundinamarca["cities"])

    with pytest.raises(OrderValidationError) as exc_info:
        validate_delivery_location("CUNDINAMARCA", "SOACHA", banned_cities=banned)
    assert exc_info.value.field == "city"


def test_unknown_banned_city_is_rejected() -> None:
    with pytest.raises(OrderValidationError) as exc_info:
        validate_banned_cities(["CIUDAD INVENTADA"])
    assert exc_info.value.field == "banned_cities"
