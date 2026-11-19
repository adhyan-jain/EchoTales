"""Panel detection and reading order by recursive XY-cut on the gutters.

Deterministic and model-free: the page background is whatever colour the page border is (white for a western comic,
black for some webtoons), a row or column is gutter when almost nothing in it differs from that colour, and the page is
cut at gutters, alternating direction, until no cut is left. The recursion yields reading order as it goes (rows top to
bottom, panels within a row left to right, or right to left for manga).

Measured limit: a panel whose own art is the background colour across a whole row (a white sky bleeding off a page edge)
can be cut short or split. Diagonal or overlapping panels are not handled; they come back as one box.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

#: Pixel differs from background when any channel is further than this from it.
BG_TOL = 28
#: A row or column is gutter when under this fraction of its pixels differ from the background.
GUTTER_FRAC = 0.02
#: Smallest gutter, as a fraction of the page's short side. Thinner gaps are art detail, not panel borders.
MIN_GUTTER_FRAC = 0.008
#: A panel under this fraction of page area is a speck (a stray mark), not a panel.
MIN_AREA_FRAC = 0.01


@dataclass(frozen=True, slots=True)
class Panel:
    index: int
    box: tuple[int, int, int, int]  # x0, y0, x1, y1

    @property
    def size(self) -> tuple[int, int]:
        return self.box[2] - self.box[0], self.box[3] - self.box[1]


def _background(arr: np.ndarray) -> np.ndarray:
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    return np.median(border, axis=0)


def _trim(mask: np.ndarray, x0: int, y0: int) -> tuple[int, int, int, int] | None:
    ys = np.flatnonzero(mask.mean(axis=1) >= GUTTER_FRAC)
    xs = np.flatnonzero(mask.mean(axis=0) >= GUTTER_FRAC)
    if len(ys) == 0 or len(xs) == 0:
        return None
    return x0 + int(xs[0]), y0 + int(ys[0]), x0 + int(xs[-1]) + 1, y0 + int(ys[-1]) + 1


def _runs(content: np.ndarray, min_gutter: int) -> list[tuple[int, int]]:
    """Content segments of a 1-D profile, split at gutter runs of at least `min_gutter`."""
    segs: list[tuple[int, int]] = []
    start: int | None = None
    gap = 0
    for i, c in enumerate(content):
        if c:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gutter:
                segs.append((start, i - gap + 1))
                start = None
    if start is not None:
        segs.append((start, len(content) - gap if gap else len(content)))
    return segs


def _cut(mask: np.ndarray, x0: int, y0: int, min_gutter: int, rtl: bool, horizontal: bool, out: list) -> None:
    box = _trim(mask, x0, y0)
    if box is None:
        return
    bx0, by0, bx1, by1 = box
    sub = mask[by0 - y0 : by1 - y0, bx0 - x0 : bx1 - x0]
    for axis_horizontal in (horizontal, not horizontal):
        profile = sub.mean(axis=1) if axis_horizontal else sub.mean(axis=0)
        segs = _runs(profile >= GUTTER_FRAC, min_gutter)
        if len(segs) > 1:
            if not axis_horizontal and rtl:
                segs = segs[::-1]
            for a, b in segs:
                if axis_horizontal:
                    _cut(sub[a:b], bx0, by0 + a, min_gutter, rtl, False, out)
                else:
                    _cut(sub[:, a:b], bx0 + a, by0, min_gutter, rtl, True, out)
            return
    out.append(box)


def detect_panels(image: Image.Image, *, rtl: bool = False) -> list[Panel]:
    """Panels of one page in reading order. `rtl=True` is the manga order (right panel first within a row)."""
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)
    h, w = arr.shape[:2]
    mask = (np.abs(arr - _background(arr)).max(axis=2) > BG_TOL)
    min_gutter = max(3, int(min(h, w) * MIN_GUTTER_FRAC))
    boxes: list[tuple[int, int, int, int]] = []
    _cut(mask, 0, 0, min_gutter, rtl, True, boxes)
    keep = [b for b in boxes if (b[2] - b[0]) * (b[3] - b[1]) >= MIN_AREA_FRAC * w * h]
    if not keep:
        keep = [(0, 0, w, h)]
    return [Panel(i, b) for i, b in enumerate(keep)]
