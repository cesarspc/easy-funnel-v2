"""End-to-end tests for per-landing offers, accent color, and order pricing.

Drives the real ASGI application: an Administrator configures how many quantity
offers the COD form shows, the copy for each, a discount on the multi-unit
offers and a reference price on the single-unit one, plus the landing's accent
color — then a buyer submits an order against that configuration.

The assertions concentrate on the two places this feature can do real damage:

- **Money.** A discounted offer has to reduce the total the buyer is quoted, and
  the order has to *record* that total. Editing the discount afterwards must not
  change what an existing order was owed, because a courier is collecting cash
  against it.
- **Reachability.** A quantity the landing does not offer must be rejected rather
  than priced at some default, so a crafted request cannot buy at a price the
  merchant never configured.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import CodFlowHarness

pytestmark = pytest.mark.e2e


def _offer(quantity: int, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "quantity": quantity,
        "label": f"{quantity} unidades",
        "sublabel": "",
        "discount_percent": None,
        "compare_at_price": None,
    }
    base.update(overrides)
    return base


async def _published_landing(cod_flow: CodFlowHarness):
    """A published landing with one banner, ready to serve publicly."""
    landing = await cod_flow.seed_landing()
    await cod_flow.seed_banner(landing, order_index=0)
    return landing


async def _configure(cod_flow: CodFlowHarness, landing, payload: dict[str, object]):
    return await cod_flow.client.patch(
        f"/api/admin/landings/{landing.landing_id}",
        headers=cod_flow.admin_headers(),
        json=payload,
    )


async def _submit_order(cod_flow: CodFlowHarness, landing, *, quantity: int, phone: str):
    return await cod_flow.client.post(
        "/api/public/orders",
        json={
            "landing_slug": landing.slug,
            "full_name": "Camila Restrepo",
            "phone": phone,
            "department": "Antioquia",
            "city": "Medellin",
            "address": "Calle 10 # 43-25 Apto 302",
            "quantity": quantity,
        },
    )


class TestOfferConfiguration:
    async def test_a_new_landing_offers_three_quantities_with_the_shipped_copy(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)

        response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

        assert response.status_code == 200
        offers = response.json()["offers"]
        assert [offer["quantity"] for offer in offers] == [1, 2, 3]
        assert [offer["label"] for offer in offers] == [
            "1 unidad",
            "2 unidades",
            "3 unidades",
        ]
        # Nothing is discounted or annotated until the merchant says so.
        assert all(offer["discount_percent"] == 0 for offer in offers)
        assert all(offer["sublabel"] is None for offer in offers)

    async def test_reducing_the_offer_count_shortens_the_public_list(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)

        response = await _configure(cod_flow, landing, {"offer_count": 1})
        assert response.status_code == 200
        assert response.json()["offer_count"] == 1

        public = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")
        assert [offer["quantity"] for offer in public.json()["offers"]] == [1]

    async def test_merchant_copy_survives_a_change_of_offer_count(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)
        await _configure(
            cod_flow,
            landing,
            {
                "offer_count": 3,
                "offers": [
                    _offer(1, label="Solo una"),
                    _offer(2, label="Llévate dos"),
                    _offer(3, label="Pack de tres"),
                ],
            },
        )

        # Dropping to two offers must not discard the wording for 1 and 2.
        response = await _configure(cod_flow, landing, {"offer_count": 2})

        assert response.status_code == 200
        assert [offer["label"] for offer in response.json()["offers"]] == [
            "Solo una",
            "Llévate dos",
        ]

    async def test_blank_subtext_turns_the_second_line_off(self, cod_flow: CodFlowHarness) -> None:
        landing = await _published_landing(cod_flow)

        response = await _configure(
            cod_flow,
            landing,
            {
                "offer_count": 2,
                "offers": [
                    _offer(1, sublabel=""),
                    _offer(2, sublabel="Ahorra en pedidos grandes"),
                ],
            },
        )

        assert response.status_code == 200
        offers = response.json()["offers"]
        assert offers[0]["sublabel"] is None
        assert offers[1]["sublabel"] == "Ahorra en pedidos grandes"

    async def test_a_discount_on_the_single_unit_offer_is_a_field_error(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)

        response = await _configure(
            cod_flow,
            landing,
            {"offer_count": 1, "offers": [_offer(1, discount_percent=20)]},
        )

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "offers"

    async def test_a_reference_price_on_a_multi_unit_offer_is_a_field_error(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)

        response = await _configure(
            cod_flow,
            landing,
            {
                "offer_count": 2,
                "offers": [_offer(1), _offer(2, compare_at_price=1000)],
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "offers"

    @pytest.mark.parametrize("count", [0, 4])
    async def test_an_unsupported_offer_count_is_a_field_error(
        self, cod_flow: CodFlowHarness, count: int
    ) -> None:
        landing = await _published_landing(cod_flow)

        response = await _configure(cod_flow, landing, {"offer_count": count})

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "offer_count"

    async def test_a_rejected_offer_list_leaves_the_stored_configuration_intact(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)
        await _configure(
            cod_flow, landing, {"offer_count": 2, "offers": [_offer(1, label="Buena"), _offer(2)]}
        )

        rejected = await _configure(
            cod_flow,
            landing,
            {"offer_count": 2, "offers": [_offer(1, label=""), _offer(2)]},
        )
        assert rejected.status_code == 422

        current = await cod_flow.client.get(
            f"/api/admin/landings/{landing.landing_id}", headers=cod_flow.admin_headers()
        )
        assert current.json()["offers"][0]["label"] == "Buena"


class TestAccentColor:
    async def test_the_public_payload_carries_the_accent_and_its_derived_shades(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)
        await _configure(cod_flow, landing, {"accent_color": "#2563EB"})

        response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

        assert response.status_code == 200
        body = response.json()
        # Stored and served canonically lowercase, matching the database check.
        assert body["accent_color"] == "#2563eb"
        palette = body["accent_palette"]
        assert palette["accent"] == "#2563eb"
        # Every shade is a usable CSS color the page can apply without parsing.
        for key in ("accent", "deep", "tint", "ink"):
            assert palette[key].startswith("#")
            assert len(palette[key]) == 7

    async def test_shorthand_hex_is_accepted_and_expanded(self, cod_flow: CodFlowHarness) -> None:
        landing = await _published_landing(cod_flow)

        response = await _configure(cod_flow, landing, {"accent_color": "#abc"})

        assert response.status_code == 200
        assert response.json()["accent_color"] == "#aabbcc"

    @pytest.mark.parametrize("value", ["nope", "#12345", "rgb(1,2,3)", ""])
    async def test_a_malformed_accent_is_a_field_error(
        self, cod_flow: CodFlowHarness, value: str
    ) -> None:
        landing = await _published_landing(cod_flow)

        response = await _configure(cod_flow, landing, {"accent_color": value})

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "accent_color"

    async def test_a_default_landing_serves_the_shipped_accent(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)

        response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

        assert response.json()["accent_color"] == "#1a7a4c"


class TestOfferPricing:
    async def test_a_discount_reduces_the_quoted_total_for_that_offer_only(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)  # product price 59900.00
        await _configure(
            cod_flow,
            landing,
            {
                "offer_count": 3,
                "offers": [
                    _offer(1),
                    _offer(2, discount_percent=10),
                    _offer(3, discount_percent=20),
                ],
            },
        )

        offers = (await cod_flow.client.get(f"/api/public/landings/{landing.slug}")).json()[
            "offers"
        ]

        assert offers[0]["total"] == pytest.approx(59900.0)
        assert offers[0]["savings"] == pytest.approx(0.0)
        # 2 x 59900 = 119800, less 10%.
        assert offers[1]["gross"] == pytest.approx(119800.0)
        assert offers[1]["total"] == pytest.approx(107820.0)
        assert offers[1]["savings"] == pytest.approx(11980.0)
        # 3 x 59900 = 179700, less 20%.
        assert offers[2]["total"] == pytest.approx(143760.0)

    async def test_the_single_unit_reference_price_is_served_but_never_charged(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)
        await _configure(
            cod_flow,
            landing,
            {"offer_count": 1, "offers": [_offer(1, compare_at_price=79900)]},
        )

        offer = (await cod_flow.client.get(f"/api/public/landings/{landing.slug}")).json()[
            "offers"
        ][0]

        assert offer["compare_at_price"] == pytest.approx(79900.0)
        # Informational only: the amount owed is still the product's price.
        assert offer["total"] == pytest.approx(59900.0)

    async def test_an_order_records_the_discounted_amount_it_was_quoted(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)
        await _configure(
            cod_flow,
            landing,
            {"offer_count": 2, "offers": [_offer(1), _offer(2, discount_percent=25)]},
        )

        response = await _submit_order(cod_flow, landing, quantity=2, phone="300 111 2233")

        assert response.status_code == 201
        order = await cod_flow.db.order.find_unique(where={"id": response.json()["order_id"]})
        assert order is not None
        assert order.quantity == 2
        assert order.discountPercent == 25
        assert float(order.unitPrice) == pytest.approx(59900.0)
        # 2 x 59900 = 119800, less 25% = 89850.
        assert float(order.totalPrice) == pytest.approx(89850.0)

    async def test_editing_a_discount_does_not_rewrite_an_existing_order(
        self, cod_flow: CodFlowHarness
    ) -> None:
        # The reason the order snapshots money at all: a courier is collecting
        # cash against what the buyer agreed to, not against today's config.
        landing = await _published_landing(cod_flow)
        await _configure(
            cod_flow,
            landing,
            {"offer_count": 2, "offers": [_offer(1), _offer(2, discount_percent=10)]},
        )
        submitted = await _submit_order(cod_flow, landing, quantity=2, phone="300 222 3344")
        order_id = submitted.json()["order_id"]

        await _configure(
            cod_flow,
            landing,
            {"offer_count": 2, "offers": [_offer(1), _offer(2, discount_percent=50)]},
        )

        order = await cod_flow.db.order.find_unique(where={"id": order_id})
        assert order is not None
        assert order.discountPercent == 10
        assert float(order.totalPrice) == pytest.approx(107820.0)

    async def test_a_quantity_the_landing_does_not_offer_is_rejected(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)
        await _configure(cod_flow, landing, {"offer_count": 1})

        response = await _submit_order(cod_flow, landing, quantity=3, phone="300 333 4455")

        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "quantity"

    async def test_no_order_is_persisted_for_an_unofferable_quantity(
        self, cod_flow: CodFlowHarness
    ) -> None:
        landing = await _published_landing(cod_flow)
        await _configure(cod_flow, landing, {"offer_count": 2})

        await _submit_order(cod_flow, landing, quantity=3, phone="300 444 5566")

        assert await cod_flow.db.order.count(where={"landingId": landing.landing_id}) == 0
