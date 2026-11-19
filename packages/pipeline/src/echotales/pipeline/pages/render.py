"""Draw one composed page: panel pictures into their rects, then the lettering on top (roadmap M1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from echotales.pipeline.pages.composer import PageLayout
from echotales.pipeline.pages.lettering import INK, LetterItem, LetterResult, letter_panel
from PIL import Image, ImageDraw, ImageOps

BORDER = 4


def render_page(
    layout: PageLayout,
    images: Mapping[str, Image.Image],
    lettering: Mapping[str, Sequence[LetterItem]],
    *,
    rtl: bool,
) -> tuple[Image.Image, dict[str, LetterResult]]:
    page = Image.new("RGB", (layout.width, layout.height), (255, 255, 255))
    results: dict[str, LetterResult] = {}
    draw = ImageDraw.Draw(page)
    for r in layout.panels:
        # Cover-fit: a panel keeps its aspect and loses edge rather than being stretched, because the
        # director frames the subject near the centre.
        page.paste(ImageOps.fit(images[r.panel_id].convert("RGB"), (r.w, r.h), Image.Resampling.LANCZOS), (r.x, r.y))
        draw.rectangle((r.x, r.y, r.x + r.w - 1, r.y + r.h - 1), outline=INK, width=BORDER)
    # Lettering after every border so a bubble may cross its panel's frame without being overpainted.
    for r in layout.panels:
        items = lettering.get(r.panel_id)
        if items:
            results[r.panel_id] = letter_panel(page, (r.x, r.y, r.w, r.h), list(items), rtl=rtl)
    return page, results
