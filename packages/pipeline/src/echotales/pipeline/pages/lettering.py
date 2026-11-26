"""Lettering by code, never by the image model (roadmap M1 step 2; placement and style reworked in 4.185).

**Why this exists.** A diffusion model draws text as shapes that look like text, so every word on a
page is set here, from the span types the pipeline already produced: rounded speech bubbles for dialogue
(tail toward the speaker's face), muted rectangular captions for narration, cloud bubbles for inner
monologue, a spiky bold bubble for a shouted line, and an optional SFX layer.

**Bubbles do not cover the picture.** Each bubble goes to the lowest-cost spot of a cheap subject estimate
read from the panel's own pixels (`placement.py`). When the panel has no clear spot big enough and the
caller reserved a strip of gutter below it (webtoon), the bubble moves into the gutter instead of
shrinking the font: legibility is a floor (`MIN_FONT_PX`), not something to trade for fit.

**Text is never silently dropped.** Fitting shrinks the font to that floor, then splits one line over
two bubbles, then truncates with an ellipsis; each of those, and any bubble that finds no room, is
returned in `LetterResult.overflow` so the page report says exactly what did not make it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from echotales.pipeline.compositor.manga import (
    render_onomatopoeia_overlay,
)
from echotales.pipeline.pages.placement import (
    SPILL_LIMIT,
    SubjectMap,
    estimate_subject,
    find_clear_spot,
    find_gutter_spot,
    speaker_point,
)
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
#: Liberation Sans (SIL OFL 1.1, licence file beside the fonts): a clean sans that stays readable at webtoon
#: size. Bangers/Comic Neue, which this module once named, were never bundled, so every page had been set
#: in Pillow's built-in font. When a file is absent Pillow's scalable font is still used.
DIALOGUE_FONT = FONT_DIR / "LiberationSans-Regular.ttf"
SHOUT_FONT = FONT_DIR / "LiberationSans-Bold.ttf"

INK = (20, 20, 20)
PAPER = (255, 255, 255)
#: Narration boxes are quieter than speech so the eye reads them as the narrator, not a character.
CAPTION = (236, 233, 224)
CAPTION_INK = (70, 66, 60)
CAPTION_EDGE = (120, 115, 105)
#: Placement keeps this many pixels between two bubbles so tails and outlines never touch.
CLEARANCE = 6
#: Smallest font a page may use at its export size (800 px webtoon, 1200 px page). Below this a phone
#: reader cannot read the line; 4.185 reports the measured minimum per book.
MIN_FONT_PX = 22
#: Panels narrower than this are test fixtures or thumbnails; the legibility floor does not apply to them.
LEGIBLE_PANEL_MIN_W = 480
#: Tallest gutter bubble stack allowed for one bubble. A constant, not the strip's height, so the dry run
#: that measures the strip and the real run that draws in it fit text identically.
GUTTER_MAX_H = 300
#: Elliptical and jagged shapes need more room than their text block to keep text inside the outline.
INFLATE = {
    "speech": 1.0,
    "narration": 1.0,
    "thought": 1.3,
    "shout": 1.3,
    "memory": 1.1,
    "flashback": 1.0,
    "time_skip": 1.0,
    "poetry": 1.2,
    "system_interface": 1.0,
    "crowd_collective": 1.3,
}


class LetterKind(StrEnum):
    SPEECH = "SPEECH"
    NARRATION = "NARRATION"
    THOUGHT = "THOUGHT"
    SFX = "SFX"
    SHOUT = "SHOUT"
    MEMORY = "MEMORY"
    FLASHBACK = "FLASHBACK"
    TIME_SKIP = "TIME_SKIP"
    POETRY = "POETRY"
    SYSTEM_INTERFACE = "SYSTEM_INTERFACE"
    CROWD_COLLECTIVE = "CROWD_COLLECTIVE"


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
    #: True when the bubble sits in the gutter strip below the panel instead of on the picture.
    in_gutter: bool = False


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
    #: Pixels of gutter below the panel the gutter bubbles needed (0 when none). The webtoon builder runs
    #: the lettering once with a generous strip to read this, then lays the strip out at exactly that size.
    gutter_used: int = 0


# --------------------------------------------------------------------------- text fitting


@lru_cache(maxsize=64)
def _font(shout: bool, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = SHOUT_FONT if shout else DIALOGUE_FONT
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size=size)


def sentence_case(text: str) -> str:
    """Novels print shouts in capitals; manhwa letter them in sentence case with a bold face, so the weight
    carries the volume and the line stays readable. Only fully capitalised text is touched."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 4 or not all(c.isupper() for c in letters):
        return text
    out, start = [], True
    for ch in text.lower():
        out.append(ch.upper() if start and ch.isalpha() else ch)
        if ch.isalpha():
            start = False
        elif ch in ".!?":
            start = True
    return "".join(out).replace(" i ", " I ").replace(" i'", " I'")


def _greedy(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_w: float) -> list[str]:
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


def _wrap(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_w: float) -> list[str]:
    """Greedy wrap, then the narrowest width that keeps the same line count. Greedy alone leaves a one-word
    last line under a full-width first line; centred, that reads as a typo in a bubble. Balanced lines are
    what manhwa lettering looks like, and a narrower block also covers less picture."""
    lines = _greedy(text, font, max_w)
    n = len(lines)
    if n < 2:
        return lines
    lo, hi = max(font.getlength(w) for w in text.split()), max_w
    for _ in range(12):
        mid = (lo + hi) / 2
        if len(_greedy(text, font, mid)) <= n:
            hi = mid
        else:
            lo = mid
    return _greedy(text, font, hi)


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
        lh = size * 1.2
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
    """Where the speaker is in the panel when the picture shows no face there; the centre when the
    director did not say either."""
    x, y, w, h = rect
    pos = (position or "").lower()
    fx = next((v for k, v in _ANCHOR_X.items() if k in pos), 0.5)
    fy = next((v for k, v in _ANCHOR_Y.items() if k in pos), 0.72)
    return round(x + w * fx), round(y + h * fy)


# --------------------------------------------------------------------------- drawing


def _tail(
    box: tuple[int, int, int, int], anchor: tuple[int, int], rect: tuple[int, int, int, int], size: int, stop: int
) -> tuple[tuple[float, float], float, tuple[int, int]]:
    """Tail base on the bubble edge facing the speaker, and a tip that stops `stop` px short of the
    speaker's face so the tail points at the head without covering it."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    below = anchor[1] > cy
    by = y1 if below else y0
    bx = min(max(cx + 0.45 * (anchor[0] - cx), x0 + (x1 - x0) * 0.2), x1 - (x1 - x0) * 0.2)
    dx, dy = anchor[0] - bx, anchor[1] - by
    dist = math.hypot(dx, dy) or 1.0
    length = max(min(dist - stop, max(rect[3] * 0.3, size * 2)), min(dist, size * 1.2))
    tip = (round(bx + dx / dist * length), round(by + dy / dist * length))
    tip = (min(max(tip[0], rect[0]), rect[0] + rect[2]), min(max(tip[1], rect[1]), rect[1] + rect[3]))
    half = max(4, size * 0.32)
    return (bx, by), half, tip


def _draw_body(draw: ImageDraw.ImageDraw, style: str, box: tuple[int, int, int, int], size: int) -> None:
    x0, y0, x1, y1 = box
    if style == "narration":
        draw.rectangle(box, fill=CAPTION, outline=CAPTION_EDGE, width=2)
    elif style == "speech":
        draw.rounded_rectangle(box, radius=min((y1 - y0) // 2, size * 1.6), fill=PAPER, outline=INK, width=2)
    elif style == "thought":
        r = max(4, round(min(x1 - x0, y1 - y0) * 0.1))
        ex0, ey0, ex1, ey1 = x0 + r, y0 + r, x1 - r, y1 - r
        cx, cy, rx, ry = (ex0 + ex1) / 2, (ey0 + ey1) / 2, (ex1 - ex0) / 2, (ey1 - ey0) / 2
        for k in range(18):
            a = k * math.tau / 18
            px, py = cx + rx * math.cos(a), cy + ry * math.sin(a)
            draw.ellipse((px - r, py - r, px + r, py + r), fill=PAPER, outline=INK, width=2)
        draw.ellipse((ex0, ey0, ex1, ey1), fill=PAPER)
    elif style == "memory":
        draw.rounded_rectangle(box, radius=min((y1 - y0) // 2, size * 1.4), fill=(253, 250, 240), outline=(217, 160, 40), width=3)
    elif style == "flashback":
        draw.rectangle(box, fill=(24, 24, 27), outline=(113, 113, 122), width=2)
    elif style == "time_skip":
        draw.rounded_rectangle(box, radius=4, fill=(244, 244, 245), outline=(82, 82, 91), width=1)
    elif style == "poetry":
        draw.rounded_rectangle(box, radius=min((y1 - y0) // 2, size * 1.8), fill=(248, 245, 238), outline=(180, 165, 145), width=2)
    elif style == "system_interface":
        draw.rectangle(box, fill=(15, 23, 42), outline=(56, 189, 248), width=2)
    elif style == "crowd_collective":
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        pts = []
        for k in range(20):
            f = 1.0 if k % 2 == 0 else 0.88
            a = k * math.tau / 20
            pts.append((cx + rx * f * math.cos(a), cy + ry * f * math.sin(a)))
        draw.polygon(pts, fill=PAPER, outline=INK, width=2)
    else:  # shout: alternating radii give the jagged outline a deterministic spike count
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        pts = []
        for k in range(28):
            f = 1.0 if k % 2 == 0 else 0.84
            a = k * math.tau / 28
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
    mapping = {
        LetterKind.NARRATION: "narration",
        LetterKind.THOUGHT: "thought",
        LetterKind.SFX: "sfx",
        LetterKind.SHOUT: "shout",
        LetterKind.MEMORY: "memory",
        LetterKind.FLASHBACK: "flashback",
        LetterKind.TIME_SKIP: "time_skip",
        LetterKind.POETRY: "poetry",
        LetterKind.SYSTEM_INTERFACE: "system_interface",
        LetterKind.CROWD_COLLECTIVE: "crowd_collective",
    }
    return mapping.get(item.kind, "speech")


def _sfx(img: Image.Image, rect: tuple[int, int, int, int], item: LetterItem) -> PlacedLetter:
    """Reuses the manga SFX overlay (`compositor/manga.py`) so one look serves video and pages."""
    x, y, w, h = rect
    size = max(24, round(min(w, h) * 0.22))
    overlay = render_onomatopoeia_overlay(item.text, w, h, position=(w // 2, h // 2), font_size=size)
    img.paste(overlay.convert("RGB"), (x, y), overlay)
    bb = overlay.getbbox() or (0, 0, w, h)
    return PlacedLetter(item.span_id, "sfx", (x + bb[0], y + bb[1], x + bb[2], y + bb[3]), None, item.text, size)


def _pieces(
    text: str, style: str, max_w: float, max_h: float, base: int, floor: int, span_id: str, overflow: list[Overflow]
) -> list[tuple[str, _Fit]]:
    """The text as one bubble, two bubbles, or a truncated bubble, recording which in `overflow`."""
    fit = _fit(text, style, max_w, max_h, base, floor)
    if fit is not None:
        return [(text, fit)]
    words = text.split()
    half = len(words) // 2
    parts = [" ".join(words[:half]), " ".join(words[half:])] if half else [text]
    fits = [_fit(p, style, max_w, max_h, base, floor) for p in parts]
    if len(parts) == 2 and all(fits):
        overflow.append(Overflow(span_id, "split"))
        return [(p, f) for p, f in zip(parts, fits, strict=True) if f is not None]
    if (cut := _truncate(words, style, max_w, max_h, base, floor)) is not None:
        overflow.append(Overflow(span_id, "truncated", cut[2]))
        return [(cut[0], cut[1])]
    return []


def letter_panel(
    img: Image.Image,
    rect: tuple[int, int, int, int],
    items: list[LetterItem],
    *,
    rtl: bool,
    subject: SubjectMap | None = None,
    gutter_below: int = 0,
) -> LetterResult:
    """Draw `items` into `img` inside `rect` (x, y, w, h), in order. Mutates `img`.

    `subject` is the panel's subject estimate (taken from the pixels under `rect` when not given).
    `gutter_below` is how many pixels of free page lie under the panel; a bubble with no clear spot on the
    picture goes there. 0 keeps every bubble on the picture, at the least harmful spot."""
    result = LetterResult()
    rx, ry, rw, rh = rect
    if subject is None:
        subject = estimate_subject(img.crop((rx, ry, rx + rw, ry + rh)))
    base = min(max(round(min(rh * 0.055, rw * 0.065)), 12), 40)
    floor = max(9, round(base * 0.65))
    if rw >= LEGIBLE_PANEL_MIN_W:
        floor = max(floor, MIN_FONT_PX)
        base = max(base, floor)
    draw = ImageDraw.Draw(img)
    taken: list[tuple[int, int, int, int]] = []
    gutter_pad = 14
    stop = round(min(rw, rh) * 0.09)

    for item in items:
        style = _style_of(item)
        if style == "sfx":
            placed = _sfx(img, rect, item)
            result.placed.append(placed)
            taken.append(placed.box)
            continue
        text = sentence_case(item.text)
        max_w = rw * (0.9 if style == "narration" else 0.62)
        # Captions are the quiet voice: a notch smaller than speech, never below the legibility floor.
        sbase = max(floor, round(base * 0.82)) if style == "narration" else base
        pieces = _pieces(text, style, max_w, rh * 0.4, sbase, floor, item.span_id, result.overflow)
        force_gutter = False
        if not pieces:
            if gutter_below > 0:
                # No legible fit on the picture: the gutter is wider and taller, so the same text fits there.
                pieces = _pieces(text, style, rw * 0.92, GUTTER_MAX_H, sbase, floor, item.span_id, result.overflow)
                force_gutter = bool(pieces)
            if not pieces:
                result.overflow.append(Overflow(item.span_id, "unplaced", text))
                continue

        face = speaker_point(subject, rect, item.speaker_position)
        anchor = face or _anchor(item.speaker_position, rect)
        for text_piece, f in pieces:
            pull = ((rx + rw - 8) if rtl else (rx + 8), ry) if style == "narration" else anchor
            spot = None if force_gutter else find_clear_spot(f.w, f.h, rect, subject, taken, pull, CLEARANCE)
            if gutter_below > 0 and (spot is None or spot.spill > SPILL_LIMIT):
                gf = f if force_gutter else _fit(text_piece, style, rw * 0.92, GUTTER_MAX_H, sbase, floor)
                g = (
                    find_gutter_spot(gf.w, gf.h, rect, taken, pull[0], CLEARANCE, avail=gutter_below, pad=gutter_pad)
                    if gf is not None
                    else None
                )
                if g is not None and gf is not None:
                    spot, f = g, gf
            if spot is None:
                result.overflow.append(Overflow(item.span_id, "unplaced", text_piece))
                continue
            box = (spot.x, spot.y, spot.x + f.w, spot.y + f.h)
            tip = None
            if style != "narration":
                tail_anchor = anchor
                if spot.in_gutter:
                    # Up into the picture only far enough to point at the speaker's side of it.
                    tail_anchor = (anchor[0], ry + rh - min(round(rh * 0.14), 60))
                base_pt, half, tip = _tail(box, tail_anchor, rect, f.size, 0 if spot.in_gutter else stop)
                _draw_tail(draw, style, base_pt, half, tip)
            _draw_body(draw, style, box, f.size)
            if style in ("speech", "shout") and tip is not None:
                # Paint over the outline where the tail joins the body so they read as one shape.
                sgn = 1 if base_pt[1] >= (box[1] + box[3]) / 2 else -1
                draw.polygon(
                    [(base_pt[0] - half + 2, base_pt[1] - sgn), (base_pt[0] + half - 2, base_pt[1] - sgn),
                     (base_pt[0] + (tip[0] - base_pt[0]) * 0.2, base_pt[1] + (tip[1] - base_pt[1]) * 0.2)],
                    fill=PAPER,
                )
            font = _font(style == "shout", f.size)
            lh = f.size * 1.2
            ty = (box[1] + box[3]) / 2 - len(f.lines) * lh / 2
            if style in ("flashback", "system_interface"):
                ink = (248, 250, 252)
            elif style == "narration":
                ink = CAPTION_INK
            elif style == "poetry":
                ink = (60, 50, 40)
            else:
                ink = INK
            for k, line in enumerate(f.lines):
                lw = font.getlength(line)
                draw.text(((box[0] + box[2]) / 2 - lw / 2, ty + k * lh), line, fill=ink, font=font)
            result.placed.append(PlacedLetter(item.span_id, style, box, tip, text_piece, f.size, spot.in_gutter))
            taken.append(box)
            if spot.in_gutter:
                result.gutter_used = max(result.gutter_used, box[3] + gutter_pad - (ry + rh))
    return result
