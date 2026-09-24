"""End-to-end tests for admin-editable platform parameters.

Market conventions (locale, currency, time zone, phone rules) and the
fulfillment integration live in `store_settings` and take effect without a
redeploy; the provider API key is write-only.
"""

from __future__ import annotations

from app.services.platform_config import invalidate_platform_config

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness

pytestmark = requires_database

_REGIONAL_FIELDS = (
    "countryCode",
    "locale",
    "currency",
    "timeZone",
    "phoneCountryCode",
    "phoneNationalPattern",
)


async def _restore_regional(cod_flow: CodFlowHarness, previous: object) -> None:
    await cod_flow.db.storesettings.update(
        where={"id": 1},
        data={field: getattr(previous, field) for field in _REGIONAL_FIELDS},
    )
    invalidate_platform_config()


async def test_admin_edits_market_and_public_store_reflects_it(cod_flow: CodFlowHarness) -> None:
    previous = await cod_flow.db.storesettings.find_unique(where={"id": 1})
    try:
        response = await cod_flow.client.patch(
            "/api/admin/store",
            json={
                "country_code": "mx",
                "locale": "es-MX",
                "currency": "mxn",
                "time_zone": "America/Mexico_City",
                "phone_country_code": "52",
                "phone_national_pattern": "[0-9]{10}",
                "mastershop_api_key": "super-secret",
            },
            headers=cod_flow.admin_headers(),
        )
        assert response.status_code == 200
        admin_body = response.json()
        assert admin_body["currency"] == "MXN"
        assert admin_body["mastershop_api_key_configured"] is True
        assert "mastershop_api_key" not in admin_body

        public = (await cod_flow.client.get("/api/public/store")).json()
        assert public["country_code"] == "MX"
        assert public["locale"] == "es-MX"
        assert public["time_zone"] == "America/Mexico_City"
        assert public["phone_country_code"] == "52"
        assert "fulfillment_provider" not in public
        assert "mastershop_api_key_configured" not in public

        landing = await cod_flow.seed_landing()
        order = await cod_flow.client.post(
            "/api/public/orders",
            json={
                "landing_slug": landing.slug,
                "full_name": "Ana Lopez",
                "first_name": "Ana",
                "last_name": "Lopez",
                "phone": "+52 55 1234 5678",
                "department": "CUNDINAMARCA",
                "city": "SOACHA",
                "address": "Calle 123 #45-67",
                "address1": "Calle 123 #45-67",
                "address2": None,
                "quantity": 1,
            },
            headers={"X-Forwarded-For": "203.0.113.77", "User-Agent": "E2E"},
        )
        assert order.status_code == 201
        stored = await cod_flow.db.order.find_unique(where={"id": order.json()["order_id"]})
        assert stored is not None
        assert stored.phoneE164 == "+525512345678"
    finally:
        await _restore_regional(cod_flow, previous)


async def test_invalid_platform_setting_names_the_field(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.patch(
        "/api/admin/store",
        json={"time_zone": "Mars/Olympus"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "timeZone"
