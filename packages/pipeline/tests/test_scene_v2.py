"""Scene-cut v2: model scene lists, place/time tags, the score combination, the presence fix, embedder fallback.

Fake LLMs only; the measured behaviour on real novels is in docs/results/SCENE_INDUCTION.md. These pin the
contracts that the v2 failures taught: a model that lists a scene per beat must not turn into a cut per beat,
a place worded two ways is one place, and a missing embedder or parser degrades instead of raising.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.pipeline.segment.cuts import CutType, TimeRelation
from echotales.pipeline.segment.discontinuity import Boundary
from echotales.pipeline.segment.embed import OllamaEmbedder, cosine_distance, get_embedder
from echotales.pipeline.segment.llm_segment import (
    LLMScene,
    SceneItem,
    SceneList,
    _same_place,
    cut_type_for,
    segment_chapter_llm,
)
from echotales.pipeline.segment.place_tags import (
    BlockTag,
    BlockTagList,
    PlaceCutParams,
    TaggedBlock,
    place_candidates,
    scenes_from_tags,
    select_cuts,
    tag_chapter,
)
from echotales.pipeline.segment.presence import Candidate, _heuristic, _is_subject_at
from echotales.pipeline.segment.scenes import combine_llm_cuts

FILL = "walked slowly along the quiet road and said nothing at all today"


def _chapter(n: int = 40) -> Chapter:
    return Chapter(
        novel_id="t",
        number=1.0,
        title="T",
        source_href="a.html",
        blocks=[Block(index=i, block_type=BlockType.PROSE, text=f"Person{i % 3} {FILL} {i}.") for i in range(n)],
    )


class FakeLLM:
    """Returns whatever `answer(prompt)` builds, wrapped like an LLMResult."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, request, schema):
        self.prompts.append(request.prompt)
        return SimpleNamespace(value=self.answer(request.prompt))


# ------------------------------------------------------------------ llm_segment


def test_segment_chapter_llm_merges_a_scene_that_repeats_the_previous_place() -> None:
    """LotM ch2: the model listed 17 'scenes' in 76 blocks with the place unchanged; only a real place change is a cut."""
    items = [
        SceneItem(start=0, place="Fang Yuan's room"),
        SceneItem(start=10, place="Fang Yuan's room"),  # same place, no time move: not a cut
        SceneItem(start=20, place="Clan hall", time_relation="LATER"),
    ]
    scenes = segment_chapter_llm(_chapter(), FakeLLM(lambda _p: SceneList(scenes=items)))
    assert [s.start for s in scenes] == [0, 20]
    assert scenes[1].time_relation is TimeRelation.LATER


def test_segment_chapter_llm_ignores_unreachable_model() -> None:
    def boom(_p):
        raise RuntimeError("ollama down")

    scenes = segment_chapter_llm(_chapter(), FakeLLM(boom))
    assert [s.start for s in scenes] == [0]  # no model answer means no invented cuts


def test_segment_chapter_llm_drops_starts_that_are_not_shown_blocks() -> None:
    items = [SceneItem(start=0, place="a"), SceneItem(start=999, place="elsewhere")]
    assert len(segment_chapter_llm(_chapter(), FakeLLM(lambda _p: SceneList(scenes=items)))) == 1


def test_same_place_is_wording_tolerant_but_not_loose() -> None:
    assert _same_place("the clan hall", "clan hall")
    assert not _same_place("clan hall", "mountain cliff")
    assert not _same_place("", "clan hall")


def test_cut_type_follows_time_relation() -> None:
    assert cut_type_for(LLMScene(1, time_relation=TimeRelation.EARLIER)) is CutType.FLASHBACK
    assert cut_type_for(LLMScene(1, time_relation=TimeRelation.LATER)) is CutType.TIME_JUMP
    assert cut_type_for(LLMScene(1)) is CutType.NEW_SCENE


# ------------------------------------------------------------------ combine_llm_cuts


def _boundaries(scores: dict[int, float]) -> list[Boundary]:
    return [Boundary(position=p, marker_blocks=[], features={}, score=s, evidence={}) for p, s in sorted(scores.items())]


def test_combine_keeps_a_model_cut_only_where_the_score_agrees() -> None:
    ch = _chapter()
    scenes = [LLMScene(0), LLMScene(10, "hall"), LLMScene(25, "street")]
    cuts = combine_llm_cuts(ch, scenes, _boundaries({10: 0.9, 25: 0.1}), accept_score=0.5)
    assert [c.block for c in cuts] == [10]


def test_combine_accepts_a_low_score_cut_when_enough_models_voted() -> None:
    ch = _chapter()
    scenes = [LLMScene(0), LLMScene(25, "street")]
    b = _boundaries({25: 0.1})
    assert combine_llm_cuts(ch, scenes, b, accept_score=0.5) == []
    got = combine_llm_cuts(ch, scenes, b, accept_score=0.5, votes={25: 2}, min_votes=2)
    assert [c.block for c in got] == [25] and got[0].confidence < 0.9


def test_combine_drops_a_cut_adjacent_to_the_previous_one() -> None:
    ch = _chapter()
    scenes = [LLMScene(0), LLMScene(10, "a"), LLMScene(11, "b")]
    cuts = combine_llm_cuts(ch, scenes, _boundaries({10: 0.9, 11: 0.9}), accept_score=0.5)
    assert [c.block for c in cuts] == [10]


# ------------------------------------------------------------------ place tags


def _tags(places: list[str], shifts: dict[int, TimeRelation] | None = None) -> list[TaggedBlock]:
    return [TaggedBlock(i, p, (shifts or {}).get(i, TimeRelation.SAME)) for i, p in enumerate(places)]


def test_tag_chapter_fills_missing_answers_with_the_previous_place() -> None:
    ch = _chapter(30)

    def answer(prompt: str) -> BlockTagList:
        # The model answers only the first block of each window.
        first = int(prompt.split("[")[1].split("]")[0])
        return BlockTagList(tags=[BlockTag(i=first, place="Hall")])

    tags = tag_chapter(ch, FakeLLM(answer))
    assert len(tags) == 30 and {t.place for t in tags} == {"Hall"}


def test_tag_chapter_carries_the_last_place_into_the_next_window() -> None:
    ch = _chapter(30)
    llm = FakeLLM(lambda p: BlockTagList(tags=[BlockTag(i=int(p.split("[")[1].split("]")[0]), place="Cliff")]))
    tag_chapter(ch, llm)
    assert "previous block's place was: Cliff" in llm.prompts[1]


def test_tag_chapter_survives_an_unreachable_model() -> None:
    def boom(_p):
        raise RuntimeError("down")

    tags = tag_chapter(_chapter(8), FakeLLM(boom))
    assert len(tags) == 8 and all(t.time_shift is TimeRelation.SAME for t in tags)


def test_place_change_is_a_cut_and_rewording_is_not() -> None:
    places = ["old stone cliff"] * 10 + ["old stone cliff top"] * 4 + ["clan hall"] * 10
    ch = _chapter(len(places))
    scenes = scenes_from_tags(ch, _tags(places), PlaceCutParams(threshold=0.5, min_gap=3, both=False))
    assert [s.start for s in scenes] == [0, 14]


def test_one_block_aside_does_not_cut() -> None:
    """A single block set elsewhere is a detour of the text, not a scene: averaging over 3 blocks per side damps it."""
    places = ["clan hall"] * 10 + ["window"] + ["clan hall"] * 10
    ch = _chapter(len(places))
    scenes = scenes_from_tags(ch, _tags(places), PlaceCutParams(threshold=0.75, min_gap=3, both=False))
    assert [s.start for s in scenes] == [0]


def test_time_jump_cuts_without_a_place_change_and_can_be_switched_off() -> None:
    places = ["clan hall"] * 20
    ch = _chapter(20)
    tags = _tags(places, {10: TimeRelation.LATER})
    assert [s.start for s in scenes_from_tags(ch, tags, PlaceCutParams(threshold=0.5, time_weight=0.6, both=False))] == [0, 10]
    assert [s.start for s in scenes_from_tags(ch, tags, PlaceCutParams(threshold=0.5, time_weight=0.0, both=False))] == [0]


def test_cap_keeps_the_strongest_cuts_per_the_learned_rate() -> None:
    places = ["a b"] * 8 + ["c d"] * 8 + ["e f"] * 8 + ["a b"] * 8
    ch = _chapter(len(places))
    cands = place_candidates(_tags(places), None)
    chosen = select_cuts(ch, cands, PlaceCutParams(threshold=0.1, cap_rate=0.05, min_gap=2, both=False), len(places))
    assert len(chosen) == 2  # ceil(0.05 * 32)


class _FakeEmbedder:
    """Maps each place string to a fixed vector so the embedding path is exercised without ollama."""

    def __init__(self, table: dict[str, list[float]]) -> None:
        self.table = table

    def embed(self, texts):
        return [self.table[t] for t in texts]


def test_embedding_distance_sees_synonymous_places_as_one() -> None:
    """Token overlap calls 'the great hall' and 'banquet room' different; the embedder knows they are not."""
    places = ["the great hall"] * 6 + ["banquet room"] * 6 + ["mountain cliff"] * 6
    emb = _FakeEmbedder(
        {"the great hall": [1.0, 0.0], "banquet room": [0.98, 0.2], "mountain cliff": [0.0, 1.0]}
    )
    ch = _chapter(len(places))
    p = PlaceCutParams(threshold=0.5, min_gap=3, both=False)
    with_emb = scenes_from_tags(ch, _tags(places), p, embedder=emb)
    without = scenes_from_tags(ch, _tags(places), p, embedder=None)
    assert [s.start for s in with_emb] == [0, 12]
    assert [s.start for s in without] == [0, 6, 12]


def test_unreachable_embedder_falls_back_to_token_overlap() -> None:
    class Down:
        def embed(self, _texts):
            return None

    places = ["clan hall"] * 6 + ["mountain cliff"] * 6
    scenes = scenes_from_tags(_chapter(12), _tags(places), PlaceCutParams(threshold=0.5, min_gap=3, both=False), embedder=Down())
    assert [s.start for s in scenes] == [0, 6]


def test_ollama_embedder_reports_unavailable_instead_of_raising() -> None:
    e = OllamaEmbedder(host="http://127.0.0.1:9")  # nothing listens on the discard port
    assert e.available() is False
    assert e.embed(["x"]) is None
    assert get_embedder.__name__ == "get_embedder"


def test_cosine_distance_handles_zero_vectors() -> None:
    assert cosine_distance([0.0, 0.0], [1.0, 0.0]) == 0.5
    assert cosine_distance([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


# ------------------------------------------------------------------ presence fix


def test_heuristic_requires_acting_mentions_not_just_narration_mentions() -> None:
    """RI ch1: Fang Yuan is named in narration of the ritual (talked about) and must stay referenced-only."""
    talked = Candidate("e1", "Fang Yuan", narration_present_mentions=3, acting_mentions=0)
    acting = Candidate("e2", "Clan Head", narration_present_mentions=3, acting_mentions=3)
    assert _heuristic(talked) is False
    assert _heuristic(acting) is True
    assert _heuristic(Candidate("e3", "Elder", speaks=True)) is True


def test_subject_test_separates_actor_from_topic() -> None:
    text = "The elders were discussing the youth Fang Yuan while the clan head watched."
    a = _is_subject_at(text, text.index("Fang Yuan"), len("Fang Yuan"))
    if a is None:
        pytest.skip("spaCy dependency parser not installed")
    b = _is_subject_at(text, text.index("clan head"), len("clan head"))
    assert a is False and b is True
