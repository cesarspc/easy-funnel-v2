"""Conversion components end to end (Requirements 3.27-3.31).

Drives the real ASGI application: an Administrator places components into slots
of a landing's rendered sequence, and the public landing payload carries them
back with the slot each one occupies. Covers what a merchant can actually do
wrong — an unknown type, missing content, a slot past the sequence — and the
two rules that protect the page: presentation is never configurable, and a
disabled component never reaches a visitor.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import CodFlowHarness

pytestmark = pytest.mark.e2e


async def _seed_three_banner_landing(cod_flow: CodFlowHarness):
    """A landing with 3 banners and a CTA after each: 6 rendered elements."""
    landing = await cod_flow.seed_landing()
    for index in range(3):
        await cod_flow.seed_banner(landing, order_index=index)
    await cod_flow.db.landing.update(
        where={"id": landing.landing_id},
        data={"ctaMode": "fixed_positions", "ctaPositions": [1, 2, 3]},
    )
    return landing


class TestPlacement:
    async def test_three_banners_and_three_ctas_offer_seven_slots(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)

        response = await cod_flow.client.get(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["blocks"] == []
        # 6 elements -> 7 placement slots, the merchant's "1-2" through "6-7"
        # plus the leading one.
        assert len(body["slots"]) == 7
        assert body["slots"][1].startswith("1-2")
        assert body["slots"][2].startswith("2-3")
        assert len(body["allowed_block_types"]) == 13

    async def test_places_components_in_two_slots_and_reports_them_in_render_order(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        headers = cod_flow.admin_headers()

        # Placed out of order on purpose: the API answers in render order.
        second = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={
                "block_type": "benefits",
                "slot_index": 2,
                "config": {"items": ["Envío a todo el país", "Revisas antes de pagar"]},
            },
            headers=headers,
        )
        first = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "cod_assurance", "slot_index": 1, "config": {}},
            headers=headers,
        )

        assert second.status_code == 201
        assert first.status_code == 201
        blocks = first.json()["blocks"]
        assert [(block["block_type"], block["slot_index"]) for block in blocks] == [
            ("cod_assurance", 1),
            ("benefits", 2),
        ]
        assert all(block["order_index"] == 0 for block in blocks)

    async def test_two_components_in_one_slot_stack_instead_of_colliding(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        headers = cod_flow.admin_headers()

        for _ in range(2):
            response = await cod_flow.client.post(
                f"/api/admin/landings/{landing.landing_id}/blocks",
                json={"block_type": "cod_assurance", "slot_index": 3, "config": {}},
                headers=headers,
            )
            assert response.status_code == 201

        blocks = response.json()["blocks"]
        assert [block["order_index"] for block in blocks] == [0, 1]

    async def test_moving_a_component_to_another_slot_keeps_one_row(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        headers = cod_flow.admin_headers()

        created = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "cod_assurance", "slot_index": 1, "config": {}},
            headers=headers,
        )
        block_id = created.json()["blocks"][0]["id"]

        moved = await cod_flow.client.patch(
            f"/api/admin/landings/{landing.landing_id}/blocks/{block_id}",
            json={"slot_index": 5},
            headers=headers,
        )

        assert moved.status_code == 200
        blocks = moved.json()["blocks"]
        assert len(blocks) == 1
        assert blocks[0]["slot_index"] == 5

    async def test_a_slot_past_the_sequence_is_rejected_with_its_field(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)

        response = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "cod_assurance", "slot_index": 99, "config": {}},
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "slot_index"

    async def test_unknown_component_type_is_rejected(self, cod_flow: CodFlowHarness) -> None:
        landing = await _seed_three_banner_landing(cod_flow)

        response = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "countdown_timer", "slot_index": 1, "config": {}},
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "block_type"

    async def test_missing_content_is_rejected_and_places_nothing(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        headers = cod_flow.admin_headers()

        response = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "benefits", "slot_index": 1, "config": {"items": []}},
            headers=headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "items"

        listed = await cod_flow.client.get(
            f"/api/admin/landings/{landing.landing_id}/blocks", headers=headers
        )
        assert listed.json()["blocks"] == []

    async def test_presentation_keys_are_dropped_rather_than_stored(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)

        response = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={
                "block_type": "guarantee",
                "slot_index": 1,
                "config": {
                    "title": "Garantía de 30 días",
                    "text": "Si no te sirve, lo devuelves.",
                    "days": 30,
                    "padding": "64px",
                    "background": "#ff00ff",
                },
            },
            headers=cod_flow.admin_headers(),
        )

        assert response.status_code == 201
        config = response.json()["blocks"][0]["config"]
        assert config == {
            "title": "Garantía de 30 días",
            "text": "Si no te sirve, lo devuelves.",
            "days": 30,
            "eyebrow": None,
            "benefits": [],
            "accent_color": None,
            # Presentation is fixed in the chrome, with two bounded exceptions
            # every type accepts: `accent_color` and `dark_mode`. An unset
            # accent means "inherit the form accent"; an unset dark mode stays
            # null so the public component follows the landing-level default.
            "dark_mode": None,
        }

    async def test_anonymous_callers_cannot_place_components(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)

        response = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "cod_assurance", "slot_index": 1, "config": {}},
        )

        assert response.status_code == 401

    async def test_removing_a_component_leaves_the_rest_in_place(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        headers = cod_flow.admin_headers()

        await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "cod_assurance", "slot_index": 1, "config": {}},
            headers=headers,
        )
        created = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={
                "block_type": "faq",
                "slot_index": 4,
                "config": {"items": [{"question": "¿Cuándo llega?", "answer": "1 a 3 días."}]},
            },
            headers=headers,
        )
        faq_id = next(
            block["id"] for block in created.json()["blocks"] if block["block_type"] == "faq"
        )

        removed = await cod_flow.client.delete(
            f"/api/admin/landings/{landing.landing_id}/blocks/{faq_id}", headers=headers
        )

        assert removed.status_code == 200
        assert [block["block_type"] for block in removed.json()["blocks"]] == ["cod_assurance"]


class TestPublicRendering:
    async def test_the_public_payload_carries_enabled_components_in_render_order(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        headers = cod_flow.admin_headers()

        await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={
                "block_type": "reviews",
                "slot_index": 4,
                "config": {
                    "items": [
                        {
                            "name": "Cliente de ejemplo",
                            "city": "Medellín",
                            "text": "Llegó en dos días y pagué al recibir.",
                            "rating": 5,
                        }
                    ]
                },
            },
            headers=headers,
        )
        await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={
                "block_type": "cod_assurance",
                "slot_index": 1,
                "config": {"note": "Cobertura nacional"},
            },
            headers=headers,
        )

        public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

        assert public.status_code == 200
        blocks = public.json()["blocks"]
        assert [(block["block_type"], block["slot_index"]) for block in blocks] == [
            ("cod_assurance", 1),
            ("reviews", 4),
        ]
        assert blocks[0]["config"]["note"] == "Cobertura nacional"

    async def test_a_disabled_component_is_absent_from_the_public_payload(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        headers = cod_flow.admin_headers()

        created = await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "cod_assurance", "slot_index": 1, "config": {}},
            headers=headers,
        )
        block_id = created.json()["blocks"][0]["id"]

        await cod_flow.client.patch(
            f"/api/admin/landings/{landing.landing_id}/blocks/{block_id}",
            json={"enabled": False},
            headers=headers,
        )

        public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")
        assert public.json()["blocks"] == []

        # Still visible to the Administrator, as a draft.
        listed = await cod_flow.client.get(
            f"/api/admin/landings/{landing.landing_id}/blocks", headers=headers
        )
        assert listed.json()["blocks"][0]["enabled"] is False

    async def test_a_landing_with_no_components_returns_an_empty_list(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)

        public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

        assert public.status_code == 200
        assert public.json()["blocks"] == []

    async def test_a_component_without_an_override_carries_no_accent_palette(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={"block_type": "cod_assurance", "slot_index": 1, "config": {}},
            headers=cod_flow.admin_headers(),
        )

        public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

        assert public.status_code == 200
        assert public.json()["blocks"][0]["accent_palette"] is None

    async def test_a_component_with_an_override_carries_its_derived_palette(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _seed_three_banner_landing(cod_flow)
        await cod_flow.client.post(
            f"/api/admin/landings/{landing.landing_id}/blocks",
            json={
                "block_type": "announcement_bar",
                "slot_index": 0,
                "config": {"text": "Envío gratis", "accent_color": "#ff6600"},
            },
            headers=cod_flow.admin_headers(),
        )

        public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

        assert public.status_code == 200
        block = public.json()["blocks"][0]
        assert block["config"]["accent_color"] == "#ff6600"
        palette = block["accent_palette"]
        assert palette is not None
        assert palette["accent"] == "#ff6600"
        assert palette["deep"] and palette["tint"] and palette["ink"]
