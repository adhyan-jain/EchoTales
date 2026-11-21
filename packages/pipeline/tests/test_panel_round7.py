"""Panel quality round 7: shot variety in the crowd and lone-lead scenes (EVOLUTION 4.182).

Round 6 fixed the staging but drew 5 of 13 cliff panels as one side view and the LotM corner view as the same chest-up man at the
desk. The rotation below pins that a run in either scene type is several different pictures."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

from echotales.pipeline.render import framing as fr
from echotales.pipeline.render.compiler import trim_staging


def _crowd_run(n: int) -> list[fr.Framing]:
    state = fr.FramingState()
    return [fr.plan_framing("They did not move.", names=["Fang Yuan"], crowd_in_scene=True, state=state, opens_chapter=False) for _ in range(n)]


def test_a_crowd_scene_rotates_through_different_views_and_no_view_repeats_back_to_back() -> None:
    out = _crowd_run(10)
    keys = [(f.size, f.focus) for f in out]
    assert all(a != b for a, b in pairwise(keys))
    assert Counter(keys).most_common(1)[0][1] / len(keys) <= 0.35
    assert {"behind", "reverse", "overview", "low"} <= {f.focus for f in out}


def test_the_first_crowd_panel_is_still_the_side_view() -> None:
    first = _crowd_run(1)[0]
    assert (first.focus, first.subject) == ("behind", "crowd")


def test_the_reverse_view_leaves_the_lead_out_and_the_overview_makes_him_a_small_lone_figure() -> None:
    rev = fr.framing_sentence(fr.Framing("medium", focus="reverse", subject="crowd"), "Fang Yuan")
    assert "Fang Yuan" not in rev and "glaring" in rev
    over = fr.framing_sentence(fr.Framing("wide", "high-angle", "overview", "crowd"), "Fang Yuan")
    assert "Fang Yuan" in over and "small" in over


def test_a_lone_lead_run_rotates_views_with_no_view_more_than_twice_in_a_row() -> None:
    state = fr.FramingState()
    out = [fr.plan_framing("He sat at the desk.", names=["Klein"], others_present=False, state=state, opens_chapter=False) for _ in range(12)]
    keys = [(f.size, f.focus) for f in out]
    for i in range(2, len(keys)):
        assert not (keys[i] == keys[i - 1] == keys[i - 2])
    assert {"down", "profile"} <= {f.focus for f in out}


def test_a_view_with_nobody_or_one_person_keeps_only_the_place_of_the_staging() -> None:
    st = "Set: a cliff. Blocking: X stands alone; the crowd stands in rows. Light: sun."
    for focus in ("reverse", "overview", "low", "down", "profile"):
        out = trim_staging(st, focus, "medium", "crowd")
        assert "Blocking" not in out and "Set" in out and "Light" in out
