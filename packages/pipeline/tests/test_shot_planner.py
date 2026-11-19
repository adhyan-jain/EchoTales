"""Shot planner: the decision table row by row, the capability limits, tiling and budget properties."""

from __future__ import annotations

import itertools
from dataclasses import replace
from types import SimpleNamespace

import pytest
from echotales.core.enums import SpanType
from echotales.pipeline.render.direction import PanelDirection
from echotales.pipeline.render.director import _pan_direction
from echotales.pipeline.render.plan import PanelPlan, PlanCastMember
from echotales.pipeline.render.shots import (
    CLOUD_ANIME,
    DECISION_TABLE,
    LOCAL_LTX,
    STILLS,
    MotionLevel,
    PairDifference,
    ShotBudget,
    ShotFacts,
    ShotMode,
    ShotsSchemaError,
    decide,
    load_shots,
    pair_difference,
    plan_shots,
    summarise,
    write_shots,
)
from echotales.pipeline.screenplay.schema import CameraMove, Transition
from echotales.pipeline.voice.timing import LineTiming
from hypothesis import given, settings
from hypothesis import strategies as st

BIG = ShotBudget(max_generated_seconds=10_000, max_clips=10_000)
DLG = SpanType.DIALOGUE.value
DESC = SpanType.NARRATION_DESCRIPTION.value
ACT = SpanType.NARRATION_ACTION.value


def panel(seq, blocks, *, scene=0, cast=("a",), loc="yard", slot="scene", shot="medium",
          action="", expression="", direction=True, state=None):
    d = PanelDirection(shot=shot, action=action, expression=expression, setting="mist, stone") \
        if direction else None
    return PanelPlan(
        novel_id="n", chapter=1.0, panel_seq=seq, panel_id=f"n:1:{seq}", scene_index=scene,
        scene_state_id=state if state is not None else f"s{scene}", slot_kind=slot,
        lead_block=blocks[0], block_indexes=list(blocks),
        cast=[PlanCastMember(self_id=c) for c in cast], location=loc, direction=d,
        prompt="p", engine="stub", width=8, height=8, seed=1, image_path="x.png", cache_key="k",
        provenance="generated",
    )


def timing(spec):
    """spec: list of (block, seconds, span_type, speaker[, text])."""
    out, t = [], 0.0
    for i, row in enumerate(spec):
        block, sec, stype, spk = row[:4]
        text = row[4] if len(row) > 4 else ""
        out.append(LineTiming(
            chapter=1.0, order=i, span_id=f"sp{i}", block_index=block, speaker_id=spk,
            speaker_label=spk, span_type=stype, text=text, audio_path="x.wav", duration=sec,
            start_gapless=t, end_gapless=t + sec, start_gapped=t, end_gapped=t + sec,
        ))
        t += sec
    return out


def one(panels, lines, cap=LOCAL_LTX, budget=BIG, **kw):
    return plan_shots(panels, lines, cap, budget, **kw)


# ----------------------------------------------------------------- one test per table row


def facts(**kw):
    base = dict(cap=LOCAL_LTX, duration=5.0, slot_kind="scene", has_cast=True, next_pair=None,
                dialogue_exchange=False)
    return ShotFacts(**{**base, **kw})


@pytest.mark.parametrize("kw,row", [
    (dict(cap=STILLS), "R1_no_engine"),
    (dict(duration=0.5), "R2_too_short"),
    (dict(slot_kind="crowd"), "R3_crowd"),
    (dict(has_cast=False), "R4_no_characters"),
    (dict(slot_kind="establishing", has_cast=False), "R5_ambient_establishing"),
    (dict(cap=CLOUD_ANIME, next_pair=PairDifference.SAME_SHOT), "R6_interpolate_next_panel"),
    (dict(dialogue_exchange=True), "R7_dialogue_push_in"),
    (dict(), "R8_animate_single"),
    (dict(cap=replace(LOCAL_LTX, supports_single_image=False)), "R9_hold_default"),
])
def test_each_table_row_is_reachable(kw, row):
    assert decide(facts(**kw)).id == row


def test_table_covers_every_row_once_in_order():
    ids = [r.id for r in DECISION_TABLE]
    assert ids == sorted(ids) and len(set(ids)) == 9


def test_r1_stills_is_all_hold_with_todays_pan_rule():
    ps = [panel(0, [1]), panel(1, [2]), panel(2, [3, 4])]
    ls = timing([(1, 3, DLG, "x"), (2, 3, DESC, "n"), (3, 2, ACT, "n"), (4, 2, ACT, "n")])
    shots = one(ps, ls, STILLS)
    assert [s.mode for s in shots] == [ShotMode.HOLD] * 3
    expect = {"zoom_in": CameraMove.SLOW_PUSH_IN, "zoom_out": CameraMove.PULL_OUT,
              "pan_left": CameraMove.PAN_LEFT, "pan_right": CameraMove.PAN_RIGHT}
    for s, block, stype in [(shots[0], 1, SpanType.DIALOGUE), (shots[1], 2, SpanType.NARRATION_DESCRIPTION),
                            (shots[2], 3, SpanType.NARRATION_ACTION)]:
        today = _pan_direction([SimpleNamespace(span_type=stype)], block)
        assert s.camera_move == expect[today]
    assert all(s.generated_seconds == 0 and s.fallback.camera_move == s.camera_move for s in shots)


def test_r2_short_shot_holds():
    (s,) = one([panel(0, [1])], timing([(1, 0.4, DLG, "x")]))
    assert s.mode is ShotMode.HOLD and "row=R2_too_short" in s.reasons


def test_r3_crowd_never_animated():
    (s,) = one([panel(0, [1], slot="crowd")], timing([(1, 5, ACT, "n")]), CLOUD_ANIME)
    assert s.mode is ShotMode.HOLD


def test_r4_no_characters_holds():
    (s,) = one([panel(0, [1], cast=())], timing([(1, 5, DESC, "n")]))
    assert s.mode is ShotMode.HOLD


def test_r5_establishing_gets_ambient_only_even_for_strong_beats():
    p = panel(0, [1], slot="establishing", cast=(), action="sword clash explosion")
    (s,) = one([p], timing([(1, 5, DESC, "n")]), CLOUD_ANIME)
    assert s.mode is ShotMode.ANIMATE and s.motion is MotionLevel.SUBTLE
    assert "no people" in s.motion_prompt and "sword" not in s.motion_prompt


def test_r6_cloud_interpolates_same_scene_and_cuts_across_scene_change():
    a, b = panel(0, [1], shot="wide"), panel(1, [2], shot="close")
    c = panel(2, [3], scene=1)
    ls = timing([(1, 3, DLG, "x"), (2, 3, DLG, "x"), (3, 3, DLG, "x")])
    s = one([a, b, c], ls, CLOUD_ANIME)
    assert s[0].mode is ShotMode.INTERPOLATE and s[0].end_panel_id == b.panel_id
    assert s[0].pair_difference is PairDifference.SAME_SCENE_SAME_CAST
    assert s[0].generated_start == pytest.approx(s[0].duration - s[0].generated_seconds)
    assert s[0].transition_to_next is Transition.CUT
    assert s[1].mode is not ShotMode.INTERPOLATE or s[1].end_panel_id is None
    assert s[1].pair_difference is PairDifference.ANY
    assert s[1].transition_to_next is Transition.DISSOLVE


def test_ltx_never_interpolates_between_two_panels():
    a, b = panel(0, [1], shot="medium"), panel(1, [2], shot="medium")  # even SAME_SHOT
    assert pair_difference(a, b) is PairDifference.SAME_SHOT
    s = one([a, b], timing([(1, 3, DLG, "x"), (2, 3, DLG, "x")]))
    assert all(x.end_panel_id is None for x in s)
    assert any("exceeds engine SAME_FRAME_DERIVED: cut" in r for r in s[0].reasons)


def test_r7_exchange_on_one_panel_under_ltx_pushes_in_to_derived_end():
    p = [panel(0, [1, 2]), panel(1, [3], shot="close")]
    ls = timing([(1, 3, DLG, "x"), (2, 3, DLG, "y"), (3, 3, DLG, "x")])
    s = one(p, ls)
    assert s[0].mode is ShotMode.INTERPOLATE and s[0].end_derived is not None
    assert s[0].end_panel_id is None and s[0].generated_start == 0.0
    assert "push-in" in s[0].motion_prompt


def test_r8_monologue_generates_one_clip_and_holds_the_rest():
    p = panel(0, [1], action="standing, looking_up", expression="calm_expression")
    (s,) = one([p], timing([(1, 20, DLG, "x")]))
    assert s.mode is ShotMode.ANIMATE
    assert s.generated_seconds == pytest.approx(97 / 24) and s.frames == 97
    assert s.hold_seconds == pytest.approx(20 - 97 / 24)
    assert any("hold the rest" in r for r in s.reasons)
    assert "looking up" in s.motion_prompt and "_" not in s.motion_prompt


def test_r9_first_last_only_engine_holds_without_exchange():
    cap = replace(LOCAL_LTX, supports_single_image=False)
    (s,) = one([panel(0, [1])], timing([(1, 5, DLG, "x")]), cap)
    assert s.mode is ShotMode.HOLD


# ----------------------------------------------------------------- motion, prompt, budget


def test_strong_action_capped_to_subtle_under_ltx_with_reason():
    p = panel(0, [1], action="sword_clash, weapons_drawn")
    (s,) = one([p], timing([(1, 5, ACT, "n")]))
    assert s.motion_requested is MotionLevel.STRONG and s.motion is MotionLevel.SUBTLE
    assert "motion capped STRONG->SUBTLE by engine" in s.reasons
    (c,) = one([p], timing([(1, 5, ACT, "n")]), CLOUD_ANIME)
    assert c.motion is MotionLevel.STRONG


def test_delivery_markers_and_emotion_raise_motion():
    p = panel(0, [1])
    (a,) = one([p], timing([(1, 5, DLG, "x", 'he shouted, "Stop!"')]), CLOUD_ANIME)
    assert a.motion_requested >= MotionLevel.MODERATE
    (b,) = one([p], timing([(1, 5, DLG, "x")]), CLOUD_ANIME, emotions={"sp0": ("anger", 3)})
    assert b.motion_requested is MotionLevel.STRONG


def test_no_direction_means_no_prompt():
    (s,) = one([panel(0, [1], direction=False)], timing([(1, 5, DLG, "x")]))
    assert s.mode is ShotMode.ANIMATE and s.motion_prompt == ""
    assert "no direction: no motion prompt" in s.reasons


def test_zero_budget_is_all_hold_and_records_why():
    ps = [panel(0, [1]), panel(1, [2], scene=1)]
    ls = timing([(1, 5, DLG, "x"), (2, 5, DLG, "x")])
    for b in (ShotBudget(0, 10), ShotBudget(100, 0)):
        s = one(ps, ls, CLOUD_ANIME, b)
        assert all(x.mode is ShotMode.HOLD for x in s)
        assert all(any("budget exhausted" in r for r in x.reasons) for x in s)
        assert all(x.fallback.camera_move == x.camera_move for x in s)


def test_budget_prefers_stronger_motion():
    ps = [panel(0, [1]), panel(1, [2], scene=1, action="sword_clash")]
    ls = timing([(1, 3, DLG, "x"), (2, 3, DLG, "x")])
    s = one(ps, ls, CLOUD_ANIME, ShotBudget(100, 1))
    assert [x.mode for x in s] == [ShotMode.HOLD, ShotMode.ANIMATE]


def test_summarise_estimate():
    ps = [panel(0, [1]), panel(1, [2], scene=1)]
    s = one(ps, timing([(1, 20, DLG, "x"), (2, 2, DLG, "x")]))
    out = summarise(s, LOCAL_LTX)
    assert out["modes"]["ANIMATE"] == 2 and out["clips"] == 2
    assert out["generated_seconds"] == pytest.approx(97 / 24 + 2, abs=1e-3)
    assert out["estimate_wall_seconds"] == (2 * (17 + 9), 2 * (17 + 50))


def test_uncovered_voiced_block_rides_on_previous_panel():
    ps = [panel(0, [1]), panel(1, [5])]
    s = one(ps, timing([(1, 2, DLG, "x"), (3, 2, DLG, "x"), (5, 2, DLG, "x")]), STILLS)
    assert s[0].block_indexes == [1, 3] and s[1].block_indexes == [5]
    assert any("carried" in r for r in s[0].reasons)


def test_interleaved_panels_come_back_as_cut_backs():
    """RI ch1 v55: one image holds blocks 1 and 3, another block 2. The planner used to refuse this."""
    ps = [panel(0, [1, 3]), panel(1, [2])]
    ls = timing([(1, 2, DLG, "x"), (2, 2, DLG, "y"), (3, 2, DLG, "x")])
    s = one(ps, ls, STILLS)
    assert [x.panel_id for x in s] == ["n:1:0", "n:1:1", "n:1:0"]
    assert [x.shot_index for x in s] == [0, 1, 2]
    assert s[0].end == s[1].start and s[1].end == s[2].start and s[-1].end == ls[-1].end_gapless
    assert [x.block_indexes for x in s] == [[1], [2], [3]]


# ----------------------------------------------------------------- io


def test_round_trip_and_schema(tmp_path):
    ps = [panel(0, [1, 2]), panel(1, [3], shot="close")]
    s = one(ps, timing([(1, 3, DLG, "x"), (2, 3, DLG, "y"), (3, 3, DLG, "x")]), CLOUD_ANIME)
    write_shots(tmp_path, s)
    assert load_shots(tmp_path) == s
    f = tmp_path / "shots.jsonl"
    f.write_text(f.read_text().replace('"schema_version":1', '"schema_version":7'))
    with pytest.raises(ShotsSchemaError):
        load_shots(tmp_path)


# ----------------------------------------------------------------- properties

CAPS = st.sampled_from([
    STILLS, LOCAL_LTX, CLOUD_ANIME,
    replace(CLOUD_ANIME, max_pair_difference=PairDifference.ANY, max_motion=MotionLevel.MODERATE),
    replace(LOCAL_LTX, max_pair_difference=PairDifference.SAME_SHOT, max_frames=25),
    replace(LOCAL_LTX, supports_single_image=False),
    replace(CLOUD_ANIME, supports_first_last=False),
])


@st.composite
def chapters(draw):
    n = draw(st.integers(1, 8))
    panels, lines, block = [], [], 0
    scene = 0
    for i in range(n):
        if draw(st.booleans()):
            scene += 1
        nb = draw(st.integers(1, 3))
        first = block + draw(st.integers(0, 2))
        blocks = list(range(first, first + nb))
        block = first + nb
        panels.append(panel(
            i, blocks, scene=scene,
            cast=draw(st.sampled_from([(), ("a",), ("a", "b")])),
            loc=draw(st.sampled_from(["yard", "hall"])),
            slot=draw(st.sampled_from(["establishing", "closeup", "scene", "crowd"])),
            shot=draw(st.sampled_from(["wide", "medium", "close"])),
            action=draw(st.sampled_from(["", "sword_clash", "walking", "mist"])),
            direction=draw(st.booleans()),
        ))
        for b in blocks:
            for _ in range(draw(st.integers(0, 3))):
                lines.append((b, draw(st.floats(0.05, 30, allow_nan=False)),
                              draw(st.sampled_from([DLG, DESC, ACT])), draw(st.sampled_from(["x", "y", "n"]))))
    return panels, timing(lines)


BUDGETS = st.builds(
    ShotBudget, max_generated_seconds=st.floats(0, 60), max_clips=st.integers(0, 6),
    base_seed=st.integers(0, 5),
)


@settings(max_examples=300, deadline=None)
@given(chapters(), CAPS, BUDGETS)
def test_properties_capability_conservation_budget_determinism(ch, cap, budget):
    panels, lines = ch
    shots = plan_shots(panels, lines, cap, budget)
    again = plan_shots(list(panels), list(lines), cap, budget)
    assert shots == again  # f: same inputs, same plan and seeds

    by_id = {p.panel_id: p for p in panels}
    for s in shots:
        # a: never exceed the capability
        if not cap.can_generate:
            assert s.mode is ShotMode.HOLD
        assert s.motion <= cap.max_motion
        assert s.frames <= cap.max_frames
        assert s.generated_seconds <= cap.max_clip_seconds + 1e-9
        assert s.generated_seconds <= s.duration + 1e-9
        if s.mode is ShotMode.INTERPOLATE and s.end_panel_id:
            nxt = by_id[s.end_panel_id]
            assert pair_difference(by_id[s.panel_id], nxt) <= cap.max_pair_difference
            assert cap.supports_first_last
        if s.mode is ShotMode.INTERPOLATE:
            assert (s.end_panel_id is None) != (s.end_derived is None)
        if s.mode is ShotMode.HOLD:
            assert s.generated_seconds == 0 and s.fallback.camera_move is not None
        # c: no character motion on crowds or empty casts, except ambient on establishing
        p = by_id[s.panel_id]
        if s.mode is not ShotMode.HOLD and (not p.cast or p.slot_kind == "crowd"):
            assert p.slot_kind == "establishing" and s.motion is MotionLevel.SUBTLE
        if p.slot_kind == "crowd":
            assert s.mode is ShotMode.HOLD

    # b: tiling and block coverage
    total = sum(t.duration for t in lines)
    if not lines:
        assert shots == []  # no audio, no shot: a panel nobody speaks over is not a zero-length shot
        return
    assert shots[0].start == 0.0
    for x, y in itertools.pairwise(shots):
        assert x.end == y.start
    assert shots[-1].end == pytest.approx(total)
    assert sum(s.duration for s in shots) == pytest.approx(total)
    assert sorted(i for s in shots for i in s.span_ids) == sorted(t.span_id for t in lines)
    covered = [b for s in shots for b in s.block_indexes]
    assert len(covered) == len(set(covered))
    shown = {s.panel_id for s in shots}
    assert set(covered) >= {b for p in panels if p.panel_id in shown for b in p.block_indexes} | {t.block_index for t in lines}

    # e: budget
    clips = [s for s in shots if s.mode is not ShotMode.HOLD]
    assert len(clips) <= budget.max_clips
    assert sum(s.generated_seconds for s in clips) <= budget.max_generated_seconds + 1e-9
    assert summarise(shots, cap)["clips"] == len(clips)
