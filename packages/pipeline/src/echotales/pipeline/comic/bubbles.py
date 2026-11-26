"""Speech bubbles from OCR lines, plus who they point at.

OCR gives text lines; this groups them into bubbles, finds the bubble's filled region by colour, decides speech,
narration box or sound effect, finds the tail tip, and samples the pixels the tail points at so characters can be
clustered across panels.

Why the colour flood and not a learned bubble detector: Magi v2 (the candidate model) is licensed for
non-commercial use only, and a flat-fill flood is deterministic and testable. The cost is that a bubble drawn over
art of nearly its own colour, or one with an outline broken by overlap, falls back to `sfx`/no tail.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from echotales.pipeline.comic.ocr import TextLine
from echotales.pipeline.comic.panels import Panel
from PIL import Image
from scipy import ndimage

#: Per-channel distance from the bubble's fill colour that still counts as the same fill.
FILL_TOL = 34
#: Share of the text box that must be fill (the rest is the glyphs themselves).
MIN_FILL_SHARE = 0.55
#: Fill region must be at least this many times the text box (a bubble is bigger than its text) ...
MIN_AREA_RATIO = 1.3
#: ... and at most this many (a "bubble" that large is background that happens to match).
MAX_AREA_RATIO = 14.0
#: Rectangular captions fill their bounding box; ellipses fill pi/4 = 0.785 of it.
RECT_SOLIDITY = 0.9
#: Mahalanobis radius of a uniform ellipse is about 2; beyond this a pixel is a tail, not the body.
TAIL_MAHALANOBIS = 2.6
#: Speech lettering is near-black or grey; sound effects are painted in warm colour. A text box with more than this
#: share of vivid warm pixels (hue under 47 degrees, saturation and value over 0.4) is lettering, not speech.
#: Pepper&Carrot "SHSH" sat inside a pale bubble-coloured window and flooded into the real bubble's fill, so the fill
#: test alone called it speech. Measured on 7 text boxes of that comic: effects 0.09-0.26, speech 0.0-0.002. Warm
#: colours only; cool-coloured effects are not caught.
MAX_VIVID_SHARE = 0.04


@dataclass(slots=True)
class Bubble:
    id: str
    panel_index: int
    text: str
    kind: str  # speech | narration | sfx
    text_box: tuple[int, int, int, int]
    box: tuple[int, int, int, int]  # the whole bubble (fill region) or the text box when there is none
    tail: tuple[int, int] | None = None
    #: Colour signature of what the tail points at; None when there is no tail.
    embedding: list[float] | None = None
    confidence: float = 1.0
    speaker: str | None = None
    order: int = 0
    #: Pixels of this bubble (page coordinates), kept in memory for the clean-plate mask; never serialised.
    mask: np.ndarray | None = field(default=None, repr=False, compare=False)


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _group_lines(lines: list[TextLine]) -> list[list[TextLine]]:
    """Stack lines that overlap horizontally and sit within about a line-height of each other."""
    groups: list[list[TextLine]] = []
    for ln in sorted(lines, key=lambda l: (l.box[1], l.box[0])):
        h = ln.box[3] - ln.box[1]
        for g in groups:
            gb = _union([l.box for l in g])
            overlap = min(gb[2], ln.box[2]) - max(gb[0], ln.box[0])
            width = min(gb[2] - gb[0], ln.box[2] - ln.box[0])
            gap = ln.box[1] - gb[3]
            if width > 0 and overlap / width > 0.3 and -h * 0.5 <= gap <= h * 1.0:
                g.append(ln)
                break
        else:
            groups.append([ln])
    return groups


def _panel_of(box, panels: list[Panel]) -> int:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for p in panels:
        if p.box[0] <= cx < p.box[2] and p.box[1] <= cy < p.box[3]:
            return p.index
    # Lettering in a gutter belongs to the nearest panel centre.
    return min(panels, key=lambda p: (cx - (p.box[0] + p.box[2]) / 2) ** 2 + (cy - (p.box[1] + p.box[3]) / 2) ** 2).index


def _vivid_share(rgb: np.ndarray) -> float:
    hsv = np.asarray(Image.fromarray(rgb.reshape(1, -1, 3).astype(np.uint8)).convert("HSV"), dtype=float).reshape(-1, 3) / 255
    return float(((hsv[:, 1] > 0.4) & (hsv[:, 2] > 0.4) & (hsv[:, 0] < 0.13)).mean())


def _fill_region(arr: np.ndarray, tbox) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    x0, y0, x1, y1 = tbox
    patch = arr[y0:y1, x0:x1].reshape(-1, 3)
    if patch.size == 0:
        return None
    fill = np.median(patch, axis=0)
    if _vivid_share(patch) > MAX_VIVID_SHARE:
        return None
    near = np.abs(patch - fill).max(axis=1) <= FILL_TOL
    if near.mean() < MIN_FILL_SHARE:
        return None
    mask = np.abs(arr - fill).max(axis=2) <= FILL_TOL
    # Glyphs are holes in the fill; close them so the text box sits inside one component.
    mask = ndimage.binary_closing(mask, iterations=2)
    labels, _ = ndimage.label(mask)
    inside = labels[y0:y1, x0:x1]
    ids, counts = np.unique(inside[inside > 0], return_counts=True)
    if len(ids) == 0:
        return None
    comp = ndimage.binary_fill_holes(labels == ids[np.argmax(counts)])
    area = int(comp.sum())
    text_area = (x1 - x0) * (y1 - y0)
    if not (MIN_AREA_RATIO * text_area <= area <= MAX_AREA_RATIO * text_area):
        return None
    ys, xs = np.nonzero(comp)
    return comp, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _tail_tip(comp: np.ndarray) -> tuple[int, int] | None:
    ys, xs = np.nonzero(comp)
    pts = np.stack([xs, ys], axis=1).astype(float)
    mean = pts.mean(axis=0)
    cov = np.cov((pts - mean).T) + np.eye(2) * 1e-6
    d = np.einsum("ij,jk,ik->i", pts - mean, np.linalg.inv(cov), pts - mean)
    i = int(np.argmax(d))
    return (int(pts[i, 0]), int(pts[i, 1])) if np.sqrt(d[i]) > TAIL_MAHALANOBIS else None


def _signature(arr: np.ndarray, tip, centre, size: int = 56) -> list[float]:
    """Normalised 4x4x4 colour histogram of the patch just beyond the tail tip, away from the bubble."""
    v = np.array(tip, dtype=float) - np.array(centre, dtype=float)
    v /= (np.linalg.norm(v) or 1.0)
    cx, cy = (np.array(tip, dtype=float) + v * size * 0.6).astype(int)
    h, w = arr.shape[:2]
    patch = arr[max(0, cy - size // 2): min(h, cy + size // 2), max(0, cx - size // 2): min(w, cx + size // 2)]
    if patch.size == 0:
        patch = arr[max(0, tip[1] - 8): tip[1] + 8, max(0, tip[0] - 8): tip[0] + 8]
    q = (patch.reshape(-1, 3) // 64).astype(int)
    hist = np.bincount(q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2], minlength=64).astype(float)
    return (hist / max(hist.sum(), 1.0)).tolist()


def detect_bubbles(
    image: Image.Image, lines: list[TextLine], panels: list[Panel], *, rtl: bool = False
) -> list[Bubble]:
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)
    found: list[Bubble] = []
    for group in _group_lines(lines):
        tbox = _union([l.box for l in group])
        text = " ".join(l.text for l in group)
        region = _fill_region(arr, tbox)
        kind, tail, emb, box, mask = "sfx", None, None, tbox, None
        if region is not None:
            comp, box = region
            mask = comp
            solidity = comp.sum() / max((box[2] - box[0]) * (box[3] - box[1]), 1)
            if solidity >= RECT_SOLIDITY:
                kind = "narration"
            else:
                kind = "speech"
                tail = _tail_tip(comp)
                if tail is not None:
                    ys, xs = np.nonzero(comp)
                    emb = _signature(arr, tail, (xs.mean(), ys.mean()))
        found.append(Bubble(
            id="", panel_index=_panel_of(tbox, panels), text=text, kind=kind, text_box=tbox, box=box,
            tail=tail, embedding=emb, confidence=min(l.confidence for l in group), mask=mask,
        ))
    # Reading order: panel by panel; inside a panel top to bottom, ties on a shared row go left to right (right to
    # left for manga). A row is bubbles whose tops sit within half a bubble height of each other.
    found.sort(key=lambda b: (b.panel_index, b.box[1]))
    ordered: list[Bubble] = []
    i = 0
    while i < len(found):
        j = i + 1
        while j < len(found) and found[j].panel_index == found[i].panel_index and \
                found[j].box[1] - found[i].box[1] < 0.5 * (found[i].box[3] - found[i].box[1]):
            j += 1
        ordered.extend(sorted(found[i:j], key=lambda b: -b.box[0] if rtl else b.box[0]))
        i = j
    for n, b in enumerate(ordered):
        b.order = n
    return ordered


def cluster_speakers(embeddings: list, *, threshold: float = 0.45) -> list[int | None]:
    """Greedy clustering of tail-target signatures by half the L1 distance to a running centroid.

    A bubble with no tail (no signature) gets None: it is not guessed into the nearest cluster, because a wrong
    voice is worse than an unattributed one (non-negotiable 9, precision over recall).
    """
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    labels: list[int | None] = []
    for e in embeddings:
        if e is None:
            labels.append(None)
            continue
        v = np.asarray(e, dtype=float)
        v = v / max(v.sum(), 1e-9)
        best, best_d = None, threshold
        for k, c in enumerate(centroids):
            d = 0.5 * float(np.abs(v - c).sum())
            if d < best_d:
                best, best_d = k, d
        if best is None:
            centroids.append(v)
            counts.append(1)
            labels.append(len(centroids) - 1)
        else:
            counts[best] += 1
            centroids[best] += (v - centroids[best]) / counts[best]
            labels.append(best)
    return labels


#: How far past the lettering a bubble's body may reach, per side: a share of the text box width and height. A speech
#: bubble is the text plus a margin, and an ellipse needs at least ~0.21 of each side to enclose the corners; measured
#: on Pepper&Carrot ep01 bubbles the margin is 0.2-0.4 of the width and 0.4-0.9 of the height (short text, tall ellipse).
BUBBLE_PAD_X, BUBBLE_PAD_Y = 0.45, 1.0
#: A tail is thinner than this many pixels across (opening radius); a leak into same-coloured art is wider.
TAIL_MAX_HALF_WIDTH = 7


def trim_bubble_mask(comp: np.ndarray, text_box: tuple[int, int, int, int]) -> np.ndarray:
    """The part of a flooded bubble region that is really the bubble: its body plus its tail.

    The fill flood (`_fill_region`) follows any pixels of the bubble's colour, so a pale bubble sitting on a bright
    window returns the window as well (Pepper&Carrot ep01 page 1: the first bubble's mask swallowed the window frame,
    and inpainting it redrew the window without its bars). The body is the flood clipped to the text box grown by
    `BUBBLE_PAD_*`; what lies outside is kept only if it is thin (narrower than a tail) and attached to the body
    within one text-box length, so tails survive and the wide leak does not."""
    x0, y0, x1, y1 = text_box
    w, h = x1 - x0, y1 - y0
    px, py = int(w * BUBBLE_PAD_X), int(h * BUBBLE_PAD_Y)
    body = np.zeros_like(comp, dtype=bool)
    body[max(0, y0 - py): y1 + py, max(0, x0 - px): x1 + px] = True
    body &= comp
    rest = comp & ~body
    if not rest.any():
        return body
    r = TAIL_MAX_HALF_WIDTH
    yy, xx = np.mgrid[-r: r + 1, -r: r + 1]
    wide = ndimage.binary_opening(rest, structure=(xx**2 + yy**2) <= r * r)
    thin = rest & ~ndimage.binary_dilation(wide, iterations=2)
    near = ndimage.distance_transform_edt(~body) <= max(w, h)
    labels, n = ndimage.label(thin & near, structure=np.ones((3, 3)))
    if n == 0:
        return body
    touching = np.unique(labels[ndimage.binary_dilation(body, iterations=2) & (labels > 0)])
    return body | np.isin(labels, touching[touching > 0])
