"""M1 step 1 (community_roadmap.md): the page composer is a pure function from ordered panels to page layouts."""

from __future__ import annotations

import pytest
from echotales.pipeline.pages.composer import (
    ComposerPanel,
    PageFacts,
    PanelRole,
    assign_roles,
    compose_pages,
)

S, E, X, N = PanelRole.SPLASH, PanelRole.ESTABLISHING, PanelRole.EXCHANGE, PanelRole.SCENE


def _panels(roles: list[PanelRole]) -> list[ComposerPanel]:
    return [ComposerPanel(f"p{i}", r, 512, 768) for i, r in enumerate(roles)]


def test_same_input_gives_same_pages() -> None:
    panels = _panels([E, N, N, X, X, X, S, N, N, N, N, N])
    assert compose_pages(panels, "manga") == compose_pages(panels, "manga")


def test_splash_gets_its_own_full_page() -> None:
    pages = compose_pages(_panels([N, S, N]), "comic")
    splash = next(p for p in pages if p.template == "splash")
    assert [r.panel_id for r in splash.panels] == ["p1"]
    only = splash.panels[0]
    assert only.w > splash.width * 0.8 and only.h > splash.height * 0.8


def test_establishing_leads_a_page_with_a_wide_strip() -> None:
    page = compose_pages(_panels([E, N, N]), "comic")[0]
    assert page.template == "wide"
    first = page.panels[0]
    assert first.panel_id == "p0" and first.w == max(r.w for r in page.panels)
    assert first.w > first.h * 2


def test_dialogue_exchange_stacks_full_width_rows() -> None:
    page = compose_pages(_panels([X, X, X]), "comic")[0]
    assert page.template == "stack"
    assert len({r.x for r in page.panels}) == 1 and len({r.y for r in page.panels}) == 3


def test_other_panels_go_into_a_grid() -> None:
    page = compose_pages(_panels([N, N, N, N]), "comic")[0]
    assert page.template == "grid"
    assert len(page.panels) == 4


def test_manga_reads_right_to_left_and_comic_left_to_right() -> None:
    panels = _panels([N, N, N, N])
    manga = compose_pages(panels, "manga")[0]
    comic = compose_pages(panels, "comic")[0]
    m = sorted(manga.panels, key=lambda r: r.order)
    c = sorted(comic.panels, key=lambda r: r.order)
    assert m[0].x > m[1].x and m[0].y == m[1].y
    assert c[0].x < c[1].x and c[0].y == c[1].y
    assert [r.panel_id for r in m] == [r.panel_id for r in c] == ["p0", "p1", "p2", "p3"]


def test_every_panel_appears_once_in_order_and_rects_do_not_overlap() -> None:
    panels = _panels([E, N, X, X, S, N, N, N, N, N, N, X, E])
    for fmt in ("manga", "comic"):
        pages = compose_pages(panels, fmt)
        ids = [r.panel_id for p in pages for r in sorted(p.panels, key=lambda r: r.order)]
        assert ids == [p.panel_id for p in panels]
        for page in pages:
            for a in page.panels:
                assert a.x >= 0 and a.x + a.w <= page.width and a.y >= 0 and a.y + a.h <= page.height
                for b in page.panels:
                    if a is not b:
                        assert a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y


def test_webtoon_is_one_vertical_strip_with_gutters() -> None:
    pages = compose_pages(_panels([E, N, X, S]), "webtoon")
    assert len(pages) == 1
    strip = pages[0]
    assert strip.height > strip.width * 2
    rects = sorted(strip.panels, key=lambda r: r.order)
    assert [r.panel_id for r in rects] == ["p0", "p1", "p2", "p3"]
    assert all(b.y > a.y + a.h for a, b in zip(rects, rects[1:], strict=False))


def test_unknown_format_is_refused() -> None:
    with pytest.raises(ValueError, match="format"):
        compose_pages(_panels([N]), "scroll")


def test_no_panels_gives_no_pages() -> None:
    assert compose_pages([], "manga") == []


def test_roles_follow_the_rules() -> None:
    facts = [
        PageFacts(scene_index=0, slot_kind="establishing", intensity=0, dialogue_lines=0),
        PageFacts(scene_index=0, slot_kind="scene", intensity=2, dialogue_lines=3),
        PageFacts(scene_index=0, slot_kind="scene", intensity=3, dialogue_lines=1),
        PageFacts(scene_index=0, slot_kind="scene", intensity=3, dialogue_lines=1),
        PageFacts(scene_index=1, slot_kind="closeup", intensity=1, dialogue_lines=0),
    ]
    assert assign_roles(facts) == [E, X, S, N, N]
