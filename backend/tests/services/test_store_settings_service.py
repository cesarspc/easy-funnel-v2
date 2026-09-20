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
        ("whatsappNumber", "+15551234567"),
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
    settings = SimpleNamespace(
        store_name="Nueva Tienda",
        store_legal_name="Nueva Tienda SAS",
        store_primary_color="#123456",
        store_whatsapp_number="+573001234567",
        store_whatsapp_message="Hola",
        store_support_email="soporte@example.com",
    )

    await ensure_store_settings(db, settings)

    delegate.create.assert_awaited_once()
    assert delegate.create.await_args.kwargs["data"]["storeName"] == "Nueva Tienda"


@pytest.mark.asyncio
async def test_bootstrap_never_overwrites_admin_configuration() -> None:
    delegate = SimpleNamespace(
        find_unique=AsyncMock(return_value=SimpleNamespace(id=1)),
        create=AsyncMock(),
    )
    db = SimpleNamespace(storesettings=delegate)

    await ensure_store_settings(db, SimpleNamespace())

    delegate.create.assert_not_awaited()
