"""Storyboard director: validators and repairs against fake model output (no GPU, no network).

The fake plan below breaks the grammar on purpose, one rule per panel, because the validators exist for exactly the
slips a small local model makes (docs/results/STORYBOARD_DIRECTOR.md): a person who is only talked about drawn in the
room, a spoken line dropped, no cold open, a scene cut with no signal, a peak with no insert.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from echotales.core.enums import BlockType, Prominence, SpanType
from echotales.core.models import Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline.llm.base import LLMParseError
from echotales.pipeline.storyboard import inputs as sb_inputs
from echotales.pipeline.storyboard.director import build_storyboard, run_chapter
from echotales.pipeline.storyboard.inputs import RosterEntry, match_entry
from echotales.pipeline.storyboard.plan_schema import (
    LCutLine,
    LLetter,
    LPanel,
    LPresence,
    LSceneList,
    LSceneMark,
    LWindow,
)
from echotales.pipeline.storyboard.schema import Layer, LetterKind, Purpose, Shape, Shot
from echotales.pipeline.storyboard.scorecard import score

NOVEL = "t"
TEXTS = [
    "“Surrender the relic!”",  # 0 crowd line, unattributed
    "Alice stood alone at the gate, blood on her sleeve.",  # 1
    "“I will not yield,” Alice said.",  # 2
    "The crowd pressed closer, torches high.",  # 3
    "Alice thought of Carol, her old teacher, who had warned her about this day.",  # 4
    "“Carol was right,” Alice whispered.",  # 5
    "She raised the blade.",  # 6
    "“Kill her!” someone screamed.",  # 7
    "Steel rang against steel.",  # 8
    "……",  # 9
    "Morning came to the river town of Brook.",  # 10
    "Bob sat on the quay and counted coins.",  # 11
    "“Alice will not come back,” Bob said to himself.",  # 12
    "He spat into the water.",  # 13
    "The ferry bell rang twice.",  # 14
    "Bob stood and walked away.",  # 15
]


def _store() -> Store:
    st = Store(":memory:")
    st.add_novel(NOVEL, "T", "x.epub", "generic")
    st.add_chapter(
        Chapter(novel_id=NOVEL, number=1.0, title="One", source_href="1.html",
                blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(TEXTS)])
    )
    for sid, label in (("t:self:alice", "Alice"), ("t:self:bob", "Bob"), ("t:self:carol", "Carol")):
        st.add_self(Self(id=sid, novel_id=NOVEL, canonical_label=label, first_attested_pos=DiscoursePosition(chapter=1, offset=0),
                         prominence=Prominence.INCIDENTAL))
    spans = []
    speakers = {2: "t:self:alice", 5: "t:self:alice", 12: "t:self:bob"}
    for i, t in enumerate(TEXTS):
        quoted = t.startswith("“")
        spans.append(
            Span(id=f"t:1:{i}", novel_id=NOVEL, chapter=1.0, block_index=i, start=0, end=len(t),
                 span_type=SpanType.DIALOGUE if quoted else SpanType.NARRATION_ACTION, text=t,
                 speaker_self_id=speakers.get(i))
        )
    st.add_spans(spans)
    st.conn.commit()
    return st


@dataclass
class _Res:
    value: LWindow
    latency_ms: int = 5
    prompt_tokens: int = 10
    completion_tokens: int = 10


class FakeClient:
    """Answers the three storyboard calls by schema: scene marks, per-scene presence, window panel plans."""

    def __init__(self, plans: list[LWindow | Exception], *, presence: list[LPresence] | None = None,
                 marks: LSceneList | None = None) -> None:
        self.plans = plans
        self.calls = 0
        self._presence = presence if presence is not None else [
            LPresence(present=["Alice"], referenced=["Carol"]), LPresence(present=["Bob"], referenced=[])]
        self._marks = marks if marks is not None else LSceneList(scenes=[
            LSceneMark(from_block=0, place="the gate"), LSceneMark(from_block=10, place="the river town of Brook", cut_signal="card")])
        self._pi = 0

    def complete(self, task, prompt, schema, **kw):
        if schema is LSceneList:
            return _Res(self._marks)
        if schema is LPresence:
            r = self._presence[min(self._pi, len(self._presence) - 1)]
            self._pi += 1
            return _Res(r)
        p = self.plans[min(self.calls, len(self.plans) - 1)]
        self.calls += 1
        if isinstance(p, Exception):
            raise p
        return _Res(p)

    def model_for(self, task):
        return "fake"


def _p(purpose, cast=(), letters=(), blocks=(), **kw):
    return LPanel(purpose=purpose, shape=kw.pop("shape", Shape.STANDARD), shot=kw.pop("shot", Shot.MEDIUM),
                  layer=kw.pop("layer", Layer.PRESENT), cast=list(cast), letters=list(letters), blocks=list(blocks), **kw)


def _bad_plan_scene1() -> LWindow:
    """Window over blocks 0-8: breaks rules 1, 4, 5 and the peak rule."""
    return LWindow(
        panels=[
            _p(Purpose.ESTABLISHING, blocks=[1], visual="Alice at the gate", cast=["Alice"],
               letters=[LLetter(ref="s1", kind=LetterKind.NARRATION)]),
            # Carol is only remembered: drawn standing beside Alice is the failure the validator exists for
            _p(Purpose.DIALOGUE, cast=["Alice", "Carol"], blocks=[2], visual="Carol stands behind Alice",
               letters=[LLetter(ref="s2", kind=LetterKind.SPEECH)]),
            # line s5 (Alice's whisper) is left out entirely; s0 is carried by a named character panel
            _p(Purpose.CROWD_INDIVIDUAL, cast=["a bearded man"], blocks=[0],
               letters=[LLetter(ref="s0", kind=LetterKind.SHOUT)], invented=True,
               reason="crowd face"),
            _p(Purpose.BEAT, cast=["Alice"], blocks=[6], visual="Alice raises the blade", peak=True,
               letters=[LLetter(ref="s6", kind=LetterKind.NARRATION), LLetter(ref="s99", kind=LetterKind.SPEECH)]),
            _p(Purpose.DIALOGUE, cast=["Zed"], blocks=[7], letters=[LLetter(ref="s7", kind=LetterKind.SHOUT)]),
        ],
    )


def _plan_scene2() -> LWindow:
    return LWindow(
        panels=[
            _p(Purpose.BEAT, cast=["Bob"], blocks=[11], visual="Bob counts coins on the quay",
               letters=[LLetter(ref="s11", kind=LetterKind.NARRATION)]),
            _p(Purpose.DIALOGUE, cast=["Bob"], blocks=[12], letters=[LLetter(ref="s12", kind=LetterKind.SPEECH)]),
        ],
    )


@pytest.fixture(autouse=True)
def _no_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb_inputs, "_load_present_cast", lambda: None)
    monkeypatch.setattr(sb_inputs, "_load_look_at", lambda: None)
    monkeypatch.setattr(sb_inputs, "MIN_SCENE_BLOCKS", 5)  # the 16-block toy chapter, not a real 80-block one


def _run(plans: list[LWindow | Exception]):
    st = _store()
    client = FakeClient(plans)
    return build_storyboard(st, client, NOVEL, 1.0, say=lambda *_: None)


def test_name_matching_does_not_merge_mr_and_mrs() -> None:
    roster = [RosterEntry("a", "Mrs. Bennet"), RosterEntry("b", "Mr. Bennet"), RosterEntry("c", "Fang Yuan")]
    assert match_entry("Mr. Bennet", roster).entity_id == "b"
    assert match_entry("Bennet", roster) is None or match_entry("Bennet", roster).entity_id in {"a", "b"}
    assert match_entry("Gu Yue Fang Yuan", roster).entity_id == "c"  # house-prefixed form of the same person
    assert match_entry("Fang", roster).entity_id == "c"


def test_scene_split_at_separator_and_unmarked_cut_found() -> None:
    st = _store()
    inp = sb_inputs.load_chapter(st, NOVEL, 1.0)
    # the "……" at block 9 splits the 16 story blocks into two scenes
    assert [(s.block_from, s.block_to) for s in inp.scenes] == [(0, 9), (10, 15)]


def test_validators_repair_the_grammar_breaks() -> None:
    sb, report, inp = _run([_bad_plan_scene1(), _plan_scene2(), _plan_scene2()])

    assert report.before["referenced_in_room"] >= 1
    assert report.before["no_cold_open"] == 1
    assert report.before["invented_speech"] == 0  # a letter can only name a source line; a bad tag is dropped at conversion
    assert report.conversion["bad_line_ref"] == 1
    assert report.before["speech_lost"] >= 1  # s5 whisper, s12 if the window dropped it
    assert report.before["name_not_in_cast"] >= 1  # "Zed"

    # after repair none of the repairable rules remain
    for rule in ("referenced_in_room", "no_cold_open", "speech_lost", "name_not_in_cast", "cut_unsignalled", "peak_no_relief"):
        assert report.after[rule] == 0, (rule, report.after)

    assert sb.panels[0].purpose is Purpose.COLD_OPEN and sb.panels[0].invented
    # Carol never stands in a non-inset panel
    for p in sb.panels:
        names = {m.name for m in p.cast}
        if "Carol" in names:
            assert p.purpose is Purpose.REFERENCED_INSET and p.layer is Layer.IMAGINED
    # every spoken line survives
    spoken = {lt.source_span_id for p in sb.panels for lt in p.letters}
    for ln in inp.lines:
        if ln.kind == "speech":
            assert ln.span_id in spoken
    # invented panels carry no new speech: only sfx / cards without a source span
    for p in sb.panels:
        for lt in p.letters:
            if lt.source_span_id is None:
                assert lt.kind in {LetterKind.SFX, LetterKind.TIME_PLACE, LetterKind.NAME_CARD}
    # the repair log says what it did
    assert any(e["rule"] == "no_cold_open" for e in report.log)


def test_scene_cut_after_first_scene_opens_with_a_signal() -> None:
    sb, _report, _ = _run([_bad_plan_scene1(), _plan_scene2(), _plan_scene2()])
    assert len(sb.segments) >= 2
    for seg in sb.segments[1:]:
        first = next(p for p in sb.panels if p.segment_id == seg.segment_id)
        assert first.purpose in {Purpose.TIME_PLACE_CARD, Purpose.TRANSITION, Purpose.ESTABLISHING}


def test_crowd_line_with_named_speaker_is_not_a_crowd_individual() -> None:
    plan = LWindow(
        panels=[_p(Purpose.CROWD_INDIVIDUAL, cast=["a bearded man"], blocks=[2], invented=True, reason="x",
                   letters=[LLetter(ref="s2", kind=LetterKind.SPEECH)])],
    )
    _sb, report, _ = _run([plan, plan, plan])
    assert report.before["crowd_named"] == 1 and report.after["crowd_named"] == 0


def test_cut_line_with_reason_is_not_lost_but_without_reason_is_restored() -> None:
    base = _plan_scene2()
    cut = base.model_copy(update={"cut_lines": [LCutLine(ref="s12", reason="duplicates the picture")]})
    cut.panels = cut.panels[:1]
    _, rep_cut, _ = _run([_bad_plan_scene1(), cut, cut])
    nocut = base.model_copy()
    nocut.panels = nocut.panels[:1]
    _, rep_no, _ = _run([_bad_plan_scene1(), nocut, nocut])
    assert rep_no.before["speech_lost"] > rep_cut.before["speech_lost"]
    assert rep_no.after["speech_lost"] == 0


def test_model_failure_falls_back_to_a_plain_plan_and_keeps_every_line() -> None:
    sb, report, inp = _run([LLMParseError("bad json")])
    assert report.llm_failures >= 1
    spoken = {lt.source_span_id for p in sb.panels for lt in p.letters}
    assert all(ln.span_id in spoken for ln in inp.lines if ln.kind == "speech")


def test_referenced_speaker_is_cleared() -> None:
    """The reader attributed a line to a person who is only talked about in this scene: keep the line, drop the speaker."""
    st = _store()
    st.conn.execute("UPDATE span SET speaker_self_id='t:self:carol' WHERE id='t:1:5'")
    st.conn.commit()
    client = FakeClient([_bad_plan_scene1(), _plan_scene2(), _plan_scene2()])
    sb, report, _ = build_storyboard(st, client, NOVEL, 1.0, say=lambda *_: None)
    carol_lines = [lt for p in sb.panels for lt in p.letters if lt.speaker_id == "t:self:carol"]
    assert not carol_lines
    assert any(e["rule"] == "speaker_not_present" for e in report.log) and report.after["speaker_not_present"] == 0


def test_cache_by_input_hash(tmp_path) -> None:
    st = _store()
    client = FakeClient([_bad_plan_scene1(), _plan_scene2(), _plan_scene2()])
    sb1, meta1, cached1 = run_chapter(st, client, NOVEL, 1.0, data_root=tmp_path, say=lambda *_: None)
    calls = client.calls
    sb2, meta2, cached2 = run_chapter(st, client, NOVEL, 1.0, data_root=tmp_path, say=lambda *_: None)
    assert not cached1 and cached2 and client.calls == calls
    assert sb1.model_dump() == sb2.model_dump()
    assert meta2["cache_key"] == meta1["cache_key"]


def test_scorecard_counts_from_the_storyboard() -> None:
    sb, _, inp = _run([_bad_plan_scene1(), _plan_scene2(), _plan_scene2()])
    card = score(sb, n_blocks=len(inp.blocks))
    assert card["cold_open"] is True
    assert card["panels"] == len(sb.panels)
    assert card["crowd_individuals"] >= 1
    assert card["shapes_used"] >= 1


def test_overstuffed_panel_is_split_and_crowd_lines_get_distinct_faces() -> None:
    slab = LWindow(
        panels=[_p(Purpose.DIALOGUE, cast=["Alice"], blocks=[0, 1, 2, 3, 6, 7], visual="the gate",
                   letters=[LLetter(ref="s0", kind=LetterKind.SHOUT), LLetter(ref="s2", kind=LetterKind.SPEECH),
                            LLetter(ref="s7", kind=LetterKind.SHOUT)])]
    )
    client = FakeClient([slab, _plan_scene2(), _plan_scene2()],
                        presence=[LPresence(present=["Alice", "crowd"], referenced=["Carol"]), LPresence(present=["Bob"])])
    sb, report, _ = build_storyboard(_store(), client, NOVEL, 1.0, say=lambda *_: None)
    assert report.before["panel_overstuffed"] >= 1 and report.after["panel_overstuffed"] == 0
    faces = [p for p in sb.panels if p.purpose is Purpose.CROWD_INDIVIDUAL]
    assert len(faces) == 2 and faces[0].cast[0].name != faces[1].cast[0].name
    assert all(p.invented and p.invented_reason for p in faces)
    # the named speaker's line stays a plain dialogue panel with its speaker
    alice = next(lt for p in sb.panels for lt in p.letters if lt.source_span_id == "t:1:2")
    assert alice.speaker_id == "t:self:alice"


def test_scene_pass_cut_not_in_the_graph_is_found_and_signalled() -> None:
    st = _store()
    st.conn.execute("UPDATE chapter SET blocks_json=blocks_json")  # no-op: the separator split is bypassed below
    sb_inputs.MIN_SCENE_BLOCKS = 99  # the graph/separator split finds nothing, as on RI ch1 block 80
    try:
        sb, report, _ = build_storyboard(st, FakeClient([_bad_plan_scene1(), _plan_scene2(), _plan_scene2()]), NOVEL, 1.0,
                                         say=lambda *_: None)
    finally:
        sb_inputs.MIN_SCENE_BLOCKS = 5
    assert [s.block_from for s in sb.segments] == [0, 10]
    assert any(e["rule"] == "scene_cut_found" for e in report.log)
    assert sb.segments[1].place == "the river town of Brook"


def test_unparseable_window_is_bisected_not_dropped() -> None:
    calls = [LLMParseError("truncated"), _bad_plan_scene1(), _bad_plan_scene1(), _plan_scene2(), _plan_scene2()]
    _, report, _ = _run(calls)
    assert any(e["rule"] == "llm_bisect" for e in report.log)
    assert report.llm_failures == 0
