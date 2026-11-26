"""Comic page ingest: folder, CBZ, PDF, and webtoon slicing on synthetic pages."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from echotales.pipeline.comic.ingest import (
    ComicInputError,
    load_pages,
    natural_key,
    slice_webtoon,
)
from PIL import Image


def _page(color: int = 90, size: tuple[int, int] = (120, 160)) -> Image.Image:
    return Image.new("RGB", size, (color, color, color))


def test_natural_order_not_lexicographic() -> None:
    names = ["p10.png", "p2.png", "p1.png", "P3.png"]
    assert sorted(names, key=natural_key) == ["p1.png", "p2.png", "P3.png", "p10.png"]


def test_folder_pages_in_natural_order_ignoring_non_images(tmp_path: Path) -> None:
    for n in (10, 2, 1):
        _page(color=n * 10).save(tmp_path / f"page{n}.png")
    (tmp_path / "notes.txt").write_text("not a page")
    pages = load_pages(tmp_path)
    assert [p.name for p in pages] == ["page1.png", "page2.png", "page10.png"]
    assert [p.index for p in pages] == [0, 1, 2]
    assert pages[0].image.getpixel((0, 0))[0] == 10


def test_cbz_matches_folder_and_skips_junk(tmp_path: Path) -> None:
    cbz = tmp_path / "ep.cbz"
    with zipfile.ZipFile(cbz, "w") as z:
        for n in (10, 2, 1):
            buf = io.BytesIO()
            _page(color=n * 10).save(buf, "PNG")
            z.writestr(f"ep/{n}.png", buf.getvalue())
        z.writestr("__MACOSX/ep/._1.png", b"junk")
        z.writestr("ep/ComicInfo.xml", "<x/>")
    pages = load_pages(cbz)
    assert [p.name for p in pages] == ["1.png", "2.png", "10.png"]
    assert pages[1].image.size == (120, 160)


def test_pdf_pages_rendered_when_pdfium_present(tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    pdf = tmp_path / "ep.pdf"
    _page().save(pdf, "PDF", save_all=True, append_images=[_page(200)])
    pages = load_pages(pdf)
    assert len(pages) == 2
    assert pages[1].image.getpixel((5, 5))[0] > 150


def test_unsupported_input_reports_clearly(tmp_path: Path) -> None:
    bad = tmp_path / "x.docx"
    bad.write_text("x")
    with pytest.raises(ComicInputError, match="folder, .cbz or .pdf"):
        load_pages(bad)
    with pytest.raises(ComicInputError, match="not found"):
        load_pages(tmp_path / "missing")


def _strip(blocks: list[int], gutter: int = 40, width: int = 100) -> Image.Image:
    height = sum(blocks) + gutter * (len(blocks) - 1)
    arr = np.full((height, width, 3), 255, dtype=np.uint8)
    rng = np.random.default_rng(0)
    y = 0
    for h in blocks:
        # Per-pixel noise so art rows have horizontal variance, unlike the flat gutter.
        arr[y : y + h] = rng.integers(0, 200, size=(h, width, 3), dtype=np.uint8)
        y += h + gutter
    return Image.fromarray(arr)


def test_webtoon_cuts_at_blank_gutters_and_loses_nothing() -> None:
    strip = _strip([300, 250, 400])
    slices = slice_webtoon(strip, min_gutter=20, min_height=100)
    assert len(slices) == 3
    assert sum(s.height for s in slices) == strip.height


def test_webtoon_ignores_thin_gutters_and_tiny_slices() -> None:
    thin = _strip([300, 300], gutter=6)
    assert len(slice_webtoon(thin, min_gutter=20, min_height=100)) == 1
    tiny = _strip([300, 30, 300], gutter=40)
    out = slice_webtoon(tiny, min_gutter=20, min_height=100)
    assert len(out) == 2 and all(s.height >= 100 for s in out)


def test_webtoon_mode_expands_tall_pages(tmp_path: Path) -> None:
    _strip([300, 300]).save(tmp_path / "strip1.png")
    pages = load_pages(tmp_path, webtoon=True, min_gutter=20, min_height=100)
    assert len(pages) == 2
    assert [p.index for p in pages] == [0, 1]
