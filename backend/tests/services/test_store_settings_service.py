from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.store_settings_service import (
    StoreSettingsValidationError,
    ensure_store_settings,
    validate_store_update,
)


def test_store_update_normalizes_customizable_identity_fields() -> None:
    result = validate_store_update(
        {
            "storeName": "  Tienda Cafetera  ",
            "primaryColor": "#A04F2B",
            "whatsappNumber": "+573001234567",
            "supportEmail": " SOPORTE@Example.COM ",
            "gtmContainerId": "gtm-ab12",
            "metaPixelId": "1234567890",
            "trustItems": [" Pago contraentrega ", "Envío nacional"],
        }
    )

    assert result == {
        "storeName": "Tienda Cafetera",
        "primaryColor": "#a04f2b",
        "whatsappNumber": "+573001234567",
        "supportEmail": "soporte@example.com",
        "gtmContainerId": "GTM-AB12",
        "metaPixelId": "1234567890",
        "trustItems": ["Pago contraentrega", "Envío nacional"],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("primaryColor", "orange"),
        ("whatsappNumber", "3001234567"),
        ("countryCode", "COL"),
        ("locale", "not a locale"),
        ("currency", "pesos"),
        ("timeZone", "Mars/Olympus"),
        ("phoneCountryCode", "+0"),
        ("phoneNationalPattern", "3[0-9"),
        ("fulfillmentProvider", "dropi"),
        ("mastershopOrdersUrl", "ftp://example.com"),
        ("mastershopTimeoutSeconds", 60),
        ("supportEmail", "not-an-email"),
        ("gtmContainerId", "UA-123"),
        ("metaPixelId", "pixel-one"),
        ("trustItems", ["one", "two", "three", "four"]),
    ],
)
def test_store_update_rejects_invalid_customization(field: str, value: object) -> None:
    with pytest.raises(StoreSettingsValidationError) as raised:
        validate_store_update({field: value})

    assert raised.value.field == field


@pytest.mark.asyncio
async def test_bootstrap_env_only_seeds_an_empty_database() -> None:
    delegate = SimpleNamespace(find_unique=AsyncMock(return_value=None), create=AsyncMock())
    db = SimpleNamespace(storesettings=delegate)
    settings = _bootstrap_settings()

    await ensure_store_settings(db, settings)

    delegate.create.assert_awaited_once()
    data = delegate.create.await_args.kwargs["data"]
    assert data["storeName"] == "Nueva Tienda"
    assert data["currency"] == "MXN"
    assert data["timeZone"] == "America/Mexico_City"
    assert data["phoneCountryCode"] == "52"
    assert data["fulfillmentProvider"] == "mastershop"
    assert data["mastershopApiKey"] == "seed-key"


@pytest.mark.asyncio
async def test_bootstrap_never_overwrites_admin_configuration() -> None:
    delegate = SimpleNamespace(
        find_unique=AsyncMock(return_value=SimpleNamespace(id=1, fulfillmentProvider="none")),
        create=AsyncMock(),
        update=AsyncMock(),
    )
    db = SimpleNamespace(storesettings=delegate)

    await ensure_store_settings(db, _bootstrap_settings())

    delegate.create.assert_not_awaited()
    delegate.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_bootstrap_seeds_fulfillment_once_on_upgraded_database() -> None:
    delegate = SimpleNamespace(
        find_unique=AsyncMock(return_value=SimpleNamespace(id=1, fulfillmentProvider=None)),
        create=AsyncMock(),
        update=AsyncMock(),
    )
    db = SimpleNamespace(storesettings=delegate)

    await ensure_store_settings(db, _bootstrap_settings())

    delegate.create.assert_not_awaited()
    data = delegate.update.await_args.kwargs["data"]
    assert data == {
        "fulfillmentProvider": "mastershop",
        "mastershopOrdersUrl": "https://example.com/orders",
        "mastershopTimeoutSeconds": 7.0,
        "mastershopApiKey": "seed-key",
    }


def test_store_update_accepts_another_market() -> None:
    result = validate_store_update(
        {
            "countryCode": "mx",
            "locale": "es-MX",
            "currency": "mxn",
            "timeZone": "America/Mexico_City",
            "phoneCountryCode": "+52",
            "phoneNationalPattern": "[0-9]{10}",
            "whatsappNumber": "+525512345678",
        }
    )

    assert result == {
        "countryCode": "MX",
        "locale": "es-MX",
        "currency": "MXN",
        "timeZone": "America/Mexico_City",
        "phoneCountryCode": "52",
        "phoneNationalPattern": "[0-9]{10}",
        "whatsappNumber": "+525512345678",
    }


def _bootstrap_settings() -> SimpleNamespace:
    return SimpleNamespace(
        store_name="Nueva Tienda",
        store_legal_name="Nueva Tienda SAS",
        store_primary_color="#123456",
        store_whatsapp_number="+525512345678",
        store_whatsapp_message="Hola",
        store_support_email="soporte@example.com",
        store_country_code="MX",
        store_locale="es-MX",
        store_currency="MXN",
        store_time_zone="America/Mexico_City",
        store_phone_country_code="52",
        store_phone_national_pattern="[0-9]{10}",
        fulfillment_provider="mastershop",
        mastershop_orders_url="https://example.com/orders",
        mastershop_timeout_seconds=7,
        mastershop_api_key="seed-key",
    )
