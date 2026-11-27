"""Layout invariants of the storyboard webtoon renderer (pages/storyboard_render.py, WEBTOON_GRAMMAR.md).

Runs at 800 px wide with placeholder pictures: geometry and lettering rules do not depend on real art.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _ri_ch1_storyboard import ri_ch1_storyboard
from echotales.pipeline.pages.grammar_lettering import Placed
from echotales.pipeline.pages.storyboard_render import (
    choose_cuts,
    export_storyboard_webtoon,
    render_storyboard_strip,
    render_storyboard_webtoon,
)
from echotales.pipeline.pages.storyboard_style import StyleTable
from echotales.pipeline.storyboard.schema import (
    Layer,
    Letter,
    LetterKind,
    Panel,
    Purpose,
    Shape,
    Storyboard,
)

W = 800


@pytest.fixture(scope="module")
def result():
    return render_storyboard_strip(ri_ch1_storyboard(), {}, StyleTable(width=W))


def test_no_balloon_crosses_a_slice_cut(result):
    assert result.cuts, "fixture is long enough to need cuts"
    for cut in result.cuts:
        for pl in result.placed:
            assert not (pl.extent[1] < cut < pl.extent[3]), (pl.panel_id, pl.kind, cut)


def test_every_letter_placed_or_reported(result):
    sb = ri_ch1_storyboard()
    placed = {(p.panel_id, p.idx) for p in result.placed}
    lost = {(o.panel_id, o.idx) for o in result.overflow if o.reason == "unplaced"}
    for p in sb.panels:
        for i, _ in enumerate(p.letters):
            assert (p.panel_id, i) in placed | lost


def test_placed_letters_stay_inside_the_strip_and_do_not_overlap(result):
    h = result.strip.height
    boxes = [pl.box for pl in result.placed if pl.kind != "sfx"]
    for b in boxes:
        assert b[0] >= 0 and b[2] <= W and b[1] >= 0 and b[3] <= h
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_shapes_have_expected_geometry(result):
    rects = {p.panel_id: p for p in result.panels}
    assert rects["p03"].rect[2] - rects["p03"].rect[0] == W  # wide: full width
    wide_h = rects["p03"].rect[3] - rects["p03"].rect[1]
    tall_h = rects["p02"].rect[3] - rects["p02"].rect[1]
    assert tall_h > 2.5 * wide_h  # tall is much taller than a wide strip
    inset = rects["p22"].rect
    assert inset[2] - inset[0] < W * 0.6
    assert inset[1] < rects["p21"].rect[3]  # an inset overlaps the previous panel's corner
    assert rects["p10"].shape == "text_only"


def test_gutters_follow_pacing(result):
    pans = result.panels
    gaps = {(a.panel_id, b.panel_id): b.rect[1] - a.rect[3] for a, b in itertools.pairwise(pans)}
    assert gaps[("p02", "p03")] > 3 * gaps[("p04", "p05")]  # scene cut vs close-up after close-up


def test_layer_gutter_colours_differ(result):
    pans = {p.panel_id: p for p in result.panels}
    assert sum(result.strip.getpixel((3, pans["p04"].rect[3] + 4))) < 60  # black battle gutter
    r, _, b = result.strip.getpixel((3, pans["p13"].rect[3] + 6))
    assert r > 240 and b < r  # warm gold-to-white memory gutter


def test_style_table_round_trips_through_json():
    t = StyleTable(width=800)
    assert StyleTable.from_dict(json.loads(json.dumps(t.to_dict()))).layers["memory"] == t.layers["memory"]


def test_overlong_text_is_reported_not_dropped():
    long = " ".join(["word"] * 400)
    sb = Storyboard(novel_id="X", chapter=1, panels=[Panel(
        panel_id="a", segment_id="s", layer=Layer.PRESENT, purpose=Purpose.BEAT, shape=Shape.WIDE,
        letters=[Letter(kind=LetterKind.NARRATION, text=long)])])
    res = render_storyboard_strip(sb, {}, StyleTable(width=W))
    assert res.overflow or any(p.idx == 0 for p in res.placed)
    assert all(o.reason in ("truncated", "unplaced") for o in res.overflow)


def test_choose_cuts_avoids_forbidden_rows():
    blocker = Placed("x", 0, "speech", (0, 0, 1, 1), (0, 1300, 100, 1700), None, "t", 20)
    cuts = choose_cuts(6000, [blocker], [], StyleTable(width=W))
    assert cuts and all(not (1300 - 5 < c < 1700 + 5) for c in cuts)


def test_entry_point_writes_slices_contact_and_exports(tmp_path):
    sb = ri_ch1_storyboard()
    sb.panels = sb.panels[:8]
    slices = render_storyboard_webtoon(sb, {}, tmp_path / "out", StyleTable(width=W))
    assert slices and all(p.exists() for p in slices)
    assert (tmp_path / "out" / "contact.png").exists()
    files = export_storyboard_webtoon(slices, tmp_path / "ex", "ch1", ["cbz", "pdf"])
    assert {f.suffix for f in files} == {".cbz", ".pdf"}
