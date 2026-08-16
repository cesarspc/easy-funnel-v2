"""Admin Analytics API tests (Requirements 8.11-8.13, 8.21, 10.2, 10.9).

Activity is generated through the real public endpoints (view, CTA click, COD
submission) so the per-day and per-landing aggregations are read back from the
bounded daily counters the application itself wrote.

The database is shared with every other test, so day-level totals are asserted
as "at least what this test produced", while per-landing figures — which are
scoped to a freshly seeded landing — are asserted exactly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import app.services.analytics_query_service as analytics_query_module
from app.domains.orders.normalization import normalize_colombian_phone_key
from app.main import app
from app.redis.client import get_redis

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness, SeededLanding, unique_phone
from tests.redis.fakes import FakeHangingRedis, FakeUnavailableRedis

pytestmark = requires_database

_CLIENT_IP = "203.0.113.55"
_USER_AGENT = "Mozilla/5.0 (E2E analytics test)"


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _order_payload(slug: str, phone: str) -> dict:
    return {
        "landing_slug": slug,
        "full_name": "Ana Gomez",
        "phone": phone,
        "department": "ANTIOQUIA",
        "city": "MEDELLÍN",
        "address": "Carrera 45 #12-34",
        "quantity": 1,
    }


async def _record_views(cod_flow: CodFlowHarness, landing: SeededLanding, count: int) -> None:
    for _ in range(count):
        response = await cod_flow.client.post(
            f"/api/public/landings/{landing.slug}/view",
        )
        assert response.status_code == 200


async def _record_clicks(cod_flow: CodFlowHarness, landing: SeededLanding, count: int) -> None:
    for _ in range(count):
        response = await cod_flow.client.post(f"/api/public/landings/{landing.slug}/cta-click")
        assert response.status_code == 200


async def _submit_order(cod_flow: CodFlowHarness, landing: SeededLanding) -> dict:
    response = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, unique_phone()),
        headers={"X-Forwarded-For": _CLIENT_IP, "User-Agent": _USER_AGENT},
    )
    assert response.status_code == 201
    return response.json()


# --- Per-landing analytics ---------------------------------------------------


async def test_landing_analytics_reports_views_clicks_orders_and_conversion(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    await _record_views(cod_flow, landing, 4)
    await _record_clicks(cod_flow, landing, 2)
    await _submit_order(cod_flow, landing)

    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    (row,) = response.json()
    assert row["landing_id"] == landing.landing_id
    assert row["views"] == 4
    assert row["clicks"] == 2
    assert row["orders"] == 1
    # Orders divided by views, not the inverse (Requirement 8.12).
    assert row["conversion_rate"] == 0.25

    stored = await cod_flow.db.query_raw(
        """
        SELECT "view_count", "cta_click_count"
        FROM "landing_analytics_daily"
        WHERE "landing_id" = $1
        """,
        landing.landing_id,
    )
    assert stored == [{"view_count": 4, "cta_click_count": 2}]


async def test_concurrent_views_increment_one_daily_row_without_lost_updates(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()

    responses = await asyncio.gather(
        *(cod_flow.client.post(f"/api/public/landings/{landing.slug}/view") for _ in range(20))
    )

    assert all(response.status_code == 200 for response in responses)
    # The hot request path has not written PostgreSQL once per view.
    assert (
        await cod_flow.db.query_raw(
            'SELECT COUNT(*) AS count FROM "landing_analytics_daily" WHERE "landing_id" = $1',
            landing.landing_id,
        )
    ) == [{"count": 0}]

    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )
    assert response.status_code == 200
    assert response.json()[0]["views"] == 20

    stored = await cod_flow.db.query_raw(
        """
        SELECT "view_count", "cta_click_count"
        FROM "landing_analytics_daily"
        WHERE "landing_id" = $1
        """,
        landing.landing_id,
    )
    assert stored == [{"view_count": 20, "cta_click_count": 0}]


async def test_reports_combine_legacy_events_with_new_daily_counters(
    cod_flow: CodFlowHarness,
) -> None:
    """A rolling deployment neither loses nor double-counts old-instance writes."""
    landing = await cod_flow.seed_landing()
    await cod_flow.db.landingview.create(data={"landingId": landing.landing_id})
    await cod_flow.db.ctaclick.create(data={"landingId": landing.landing_id})
    await _record_views(cod_flow, landing, 1)
    await _record_clicks(cod_flow, landing, 1)

    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    (row,) = response.json()
    assert row["views"] == 2
    assert row["clicks"] == 2


async def test_redis_outage_records_separate_durable_fallback_counts(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    app.dependency_overrides[get_redis] = lambda: FakeUnavailableRedis()
    try:
        view = await cod_flow.client.post(f"/api/public/landings/{landing.slug}/view")
        click = await cod_flow.client.post(f"/api/public/landings/{landing.slug}/cta-click")
    finally:
        app.dependency_overrides[get_redis] = lambda: cod_flow.redis

    assert view.status_code == 200
    assert click.status_code == 200
    stored = await cod_flow.db.query_raw(
        """
        SELECT "view_count", "cta_click_count",
               "fallback_view_count", "fallback_cta_click_count"
        FROM "landing_analytics_daily"
        WHERE "landing_id" = $1
        """,
        landing.landing_id,
    )
    assert stored == [
        {
            "view_count": 0,
            "cta_click_count": 0,
            "fallback_view_count": 1,
            "fallback_cta_click_count": 1,
        }
    ]

    # Redis recovers during the same day. Its later absolute snapshot remains
    # independent from the already-durable fallback increments.
    await _record_views(cod_flow, landing, 2)
    await _record_clicks(cod_flow, landing, 1)

    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )
    assert response.status_code == 200
    assert response.json()[0]["views"] == 3
    assert response.json()[0]["clicks"] == 2

    reconciled = await cod_flow.db.query_raw(
        """
        SELECT "view_count", "cta_click_count",
               "fallback_view_count", "fallback_cta_click_count"
        FROM "landing_analytics_daily"
        WHERE "landing_id" = $1
        """,
        landing.landing_id,
    )
    assert reconciled == [
        {
            "view_count": 2,
            "cta_click_count": 1,
            "fallback_view_count": 1,
            "fallback_cta_click_count": 1,
        }
    ]


async def test_slow_redis_cannot_leave_analytics_loading_indefinitely(
    cod_flow: CodFlowHarness,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    landing = await cod_flow.seed_landing()
    monkeypatch.setattr(analytics_query_module, "_TRAFFIC_RECONCILE_TIMEOUT_SECONDS", 0.01)
    app.dependency_overrides[get_redis] = lambda: FakeHangingRedis()
    try:
        response = await cod_flow.client.get(
            f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
            f"&landing_id={landing.landing_id}",
            headers=cod_flow.admin_headers(),
        )
    finally:
        app.dependency_overrides[get_redis] = lambda: cod_flow.redis

    assert response.status_code == 200
    assert response.json()[0]["landing_id"] == landing.landing_id


async def test_landing_analytics_returns_zero_conversion_without_views(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    await _submit_order(cod_flow, landing)

    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )

    (row,) = response.json()
    assert row["orders"] == 1
    assert row["views"] == 0
    # Zero-guarded denominator instead of a division error (Requirement 8.21).
    assert row["conversion_rate"] == 0.0


async def test_landing_analytics_covers_a_landing_without_activity(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()

    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )

    (row,) = response.json()
    assert (row["views"], row["clicks"], row["orders"], row["conversion_rate"]) == (0, 0, 0, 0.0)


async def test_landing_analytics_excludes_activity_outside_the_range(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    await _record_views(cod_flow, landing, 3)

    response = await cod_flow.client.get(
        "/api/admin/analytics/landings?date_from=2020-01-01&date_to=2020-01-31"
        f"&landing_id={landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )

    (row,) = response.json()
    assert row["views"] == 0


async def test_landing_analytics_without_a_landing_id_covers_every_landing(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    await _record_views(cod_flow, landing, 1)

    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    rows = response.json()
    match = next(row for row in rows if row["landing_id"] == landing.landing_id)
    assert match["views"] == 1


async def test_landing_analytics_for_an_unknown_landing_is_empty(
    cod_flow: CodFlowHarness,
) -> None:
    response = await cod_flow.client.get(
        f"/api/admin/analytics/landings?date_from={_today()}&date_to={_today()}"
        "&landing_id=99999999",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    assert response.json() == []


# --- Orders per day ----------------------------------------------------------


async def test_orders_per_day_counts_todays_order_with_a_date_only_range(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    before = await cod_flow.client.get(
        f"/api/admin/analytics/orders-per-day?date_from={_today()}&date_to={_today()}",
        headers=cod_flow.admin_headers(),
    )
    baseline = next((row["count"] for row in before.json() if row["date"] == _today()), 0)

    await _submit_order(cod_flow, landing)

    response = await cod_flow.client.get(
        f"/api/admin/analytics/orders-per-day?date_from={_today()}&date_to={_today()}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    today_row = next(row for row in response.json() if row["date"] == _today())
    # A date-only upper bound must include orders created later the same day
    # (Requirement 8.11): the inclusive range is what makes this pass.
    assert today_row["count"] == baseline + 1


async def test_orders_per_day_returns_no_rows_for_a_past_range(
    cod_flow: CodFlowHarness,
) -> None:
    response = await cod_flow.client.get(
        "/api/admin/analytics/orders-per-day?date_from=2020-01-01&date_to=2020-01-31",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    assert response.json() == []


# --- Fraud analytics ---------------------------------------------------------


async def test_fraud_analytics_counts_flagged_orders_not_flags(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    before = await cod_flow.client.get(
        f"/api/admin/analytics/fraud?date_from={_today()}&date_to={_today()}",
        headers=cod_flow.admin_headers(),
    )
    baseline = next(
        (
            (row["total_orders"], row["flagged_orders"])
            for row in before.json()
            if row["date"] == _today()
        ),
        (0, 0),
    )

    # One clean order, then one submission carrying two flags at once
    # (blacklisted phone + GeoIP rule), which is still a single flagged order.
    await _submit_order(cod_flow, landing)
    phone = unique_phone()
    await cod_flow.blacklist_phone(normalize_colombian_phone_key(phone), reason="Analitica")
    await cod_flow.add_geoip_rule("VE", action="flag")
    cod_flow.resolve_geoip_as("VE")
    flagged = await cod_flow.client.post(
        "/api/public/orders",
        json=_order_payload(landing.slug, phone),
        headers={"X-Forwarded-For": _CLIENT_IP, "User-Agent": _USER_AGENT},
    )
    assert flagged.status_code == 201
    assert flagged.json()["status"] == "flagged_fraud"
    stored = await cod_flow.db.order.find_unique(
        where={"id": flagged.json()["order_id"]}, include={"fraudFlags": True}
    )
    assert stored is not None
    assert len(stored.fraudFlags or []) >= 2

    response = await cod_flow.client.get(
        f"/api/admin/analytics/fraud?date_from={_today()}&date_to={_today()}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    row = next(row for row in response.json() if row["date"] == _today())
    assert row["total_orders"] == baseline[0] + 2
    # Two flags on one order still count as one flagged order (Requirement 8.13).
    assert row["flagged_orders"] == baseline[1] + 1
    assert row["flagged_fraud_rate"] <= 1.0


async def test_fraud_analytics_rate_is_zero_for_a_range_without_orders(
    cod_flow: CodFlowHarness,
) -> None:
    response = await cod_flow.client.get(
        "/api/admin/analytics/fraud?date_from=2020-01-01&date_to=2020-01-31",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    assert response.json() == []


# --- Input validation and authorization --------------------------------------


async def test_malformed_date_is_a_field_error_not_a_server_error(
    cod_flow: CodFlowHarness,
) -> None:
    for path in ("orders-per-day", "landings", "fraud"):
        response = await cod_flow.client.get(
            f"/api/admin/analytics/{path}?date_from=ayer&date_to={_today()}",
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "date_from"


async def test_inverted_range_is_rejected(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.get(
        "/api/admin/analytics/orders-per-day?date_from=2026-07-24&date_to=2026-07-01",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "date_from"


async def test_missing_range_is_rejected(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.get(
        "/api/admin/analytics/orders-per-day", headers=cod_flow.admin_headers()
    )

    assert response.status_code == 422


async def test_analytics_endpoints_require_an_admin_session(cod_flow: CodFlowHarness) -> None:
    for path in ("orders-per-day", "landings", "fraud"):
        response = await cod_flow.client.get(
            f"/api/admin/analytics/{path}?date_from={_today()}&date_to={_today()}"
        )

        assert response.status_code == 401
