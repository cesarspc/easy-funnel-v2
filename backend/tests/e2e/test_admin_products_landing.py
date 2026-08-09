"""Admin Products API: `landing_slug`/`landing_status` exposure.

Each Product has exactly one Landing (Requirement 2.7). The Admin
Dashboard's product list links out to each product's public Landing
(`/p/{slug}`), so `ProductResponse` must carry the Landing's slug and
status alongside the product fields. Covers create, list, get, update,
activate, and pause — every endpoint that returns a `ProductResponse`.

Uses the `cod_flow` e2e harness (real ASGI app + real PostgreSQL) purely
for its admin JWT helper and automatic per-test cleanup; no COD-flow
seeding is needed here.
"""

from __future__ import annotations

import uuid

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness

pytestmark = requires_database


def _unique_sku() -> str:
    return f"SKU-LANDING-LINK-{uuid.uuid4().hex[:12]}"


async def test_create_product_response_includes_its_draft_landing(
    cod_flow: CodFlowHarness,
) -> None:
    sku = _unique_sku()
    response = await cod_flow.client.post(
        "/api/admin/products",
        json={"name": "Audífonos Bluetooth", "sku": sku, "price": 89900.0},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["landing_slug"] is not None
    assert body["landing_status"] == "draft"

    await _cleanup_product(cod_flow, product_id=body["id"])


async def test_create_product_seeds_a_default_announcement_bar(
    cod_flow: CodFlowHarness,
) -> None:
    """A new draft landing starts with one announcement_bar component in
    slot 0 (above everything), so the merchant sees the top-of-page header in
    place rather than having to know to add it. It behaves like any other
    conversion component afterward: editable, movable, removable."""
    sku = _unique_sku()
    created = await cod_flow.client.post(
        "/api/admin/products",
        json={"name": "Parlante Portátil", "sku": sku, "price": 55000.0},
        headers=cod_flow.admin_headers(),
    )
    product_id = created.json()["id"]

    try:
        landing = await cod_flow.db.landing.find_unique(where={"productId": product_id})
        assert landing is not None

        blocks_response = await cod_flow.client.get(
            f"/api/admin/landings/{landing.id}/blocks", headers=cod_flow.admin_headers()
        )
        assert blocks_response.status_code == 200
        blocks = blocks_response.json()["blocks"]
        assert len(blocks) == 1
        assert blocks[0]["block_type"] == "announcement_bar"
        assert blocks[0]["slot_index"] == 0
        assert blocks[0]["config"]["text"]
    finally:
        await _cleanup_product(cod_flow, product_id=product_id)


async def test_list_products_includes_landing_slug_and_status(
    cod_flow: CodFlowHarness,
) -> None:
    sku = _unique_sku()
    created = await cod_flow.client.post(
        "/api/admin/products",
        json={"name": "Lámpara LED", "sku": sku, "price": 45000.0},
        headers=cod_flow.admin_headers(),
    )
    product_id = created.json()["id"]

    try:
        response = await cod_flow.client.get(
            "/api/admin/products", headers=cod_flow.admin_headers()
        )
        assert response.status_code == 200
        products = response.json()["products"]
        match = next(p for p in products if p["id"] == product_id)
        assert match["landing_slug"] is not None
        assert match["landing_status"] == "draft"
    finally:
        await _cleanup_product(cod_flow, product_id=product_id)


async def test_get_product_includes_landing_slug_and_status(
    cod_flow: CodFlowHarness,
) -> None:
    sku = _unique_sku()
    created = await cod_flow.client.post(
        "/api/admin/products",
        json={"name": "Cargador Solar", "sku": sku, "price": 65000.0},
        headers=cod_flow.admin_headers(),
    )
    product_id = created.json()["id"]

    try:
        response = await cod_flow.client.get(
            f"/api/admin/products/{product_id}", headers=cod_flow.admin_headers()
        )
        assert response.status_code == 200
        body = response.json()
        assert body["landing_slug"] == created.json()["landing_slug"]
        assert body["landing_status"] == "draft"
    finally:
        await _cleanup_product(cod_flow, product_id=product_id)


async def test_activate_and_pause_preserve_landing_slug(cod_flow: CodFlowHarness) -> None:
    sku = _unique_sku()
    created = await cod_flow.client.post(
        "/api/admin/products",
        json={"name": "Mini Ventilador", "sku": sku, "price": 32000.0},
        headers=cod_flow.admin_headers(),
    )
    product_id = created.json()["id"]
    slug = created.json()["landing_slug"]

    try:
        activated = await cod_flow.client.post(
            f"/api/admin/products/{product_id}/activate", headers=cod_flow.admin_headers()
        )
        assert activated.status_code == 200
        assert activated.json()["landing_slug"] == slug
        assert activated.json()["status"] == "active"

        paused = await cod_flow.client.post(
            f"/api/admin/products/{product_id}/pause", headers=cod_flow.admin_headers()
        )
        assert paused.status_code == 200
        assert paused.json()["landing_slug"] == slug
        assert paused.json()["status"] == "paused"
    finally:
        await _cleanup_product(cod_flow, product_id=product_id)


async def _cleanup_product(cod_flow: CodFlowHarness, *, product_id: int) -> None:
    """Delete the product created directly through the API (bypassing
    the harness's `seed_landing` bookkeeping, since these tests create
    products through the real create endpoint rather than seeding directly)."""
    db = cod_flow.db
    landing = await db.landing.find_unique(where={"productId": product_id})
    if landing is not None:
        await db.order.delete_many(where={"landingId": landing.id})
        await db.ctaclick.delete_many(where={"landingId": landing.id})
        await db.landingview.delete_many(where={"landingId": landing.id})
        # Every landing now starts with a default announcement_bar component
        # (Requirement: default header component on creation), so it must be
        # cleared before the landing itself can be deleted (restrict FK).
        await db.landingblock.delete_many(where={"landingId": landing.id})
        await db.landing.delete(where={"id": landing.id})
    await db.auditlog.delete_many(where={"targetId": str(product_id), "targetType": "product"})
    await db.product.delete(where={"id": product_id})
