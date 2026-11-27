"""Lettering taxonomy for the storyboard webtoon renderer (one drawing routine per `LetterKind`).

Why a second lettering module: `lettering.py` knows four kinds (speech, narration, thought, SFX overlay) and sets
them from span rows. The storyboard contract carries eleven (docs/results/MANHWA_DIRECTING_PATTERNS.md rule 8),
and real adapters give each its own silhouette: spiky shout, dashed whisper, fuzzy-black dread, glowing-ring
memory, a card for time and place, a name card, a poem on a pale wash, SFX drawn into the art. Placement here is
a grid search over a cost map (faces and salient cells are expensive, other balloons are forbidden) because the
v57 pages showed balloons landing on faces whenever placement was a fixed corner.

Every shape is painted on a 3x supersampled layer and reduced, because PIL's polygons and ellipses have no
antialiasing and a webtoon is read at phone size where stair-steps are the first thing the eye sees.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from echotales.pipeline.pages.storyboard_style import LayerStyle, StyleTable
from echotales.pipeline.storyboard.schema import Letter, LetterKind
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
_BOLD = FONT_DIR / "ComicNeue-Bold.pfb"
_REG = FONT_DIR / "ComicNeue-Regular.pfb"
_DISPLAY = FONT_DIR / "Lato-Black.ttf"
_FALLBACK = FONT_DIR / "LiberationSans-Bold.ttf"
INK = (18, 18, 22)
SS = 3

#: Kinds that grow a tail toward a speaker.
TAILED = {LetterKind.SPEECH, LetterKind.SHOUT, LetterKind.WHISPER, LetterKind.DREAD, LetterKind.THOUGHT}
#: Kinds placed on the panel's centre line rather than searched left/right.
CENTRED = {LetterKind.NARRATION, LetterKind.TIME_PLACE, LetterKind.POEM}


@lru_cache(maxsize=128)
def font(name: str, px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = {"bold": _BOLD, "reg": _REG, "display": _DISPLAY}[name]
    for p in (path, _FALLBACK):
        try:
            return ImageFont.truetype(str(p), px)
        except OSError:
            continue
    return ImageFont.load_default()


# --------------------------------------------------------------------------- measuring

#: kind -> (font, upper, max width share of the strip, pad x, pad y, inflate, size factor); lengths at 1600 px.
_SPEC = {
    LetterKind.SPEECH: ("bold", True, 0.40, 42, 30, 1.0, 1.0),
    LetterKind.SHOUT: ("bold", True, 0.44, 30, 24, 1.42, 1.08),
    LetterKind.WHISPER: ("reg", True, 0.34, 38, 28, 1.0, 0.92),
    LetterKind.DREAD: ("bold", True, 0.40, 44, 32, 1.0, 1.0),
    LetterKind.THOUGHT: ("bold", True, 0.36, 34, 26, 1.34, 0.96),
    LetterKind.MEMORY: ("reg", False, 0.44, 30, 24, 1.34, 1.0),
    LetterKind.NARRATION: ("reg", False, 0.58, 34, 26, 1.0, 0.94),
    LetterKind.TIME_PLACE: ("bold", True, 0.70, 80, 56, 1.0, 1.28),
    LetterKind.NAME_CARD: ("bold", False, 0.42, 40, 28, 1.0, 1.0),
    LetterKind.POEM: ("reg", False, 0.46, 46, 34, 1.0, 1.0),
}


def _wrap(text: str, f, max_w: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if cur and f.getlength(trial) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return lines or [""]


def _balanced(text: str, f, max_w: float) -> list[str]:
    """Wrap, then narrow the measure while the line count holds, so a balloon is a block, not a ragged stub."""
    lines = _wrap(text, f, max_w)
    n = len(lines)
    if n < 2:
        return lines
    w = max_w
    while w > max_w * 0.5:
        w2 = w * 0.93
        trial = _wrap(text, f, w2)
        if len(trial) != n or max(f.getlength(t) for t in trial) > max_w:
            break
        lines, w = trial, w2
    return lines


@dataclass
class Measured:
    idx: int
    letter: Letter
    kind: LetterKind
    lines: list[str]
    font_px: int
    #: Outer balloon size (w, h) in strip px, tail not included.
    size: tuple[int, int]
    sub_lines: list[str] | None = None  # name card subtitle
    sfx: Image.Image | None = None
    lost: str = ""


def measure(
    idx: int, letter: Letter, style: StyleTable, layer: LayerStyle, *, panel_w: int, panel_h: int,
    scale_down: float = 1.0, max_h: int | None = None, big_sfx: bool = False,
) -> Measured:
    """Fit `letter` into a balloon: shrink the font to the legibility floor, then truncate (never silently:
    `lost` carries the words dropped so the caller can report them)."""
    kind = letter.kind
    s = style.s
    if kind == LetterKind.SFX:
        target_w = panel_w * (0.80 if big_sfx else 0.40)
        px = int(max(s(80), min(s(430), target_w / max(len(letter.text), 1) / 0.62)) * scale_down)
        px = min(px, int(panel_h * 0.5))
        img = render_sfx(letter.text, px, layer.sfx_fill, layer.sfx_edge, seed=zlib.crc32(letter.text.encode()))
        return Measured(idx, letter, kind, [letter.text], px, img.size, sfx=img)
    fname, upper, share, padx, pady, inflate, fk = _SPEC[kind]
    padx, pady = s(padx), s(pady)
    text = letter.text.upper() if upper else letter.text
    sub = None
    if kind == LetterKind.NAME_CARD:
        name, _, rest = text.replace(" | ", "\n").partition("\n")
        text, sub = name.upper(), rest or None
    max_w = panel_w * share - 2 * padx
    max_h = max_h or int(panel_h * 0.8)
    floor = max(s(style.min_font_px) - 0, 10) if panel_w >= s(480) else 8
    base = int(style.s(style.font_px) * fk * scale_down)
    px = max(base, floor)
    while True:
        f = font(fname, px)
        lines = _balanced(text, f, max_w / inflate)
        sub_lines = _balanced(sub, font("reg", int(px * 0.78)), max_w / inflate) if sub else None
        lh = int(px * 1.14)
        th = lh * len(lines) + (int(px * 0.8 * 1.14) * len(sub_lines) + s(8) if sub_lines else 0)
        if th * inflate + 2 * pady <= max_h or px <= floor:
            break
        px = max(px - 2, floor)
    lost = ""
    if th * inflate + 2 * pady > max_h:
        keep = max(1, int((max_h - 2 * pady) / inflate // lh))
        lost = " ".join(lines[keep:])
        lines = lines[:keep]
        lines[-1] = lines[-1].rstrip(" ,.;") + "..."
        th = lh * len(lines)
    tw = max(f.getlength(t) for t in lines)
    if sub_lines:
        tw = max(tw, max(font("reg", int(px * 0.78)).getlength(t) for t in sub_lines))
    w = int(tw * inflate + 2 * padx)
    h = int(th * inflate + 2 * pady)
    if kind == LetterKind.NAME_CARD:
        w += s(24)
    return Measured(idx, letter, kind, lines, px, (w, h), sub_lines=sub_lines, lost=lost)


# --------------------------------------------------------------------------- SFX


def render_sfx(text: str, px: int, fill, edge, *, seed: int = 0) -> Image.Image:
    """Stylised lettering for drawing into art: per-glyph size and baseline wobble, white keyline, shear and a
    tilt, because real SFX are hand-lettered and a straight sans word reads as a caption, not a sound."""
    text = text.upper()
    f_base = px
    pad = int(px * 0.5)
    glyphs = []
    x = pad
    for i, ch in enumerate(text):
        k = 1.0 + 0.14 * math.sin(seed % 97 + i * 1.7)
        f = font("display", max(int(f_base * k), 8))
        adv = f.getlength(ch) + px * 0.03
        glyphs.append((ch, f, x, int(px * 0.09 * math.sin(i * 0.9 + seed % 13))))
        x += adv
    w = int(x + pad)
    h = int(px * 1.9)
    stroke = max(3, int(px * 0.085))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    for ch, f, gx, dy in glyphs:
        pos = (gx, h // 2 + dy)
        ds.text((pos[0] + stroke, pos[1] + stroke), ch, font=f, fill=(0, 0, 0, 170), anchor="lm", stroke_width=stroke * 2)
        d.text(pos, ch, font=f, fill=(*edge, 255), anchor="lm", stroke_width=stroke)
        d.text(pos, ch, font=f, fill=(*fill, 255), anchor="lm")
    shadow = shadow.filter(ImageFilter.GaussianBlur(stroke))
    out = Image.alpha_composite(shadow, layer)
    shear = 0.22 if seed % 2 else -0.22
    out = out.transform(
        (w + int(abs(shear) * h), h), Image.Transform.AFFINE,
        (1, shear, -shear * h / 2 if shear > 0 else 0, 0, 1, 0), resample=Image.Resampling.BICUBIC,
    )
    angle = ((seed >> 3) % 25) - 12
    out = out.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


# --------------------------------------------------------------------------- drawing


class _Layer:
    """A supersampled RGBA scratch region over the strip; shapes are drawn in strip coordinates."""

    def __init__(self, strip: Image.Image, box: tuple[int, int, int, int]):
        x0, y0, x1, y1 = box
        self.x0, self.y0 = max(x0, 0), max(y0, 0)
        self.x1, self.y1 = min(x1, strip.width), min(y1, strip.height)
        self.strip = strip
        self.w, self.h = self.x1 - self.x0, self.y1 - self.y0
        self.img = Image.new("RGBA", (self.w * SS, self.h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def p(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.x0) * SS, (y - self.y0) * SS)

    def bx(self, b, grow: float = 0.0) -> tuple[float, float, float, float]:
        a = self.p(b[0] - grow, b[1] - grow)
        c = self.p(b[2] + grow, b[3] + grow)
        return (*a, *c)

    def commit(self) -> None:
        small = self.img.resize((self.w, self.h), Image.Resampling.LANCZOS)
        region = self.strip.crop((self.x0, self.y0, self.x1, self.y1)).convert("RGBA")
        region.alpha_composite(small)
        self.strip.paste(region.convert("RGB"), (self.x0, self.y0))


def _rr_points(box, r: float, step: float) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = box
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts: list[tuple[float, float]] = []
    corners = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
    for cx, cy, a0 in corners:
        n = max(4, int(r * math.pi / 2 / step))
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _tail_geometry(box, tip, half_w: float, max_len: float):
    """Base centre on the balloon edge along the ray to `tip`; tip clipped to `max_len` beyond the edge."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    a, b = (box[2] - box[0]) / 2, (box[3] - box[1]) / 2
    dx, dy = tip[0] - cx, tip[1] - cy
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    t = 1.0 / math.sqrt((ux / a) ** 2 + (uy / b) ** 2)
    edge = (cx + ux * t, cy + uy * t)
    length = min(max(dist - t, 0), max_len)
    base = (cx + ux * t * 0.82, cy + uy * t * 0.82)
    tipp = (edge[0] + ux * length, edge[1] + uy * length)
    nx, ny = -uy, ux
    return base, tipp, (nx * half_w, ny * half_w), length


def _draw_text(draw: ImageDraw.ImageDraw, m: Measured, box, ink, *, inflate_center: bool = True) -> None:
    f = font("bold" if _SPEC[m.kind][0] == "bold" else "reg", m.font_px)
    lh = int(m.font_px * 1.14)
    cx = (box[0] + box[2]) / 2
    sub_h = (int(m.font_px * 0.8 * 1.14) * len(m.sub_lines) + 8) if m.sub_lines else 0
    total = lh * len(m.lines) + sub_h
    y = (box[1] + box[3]) / 2 - total / 2 + lh / 2
    tx = cx + (12 if m.kind == LetterKind.NAME_CARD else 0)
    for line in m.lines:
        draw.text((tx, y), line, font=f, fill=ink, anchor="mm")
        y += lh
    if m.sub_lines:
        sf = font("reg", int(m.font_px * 0.78))
        y += 4
        for line in m.sub_lines:
            draw.text((tx, y), line, font=sf, fill=(235, 235, 240), anchor="mm")
            y += int(m.font_px * 0.8 * 1.14)


def _spiky(box, seed: int, scale: float = 1.0):
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    a, b = (box[2] - box[0]) / 2 * scale, (box[3] - box[1]) / 2 * scale
    n = max(14, int((a + b) / 26))
    pts = []
    for i in range(2 * n):
        ang = math.pi * i / n
        j = ((zlib.crc32(f"{seed}{i}".encode()) % 100) / 100.0)
        rad = (1.0 + 0.08 * j) if i % 2 == 0 else (0.80 + 0.06 * j)
        pts.append((cx + a * rad * math.cos(ang), cy + b * rad * math.sin(ang)))
    return pts


def draw_letter(
    strip: Image.Image, m: Measured, box: tuple[int, int, int, int], tip: tuple[int, int] | None,
    *, style: StyleTable, layer: LayerStyle, on_dark: bool,
) -> tuple[int, int, int, int]:
    """Paint one placed letter; return its full extent (balloon + tail + glow) for collision and cut checks."""
    s = style.s
    kind = m.kind
    o = max(3, s(5))
    extent = list(box)
    tail = None
    if tip is not None and kind in TAILED:
        tail = _tail_geometry(box, tip, half_w=s(16) if kind != LetterKind.THOUGHT else 0, max_len=s(210))
        if tail[3] > s(24):
            extent = [min(extent[0], tail[1][0]), min(extent[1], tail[1][1]),
                      max(extent[2], tail[1][0]), max(extent[3], tail[1][1])]
        else:
            tail = None
    glow = {LetterKind.MEMORY: s(46), LetterKind.DREAD: s(26), LetterKind.POEM: s(70)}.get(kind, o + 2)
    pad = (glow if kind in (LetterKind.MEMORY, LetterKind.DREAD, LetterKind.POEM) else o) + s(10)
    region = (int(extent[0] - pad), int(extent[1] - pad), int(extent[2] + pad), int(extent[3] + pad))
    lay = _Layer(strip, region)
    d = lay.d
    fill = (255, 255, 255, 255)
    black = (*INK, 255)

    def tail_poly(color, shrink: float = 0.0):
        if not tail:
            return
        base, tipp, nrm, _ = tail
        k = max(1.0 - shrink / max(s(16), 1), 0.25)
        tp = (tipp[0] - (tipp[0] - base[0]) * (shrink * 0.06), tipp[1] - (tipp[1] - base[1]) * (shrink * 0.06))
        d.polygon([lay.p(base[0] + nrm[0] * k, base[1] + nrm[1] * k), lay.p(base[0] - nrm[0] * k, base[1] - nrm[1] * k),
                   lay.p(*tp)], fill=color)

    if kind in (LetterKind.SPEECH, LetterKind.WHISPER, LetterKind.DREAD, LetterKind.POEM):
        r = min((box[3] - box[1]) * 0.46, s(76)) * SS
        if kind == LetterKind.DREAD:
            fz = Image.new("L", lay.img.size, 0)
            ImageDraw.Draw(fz).rounded_rectangle(lay.bx(box, s(13)), r + s(13) * SS, fill=255)
            fz = fz.filter(ImageFilter.GaussianBlur(s(7) * SS)).point(lambda v: min(255, int(v * 1.9)))
            lay.img.paste(Image.new("RGBA", lay.img.size, black), (0, 0), fz)
            d.rounded_rectangle(lay.bx(box, -o * 0.4), r, fill=(236, 236, 238, 255))
            tail_poly(black)
            tail_poly((236, 236, 238, 255), shrink=o * 1.2)
        elif kind == LetterKind.WHISPER:
            d.rounded_rectangle(lay.bx(box), r, fill=fill)
            tail_poly(fill)
            pts = _rr_points(lay.bx(box), r, 14 * SS)
            dash, gap = 16 * SS * style.scale, 11 * SS * style.scale
            acc, on = 0.0, True
            for (x0, y0), (x1, y1) in zip(pts, [*pts[1:], pts[0]], strict=True):
                seg = math.hypot(x1 - x0, y1 - y0)
                acc += seg
                if on:
                    d.line([(x0, y0), (x1, y1)], fill=black, width=max(2, int(s(4) * SS * 0.8)))
                if acc > (dash if on else gap):
                    acc, on = 0.0, not on
            if tail:
                base, tipp, nrm, _ = tail
                d.line([lay.p(base[0] + nrm[0], base[1] + nrm[1]), lay.p(*tipp), lay.p(base[0] - nrm[0], base[1] - nrm[1])],
                       fill=black, width=max(2, int(s(3) * SS)))
        elif kind == LetterKind.POEM:
            d.rounded_rectangle(lay.bx(box), r, fill=(252, 250, 244, 245), outline=(150, 146, 138, 255), width=s(3) * SS)
        else:
            d.rounded_rectangle(lay.bx(box), r, fill=black)
            tail_poly(black)
            d.rounded_rectangle(lay.bx(box, -o), max(r - o * SS, 2), fill=fill)
            tail_poly(fill, shrink=o * 1.2)
    elif kind == LetterKind.SHOUT:
        pts = _spiky(box, zlib.crc32(m.letter.text.encode()))
        pts_in = _spiky(box, zlib.crc32(m.letter.text.encode()), 0.965)
        d.polygon([lay.p(*p) for p in pts], fill=black)
        tail_poly(black)
        d.polygon([lay.p(*p) for p in pts_in], fill=fill)
        tail_poly(fill, shrink=o * 1.2)
    elif kind == LetterKind.THOUGHT:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        a, b = (box[2] - box[0]) / 2, (box[3] - box[1]) / 2
        rb = min(a, b) * 0.34
        n = max(10, int(2 * math.pi * math.sqrt((a * a + b * b) / 2) / (rb * 1.5)))
        centres = [(cx + (a - rb * 0.55) * math.cos(2 * math.pi * i / n), cy + (b - rb * 0.55) * math.sin(2 * math.pi * i / n))
                   for i in range(n)]
        for grow, col in ((o, black), (0, fill)):
            d.ellipse(lay.bx((box[0] + rb * 0.4, box[1] + rb * 0.4, box[2] - rb * 0.4, box[3] - rb * 0.4), grow), fill=col)
            for x, y in centres:
                d.ellipse(lay.bx((x - rb, y - rb, x + rb, y + rb), grow), fill=col)
        if tip is not None:
            dx, dy = tip[0] - cx, tip[1] - cy
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            t = 1.0 / math.sqrt((ux / a) ** 2 + (uy / b) ** 2)
            ln = min(max(dist - t, 0), s(170))
            if ln > s(24):
                for frac, rad in ((0.25, 0.36), (0.58, 0.25), (0.9, 0.16)):
                    px_, py_ = cx + ux * (t + ln * frac), cy + uy * (t + ln * frac)
                    rr = rb * rad * 2
                    for grow, col in ((o, black), (0, fill)):
                        d.ellipse(lay.bx((px_ - rr, py_ - rr, px_ + rr, py_ + rr), grow), fill=col)
                extent = [min(extent[0], cx + ux * (t + ln)), min(extent[1], cy + uy * (t + ln)),
                          max(extent[2], cx + ux * (t + ln)), max(extent[3], cy + uy * (t + ln))]
    elif kind == LetterKind.MEMORY:
        ell = lay.bx(box)
        halo = Image.new("L", lay.img.size, 0)
        hd = ImageDraw.Draw(halo)
        hd.ellipse(ell, outline=255, width=s(14) * SS)
        halo = halo.filter(ImageFilter.GaussianBlur(s(12) * SS))
        lay.img.paste(Image.new("RGBA", lay.img.size, (255, 206, 80, 255)), (0, 0), halo)
        d.ellipse(ell, fill=(255, 255, 255, 235))
        d.ellipse(ell, outline=(255, 214, 96, 255), width=s(7) * SS)
        d.ellipse(lay.bx(box, -s(9)), outline=(255, 240, 190, 200), width=s(3) * SS)
    elif kind == LetterKind.NARRATION:
        d.rectangle(lay.bx(box), fill=(*layer.caption_edge, 255))
        d.rectangle(lay.bx(box, -s(3)), fill=(*layer.caption_fill, 255))
    elif kind == LetterKind.TIME_PLACE:
        card, ink = ((255, 255, 255, 255), black) if on_dark else ((22, 22, 26, 255), (255, 255, 255, 255))
        d.rectangle(lay.bx(box), fill=ink)
        d.rectangle(lay.bx(box, -s(4)), fill=card)
        d.rectangle(lay.bx(box, -s(12)), outline=ink, width=s(2) * SS)
    elif kind == LetterKind.NAME_CARD:
        d.rectangle(lay.bx(box), fill=(18, 22, 40, 245))
        d.rectangle(lay.bx((box[0], box[1], box[0] + s(14), box[3])), fill=(232, 190, 90, 255))
        d.rectangle(lay.bx(box), outline=(232, 190, 90, 255), width=s(3) * SS)
    if kind == LetterKind.POEM:
        wash = Image.new("L", lay.img.size, 0)
        ImageDraw.Draw(wash).rounded_rectangle(lay.bx(box, s(34)), s(60) * SS, fill=170)
        wash = wash.filter(ImageFilter.GaussianBlur(s(26) * SS))
        under = Image.new("RGBA", lay.img.size, (250, 246, 234, 255))
        under.putalpha(wash)
        lay.img = Image.alpha_composite(under, lay.img)
        lay.d = ImageDraw.Draw(lay.img)
    lay.commit()
    td = ImageDraw.Draw(strip)
    ink: tuple[int, int, int]
    if kind == LetterKind.NARRATION:
        ink = layer.caption_ink
    elif kind == LetterKind.TIME_PLACE:
        ink = INK if on_dark else (255, 255, 255)
    elif kind == LetterKind.NAME_CARD:
        ink = (240, 206, 120)
    elif kind in (LetterKind.MEMORY, LetterKind.POEM):
        ink = (70, 52, 20) if kind == LetterKind.MEMORY else (60, 58, 66)
    else:
        ink = INK
    _draw_text(td, m, box, ink)
    return (int(extent[0] - o), int(extent[1] - o), int(extent[2] + o), int(extent[3] + o))


def draw_sfx(strip: Image.Image, m: Measured, xy: tuple[int, int]) -> tuple[int, int, int, int]:
    assert m.sfx is not None
    region = strip.crop((xy[0], xy[1], xy[0] + m.sfx.width, xy[1] + m.sfx.height)).convert("RGBA")
    region.alpha_composite(m.sfx)
    strip.paste(region.convert("RGB"), xy)
    return (xy[0], xy[1], xy[0] + m.sfx.width, xy[1] + m.sfx.height)


# --------------------------------------------------------------------------- placement

Box = tuple[int, int, int, int]


@dataclass
class Placed:
    panel_id: str
    idx: int
    kind: str
    box: Box
    extent: Box
    tail_tip: tuple[int, int] | None
    text: str
    font_px: int


@dataclass
class Overflow:
    panel_id: str
    idx: int
    kind: str
    lost_text: str
    reason: str  # truncated | unplaced


def _integral(a: np.ndarray) -> np.ndarray:
    ii = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    ii[1:, 1:] = a.cumsum(0).cumsum(1)
    return ii


def _sums(ii: np.ndarray, ch: int, cw: int) -> np.ndarray:
    return ii[ch:, cw:] - ii[:-ch, cw:] - ii[ch:, :-cw] + ii[:-ch, :-cw]


class CostMap:
    """Per-cell cost over a panel: salient and skin cells (from `estimate_subject`) plus padded face boxes."""

    def __init__(self, rect: Box, cell: int, weight: np.ndarray | None, faces: list[Box], obstacles: list[Box]):
        self.rect, self.cell = rect, cell
        self.cols = max((rect[2] - rect[0]) // cell, 1)
        self.rows = max((rect[3] - rect[1]) // cell, 1)
        cost = np.zeros((self.rows, self.cols), dtype=np.float32)
        if weight is not None and weight.size:
            im = Image.fromarray((np.clip(weight / 3.0, 0, 1) * 255).astype(np.uint8))
            cost += np.asarray(im.resize((self.cols, self.rows), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
        for f in faces:
            r0, r1, c0, c1 = self._cells(f, cell * 1.5)
            cost[r0:r1, c0:c1] += 8.0
        self.cost = cost
        self.occ = np.zeros((self.rows, self.cols), dtype=np.float32)
        for ob in obstacles:
            self.block(ob, 0)

    def _cells(self, b: Box, pad: float) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = b[0] - self.rect[0] - pad, b[1] - self.rect[1] - pad, b[2] - self.rect[0] + pad, b[3] - self.rect[1] + pad
        c = self.cell
        return (max(math.floor(y0 / c), 0), min(math.ceil(y1 / c), self.rows),
                max(math.floor(x0 / c), 0), min(math.ceil(x1 / c), self.cols))

    def block(self, b: Box, clearance: int) -> None:
        r0, r1, c0, c1 = self._cells(b, clearance)
        self.occ[r0:r1, c0:c1] = 1.0

    def best(self, size: tuple[int, int], align: str | None, margin: int, prev_row: int) -> tuple[int, int] | None:
        c = self.cell
        cw, ch = max(math.ceil(size[0] / c), 1), max(math.ceil(size[1] / c), 1)
        m = max(margin // c, 1)
        if cw + 2 * m > self.cols or ch + 2 * m > self.rows:
            return None
        mean = _sums(_integral(self.cost), ch, cw) / (cw * ch)
        busy = _sums(_integral(self.occ), ch, cw)
        total = mean.copy()
        rows, cols = total.shape
        rr = np.arange(rows)[:, None]
        cc = np.arange(cols)[None, :]
        total += 0.9 * rr / max(rows, 1)
        total += np.where(rr < prev_row - 1, 3.0, 0.0)
        total[busy > 0] = np.inf
        total[:m] = np.inf
        total[max(rows - m, 0):] = np.inf
        total[:, :m] = np.inf
        total[:, max(cols - m, 0):] = np.inf
        if align == "center":
            total = np.where(np.abs(cc - (cols - 1) / 2) <= 1, total, np.inf)
        elif align == "left":
            total = np.where(cc <= m + 1, total, np.inf)
        flat = int(np.argmin(total))
        r, col = divmod(flat, cols)
        if not np.isfinite(total[r, col]):
            return None
        x = self.rect[0] + col * c
        if align == "center":
            x = self.rect[0] + (self.rect[2] - self.rect[0] - size[0]) // 2
        return x, self.rect[1] + r * c


def _nearest_on_box(face: Box, frm: tuple[float, float]) -> tuple[float, float]:
    return (min(max(frm[0], face[0]), face[2]), min(max(frm[1], face[1]), face[3]))


def tail_target(
    box: Box, faces: dict[str, Box], speaker_id: str | None, all_faces: list[Box], centroid: tuple[int, int] | None,
    gap: int,
) -> tuple[int, int] | None:
    """Where a tail points. A known speaker face wins; with exactly one face in the panel it is the speaker; with
    none known but a named speaker, the panel's skin/salience centroid (someone speaks, so a head is somewhere).
    Narrator letters never get a tail."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    face = faces.get(speaker_id) if speaker_id else None
    if face is None and len(all_faces) == 1:
        face = all_faces[0]
    if face is not None:
        px, py = _nearest_on_box(face, (cx, cy))
        fx, fy = (face[0] + face[2]) / 2, (face[1] + face[3]) / 2
        # Stop short of the face centre: the tip touches the head's edge, it does not enter the eyes.
        return int(px + (fx - px) * 0.12), int(py + (fy - py) * 0.12)
    if speaker_id and centroid:
        return centroid
    return None


def place_panel(
    panel_id: str, rect: Box, measured: list[Measured], *, style: StyleTable, layer: LayerStyle,
    weight: np.ndarray | None, faces: dict[str, Box], obstacles: list[Box], centroid: tuple[int, int] | None,
    redo,
) -> tuple[list[tuple[Measured, Box, tuple[int, int] | None]], list[Overflow]]:
    """Choose a box for each letter. `redo(m, scale_down)` re-measures a letter smaller when it finds no room."""
    s = style.s
    cell = max(s(16), 6)
    all_faces = list(faces.values())
    cm = CostMap(rect, cell, weight, all_faces, obstacles)
    out: list[tuple[Measured, Box, tuple[int, int] | None]] = []
    over: list[Overflow] = []
    prev_row = 0
    margin = s(40)
    # Balloons first in reading order, SFX last: sound effects take whatever art the balloons left free.
    order = [m for m in measured if m.kind != LetterKind.SFX] + [m for m in measured if m.kind == LetterKind.SFX]
    for m in order:
        if m.lost:
            over.append(Overflow(panel_id, m.idx, m.kind.value, m.lost, "truncated"))
        pos = None
        cur = m
        for att in (1.0, 0.88, 0.78):
            cur = m if att == 1.0 else redo(m, att)
            align = "center" if cur.kind in CENTRED else ("left" if cur.kind == LetterKind.NAME_CARD else None)
            if cur.kind == LetterKind.SFX:
                pos = cm.best(cur.size, None, s(10), 0)
            else:
                pos = cm.best(cur.size, align, margin, prev_row)
            if pos:
                break
        if pos is None:
            over.append(Overflow(panel_id, m.idx, m.kind.value, m.letter.text, "unplaced"))
            continue
        box = (pos[0], pos[1], pos[0] + cur.size[0], pos[1] + cur.size[1])
        tip = None
        if cur.kind in TAILED:
            tip = tail_target(box, faces, cur.letter.speaker_id, all_faces, centroid, s(24))
        pad = s(46) if cur.kind in TAILED else s(22)
        cm.block((box[0], box[1], box[2], box[3] + (s(90) if tip else 0)), pad)
        if cur.kind != LetterKind.SFX:
            prev_row = max(prev_row, (box[1] - rect[1]) // cell)
        out.append((cur, box, tip))
    return out, over
