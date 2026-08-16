"""Admin Landings API tests (Requirements 3.1-3.11, 3.15-3.20, 4.6, 4.21, 8.3, 10.10).

Drives the real ASGI application against the real database, with the R2
client replaced by the in-process `FakeR2Client` the `cod_flow` harness
injects — so the multipart upload endpoint runs the genuine image pipeline
(decode, EXIF strip, variant generation, atomic persistence) without an
external object store.
"""

from __future__ import annotations

from app.main import app
from app.storage.dependencies import get_r2_client

from tests.conftest import requires_database
from tests.domains.images.conftest import make_image_bytes
from tests.e2e.conftest import CodFlowHarness
from tests.storage.fakes import FakeUnavailableR2Client

pytestmark = requires_database


def _upload_files(width: int = 1600, height: int = 900) -> dict:
    return {"file": ("banner.jpg", make_image_bytes(width, height), "image/jpeg")}


async def _upload(cod_flow: CodFlowHarness, landing_id: int, *, alt_text: str = "Banner de prueba"):
    return await cod_flow.client.post(
        f"/api/admin/landings/{landing_id}/banners",
        files=_upload_files(),
        data={"alt_text": alt_text},
        headers=cod_flow.admin_headers(),
    )


async def test_banner_upload_creates_banner_with_responsive_candidates(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await _upload(cod_flow, landing.landing_id, alt_text="  Audífonos en oferta  ")

    assert response.status_code == 201
    body = response.json()
    assert body["alt_text"] == "Audífonos en oferta"  # trimmed (Requirement 3.3)
    assert body["order_index"] == 0
    assert body["image_status"] == "complete"
    assert len(body["variants"]) > 0
    assert {variant["format"] for variant in body["variants"]} == {"jpeg", "webp"}
    for variant in body["variants"]:
        assert variant["height"] > 0
        # The advertised URL is the variant's own R2 object key, so the public
        # host can serve it without a path-rewrite rule.
        assert variant["url"].startswith("https://test-images.example.com/variants/")

    # Every object the payload advertises was really uploaded (Requirement 4.11).
    stored_variants = await cod_flow.db.imagevariant.find_many(
        where={"imageAssetId": body["image_asset_id"]}
    )
    assert stored_variants
    for variant in stored_variants:
        assert variant.objectKey in cod_flow.r2.objects


async def test_uploaded_banner_is_visible_on_the_public_landing_after_publish(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    await _upload(cod_flow, landing.landing_id)

    publish = await cod_flow.client.post(
        f"/api/admin/landings/{landing.landing_id}/publish",
        headers=cod_flow.admin_headers(),
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"

    public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")
    assert public.status_code == 200
    (banner,) = public.json()["banners"]
    assert len(banner["variants"]) > 0
    assert public.json()["cta_positions"] == [1]


async def test_publish_is_rejected_without_banners_and_leaves_the_landing_in_draft(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.post(
        f"/api/admin/landings/{landing.landing_id}/publish",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "banners"
    stored = await cod_flow.db.landing.find_unique(where={"id": landing.landing_id})
    assert stored is not None
    assert stored.status == "draft"


async def test_unpublish_makes_the_public_landing_unavailable(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    await _upload(cod_flow, landing.landing_id)
    await cod_flow.client.post(
        f"/api/admin/landings/{landing.landing_id}/publish",
        headers=cod_flow.admin_headers(),
    )

    response = await cod_flow.client.post(
        f"/api/admin/landings/{landing.landing_id}/unpublish",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")
    assert public.status_code == 404


async def test_upload_rejects_an_undersized_image_without_creating_a_banner(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.post(
        f"/api/admin/landings/{landing.landing_id}/banners",
        files={"file": ("tiny.jpg", make_image_bytes(200, 200), "image/jpeg")},
        data={"alt_text": "Muy pequeño"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "file"
    assert await cod_flow.db.banner.count(where={"landingId": landing.landing_id}) == 0


async def test_upload_rejects_blank_alt_text(cod_flow: CodFlowHarness) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await _upload(cod_flow, landing.landing_id, alt_text="   ")

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "alt_text"
    assert await cod_flow.db.banner.count(where={"landingId": landing.landing_id}) == 0


async def test_upload_returns_a_non_sensitive_503_during_an_upload_outage(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    app.dependency_overrides[get_r2_client] = FakeUnavailableR2Client
    try:
        response = await _upload(cod_flow, landing.landing_id)
    finally:
        app.dependency_overrides[get_r2_client] = lambda: cod_flow.r2

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Image upload is temporarily unavailable. Please try again."
    )
    assert await cod_flow.db.banner.count(where={"landingId": landing.landing_id}) == 0


async def test_banner_patch_updates_alt_text(cod_flow: CodFlowHarness) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    banner_id = (await _upload(cod_flow, landing.landing_id)).json()["id"]

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}/banners/{banner_id}",
        json={"alt_text": "Texto corregido"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    (banner,) = response.json()["banners"]
    assert banner["alt_text"] == "Texto corregido"


async def test_banner_patch_moves_a_banner_and_keeps_contiguous_order(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    first = (await _upload(cod_flow, landing.landing_id, alt_text="Uno")).json()["id"]
    second = (await _upload(cod_flow, landing.landing_id, alt_text="Dos")).json()["id"]
    third = (await _upload(cod_flow, landing.landing_id, alt_text="Tres")).json()["id"]

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}/banners/{third}",
        json={"order_index": 0},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    banners = response.json()["banners"]
    assert [banner["id"] for banner in banners] == [third, first, second]
    assert [banner["order_index"] for banner in banners] == [0, 1, 2]


async def test_banner_order_endpoint_applies_an_explicit_sequence(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    first = (await _upload(cod_flow, landing.landing_id, alt_text="Uno")).json()["id"]
    second = (await _upload(cod_flow, landing.landing_id, alt_text="Dos")).json()["id"]

    response = await cod_flow.client.put(
        f"/api/admin/landings/{landing.landing_id}/banners/order",
        json={"banner_ids": [second, first]},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    banners = response.json()["banners"]
    assert [banner["id"] for banner in banners] == [second, first]
    assert [banner["order_index"] for banner in banners] == [0, 1]


async def test_banner_order_endpoint_rejects_an_incomplete_sequence(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    first = (await _upload(cod_flow, landing.landing_id, alt_text="Uno")).json()["id"]
    await _upload(cod_flow, landing.landing_id, alt_text="Dos")

    response = await cod_flow.client.put(
        f"/api/admin/landings/{landing.landing_id}/banners/order",
        json={"banner_ids": [first]},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "banner_ids"


async def test_banner_delete_closes_the_position_gap(cod_flow: CodFlowHarness) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    first = (await _upload(cod_flow, landing.landing_id, alt_text="Uno")).json()["id"]
    second = (await _upload(cod_flow, landing.landing_id, alt_text="Dos")).json()["id"]
    third = (await _upload(cod_flow, landing.landing_id, alt_text="Tres")).json()["id"]

    response = await cod_flow.client.delete(
        f"/api/admin/landings/{landing.landing_id}/banners/{first}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    banners = response.json()["banners"]
    assert [banner["id"] for banner in banners] == [second, third]
    assert [banner["order_index"] for banner in banners] == [0, 1]


async def test_landing_patch_updates_slug_cta_and_presentation(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    await _upload(cod_flow, landing.landing_id)
    await _upload(cod_flow, landing.landing_id)
    new_slug = f"{landing.slug}-editada"

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={
            "slug": new_slug,
            "cta_mode": "fixed_positions",
            "cta_positions": [2, 1],
            "form_presentation": "modal",
            "cta_band_style": "solid",
        },
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == new_slug
    assert body["cta_mode"] == "fixed_positions"
    assert body["cta_positions"] == [1, 2]
    assert body["cta_interval"] is None
    assert body["form_presentation"] == "modal"
    assert body["cta_band_style"] == "solid"
    assert body["resolved_cta_positions"] == [1, 2]


async def test_landing_defaults_to_a_gradient_cta_band_style(
    cod_flow: CodFlowHarness,
) -> None:
    """Landings created before the setting existed keep rendering a gradient."""
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.get(
        f"/api/admin/landings/{landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    assert response.json()["cta_band_style"] == "gradient"


async def test_landing_defaults_to_no_form_accent_color(cod_flow: CodFlowHarness) -> None:
    """A landing created before the field existed follows accent_color."""
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.get(
        f"/api/admin/landings/{landing.landing_id}",
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    assert response.json()["form_accent_color"] is None


async def test_landing_patch_sets_and_clears_the_blocks_accent_color(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    set_response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"blocks_accent_color": "#7C3AED"},
        headers=cod_flow.admin_headers(),
    )
    assert set_response.status_code == 200
    assert set_response.json()["blocks_accent_color"] == "#7c3aed"
    assert set_response.json()["form_accent_color"] is None

    clear_response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"blocks_accent_color": ""},
        headers=cod_flow.admin_headers(),
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["blocks_accent_color"] is None

    # JSON null is an explicit clear too; omission remains a no-op PATCH.
    await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"blocks_accent_color": "#7C3AED"},
        headers=cod_flow.admin_headers(),
    )
    null_clear_response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"blocks_accent_color": None},
        headers=cod_flow.admin_headers(),
    )
    assert null_clear_response.status_code == 200
    assert null_clear_response.json()["blocks_accent_color"] is None

    rejected = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"blocks_accent_color": "purple"},
        headers=cod_flow.admin_headers(),
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["field"] == "blocks_accent_color"


async def test_landing_patch_sets_and_clears_the_form_accent_color(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    set_response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"form_accent_color": "#E11D48"},
        headers=cod_flow.admin_headers(),
    )
    assert set_response.status_code == 200
    assert set_response.json()["form_accent_color"] == "#e11d48"
    # The CTA/page accent is untouched by setting the form's own accent.
    assert set_response.json()["accent_color"] == "#1a7a4c"

    clear_response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"form_accent_color": ""},
        headers=cod_flow.admin_headers(),
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["form_accent_color"] is None

    await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"form_accent_color": "#E11D48"},
        headers=cod_flow.admin_headers(),
    )
    null_clear_response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"form_accent_color": None},
        headers=cod_flow.admin_headers(),
    )
    assert null_clear_response.status_code == 200
    assert null_clear_response.json()["form_accent_color"] is None


async def test_landing_patch_rejects_a_malformed_form_accent_color_without_mutating(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"form_accent_color": "red; background: url(evil)"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "form_accent_color"
    stored = await cod_flow.db.landing.find_unique(where={"id": landing.landing_id})
    assert stored is not None
    assert stored.formAccentColor is None


async def test_landing_patch_stores_a_per_cta_position_text_override(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"cta_text_overrides": {"2": "Lo quiero ahora"}},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 200
    assert response.json()["cta_text_overrides"] == {"2": "Lo quiero ahora"}


async def test_landing_patch_rejects_a_blank_cta_text_override_without_mutating(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"cta_text_overrides": {"2": "   "}},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "cta_text_overrides"
    stored = await cod_flow.db.landing.find_unique(where={"id": landing.landing_id})
    assert stored is not None
    assert stored.ctaTextOverrides == {}


async def test_landing_patch_rejects_an_unsupported_cta_band_style_without_mutating(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"cta_band_style": "fade", "form_presentation": "modal"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "cta_band_style"
    stored = await cod_flow.db.landing.find_unique(where={"id": landing.landing_id})
    assert stored is not None
    assert stored.ctaBandStyle == "gradient"
    # Validation happens before any write, so the co-submitted valid field is
    # not applied either.
    assert stored.formPresentation == "inline"


async def test_landing_patch_rejects_a_malformed_slug_without_mutating(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"slug": "Mala Slug", "form_presentation": "modal"},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "slug"
    stored = await cod_flow.db.landing.find_unique(where={"id": landing.landing_id})
    assert stored is not None
    assert stored.slug == landing.slug
    assert stored.formPresentation == "inline"


async def test_landing_patch_rejects_a_slug_already_taken(cod_flow: CodFlowHarness) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    other = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"slug": other.slug},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 409


async def test_landing_patch_rejects_an_out_of_range_cta_interval(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        json={"cta_mode": "every_n", "cta_interval": 99},
        headers=cod_flow.admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "cta_interval"
    stored = await cod_flow.db.landing.find_unique(where={"id": landing.landing_id})
    assert stored is not None
    assert stored.ctaMode == "after_every"


async def test_landing_list_and_detail_expose_the_management_payload(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    await _upload(cod_flow, landing.landing_id)

    listed = await cod_flow.client.get("/api/admin/landings", headers=cod_flow.admin_headers())
    assert listed.status_code == 200
    match = next(item for item in listed.json()["landings"] if item["id"] == landing.landing_id)
    assert match["slug"] == landing.slug
    assert match["status"] == "draft"
    assert match["banner_count"] == 1
    assert match["product_status"] == "active"

    detail = await cod_flow.client.get(
        f"/api/admin/landings/{landing.landing_id}", headers=cod_flow.admin_headers()
    )
    assert detail.status_code == 200
    assert len(detail.json()["banners"]) == 1


async def test_landing_endpoints_require_an_admin_session(cod_flow: CodFlowHarness) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")

    assert (await cod_flow.client.get("/api/admin/landings")).status_code == 401
    assert (
        await cod_flow.client.get(f"/api/admin/landings/{landing.landing_id}")
    ).status_code == 401
    anonymous_upload = await cod_flow.client.post(
        f"/api/admin/landings/{landing.landing_id}/banners",
        files=_upload_files(),
        data={"alt_text": "Sin sesión"},
    )
    assert anonymous_upload.status_code == 401
    assert await cod_flow.db.banner.count(where={"landingId": landing.landing_id}) == 0


async def test_unknown_landing_returns_404(cod_flow: CodFlowHarness) -> None:
    response = await cod_flow.client.get(
        "/api/admin/landings/99999999", headers=cod_flow.admin_headers()
    )
    assert response.status_code == 404


async def test_banner_mutations_record_audit_rows(cod_flow: CodFlowHarness) -> None:
    landing = await cod_flow.seed_landing(landing_status="draft")
    banner_id = (await _upload(cod_flow, landing.landing_id)).json()["id"]

    await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}/banners/{banner_id}",
        json={"order_index": 0},
        headers=cod_flow.admin_headers(),
    )
    await cod_flow.client.post(
        f"/api/admin/landings/{landing.landing_id}/publish",
        headers=cod_flow.admin_headers(),
    )

    banner_actions = {
        row.action
        for row in await cod_flow.db.auditlog.find_many(
            where={"targetType": "banner", "targetId": str(banner_id)}
        )
    }
    assert {"banner.upload", "banner.reorder"} <= banner_actions
    landing_actions = {
        row.action
        for row in await cod_flow.db.auditlog.find_many(
            where={"targetType": "landing", "targetId": str(landing.landing_id)}
        )
    }
    assert "landing.publish" in landing_actions
