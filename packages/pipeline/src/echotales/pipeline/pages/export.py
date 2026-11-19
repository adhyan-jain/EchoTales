"""Export composed pages as PNG, PDF and CBZ, and cut a webtoon strip into postable pieces (roadmap M1 step 3)."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Sequence
from pathlib import Path

from echotales.pipeline.pages.composer import PageLayout
from PIL import Image

EXPORT_FORMATS = ("png", "pdf", "cbz")
#: Webtoon hosts cap an image's height; this is a conservative common ceiling, not any one site's rule.
WEBTOON_MAX_HEIGHT = 12000
#: Fixed so the same pages always give byte-identical archives.
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def split_strip(strip: Image.Image, layout: PageLayout, max_height: int = WEBTOON_MAX_HEIGHT) -> list[Image.Image]:
    """Cut the strip into pieces at most `max_height` tall, each cut in a gutter so no panel is split.

    A single panel taller than `max_height` is cut at the limit; that is the only case a panel is split.
    """
    cuts = [0]
    while strip.height - cuts[-1] > max_height:
        start = cuts[-1]
        limit = start + max_height
        # The end of the last panel that still fits, plus the gutter below it, is the latest clean cut.
        ends = [r.y + r.h for r in layout.panels if start < r.y + r.h <= limit]
        best = max(ends) if ends else limit
        nxt = min((r.y for r in layout.panels if r.y >= best), default=limit)
        cuts.append(min((best + nxt) // 2 if nxt > best else best, limit))
    cuts.append(strip.height)
    return [strip.crop((0, a, strip.width, b)) for a, b in zip(cuts, cuts[1:], strict=False)]


def _comic_info(title: str, series: str, number: str, pages: int, manga: bool) -> bytes:
    root = ET.Element("ComicInfo")
    for tag, value in (
        ("Title", title), ("Series", series), ("Number", number), ("PageCount", str(pages)),
        ("Manga", "YesAndRightToLeft" if manga else "No"),
    ):
        ET.SubElement(root, tag).text = value
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def export_pages(
    pages: Sequence[Image.Image],
    out_dir: Path,
    name: str,
    formats: Sequence[str],
    *,
    title: str,
    series: str,
    number: str,
    manga: bool,
) -> list[Path]:
    """Write the requested formats under `out_dir` and return every file written, in a stable order."""
    unknown = [f for f in formats if f not in EXPORT_FORMATS]
    if unknown:
        raise ValueError(f"unknown export format {unknown[0]!r}; expected one of {', '.join(EXPORT_FORMATS)}")
    if not pages:
        raise ValueError("no pages to export")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    rgb = [p.convert("RGB") for p in pages]
    if "png" in formats:
        for i, p in enumerate(rgb, 1):
            path = out_dir / f"{i:04d}.png"
            p.save(path)
            written.append(path)
    if "pdf" in formats:
        path = out_dir / f"{name}.pdf"
        rgb[0].save(path, save_all=True, append_images=rgb[1:])
        written.append(path)
    if "cbz" in formats:
        path = out_dir / f"{name}.cbz"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
            for i, p in enumerate(rgb, 1):
                buf = io.BytesIO()
                p.save(buf, format="PNG")
                z.writestr(zipfile.ZipInfo(f"{i:04d}.png", _ZIP_DATE), buf.getvalue())
            z.writestr(zipfile.ZipInfo("ComicInfo.xml", _ZIP_DATE), _comic_info(title, series, number, len(rgb), manga))
        written.append(path)
    return written
