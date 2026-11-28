"""Storyboard director v2 (sb-5): stage scenes, knowledge cards and budget, the v2 rules, the gold checker.

No model, no GPU: plans are canned `LWindow`s and the segment stage's answer is built in the real shape it will have
once segment v3 lands (`SceneAnalysis.time_labels`: one `SegmentTimeLabel` per segment).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from echotales.pipeline.knowledge.common import artifact_id, put_artifact
from echotales.pipeline.segment.cuts import CutType, SceneCut, TimeRelation
from echotales.pipeline.storyboard import gold_check
from echotales.pipeline.storyboard.cards import (
    Card,
    Part,
    assemble,
    build_cards,
    estimate_tokens,
    future_brief_block,
    title_meaning,
)
from echotales.pipeline.storyboard.director import build_storyboard
from echotales.pipeline.storyboard.inputs import Scene, load_chapter
from echotales.pipeline.storyboard.plan_schema import LLetter, LWindow
from echotales.pipeline.storyboard.prompts import build_prompt
from echotales.pipeline.storyboard.schema import (
    CastMember,
    Layer,
    Letter,
    LetterKind,
    Panel,
    Purpose,
    Segment,
    Shape,
    Shot,
    Storyboard,
)
from echotales.pipeline.storyboard.stage_scenes import scenes_from_analysis
from echotales.pipeline.storyboard.validators import (
    Report,
    WPanel,
    audit_v2,
    panel_duration,
    repair_v2,
)
from test_storyboard_director import NOVEL, FakeClient, _p, _plan_scene2, _store

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class SegmentTimeLabel:
    """The shape segment v3 gives `time_labels` entries (segment/storytime.py), reproduced so this suite needs no branch."""

    segment: int
    layer: str = "present"
    time_relation: TimeRelation = TimeRelation.UNKNOWN
    quote: str = ""
    verified: bool = False


@pytest.fixture(autouse=True)
def _no_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    from echotales.pipeline.storyboard import inputs

    monkeypatch.setattr(inputs, "_load_present_cast", lambda: None)
    monkeypatch.setattr(inputs, "_load_look_at", lambda: None)
    monkeypatch.setattr(inputs, "MIN_SCENE_BLOCKS", 5)


# --- scenes from the segment stage ------------------------------------------------------------------------------------


def _analysis(with_labels: bool):
    cuts = [
        SceneCut(1.0, 10, "implicit:llm", cut_type=CutType.POV_SWITCH, time_relation=TimeRelation.SAME, evidence=["same moment"]),
    ]
    ns = SimpleNamespace(chapter=1.0, cuts=cuts, prior_loop_segments={0})
    if with_labels:
        ns.time_labels = [
            SegmentTimeLabel(0, "past", TimeRelation.EARLIER, "five hundred years ago", True),
            SegmentTimeLabel(1),
        ]
    return ns


def test_stage_scenes_use_time_labels_and_prior_loops() -> None:
    inp = load_chapter(_store(), NOVEL, 1.0)
    scenes = scenes_from_analysis(inp, _analysis(True))
    assert [(s.block_from, s.block_to) for s in scenes] == [(0, 9), (10, 15)]
    assert scenes[0].layer is Layer.PAST and scenes[0].story_time == "five hundred years ago"
    assert scenes[1].cut_signal == "match" and scenes[0].cut_signal == ""


def test_stage_scenes_without_time_labels_fall_back_to_cut_evidence() -> None:
    inp = load_chapter(_store(), NOVEL, 1.0)
    scenes = scenes_from_analysis(inp, _analysis(False))  # the branch today: no time_labels attribute at all
    assert scenes[0].layer is Layer.PAST  # from prior_loop_segments
    assert scenes[1].story_time == "same moment"


def test_director_takes_scenes_from_the_stage_and_skips_its_own_pass() -> None:
    st = _store()
    client = FakeClient([_plan_scene2()])
    sb, report, _ = build_storyboard(st, client, NOVEL, 1.0, say=lambda *_: None, analysis=_analysis(True))
    assert report.scenes_from_stage
    assert [(s.block_from, s.layer) for s in sb.segments] == [(0, Layer.PAST), (10, Layer.PAST) if False else (10, Layer.PRESENT)]
    assert report.as_dict()["scenes_from_stage"] is True


# --- cards and the token budget ---------------------------------------------------------------------------------------


def _card(name: str, status: str, later: bool = False) -> Card:
    return Card(f"id:{name}", name, status, later, look="tall, black robe, white beard and a long scar over one eye, grey eyes",
                age="about sixty", role="clan head", title_meaning="leader of a family who decides its fate by custom")


def test_card_variants_shed_title_meaning_then_role_then_look() -> None:
    v = _card("A", "present").variants()
    assert "title means" in v[0] and "title means" not in v[1]
    assert "role clan head" in v[1] and "role clan head" not in v[2]
    assert len(v[3]) < len(v[2])


def test_assemble_drops_examples_then_shrinks_cards_then_drops_low_cards() -> None:
    parts = [
        Part("EXAMPLES " * 80, priority=0, name="examples"),
        Part("RULES", mandatory=True, name="rules"),
        Part(_card("Hero", "present").variants(), priority=13, name="card:Hero"),
        Part(_card("Talked", "referenced").variants(), priority=11, name="card:Talked"),
        Part("TEXT " * 40, mandatory=True, name="text"),
    ]
    full = assemble([*parts], 10**6)
    assert not full.dropped and not full.shrunk
    mid = estimate_tokens(full.text) - estimate_tokens("EXAMPLES " * 80) - 10
    out = assemble([Part(p.text, p.priority, p.mandatory, name=p.name) for p in parts], mid)
    assert out.dropped == ["examples"] and "RULES" in out.text and "TEXT" in out.text
    base = estimate_tokens("RULES\n" + "TEXT " * 40)
    hero_min = estimate_tokens(_card("Hero", "present").variants()[-1])
    tiny = assemble([Part(p.text, p.priority, p.mandatory, name=p.name) for p in parts], base + hero_min + 2)
    assert "card:Talked" in tiny.dropped and "RULES" in tiny.text and "TEXT TEXT" in tiny.text
    assert "card:Hero" not in tiny.dropped and "card:Hero" in tiny.shrunk  # the present person survives, poorer


def _glossary_store():
    st = _store()
    put_artifact(st, artifact_id("glossary", NOVEL), {"novel_id": NOVEL, "terms": [
        {"term": "clan head", "claims": [{"field": "definition", "text": "the leader of a clan, who rules by custom and rank", "source": "text"}]}]})
    return st


def test_title_meaning_found_by_sub_phrase_membership() -> None:
    st = _glossary_store()
    assert title_meaning(st, NOVEL, "Gu Yue clan head").startswith("the leader of a clan")
    assert title_meaning(st, NOVEL, "gardener") == ""


def test_cards_rank_present_before_talked_about_and_future_brief_lists_setups() -> None:
    st = _store()
    inp = load_chapter(st, NOVEL, 1.0)
    alice, carol = (r.entity_id for r in inp.roster if r.name in ("Alice", "Carol"))
    sc = Scene(0, 9, present_ids=[carol, alice], referenced_ids=[])
    sc.present_ids, sc.referenced_ids = [alice], [carol]
    brief = {"entities": [{"entity_id": carol, "label": "Carol", "matters_later": True, "role_summary": "Carol (self): teacher",
                           "setups": [{"here": "a long warning she once gave the young heroine", "later_chapter": 9.0, "later": "she returns"}]}]}
    cards = build_cards(st, inp, sc, brief)
    assert [c.name for c in cards] == ["Alice", "Carol"] and cards[1].matters_later
    block = future_brief_block(brief, sc, inp)
    assert "Carol" in block and "a long warning she once" in block and "heroine" not in block  # a 5-word anchor only


def test_prompt_budget_keeps_text_and_rules_and_reports_drops() -> None:
    from echotales.pipeline.storyboard import prompts

    st = _store()
    inp = load_chapter(st, NOVEL, 1.0)
    cards = [_card("Alice", "present"), _card("Carol", "referenced")]
    prompt = build_prompt(inp, inp.lines[:4], [], [], [], chapter_start=True, fixed_presence=True, carry="", scene_line="THIS SCENE: x",
                          n_examples=3, cards=cards, brief_block="MATTERS LATER IN THE NOVEL: x", lookahead="[b4] more",
                          budget_tokens=estimate_tokens(prompt_floor(inp)) + 40)
    assert "TEXT:" in prompt and "THIS SCENE: x" in prompt and prompt.rstrip().endswith("OUTPUT:")
    assert "examples" in prompts.last_assembly["dropped"]


def prompt_floor(inp) -> str:  # the mandatory parts only, to size a budget that forces drops
    return "INPUT:\nPASSAGE STARTS THE CHAPTER.\nTHIS SCENE: x\nTEXT:\n" + "\n".join(ln.text for ln in inp.lines[:4]) + "\nOUTPUT:"


# --- v2 rules ---------------------------------------------------------------------------------------------------------

HERO = CastMember(entity_id="fy", name="Fang Yuan")
HEAD = CastMember(entity_id="gh", name="Gu Yue Clan Head")
BNB = CastMember(entity_id="bnb", name="Bai Ning Bing")


def _seg(i: int, b0: int, b1: int, layer=Layer.PRESENT, cut="", present=(), referenced=()) -> Segment:
    return Segment(segment_id=f"s{i}", chapter=1, block_from=b0, block_to=b1, layer=layer, cut_signal=cut,
                   present_cast=list(present), referenced_cast=list(referenced))


def _pn(seg: str, purpose=Purpose.BEAT, blocks=(1,), **kw) -> Panel:
    kw.setdefault("emotion", "calm")
    return Panel(panel_id="", segment_id=seg, layer=kw.pop("layer", Layer.PRESENT), purpose=purpose, source_blocks=list(blocks), **kw)


def _inp():
    return SimpleNamespace(blocks={i: f"block {i} text" for i in range(0, 100)}, lines=[], roster=[])


def _wp(panels: list[Panel]) -> list[WPanel]:
    return [WPanel(p) for p in panels]


def _run_rules(panels, segments, cards=None, brief=None):
    cards = cards or {}
    before = audit_v2(_wp(panels), segments, _inp(), cards, brief)
    rep = Report()
    wps = repair_v2(_wp(panels), segments, _inp(), cards, brief, rep)
    return before, audit_v2(wps, segments, _inp(), cards, brief), wps, rep


def test_hero_cold_open_is_replaced_by_a_black_text_card() -> None:
    segs = [_seg(0, 0, 30, present=[HERO])]
    hero_open = _pn("s0", Purpose.COLD_OPEN, (0,), cast=[HERO], shot=Shot.EXTREME_WIDE, invented=True,
                    invented_reason="hook before exposition: chapter opened without one")
    before, after, wps, _ = _run_rules([hero_open, _pn("s0", blocks=(1,))], segs)
    assert before["cold_open_hero"] == 1 and after["cold_open_hero"] == 0
    first = wps[0].panel
    assert first.shape is Shape.TEXT_ONLY and not first.cast and first.invented_reason.startswith("text:b0")
    assert len(wps) == 2  # replaced, not stacked on the hero


def test_sfx_cold_open_passes() -> None:
    segs = [_seg(0, 0, 30)]
    op = _pn("s0", Purpose.COLD_OPEN, (0,), letters=[Letter(kind=LetterKind.SFX, text="THUD")])
    before, _a, _w, _r = _run_rules([op], segs)
    assert before["cold_open_hero"] == 0


def test_withheld_panel_loses_its_cast_and_gets_an_extreme_close_and_reveal_is_checked() -> None:
    segs = [_seg(0, 0, 100, present=[HERO])]
    op = _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY)
    held = _pn("s0", Purpose.BEAT, (79,), withheld=True, cast=[HERO], shot=Shot.MEDIUM)
    before, after, _w, _ = _run_rules([op, held], segs)
    assert before["withheld_has_cast"] == 1 and before["withheld_not_ecu"] == 1 and before["withheld_no_reveal"] == 1
    assert after["withheld_has_cast"] == 0 and after["withheld_not_ecu"] == 0
    assert after["withheld_no_reveal"] == 1  # cannot be repaired: reported
    reveal = _pn("s0", Purpose.BEAT, (80,), cast=[HERO])
    _b, after2, _w, _r = _run_rules([op, held, reveal], segs)
    assert after2["withheld_no_reveal"] == 0


def test_parallel_cut_gets_a_match_transition() -> None:
    segs = [_seg(0, 0, 78), _seg(1, 79, 90, cut="match")]
    op = _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY)
    card = _pn("s1", Purpose.TIME_PLACE_CARD, (79,), invented=True, invented_reason="text:b79 cut")
    before, after, wps, _ = _run_rules([op, card, _pn("s1", blocks=(80,))], segs)
    assert before["parallel_cut_unmatched"] == 1 and after["parallel_cut_unmatched"] == 0
    seg1 = [w.panel for w in wps if w.panel.segment_id == "s1"]
    assert seg1[0].purpose is Purpose.TRANSITION and seg1[0].cut_signal == "match"
    assert len(seg1) == 2  # the cut panel was converted, not duplicated
    _b, after2, wps2, _ = _run_rules([op, _pn("s1", blocks=(80,))], segs)
    assert wps2[1].panel.purpose is Purpose.TRANSITION and after2["parallel_cut_unmatched"] == 0


def test_referenced_person_who_matters_later_gets_a_silent_dossier_inset() -> None:
    segs = [_seg(0, 0, 78, present=[HEAD], referenced=[BNB])]
    cards = {"s0": [Card("bnb", "Bai Ning Bing", "referenced", True, look="white robes, a cold calm face", look_source="dossier")]}
    op = _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY)
    talk = _pn("s0", Purpose.DIALOGUE, (60,), cast=[HEAD], letters=[Letter(kind=LetterKind.SPEECH, text="Bai Ning Bing leads them", source_span_id="x")])
    before, after, wps, _ = _run_rules([op, talk], segs, cards)
    assert before["inset_missing"] == 1 and after["inset_missing"] == 0
    ins = next(w.panel for w in wps if w.panel.purpose is Purpose.REFERENCED_INSET)
    assert ins.layer is Layer.IMAGINED and not ins.letters and ins.cast[0].look_source == "dossier"
    assert ins.invented_reason.startswith("dossier:") and wps.index(next(w for w in wps if w.panel is ins)) == 2  # right after the line naming her


def test_inset_without_dossier_look_is_filled_and_balloon_is_reported() -> None:
    segs = [_seg(0, 0, 78, present=[HEAD], referenced=[BNB])]
    cards = {"s0": [Card("bnb", "Bai Ning Bing", "referenced", True, look="white robes", look_source="dossier")]}
    ins = _pn("s0", Purpose.REFERENCED_INSET, (60,), layer=Layer.IMAGINED, cast=[BNB.model_copy()],
              letters=[Letter(kind=LetterKind.SPEECH, text="hello", source_span_id="y")], invented=True, invented_reason="dossier:x")
    op = _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY)
    before, after, _w, _r = _run_rules([op, ins], segs, cards)
    assert before["inset_look_not_dossier"] == 1 and after["inset_look_not_dossier"] == 0
    assert after["inset_has_balloon"] == 1  # a spoken line would be lost by stripping it: reported only


def test_layer_cast_and_citation_rules() -> None:
    segs = [_seg(0, 0, 30, layer=Layer.PAST, present=[HERO])]
    op = _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY, layer=Layer.PAST)
    wrong = _pn("s0", Purpose.BEAT, (3,), layer=Layer.PRESENT, cast=[HERO], invented=True, invented_reason="a quiet moment")
    dream = _pn("s0", Purpose.BEAT, (4,), layer=Layer.DREAM, cast=[HERO])
    stranger = _pn("s0", Purpose.BEAT, (5,), cast=[BNB], layer=Layer.PAST)
    before, after, wps, _ = _run_rules([op, wrong, dream, stranger], segs)
    assert before["layer_mismatch"] == 1 and after["layer_mismatch"] == 0
    assert before["invented_no_evidence"] == 1 and after["invented_no_evidence"] == 0
    assert wps[1].panel.layer is Layer.PAST and wps[1].panel.invented_reason.startswith("text:b3")
    assert wps[2].panel.layer is Layer.DREAM  # a sub-layer inside the scene is allowed
    assert before["cast_outside_present"] == 1


def test_foreshadow_must_be_anchored_and_not_depict_the_later_event() -> None:
    segs = [_seg(0, 0, 30, present=[HERO])]
    brief = {"entities": [{"entity_id": "fy", "matters_later": True,
                           "setups": [{"later": "the cicada awakens and devours the ancestral armies"}]}]}
    op = _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY)
    ok = _pn("s0", Purpose.INSERT, (3,), beat="foreshadow", visual="a candle gutters")
    bad = _pn("s0", Purpose.INSERT, (4,), beat="curiosity", visual="the cicada devours the ancestral armies")
    loose = _pn("s0", Purpose.INSERT, (), beat="foreshadow", visual="a door")
    before, after, wps, _ = _run_rules([op, ok, bad, loose], segs, brief=brief)
    assert before["foreshadow_depicts_later"] == 1 and before["foreshadow_unanchored"] == 1
    assert after["foreshadow_depicts_later"] == 0 and after["foreshadow_unanchored"] == 0
    assert [w.panel.beat for w in wps] == ["", "foreshadow", "", ""]
    none = _run_rules([op, _pn("s0", blocks=(2,))], segs, brief=brief)[0]
    assert none["no_foreshadow"] == 1


def test_duration_follows_the_lettering() -> None:
    quick = _pn("s0", letters=[Letter(kind=LetterKind.SPEECH, text="No.", source_span_id="a")])
    slow = _pn("s0", letters=[Letter(kind=LetterKind.NARRATION, text=" ".join(["word"] * 40), source_span_id="b")])
    assert panel_duration(quick) == 1.6 < panel_duration(slow) <= 9.0
    assert panel_duration(_pn("s0", letters=[Letter(kind=LetterKind.SFX, text="BOOM")])) == 1.6


def test_v2_fields_flow_from_the_model_plan_to_the_panel() -> None:
    plan = LWindow(panels=[
        _p(Purpose.COLD_OPEN, shape=Shape.TEXT_ONLY, shot=Shot.INSERT, sfx=["THUD"], blocks=[0], emotion="Dread", visual="black",
           invented=True, reason="a hush", evidence="text:b0"),
        _p(Purpose.DIALOGUE, cast=["Alice"], blocks=[0], letters=[LLetter(ref="s0", kind=LetterKind.SCREEN)], beat="Foreshadow",
           emotion="resolve"),
    ])
    sb, _r, _ = build_storyboard(_store(), FakeClient([plan, _plan_scene2()]), NOVEL, 1.0, say=lambda *_: None)
    first, second = sb.panels[0], sb.panels[1]
    assert first.emotion == "dread" and first.invented_reason == "text:b0 a hush" and first.duration_s >= 1.6
    assert second.letters[0].kind is LetterKind.SCREEN and second.beat == "foreshadow"


# --- gold checker -----------------------------------------------------------------------------------------------------


def _ri_hand_built() -> Storyboard:
    crowd = CastMember(entity_id="crowd:accuser", name="an accuser", invented=True)
    elder = CastMember(entity_id="crowd:elders", name="elders", invented=True)
    bnb = BNB.model_copy(update={"look": "white robes, cold calm face", "look_source": "dossier"})
    segs = [
        _seg(0, 0, 30, layer=Layer.PAST, present=[HERO, crowd]),
        _seg(1, 31, 78, present=[HEAD, elder], referenced=[BNB, HERO]),
        _seg(2, 79, 89, cut="match", present=[HERO]),
    ]
    sp = lambda t, k=LetterKind.SPEECH: Letter(kind=k, text=t, source_span_id="sp")  # noqa: E731
    ps = [
        _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY, shot=Shot.INSERT, letters=[Letter(kind=LetterKind.SFX, text="THUD")]),
        _pn("s0", Purpose.DIALOGUE, (1,), cast=[HERO, crowd], layer=Layer.PAST),
        _pn("s0", Purpose.INSERT, (18,), layer=Layer.PAST, letters=[sp("verse", LetterKind.POEM)], beat="foreshadow",
            invented=True, invented_reason="brief: a setup that pays off later"),
        _pn("s1", Purpose.ESTABLISHING, (31,), invented=True, invented_reason="text:b31 rain on the village"),
        _pn("s1", Purpose.DIALOGUE, (50,), cast=[HEAD, elder]),
        _pn("s1", Purpose.REFERENCED_INSET, (55,), layer=Layer.IMAGINED, shape=Shape.INSET, cast=[bnb], invented=True,
            invented_reason="dossier:Bai Ning Bing is only talked about"),
        _pn("s2", Purpose.TRANSITION, (79,), cut_signal="match", shape=Shape.WIDE, invented=True, invented_reason="text:b79 match cut"),
        _pn("s2", Purpose.EXTREME_CLOSE, (79,), shot=Shot.EXTREME_CLOSE, withheld=True),
        _pn("s2", Purpose.REACTION, (80,), cast=[HERO]),
    ]
    return Storyboard(novel_id="x", chapter=1.0, segments=segs, panels=ps)


def test_hand_built_ri_board_passes_every_gold_check() -> None:
    gold, checks = gold_check.load_gold(ROOT / "data/gold/segment/ri_ch1_owner.json")
    rows = gold_check.check_gold(_ri_hand_built(), gold, checks)
    failed = [r for r in rows if not r[1]]
    assert not failed, failed
    assert len(rows) >= 20


def test_a_v1_style_board_fails_the_named_checks() -> None:
    gold, checks = gold_check.load_gold(ROOT / "data/gold/segment/ri_ch1_owner.json")
    sb = _ri_hand_built()
    sb.panels[0] = _pn("s0", Purpose.COLD_OPEN, (0,), cast=[HERO], shot=Shot.EXTREME_WIDE)
    sb.panels = [p for p in sb.panels if not p.withheld and p.purpose is not Purpose.REFERENCED_INSET]
    sb.segments[0].layer = Layer.PRESENT
    failed = {r[0] for r in gold_check.check_gold(sb, gold, checks) if not r[1]}
    assert {"cold open is not the hero", "scene 1 layer past", "inset: Bai Ning Bing", "b79 identity withheld (extreme close, no person)"} <= failed


def test_saved_v1_storyboard_is_scored_without_a_model() -> None:
    v1 = ROOT / "data/eval/storyboard/ri_ch1_qwen3-8b.json"
    if not v1.exists():
        pytest.skip("v1 output lives in the checkout that ran it")
    gold, checks = gold_check.load_gold(ROOT / "data/gold/segment/ri_ch1_owner.json")
    rows = gold_check.check_gold(Storyboard.model_validate_json(v1.read_text(encoding="utf-8")), gold, checks)
    failed = {r[0] for r in rows if not r[1]}
    assert "cold open is not the hero" in failed and "every invented panel cites text/dossier/brief" in failed


def test_checks_files_are_valid_json_and_name_real_gold_scenes() -> None:
    for stem in ("ri_ch1_owner", "lotm_ch1_silver", "orv_ch1_silver"):
        gold, checks = gold_check.load_gold(ROOT / f"data/gold/segment/{stem}.json")
        assert checks, stem
        json.dumps(checks)
        for s in checks.get("match_cut_scenes", []):
            assert any(sc["scene"] == s for sc in gold["scenes"])


def test_withheld_panel_moves_into_the_next_segment_with_its_reveal_and_the_cut_moves() -> None:
    segs = [_seg(0, 0, 79), _seg(1, 80, 90)]
    op = _pn("s0", Purpose.COLD_OPEN, (0,), shape=Shape.TEXT_ONLY)
    held = _pn("s0", Purpose.BEAT, (79,), withheld=True, shot=Shot.EXTREME_CLOSE)
    reveal = _pn("s1", Purpose.BEAT, (80,), cast=[HERO])
    _b, _a, wps, rep = _run_rules([op, _pn("s0", blocks=(70,)), held, reveal], segs)
    assert [w.panel.segment_id for w in wps][-2:] == ["s1", "s1"]
    assert (segs[0].block_to, segs[1].block_from) == (78, 79)
    assert rep.log[-1]["rule"] == "withheld_cross_segment"

    # another panel of the old scene sits at or after the clue: nothing moves
    segs2 = [_seg(0, 0, 79), _seg(1, 80, 90)]
    late = _pn("s0", blocks=(79,))
    held2 = _pn("s0", Purpose.BEAT, (79,), withheld=True, shot=Shot.EXTREME_CLOSE)
    reveal2 = _pn("s1", Purpose.BEAT, (80,), cast=[HERO])
    _b, _a, wps2, _r = _run_rules([op, held2, late, reveal2], segs2)
    assert wps2[1].panel.segment_id == "s0" and segs2[0].block_to == 79
