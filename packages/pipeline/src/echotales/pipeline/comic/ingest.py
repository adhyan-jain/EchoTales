"""Comic pages in: a folder of images, a .cbz, or a .pdf, in natural page order.

Webtoons arrive as one very tall strip; `slice_webtoon` cuts it at blank horizontal gutters with a deterministic
row-variance scan, so the same strip always yields the same slices (no model in the loop).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
#: A row counts as gutter when its pixel standard deviation is below this (0-255 scale). Scanned or JPEG gutters are
#: not perfectly flat, so exact equality would miss real gutters.
GUTTER_STD = 6.0
PDF_SCALE = 2.0


class ComicInputError(ValueError):
    """The input is not a comic source this module can read; the message says what to supply instead."""


@dataclass(slots=True)
class PageImage:
    index: int
    name: str
    image: Image.Image


def natural_key(name: str) -> list[object]:
    """`p2` before `p10`; case-insensitive. Plain sort put page10 between page1 and page2."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _open(data: bytes | Path) -> Image.Image:
    img = Image.open(io.BytesIO(data) if isinstance(data, bytes) else data)
    img.load()
    return img.convert("RGB")


def _from_folder(folder: Path) -> list[tuple[str, Image.Image]]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    return [(p.name, _open(p)) for p in sorted(files, key=lambda p: natural_key(p.name))]


def _from_cbz(path: Path) -> list[tuple[str, Image.Image]]:
    with zipfile.ZipFile(path) as z:
        members = [
            i for i in z.infolist()
            if not i.is_dir()
            and Path(i.filename).suffix.lower() in IMAGE_SUFFIXES
            # macOS resource forks carry an image suffix but are not images.
            and "__MACOSX" not in i.filename
            and not Path(i.filename).name.startswith("._")
        ]
        members.sort(key=lambda i: natural_key(i.filename))
        return [(Path(i.filename).name, _open(z.read(i))) for i in members]


def _from_pdf(path: Path) -> list[tuple[str, Image.Image]]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ComicInputError("reading a .pdf needs pypdfium2 (pip install pypdfium2); or supply a folder or .cbz") from exc
    pdf = pdfium.PdfDocument(str(path))
    try:
        out = []
        for i in range(len(pdf)):
            img = pdf[i].render(scale=PDF_SCALE).to_pil().convert("RGB")
            out.append((f"page{i + 1:03d}.png", img))
        return out
    finally:
        pdf.close()


def slice_webtoon(strip: Image.Image, *, min_gutter: int = 24, min_height: int = 200) -> list[Image.Image]:
    """Cut a tall strip at the middle of every blank run of at least `min_gutter` rows.

    A slice shorter than `min_height` is merged into its neighbour rather than emitted: a lone caption line between
    two gutters is not a page. The cuts partition the strip, so slice heights always sum to the strip height.
    """
    gray = np.asarray(strip.convert("L"), dtype=np.float32)
    blank = gray.std(axis=1) < GUTTER_STD
    cuts: list[int] = []
    y, h = 0, len(blank)
    while y < h:
        if not blank[y]:
            y += 1
            continue
        start = y
        while y < h and blank[y]:
            y += 1
        # Gutters at the very top or bottom edge are margins, not separators.
        if y - start >= min_gutter and start > 0 and y < h:
            cuts.append((start + y) // 2)
    bounds = [0, *cuts, h]
    # Merge too-short slices forward (or backward at the end) until every slice is tall enough.
    merged = [bounds[0]]
    for b in bounds[1:-1]:
        if b - merged[-1] >= min_height:
            merged.append(b)
    merged.append(h)
    if len(merged) > 2 and merged[-1] - merged[-2] < min_height:
        merged.pop(-2)
    return [strip.crop((0, a, strip.width, b)) for a, b in zip(merged, merged[1:], strict=False)]


def load_pages(
    path: str | Path,
    *,
    webtoon: bool = False,
    min_gutter: int = 24,
    min_height: int = 200,
) -> list[PageImage]:
    """Pages of a folder, .cbz or .pdf in natural order, re-indexed from 0. `webtoon` slices each tall page."""
    p = Path(path)
    if not p.exists():
        raise ComicInputError(f"input not found: {p}")
    if p.is_dir():
        raw = _from_folder(p)
    elif p.suffix.lower() in (".cbz", ".zip"):
        raw = _from_cbz(p)
    elif p.suffix.lower() == ".pdf":
        raw = _from_pdf(p)
    else:
        raise ComicInputError(f"unsupported input {p.name}: give a folder, .cbz or .pdf")
    if not raw:
        raise ComicInputError(f"no page images found in {p}")
    pages: list[PageImage] = []
    for name, img in raw:
        parts = slice_webtoon(img, min_gutter=min_gutter, min_height=min_height) if webtoon else [img]
        for k, part in enumerate(parts):
            label = name if len(parts) == 1 else f"{Path(name).stem}_{k + 1:02d}.png"
            pages.append(PageImage(index=len(pages), name=label, image=part))
    return pages
