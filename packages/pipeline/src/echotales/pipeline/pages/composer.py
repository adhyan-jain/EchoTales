"""Page composer: ordered panels in, page layouts out (roadmap M1 step 1).

**Why this exists.** The pipeline made loose panel images, and fans share pages. Layout is chosen
by rule from what the panel is (a reveal, an establishing shot, a dialogue exchange), never by a
model, and the function is pure so the same chapter always gives the same pages and a reviewer's
"page 4 looks wrong" is reproducible.

Templates are written in reading order. A manga page is the same template placed from the right,
so RTL costs nothing in the layout rules and every other module reads `order`, not `x`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

PAGE_W = 1200
PAGE_H = 1800
MARGIN = 60
GUTTER = 24
WEBTOON_W = 800
WEBTOON_GUTTER = 48

FORMATS = ("manga", "comic", "webtoon")


class PanelRole(StrEnum):
    SPLASH = "SPLASH"
    ESTABLISHING = "ESTABLISHING"
    EXCHANGE = "EXCHANGE"
    SCENE = "SCENE"


@dataclass(frozen=True, slots=True)
class ComposerPanel:
    panel_id: str
    role: PanelRole
    #: The source image size; only the webtoon strip uses it, to keep each panel's own shape.
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PlacedPanel:
    panel_id: str
    x: int
    y: int
    w: int
    h: int
    #: Reading order on the page, 0 first. The one thing a reader of the layout may rely on.
    order: int


@dataclass(frozen=True, slots=True)
class PageLayout:
    index: int
    width: int
    height: int
    template: str
    panels: tuple[PlacedPanel, ...]


@dataclass(frozen=True, slots=True)
class PageFacts:
    """What `assign_roles` may look at for one panel."""

    scene_index: int
    slot_kind: str
    #: 0-3, `director._delivery_intensity` over the panel's dialogue.
    intensity: int
    dialogue_lines: int


#: A line delivered at this intensity (HEIGHTENED) is what a reveal looks like in the text; below it a
#: splash would spend a whole page on a beat the prose did not stress (decisions: delivery overrides scene sentiment).
SPLASH_INTENSITY = 3


def assign_roles(facts: Sequence[PageFacts]) -> list[PanelRole]:
    """Splash: the first strongest panel of each scene when it reaches `SPLASH_INTENSITY`.
    Establishing: an establishing slot. Exchange: two or more dialogue lines. Otherwise scene."""
    peak: dict[int, int] = {}
    for i, f in enumerate(facts):
        if f.intensity >= SPLASH_INTENSITY and (f.scene_index not in peak or f.intensity > facts[peak[f.scene_index]].intensity):
            peak[f.scene_index] = i
    roles: list[PanelRole] = []
    for i, f in enumerate(facts):
        if peak.get(f.scene_index) == i:
            roles.append(PanelRole.SPLASH)
        elif f.slot_kind == "establishing":
            roles.append(PanelRole.ESTABLISHING)
        elif f.dialogue_lines >= 2:
            roles.append(PanelRole.EXCHANGE)
        else:
            roles.append(PanelRole.SCENE)
    return roles


# --------------------------------------------------------------------------- templates

#: (row height weight, cells in the row)
Rows = list[tuple[float, int]]


def _grid_rows(n: int, odd_page: bool) -> Rows:
    if n == 1:
        return [(1.0, 1)]
    if n == 4 and odd_page:
        # Alternate the 2x2 with a 1-2-1 so consecutive pages do not look stamped.
        return [(1.0, 1), (1.4, 2), (1.0, 1)]
    rows: Rows = [(1.0, 2)] * (n // 2)
    return rows + ([(1.0, 1)] if n % 2 else [])


def _rows(template: str, n: int, page_index: int) -> Rows:
    if template == "splash":
        return [(1.0, 1)]
    if template == "stack":
        return [(1.0, 1)] * n
    if template == "wide":
        return [(0.45, 1)] + (_grid_rows(n - 1, False) if n > 1 else [])
    return _grid_rows(n, page_index % 2 == 1)


#: How many panels a page of each template takes.
CAPACITY = {"splash": 1, "wide": 5, "stack": 3, "grid": 4}


def _take(panels: Sequence[ComposerPanel], i: int) -> tuple[str, int]:
    """The template for the page that starts at `panels[i]`, and how many panels it holds."""
    head = panels[i].role
    if head is PanelRole.SPLASH:
        return "splash", 1
    stop = (PanelRole.SPLASH, PanelRole.ESTABLISHING)
    if head is PanelRole.ESTABLISHING:
        template = "wide"
    elif head is PanelRole.EXCHANGE and i + 1 < len(panels) and panels[i + 1].role is PanelRole.EXCHANGE:
        template, stop = "stack", (PanelRole.SPLASH, PanelRole.ESTABLISHING, PanelRole.SCENE)
    else:
        template = "grid"
    n = 1
    while n < CAPACITY[template] and i + n < len(panels) and panels[i + n].role not in stop:
        n += 1
    return template, n


def _place(rows: Rows, ids: Sequence[str], *, rtl: bool, page_index: int, template: str) -> PageLayout:
    inner_w = PAGE_W - 2 * MARGIN
    inner_h = PAGE_H - 2 * MARGIN - GUTTER * (len(rows) - 1)
    total = sum(w for w, _ in rows)
    placed: list[PlacedPanel] = []
    y = MARGIN
    k = 0
    for ri, (weight, cells) in enumerate(rows):
        h = round(inner_h * weight / total) if ri < len(rows) - 1 else PAGE_H - MARGIN - y
        cell_w = (inner_w - GUTTER * (cells - 1)) // cells
        for c in range(cells):
            col = cells - 1 - c if rtl else c
            x = MARGIN + col * (cell_w + GUTTER)
            # The last column absorbs the rounding so a row always reaches the right margin.
            w = cell_w if col < cells - 1 else PAGE_W - MARGIN - x
            placed.append(PlacedPanel(ids[k], x, y, w, h, k))
            k += 1
        y += h + GUTTER
    return PageLayout(page_index, PAGE_W, PAGE_H, template, tuple(placed))


def _webtoon(panels: Sequence[ComposerPanel]) -> list[PageLayout]:
    placed: list[PlacedPanel] = []
    y = WEBTOON_GUTTER
    for k, p in enumerate(panels):
        if p.role is PanelRole.SPLASH:
            ratio = 1.6
        elif p.role is PanelRole.ESTABLISHING:
            ratio = 0.6
        else:
            ratio = min(max(p.height / p.width if p.width else 1.0, 0.75), 1.5)
        h = round(WEBTOON_W * ratio)
        placed.append(PlacedPanel(p.panel_id, 0, y, WEBTOON_W, h, k))
        y += h + WEBTOON_GUTTER
    return [PageLayout(1, WEBTOON_W, y, "webtoon", tuple(placed))]


def compose_pages(panels: Sequence[ComposerPanel], fmt: str) -> list[PageLayout]:
    """Lay the chapter's panels out as pages. Pure: no files, no randomness."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown page format {fmt!r}; expected one of {', '.join(FORMATS)}")
    if not panels:
        return []
    if fmt == "webtoon":
        return _webtoon(panels)
    pages: list[PageLayout] = []
    i = 0
    while i < len(panels):
        template, n = _take(panels, i)
        ids = [p.panel_id for p in panels[i : i + n]]
        pages.append(_place(_rows(template, n, len(pages)), ids, rtl=fmt == "manga", page_index=len(pages) + 1, template=template))
        i += n
    return pages
