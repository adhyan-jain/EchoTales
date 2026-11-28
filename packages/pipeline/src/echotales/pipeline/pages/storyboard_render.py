"""Render a `Storyboard` as a vertical-scroll webtoon chapter with the grammar real manhwa use.

Why this exists: `echotales pages --format webtoon` stacks same-size panels with plain balloons. The reference
chapters (docs/results/MANHWA_DIRECTING_PATTERNS.md) carry rhythm in panel shape, gutter length and colour, and
meaning in the balloon kind and an image grade per narrative layer. The director already decides all of that
(`storyboard/schema.py`); this module only draws it, so a different novel changes the `StyleTable`, not the code.

Pipeline: measure letters -> size and place panels -> paint gutter background -> paint shaped, graded pictures ->
letter (balloons by cost-map search, SFX into the art) -> cut into slices without crossing a balloon.
"""

from __future__ import annotations

import itertools
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from echotales.pipeline.pages import grammar_lettering as gl
from echotales.pipeline.pages.export import export_pages
from echotales.pipeline.pages.placement import estimate_subject
from echotales.pipeline.pages.storyboard_style import DEFAULT_STYLE, StyleTable
from echotales.pipeline.storyboard.schema import LetterKind, Panel, Purpose, Shape, Storyboard
from PIL import Image, ImageDraw, ImageFile, ImageFilter

ImageFile.LOAD_TRUNCATED_IMAGES = True

#: Normalised (x0, y0, x1, y1) face box in the SOURCE image, keyed panel_id -> speaker_id (or any label).
FaceBoxes = Mapping[str, Mapping[str, tuple[float, float, float, float]]]


@dataclass
class PlacedPanel:
    panel_id: str
    rect: gl.Box
    shape: str
    layer: str


@dataclass
class StripResult:
    strip: Image.Image
    panels: list[PlacedPanel] = field(default_factory=list)
    placed: list[gl.Placed] = field(default_factory=list)
    overflow: list[gl.Overflow] = field(default_factory=list)
    gutters: list[tuple[int, int]] = field(default_factory=list)
    cuts: list[int] = field(default_factory=list)


# --------------------------------------------------------------------------- image grades


def _arr(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.float32)


def _img(a: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _desat(a: np.ndarray, k: float) -> np.ndarray:
    g = (a @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[..., None]
    return g + (a - g) * (1.0 - k)


def _vignette(h: int, w: int, strength: float) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    return (np.clip((d - 0.55) / 0.85, 0, 1) ** 1.6 * strength)[..., None]


def _bloom(a: np.ndarray, amount: float) -> np.ndarray:
    bright = np.clip(a - 150, 0, None)
    blur = np.asarray(_img(np.clip(bright * 2, 0, 255)).filter(ImageFilter.GaussianBlur(max(a.shape[1] // 40, 3))), dtype=np.float32)
    return a + blur * amount


def grade_memory(img: Image.Image) -> Image.Image:
    a = _desat(_arr(img), 0.55)
    a = a * 0.65 + a * np.array([255, 226, 150], dtype=np.float32) / 255 * 0.35 + 14
    a = _bloom(a, 0.35)
    v = _vignette(a.shape[0], a.shape[1], 0.7)
    return _img(a * (1 - v) + np.array([255, 240, 205], dtype=np.float32) * v)


def grade_past(img: Image.Image) -> Image.Image:
    a = _desat(_arr(img), 0.22)
    return _img(a * 0.94 + np.array([255, 236, 210], dtype=np.float32) * 0.06)


def grade_imagined(img: Image.Image) -> Image.Image:
    a = _desat(_arr(img), 0.25)
    a = a * 0.78 + np.array([190, 215, 255], dtype=np.float32) * 0.22
    a = _bloom(a, 0.25)
    v = _vignette(a.shape[0], a.shape[1], 0.55)
    return _img(a * (1 - v) + np.array([200, 225, 255], dtype=np.float32) * v)


def grade_lore(img: Image.Image) -> Image.Image:
    g = _desat(_arr(img), 1.0)
    g = np.clip((g - 128) * 1.25 + 128, 0, 255)
    return _img(g * (np.array([236, 222, 190], dtype=np.float32) / 255))


def grade_dream(img: Image.Image) -> Image.Image:
    a = _desat(_arr(img), 0.2)
    a = a * 0.8 + np.array([225, 200, 255], dtype=np.float32) * 0.2
    return _img(_bloom(a, 0.4))


GRADES = {"none": lambda i: i, "memory": grade_memory, "past": grade_past, "imagined": grade_imagined,
          "lore": grade_lore, "dream": grade_dream}


# --------------------------------------------------------------------------- pictures


def _placeholder(w: int, h: int, panel: Panel) -> Image.Image:
    """A stand-in for a panel with no picture yet: tinted gradient with a skin-coloured head, so layout (and
    the cost map's face avoidance) can be tested before any render exists."""
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    base = np.array([70, 80, 120], dtype=np.float32) if panel.layer.value != "present" else np.array([90, 40, 60], dtype=np.float32)
    a = np.broadcast_to(base * (0.6 + 0.6 * yy), (h, w, 3)).copy()
    im = _img(a)
    d = ImageDraw.Draw(im)
    r = int(min(w, h) * 0.17)
    cx, cy = w // 2, int(h * 0.45)
    d.ellipse((cx - r, cy - int(r * 1.25), cx + r, cy + int(r * 1.25)), fill=(224, 180, 150))
    d.text((12, 12), f"{panel.panel_id} {panel.shape.value}", fill=(255, 255, 255))
    return im


def _fit(img: Image.Image, size: tuple[int, int], focus: tuple[float, float] | None) -> tuple[Image.Image, float, tuple[int, int]]:
    """Cover-fit with the crop window centred on `focus` (normalised source coords). Returns the crop and the
    (scale, offset) that maps source px to panel px, so face boxes can follow the crop."""
    w, h = size
    s = max(w / img.width, h / img.height)
    big = img.resize((max(round(img.width * s), w), max(round(img.height * s), h)), Image.Resampling.LANCZOS)
    fx, fy = focus if focus else (0.5, 0.5)
    ox = int(min(max(fx * big.width - w / 2, 0), big.width - w))
    oy = int(min(max(fy * big.height - h * 0.42, 0), big.height - h))
    return big.crop((ox, oy, ox + w, oy + h)), s, (ox, oy)


def _focus_of(img: Image.Image, face_boxes: Mapping[str, tuple[float, float, float, float]] | None) -> tuple[float, float]:
    if face_boxes:
        bs = list(face_boxes.values())
        return (sum((b[0] + b[2]) / 2 for b in bs) / len(bs), sum((b[1] + b[3]) / 2 for b in bs) / len(bs))
    small = img.convert("RGB")
    small.thumbnail((160, 160))
    smap = estimate_subject(small)
    wt = smap.weight
    if wt.sum() <= 0:
        return (0.5, 0.5)
    ys, xs = np.mgrid[0:wt.shape[0], 0:wt.shape[1]]
    return (float((xs * wt).sum() / wt.sum() / wt.shape[1]), float((ys * wt).sum() / wt.sum() / wt.shape[0]))


# --------------------------------------------------------------------------- geometry


def _panel_height(p: Panel, style: StyleTable) -> int:
    base = style.purpose_height.get(p.purpose.value) if p.shape == Shape.STANDARD else None
    return style.s(base or style.shape_height.get(p.shape.value, 1100))


def _gap(prev: Panel | None, cur: Panel, style: StyleTable) -> int:
    """Tight inside a beat, longer between beats, longest at a scene cut; extra when the layer changes."""
    if prev is None:
        return 0
    if cur.shape == Shape.TEXT_ONLY or prev.shape == Shape.TEXT_ONLY:
        # A card is part of the gutter: a gap on top of its own padding would read as two pauses.
        return style.s(40)
    if cur.shape == Shape.INSET:
        return 0
    if cur.segment_id != prev.segment_id:
        g = style.gap_scene
    elif cur.purpose.value in style.tight_purposes:
        g = style.gap_tight
    else:
        g = style.gap_beat
    if cur.layer != prev.layer:
        g += style.gap_layer_extra
    return style.s(g)


def _lum(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _fill_rows(bg: np.ndarray, y0: int, y1: int, c0, c1) -> None:
    y0, y1 = max(y0, 0), min(y1, bg.shape[0])
    if y1 <= y0:
        return
    t = np.linspace(0, 1, y1 - y0, dtype=np.float32)[:, None]
    bg[y0:y1] = (np.array(c0, dtype=np.float32) * (1 - t) + np.array(c1, dtype=np.float32) * t)[:, None, :]


def _bg_colour_at(bg: np.ndarray, y: int) -> tuple[int, int, int]:
    return tuple(int(v) for v in bg[min(max(y, 0), bg.shape[0] - 1), 0])  # type: ignore[return-value]


# --------------------------------------------------------------------------- main


def render_storyboard_strip(
    storyboard: Storyboard, images: Mapping[str, Path | Image.Image], style: StyleTable | None = None,
    *, faces: FaceBoxes | None = None, drama_fx: bool = True,
) -> StripResult:
    """`drama_fx` (default on for the storyboard path: the bake-off pictures read flat without it, ART_DRAMA; pass False for a plain
    page) adds the drama layer of `pages/drama_fx.py`: per-purpose speed
    lines, a per-layer contrast and vignette grade, screentone on memory/lore, and a burst with brushed lettering behind SFX."""
    style = style or DEFAULT_STYLE
    s, width = style.s, style.width
    faces = faces or {}
    panels = storyboard.panels
    if not panels:
        raise ValueError("storyboard has no panels")

    # ---- 1. measure letters and size every panel
    geoms: list[dict] = []
    prev: Panel | None = None
    cursor = 0
    inset_flip = 0
    top_pad = s(30)
    cursor = top_pad
    for p in panels:
        layer = style.layer(p.layer.value)
        w = width
        h = _panel_height(p, style)
        if p.shape == Shape.INSET:
            w = int(width * 0.5)
            h = s(style.shape_height["inset"])
        meas_w = max(w, int(width * 0.62))
        big_sfx = p.purpose == Purpose.COLD_OPEN or p.shape == Shape.BLEED
        ms = [gl.measure(i, lt, style, layer, panel_w=meas_w, panel_h=h, big_sfx=big_sfx) for i, lt in enumerate(p.letters)]
        text_h = sum(m.size[1] + s(34) for m in ms if m.kind != LetterKind.SFX)
        if p.shape == Shape.TEXT_ONLY:
            h = max(h, text_h + 2 * s(110))
        elif text_h:
            h = max(h, min(int(text_h / 0.55 + s(80)), int(h * 1.9)))
            # Re-measure against the final height so the font floor, not the old height, limits the fit.
            ms = [gl.measure(i, lt, style, layer, panel_w=meas_w, panel_h=h, big_sfx=big_sfx) for i, lt in enumerate(p.letters)]
        g = _gap(prev, p, style)
        if p.shape == Shape.DIAGONAL and prev is not None:
            g = max(g - s(style.diagonal_slant) // 2, s(20))
        gap_y0 = cursor
        cursor += g
        if p.shape == Shape.INSET and geoms and geoms[-1]["panel"].shape != Shape.TEXT_ONLY:
            pr = geoms[-1]["rect"]
            x = width - w - s(40) if inset_flip % 2 == 0 else s(40)
            inset_flip += 1
            y = pr[3] - int(h * 0.5)
            rect = (x, y, x + w, y + h)
            cursor = max(cursor, y + h)
            gap_rec = None
        else:
            rect = (0, cursor, w, cursor + h)
            cursor += h
            gap_rec = (gap_y0, rect[1]) if g else None
        geoms.append({"panel": p, "rect": rect, "m": ms, "layer": layer, "prev": prev, "gap": gap_rec, "meas_w": meas_w})
        prev = p
    total_h = cursor + s(320)

    # ---- 2. gutter background
    bg = np.zeros((total_h, width, 3), dtype=np.float32)
    first_layer = geoms[0]["layer"]
    _fill_rows(bg, 0, geoms[0]["rect"][1], first_layer.gutter_start, first_layer.gutter_start)
    last_end = geoms[0]["layer"].gutter_start
    last_y = geoms[0]["rect"][1]
    for gm in geoms:
        r, ly = gm["rect"], gm["layer"]
        if r[1] > last_y:
            _fill_rows(bg, last_y, r[1], last_end, ly.gutter_start)
        if r[3] > last_y:
            _fill_rows(bg, max(r[1], last_y), r[3], ly.gutter_start, ly.gutter_end)
            last_y, last_end = r[3], ly.gutter_end
    _fill_rows(bg, last_y, total_h, last_end, last_end)
    strip = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    gutters = [g["gap"] for g in geoms if g["gap"]]

    # ---- 3. pictures
    face_px: dict[str, dict[str, gl.Box]] = {}
    weights: dict[str, np.ndarray | None] = {}
    centroids: dict[str, tuple[int, int] | None] = {}
    placed_panels: list[PlacedPanel] = []
    for gm in geoms:
        p: Panel = gm["panel"]
        x0, y0, x1, y1 = gm["rect"]
        w, h = x1 - x0, y1 - y0
        placed_panels.append(PlacedPanel(p.panel_id, gm["rect"], p.shape.value, p.layer.value))
        if p.shape == Shape.TEXT_ONLY:
            weights[p.panel_id], centroids[p.panel_id] = None, None
            continue
        src = images.get(p.panel_id)
        fb = faces.get(p.panel_id)
        if src is None or (isinstance(src, Path) and not src.exists()):
            pic, scale, off, weight_ok = _placeholder(w, h, p), 1.0, (0, 0), True
            fb = None
        else:
            raw = src if isinstance(src, Image.Image) else Image.open(src)
            raw = raw.convert("RGB")
            pic, scale, off = _fit(raw, (w, h), _focus_of(raw, fb))
            weight_ok = True
            if fb:
                face_px[p.panel_id] = {
                    k: (int(x0 + b[0] * raw.width * scale - off[0]), int(y0 + b[1] * raw.height * scale - off[1]),
                        int(x0 + b[2] * raw.width * scale - off[0]), int(y0 + b[3] * raw.height * scale - off[1]))
                    for k, b in fb.items()
                }
        if weight_ok:
            smap = estimate_subject(pic)
            weights[p.panel_id] = smap.weight
            wt = smap.weight
            if wt.sum() > 0:
                ys, xs = np.mgrid[0:wt.shape[0], 0:wt.shape[1]]
                centroids[p.panel_id] = (int(x0 + (xs * wt).sum() / wt.sum() / wt.shape[1] * w),
                                         int(y0 + (ys * wt).sum() / wt.sum() / wt.shape[0] * h))
            else:
                centroids[p.panel_id] = None
        if p.panel_id not in face_px and src is None:
            # Placeholder head, so tails and avoidance have a face to work with in fixtures.
            face_px[p.panel_id] = {"_ph": (x0 + w // 2 - int(min(w, h) * 0.17), y0 + int(h * 0.45 - min(w, h) * 0.21),
                                           x0 + w // 2 + int(min(w, h) * 0.17), y0 + int(h * 0.45 + min(w, h) * 0.21))}
        pic = GRADES.get(gm["layer"].grade, GRADES["none"])(pic)
        if drama_fx:
            from echotales.pipeline.pages import drama_fx as fx

            pic = fx.apply_panel_fx(pic, p, seed=zlib.crc32(p.panel_id.encode()))
        _paste_shaped(strip, pic, gm, style, bg, panels[0] is p)

    # ---- 4. lettering
    placed: list[gl.Placed] = []
    overflow: list[gl.Overflow] = []
    for k, gm in enumerate(geoms):
        p = gm["panel"]
        if not p.letters:
            continue
        rect, layer, ms = gm["rect"], gm["layer"], gm["m"]
        meas_w = gm["meas_w"]
        mid_bg = _bg_colour_at(bg, (rect[1] + rect[3]) // 2)

        def redo(m: gl.Measured, att: float, _gm=gm, _p=p, _layer=layer) -> gl.Measured:
            return gl.measure(m.idx, m.letter, style, _layer, panel_w=_gm["meas_w"], panel_h=_gm["rect"][3] - _gm["rect"][1],
                              scale_down=att, big_sfx=_p.purpose == Purpose.COLD_OPEN or _p.shape == Shape.BLEED)

        if p.shape == Shape.TEXT_ONLY:
            order = [m for m in ms if m.kind != LetterKind.SFX]
            total = sum(m.size[1] for m in order) + s(34) * (len(order) - 1)
            y = rect[1] + (rect[3] - rect[1] - total) // 2
            for m in order:
                bx = (rect[0] + (width - m.size[0]) // 2, y, rect[0] + (width + m.size[0]) // 2, y + m.size[1])
                ext = gl.draw_letter(strip, m, bx, None, style=style, layer=layer, on_dark=_lum(mid_bg) < 110)
                placed.append(gl.Placed(p.panel_id, m.idx, m.kind.value, bx, ext, None, " ".join(m.lines), m.font_px))
                if m.lost:
                    overflow.append(gl.Overflow(p.panel_id, m.idx, m.kind.value, m.lost, "truncated"))
                y += m.size[1] + s(34)
            continue
        obstacles: list[gl.Box] = [g["rect"] for g in geoms[k + 1:k + 3] if g["panel"].shape == Shape.INSET
                                   and g["rect"][1] < rect[3]]
        if p.shape == Shape.DIAGONAL:
            obstacles.append((rect[0], rect[1], rect[2], rect[1] + s(style.diagonal_slant)))
        if p.shape == Shape.BLEED:
            obstacles.append((rect[0], rect[1], rect[2], rect[1] + s(style.bleed_fade) // 2))
            obstacles.append((rect[0], rect[3] - s(style.bleed_fade) // 2, rect[2], rect[3]))
        if p.shape == Shape.INSET:
            # Letters of an inset stay inside it; the frame, not the neighbour, bounds them.
            pass
        res, over = gl.place_panel(
            p.panel_id, rect, ms, style=style, layer=layer, weight=weights.get(p.panel_id),
            faces=face_px.get(p.panel_id, {}), obstacles=obstacles, centroid=centroids.get(p.panel_id), redo=redo,
        )
        overflow.extend(over)
        res.sort(key=lambda t: (t[0].kind == LetterKind.SFX, t[1][1], t[1][0]))
        for m, bx, tip in res:
            if m.kind == LetterKind.SFX:
                if drama_fx:
                    from echotales.pipeline.pages import drama_fx as fx

                    ext = fx.draw_burst_and_brush(strip, m, (bx[0], bx[1]), layer.sfx_fill, layer.sfx_edge,
                                                  seed=zlib.crc32(m.letter.text.encode()))
                else:
                    ext = gl.draw_sfx(strip, m, (bx[0], bx[1]))
                placed.append(gl.Placed(p.panel_id, m.idx, "sfx", bx, ext, None, m.letter.text, m.font_px))
                continue
            on_dark = _lum(mid_bg) < 110
            ext = gl.draw_letter(strip, m, bx, tip, style=style, layer=layer, on_dark=on_dark)
            placed.append(gl.Placed(p.panel_id, m.idx, m.kind.value, bx, ext, tip, " ".join(m.lines), m.font_px))

    result = StripResult(strip, placed_panels, placed, overflow, gutters)
    result.cuts = choose_cuts(strip.height, placed, gutters, style)
    return result


def _paste_shaped(strip: Image.Image, pic: Image.Image, gm: dict, style: StyleTable, bg: np.ndarray, first: bool) -> None:
    p: Panel = gm["panel"]
    x0, y0, x1, y1 = gm["rect"]
    w, h = pic.size
    s = style.s
    mask = Image.new("L", (w, h), 255)
    if p.shape == Shape.DIAGONAL:
        slant = s(style.diagonal_slant)
        left_low = (zlib.crc32(p.panel_id.encode()) % 2) == 0
        a, b = (slant, 0) if left_low else (0, slant)
        big = Image.new("L", (w * 3, h * 3), 0)
        ImageDraw.Draw(big).polygon([(0, a * 3), (w * 3, b * 3), (w * 3, h * 3), (0, h * 3)], fill=255)
        mask = big.resize((w, h), Image.Resampling.LANCZOS)
    elif p.shape == Shape.BLEED:
        f = s(style.bleed_fade)
        ramp = np.ones(h, dtype=np.float32)
        t = np.linspace(0, 1, f, dtype=np.float32) ** 1.4
        if not first:
            ramp[:f] = t
        ramp[-f:] = t[::-1]
        mask = Image.fromarray((np.repeat(ramp[:, None], w, 1) * 255).astype(np.uint8))
    elif p.shape == Shape.INSET:
        fw = s(style.inset_frame)
        big = Image.new("L", (w * 3, h * 3), 0)
        ImageDraw.Draw(big).rounded_rectangle((0, 0, w * 3 - 1, h * 3 - 1), s(18) * 3, fill=255)
        mask = big.resize((w, h), Image.Resampling.LANCZOS)
        frame = gm["layer"].frame
        halo_pad = s(40) if gm["layer"].grade == "imagined" else s(10)
        glow = Image.new("L", (w + 2 * halo_pad, h + 2 * halo_pad), 0)
        ImageDraw.Draw(glow).rounded_rectangle((halo_pad - fw, halo_pad - fw, halo_pad + w + fw, halo_pad + h + fw),
                                               s(24), fill=255)
        if gm["layer"].grade == "imagined":
            glow = glow.filter(ImageFilter.GaussianBlur(s(14))).point(lambda v: min(255, int(v * 1.6)))
        region = strip.crop((x0 - halo_pad, y0 - halo_pad, x1 + halo_pad, y1 + halo_pad))
        region.paste(Image.new("RGB", glow.size, frame), (0, 0), glow)
        strip.paste(region, (x0 - halo_pad, y0 - halo_pad))
    strip.paste(pic, (x0, y0), mask)


# --------------------------------------------------------------------------- slicing


def choose_cuts(height: int, placed: list[gl.Placed], gutters: list[tuple[int, int]], style: StyleTable) -> list[int]:
    """Cut positions (y) giving slices of about `slice_target`, never through a balloon, SFX or card; a cut
    inside a gutter is preferred to one across art. A slice may exceed `slice_max` only when a balloon or an
    unbroken run of lettering leaves no legal row inside it (reported by the caller via slice heights)."""
    clear = style.s(14)
    forbidden = np.zeros(height + 1, dtype=bool)
    for pl in placed:
        forbidden[max(pl.extent[1] - clear, 0):min(pl.extent[3] + clear, height) + 1] = True
    in_gutter = np.zeros(height + 1, dtype=bool)
    for a, b in gutters:
        in_gutter[a:b + 1] = True
    cuts: list[int] = []
    cur = 0
    while height - cur > style.slice_max:
        lo, hi = cur + style.slice_min, cur + style.slice_max
        ys = np.arange(lo, min(hi, height - 1) + 1)
        ok = ys[~forbidden[ys]]
        if ok.size == 0:
            ys = np.arange(hi, min(cur + 2 * style.slice_max, height - 1) + 1)
            ok = ys[~forbidden[ys]]
            if ok.size == 0:
                break
            cut = int(ok[0])
        else:
            score = np.abs(ok - (cur + style.slice_target)) + np.where(in_gutter[ok], 0, 400)
            cut = int(ok[int(np.argmin(score))])
        cuts.append(cut)
        cur = cut
    return cuts


def _contact_sheet(slices: list[Image.Image], path: Path, col_w: int = 360) -> None:
    thumbs = [im.resize((col_w, max(int(im.height * col_w / im.width), 1)), Image.Resampling.LANCZOS) for im in slices]
    gap = 16
    tallest = max(t.height for t in thumbs)
    sheet = Image.new("RGB", ((col_w + gap) * len(thumbs) + gap, tallest + 2 * gap), (96, 96, 100))
    for i, t in enumerate(thumbs):
        sheet.paste(t, (gap + i * (col_w + gap), gap))
    sheet.save(path)


def render_storyboard_webtoon(
    storyboard: Storyboard, images: Mapping[str, Path], out_dir: Path, style: StyleTable | None = None,
    *, faces: FaceBoxes | None = None, drama_fx: bool = True,
) -> list[Path]:
    """Slices `slice_001.png` ... plus `contact.png` and `layout.json` under `out_dir`; returns the slice paths."""
    import json

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = render_storyboard_strip(storyboard, images, style, faces=faces, drama_fx=drama_fx)
    bounds = [0, *res.cuts, res.strip.height]
    slices = [res.strip.crop((0, a, res.strip.width, b)) for a, b in itertools.pairwise(bounds)]
    paths = []
    for i, im in enumerate(slices, 1):
        path = out_dir / f"slice_{i:03d}.png"
        im.save(path)
        paths.append(path)
    _contact_sheet(slices, out_dir / "contact.png")
    (out_dir / "layout.json").write_text(json.dumps({
        "cuts": res.cuts,
        "overflow": [o.__dict__ for o in res.overflow],
        "letters": [{"panel_id": p.panel_id, "kind": p.kind, "box": p.box, "tail_tip": p.tail_tip, "font_px": p.font_px}
                    for p in res.placed],
    }, indent=1))
    return paths


def export_storyboard_webtoon(
    slices: list[Path], out_dir: Path, name: str, formats: list[str], *, title: str = "", series: str = "", number: str = "1",
) -> list[Path]:
    """CBZ/PDF/PNG through the existing exporter (webtoon reads left-to-right, top to bottom, so manga=False)."""
    pages = [Image.open(p).convert("RGB") for p in slices]
    return export_pages(pages, Path(out_dir), name, formats, title=title or name, series=series or name, number=number, manga=False)


def storyboard_dir_images(storyboard: Storyboard, image_dir: Path) -> dict[str, Path]:
    """`<panel_id>.png` (or .jpg/.webp) under `image_dir` for every panel that has one."""
    found: dict[str, Path] = {}
    for p in storyboard.panels:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            c = Path(image_dir) / f"{p.panel_id}{ext}"
            if c.exists():
                found[p.panel_id] = c
                break
    return found


