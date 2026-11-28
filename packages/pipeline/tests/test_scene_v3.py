"""Scene-cut v3: candidate union, the pairwise judge, rule decision, the story-time quote check, quoted presence.

Fake LLMs only. Each test pins a failure measured on the v2.1 run (docs/results/SCENE_INDUCTION.md): a parallel
action has time SAME and still must cut, one person walking on is not a cut, and a model answer without a quote
that exists in the chapter must not become a layer.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.pipeline.segment.cuts import TimeRelation
from echotales.pipeline.segment.discontinuity import Boundary
from echotales.pipeline.segment.judge import (
    BoundaryJudgement,
    CutRule,
    JudgeAnswer,
    JudgeCache,
    build_prompt,
    candidate_boundaries,
    decide_cuts,
    judge_boundary,
    rule_grid,
    story_blocks,
)
from echotales.pipeline.segment.place_tags import TaggedBlock
from echotales.pipeline.segment.presence import Candidate, _classify, _quote_checks
from echotales.pipeline.segment.storytime import (
    SegmentTime,
    SegmentTimeLabel,
    StoryTimeAnswer,
    prior_loop_segments,
    quote_in,
    story_time_pass,
)

FILL = "walked slowly along the quiet road and said nothing at all today"


def _chapter(n: int = 20) -> Chapter:
    return Chapter(
        novel_id="t",
        number=1.0,
        title="T",
        source_href="a.html",
        blocks=[Block(index=i, block_type=BlockType.PROSE, text=f"Person{i % 3} {FILL} {i}.") for i in range(n)],
    )


class FakeLLM:
    model = "fake"

    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls = 0

    def complete(self, request, schema):
        self.calls += 1
        return SimpleNamespace(value=self.answer(request.prompt))


def _bound(pos: int, score: float = 0.1, marker: list[int] | None = None) -> Boundary:
    return Boundary(position=pos, marker_blocks=marker or [], features={}, score=score, evidence={})


def test_candidates_are_the_union_of_proposers_and_judge_neighbours() -> None:
    ch = _chapter()
    bs = [_bound(i, 0.9 if i == 12 else 0.1) for i in range(1, 20)]
    tags = [TaggedBlock(i, "room" if i < 5 else "street", TimeRelation.SAME) for i in range(20)]
    cands = candidate_boundaries(ch, bs, tags, disc_rate=0.05, spread=1)
    pos = {c.position for c in cands}
    # tag change at 5, score peak at 12, each with its one-block neighbours (gold needs the exact block)
    assert {4, 5, 6, 11, 12, 13} <= pos
    assert 0 not in pos


def test_separator_marks_the_candidate_without_any_word_list() -> None:
    ch = _chapter()
    bs = [_bound(i, 0.1, marker=[99] if i == 8 else None) for i in range(1, 20)]
    cands = {c.position: c for c in candidate_boundaries(ch, bs, None, disc_rate=0.0, spread=0)}
    assert cands[8].separator and "sep" in cands[8].sources


def test_parallel_action_cuts_even_though_time_is_the_same() -> None:
    """RI ch1 block 79: another place, other people, same moment; v2.1's place-and-time rule could never fire."""
    j = BoundaryJudgement(79, time_continuous="yes", same_location="no", same_people_in_focus="no")
    rule = CutRule("place&people", False, False, True)
    assert rule.fires(j)
    assert not CutRule("time_no", False, True, False).fires(j)


def test_same_people_walking_to_the_next_room_is_not_a_cut() -> None:
    """RI ch1 block 75: the clan head walks to his garret; gold keeps the scene."""
    j = BoundaryJudgement(75, time_continuous="yes", same_location="yes", same_people_in_focus="yes")
    assert not any(r.fires(j) for r in rule_grid())


def test_decide_cuts_keeps_the_most_clearly_broken_block_of_an_adjacent_run() -> None:
    ch = _chapter()
    js = [
        BoundaryJudgement(9, "yes", "no", "yes"),
        BoundaryJudgement(10, "no", "no", "no"),
        BoundaryJudgement(11, "yes", "no", "yes"),
        BoundaryJudgement(16, "no", "yes", "yes"),
    ]
    rule = CutRule("any", False, True, False, True, min_gap=1)
    assert decide_cuts(js, rule, ch) == [10, 16]
    assert decide_cuts(js, CutRule("any", False, True, False, True, min_gap=8), ch) == [10]


def test_judge_cache_makes_a_rerun_free_and_failure_invents_no_cut(tmp_path) -> None:
    ch = _chapter()
    llm = FakeLLM(lambda p: JudgeAnswer(time_continuous="no", same_location="no", same_people_in_focus="no", reason="x"))
    cache = JudgeCache(tmp_path, "fake")
    a = judge_boundary(ch, 10, llm, novel_id="t", cache=cache)
    b = judge_boundary(ch, 10, llm, novel_id="t", cache=cache)
    assert llm.calls == 1 and a == b and a.time_continuous == "no"

    def boom(_):
        raise RuntimeError("down")

    bad = judge_boundary(ch, 11, FakeLLM(boom), novel_id="t", cache=cache)
    assert (bad.time_continuous, bad.same_location, bad.same_people_in_focus) == ("unclear", "yes", "yes")
    assert json.loads(cache.path("t", 1.0, 10).read_text())["block"] == 10


def test_prompt_shows_three_blocks_each_side_and_the_people_before() -> None:
    ch = _chapter()
    p = build_prompt(ch, 10, ["Fang Yuan"])
    assert p.count("- Person") == 6 and "Fang Yuan" in p
    assert story_blocks(ch)[0] == 0


def test_unrecognised_judge_values_fall_back_to_continuous() -> None:
    j = BoundaryJudgement.from_answer(5, JudgeAnswer(time_continuous="maybe", same_location="??", same_people_in_focus="NO"))
    assert (j.time_continuous, j.same_location, j.same_people_in_focus) == ("unclear", "yes", "no")


def test_story_time_quote_must_exist_in_the_chapter() -> None:
    ch = Chapter(
        novel_id="t",
        number=1.0,
        title="T",
        source_href="a.html",
        blocks=[
            Block(index=0, block_type=BlockType.PROSE, text="He fell from the cliff and died."),
            Block(index=1, block_type=BlockType.PROSE, text="The rain fell on the village that morning."),
            Block(index=2, block_type=BlockType.PROSE, text="This is five hundred years ago, he thought."),
        ],
    )

    def answer(prompt):
        return StoryTimeAnswer(
            main_segment=1,
            segments=[
                SegmentTime(segment=0, layer="past", time_relation="earlier", quote="five hundred years ago"),
                SegmentTime(segment=2, layer="dream", time_relation="later", quote="invented words nowhere"),
            ],
        )

    labels = story_time_pass(ch, [1, 2], FakeLLM(answer))
    assert labels[0].verified and labels[0].layer == "past" and labels[0].time_relation is TimeRelation.EARLIER
    assert not labels[2].verified and labels[2].layer == "present"
    assert prior_loop_segments(labels) == {0}
    assert quote_in("He said: Hello, there!", "hello there") and not quote_in("abc def", "abc")


def test_prior_loop_needs_a_verified_earlier_past() -> None:
    labels = [SegmentTimeLabel(0, "past", TimeRelation.UNKNOWN, "x y", True), SegmentTimeLabel(1, "past", TimeRelation.EARLIER, "", False)]
    assert prior_loop_segments(labels) == set()


def test_presence_needs_a_quote_from_a_block_about_the_person() -> None:
    texts = {0: "Fang Yuan bowed to the elder.", 1: "The elders discussed the boy at length."}
    c = Candidate(entity_id="e1", label="Fang Yuan", blocks=[0])
    assert _quote_checks(c, "Fang Yuan bowed to", texts, 0, 1)
    assert not _quote_checks(c, "elders discussed the boy", texts, 0, 1)  # real quote, but a block that is not about him
    assert not _quote_checks(c, "he never appears here", texts, 0, 1)

    from echotales.pipeline.segment.presence import PresenceResponse, Verdict

    llm = FakeLLM(lambda p: PresenceResponse(verdicts=[Verdict(candidate=1, present=True, quote="made up words here")]))
    assert _classify(llm, "scene", [c], texts, 0, 1) == {"e1": False}
    llm2 = FakeLLM(lambda p: PresenceResponse(verdicts=[Verdict(candidate=1, present=True, quote="Fang Yuan bowed to the elder")]))
    assert _classify(llm2, "scene", [c], texts, 0, 1) == {"e1": True}
