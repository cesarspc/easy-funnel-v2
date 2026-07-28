"""Public landing image-candidate API regression tests.

The normal upload pipeline is covered by `test_banner_upload_service.py`.
These tests focus on the HTTP read boundary: Prisma relations must be eagerly
loaded and serialized into usable responsive candidates without crashing on
legacy rows that contain no variants.
"""

from __future__ import annotations

from app.domains.images.edge_color import blend_hex

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness

pytestmark = requires_database


async def test_public_landing_returns_loaded_responsive_image_variants(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    seeded_banner = await cod_flow.seed_banner(landing)

    response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

    assert response.status_code == 200
    (banner,) = response.json()["banners"]
    assert banner["id"] == seeded_banner.banner_id
    assert banner["alt_text"] == "E2E banner 0"
    assert banner["order_index"] == 0
    assert banner["variants"] == [
        {
            "width": 480,
            "height": 320,
            "format": "jpeg",
            "url": (f"https://test-images.example.com/variants/{seeded_banner.opaque_key}/480.jpg"),
        },
        {
            "width": 800,
            "height": 533,
            "format": "webp",
            "url": (
                f"https://test-images.example.com/variants/{seeded_banner.opaque_key}/800.webp"
            ),
        },
    ]


async def test_public_landing_does_not_crash_when_legacy_asset_has_no_variants(
    cod_flow: CodFlowHarness,
) -> None:
    landing = await cod_flow.seed_landing()
    seeded_banner = await cod_flow.seed_banner(landing, with_variants=False)

    response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

    assert response.status_code == 200
    (banner,) = response.json()["banners"]
    assert banner["id"] == seeded_banner.banner_id
    assert banner["variants"] == []


async def test_public_landing_blends_cta_band_from_precomputed_edge_colors(
    cod_flow: CodFlowHarness,
) -> None:
    """The band between two banners is derived per request from stored edges."""
    landing = await cod_flow.seed_landing()
    await cod_flow.seed_banner(
        landing, order_index=0, top_edge_color="#ffffff", bottom_edge_color="#204080"
    )
    await cod_flow.seed_banner(
        landing, order_index=1, top_edge_color="#802040", bottom_edge_color="#000000"
    )

    response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cta_positions"] == [1, 2]
    first, second = payload["cta_backgrounds"]

    assert first == {
        "position": 1,
        "top_color": "#204080",
        "bottom_color": "#802040",
        "blend_color": blend_hex("#204080", "#802040"),
        "foreground": "light",
        "source": "blend",
    }
    # The last position has no banner below it, so the band is a solid.
    assert second["source"] == "above"
    assert second["top_color"] == second["bottom_color"] == "#000000"

    assert payload["banners"][0]["bottom_edge_color"] == "#204080"


async def test_public_landing_carries_the_cta_band_style_without_altering_colors(
    cod_flow: CodFlowHarness,
) -> None:
    """`solid` is a paint instruction, not a different set of colors.

    The band descriptors are byte-identical between the two styles; the client
    decides whether to run the gradient or fill with `blend_color`. Deriving
    different colors per style here would put the same decision in two places.
    """
    payloads = {}
    for style in ("gradient", "solid"):
        landing = await cod_flow.seed_landing(cta_band_style=style)
        await cod_flow.seed_banner(
            landing, order_index=0, top_edge_color="#ffffff", bottom_edge_color="#204080"
        )
        await cod_flow.seed_banner(
            landing, order_index=1, top_edge_color="#802040", bottom_edge_color="#000000"
        )
        response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")
        assert response.status_code == 200
        payloads[style] = response.json()

    assert payloads["gradient"]["cta_band_style"] == "gradient"
    assert payloads["solid"]["cta_band_style"] == "solid"
    assert payloads["solid"]["cta_backgrounds"] == payloads["gradient"]["cta_backgrounds"]

    # The color a `solid` landing paints is on the descriptor already.
    first = payloads["solid"]["cta_backgrounds"][0]
    assert first["blend_color"] == blend_hex("#204080", "#802040")


async def test_public_landing_paints_cta_band_from_edges_that_are_not_flat(
    cod_flow: CodFlowHarness,
) -> None:
    """A busy photographic edge still paints; `*_edge_flat` gates nothing.

    Full-resolution strips of real product photography almost never pass the
    flatness test, so treating the flag as a suppressor left every band on the
    client's neutral token (see app/domains/landings/cta_background.py).
    """
    landing = await cod_flow.seed_landing()
    await cod_flow.seed_banner(
        landing,
        order_index=0,
        top_edge_color="#817d7c",
        bottom_edge_color="#bba495",
        edges_flat=False,
    )
    await cod_flow.seed_banner(
        landing,
        order_index=1,
        top_edge_color="#0b377e",
        bottom_edge_color="#c3beb9",
        edges_flat=False,
    )

    response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

    assert response.status_code == 200
    payload = response.json()
    first, second = payload["cta_backgrounds"]

    assert first["source"] == "blend"
    assert first["top_color"] == "#bba495"
    assert first["bottom_color"] == "#0b377e"
    assert first["foreground"] is not None
    assert second["source"] == "above"
    assert second["top_color"] == second["bottom_color"] == "#c3beb9"

    # The per-banner edge colors are surfaced unsuppressed too.
    assert payload["banners"][0]["top_edge_color"] == "#817d7c"
    assert payload["banners"][1]["bottom_edge_color"] == "#c3beb9"


async def test_public_landing_falls_back_when_no_edge_colors_are_stored(
    cod_flow: CodFlowHarness,
) -> None:
    """Assets predating edge extraction yield a neutral-fallback band."""
    landing = await cod_flow.seed_landing()
    await cod_flow.seed_banner(landing)

    response = await cod_flow.client.get(f"/api/public/landings/{landing.slug}")

    assert response.status_code == 200
    (band,) = response.json()["cta_backgrounds"]
    assert band == {
        "position": 1,
        "top_color": None,
        "bottom_color": None,
        "blend_color": None,
        "foreground": None,
        "source": "fallback",
    }
