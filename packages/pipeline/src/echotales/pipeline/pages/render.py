"""Draw one composed page: panel pictures into their rects, then the lettering on top (roadmap M1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from echotales.pipeline.pages.composer import PageLayout  # type: ignore[import-untyped]
from echotales.pipeline.pages.lettering import (  # type: ignore[import-untyped]
    INK,
    LetterItem,
    LetterResult,
    letter_panel,
)
from echotales.pipeline.pages.placement import estimate_subject  # type: ignore[import-untyped]
from PIL import Image, ImageDraw, ImageOps

BORDER = 4
#: A webtoon panel has no frame line: the page is white and the picture bleeds full width.
WEBTOON_BORDER = 0
#: Strip a probe run may use below each panel to measure how much gutter its bubbles want.
GUTTER_PROBE = 400


def _edge_colour(img: Image.Image, top: bool) -> np.ndarray:
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    rows = arr[: max(2, arr.shape[0] // 20)] if top else arr[-max(2, arr.shape[0] // 20) :]
    return rows.reshape(-1, 3).mean(axis=0)


def _draw_band(page: Image.Image, y: int, h: int, top: np.ndarray, bottom: np.ndarray) -> None:
    """Fade the colour the previous scene ended on into the colour the next one starts with, through the
    page white in the middle so the band reads as a pause and not a smear."""
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    white = np.array([255.0, 255.0, 255.0], dtype=np.float32)
    # Third-strength tints: the full edge colour of a dark panel would make the band a black bar.
    a = 0.35 * top + 0.65 * white
    b = 0.35 * bottom + 0.65 * white
    col = np.where(t < 0.5, a + (white - a) * (t / 0.5), white + (b - white) * ((t - 0.5) / 0.5))
    strip = np.repeat(col[:, None, :], page.width, axis=1)
    page.paste(Image.fromarray(np.clip(strip, 0, 255).astype(np.uint8)), (0, y))


def render_page(
    layout: PageLayout,
    images: Mapping[str, Image.Image],
    lettering: Mapping[str, Sequence[LetterItem]],
    *,
    rtl: bool,
    probe_gutters: bool = False,
) -> tuple[Image.Image, dict[str, LetterResult]]:
    """`probe_gutters` letters every panel with `GUTTER_PROBE` px of room below it whatever the layout
    gives, to read each panel's `gutter_used`; the page it returns is then thrown away."""
    webtoon = layout.template == "webtoon"
    page = Image.new("RGB", (layout.width, layout.height), (255, 255, 255))
    results: dict[str, LetterResult] = {}
    draw = ImageDraw.Draw(page)
    subjects = {}
    fitted: dict[str, Image.Image] = {}
    for r in layout.panels:
        # Cover-fit: a panel keeps its aspect and loses edge rather than being stretched, because the
        # director frames the subject near the centre.
        pic = ImageOps.fit(images[r.panel_id].convert("RGB"), (r.w, r.h), Image.Resampling.LANCZOS)
        fitted[r.panel_id] = pic
        subjects[r.panel_id] = estimate_subject(pic)
        page.paste(pic, (r.x, r.y))
        if not webtoon:
            draw.rectangle((r.x, r.y, r.x + r.w - 1, r.y + r.h - 1), outline=INK, width=BORDER)
    for band in layout.bands:
        _draw_band(page, band.y, band.h, _edge_colour(fitted[band.above], False), _edge_colour(fitted[band.below], True))
    # Lettering after every border so a bubble may cross its panel's frame without being overpainted.
    for k, r in enumerate(layout.panels):
        items = lettering.get(r.panel_id)
        if not items:
            continue
        gutter = 0
        if webtoon:
            below = layout.panels[k + 1].y if k + 1 < len(layout.panels) else layout.height
            gutter = GUTTER_PROBE if probe_gutters else max(below - (r.y + r.h), 0)
        results[r.panel_id] = letter_panel(
            page, (r.x, r.y, r.w, r.h), list(items), rtl=rtl, subject=subjects[r.panel_id], gutter_below=gutter
        )
    return page, results
