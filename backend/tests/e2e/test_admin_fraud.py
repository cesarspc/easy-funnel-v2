"""Admin Fraud API tests (Requirements 6.6-6.8, 6.20-6.24, 8.10, 10.9, 10.10).

Drives the real ASGI application against the real database, so validation,
normalization, conflict handling, and the audit records every fraud mutation
must leave behind are all exercised for real.

`fraud_config` is a seeded singleton shared by the whole suite, so the
configuration tests restore the stored values before finishing.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from app.core.regional import DEFAULT_REGIONAL
from app.domains.orders.normalization import normalize_phone_key
from prisma import Json

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness, unique_phone

pytestmark = requires_database


@pytest_asyncio.fixture
async def restored_config(cod_flow: CodFlowHarness) -> AsyncIterator[dict]:
    """Yield the stored fraud configuration and put it back afterwards."""
    response = await cod_flow.client.get(
        "/api/admin/fraud/config", headers=cod_flow.admin_headers()
    )
    original = response.json()
    try:
        yield original
    finally:
        await cod_flow.client.put(
            "/api/admin/fraud/config",
            json={
                "duplicate_window_hours": original["duplicate_window_hours"],
                "duplicate_match_fields": original["duplicate_match_fields"],
                "rate_limit_max": original["rate_limit_max"],
                "rate_limit_window_minutes": original["rate_limit_window_minutes"],
            },
            headers=cod_flow.admin_headers(),
        )


def _unique_ip() -> str:
    """Return an address unique to this call, from the documentation range.

    Blacklist values are unique per entry type and the database is not reset
    between runs, so a fixed literal would collide with a leftover entry (or
    with local seed data) and turn a create into a 409.
    """
    return f"2001:db8:e2e::{uuid.uuid4().hex[:4]}:{uuid.uuid4().hex[:4]}"


def _unique_location_code() -> str:
    """Return a GeoIP location code unique to this call.

    `geoip_rules.location_code` is unique, so real country codes would clash
    with rules another test (or the local database) already holds.
    """
    return f"E2E{uuid.uuid4().hex[:5].upper()}"


async def _delete_blacklist_entry(cod_flow: CodFlowHarness, entry_id: int) -> None:
    await cod_flow.db.auditlog.delete_many(
        where={"targetType": "blacklist_entry", "targetId": str(entry_id)}
    )
    if await cod_flow.db.blacklistentry.find_unique(where={"id": entry_id}) is not None:
        await cod_flow.db.blacklistentry.delete(where={"id": entry_id})


async def _delete_geoip_rule(cod_flow: CodFlowHarness, rule_id: int) -> None:
    await cod_flow.db.auditlog.delete_many(
        where={"targetType": "geoip_rule", "targetId": str(rule_id)}
    )
    if await cod_flow.db.geoiprule.find_unique(where={"id": rule_id}) is not None:
        await cod_flow.db.geoiprule.delete(where={"id": rule_id})


# --- Configuration -----------------------------------------------------------


async def test_get_config_returns_the_stored_configuration(
    cod_flow: CodFlowHarness, restored_config: dict
) -> None:
    response = await cod_flow.client.get(
        "/api/admin/fraud/config", headers=cod_flow.admin_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate_window_hours"] > 0
    assert set(body["duplicate_match_fields"]) <= {"phone", "ip"}
    assert body["rate_limit_max"] > 0
    assert body["rate_limit_window_minutes"] > 0


async def test_update_config_persists_every_field(
    cod_flow: CodFlowHarness, restored_config: dict
) -> None:
    response = await cod_flow.client.put(
        "/api/admin/fraud/config",
        json={
            "duplicate_window_hours": 48,
            "duplicate_match_fields": ["phone"],
            "rate_limit_max": 9,
            "rate_limit_window_minutes": 15,
        },
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate_window_hours"] == 48
    assert body["duplicate_match_fields"] == ["phone"]
    assert body["rate_limit_max"] == 9
    assert body["rate_limit_window_minutes"] == 15


async def test_update_config_leaves_omitted_fields_untouched(
    cod_flow: CodFlowHarness, restored_config: dict
) -> None:
    response = await cod_flow.client.put(
        "/api/admin/fraud/config",
        json={"rate_limit_max": 7},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rate_limit_max"] == 7
    assert body["duplicate_window_hours"] == restored_config["duplicate_window_hours"]
    assert body["duplicate_match_fields"] == restored_config["duplicate_match_fields"]


async def test_update_config_records_an_audit_row(
    cod_flow: CodFlowHarness, restored_config: dict
) -> None:
    actor = "e2e-fraud-admin"
    try:
        await cod_flow.client.put(
            "/api/admin/fraud/config",
            json={"duplicate_window_hours": 36},
            headers=cod_flow.admin_headers(actor),
        )

        rows = await cod_flow.db.auditlog.find_many(
            where={"actor": actor, "action": "fraud.config.update"}
        )
        assert len(rows) == 1
        assert rows[0].targetType == "fraud_config"
        assert rows[0].result == "success"
    finally:
        await cod_flow.db.auditlog.delete_many(where={"actor": actor})


async def test_update_config_rejects_zero_without_replacing_the_active_config(
    cod_flow: CodFlowHarness, restored_config: dict
) -> None:
    response = await cod_flow.client.put(
        "/api/admin/fraud/config",
        json={"rate_limit_max": 0},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "rate_limit_max"
    stored = await cod_flow.client.get("/api/admin/fraud/config", headers=cod_flow.admin_headers())
    assert stored.json()["rate_limit_max"] == restored_config["rate_limit_max"]


async def test_update_config_rejects_an_empty_match_field_set(
    cod_flow: CodFlowHarness, restored_config: dict
) -> None:
    response = await cod_flow.client.put(
        "/api/admin/fraud/config",
        json={"duplicate_match_fields": []},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "duplicate_match_fields"


async def test_update_config_rejects_an_unsupported_match_field(
    cod_flow: CodFlowHarness, restored_config: dict
) -> None:
    response = await cod_flow.client.put(
        "/api/admin/fraud/config",
        json={"duplicate_match_fields": ["phone", "address"]},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "duplicate_match_fields"


# --- Manual blacklist --------------------------------------------------------


async def test_add_blacklist_entry_normalizes_a_phone_and_is_listed(
    cod_flow: CodFlowHarness,
) -> None:
    phone = unique_phone()
    spaced = f"{phone[:3]} {phone[3:6]} {phone[6:]}"
    created = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={
            "entry_type": "phone",
            "value_normalized": spaced,
            "reason": "  Pedidos falsos  ",
        },
        headers=cod_flow.admin_headers(),
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    try:
        body = created.json()
        assert body["entry_type"] == "phone"
        # Stored in the same form the fraud checks compare against, so spacing
        # in the submitted value cannot hide a match (Requirement 6.5).
        assert body["value_normalized"] == normalize_phone_key(phone, DEFAULT_REGIONAL.phone)
        assert body["reason"] == "Pedidos falsos"
        assert body["created_at"]

        listed = await cod_flow.client.get(
            "/api/admin/fraud/blacklist", headers=cod_flow.admin_headers()
        )
        assert listed.status_code == 200
        match = next(entry for entry in listed.json()["entries"] if entry["id"] == entry_id)
        assert match["value_normalized"] == body["value_normalized"]
    finally:
        await _delete_blacklist_entry(cod_flow, entry_id)


async def test_add_blacklist_entry_canonicalizes_an_ip(cod_flow: CodFlowHarness) -> None:
    suffix = uuid.uuid4().hex[:4]
    expanded = f"2001:0db8:e2e0:0000:0000:0000:0000:{suffix}"
    created = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={
            "entry_type": "ip",
            "value_normalized": expanded,
            "reason": "Abuso reiterado",
        },
        headers=cod_flow.admin_headers(),
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    try:
        assert created.json()["value_normalized"] == f"2001:db8:e2e0::{suffix.lstrip('0') or '0'}"
    finally:
        await _delete_blacklist_entry(cod_flow, entry_id)


async def test_add_blacklist_entry_records_an_audit_row(cod_flow: CodFlowHarness) -> None:
    actor = "e2e-fraud-admin"
    created = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={
            "entry_type": "ip",
            "value_normalized": _unique_ip(),
            "reason": "Auditoria",
        },
        headers=cod_flow.admin_headers(actor),
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    try:
        rows = await cod_flow.db.auditlog.find_many(
            where={"actor": actor, "targetType": "blacklist_entry", "targetId": str(entry_id)}
        )
        assert [row.action for row in rows] == ["fraud.blacklist.add"]
    finally:
        await _delete_blacklist_entry(cod_flow, entry_id)
        await cod_flow.db.auditlog.delete_many(where={"actor": actor})


async def test_add_blacklist_entry_rejects_a_duplicate_of_the_same_type(
    cod_flow: CodFlowHarness,
) -> None:
    payload = {
        "entry_type": "ip",
        "value_normalized": _unique_ip(),
        "reason": "Primera razon",
    }
    created = await cod_flow.client.post(
        "/api/admin/fraud/blacklist", json=payload, headers=cod_flow.admin_headers()
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    try:
        conflict = await cod_flow.client.post(
            "/api/admin/fraud/blacklist",
            json={**payload, "reason": "Segunda razon"},
            headers=cod_flow.admin_headers(),
        )

        assert conflict.status_code == 409
        # The existing entry keeps its original reason (Requirement 6.7).
        stored = await cod_flow.db.blacklistentry.find_unique(where={"id": entry_id})
        assert stored is not None
        assert stored.reason == "Primera razon"
    finally:
        await _delete_blacklist_entry(cod_flow, entry_id)


async def test_add_blacklist_entry_rejects_an_invalid_phone(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={"entry_type": "phone", "value_normalized": "12345", "reason": "Motivo"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "value_normalized"


async def test_add_blacklist_entry_rejects_an_invalid_ip(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={"entry_type": "ip", "value_normalized": "999.0.0.1", "reason": "Motivo"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "value_normalized"


async def test_add_blacklist_entry_rejects_an_unsupported_entry_type(
    cod_flow: CodFlowHarness,
) -> None:
    response = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={"entry_type": "email", "value_normalized": "a@b.co", "reason": "Motivo"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "entry_type"


async def test_add_blacklist_entry_rejects_a_blank_reason(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={"entry_type": "ip", "value_normalized": "198.51.100.30", "reason": "   "},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "reason"


async def test_remove_blacklist_entry_preserves_historical_fraud_flags(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    blocked_ip = _unique_ip()
    phone = unique_phone()
    order = await cod_flow.db.order.create(
        {
            "productId": landing.product_id,
            "landingId": landing.landing_id,
            "landingSlug": landing.slug,
            "customerName": "Cliente Historico",
            "phoneE164": f"+57{phone}",
            "phoneNormalizedKey": normalize_phone_key(phone, DEFAULT_REGIONAL.phone),
            "department": "Cundinamarca",
            "city": "Bogota",
            "address": "Calle 1 #2-3",
            "quantity": 1,
            "unitPrice": Decimal("59900.00"),
            "totalPrice": Decimal("59900.00"),
            "status": "flagged_fraud",
            "ipAddress": blocked_ip,
            "userAgent": "e2e",
        }
    )
    flag = await cod_flow.db.fraudflag.create(
        {
            "orderId": order.id,
            "flagType": "blacklist",
            # `detail` is a jsonb column: Prisma needs the explicit Json wrapper.
            "detail": Json({"entry_type": "ip", "reason": "Historico"}),
        }
    )
    created = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={
            "entry_type": "ip",
            "value_normalized": blocked_ip,
            "reason": "Historico",
        },
        headers=cod_flow.admin_headers(),
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]

    response = await cod_flow.client.delete(
        f"/api/admin/fraud/blacklist/{entry_id}", headers=cod_flow.admin_headers()
    )

    assert response.status_code == 200
    assert await cod_flow.db.blacklistentry.find_unique(where={"id": entry_id}) is None
    assert await cod_flow.db.fraudflag.find_unique(where={"id": flag.id}) is not None
    await _delete_blacklist_entry(cod_flow, entry_id)


async def test_remove_unknown_blacklist_entry_returns_404(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.delete(
        "/api/admin/fraud/blacklist/99999999", headers=cod_flow.admin_headers()
    )

    assert response.status_code == 404


# --- GeoIP rules -------------------------------------------------------------


async def test_create_geoip_rule_normalizes_the_location_code(
    cod_flow: CodFlowHarness,
) -> None:
    code = _unique_location_code()
    created = await cod_flow.client.post(
        "/api/admin/fraud/geoip-rules",
        json={"location_code": code.lower(), "action": "flag"},
        headers=cod_flow.admin_headers(),
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    try:
        body = created.json()
        # Stored uppercase, matching the resolver's output (Requirement 6.13).
        assert body["location_code"] == code
        assert body["action"] == "flag"
        assert body["enabled"] is True
        assert body["created_at"] and body["updated_at"]

        listed = await cod_flow.client.get(
            "/api/admin/fraud/geoip-rules", headers=cod_flow.admin_headers()
        )
        assert listed.status_code == 200
        assert any(rule["id"] == rule_id for rule in listed.json()["rules"])
    finally:
        await _delete_geoip_rule(cod_flow, rule_id)


async def test_create_geoip_rule_rejects_an_unsupported_action(
    cod_flow: CodFlowHarness,
) -> None:
    response = await cod_flow.client.post(
        "/api/admin/fraud/geoip-rules",
        json={"location_code": _unique_location_code(), "action": "drop"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "action"


async def test_create_geoip_rule_rejects_a_duplicate_location(
    cod_flow: CodFlowHarness,
) -> None:
    code = _unique_location_code()
    created = await cod_flow.client.post(
        "/api/admin/fraud/geoip-rules",
        json={"location_code": code, "action": "flag"},
        headers=cod_flow.admin_headers(),
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    try:
        conflict = await cod_flow.client.post(
            "/api/admin/fraud/geoip-rules",
            json={"location_code": code.lower(), "action": "block"},
            headers=cod_flow.admin_headers(),
        )

        assert conflict.status_code == 409
        stored = await cod_flow.db.geoiprule.find_unique(where={"id": rule_id})
        assert stored is not None
        assert stored.action == "flag"
    finally:
        await _delete_geoip_rule(cod_flow, rule_id)


async def test_patch_geoip_rule_accepts_a_partial_body(cod_flow: CodFlowHarness) -> None:
    code = _unique_location_code()
    created = await cod_flow.client.post(
        "/api/admin/fraud/geoip-rules",
        json={"location_code": code, "action": "flag"},
        headers=cod_flow.admin_headers(),
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    try:
        response = await cod_flow.client.patch(
            f"/api/admin/fraud/geoip-rules/{rule_id}",
            json={"enabled": False},
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is False
        # Untouched fields keep their stored values.
        assert body["location_code"] == code
        assert body["action"] == "flag"
    finally:
        await _delete_geoip_rule(cod_flow, rule_id)


async def test_patch_geoip_rule_records_an_audit_row(cod_flow: CodFlowHarness) -> None:
    actor = "e2e-fraud-admin"
    created = await cod_flow.client.post(
        "/api/admin/fraud/geoip-rules",
        json={"location_code": _unique_location_code(), "action": "flag"},
        headers=cod_flow.admin_headers(actor),
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    try:
        await cod_flow.client.patch(
            f"/api/admin/fraud/geoip-rules/{rule_id}",
            json={"action": "block"},
            headers=cod_flow.admin_headers(actor),
        )

        actions = {
            row.action
            for row in await cod_flow.db.auditlog.find_many(
                where={"targetType": "geoip_rule", "targetId": str(rule_id)}
            )
        }
        assert actions == {"fraud.geoip.create", "fraud.geoip.update"}
    finally:
        await _delete_geoip_rule(cod_flow, rule_id)
        await cod_flow.db.auditlog.delete_many(where={"actor": actor})


async def test_patch_unknown_geoip_rule_returns_404(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.patch(
        "/api/admin/fraud/geoip-rules/99999999",
        json={"enabled": False},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 404


async def test_delete_geoip_rule_removes_it_from_evaluation(cod_flow: CodFlowHarness) -> None:
    created = await cod_flow.client.post(
        "/api/admin/fraud/geoip-rules",
        json={"location_code": _unique_location_code(), "action": "block"},
        headers=cod_flow.admin_headers(),
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    response = await cod_flow.client.delete(
        f"/api/admin/fraud/geoip-rules/{rule_id}", headers=cod_flow.admin_headers()
    )

    assert response.status_code == 200
    assert await cod_flow.db.geoiprule.find_unique(where={"id": rule_id}) is None
    await _delete_geoip_rule(cod_flow, rule_id)


async def test_delete_unknown_geoip_rule_returns_404(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.delete(
        "/api/admin/fraud/geoip-rules/99999999", headers=cod_flow.admin_headers()
    )

    assert response.status_code == 404


# --- Authorization -----------------------------------------------------------


async def test_fraud_endpoints_require_an_admin_session(cod_flow: CodFlowHarness) -> None:
    assert (await cod_flow.client.get("/api/admin/fraud/config")).status_code == 401
    assert (await cod_flow.client.get("/api/admin/fraud/blacklist")).status_code == 401
    assert (await cod_flow.client.get("/api/admin/fraud/geoip-rules")).status_code == 401

    anonymous_value = _unique_ip()
    anonymous_write = await cod_flow.client.post(
        "/api/admin/fraud/blacklist",
        json={"entry_type": "ip", "value_normalized": anonymous_value, "reason": "Sin sesion"},
    )
    assert anonymous_write.status_code == 401
    assert await cod_flow.db.blacklistentry.count(where={"valueNormalized": anonymous_value}) == 0
