"""Per-novel scene-cut induction, implicit cuts and presence.

Every test uses synthetic text and fake LLMs. The measured behaviour on real
novels lives in docs/results/SCENE_INDUCTION.md; these tests pin the contracts
other stages depend on (canonical positions, shape signatures carrying no
words, presence separating "in the room" from "talked about").
"""

from __future__ import annotations

from echotales.core.enums import (
    AliasType,
    AttributionMethod,
    BlockType,
    ReferenceMode,
    SegmentType,
    SpanType,
    TargetKind,
)
from echotales.core.models import (
    Block,
    Chapter,
    DiscoursePosition,
    Mention,
    NarrativeSegment,
    Self,
    Span,
)
from echotales.core.store import Store
from echotales.pipeline.llm import StubProvider
from echotales.pipeline.segment.cuts import CutType, SceneCut, TimeRelation
from echotales.pipeline.segment.discontinuity import canonical_position, score_chapter
from echotales.pipeline.segment.implicit import CutJudgement, propose_implicit_cuts, resolve_story_order
from echotales.pipeline.segment.induce import (
    block_shapes,
    find_induced_cuts,
    induce_conventions,
    load_conventions,
    save_conventions,
)
from echotales.pipeline.segment.presence import present_cast
from echotales.pipeline.segment.scenes import (
    SceneAnalysis,
    apply_cuts_to_segments,
    load_scene_cuts,
    save_scene_cuts,
)

FILL = "walked slowly along the quiet road and said nothing at all today"


def _chapter(blocks: list[tuple[str, BlockType]], number: float = 1.0) -> Chapter:
    return Chapter(
        novel_id="t",
        number=number,
        title="T",
        source_href="a.html",
        blocks=[Block(index=i, block_type=bt, text=t) for i, (t, bt) in enumerate(blocks)],
    )


def _scene(names: list[str], n: int = 4) -> list[tuple[str, BlockType]]:
    return [(f"{names[i % len(names)]} {FILL} {i}.", BlockType.PROSE) for i in range(n)]


def _volume(marker: str, n_chapters: int = 6) -> list[Chapter]:
    """Each chapter: scene of Alice and Bob, a symbol line, then a scene of Carol and Dave."""
    out = []
    for c in range(n_chapters):
        blocks = _scene(["Alice", "Bob"], 5) + [(marker, BlockType.NON_DIEGETIC)] + _scene(["Carol", "Dave"], 5)
        out.append(_chapter(blocks, number=float(c + 1)))
    return out


# ------------------------------------------------------------------ discontinuity


def test_canonical_position_skips_one_line_headers_and_symbol_lines() -> None:
    ch = _chapter(
        _scene(["Alice"], 3) + [("...", BlockType.PROSE), ("Southern Border", BlockType.PROSE)] + _scene(["Carol"], 3)
    )
    assert canonical_position(ch, 3) == 5
    assert canonical_position(ch, 4) == 5
    assert canonical_position(ch, 5) == 5


def test_boundary_score_peaks_where_the_cast_changes() -> None:
    ch = _chapter(_scene(["Alice", "Bob"], 6) + _scene(["Carol", "Dave"], 6))
    bs = score_chapter(ch, nlp=None)
    best = max(bs, key=lambda b: b.score)
    assert best.position == 6
    assert best.features["cast"] > 0.9


def test_score_is_empty_for_a_chapter_without_two_substantive_blocks() -> None:
    assert score_chapter(_chapter([("Hi.", BlockType.PROSE)]), nlp=None) == []


# ----------------------------------------------------------------------- induction


def test_block_shape_contains_no_words_of_the_text() -> None:
    ch = _chapter(_scene(["Alice"], 2) + [("Southern Border", BlockType.PROSE)] + _scene(["Bob"], 2))
    shapes = block_shapes(ch, 2, nlp=None)
    assert "southern" not in " ".join(shapes.values()).lower()
    assert shapes["short"].startswith("w2-3|title")


def test_a_recurring_marker_shape_on_high_boundaries_is_induced_and_applied() -> None:
    chapters = _volume("* * *")
    cset = induce_conventions("t", chapters, nlp=None, min_support=3)
    accepted = {c.id for c in cset.accepted()}
    assert "symbol:* * *" in accepted
    new = _chapter(_scene(["Alice", "Bob"], 5) + [("* * *", BlockType.NON_DIEGETIC)] + _scene(["Carol", "Dave"], 5))
    cuts = find_induced_cuts(new, cset, nlp=None)
    assert [c.block for c in cuts] == [6]
    assert cuts[0].source.startswith("induced-")


def test_a_shape_that_sits_on_ordinary_boundaries_is_not_induced() -> None:
    # The same symbol line, but dropped inside one continuous scene.
    chapters = [
        _chapter(_scene(["Alice", "Bob"], 5) + [("* * *", BlockType.NON_DIEGETIC)] + _scene(["Alice", "Bob"], 5), float(i))
        for i in range(1, 7)
    ]
    cset = induce_conventions("t", chapters, nlp=None, min_support=3)
    assert "symbol:* * *" not in {c.id for c in cset.accepted()}


def test_model_can_veto_an_induced_convention_but_never_add_one(tmp_path) -> None:
    chapters = _volume("* * *")
    no = StubProvider()
    no.register_response("scene_convention_confirm", {"marks_scene_change": False, "reason": "pause"})
    cset = induce_conventions("t", chapters, nlp=None, llm=no)
    vetoed = next(c for c in cset.conventions if c.id == "symbol:* * *")
    assert not vetoed.accepted and "vetoed" in vetoed.reason
    path = save_conventions(cset, tmp_path / "t.scene_conventions.json")
    assert load_conventions(path).conventions[0].id == cset.conventions[0].id


# ------------------------------------------------------------------------ implicit


def _judge(cut: bool, ctype: str = "NEW_SCENE", rel: str = "UNKNOWN", conf: float = 0.9) -> StubProvider:
    stub = StubProvider()
    stub.register_response(
        "scene_cut_judge",
        CutJudgement(is_cut=cut, cut_type=ctype, time_relation=rel, confidence=conf, reason="r"),
    )
    return stub


def test_implicit_cuts_come_only_from_boundaries_the_model_confirms() -> None:
    ch = _chapter(_scene(["Alice", "Bob"], 6) + _scene(["Carol", "Dave"], 6))
    bs = score_chapter(ch, nlp=None)
    cuts = propose_implicit_cuts(ch, bs, set(), _judge(True, "TIME_JUMP", "LATER"), threshold=0.0)
    # A model that says yes to everything still gets the real cut asked first, and no two cuts one block apart.
    assert cuts and 6 in {c.block for c in cuts} and cuts[0].cut_type is CutType.TIME_JUMP
    assert all(b - a > 1 for a, b in zip([c.block for c in cuts], [c.block for c in cuts][1:], strict=False))
    assert propose_implicit_cuts(ch, bs, set(), _judge(False), threshold=0.0) == []
    assert propose_implicit_cuts(ch, bs, set(), _judge(True, conf=0.2), threshold=0.0) == []


def test_unknown_time_relation_is_revised_from_the_whole_chapter() -> None:
    ch = _chapter(_scene(["Alice"], 4) + _scene(["Carol"], 4))
    cut = SceneCut(chapter=1.0, block=4, source="implicit:llm")
    stub = StubProvider()
    stub.register_response("scene_story_order", {"items": [
        {"segment": 0, "relative_to_previous": "UNKNOWN", "prior_loop": True},
        {"segment": 1, "relative_to_previous": "EARLIER", "prior_loop": False, "reason": "500 years ago"},
    ]})
    prior = resolve_story_order(ch, [cut], stub, nlp=None)
    assert cut.time_relation is TimeRelation.EARLIER
    assert prior == {0}


def test_scene_cuts_split_main_segments_and_a_prior_loop_keeps_its_type() -> None:
    ch = _chapter(_scene(["Alice"], 4) + _scene(["Carol"], 4) + _scene(["Dave"], 4))
    main = NarrativeSegment(
        id="t:1:main0", novel_id="t", chapter_from=1.0, offset_from=0, chapter_to=1.0, offset_to=11,
        timeline_id="MAIN", story_seq_from=1.0, story_seq_to=1.0,
        segment_type=SegmentType.MAIN, narrative_layer="MAIN",  # type: ignore[arg-type]
    )
    analysis = SceneAnalysis(
        chapter=1.0,
        cuts=[SceneCut(1.0, 4, "implicit:llm"), SceneCut(1.0, 8, "implicit:llm")],
        prior_loop_segments={0},
    )
    segs = apply_cuts_to_segments(ch, [main], analysis)
    assert [(s.offset_from, s.offset_to) for s in segs] == [(0, 3), (4, 7), (8, 11)]
    assert segs[0].segment_type is SegmentType.REGRESSION_PRIOR_LOOP
    assert segs[1].segment_type is SegmentType.MAIN and segs[1].timeline_id == "MAIN"
    # Tiling: no block left outside a segment (the flow auditor's segment.tiling check).
    covered = [i for s in segs for i in range(s.offset_from, s.offset_to + 1)]
    assert covered == list(range(12))


def test_cut_labels_round_trip_through_the_store() -> None:
    store = Store(":memory:")
    analysis = SceneAnalysis(
        chapter=3.0,
        cuts=[SceneCut(3.0, 5, "implicit:llm", cut_type=CutType.FLASHBACK, time_relation=TimeRelation.EARLIER)],
        prior_loop_segments={1},
    )
    save_scene_cuts(store, "t", analysis)
    back = load_scene_cuts(store, "t", 3.0)
    assert back is not None
    assert back.cuts[0].cut_type is CutType.FLASHBACK
    assert back.cuts[0].time_relation is TimeRelation.EARLIER
    assert back.prior_loop_segments == {1}


# ---------------------------------------------------------------------- presence


def _presence_store() -> Store:
    """RI ch1 shape: a clan head with elders; an absent boy they discuss; a speaker."""
    store = Store(":memory:")
    store.add_novel("t", "T", "x", "generic")
    texts = [
        "The clan head knelt before the altar in the rain.",
        "“The boy Fang Yuan has great talent,” said the first elder.",
        "The elders murmured about Fang Yuan and what he might become.",
        "The clan head listened to the old servant without a word.",
    ]
    store.add_chapter(
        Chapter(
            novel_id="t", number=1.0, title="T", source_href="a",
            blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)],
        )
    )
    store.add_self(Self(id="t:fy", novel_id="t", canonical_label="Fang Yuan", first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.add_self(Self(id="t:el", novel_id="t", canonical_label="First Elder", first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.add_self(
        Self(id="t:loc", novel_id="t", canonical_label="Gu Yue Village", first_attested_pos=DiscoursePosition(chapter=1, offset=0), kind=TargetKind.LOCATION)
    )

    def mention(i: int, block: int, text: str, target: str | None, mode: ReferenceMode, span: SpanType) -> Mention:
        return Mention(
            id=f"m{i}", novel_id="t", segment_id="t:1:main0", chapter=1.0, offset=0, text=text,
            alias_type=AliasType.RIGID_NAME, span_type=span, reference_mode=mode,
            target_kind=TargetKind.SELF if target else None, target_id=target, block_index=block,
        )

    store.add_mentions([
        mention(1, 0, "The clan head", None, ReferenceMode.PRESENT, SpanType.NARRATION_ACTION),
        mention(2, 1, "Fang Yuan", "t:fy", ReferenceMode.DIALOGUE_REFERENCE, SpanType.DIALOGUE),
        # The reader's own failure mode: a PRESENT mention of someone who is only discussed.
        mention(3, 2, "Fang Yuan", "t:fy", ReferenceMode.PRESENT, SpanType.NARRATION_DESCRIPTION),
        mention(4, 3, "The clan head", None, ReferenceMode.PRESENT, SpanType.NARRATION_ACTION),
        mention(5, 0, "Gu Yue Village", "t:loc", ReferenceMode.PRESENT, SpanType.NARRATION_DESCRIPTION),
    ])
    store.add_spans([
        Span(id="s1", novel_id="t", chapter=1.0, block_index=1, start=0, end=10, span_type=SpanType.DIALOGUE,
             text="x", speaker_self_id="t:el", attribution_method=AttributionMethod.EXPLICIT),
    ])
    store.conn.commit()
    return store


def test_presence_without_a_model_uses_speakers_and_never_lists_places() -> None:
    store = _presence_store()
    present, referenced = present_cast(store, "t", 1.0, 0, 3)
    assert "t:el" in present  # a speaker is in the room
    assert "t:loc" not in present + referenced  # a place is not a cast member
    assert "unresolved:clan head" in present
    # Without a model the PRESENT-mention failure mode shows: Fang Yuan has one DIALOGUE_REFERENCE,
    # so the talked-about count keeps him out even though block 2 calls him PRESENT.
    assert "t:fy" in referenced


def test_presence_model_overrides_mention_roles_and_is_cached() -> None:
    store = _presence_store()
    stub = StubProvider()

    def answer(_req, schema):
        # Candidate order is first appearance: clan head, Fang Yuan (the elder speaks, so is not asked).
        return schema.model_validate({"verdicts": [
            {"candidate": 1, "present": True}, {"candidate": 2, "present": False}]}).model_dump_json()

    stub.register("scene_presence", answer)
    present, referenced = present_cast(store, "t", 1.0, 0, 3, llm=stub)
    assert "t:fy" in referenced and "t:fy" not in present
    assert "unresolved:clan head" in present
    calls = len(stub.calls)
    present_cast(store, "t", 1.0, 0, 3, llm=stub)
    assert len(stub.calls) == calls  # served from derived_artifact


def test_segment_novel_splits_main_segments_only_when_scene_cuts_are_enabled(tmp_path) -> None:
    from echotales.pipeline.segment import SceneCutConfig, segment_novel

    def build() -> Store:
        store = Store(":memory:")
        store.add_novel("t", "T", "x", "generic")
        for ch in _volume("* * *"):
            store.add_chapter(ch)
        return store

    off = build()
    segment_novel("t", off)
    assert len(off.get_segments("t", 1.0)) == 1

    on = build()
    report = segment_novel("t", on, scene_cuts=SceneCutConfig(enabled=True, conventions_dir=str(tmp_path)))
    segs = on.get_segments("t", 1.0)
    assert [(s.offset_from, s.offset_to) for s in segs] == [(0, 5), (6, 10)]
    assert report.scene_cuts >= 1
    assert (tmp_path / "t.scene_conventions.json").exists()
    assert load_scene_cuts(on, "t", 1.0) is not None
