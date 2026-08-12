"""End-to-end: save a landing's configuration as a template, apply it to another.

Covers the flow a merchant actually performs — configure one funnel, save it,
open a different product's landing, apply it — plus the three refusals that make
the feature safe to use on a page about to be published:

- a banner count that does not match is refused, naming both counts
- a name already in use is refused until the merchant confirms an overwrite
- an unknown template is a 404, not a partial write

and the two guarantees about scope: applying a template replaces the target's
conversion components wholesale, and never touches its banners, slug, or
publication status.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness

pytestmark = requires_database


def template_name() -> str:
    """A unique name per test, so a leaked row can never collide."""
    return f"E2E plantilla {uuid.uuid4().hex[:8]}"


async def configure_source_landing(cod_flow: CodFlowHarness, landing_id: int) -> dict[str, object]:
    """Give the source landing a distinctive, fully-populated configuration.

    Requires the landing to already have **at least two banners**: it sets
    `cta_positions: [1, 2]`, and fixed positions are validated against the
    current banner sequence.
    """
    response = await cod_flow.client.patch(
        f"/api/admin/landings/{landing_id}",
        json={
            "cta_mode": "fixed_positions",
            "cta_positions": [1, 2],
            "form_presentation": "modal",
            "cta_band_style": "solid",
            "accent_color": "#2563eb",
            "form_accent_color": "#e11d48",
            "cta_text": "Lo quiero ahora",
            "cta_animation": "shake",
            "cta_text_overrides": {"2": "Pídelo hoy"},
            "blocks_dark_mode": True,
            "offer_count": 2,
            "offers": [
                {
                    "quantity": 1,
                    "label": "1 unidad",
                    "sublabel": "Prueba",
                    "discount_percent": None,
                    "compare_at_price": 79900,
                },
                {
                    "quantity": 2,
                    "label": "2 unidades",
                    "sublabel": "Ahorra",
                    "discount_percent": 15,
                    "compare_at_price": None,
                },
            ],
        },
        headers=cod_flow.admin_headers(),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def add_block(
    cod_flow: CodFlowHarness,
    landing_id: int,
    *,
    block_type: str,
    slot_index: int,
    config: dict[str, object],
) -> None:
    response = await cod_flow.client.post(
        f"/api/admin/landings/{landing_id}/blocks",
        json={"block_type": block_type, "slot_index": slot_index, "config": config},
        headers=cod_flow.admin_headers(),
    )
    assert response.status_code == 201, response.text


async def save_template(
    cod_flow: CodFlowHarness, landing_id: int, name: str, *, overwrite: bool = False
):
    return await cod_flow.client.post(
        "/api/admin/landing-templates",
        json={"landing_id": landing_id, "name": name, "overwrite": overwrite},
        headers=cod_flow.admin_headers(),
    )


class TestSaveTemplate:
    async def test_saves_the_configuration_and_reports_its_preconditions(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await cod_flow.seed_landing(landing_status="draft")
        await cod_flow.seed_banner(landing, order_index=0)
        await cod_flow.seed_banner(landing, order_index=1)
        await configure_source_landing(cod_flow, landing.landing_id)
        await add_block(
            cod_flow,
            landing.landing_id,
            block_type="cod_assurance",
            slot_index=1,
            config={"note": "Cobertura nacional"},
        )

        response = await save_template(cod_flow, landing.landing_id, template_name())

        assert response.status_code == 201, response.text
        body = response.json()
        cod_flow.track_template(body["id"])
        assert body["banner_count"] == 2
        assert body["block_count"] == 1

    async def test_a_blank_name_is_a_field_error(self, cod_flow: CodFlowHarness) -> None:
        landing = await cod_flow.seed_landing()

        response = await save_template(cod_flow, landing.landing_id, "   ")

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "name"

    async def test_an_unknown_landing_is_a_404(self, cod_flow: CodFlowHarness) -> None:
        response = await save_template(cod_flow, 99_999_999, template_name())
        assert response.status_code == 404

    async def test_a_repeated_name_is_refused_until_overwrite_is_confirmed(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await cod_flow.seed_landing()
        await cod_flow.seed_banner(landing, order_index=0)
        name = template_name()

        first = await save_template(cod_flow, landing.landing_id, name)
        assert first.status_code == 201, first.text
        template_id = cod_flow.track_template(first.json()["id"])

        conflict = await save_template(cod_flow, landing.landing_id, name)
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["field"] == "name"

        confirmed = await save_template(cod_flow, landing.landing_id, name, overwrite=True)
        assert confirmed.status_code == 201, confirmed.text
        # Overwriting updates in place rather than adding a second entry.
        assert confirmed.json()["id"] == template_id

    async def test_anonymous_callers_cannot_save(self, cod_flow: CodFlowHarness) -> None:
        landing = await cod_flow.seed_landing()
        response = await cod_flow.client.post(
            "/api/admin/landing-templates",
            json={"landing_id": landing.landing_id, "name": template_name()},
        )
        assert response.status_code == 401


class TestLoadTemplate:
    async def test_applies_every_configured_field_to_another_landing(
        self, cod_flow: CodFlowHarness
    ) -> None:
        source = await cod_flow.seed_landing(landing_status="draft")
        await cod_flow.seed_banner(source, order_index=0)
        await cod_flow.seed_banner(source, order_index=1)
        await configure_source_landing(cod_flow, source.landing_id)
        await add_block(
            cod_flow,
            source.landing_id,
            block_type="cod_assurance",
            slot_index=1,
            config={"note": "Cobertura nacional"},
        )
        await add_block(
            cod_flow,
            source.landing_id,
            block_type="faq",
            slot_index=2,
            config={
                "title": "Dudas",
                "items": [{"question": "¿Cuándo llega?", "answer": "1-3 días"}],
            },
        )

        saved = await save_template(cod_flow, source.landing_id, template_name())
        assert saved.status_code == 201, saved.text
        template_id = cod_flow.track_template(saved.json()["id"])

        target = await cod_flow.seed_landing(landing_status="draft")
        await cod_flow.seed_banner(target, order_index=0)
        await cod_flow.seed_banner(target, order_index=1)

        response = await cod_flow.client.post(
            f"/api/admin/landings/{target.landing_id}/load-template",
            json={"template_id": template_id},
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["cta_mode"] == "fixed_positions"
        assert body["cta_positions"] == [1, 2]
        assert body["form_presentation"] == "modal"
        assert body["cta_band_style"] == "solid"
        assert body["accent_color"] == "#2563eb"
        assert body["form_accent_color"] == "#e11d48"
        assert body["cta_text"] == "Lo quiero ahora"
        assert body["cta_animation"] == "shake"
        assert body["cta_text_overrides"] == {"2": "Pídelo hoy"}
        assert body["blocks_dark_mode"] is True
        assert body["offer_count"] == 2
        assert [offer["quantity"] for offer in body["offers"]] == [1, 2]
        assert body["offers"][1]["discount_percent"] == 15

        blocks = await cod_flow.client.get(
            f"/api/admin/landings/{target.landing_id}/blocks",
            headers=cod_flow.admin_headers(),
        )
        assert blocks.status_code == 200, blocks.text
        placed = blocks.json()["blocks"]
        assert [block["block_type"] for block in placed] == ["cod_assurance", "faq"]
        assert [block["slot_index"] for block in placed] == [1, 2]

    async def test_loading_replaces_the_targets_own_components(
        self, cod_flow: CodFlowHarness
    ) -> None:
        """A merchant applying a template wants that template's page, not their
        old components interleaved into it."""
        source = await cod_flow.seed_landing()
        await cod_flow.seed_banner(source, order_index=0)
        await add_block(
            cod_flow,
            source.landing_id,
            block_type="cod_assurance",
            slot_index=1,
            config={"note": "De la plantilla"},
        )
        saved = await save_template(cod_flow, source.landing_id, template_name())
        template_id = cod_flow.track_template(saved.json()["id"])

        target = await cod_flow.seed_landing()
        await cod_flow.seed_banner(target, order_index=0)
        await add_block(
            cod_flow,
            target.landing_id,
            block_type="guarantee",
            slot_index=1,
            config={"title": "Garantía previa", "text": "Debe desaparecer"},
        )

        response = await cod_flow.client.post(
            f"/api/admin/landings/{target.landing_id}/load-template",
            json={"template_id": template_id},
            headers=cod_flow.admin_headers(),
        )
        assert response.status_code == 200, response.text

        blocks = await cod_flow.client.get(
            f"/api/admin/landings/{target.landing_id}/blocks",
            headers=cod_flow.admin_headers(),
        )
        placed = blocks.json()["blocks"]
        assert [block["block_type"] for block in placed] == ["cod_assurance"]
        assert placed[0]["config"]["note"] == "De la plantilla"

    async def test_never_touches_banners_slug_or_publication_status(
        self, cod_flow: CodFlowHarness
    ) -> None:
        source = await cod_flow.seed_landing(landing_status="draft")
        await cod_flow.seed_banner(source, order_index=0)
        saved = await save_template(cod_flow, source.landing_id, template_name())
        template_id = cod_flow.track_template(saved.json()["id"])

        target = await cod_flow.seed_landing(landing_status="published")
        await cod_flow.seed_banner(target, order_index=0)
        before = await cod_flow.client.get(
            f"/api/admin/landings/{target.landing_id}", headers=cod_flow.admin_headers()
        )
        original = before.json()

        response = await cod_flow.client.post(
            f"/api/admin/landings/{target.landing_id}/load-template",
            json={"template_id": template_id},
            headers=cod_flow.admin_headers(),
        )
        assert response.status_code == 200, response.text
        after = response.json()

        assert after["slug"] == original["slug"]
        assert after["status"] == original["status"] == "published"
        assert after["product_id"] == original["product_id"]
        assert [banner["id"] for banner in after["banners"]] == [
            banner["id"] for banner in original["banners"]
        ]

    async def test_an_unknown_template_is_a_404(self, cod_flow: CodFlowHarness) -> None:
        landing = await cod_flow.seed_landing()
        response = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/load-template",
            json={"template_id": 99_999_999},
            headers=cod_flow.admin_headers(),
        )
        assert response.status_code == 404

    async def test_anonymous_callers_cannot_load(self, cod_flow: CodFlowHarness) -> None:
        landing = await cod_flow.seed_landing()
        response = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/load-template",
            json={"template_id": 1},
        )
        assert response.status_code == 401


class TestBannerCountRefusal:
    @pytest.mark.parametrize("target_banners", [0, 1, 3])
    async def test_a_different_banner_count_is_refused(
        self, cod_flow: CodFlowHarness, target_banners: int
    ) -> None:
        source = await cod_flow.seed_landing()
        await cod_flow.seed_banner(source, order_index=0)
        await cod_flow.seed_banner(source, order_index=1)
        saved = await save_template(cod_flow, source.landing_id, template_name())
        template_id = cod_flow.track_template(saved.json()["id"])

        target = await cod_flow.seed_landing()
        for index in range(target_banners):
            await cod_flow.seed_banner(target, order_index=index)

        response = await cod_flow.client.post(
            f"/api/admin/landings/{target.landing_id}/load-template",
            json={"template_id": template_id},
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["field"] == "banner_count"
        # Both numbers, so the merchant knows whether to add or remove.
        assert "2" in detail["message"]
        assert str(target_banners) in detail["message"]

    async def test_a_refused_load_leaves_the_target_untouched(
        self, cod_flow: CodFlowHarness
    ) -> None:
        source = await cod_flow.seed_landing()
        await cod_flow.seed_banner(source, order_index=0)
        await cod_flow.seed_banner(source, order_index=1)
        await configure_source_landing(cod_flow, source.landing_id)
        saved = await save_template(cod_flow, source.landing_id, template_name())
        template_id = cod_flow.track_template(saved.json()["id"])

        # One banner, so the template cannot apply.
        target = await cod_flow.seed_landing()
        await cod_flow.seed_banner(target, order_index=0)
        await add_block(
            cod_flow,
            target.landing_id,
            block_type="guarantee",
            slot_index=1,
            config={"title": "Intacta", "text": "No debe cambiar"},
        )
        before = (
            await cod_flow.client.get(
                f"/api/admin/landings/{target.landing_id}", headers=cod_flow.admin_headers()
            )
        ).json()

        refused = await cod_flow.client.post(
            f"/api/admin/landings/{target.landing_id}/load-template",
            json={"template_id": template_id},
            headers=cod_flow.admin_headers(),
        )
        assert refused.status_code == 422

        after = (
            await cod_flow.client.get(
                f"/api/admin/landings/{target.landing_id}", headers=cod_flow.admin_headers()
            )
        ).json()
        assert after["cta_mode"] == before["cta_mode"]
        assert after["accent_color"] == before["accent_color"]
        assert after["form_presentation"] == before["form_presentation"]

        blocks = await cod_flow.client.get(
            f"/api/admin/landings/{target.landing_id}/blocks",
            headers=cod_flow.admin_headers(),
        )
        placed = blocks.json()["blocks"]
        assert [block["block_type"] for block in placed] == ["guarantee"]

    async def test_a_template_with_no_banners_applies_only_to_a_landing_with_none(
        self, cod_flow: CodFlowHarness
    ) -> None:
        source = await cod_flow.seed_landing(landing_status="draft")
        saved = await save_template(cod_flow, source.landing_id, template_name())
        assert saved.status_code == 201, saved.text
        body = saved.json()
        template_id = cod_flow.track_template(body["id"])
        assert body["banner_count"] == 0

        target = await cod_flow.seed_landing(landing_status="draft")
        response = await cod_flow.client.post(
            f"/api/admin/landings/{target.landing_id}/load-template",
            json={"template_id": template_id},
            headers=cod_flow.admin_headers(),
        )
        assert response.status_code == 200, response.text


class TestListAndDelete:
    async def test_a_saved_template_appears_in_the_list(self, cod_flow: CodFlowHarness) -> None:
        landing = await cod_flow.seed_landing()
        await cod_flow.seed_banner(landing, order_index=0)
        name = template_name()
        saved = await save_template(cod_flow, landing.landing_id, name)
        template_id = cod_flow.track_template(saved.json()["id"])

        response = await cod_flow.client.get(
            "/api/admin/landing-templates", headers=cod_flow.admin_headers()
        )

        assert response.status_code == 200, response.text
        listed = {item["id"]: item for item in response.json()["templates"]}
        assert template_id in listed
        assert listed[template_id]["name"] == name
        assert listed[template_id]["banner_count"] == 1

    async def test_deleting_a_template_removes_it_from_the_list(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await cod_flow.seed_landing()
        saved = await save_template(cod_flow, landing.landing_id, template_name())
        template_id = cod_flow.track_template(saved.json()["id"])

        response = await cod_flow.client.delete(
            f"/api/admin/landing-templates/{template_id}",
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 200, response.text
        assert all(item["id"] != template_id for item in response.json()["templates"])

    async def test_deleting_an_unknown_template_is_a_404(self, cod_flow: CodFlowHarness) -> None:
        response = await cod_flow.client.delete(
            "/api/admin/landing-templates/99999999", headers=cod_flow.admin_headers()
        )
        assert response.status_code == 404

    async def test_anonymous_callers_cannot_list(self, cod_flow: CodFlowHarness) -> None:
        response = await cod_flow.client.get("/api/admin/landing-templates")
        assert response.status_code == 401

    async def test_deleting_a_template_leaves_landings_configured_from_it_alone(
        self, cod_flow: CodFlowHarness
    ) -> None:
        source = await cod_flow.seed_landing()
        await cod_flow.seed_banner(source, order_index=0)
        await cod_flow.seed_banner(source, order_index=1)
        await configure_source_landing(cod_flow, source.landing_id)
        saved = await save_template(cod_flow, source.landing_id, template_name())
        template_id = cod_flow.track_template(saved.json()["id"])

        target = await cod_flow.seed_landing()
        await cod_flow.seed_banner(target, order_index=0)
        await cod_flow.seed_banner(target, order_index=1)
        loaded = await cod_flow.client.post(
            f"/api/admin/landings/{target.landing_id}/load-template",
            json={"template_id": template_id},
            headers=cod_flow.admin_headers(),
        )
        assert loaded.status_code == 200, loaded.text

        deleted = await cod_flow.client.delete(
            f"/api/admin/landing-templates/{template_id}",
            headers=cod_flow.admin_headers(),
        )
        assert deleted.status_code == 200

        after = await cod_flow.client.get(
            f"/api/admin/landings/{target.landing_id}", headers=cod_flow.admin_headers()
        )
        assert after.status_code == 200
        assert after.json()["accent_color"] == "#2563eb"
