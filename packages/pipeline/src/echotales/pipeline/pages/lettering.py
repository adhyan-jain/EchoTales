"""Lettering by code, never by the image model (roadmap M1 step 2).

**Why this exists.** A diffusion model draws text as shapes that look like text, so every word on a
page is set here, from the span types the pipeline already produced: speech bubbles for dialogue
(tail toward the director's `characters[].position`), caption boxes for narration, cloud bubbles for
inner monologue, a jagged bubble for a shouted line, and an optional SFX layer.

**Text is never silently dropped.** Fitting shrinks the font to a floor, then splits one line over
two bubbles, then truncates with an ellipsis; each of those, and any bubble that finds no room, is
returned in `LetterResult.overflow` so the page report says exactly what did not make it.

Placement is greedy and only avoids other bubbles: it cannot see where a face is, so a reviewer
still checks pages (the plan's "Opus reviews every page").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from echotales.pipeline.compositor.manga import render_onomatopoeia_overlay
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
#: Comic Neue (dialogue) and Bangers (shouts), both OFL. When a file is absent Pillow's built-in
#: scalable font is used, so lettering still works; the pages just look plainer.
DIALOGUE_FONT = FONT_DIR / "ComicNeue-Regular.ttf"
SHOUT_FONT = FONT_DIR / "Bangers-Regular.ttf"

INK = (20, 20, 20)
PAPER = (255, 255, 255)
CAPTION = (255, 246, 205)
#: Placement keeps this many pixels between two bubbles so tails and outlines never touch.
CLEARANCE = 6
#: Elliptical and jagged shapes need more room than their text block to keep text inside the outline.
INFLATE = {"speech": 1.0, "narration": 1.0, "thought": 1.3, "shout": 1.3}


class LetterKind(StrEnum):
    SPEECH = "SPEECH"
    NARRATION = "NARRATION"
    THOUGHT = "THOUGHT"
    SFX = "SFX"


@dataclass(frozen=True, slots=True)
class LetterItem:
    span_id: str
    kind: LetterKind
    text: str
    #: The speaker's `characters[].position` in the panel ("left", "right", ...), or None when unknown.
    speaker_position: str | None = None
    shouted: bool = False


@dataclass(frozen=True, slots=True)
class PlacedLetter:
    span_id: str
    style: str
    #: (x0, y0, x1, y1) in the coordinates of the image drawn on.
    box: tuple[int, int, int, int]
    tail_tip: tuple[int, int] | None
    #: The text actually drawn (a split part, or a truncated line ending in an ellipsis).
    text: str
    font_size: int


@dataclass(frozen=True, slots=True)
class Overflow:
    span_id: str
    #: split: kept in two bubbles. truncated: words lost. unplaced: no room left in the panel.
    kind: str
    lost_text: str = ""


@dataclass(slots=True)
class LetterResult:
    placed: list[PlacedLetter] = field(default_factory=list)
    overflow: list[Overflow] = field(default_factory=list)


# --------------------------------------------------------------------------- text fitting


@lru_cache(maxsize=64)
def _font(shout: bool, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = SHOUT_FONT if shout else DIALOGUE_FONT
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _wrap(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_w: float) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        # A single word wider than the bubble (a long cry, a URL) is broken by character, or it would
        # overflow whatever box was chosen for the rest.
        while font.getlength(word) > max_w and len(word) > 1:
            cut = len(word) - 1
            while cut > 1 and font.getlength(word[:cut]) > max_w:
                cut -= 1
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:cut])
            word = word[cut:]
        trial = f"{cur} {word}".strip()
        if cur and font.getlength(trial) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


@dataclass(slots=True)
class _Fit:
    lines: list[str]
    size: int
    w: int
    h: int


def _fit(text: str, style: str, max_w: float, max_h: float, base: int, floor: int) -> _Fit | None:
    shout = style == "shout"
    infl = INFLATE[style]
    for size in range(base, floor - 1, -1):
        font = _font(shout, size)
        pad = size * 0.6
        lines = _wrap(text, font, max_w / infl - 2 * pad)
        lh = size * 1.15
        h = len(lines) * lh + 2 * pad
        w = max((font.getlength(line) for line in lines), default=0) + 2 * pad
        if h * infl <= max_h and w * infl <= max_w + 1:
            return _Fit(lines, size, math.ceil(w * infl), math.ceil(h * infl))
    return None


def _truncate(words: list[str], style: str, max_w: float, max_h: float, base: int, floor: int) -> tuple[str, _Fit, str] | None:
    """The longest word prefix that fits with an ellipsis; its fit and the words that were cut."""
    lo, hi = 1, len(words)
    best: tuple[str, _Fit, str] | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        text = " ".join(words[:mid]) + "…"
        fit = _fit(text, style, max_w, max_h, base, floor)
        if fit is not None:
            best = (text, fit, " ".join(words[mid:]))
            lo = mid + 1
        else:
            hi = mid - 1
    return best


# --------------------------------------------------------------------------- geometry

_ANCHOR_X = {"left": 0.25, "right": 0.75}
_ANCHOR_Y = {"foreground": 0.85, "background": 0.55}


def _anchor(position: str | None, rect: tuple[int, int, int, int]) -> tuple[int, int]:
    """Where the speaker is in the panel; the centre when the director did not say."""
    x, y, w, h = rect
    pos = (position or "").lower()
    fx = next((v for k, v in _ANCHOR_X.items() if k in pos), 0.5)
    fy = next((v for k, v in _ANCHOR_Y.items() if k in pos), 0.72)
    return round(x + w * fx), round(y + h * fy)


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] + CLEARANCE <= b[0] or b[2] + CLEARANCE <= a[0] or a[3] + CLEARANCE <= b[1] or b[3] + CLEARANCE <= a[1])


def _find_spot(
    bw: int, bh: int, rect: tuple[int, int, int, int], taken: list[tuple[int, int, int, int]], anchor_x: int
) -> tuple[int, int] | None:
    rx, ry, rw, rh = rect
    edge = 8
    ystep = max(4, round(rh * 0.03))
    xstep = max(4, round(rw * 0.03))
    xs = list(range(rx + edge, rx + rw - bw - edge + 1, xstep))
    xs.sort(key=lambda x: (abs(x + bw / 2 - anchor_x), x))
    for y in range(ry + edge, ry + rh - bh - edge + 1, ystep):
        for x in xs:
            if not any(_overlaps((x, y, x + bw, y + bh), t) for t in taken):
                return x, y
    return None


# --------------------------------------------------------------------------- drawing


def _tail(box: tuple[int, int, int, int], anchor: tuple[int, int], rect: tuple[int, int, int, int], size: int):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    below = anchor[1] > cy
    by = y1 if below else y0
    bx = min(max(cx + 0.45 * (anchor[0] - cx), x0 + (x1 - x0) * 0.2), x1 - (x1 - x0) * 0.2)
    dx, dy = anchor[0] - bx, anchor[1] - by
    dist = math.hypot(dx, dy) or 1.0
    length = min(dist, max(rect[3] * 0.3, size * 2))
    tip = (round(bx + dx / dist * length), round(by + dy / dist * length))
    tip = (min(max(tip[0], rect[0]), rect[0] + rect[2]), min(max(tip[1], rect[1]), rect[1] + rect[3]))
    half = max(4, size * 0.4)
    return (bx, by), half, tip


def _draw_body(draw: ImageDraw.ImageDraw, style: str, box: tuple[int, int, int, int], size: int) -> None:
    x0, y0, x1, y1 = box
    if style == "narration":
        draw.rectangle(box, fill=CAPTION, outline=INK, width=2)
    elif style == "speech":
        draw.rounded_rectangle(box, radius=min((y1 - y0) // 2, size * 1.2), fill=PAPER, outline=INK, width=3)
    elif style == "thought":
        r = max(4, round(min(x1 - x0, y1 - y0) * 0.1))
        ex0, ey0, ex1, ey1 = x0 + r, y0 + r, x1 - r, y1 - r
        cx, cy, rx, ry = (ex0 + ex1) / 2, (ey0 + ey1) / 2, (ex1 - ex0) / 2, (ey1 - ey0) / 2
        for k in range(16):
            a = k * math.tau / 16
            px, py = cx + rx * math.cos(a), cy + ry * math.sin(a)
            draw.ellipse((px - r, py - r, px + r, py + r), fill=PAPER, outline=INK, width=2)
        draw.ellipse((ex0, ey0, ex1, ey1), fill=PAPER)
    else:  # shout: alternating radii give the jagged outline a deterministic spike count
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        pts = []
        for k in range(24):
            f = 1.0 if k % 2 == 0 else 0.8
            a = k * math.tau / 24
            pts.append((cx + rx * f * math.cos(a), cy + ry * f * math.sin(a)))
        draw.polygon(pts, fill=PAPER, outline=INK, width=3)


def _draw_tail(draw: ImageDraw.ImageDraw, style: str, base: tuple[float, float], half: float, tip: tuple[int, int]) -> None:
    if style == "thought":
        for k, f in enumerate((0.3, 0.55, 0.8)):
            r = max(2, half * (0.9 - 0.25 * k))
            px, py = base[0] + (tip[0] - base[0]) * f, base[1] + (tip[1] - base[1]) * f
            draw.ellipse((px - r, py - r, px + r, py + r), fill=PAPER, outline=INK, width=2)
        return
    draw.polygon([(base[0] - half, base[1]), (base[0] + half, base[1]), tip], fill=PAPER, outline=INK)


def _style_of(item: LetterItem) -> str:
    if item.kind is LetterKind.SPEECH:
        return "shout" if item.shouted else "speech"
    return {LetterKind.NARRATION: "narration", LetterKind.THOUGHT: "thought", LetterKind.SFX: "sfx"}[item.kind]


def _sfx(img: Image.Image, rect: tuple[int, int, int, int], item: LetterItem) -> PlacedLetter:
    """Reuses the manga SFX overlay (`compositor/manga.py`) so one look serves video and pages."""
    x, y, w, h = rect
    size = max(24, round(min(w, h) * 0.22))
    overlay = render_onomatopoeia_overlay(item.text, w, h, position=(w // 2, h // 2), font_size=size)
    img.paste(overlay.convert("RGB"), (x, y), overlay)
    bb = overlay.getbbox() or (0, 0, w, h)
    return PlacedLetter(item.span_id, "sfx", (x + bb[0], y + bb[1], x + bb[2], y + bb[3]), None, item.text, size)


def letter_panel(
    img: Image.Image, rect: tuple[int, int, int, int], items: list[LetterItem], *, rtl: bool
) -> LetterResult:
    """Draw `items` into `img` inside `rect` (x, y, w, h), in order. Mutates `img`."""
    result = LetterResult()
    rx, ry, rw, rh = rect
    base = min(max(round(min(rh * 0.055, rw * 0.065)), 12), 40)
    floor = max(9, round(base * 0.65))
    draw = ImageDraw.Draw(img)
    taken: list[tuple[int, int, int, int]] = []

    for item in items:
        style = _style_of(item)
        if style == "sfx":
            placed = _sfx(img, rect, item)
            result.placed.append(placed)
            taken.append(placed.box)
            continue
        max_w = rw * (0.9 if style == "narration" else 0.62)
        max_h = rh * 0.4
        pieces: list[tuple[str, _Fit]] = []
        fit = _fit(item.text, style, max_w, max_h, base, floor)
        if fit is not None:
            pieces.append((item.text, fit))
        else:
            words = item.text.split()
            half = len(words) // 2
            parts = [" ".join(words[:half]), " ".join(words[half:])] if half else [item.text]
            fits = [_fit(p, style, max_w, max_h, base, floor) for p in parts]
            if len(parts) == 2 and all(fits):
                pieces = [(p, f) for p, f in zip(parts, fits, strict=True) if f is not None]
                result.overflow.append(Overflow(item.span_id, "split"))
            elif (cut := _truncate(words, style, max_w, max_h, base, floor)) is not None:
                pieces = [(cut[0], cut[1])]
                result.overflow.append(Overflow(item.span_id, "truncated", cut[2]))
            else:
                result.overflow.append(Overflow(item.span_id, "unplaced", item.text))
                continue

        for text, f in pieces:
            anchor = _anchor(item.speaker_position, rect)
            start_x = rx + 8 if not rtl else rx + rw - f.w - 8
            spot = _find_spot(f.w, f.h, rect, taken, anchor[0] if style != "narration" else start_x + f.w // 2)
            if spot is None:
                result.overflow.append(Overflow(item.span_id, "unplaced", text))
                continue
            box = (spot[0], spot[1], spot[0] + f.w, spot[1] + f.h)
            tip = None
            if style != "narration":
                base_pt, half, tip = _tail(box, anchor, rect, f.size)
                _draw_tail(draw, style, base_pt, half, tip)
            _draw_body(draw, style, box, f.size)
            if style in ("speech", "shout") and tip is not None:
                # Paint over the outline where the tail joins the body so they read as one shape.
                draw.polygon(
                    [(base_pt[0] - half + 2, base_pt[1]), (base_pt[0] + half - 2, base_pt[1]),
                     (base_pt[0] + (tip[0] - base_pt[0]) * 0.2, base_pt[1] + (tip[1] - base_pt[1]) * 0.2)],
                    fill=PAPER,
                )
            font = _font(style == "shout", f.size)
            lh = f.size * 1.15
            ty = (box[1] + box[3]) / 2 - len(f.lines) * lh / 2
            for k, line in enumerate(f.lines):
                lw = font.getlength(line)
                draw.text(((box[0] + box[2]) / 2 - lw / 2, ty + k * lh), line, fill=INK, font=font)
            result.placed.append(PlacedLetter(item.span_id, style, box, tip, text, f.size))
            taken.append(box)
    return result
