"""Scene-cut v5b: boundary refine, the story-time pass shown every time statement, presence defects. Fake LLMs only.

RI ch1 / ORV ch1 cases from docs/results/SCENE_INDUCTION.md (v5b).
"""

from __future__ import annotations

from types import SimpleNamespace

from echotales.pipeline.segment.outline import OutlineLine, RefineAnswer, refine_cut, refine_cuts
from echotales.pipeline.segment.storytime import (
    SegmentTime,
    StoryTimeAnswer,
    explicit_time_statements,
    prior_loop_segments,
    story_time_pass,
)
from test_scene_v4 import _chapter


class _Fake:
    model = "fake"

    def __init__(self, answer) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, request, schema):
        self.prompts.append(request.prompt)
        return SimpleNamespace(value=self.answer(schema))


def test_refine_moves_the_cut_one_block_back_when_the_block_before_already_turns_to_the_new_scene() -> None:
    ch = _chapter(20)
    assert refine_cut(ch, 10, _Fake(lambda s: RefineAnswer(before_cut="new", at_cut="new"))) == 9


def test_refine_moves_the_cut_one_block_on_when_the_cut_block_still_continues() -> None:
    ch = _chapter(20)
    assert refine_cut(ch, 10, _Fake(lambda s: RefineAnswer(before_cut="continues", at_cut="continues"))) == 11


def test_refine_keeps_a_cut_the_model_confirms_and_one_it_cannot_judge() -> None:
    ch = _chapter(20)
    assert refine_cut(ch, 10, _Fake(lambda s: RefineAnswer(before_cut="continues", at_cut="new"))) == 10

    def boom(schema):
        raise RuntimeError("unreachable")

    assert refine_cut(ch, 10, _Fake(boom)) == 10
    assert refine_cut(ch, 1, _Fake(lambda s: RefineAnswer(before_cut="new"))) == 1  # no block two before: unchanged


def test_refine_shows_four_blocks_and_collapses_cuts_that_land_together() -> None:
    ch = _chapter(20)
    llm = _Fake(lambda s: RefineAnswer(before_cut="new", at_cut="new"))
    assert refine_cuts(ch, [10, 9], llm) == [8, 9]
    assert llm.prompts[0].count("[") == 4 and "CUT" in llm.prompts[0]


def _time_chapter():
    texts = {2: "He was sent back. “This is 500 years ago?!” he said.", 9: "A quiet evening."}
    return _chapter(12, texts)


def test_every_explicit_time_statement_is_shown_with_its_segment() -> None:
    import spacy

    nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
    ch = _time_chapter()
    ranges = [(0, 4), (5, 11)]
    stated = explicit_time_statements(ch, ranges, nlp)
    assert any("500 years ago" in s and "segment 0" in s for s in stated)


def test_story_time_pass_lets_an_earlier_shown_segment_be_past_and_checks_the_quote() -> None:
    import spacy

    nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
    ch = _time_chapter()
    outline = [OutlineLine(i, who="Fang") for i in range(12)]

    def good(schema):
        return StoryTimeAnswer(
            main_segment=1,
            segments=[SegmentTime(segment=0, layer="past", time_relation="earlier", quote="This is 500 years ago")],
        )

    llm = _Fake(good)
    labels = story_time_pass(ch, [5], llm, nlp=nlp, outline=outline)
    assert prior_loop_segments(labels) == {0}
    assert "TIME STATEMENTS" in llm.prompts[0] and "500 years ago" in llm.prompts[0]

    def invented(schema):
        return StoryTimeAnswer(main_segment=1, segments=[SegmentTime(segment=0, layer="past", time_relation="earlier", quote="a thousand winters before")])

    assert prior_loop_segments(story_time_pass(ch, [5], _Fake(invented), nlp=nlp, outline=outline)) == set()


def test_a_segment_answered_twice_keeps_its_first_verified_answer() -> None:
    ch = _time_chapter()
    ans = StoryTimeAnswer(
        main_segment=1,
        segments=[
            SegmentTime(segment=0, layer="past", time_relation="earlier", quote="This is 500 years ago"),
            SegmentTime(segment=0, layer="present", time_relation="same", quote="A quiet evening"),
        ],
    )
    labels = story_time_pass(ch, [5], _Fake(lambda s: ans), nlp=None)
    assert labels[0].layer == "past"


def test_outline_narrator_is_not_an_unresolved_entity_and_on_screen_names_are_referenced() -> None:
    from echotales.core.enums import BlockType
    from echotales.core.models import Block, Chapter
    from echotales.core.store import Store
    from echotales.pipeline.segment.presence import present_cast

    # "Narrator" is the outline model's role word and no block says it; "tls123" appears only as message labels.
    texts = ["Author: tls123", "–tls123: Thank you.", "–tls123: It is thanks to my dear reader.", "I closed the phone."]
    store = Store(":memory:")
    store.add_novel("t", "T", "x", "generic")
    store.add_chapter(
        Chapter(novel_id="t", number=1.0, title="T", source_href="a", blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)])
    )
    outline = [OutlineLine(0, who="Narrator, tls123"), OutlineLine(1, who="Narrator, tls123"), OutlineLine(2, who="tls123"), OutlineLine(3, who="clan head")]
    outline[3] = OutlineLine(3, who="Narrator")
    present, referenced = present_cast(store, "t", 1.0, 0, 3, outline=outline)
    assert not any("narrator" in i for i in present + referenced)
    assert "unresolved:tls123" in referenced and "unresolved:tls123" not in present
