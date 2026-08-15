"""Canonical Colombian delivery locations backed by bundled DIVIPOLA data."""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domains.orders.errors import OrderValidationError

_CATALOG_PATH = Path(__file__).parents[2] / "data" / "colombia_locations.json"


def normalize_location_name(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split())).upper()


@lru_cache(maxsize=1)
def location_catalog() -> dict[str, Any]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _location_index() -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    by_department: dict[str, frozenset[str]] = {}
    all_cities: set[str] = set()
    for department in location_catalog()["departments"]:
        cities = frozenset(city["name"] for city in department["cities"])
        by_department[department["name"]] = cities
        all_cities.update(cities)
    return by_department, frozenset(all_cities)


def validate_banned_cities(values: list[str]) -> list[str]:
    """Normalize newline-derived city names and reject catalog typos."""
    _, all_cities = _location_index()
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        city = normalize_location_name(raw)
        if not city or city in seen:
            continue
        if city not in all_cities:
            raise OrderValidationError("banned_cities", f"Unknown Colombian city: {city}.")
        seen.add(city)
        normalized.append(city)
    return sorted(normalized)


def public_location_catalog(banned_cities: list[str]) -> list[dict[str, Any]]:
    banned = frozenset(normalize_location_name(city) for city in banned_cities)
    return [
        {
            "code": department["code"],
            "name": department["name"],
            "cities": [city for city in department["cities"] if city["name"] not in banned],
        }
        for department in location_catalog()["departments"]
    ]


def validate_delivery_location(
    department: str, city: str, *, banned_cities: list[str]
) -> tuple[str, str]:
    normalized_department = normalize_location_name(department)
    normalized_city = normalize_location_name(city)
    by_department, _ = _location_index()
    cities = by_department.get(normalized_department)
    if cities is None:
        raise OrderValidationError("department", "Select a valid Colombian department.")
    if normalized_city not in cities:
        raise OrderValidationError(
            "city", "Select a city or municipality belonging to the chosen department."
        )
    banned = frozenset(normalize_location_name(value) for value in banned_cities)
    if normalized_city in banned:
        raise OrderValidationError("city", "Delivery is not available in the selected city.")
    return normalized_department, normalized_city
