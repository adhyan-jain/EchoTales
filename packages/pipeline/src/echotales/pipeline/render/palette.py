"""Palette treatment: the restraint the reference art has and a checkpoint
does not.

**Why this is a post-process and not a prompt.** The same lesson the
monochrome attempt already learned (`panels.py`): a checkpoint renders what
its training distribution knows, and asking it in words for a discipline it
does not have produces the same picture with the words ignored. Colour
restraint is arithmetic, so it belongs where it cannot fail.

**Three treatments, because the reference art uses all three** -- the fan
art this pipeline is aimed at is mostly ink-on-paper monochrome, sometimes
monochrome with a single accent (a red robe, a gold flare, a teal flame
against grey), and occasionally full but muted colour. One flag could not
express that, and flat `convert("L")` -- the only option before this module
-- collapsed the middle case, which is the most striking of the three.

`ACCENT` is the one worth understanding. It keeps saturation only where the
hue is already close to a chosen one and desaturates everything else, so a
red-robed figure stays red against an ink-grey world. That is a composition
device, not a filter: it puts the eye exactly where the accent is, which is
why the reference pieces use it for the character and never for the
background.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from enum import StrEnum


class Palette(StrEnum):
    """How much colour a panel keeps."""

    #: Whatever the checkpoint produced. Right when the checkpoint's own
    #: palette is already restrained.
    COLOUR = "colour"
    #: Ink: greyscale with a contrast curve. Flat desaturation makes weak
    #: linework read as unfinished, which is why the first monochrome
    #: attempt was abandoned; the curve is what gives it something to stand
    #: on.
    INK = "ink"
    #: Ink, except where the hue is near `accent_hue`.
    ACCENT = "accent"


@dataclass(frozen=True, slots=True)
class PaletteSpec:
    """A treatment and its parameters."""

    palette: Palette = Palette.COLOUR
    #: Hue to preserve under `ACCENT`, in degrees (0 = red, 120 = green,
    #: 240 = blue). Xianxia's signature accent is cinnabar red; jade green
    #: and gold are the other two the genre reaches for.
    accent_hue: float = 0.0
    #: How wide a band around `accent_hue` survives, in degrees. Too narrow
    #: and a robe rendered in two shades of red half-desaturates, which
    #: looks like a bug rather than a choice.
    accent_width: float = 30.0
    #: Contrast applied to the desaturated part. 1.0 is unchanged; the
    #: default lifts blacks apart from midtones the way ink on paper does.
    contrast: float = 1.25
    #: Kept below 1.0 so the accent reads as *tinted*, not neon, against a
    #: grey field -- full saturation next to pure grey looks composited.
    accent_strength: float = 0.85


def _curve(value: float, contrast: float) -> float:
    """S-curve around mid-grey. Pure function so it is testable without PIL."""
    centred = (value - 0.5) * contrast + 0.5
    return min(1.0, max(0.0, centred))


def _hue_distance(hue: float, target: float) -> float:
    """Shortest distance between two hues on the colour wheel, in degrees."""
    diff = abs((hue % 360.0) - (target % 360.0))
    return min(diff, 360.0 - diff)


def accent_keep(hue: float, spec: PaletteSpec) -> float:
    """How much saturation a hue keeps: 1.0 inside the band, 0.0 outside.

    Falls off over the outer half of the band rather than cutting hard --
    a hard edge produces a visible contour through a gradient, which is the
    artefact that makes this read as a filter.
    """
    distance = _hue_distance(hue, spec.accent_hue)
    if distance <= spec.accent_width * 0.5:
        return 1.0
    if distance >= spec.accent_width:
        return 0.0
    span = spec.accent_width * 0.5
    return max(0.0, 1.0 - (distance - span) / span)


def apply_palette(image: object, spec: PaletteSpec) -> object:
    """Apply `spec` to a PIL image, returning a new RGB image.

    Returns the image untouched under `COLOUR`, so a caller can always route
    through here rather than branching at every call site.
    """
    if spec.palette is Palette.COLOUR:
        return image

    from PIL import Image, ImageEnhance

    rgb = image.convert("RGB")  # type: ignore[attr-defined]

    if spec.palette is Palette.INK:
        # "L" then back to "RGB": the ffmpeg segments and the IP-Adapter
        # both expect three channels, and a single-channel PNG would force a
        # conversion somewhere less visible.
        grey = rgb.convert("L")
        grey = ImageEnhance.Contrast(grey).enhance(spec.contrast)
        return grey.convert("RGB")

    # ACCENT: desaturate per pixel by how far its hue is from the accent.
    grey = ImageEnhance.Contrast(rgb.convert("L")).enhance(spec.contrast)
    source = rgb.load()
    grey_px = grey.load()
    out = Image.new("RGB", rgb.size)
    out_px = out.load()

    width, height = rgb.size
    for y in range(height):
        for x in range(width):
            r, g, b = source[x, y]
            hue, _lightness, saturation = colorsys.rgb_to_hls(
                r / 255.0, g / 255.0, b / 255.0
            )
            keep = accent_keep(hue * 360.0, spec) * spec.accent_strength
            if keep <= 0.0 or saturation <= 0.05:
                level = grey_px[x, y]
                out_px[x, y] = (level, level, level)
                continue
            level = grey_px[x, y]
            out_px[x, y] = (
                round(level + (r - level) * keep),
                round(level + (g - level) * keep),
                round(level + (b - level) * keep),
            )
    return out
