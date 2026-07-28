"""Unit + property tests for CTA band background derivation.

Covers `app.domains.landings.cta_background`: pairing each CTA position with
the banner edges above and below it, degenerating to a single-sided band at
the sequence end, and falling back cleanly when neither edge is usable.
"""

from __future__ import annotations

from app.domains.images.edge_color import (
    FOREGROUND_DARK,
    FOREGROUND_LIGHT,
    blend_hex,
    format_hex,
    parse_hex,
)
from app.domains.landings.cta_background import (
    SOURCE_ABOVE,
    SOURCE_BELOW,
    SOURCE_BLEND,
    SOURCE_FALLBACK,
    BannerEdges,
    compute_cta_backgrounds,
)
from app.domains.landings.cta_placement import compute_cta_positions, validate_cta_config
from hypothesis import given, settings
from hypothesis import strategies as st

_HEX = st.tuples(
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
).map(format_hex)
_MAYBE_HEX = st.one_of(st.none(), _HEX)
_EDGES = st.builds(BannerEdges, top=_MAYBE_HEX, bottom=_MAYBE_HEX)


class TestComputeCtaBackgrounds:
    def test_band_between_two_banners_blends_both_edges(self) -> None:
        edges = [
            BannerEdges(top="#ffffff", bottom="#204080"),
            BannerEdges(top="#802040", bottom="#000000"),
        ]

        bands = compute_cta_backgrounds([1], edges)

        assert len(bands) == 1
        band = bands[0]
        assert band.position == 1
        assert band.source == SOURCE_BLEND
        assert band.top_color == "#204080"  # bottom edge of the banner above
        assert band.bottom_color == "#802040"  # top edge of the banner below
        assert band.blend_color == blend_hex("#204080", "#802040")

    def test_last_position_uses_only_the_banner_above(self) -> None:
        edges = [BannerEdges(top="#ffffff", bottom="#123456")]

        band = compute_cta_backgrounds([1], edges)[0]

        assert band.source == SOURCE_ABOVE
        # Both gradient endpoints equal, so the band renders as a solid.
        assert band.top_color == band.bottom_color == "#123456"
        assert band.blend_color == "#123456"

    def test_unusable_edge_above_falls_through_to_the_banner_below(self) -> None:
        edges = [BannerEdges(top="#ffffff", bottom=None), BannerEdges(top="#abcdef", bottom=None)]

        band = compute_cta_backgrounds([1], edges)[0]

        assert band.source == SOURCE_BELOW
        assert band.top_color == band.bottom_color == "#abcdef"

    def test_no_usable_edge_returns_a_fallback_band(self) -> None:
        edges = [BannerEdges(top=None, bottom=None), BannerEdges(top=None, bottom=None)]

        band = compute_cta_backgrounds([1], edges)[0]

        assert band.source == SOURCE_FALLBACK
        assert band.top_color is None
        assert band.bottom_color is None
        assert band.blend_color is None
        assert band.foreground is None

    def test_position_beyond_the_sequence_is_resolved_from_whatever_exists(self) -> None:
        edges = [BannerEdges(top="#ffffff", bottom="#111111")]

        bands = compute_cta_backgrounds([1, 5], edges)

        assert [band.position for band in bands] == [1, 5]
        assert bands[1].source == SOURCE_FALLBACK

    def test_foreground_follows_the_blended_luminance(self) -> None:
        dark = compute_cta_backgrounds([1], [BannerEdges(top=None, bottom="#101010")])[0]
        light = compute_cta_backgrounds([1], [BannerEdges(top=None, bottom="#f5f0e8")])[0]

        assert dark.foreground == FOREGROUND_LIGHT
        assert light.foreground == FOREGROUND_DARK

    def test_positions_are_deduplicated_and_sorted(self) -> None:
        edges = [BannerEdges(top="#ffffff", bottom="#ffffff")] * 3

        bands = compute_cta_backgrounds([3, 1, 1, 2], edges)

        assert [band.position for band in bands] == [1, 2, 3]

    def test_no_positions_yields_no_bands(self) -> None:
        assert compute_cta_backgrounds([], [BannerEdges(top="#fff", bottom="#fff")]) == []

    @given(
        banner_count=st.integers(min_value=1, max_value=15),
        interval=st.integers(min_value=1, max_value=15),
        edges=st.lists(_EDGES, min_size=1, max_size=15),
    )
    @settings(max_examples=60, deadline=None)
    def test_every_cta_position_gets_exactly_one_valid_band(
        self, banner_count: int, interval: int, edges: list[BannerEdges]
    ) -> None:
        """One band per CTA position, in order, with parseable colors.

        Either all three colors are present (band is paintable) or all three
        are absent (client applies its neutral) - never a half-filled band.
        """
        config = validate_cta_config("every_n", interval=interval)
        positions = compute_cta_positions(config, banner_count)

        bands = compute_cta_backgrounds(positions, edges[:banner_count])

        assert [band.position for band in bands] == positions
        for band in bands:
            colors = (band.top_color, band.bottom_color, band.blend_color)
            if band.source == SOURCE_FALLBACK:
                assert colors == (None, None, None)
                assert band.foreground is None
                continue
            assert all(color is not None for color in colors)
            assert band.foreground in {FOREGROUND_LIGHT, FOREGROUND_DARK}
            for color in colors:
                assert color is not None
                parse_hex(color)  # raises if not a valid CSS hex color
