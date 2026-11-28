"""Scene-cut v4: whole-chapter outline, cast continuity from the graph, fusion. Fake LLMs only.

Each test pins a failure measured in v3 (docs/results/SCENE_INDUCTION.md): a per-boundary judge floods false cuts, so
the model answer is validated in code; landscape blocks name nobody and must not look like a cast change; and a
model that cannot be reached must never invent a cut.
"""

from __future__ import annotations

from types import SimpleNamespace

from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.pipeline.segment.cast import (
    FusionParams,
    block_casts,
    cast_cuts,
    cast_scores,
    fuse,
    separator_positions,
)
from echotales.pipeline.segment.outline import (
    OutlineAnswer,
    OutlineCache,
    OutlineItem,
    OutlineLine,
    SceneStart,
    SegmentAnswer,
    SegmentCache,
    outline_chapter,
    outline_prompt,
    segment_outline,
    validate_starts,
)

FILL = "walked slowly along the quiet road and said nothing at all today"


def _chapter(n: int = 20, texts: dict[int, str] | None = None) -> Chapter:
    texts = texts or {}
    return Chapter(
        novel_id="t",
        number=1.0,
        title="T",
        source_href="a.html",
        blocks=[Block(index=i, block_type=BlockType.PROSE, text=texts.get(i, f"{FILL} {i}.")) for i in range(n)],
    )


class FakeLLM:
    model = "fake"

    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls: list[str] = []

    def complete(self, request, schema):
        self.calls.append(request.stage)
        return SimpleNamespace(value=self.answer(request, schema))


def _echo_outline(request, schema):
    if schema is OutlineAnswer:
        ns = [int(x) for x in __import__("re").findall(r"^\[(\d+)\]", request.prompt, flags=__import__("re").M)]
        return OutlineAnswer(lines=[OutlineItem(n=n, who="Ann, Bob" if n < 10 else "Cara", where="the inn" if n == 0 else "") for n in ns])
    return SegmentAnswer(scene_starts=[SceneStart(block=10, reason="other people elsewhere")])


def test_outline_chunks_the_chapter_and_gives_one_line_per_story_block() -> None:
    ch = _chapter(60)
    llm = FakeLLM(_echo_outline)
    lines = outline_chapter(ch, llm)
    assert [ln.block for ln in lines] == list(range(60))
    assert len(llm.calls) >= 2  # 60 blocks do not fit one chunk
    assert lines[3].who == "Ann, Bob" and lines[30].who == "Cara"


def test_outline_is_cached_and_a_failed_chunk_is_not() -> None:
    ch = _chapter(30)
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        cache = OutlineCache(d, "fake")
        llm = FakeLLM(_echo_outline)
        outline_chapter(ch, llm, novel_id="n", cache=cache)
        n = len(llm.calls)
        outline_chapter(ch, llm, novel_id="n", cache=cache)
        assert len(llm.calls) == n

        def boom(request, schema):
            raise RuntimeError("down")

        bad = FakeLLM(boom)
        lines = outline_chapter(ch, bad, novel_id="m", cache=cache)
        assert all(not ln.who for ln in lines)
        assert cache.get("m", 1.0) is None


def test_validate_starts_drops_out_of_range_first_and_duplicates() -> None:
    lines = [OutlineLine(b) for b in range(5, 25)]
    starts = [SceneStart(block=20, reason="b"), SceneStart(block=5), SceneStart(block=99), SceneStart(block=20), SceneStart(block=12, reason="a")]
    assert validate_starts(starts, lines) == [(12, "a", 3), (20, "b", 3)]


def test_segment_outline_returns_validated_starts_and_survives_a_failure() -> None:
    ch = _chapter(20)
    lines = [OutlineLine(i, "Ann") for i in range(20)]
    assert segment_outline(ch, lines, FakeLLM(_echo_outline)) == [(10, "other people elsewhere", 3)]

    def boom(request, schema):
        raise RuntimeError("down")

    assert segment_outline(ch, lines, FakeLLM(boom)) == []  # an unreachable model never invents a cut
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        cache = SegmentCache(d, "fake")
        llm = FakeLLM(_echo_outline)
        segment_outline(ch, lines, llm, novel_id="n", cache=cache)
        segment_outline(ch, lines, llm, novel_id="n", cache=cache)
        assert len(llm.calls) == 1


def test_a_very_long_outline_is_trimmed_to_fit_the_context() -> None:
    lines = [OutlineLine(i, "A One, B Two, C Three, D Four", "somewhere far away", "three days later") for i in range(400)]
    text = outline_prompt(lines)
    assert len(text) / 3.2 <= 2700 or text.count("\n") < 400  # trimmed fields, or runs merged


def _graph_chapter() -> tuple[Chapter, dict[int, dict[str, float]]]:
    """Blocks 0-9 Ann and Bob; 10-14 landscape (nobody); 15-24 Cara and Dan."""
    ch = _chapter(25)
    casts: dict[int, dict[str, float]] = {}
    for i in range(10):
        casts[i] = {"ann": 1.0, "bob": 1.0}
    for i in range(15, 25):
        casts[i] = {"cara": 1.0, "dan": 1.0}
    return ch, casts


def test_cast_score_skips_landscape_blocks_and_peaks_across_the_gap() -> None:
    """RI ch1 31-35 names nobody; the score must still see the old cast against the new one."""
    ch, casts = _graph_chapter()
    s = cast_scores(ch, casts, 3)
    assert s[12] == 1.0 and s[5] == 0.0
    # every position in the gap scores the same; the cut goes at the earliest, right after the old cast
    assert cast_cuts(list(range(25)), s, 0.5, 3) == [10]


def test_same_people_continuing_scores_zero_and_no_cast_is_no_evidence() -> None:
    ch = _chapter(12)
    casts = {i: {"ann": 1.0} for i in range(12)}
    assert max(cast_scores(ch, casts, 3).values()) == 0.0
    assert set(cast_scores(ch, {}, 3).values()) == {0.0}


def test_reported_speech_weighs_less_than_acting() -> None:
    from echotales.core.enums import AliasType, ReferenceMode, SpanType
    from echotales.core.models import Mention

    def m(i: int, mode: ReferenceMode) -> Mention:
        return Mention(
            id=f"m{i}", novel_id="t", segment_id="s", chapter=1.0, offset=0, text="Fang Yuan", alias_type=AliasType.RIGID_NAME,
            span_type=SpanType.NARRATION_ACTION, reference_mode=mode, target_id="fang", block_index=i,
        )

    ch = _chapter(4)
    casts = block_casts(ch, [m(0, ReferenceMode.PRESENT), m(1, ReferenceMode.DIALOGUE_REFERENCE)])
    assert casts[0]["fang"] == 1.0 and casts[1]["fang"] < 0.5


def test_no_mentions_falls_back_to_capitalised_names() -> None:
    ch = _chapter(3, {1: "He saw Mr Bennet and Jane Bennet near the gate yesterday."})
    casts = block_casts(ch, None)
    assert casts[1] and not casts.get(0)


def test_separator_positions_are_structural() -> None:
    ch = _chapter(12, {5: "..."})
    assert separator_positions(ch) == {6}


def test_fusion_modes() -> None:
    ch, casts = _graph_chapter()
    sc = cast_scores(ch, casts, 3)
    seps = {20}
    # an outline cut where the cast changes is kept; one in the middle of Ann and Bob is dropped
    p = FusionParams("and", 3, 0.5, 2, False, 1)
    assert fuse(ch, [12, 5], sc, seps, p) == [12]
    # ... unless a separator sits at it
    assert fuse(ch, [20], sc, seps, FusionParams("and", 3, 0.5, 0, True, 1)) == [20]
    assert fuse(ch, [20], sc, seps, FusionParams("and", 3, 0.5, 0, False, 1)) == []
    assert fuse(ch, [12, 5], sc, seps, FusionParams("outline", min_gap=1)) == [5, 12]
    assert fuse(ch, [5], sc, set(), FusionParams("cast", 3, 0.5, min_gap=3)) == [10]
    # "or" adds a cast cut only when a separator backs it
    assert fuse(ch, [5], sc, {10}, FusionParams("or", 3, 0.5, min_gap=1)) == [5, 10]
    assert fuse(ch, [5], sc, set(), FusionParams("or", 3, 0.5, min_gap=1)) == [5]
    # min_gap spaces the survivors
    assert fuse(ch, [5, 6], sc, seps, FusionParams("outline", min_gap=3)) == [5]


def test_method_outline_end_to_end_with_a_stub_model() -> None:
    """analyse_chapter_scenes(method="outline"): the model's start becomes a cut; an unreachable model gives none."""
    from echotales.pipeline.segment.scenes import analyse_chapter_scenes
    from echotales.pipeline.segment.storytime import StoryTimeAnswer

    ch = _chapter(30)

    def answer(request, schema):
        if schema is StoryTimeAnswer:
            return StoryTimeAnswer()
        return _echo_outline(request, schema)

    an = analyse_chapter_scenes(ch, None, llm=FakeLLM(answer), method="outline", novel_id="t", outline_params=FusionParams("outline", min_gap=1))
    assert [c.block for c in an.cuts] == [10]
    assert an.cuts[0].source == "outline" and an.cuts[0].evidence == ["other people elsewhere"]

    def boom(request, schema):
        raise RuntimeError("down")

    assert analyse_chapter_scenes(ch, None, llm=FakeLLM(boom), method="outline", novel_id="t").cuts == []
