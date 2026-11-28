"""Drama FX layer: speed lines, impact bursts, per-layer contrast grade, screentone and brush-style SFX, drawn over panels.

Why (owner, 2026-11-28): even a relevant Z-Image panel read as flat next to real manhwa, whose drama is partly drawn on top of
the picture, not in it: radial speed lines at a shout, a white burst behind the sound effect, a darker vignette on a peak, halftone
screentone on a memory. The model cannot be trusted to paint these (Z-Image has no CFG, EVOLUTION 4.171), and they are
arithmetic, so they are a post layer keyed by the same schema enums (`Purpose`, `Layer`, `Shape`) as the prompt table in
`render/drama.py`, switchable per call so the bake-off can show it on and off. Nothing here names a work or a person; the
grades reuse `render/palette.py` (the S-curve) and `render/lightgrade.py`'s notion of low-key light.

No font is downloaded: the brush SFX is the existing display font drawn with a rough edge (noise-eroded alpha), a dry-brush
stroke look from the glyph outline."""

from __future__ import annotations

import math
import random

import numpy as np
from echotales.pipeline.pages import grammar_lettering as gl
from echotales.pipeline.render.drama import is_peak
from echotales.pipeline.storyboard.schema import Layer, Panel, Purpose, Shape
from PIL import Image, ImageDraw, ImageFilter

#: Purposes that get focus lines (converging on the face) rather than speed lines (a direction of travel).
_FOCUS = frozenset({Purpose.EXTREME_CLOSE, Purpose.REACTION, Purpose.CROWD_INDIVIDUAL, Purpose.COLD_OPEN})
_SCREENTONE = frozenset({Layer.MEMORY, Layer.LORE})
#: Per layer (vignette strength, contrast). A peak adds to both; a calm beat keeps the layer's base so the peak reads as a peak.
_LAYER_GRADE = {
    Layer.PRESENT: (0.30, 1.06), Layer.PAST: (0.38, 1.12), Layer.MEMORY: (0.22, 1.02),
    Layer.LORE: (0.25, 1.15), Layer.IMAGINED: (0.35, 1.08), Layer.DREAM: (0.28, 1.04),
}


def _arr(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.float32)


def _img(a: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def speed_lines(size: tuple[int, int], *, centre: tuple[float, float] = (0.5, 0.45), count: int = 110, seed: int = 0,
                inner: float = 0.28, colour: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """RGBA radial lines from the frame edge toward `centre`, stopping at `inner` of the half-diagonal so the subject stays clear.
    Line width tapers to a point at the inner end, as drawn lines do."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    cx, cy = centre[0] * w, centre[1] * h
    reach = math.hypot(w, h)
    for _ in range(count):
        ang = rng.uniform(0, math.tau)
        r0 = reach * rng.uniform(inner, inner + 0.22)
        r1 = reach * rng.uniform(0.62, 0.85)
        half = rng.uniform(0.0015, 0.006)
        p0 = (cx + math.cos(ang) * r0, cy + math.sin(ang) * r0)
        a1, a2 = ang - half, ang + half
        p1 = (cx + math.cos(a1) * r1, cy + math.sin(a1) * r1)
        p2 = (cx + math.cos(a2) * r1, cy + math.sin(a2) * r1)
        d.polygon([p0, p1, p2], fill=(*colour, rng.randint(70, 150)))
    return layer


def screentone(size: tuple[int, int], *, pitch: int = 9, angle_deg: float = 45.0) -> np.ndarray:
    """A 0..1 halftone-dot field (1 = ink dot) at `pitch` px on a 45 degree grid. A numpy field rather than a drawn grid so
    it is exact at any size and testable."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(angle_deg)
    u = (xx * math.cos(a) + yy * math.sin(a)) / pitch
    v = (-xx * math.sin(a) + yy * math.cos(a)) / pitch
    dist = np.sqrt((u - np.round(u)) ** 2 + (v - np.round(v)) ** 2)
    return (dist < 0.30).astype(np.float32)


def apply_panel_fx(img: Image.Image, panel: Panel, *, seed: int = 0, centre: tuple[float, float] = (0.5, 0.45)) -> Image.Image:
    """Grade and decorate one panel picture by its purpose and layer. Returns a new RGB image."""
    peak = is_peak(panel)
    w, h = img.size
    a = _arr(img)
    vig, con = _LAYER_GRADE[panel.layer]
    if peak:
        vig, con = vig + 0.22, con + 0.12
    a = np.clip((a - 128.0) * con + 128.0, 0, 255)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w * centre[0]) / (w / 1.4)) ** 2 + ((yy - h * centre[1]) / (h / 1.4)) ** 2)
    v = (np.clip((d - 0.45) / 0.9, 0, 1) ** 1.5 * vig)[..., None]
    a = a * (1 - v)
    if panel.layer in _SCREENTONE:
        # Dots only in the dark half of the picture, as a printed tone: it keeps highlights clean and reads as print, not noise.
        lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        dark = np.clip((150.0 - lum) / 150.0, 0, 1)[..., None]
        dots = screentone((w, h), pitch=max(w // 110, 6))[..., None]
        a = a * (1 - 0.30 * dark * dots)
    out = _img(a).convert("RGBA")
    if peak and panel.shape is not Shape.TEXT_ONLY:
        if panel.purpose in _FOCUS:
            out.alpha_composite(speed_lines(out.size, centre=centre, seed=seed, count=150, inner=0.34))
        elif panel.shape in (Shape.TALL, Shape.BLEED, Shape.DIAGONAL) or panel.purpose in (Purpose.HERO, Purpose.TRANSITION):
            out.alpha_composite(speed_lines(out.size, centre=centre, seed=seed, count=90, inner=0.42))
    return out.convert("RGB")


def burst(size: int, *, seed: int = 0, points: int = 18, fill: tuple[int, int, int] = (255, 255, 255),
          edge: tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    """An RGBA jagged impact star of `size` px, drawn behind SFX so a sound reads as an event."""
    rng = random.Random(seed)
    pad = size // 10
    img = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2 + pad
    pts = []
    for i in range(points * 2):
        ang = math.tau * i / (points * 2) + rng.uniform(-0.04, 0.04)
        r = size / 2 * (1.0 if i % 2 == 0 else rng.uniform(0.55, 0.72)) * rng.uniform(0.9, 1.0)
        pts.append((c + math.cos(ang) * r, c + math.sin(ang) * r))
    d.polygon([(x + size * 0.015, y + size * 0.015) for x, y in pts], fill=(0, 0, 0, 120))
    d.polygon(pts, fill=(*fill, 235), outline=(*edge, 255), width=max(size // 90, 2))
    return img


def brush_sfx(text: str, px: int, fill: tuple[int, int, int], edge: tuple[int, int, int], *, seed: int = 0) -> Image.Image:
    """Hand-brushed SFX: the display font at a heavy stroke, edge eroded by noise and streaked in the stroke direction (dry brush)."""
    f = gl.font("display", max(px, 12))
    text = text.upper()
    pad = int(px * 0.4)
    w = int(sum(f.getlength(c) for c in text) + 2 * pad + px * 0.1 * len(text))
    h = int(px * 1.9)
    stroke = max(3, int(px * 0.11))
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    x = pad
    rng = random.Random(seed)
    for ch in text:
        dy = int(rng.uniform(-0.08, 0.08) * px)
        d.text((x, h // 2 + dy), ch, font=f, fill=(*edge, 255), anchor="lm", stroke_width=stroke)
        d.text((x, h // 2 + dy), ch, font=f, fill=(*fill, 255), anchor="lm")
        x += f.getlength(ch) + px * 0.1
    alpha = np.asarray(base.getchannel("A"), dtype=np.float32) / 255.0
    nrng = np.random.default_rng(seed)
    # Streaks: noise stretched along x, so the erosion looks like bristle drag and not film grain.
    noise = nrng.random((h, w // 12 + 2)).astype(np.float32)
    streak = np.asarray(Image.fromarray((noise * 255).astype(np.uint8)).resize((w, h), Image.Resampling.BICUBIC), dtype=np.float32) / 255.0
    edge_zone = np.asarray(base.getchannel("A").filter(ImageFilter.GaussianBlur(max(stroke // 2, 2))), dtype=np.float32) / 255.0
    rough = np.where(edge_zone < 0.85, (streak > 0.38 + 0.25 * (1 - edge_zone)).astype(np.float32), 1.0)
    base.putalpha(Image.fromarray((alpha * rough * 255).astype(np.uint8)))
    angle = ((seed >> 3) % 21) - 10
    out = base.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


def draw_burst_and_brush(strip: Image.Image, m: gl.Measured, xy: tuple[int, int], fill, edge, *, seed: int = 0) -> tuple[int, int, int, int]:
    """Replace `gl.draw_sfx` when the FX layer is on: burst behind, brushed lettering on top, inside the measured SFX box."""
    assert m.sfx is not None
    bw, bh = m.sfx.size
    brush = brush_sfx(m.letter.text, m.font_px, fill, edge, seed=seed)
    k = min(bw / brush.width, bh / brush.height, 1.0)
    if k < 1.0:
        brush = brush.resize((max(int(brush.width * k), 1), max(int(brush.height * k), 1)), Image.Resampling.LANCZOS)
    star_size = int(min(max(bw, bh) * 1.25, strip.width * 0.9))
    star = burst(star_size, seed=seed)
    cx, cy = xy[0] + bw // 2, xy[1] + bh // 2
    # Only the star's own window is composited: the strip is ~1600 x 30000 px and a full-strip alpha composite per SFX is slow.
    x0, y0 = max(cx - star.width // 2, 0), max(cy - star.height // 2, 0)
    box = (x0, y0, min(x0 + star.width, strip.width), min(y0 + star.height, strip.height))
    region = strip.crop(box).convert("RGBA")
    region.alpha_composite(star, (0, 0), (0, 0, box[2] - box[0], box[3] - box[1]))
    region.alpha_composite(brush, (max(cx - brush.width // 2 - x0, 0), max(cy - brush.height // 2 - y0, 0)))
    strip.paste(region.convert("RGB"), box[:2])
    return (xy[0], xy[1], xy[0] + bw, xy[1] + bh)
