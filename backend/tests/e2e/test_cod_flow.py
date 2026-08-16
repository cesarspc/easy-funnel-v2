"""End-to-end tests for the COD flow.

Proves the critical path (publish active product -> open `/api/public/landings/{slug}`
-> record view -> click CTA -> submit COD form -> apply fraud rules -> read the
order and its flags back through the admin data layer) and each classification
branch:

- clean submission -> `pending` with no flags (Requirement 5.13)
- duplicate -> `flagged_fraud` + duplicate flag (Requirements 6.2-6.4)
- manual blacklist -> `flagged_fraud` + blacklist flag (Requirement 6.5)
- rate limit -> `flagged_fraud` + IP rate-limit flag on the 6th attempt
  (Requirements 6.10-6.12)
- GeoIP `flag` and `block` -> both persist a reviewable `flagged_fraud` order
  rather than dropping the submission (Requirements 6.13-6.15, 5.15)
- draft / paused / retired / unknown slug -> one identical 404 (Requirement 3.24)

Fixtures, seeding, and the two injected doubles (Redis, GeoIP) are documented
in `tests/e2e/conftest.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domains.orders.normalization import normalize_colombian_phone_key

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness, unique_phone

pytestmark = requires_database

_CLIENT_IP = "203.0.113.10"
_USER_AGENT = "Mozilla/5.0 (E2E COD flow test)"


def _order_payload(slug: str, phone: str) -> dict:
    return {
        "landing_slug": slug,
        "full_name": "Juana Perez",
        "phone": phone,
        "department": "CUNDINAMARCA",
        "city": "SOACHA",
        "address": "Calle 123 #45-67",
        "quantity": 1,
    }


def _submission_headers(ip_address: str = _CLIENT_IP) -> dict:
    """Headers a real request carries: forwarded client IP + user agent."""
    return {"X-Forwarded-For": ip_address, "User-Agent": _USER_AGENT}


async def test_e2e_cod_flow_clean_order(cod_flow: CodFlowHarness) -> None:
    """Clean submission walks the whole path and lands as `pending`, no flags."""
    landing = await cod_flow.seed_landing()
    phone = unique_phone()

    # 1. Open the public landing (active product + published landing).
    landing_response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

    assert landing_response.status_code == 200
    payload = landing_response.json()
    assert payload["slug"] == landing.slug
    assert payload["landing_id"] == landing.landing_id
    assert payload["form_presentation"] == "inline"

    # 2. Record the view on display.
    view_response = await cod_flow.client.post(
        f"/api/public/landings/{landing.slug}/view",
    )
    assert view_response.status_code == 200

    # 3. Click the CTA.
    click_response = await cod_flow.client.post(f"/api/public/landings/{landing.slug}/cta-click")
    assert click_response.status_code == 200

    # 4. Submit the COD form.
    order_response = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, phone),
        headers=_submission_headers(),
    )

    assert order_response.status_code == 201
    body = order_response.json()
    assert body["status"] == "pending"
    assert isinstance(body["order_id"], int)

    # 5. The order and its (absent) flags are readable by the admin data layer,
    #    with the attribution and request metadata captured (Requirement 5.9).
    orders = await cod_flow.orders_for(landing)
    assert len(orders) == 1
    stored = orders[0]
    assert stored.id == body["order_id"]
    assert stored.status == "pending"
    assert stored.fraudFlags == []
    assert stored.landingSlug == landing.slug
    assert stored.productId == landing.product_id
    assert stored.phoneE164 == f"+57{phone}"
    assert stored.ipAddress == _CLIENT_IP
    assert stored.userAgent == _USER_AGENT

    # 6. Reading analytics reconciles the live Redis counters durably.
    today = datetime.now(UTC).date().isoformat()
    analytics_response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={today}&date_to={today}"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )
    assert analytics_response.status_code == 200
    assert analytics_response.json()[0]["views"] == 1
    assert analytics_response.json()[0]["clicks"] == 1

    traffic = await cod_flow.db.query_raw(
        """
        SELECT "view_count", "cta_click_count"
        FROM "landing_analytics_daily"
        WHERE "landing_id" = $1
        """,
        landing.landing_id,
    )
    assert traffic == [{"view_count": 1, "cta_click_count": 1}]
    assert await cod_flow.db.landingview.count(where={"landingId": landing.landing_id}) == 0
    assert await cod_flow.db.ctaclick.count(where={"landingId": landing.landing_id}) == 0


async def test_e2e_cod_flow_duplicate_detection(cod_flow: CodFlowHarness) -> None:
    """Same phone + IP inside the window flags the second order as fraud."""
    landing = await cod_flow.seed_landing()
    phone = unique_phone()
    payload = _order_payload(landing.slug, phone)

    first = await cod_flow.client.post(
        "/api/public/orders", json=payload, headers=_submission_headers()
    )
    second = await cod_flow.client.post(
        "/api/public/orders", json=payload, headers=_submission_headers()
    )

    assert first.status_code == 201
    assert first.json()["status"] == "pending"
    assert second.status_code == 201
    assert second.json()["status"] == "flagged_fraud"

    orders = await cod_flow.orders_for(landing)
    assert len(orders) == 2
    flagged = orders[1]
    flag_types = [flag.flagType for flag in flagged.fraudFlags]
    assert flag_types == ["duplicate"]
    assert flagged.fraudFlags[0].detail["order_id"] == orders[0].id


async def test_e2e_cod_flow_blacklist(cod_flow: CodFlowHarness) -> None:
    """A blacklisted phone flags the order and preserves the entry reason."""
    landing = await cod_flow.seed_landing()
    phone = unique_phone()
    await cod_flow.blacklist_phone(
        normalize_colombian_phone_key(phone), reason="Chargeback history"
    )

    response = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, phone),
        headers=_submission_headers(),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "flagged_fraud"

    (stored,) = await cod_flow.orders_for(landing)
    assert [flag.flagType for flag in stored.fraudFlags] == ["blacklist"]
    detail = stored.fraudFlags[0].detail
    assert detail["entry_type"] == "phone"
    assert detail["reason"] == "Chargeback history"


async def test_e2e_cod_flow_rate_limit(cod_flow: CodFlowHarness) -> None:
    """The sixth submission from one IP in the window carries an IP rate-limit flag.

    Each attempt uses a different phone number so the default five-per-ten-minute
    IP limit is the only rule that can trigger (Requirement 6.11).
    """
    landing = await cod_flow.seed_landing()

    statuses = []
    for _ in range(6):
        response = await cod_flow.client.post(
            "/api/public/orders",
            json=_order_payload(landing.slug, unique_phone()),
            headers=_submission_headers(),
        )
        assert response.status_code == 201
        statuses.append(response.json()["status"])

    assert statuses == ["pending"] * 5 + ["flagged_fraud"]

    orders = await cod_flow.orders_for(landing)
    assert len(orders) == 6
    flagged = orders[5]
    assert [flag.flagType for flag in flagged.fraudFlags] == ["rate_limit_ip"]
    detail = flagged.fraudFlags[0].detail
    assert detail["count"] == 6
    assert detail["limit"] == 5
    assert detail["window_minutes"] == 10


async def test_e2e_cod_flow_geoip_flag(cod_flow: CodFlowHarness) -> None:
    """A matching GeoIP `flag` rule produces a reviewable flagged order."""
    landing = await cod_flow.seed_landing()
    await cod_flow.add_geoip_rule("XK", action="flag")
    cod_flow.resolve_geoip_as("XK")

    response = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, unique_phone()),
        headers=_submission_headers(),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "flagged_fraud"

    (stored,) = await cod_flow.orders_for(landing)
    assert [flag.flagType for flag in stored.fraudFlags] == ["geoip"]
    assert stored.fraudFlags[0].detail["action"] == "flag"


async def test_e2e_cod_flow_geoip_block(cod_flow: CodFlowHarness) -> None:
    """A `block` rule also persists a reviewable order — never a silent drop."""
    landing = await cod_flow.seed_landing()
    await cod_flow.add_geoip_rule("XM", action="block")
    cod_flow.resolve_geoip_as("XM")

    response = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, unique_phone()),
        headers=_submission_headers(),
    )

    # Not a 403 and not discarded: the submission is stored for review.
    assert response.status_code == 201
    assert response.json()["status"] == "flagged_fraud"

    (stored,) = await cod_flow.orders_for(landing)
    assert [flag.flagType for flag in stored.fraudFlags] == ["geoip"]
    assert stored.fraudFlags[0].detail["action"] == "block"


async def test_e2e_cod_flow_not_found_denial(cod_flow: CodFlowHarness) -> None:
    """Unknown, draft, paused, and retired slugs return one identical 404."""
    draft = await cod_flow.seed_landing(landing_status="draft")
    paused = await cod_flow.seed_landing(product_status="paused")
    retired = await cod_flow.seed_landing(product_status="retired")

    responses = [
        await cod_flow.client.get("/api/public/landings/unknown-slug-e2e"),
        await cod_flow.client.get(f"/api/public/landings/{draft.slug}"),
        await cod_flow.client.get(f"/api/public/landings/{paused.slug}"),
        await cod_flow.client.get(f"/api/public/landings/{retired.slug}"),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404]
    bodies = [response.json() for response in responses]
    assert all(body == bodies[0] for body in bodies), "denial responses must be identical"


async def test_e2e_cod_flow_denied_landing_rejects_order_submission(
    cod_flow: CodFlowHarness,
) -> None:
    """A draft landing cannot take orders: validation error, no order stored."""
    draft = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(draft.slug, unique_phone()),
        headers=_submission_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "landing_slug"
    assert await cod_flow.orders_for(draft) == []


async def test_e2e_cod_flow_validation_error_creates_no_order(
    cod_flow: CodFlowHarness,
) -> None:
    """An invalid phone is rejected field-specifically without storing an order."""
    landing = await cod_flow.seed_landing()

    response = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, "12345"),
        headers=_submission_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "phone"
    assert await cod_flow.orders_for(landing) == []


async def test_e2e_cod_flow_order_visible_in_admin_with_flags(
    cod_flow: CodFlowHarness,
) -> None:
    """Step 6 of the critical path: the flagged order is reviewable in admin."""
    landing = await cod_flow.seed_landing()
    phone = unique_phone()
    payload = _order_payload(landing.slug, phone)
    await cod_flow.client.post("/api/public/orders", json=payload, headers=_submission_headers())
    flagged = await cod_flow.client.post(
        "/api/public/orders", json=payload, headers=_submission_headers()
    )
    order_id = flagged.json()["order_id"]

    listed = await cod_flow.client.get(
        "/api/admin/orders",
        params={"landing_id": landing.landing_id},
        headers=cod_flow.admin_headers(),
    )
    detail = await cod_flow.client.get(
        f"/api/admin/orders/{order_id}", headers=cod_flow.admin_headers()
    )

    assert listed.status_code == 200
    assert listed.json()["count"] == 2
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == order_id
    assert detail_body["status"] == "flagged_fraud"
    assert detail_body["landing_slug"] == landing.slug
    assert detail_body["phone_e164"] == f"+57{phone}"
    assert detail_body["product_name"]
    assert detail_body["product_sku"]
    assert detail_body["unit_price"] > 0
    assert detail_body["discount_percent"] == 0
    assert detail_body["total_price"] == detail_body["unit_price"]
    assert detail_body["ip_address"]
    assert detail_body["user_agent"]
    assert detail_body["created_at"]
    assert detail_body["updated_at"]
    assert [flag["flag_type"] for flag in detail_body["fraud_flags"]] == ["duplicate"]
    assert detail_body["fraud_flags"][0]["id"]
    assert detail_body["fraud_flags"][0]["created_at"]


async def test_e2e_cod_flow_admin_endpoints_require_authentication(
    cod_flow: CodFlowHarness,
) -> None:
    """Customer data is never public: admin order endpoints reject anonymous calls."""
    landing = await cod_flow.seed_landing()

    listed = await cod_flow.client.get(
        "/api/admin/orders", params={"landing_id": landing.landing_id}
    )

    assert listed.status_code == 401


async def test_e2e_cod_flow_order_status_transitions(cod_flow: CodFlowHarness) -> None:
    """Legal transitions apply; an illegal one is rejected without changing status."""
    landing = await cod_flow.seed_landing()
    submitted = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, unique_phone()),
        headers=_submission_headers(),
    )
    order_id = submitted.json()["order_id"]

    async def transition(to_status: str):
        return await cod_flow.client.post(
            f"/api/admin/orders/{order_id}/transition",
            json={"to_status": to_status},
            headers=cod_flow.admin_headers(),
        )

    # pending -> confirmed -> shipped -> delivered (Requirement 5.19)
    for to_status in ("confirmed", "shipped", "delivered"):
        response = await transition(to_status)
        assert response.status_code == 200, to_status
        assert response.json()["status"] == to_status

    # delivered -> cancelled is outside the graph (Requirement 5.22)
    rejected = await transition("cancelled")

    assert rejected.status_code == 409
    (stored,) = await cod_flow.orders_for(landing)
    assert stored.status == "delivered"


async def test_e2e_cod_flow_csv_export(cod_flow: CodFlowHarness) -> None:
    """Export returns the order as CSV data, neutralizing formula-looking values."""
    landing = await cod_flow.seed_landing()
    phone = unique_phone()
    payload = _order_payload(landing.slug, phone)
    # A name a spreadsheet would otherwise evaluate as a formula.
    payload["full_name"] = "=cmd|' /c calc'!A1"
    submitted = await cod_flow.client.post(
        "/api/public/orders", json=payload, headers=_submission_headers()
    )
    assert submitted.status_code == 201

    export = await cod_flow.client.get(
        "/api/admin/orders/export.csv",
        params={"landing_id": landing.landing_id},
        headers=cod_flow.admin_headers(),
    )

    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    body = export.text
    assert landing.slug in body
    assert f"+57{phone}" in body
    # Requirement 10: the exported value must not start a formula.
    assert "=cmd|" in body
    assert "\n=cmd|" not in body
    assert not body.splitlines()[1].startswith("=")
