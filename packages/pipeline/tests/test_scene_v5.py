"""Scene-cut v5: one-to-one +-1 block scoring and the thinking segmentation call. Fake LLMs only.

The scorer pins the v4 RI ch1 case (docs/results/SCENE_INDUCTION.md): qwen3 answered {31, 80} for gold {31, 79}, which
exact scoring counted as a false positive and a false negative at once.
"""

from __future__ import annotations

from types import SimpleNamespace

from echotales.pipeline.llm.base import LLMRequest
from echotales.pipeline.segment.outline import (
    OutlineLine,
    SceneStart,
    SegmentAnswer,
    SegmentCache,
    segment_outline,
)
from echotales.pipeline.segment.scoring import match_cuts, score_cuts
from test_scene_v4 import _chapter


def test_off_by_one_is_a_hit_with_tolerance_and_two_errors_exactly() -> None:
    assert score_cuts({31, 79}, {31, 80}, 0) == (1, 1, 1)
    assert score_cuts({31, 79}, {31, 80}, 1) == (2, 0, 0)
    assert score_cuts({31, 79}, {31, 81}, 1) == (1, 1, 1)


def test_matching_is_one_to_one() -> None:
    # two predictions beside one gold cut: one hit, one false positive; one prediction between two gold cuts: one hit
    assert score_cuts({10}, {9, 11}, 1) == (1, 1, 0)
    assert match_cuts({10, 12}, {11}, 1) == [(10, 11)]
    assert score_cuts({10, 12}, {11}, 1) == (1, 0, 1)


def test_greedy_pairing_is_not_fooled_by_a_near_neighbour() -> None:
    # 10 must pair with 9 and 12 with 11 (both within 1); pairing 10 with 11 would strand 12
    assert score_cuts({10, 12}, {9, 11}, 1) == (2, 0, 0)


def test_prediction_beside_an_ambiguous_gold_cut_is_neither_hit_nor_error() -> None:
    assert score_cuts({5}, {5, 20}, 1, ignore={21}) == (1, 0, 0)
    assert score_cuts({5}, {5, 20}, 1, ignore={40}) == (1, 1, 0)


class _ThinkLLM:
    model = "fake"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def complete(self, request, schema):
        self.requests.append(request)
        return SimpleNamespace(value=SegmentAnswer(scene_starts=[SceneStart(block=8, confidence=5, reason="elsewhere")]))


def test_segment_outline_asks_for_thinking_only_when_told_and_keeps_the_cap() -> None:
    import tempfile

    ch = _chapter(20)
    lines = [OutlineLine(i, who="Ann") for i in range(20)]
    llm = _ThinkLLM()
    assert [b for b, _, _ in segment_outline(ch, lines, llm)] == [8]
    assert llm.requests[-1].extra == {} and llm.requests[-1].max_tokens == 300
    with tempfile.TemporaryDirectory() as d:
        cache = SegmentCache(d, "fake", "think")
        out = segment_outline(ch, lines, llm, cache=cache, think=True, max_tokens=7000)
        assert [b for b, _, _ in out] == [8]
        assert llm.requests[-1].extra == {"think": True} and llm.requests[-1].max_tokens == 7000
        assert cache.get("", 1.0) is not None and cache.dir.name.endswith("_think")


def test_outline_presence_keeps_a_talked_about_person_out_and_adds_an_unmapped_group() -> None:
    from echotales.pipeline.segment.presence import (
        _name_tokens,
        _same_person,
        outline_present_labels,
    )

    # Fang Yuan is named in every block of the clan head's talk but listed as acting in none (RI ch1 31-78)
    outline = [OutlineLine(i, who="Gu Yue clan head, elders") for i in range(31, 36)] + [OutlineLine(40, who="Fang Yuan")]
    who = outline_present_labels(outline, 31, 39)
    toks = [w for _, _, w in who]
    assert not any(_same_person(_name_tokens("Gu Yue Fang Yuan"), w) for w in toks)
    assert any(_same_person(_name_tokens("Gu Yue clan head"), w) for w in toks)
    assert any(_same_person(_name_tokens("elder"), w) for w in toks)  # plural -s does not split them
    assert outline_present_labels(outline, 40, 40)[0][1] == "Fang Yuan"


def test_present_cast_reads_the_outline_who_lines_and_never_asks_the_model() -> None:
    from echotales.pipeline.segment.presence import present_cast
    from test_scene_induction import _presence_store

    store = _presence_store()
    # Fang Yuan has a PRESENT mention in block 2, but the outline never lists him as acting; the clan head acts in 0 and 3;
    # the elder speaks (block 1); "the old servant" is in no mention at all but is listed in two blocks.
    outline = [OutlineLine(0, who="clan head"), OutlineLine(1, who="Elder, old servant"), OutlineLine(2, who="old servant"), OutlineLine(3, who="clan head")]
    llm = _ThinkLLM()
    present, referenced = present_cast(store, "t", 1.0, 0, 3, llm=llm, outline=outline)
    assert llm.requests == []
    assert "t:fy" in referenced and "t:fy" not in present
    assert "t:el" in present and "unresolved:clan head" in present
    assert "unresolved:old servant" in present  # listed in 2 blocks, no entity in the graph


def test_outline_options_send_the_segmentation_call_to_a_separate_thinking_model() -> None:
    from echotales.pipeline.segment.cast import FusionParams
    from echotales.pipeline.segment.outline import OutlineOptions
    from echotales.pipeline.segment.scenes import SceneCutConfig, analyse_chapter_scenes
    from echotales.pipeline.segment.storytime import StoryTimeAnswer
    from test_scene_v4 import FakeLLM, _echo_outline

    def answer(request, schema):
        return StoryTimeAnswer() if schema is StoryTimeAnswer else _echo_outline(request, schema)

    small, big = FakeLLM(answer), FakeLLM(answer)
    opts = OutlineOptions(think=True, max_tokens=7000, segment_llm=big, tag="think")
    cfg = SceneCutConfig(enabled=True, method="outline", outline_options=opts)
    an = analyse_chapter_scenes(_chapter(30), None, llm=small, method=cfg.method, novel_id="t", outline_params=FusionParams("outline", min_gap=1), outline_options=cfg.outline_options)
    assert [c.block for c in an.cuts] == [10]
    assert "scene_segment" in big.calls and "scene_segment" not in small.calls
    assert "scene_outline" in small.calls and "scene_outline" not in big.calls


def test_raw_text_prompt_shrinks_the_words_per_block_to_fit_and_keeps_every_row() -> None:
    from echotales.pipeline.segment.outline import RAW_TOKEN_BUDGET, _est_tokens, raw_outline_prompt

    ch = _chapter(120, {i: "word " * 80 for i in range(120)})
    lines = [OutlineLine(i, who="Ann", where="inn") for i in range(120)]
    short = raw_outline_prompt(lines, ch, 40)
    assert len(short.splitlines()) == 120 and _est_tokens(short) <= RAW_TOKEN_BUDGET
    few = raw_outline_prompt(lines[:10], ch, 40)
    assert few.splitlines()[0].count("word") == 40  # a short chapter keeps the full 40 words
    assert "<Ann | inn>" in few
