"""Banner edge-color extraction and sRGB color math.

The CTA band that renders between two banners has to look like part of the
artwork, so it is painted with colors derived from the banner edges it sits
against. Those edge colors are a pure function of the image pixels, so they
are extracted **once** here — during upload, on the source image that is
already decoded in memory for variant generation — and persisted on
`image_assets`. Nothing in the request path ever re-reads an image.

Cost control:

- Only a thin strip at each edge is sampled (`EDGE_STRIP_FRACTION`, capped
  at `EDGE_STRIP_MAX_PX`). The CTA sits flush against the edge, so a large
  region average would only wash the result out.
- Statistics come from `Image.histogram()`, which Pillow computes in C. No
  per-pixel Python loop runs at any image size; the Python cost is a fixed
  768-term reduction per edge.
- Channel means are computed in **linear light** (sRGB de-gamma, average,
  re-gamma). Averaging gamma-encoded bytes directly biases results dark and
  makes blends look dirty.

Flatness: `flat` records whether the strip's worst per-channel standard
deviation stays within `EDGE_FLATNESS_MAX_STDDEV` — whether one color is a
close stand-in for the whole strip. It is **diagnostic only**. The CTA band is
painted from `color` either way, because the strip mean minimises error
against that strip by construction and no fixed neutral can beat it; see
`app.domains.landings.cta_background` for that argument in full.

The measure is deliberately taken at full resolution, so fine texture and
dithering (PNG-8) count against flatness even where the large-scale color is
uniform. Real photographic edges are therefore usually reported as not flat,
which is why the flag must not gate anything visual.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

EDGE_STRIP_FRACTION = 0.03
EDGE_STRIP_MAX_PX = 64
EDGE_FLATNESS_MAX_STDDEV = 16.0

# Luminance at which black and white text have equal WCAG contrast against
# the background; above it prefer dark foreground, below it prefer light.
FOREGROUND_LUMINANCE_CROSSOVER = 0.179

FOREGROUND_LIGHT = "light"
FOREGROUND_DARK = "dark"

_ALPHA_FLATTEN_BACKGROUND = (255, 255, 255, 255)


def _srgb_byte_to_linear(value: int) -> float:
    channel = value / 255.0
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


# 256-entry de-gamma lookup: turns the linear-light conversion into a table
# read so it never costs anything per pixel.
_SRGB_TO_LINEAR: tuple[float, ...] = tuple(_srgb_byte_to_linear(i) for i in range(256))


def _linear_to_srgb_byte(linear: float) -> int:
    if linear <= 0.0:
        return 0
    if linear >= 1.0:
        return 255
    encoded = linear * 12.92 if linear <= 0.0031308 else 1.055 * (linear ** (1 / 2.4)) - 0.055
    return max(0, min(255, round(encoded * 255.0)))


@dataclass(frozen=True)
class EdgeColor:
    """One sampled banner edge.

    `color` is always a `#rrggbb` string; `flat` reports whether the strip
    is uniform enough for that single color to be a faithful stand-in, and is
    diagnostic only (see the module docstring — it gates no rendering).
    """

    color: str
    flat: bool
    stddev: float


@dataclass(frozen=True)
class EdgeColors:
    top: EdgeColor
    bottom: EdgeColor


def format_hex(rgb: tuple[int, int, int]) -> str:
    """Render an 8-bit RGB triple as a lowercase `#rrggbb` string."""
    red, green, blue = rgb
    return f"#{red:02x}{green:02x}{blue:02x}"


def parse_hex(color: str) -> tuple[int, int, int]:
    """Parse `#rrggbb` (or `#rgb`) into an 8-bit RGB triple.

    Raises `ValueError` for anything else, so a malformed stored value
    surfaces as a handled fallback rather than a bad CSS color.
    """
    text = color.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        raise ValueError(f"Not a hex color: {color!r}")
    try:
        value = int(text, 16)
    except ValueError as exc:
        raise ValueError(f"Not a hex color: {color!r}") from exc
    return (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF


def blend_hex(first: str, second: str, weight: float = 0.5) -> str:
    """Mix two hex colors in linear light; `weight` is `second`'s share."""
    if not 0.0 <= weight <= 1.0:
        raise ValueError("weight must be between 0.0 and 1.0")
    first_rgb = parse_hex(first)
    second_rgb = parse_hex(second)
    mixed = tuple(
        _linear_to_srgb_byte(
            _SRGB_TO_LINEAR[first_channel] * (1.0 - weight)
            + _SRGB_TO_LINEAR[second_channel] * weight
        )
        for first_channel, second_channel in zip(first_rgb, second_rgb, strict=True)
    )
    return format_hex((mixed[0], mixed[1], mixed[2]))


def relative_luminance(color: str) -> float:
    """WCAG 2.x relative luminance (0.0 black - 1.0 white)."""
    red, green, blue = parse_hex(color)
    return (
        0.2126 * _SRGB_TO_LINEAR[red]
        + 0.7152 * _SRGB_TO_LINEAR[green]
        + 0.0722 * _SRGB_TO_LINEAR[blue]
    )


def preferred_foreground(color: str) -> str:
    """Return `"light"` or `"dark"`: the foreground that reads on `color`.

    Without this the CTA button and its label can land on a band of
    near-identical lightness (WCAG 1.4.3 failure).
    """
    if relative_luminance(color) > FOREGROUND_LUMINANCE_CROSSOVER:
        return FOREGROUND_DARK
    return FOREGROUND_LIGHT


def edge_strip_height(image_height: int) -> int:
    """Rows sampled at each edge: `EDGE_STRIP_FRACTION`, clamped."""
    if image_height <= 0:
        raise ValueError("image_height must be positive")
    scaled = round(image_height * EDGE_STRIP_FRACTION)
    return max(1, min(scaled, EDGE_STRIP_MAX_PX, image_height))


def _flatten_to_rgb(strip: Image.Image) -> Image.Image:
    """Return `strip` as RGB, compositing any alpha over white.

    White matches how the JPEG variants flatten transparency, so a
    transparent edge and its rendered variant agree.
    """
    if strip.mode == "RGB":
        return strip
    has_alpha = strip.mode in {"RGBA", "LA", "PA"} or (
        strip.mode == "P" and "transparency" in strip.info
    )
    if has_alpha:
        rgba = strip.convert("RGBA")
        background = Image.new("RGBA", rgba.size, _ALPHA_FLATTEN_BACKGROUND)
        return Image.alpha_composite(background, rgba).convert("RGB")
    return strip.convert("RGB")


def _strip_statistics(strip: Image.Image) -> tuple[tuple[int, int, int], float]:
    """Linear-light mean color and worst per-channel sRGB stddev of `strip`.

    Both come from the C-level histogram, so cost is independent of the
    strip's pixel count.
    """
    histogram = strip.histogram()
    if len(histogram) < 768:  # pragma: no cover - _flatten_to_rgb guarantees RGB
        raise ValueError("Expected an RGB strip with a 3x256 histogram")

    mean_channels: list[int] = []
    worst_stddev = 0.0

    for channel_index in range(3):
        counts = histogram[channel_index * 256 : (channel_index + 1) * 256]
        total = sum(counts)
        if total == 0:  # pragma: no cover - a cropped strip always has pixels
            mean_channels.append(0)
            continue

        linear_sum = 0.0
        encoded_sum = 0
        encoded_square_sum = 0
        for value, count in enumerate(counts):
            if count == 0:
                continue
            linear_sum += _SRGB_TO_LINEAR[value] * count
            encoded_sum += value * count
            encoded_square_sum += value * value * count

        mean_channels.append(_linear_to_srgb_byte(linear_sum / total))

        encoded_mean = encoded_sum / total
        variance = max(0.0, encoded_square_sum / total - encoded_mean * encoded_mean)
        worst_stddev = max(worst_stddev, variance**0.5)

    return (mean_channels[0], mean_channels[1], mean_channels[2]), worst_stddev


def _extract_edge(image: Image.Image, *, top: bool) -> EdgeColor:
    width, height = image.size
    strip_height = edge_strip_height(height)
    box = (0, 0, width, strip_height) if top else (0, height - strip_height, width, height)
    strip = _flatten_to_rgb(image.crop(box))
    rgb, stddev = _strip_statistics(strip)
    return EdgeColor(
        color=format_hex(rgb),
        flat=stddev <= EDGE_FLATNESS_MAX_STDDEV,
        stddev=stddev,
    )


def extract_edge_colors(image: Image.Image) -> EdgeColors:
    """Sample the top and bottom edge colors of a decoded banner image.

    Call once per upload with the same in-memory image used for variant
    generation; the result is persisted and never recomputed per request.
    """
    if image.width <= 0 or image.height <= 0:
        raise ValueError("image must have positive dimensions")
    return EdgeColors(
        top=_extract_edge(image, top=True),
        bottom=_extract_edge(image, top=False),
    )
