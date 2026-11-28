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
