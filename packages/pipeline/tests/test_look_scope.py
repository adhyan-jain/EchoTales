"""A character's default look versus a change to it (owner, 2026-10-31).

"Blue eyes" stated in chapter 12 is not a change in chapter 12; it is true of the character from their first
appearance, and chapter 1's picture should have them. "Half his face was burned" in chapter 8 is a change: it holds
from chapter 8 on, and the earlier chapters keep the old face. Both are stated late, so what separates them is what the
sentence says, and the story clock (when it is true) has to be kept apart from the reading clock (when it was learned).
"""

from __future__ import annotations

import pytest
from echotales.core.enums import AssertedBy, TargetKind, TruthStatus
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import appearance_of
from echotales.pipeline.persona.split import standing_values
from echotales.pipeline.reader.facts_pass import fact_scope, story_start


@pytest.mark.parametrize(
    ("attribute", "quote", "scope"),
    [
        ("eye_color", "He had blue eyes and a quiet manner.", "baseline"),
        ("hair_color", "Her black hair fell to her waist.", "baseline"),
        ("height_build", "A tall, broad man with a heavy tread.", "baseline"),
        ("hair_color", "His hair had turned white after the fire.", "change"),
        ("hair_color", "She dyed her hair red.", "change"),
        ("eye_color", "Now one eye was gone, lost in the war.", "change"),
        ("distinguishing_features", "Half his face was burned.", "change"),
        ("typical_attire", "He wore a black robe.", "state"),
        ("hair_style", "She wore her hair in a long braid.", "state"),
    ],
)
def test_the_sentence_decides_default_look_or_change(attribute: str, quote: str, scope: str) -> None:
    assert fact_scope(attribute, quote) == scope


def test_a_default_trait_is_true_from_the_characters_first_appearance() -> None:
    assert story_start("baseline", stated=12, first_attested=1) == 1
    assert story_start("baseline", stated=3, first_attested=7) == 3  # never later than the statement itself
    assert story_start("change", stated=8, first_attested=1) == 8
    assert story_start("state", stated=8, first_attested=1) == 8


def _row(key: str, value: str, from_chapter: int, learned_chapter: int) -> Attribute:
    return Attribute(
        target_kind=TargetKind.PERSONA, target_id="p:body1", key=key, value=value,
        interval=FuzzyInterval.open_ended(from_chapter, last_evidence=learned_chapter),
        learned_at_pos=DiscoursePosition(chapter=learned_chapter, offset=0), observer_id="READER",
        asserted_by=AssertedBy.INFERENCE, truth_status=TruthStatus.TRUE, evidence="t",
    )


def _store(*rows: Attribute) -> Store:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    for row in rows:
        store.add_attribute("n", row)
    return store


# Black hair is the default look (true from chapter 1, learned in chapter 12); white hair is a change that happened in
# chapter 8 and was learned in chapter 8. Learned-latest alone would pick black at chapter 9, which is wrong.
HAIR = (_row("hair_color", "black", from_chapter=1, learned_chapter=12), _row("hair_color", "white", 8, 8))


@pytest.mark.parametrize(("chapter", "expected"), [(1, "black"), (5, "black"), (8, "white"), (9, "white"), (12, "white"), (40, "white")])
def test_a_later_story_state_beats_a_default_learned_later(chapter: int, expected: str) -> None:
    store = _store(*HAIR)
    assert appearance_of(store, "p:body1", standing_only=False, position=chapter)["hair_color"] == expected
    assert standing_values(store, "p:body1", position=chapter)["hair_color"] == expected


def test_the_default_reaches_chapter_one_before_it_was_learned() -> None:
    store = _store(_row("eye_color", "blue", from_chapter=1, learned_chapter=12))
    assert appearance_of(store, "p:body1", standing_only=False, position=1)["eye_color"] == "blue"


def test_rows_that_differ_only_in_learned_time_keep_the_old_rule() -> None:
    """Prefix-causal trait revisions share one story interval and differ in learned time: the latest learned wins."""
    store = _store(_row("eye_color", "gray", 1, 3), _row("eye_color", "green", 1, 9))
    assert appearance_of(store, "p:body1", standing_only=False, position=20)["eye_color"] == "green"
    assert standing_values(store, "p:body1", position=20)["eye_color"] == "green"


def _facts_run(number: float, text: str, claim: dict):  # type: ignore[type-arg]
    """Run the real facts pass for one chapter of a character first seen in chapter 1."""
    from echotales.core.enums import BlockType, Prominence
    from echotales.core.models import Block, Chapter, Self
    from echotales.pipeline.llm.client import ModelClient
    from echotales.pipeline.llm.stub import StubProvider
    from echotales.pipeline.reader import facts_pass as fp

    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    chapter = Chapter(novel_id="n", number=number, title="T", source_href="a",
                      blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)])
    store.add_chapter(chapter)
    store.add_self(Self(id="n:self:tom", novel_id="n", canonical_label="Tom", prominence=Prominence.RECURRING,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    stub = StubProvider()
    stub.register_response("reader", {"appearance": [claim], "identities": [], "ages": []})
    report = fp.read_chapter_facts(store, ModelClient(provider_override=stub), chapter)
    rows = store.get_attributes(TargetKind.PERSONA, "n:self:tom:body1")
    return rows, report


def test_blue_eyes_stated_in_chapter_twelve_hold_from_chapter_one() -> None:
    rows, report = _facts_run(
        12.0, "Tom had blue eyes and a quiet manner.",
        {"character": "Tom", "attribute": "eye_color", "value": "blue", "quote": "Tom had blue eyes"},
    )
    assert [(r.key, r.interval.from_lb, r.learned_at_pos.chapter) for r in rows] == [("eye_color", 1, 12)]
    assert report.retroactive == 1


def test_a_burned_face_stated_in_chapter_eight_starts_in_chapter_eight() -> None:
    rows, report = _facts_run(
        8.0, "Half of Tom's face was burned in the fire.",
        {"character": "Tom", "attribute": "distinguishing_features", "value": "half his face burned",
         "quote": "Half of Tom's face was burned"},
    )
    assert [(r.key, r.interval.from_lb, r.learned_at_pos.chapter) for r in rows] == [("distinguishing_features", 8, 8)]
    assert report.retroactive == 0


def test_a_change_to_a_default_trait_starts_when_it_happens_not_at_chapter_one() -> None:
    rows, _ = _facts_run(
        9.0, "Tom's hair had turned white after the fire.",
        {"character": "Tom", "attribute": "hair_color", "value": "white", "quote": "Tom's hair had turned white"},
    )
    assert [(r.key, r.interval.from_lb) for r in rows] == [("hair_color", 9)]
