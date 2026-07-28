"""CTA band background derivation (see docs/backend.md, Requirements 3.9-3.15).

A CTA renders after a 1-based banner position, so its band sits between the
**bottom** edge of the banner above and the **top** edge of the banner below.
This module turns the persisted per-banner edge colors (extracted at upload by
`app.domains.images.edge_color`) plus the computed CTA positions into one
background descriptor per band.

The blend is done here, per request, and deliberately not stored: the pairing
depends on banner order, `ctaMode`, `ctaInterval`, and `ctaPositions`, all of
which change without any upload. Recomputing is a handful of arithmetic
operations per band — no image access, no I/O — so there is nothing to cache
and nothing to invalidate.

The band is described as a gradient from the top color to the bottom color,
which reads as a continuation of the artwork. A flat mean would introduce two
seams where there was one, so `blend_color` (the linear-light midpoint) is
only a solid-fill fallback. Where a CTA has a single neighbour (last position,
or a missing opposite edge) both endpoints are that one color and the gradient
degenerates to a solid.

**Busy edges are still painted.** An earlier version withheld the color when
`image_assets.*_edge_flat` was false, on the theory that a neutral band is
safer than a confidently wrong one. That is backwards for this consumer. The
strip mean minimises error against its own strip by construction, so a fixed
neutral is weakly worse as a stand-in for *every* edge, flat or not. And the
neutral's error is the worst kind: a full-width band of unrelated lightness
between two full-bleed photos reads as a rendering failure, where an
approximate continuation reads as artwork. Since edge strips of real product
photography almost never pass a flatness test at full resolution, gating on it
meant the feature effectively never engaged. `top`/`bottom` are now `None`
only when no color was extracted at all, and `SOURCE_FALLBACK` means exactly
that: missing data, not low confidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.images.edge_color import blend_hex, preferred_foreground

SOURCE_BLEND = "blend"
SOURCE_ABOVE = "above"
SOURCE_BELOW = "below"
SOURCE_FALLBACK = "fallback"


@dataclass(frozen=True)
class BannerEdges:
    """The persisted edge colors of one banner, in render order.

    `top`/`bottom` are `None` only when no edge color is stored — the asset
    predates edge extraction, or extraction failed. A busy edge still supplies
    its mean (see the module docstring).
    """

    top: str | None
    bottom: str | None


@dataclass(frozen=True)
class CtaBandBackground:
    """Background for the CTA rendered after 1-based banner `position`.

    `top_color`/`bottom_color` are the gradient endpoints and `blend_color`
    the solid-fill equivalent; all three are `None` when neither neighbouring
    edge has a stored color, in which case the client applies its neutral
    token.
    """

    position: int
    top_color: str | None
    bottom_color: str | None
    blend_color: str | None
    foreground: str | None
    source: str


def _band_for_position(
    position: int, edges_by_position: dict[int, BannerEdges]
) -> CtaBandBackground:
    above = edges_by_position.get(position)
    below = edges_by_position.get(position + 1)

    top_color = above.bottom if above is not None else None
    bottom_color = below.top if below is not None else None

    if top_color is not None and bottom_color is not None:
        source = SOURCE_BLEND
    elif top_color is not None:
        source = SOURCE_ABOVE
        bottom_color = top_color
    elif bottom_color is not None:
        source = SOURCE_BELOW
        top_color = bottom_color
    else:
        return CtaBandBackground(
            position=position,
            top_color=None,
            bottom_color=None,
            blend_color=None,
            foreground=None,
            source=SOURCE_FALLBACK,
        )

    blend_color = (
        top_color if top_color == bottom_color else blend_hex(top_color, bottom_color, 0.5)
    )
    return CtaBandBackground(
        position=position,
        top_color=top_color,
        bottom_color=bottom_color,
        blend_color=blend_color,
        foreground=preferred_foreground(blend_color),
        source=source,
    )


def compute_cta_backgrounds(
    cta_positions: list[int], banner_edges: list[BannerEdges]
) -> list[CtaBandBackground]:
    """Derive one background per CTA position.

    `banner_edges` is in render order (index 0 is banner position 1) and must
    already exclude banners that are not displayed. Positions outside that
    sequence still produce a descriptor, resolved from whichever side exists.
    """
    edges_by_position = {index + 1: edges for index, edges in enumerate(banner_edges)}
    return [
        _band_for_position(position, edges_by_position) for position in sorted(set(cta_positions))
    ]
