"""Panel detection and reading order on synthetic pages (deterministic, no model)."""

from __future__ import annotations

import numpy as np
from echotales.pipeline.comic.panels import detect_panels
from PIL import Image


def _page(boxes: list[tuple[int, int, int, int]], size=(600, 800), bg=255) -> Image.Image:
    arr = np.full((size[1], size[0], 3), bg, dtype=np.uint8)
    rng = np.random.default_rng(1)
    for x0, y0, x1, y1 in boxes:
        arr[y0:y1, x0:x1] = rng.integers(10, 120, size=(y1 - y0, x1 - x0, 3), dtype=np.uint8)
    return Image.fromarray(arr)


def test_three_stacked_panels_in_order() -> None:
    boxes = [(30, 30, 570, 250), (30, 290, 570, 510), (30, 550, 570, 770)]
    got = detect_panels(_page(boxes))
    assert [p.box for p in got] == boxes


def test_grid_reads_ltr_row_by_row_and_rtl_reverses_rows() -> None:
    boxes = [(20, 20, 290, 380), (330, 20, 580, 380), (20, 420, 580, 780)]
    page = _page(boxes)
    assert [p.box for p in detect_panels(page)] == boxes
    assert [p.box for p in detect_panels(page, rtl=True)] == [boxes[1], boxes[0], boxes[2]]


def test_dark_background_page_is_handled_by_border_colour() -> None:
    boxes = [(30, 30, 570, 380), (30, 420, 570, 770)]
    arr = np.asarray(_page(boxes, bg=0)).copy()
    # Panels of mid-grey noise on a black page: background is whatever the border is.
    arr[30:380, 30:570] = np.random.default_rng(2).integers(90, 250, size=(350, 540, 3), dtype=np.uint8)
    arr[420:770, 30:570] = np.random.default_rng(3).integers(90, 250, size=(350, 540, 3), dtype=np.uint8)
    got = detect_panels(Image.fromarray(arr))
    assert [p.box for p in got] == boxes


def test_borderless_page_is_one_panel_and_specks_are_dropped() -> None:
    arr = np.asarray(_page([(0, 0, 600, 800)]))
    assert len(detect_panels(Image.fromarray(arr))) == 1
    speck = _page([(30, 30, 570, 400), (300, 600, 310, 610)])
    assert len(detect_panels(speck)) == 1
