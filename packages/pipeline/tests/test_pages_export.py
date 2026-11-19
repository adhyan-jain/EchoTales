"""M1 step 3: PNG pages, PDF, CBZ with ComicInfo.xml, and the webtoon strip split at a maximum height."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from echotales.pipeline.pages.composer import ComposerPanel, PanelRole, compose_pages
from echotales.pipeline.pages.export import export_pages, split_strip
from echotales.pipeline.pages.render import render_page
from PIL import Image


def _pages(n: int) -> list[Image.Image]:
    return [Image.new("RGB", (120, 180), (i * 40 % 255, 80, 120)) for i in range(n)]


def test_png_pages_are_numbered(tmp_path: Path) -> None:
    out = export_pages(_pages(3), tmp_path, "ch1", ["png"], title="T", series="S", number="1", manga=False)
    assert [p.name for p in out] == ["0001.png", "0002.png", "0003.png"]
    assert all(p.is_file() for p in out)


def test_pdf_has_one_page_per_image(tmp_path: Path) -> None:
    out = export_pages(_pages(3), tmp_path, "ch1", ["pdf"], title="T", series="S", number="1", manga=False)
    pdf = next(p for p in out if p.suffix == ".pdf")
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF") and b"/Count 3" in data
    assert data.count(b"/Type /Page\n") == 3


def test_cbz_holds_numbered_pages_and_comicinfo(tmp_path: Path) -> None:
    out = export_pages(_pages(2), tmp_path, "ch1", ["cbz"], title="Ch 1", series="Novel", number="1", manga=True)
    cbz = next(p for p in out if p.suffix == ".cbz")
    with zipfile.ZipFile(cbz) as z:
        names = z.namelist()
        info = ET.fromstring(z.read("ComicInfo.xml"))
    assert names[:2] == ["0001.png", "0002.png"] and "ComicInfo.xml" in names
    assert info.findtext("Title") == "Ch 1" and info.findtext("Series") == "Novel"
    assert info.findtext("Number") == "1" and info.findtext("PageCount") == "2"
    assert info.findtext("Manga") == "YesAndRightToLeft"


def test_comic_cbz_is_left_to_right(tmp_path: Path) -> None:
    out = export_pages(_pages(1), tmp_path, "c", ["cbz"], title="T", series="S", number="1", manga=False)
    with zipfile.ZipFile(next(p for p in out if p.suffix == ".cbz")) as z:
        assert ET.fromstring(z.read("ComicInfo.xml")).findtext("Manga") == "No"


def test_cbz_bytes_are_reproducible(tmp_path: Path) -> None:
    a = export_pages(_pages(2), tmp_path / "a", "c", ["cbz"], title="T", series="S", number="1", manga=False)
    b = export_pages(_pages(2), tmp_path / "b", "c", ["cbz"], title="T", series="S", number="1", manga=False)
    assert a[0].read_bytes() == b[0].read_bytes()


def test_webtoon_strip_splits_at_gutters_within_max_height() -> None:
    panels = [ComposerPanel(f"p{i}", PanelRole.SCENE, 512, 512) for i in range(8)]
    layout = compose_pages(panels, "webtoon")[0]
    strip = Image.new("RGB", (layout.width, layout.height), (255, 255, 255))
    parts = split_strip(strip, layout, max_height=2000)
    assert len(parts) > 1
    assert all(p.height <= 2000 for p in parts)
    assert sum(p.height for p in parts) == layout.height
    # No panel is cut: every cut sits in a gutter.
    cuts, y = [], 0
    for p in parts[:-1]:
        y += p.height
        cuts.append(y)
    for c in cuts:
        assert not any(r.y < c < r.y + r.h for r in layout.panels)


def test_short_strip_is_one_piece() -> None:
    panels = [ComposerPanel("p0", PanelRole.SCENE, 512, 512)]
    layout = compose_pages(panels, "webtoon")[0]
    assert len(split_strip(Image.new("RGB", (layout.width, layout.height)), layout, max_height=5000)) == 1


def test_render_page_crops_each_panel_into_its_rect() -> None:
    panels = [ComposerPanel("a", PanelRole.SCENE, 64, 64), ComposerPanel("b", PanelRole.SCENE, 64, 64)]
    layout = compose_pages(panels, "comic")[0]
    images = {"a": Image.new("RGB", (64, 64), (200, 0, 0)), "b": Image.new("RGB", (64, 64), (0, 200, 0))}
    page, results = render_page(layout, images, {}, rtl=False)
    assert page.size == (layout.width, layout.height)
    ra, rb = sorted(layout.panels, key=lambda r: r.order)
    assert page.getpixel((ra.x + ra.w // 2, ra.y + ra.h // 2)) == (200, 0, 0)
    assert page.getpixel((rb.x + rb.w // 2, rb.y + rb.h // 2)) == (0, 200, 0)
    assert results == {}
