"""Where a bubble may go without covering the picture (roadmap M1 pages polish, EVOLUTION 4.185).

**Why this exists.** The old placement only avoided other bubbles and walked top-left to bottom-right, so
the first bubble of every panel sat in the top-left corner whatever was drawn there; measured on the r6
LotM, Reverend Insanity and Pride and Prejudice panels, a large share of bubble area landed on the
character (4.185 has the numbers). A bubble is now scored against a cheap estimate of where the subject
is, read from the pixels of the panel itself: nothing heavy, no model, numpy and Pillow only.

**The estimate is deliberately crude.** Saliency is how far a pixel is from the panel's median colour plus
local edge density, with a skin-tone term that stands in for faces (anime faces and hands are the thing
a bubble must not cover, and skin colour is the one face cue that survives flat cel shading). It is
deterministic, so the same panel always gets the same bubble positions. It cannot tell a face from a lit
cheek-coloured wall; the measurement in 4.185 uses the same estimator, so it shows the placement obeys the
estimate, and a page is still judged by eye.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

#: The analysis width. 96 columns keep a bubble-sized box to a few cells and make the whole search cheap.
MAP_W = 96
#: Saliency above this counts as "subject" when a binary decision is needed (overlap reports, the gutter rule).
SUBJECT_THRESHOLD = 0.38
#: The fraction of a panel's cells taken as subject.
SUBJECT_SHARE = 0.35
#: A bubble covering more than this share of subject cells is not left where it is when a gutter is free.
SPILL_LIMIT = 0.04
_COLOUR_SCALE = 90.0
_EDGE_SCALE = 18.0


@dataclass(frozen=True, slots=True)
class SubjectMap:
    #: (rows, cols) 0..1, how much each cell looks like part of the subject.
    saliency: np.ndarray
    #: (rows, cols) 0..1, how skin-like (a face or hand) each cell is.
    skin: np.ndarray

    @property
    def weight(self) -> np.ndarray:
        """What a bubble pays to cover a cell: skin counts triple, because a covered face is the one defect
        that makes a page unreadable as a picture."""
        return np.minimum(self.saliency + 2.0 * self.skin, 3.0)

    def mask(self, threshold: float = SUBJECT_THRESHOLD) -> np.ndarray:
        """Subject cells: the most salient `SUBJECT_SHARE` of the panel (never below `threshold`'s floor of
        0.15), or clearly skin. Relative, because a busy background makes every cell salient in absolute
        terms and then no bubble could ever be called clear (the first cut of this mask called 92% of the
        Reverend Insanity panels subject)."""
        cut = max(float(np.quantile(self.saliency, 1.0 - SUBJECT_SHARE)), min(threshold, 0.15))
        return (self.saliency >= cut) | (self.skin >= 0.5)


def _blur(a: np.ndarray, radius: float) -> np.ndarray:
    im = Image.fromarray(np.clip(a * 255.0, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255.0


def estimate_subject(img: Image.Image) -> SubjectMap:
    """Saliency and skin maps of `img`, `MAP_W` columns wide."""
    w, h = img.size
    mh = max(8, round(MAP_W * h / max(w, 1)))
    small = np.asarray(img.convert("RGB").resize((MAP_W, mh), Image.Resampling.BOX), dtype=np.float32)
    median = np.median(small.reshape(-1, 3), axis=0)
    dist = np.linalg.norm(small - median, axis=2)
    gray = small @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    gy, gx = np.gradient(gray)
    edge = np.hypot(gx, gy)
    # Radius 3: a cel-shaded face is flat inside, so only a wide blur lets its outline fill it in.
    colour = _blur(np.clip(dist / _COLOUR_SCALE, 0, 1), 3.0)
    edges = _blur(np.clip(edge / _EDGE_SCALE, 0, 1), 3.0)
    # Skin in YCbCr (the classic Chai-Ngan box), which holds up better than RGB rules under flat shading.
    r, g, b = small[..., 0], small[..., 1], small[..., 2]
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    skin = ((cb > 95) & (cb < 125) & (cr > 140) & (cr < 168) & (gray > 110) & (r > g) & (g > b)).astype(np.float32)
    skin = _blur(skin, 1.2)
    sal = np.clip(0.55 * colour + 0.45 * edges, 0, 1)
    # A faint centre prior: the director frames the subject near the middle (`pages/render.py`'s cover-fit).
    yy, xx = np.mgrid[0:mh, 0:MAP_W]
    centre = np.exp(-(((xx - MAP_W / 2) / (MAP_W * 0.35)) ** 2 + ((yy - mh / 2) / (mh * 0.35)) ** 2))
    sal = np.clip(sal + 0.22 * centre, 0, 1)
    return SubjectMap(sal.astype(np.float32), skin.astype(np.float32))


def _integral(a: np.ndarray) -> np.ndarray:
    out = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    out[1:, 1:] = a.cumsum(0).cumsum(1)
    return out


def _box_mean(ii: np.ndarray, r0: np.ndarray, r1: np.ndarray, c0: np.ndarray, c1: np.ndarray) -> np.ndarray:
    area = np.maximum((r1 - r0) * (c1 - c0), 1)
    mean: np.ndarray = (ii[r1, c1] - ii[r0, c1] - ii[r1, c0] + ii[r0, c0]) / area
    return mean


def subject_share(boxes: list[tuple[int, int, int, int]], rect: tuple[int, int, int, int], smap: SubjectMap) -> float:
    """Share of the boxes' area that lies on the subject mask. Area outside `rect` (a gutter) counts as
    clear, so a bubble moved to the gutter lowers the number the way it lowers the harm."""
    rx, ry, rw, rh = rect
    rows, cols = smap.saliency.shape
    mask = smap.mask()
    total = 0.0
    hit = 0.0
    for x0, y0, x1, y1 in boxes:
        total += max(x1 - x0, 0) * max(y1 - y0, 0)
        c0 = max(0, int((x0 - rx) / rw * cols))
        c1 = min(cols, int(np.ceil((x1 - rx) / rw * cols)))
        r0 = max(0, int((y0 - ry) / rh * rows))
        r1 = min(rows, int(np.ceil((y1 - ry) / rh * rows)))
        if c1 > c0 and r1 > r0:
            ix0, ix1 = max(x0, rx), min(x1, rx + rw)
            iy0, iy1 = max(y0, ry), min(y1, ry + rh)
            inside = max(ix1 - ix0, 0) * max(iy1 - iy0, 0)
            hit += inside * float(mask[r0:r1, c0:c1].mean())
    return hit / total if total else 0.0


def speaker_point(smap: SubjectMap, rect: tuple[int, int, int, int], position: str | None) -> tuple[int, int] | None:
    """The centre of the speaker's face, from the skin map restricted to the side the director named.

    None when the panel has no skin-like cells there: the caller then falls back to the director's
    coarse position, which is all the old code had."""
    rx, ry, rw, rh = rect
    rows, cols = smap.skin.shape
    pos = (position or "").lower()
    c0, c1 = (0, cols // 2 + cols // 8) if "left" in pos else (cols // 2 - cols // 8, cols) if "right" in pos else (0, cols)
    region = smap.skin[:, c0:c1]
    strong = np.where(region >= 0.45, region, 0.0)
    if strong.sum() < 3.0:
        return None
    ys, xs = np.mgrid[0:rows, c0:c1]
    cx = float((strong * xs).sum() / strong.sum())
    cy = float((strong * ys).sum() / strong.sum())
    return round(rx + (cx + 0.5) / cols * rw), round(ry + (cy + 0.5) / rows * rh)


@dataclass(frozen=True, slots=True)
class Spot:
    x: int
    y: int
    #: Share of the box on the subject mask (0 clear, 1 all subject).
    spill: float
    in_gutter: bool


def find_clear_spot(
    bw: int,
    bh: int,
    rect: tuple[int, int, int, int],
    smap: SubjectMap,
    taken: list[tuple[int, int, int, int]],
    anchor: tuple[int, int],
    clearance: int,
    *,
    edge: int = 8,
) -> Spot | None:
    """The lowest-cost spot for a `bw` x `bh` box inside `rect`, or None when no spot avoids `taken`.

    Cost is the subject weight under the box, plus a small pull toward the speaker's side and toward the
    top of the panel (manga and manhwa read top-down, so the first bubble should be the highest)."""
    rx, ry, rw, rh = rect
    rows, cols = smap.saliency.shape
    xs = np.arange(rx + edge, rx + rw - bw - edge + 1, max(4, round(rw * 0.025)))
    ys = np.arange(ry + edge, ry + rh - bh - edge + 1, max(4, round(rh * 0.025)))
    if xs.size == 0 or ys.size == 0:
        return None
    gx, gy = np.meshgrid(xs, ys)
    c0 = np.clip(np.floor((gx - rx) / rw * cols).astype(int), 0, cols - 1)
    c1 = np.clip(np.ceil((gx + bw - rx) / rw * cols).astype(int), c0 + 1, cols)
    r0 = np.clip(np.floor((gy - ry) / rh * rows).astype(int), 0, rows - 1)
    r1 = np.clip(np.ceil((gy + bh - ry) / rh * rows).astype(int), r0 + 1, rows)
    cost = _box_mean(_integral(smap.weight), r0, r1, c0, c1)
    spill = _box_mean(_integral(smap.mask().astype(np.float32)), r0, r1, c0, c1)
    # Pulls are small next to a covered face (weight up to 3) but decide between equally clear spots.
    cost = cost + 0.35 * np.abs(gx + bw / 2 - anchor[0]) / rw + 0.25 * (gy - ry) / rh
    valid = np.ones(cost.shape, dtype=bool)
    for t in taken:
        valid &= (gx + bw + clearance <= t[0]) | (t[2] + clearance <= gx) | (gy + bh + clearance <= t[1]) | (t[3] + clearance <= gy)
    if not valid.any():
        return None
    cost = np.where(valid, cost, np.inf)
    i = int(np.argmin(cost))
    iy, ix = divmod(i, cost.shape[1])
    return Spot(int(gx[iy, ix]), int(gy[iy, ix]), float(spill[iy, ix]), False)


def find_gutter_spot(
    bw: int,
    bh: int,
    rect: tuple[int, int, int, int],
    taken: list[tuple[int, int, int, int]],
    anchor_x: int,
    clearance: int,
    *,
    avail: int,
    pad: int = 14,
) -> Spot | None:
    """A spot in the strip of `avail` px just below `rect`, nearest the speaker's side, stacked downward
    past any bubble already there. None when the strip is too short for the box."""
    rx, ry, rw, rh = rect
    bottom = ry + rh
    xs = sorted(range(rx + pad, rx + rw - bw - pad + 1, max(4, round(rw * 0.025))), key=lambda x: (abs(x + bw / 2 - anchor_x), x))
    if not xs:
        xs = [rx + max((rw - bw) // 2, 0)]
    y = bottom + pad
    while y + bh <= bottom + avail:
        for x in xs:
            box = (x, y, x + bw, y + bh)
            if not any(not (box[2] + clearance <= t[0] or t[2] + clearance <= box[0] or box[3] + clearance <= t[1] or t[3] + clearance <= box[1]) for t in taken):
                return Spot(x, y, 0.0, True)
        y += max(6, bh // 6)
    return None
