"""A disguise is not the character's look (owner, 2026-11-15).

"Black eyes and black hair" is the innate look; "a burned scar" is a change from that chapter on; but "brown hair and
blue eyes" written while the character wears a disguise describes the costume, and filing it as an innate trait
stamped the costume onto every picture of them back to chapter 1. A disguise fact is bounded to the chapter that
states it by a closed interval (never a retraction), so `state_of` returns it only there.
"""

from __future__ import annotations

import pytest
from echotales.core.enums import BlockType, Prominence, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.persona.reference_gen import appearance_of
from echotales.pipeline.persona.split import standing_values
from echotales.pipeline.reader import facts_pass as fp
from echotales.pipeline.reader.facts_pass import classify_scope, fact_scope


@pytest.mark.parametrize(
    ("attribute", "quote", "scope"),
    [
        # a disguise cue wins over baseline
        ("hair_color", "Disguised as a merchant, he had brown hair and blue eyes.", "disguise"),
        ("eye_color", "Under the guise of a scholar, her eyes were grey.", "disguise"),
        ("hair_color", "He wore a wig of brown hair.", "disguise"),
        # a mask hides the face, not the hair or the eyes: those stay the real look
        ("eye_color", "Behind the mask his eyes were blue.", "baseline"),
        ("hair_color", "The man wearing a silver mask had long black hair.", "baseline"),
        ("distinguishing_features", "Wearing a human-skin mask, he had a plain, sallow face.", "disguise"),
        # "glamorous" is praise, not a glamour spell
        ("hair_color", "Her glamorous golden hair fell to her waist.", "baseline"),
        ("hair_color", "Using a face-changing technique, his hair turned brown.", "disguise"),
        ("hair_color", "He transformed into a brown-haired youth.", "disguise"),
        ("typical_attire", "Posing as a priest, he wore a white cassock.", "disguise"),
        # a change cue inside a disguise sentence is the disguise, not a permanent change
        ("hair_color", "He dyed his hair black as part of the disguise.", "disguise"),
        # a permanent change stated plainly stays a change
        ("distinguishing_features", "Half his face was burned.", "change"),
        ("hair_color", "His hair had turned white after the fire.", "change"),
        # an innate statement without a cue stays baseline
        ("eye_color", "He had black eyes and black hair.", "baseline"),
        # a negated cue is not a disguise
        ("hair_color", "Without any disguise, his black hair shone.", "baseline"),
        ("hair_color", "He was not in disguise; his hair was black.", "baseline"),
        ("hair_color", "Undisguised, he had black hair.", "baseline"),
        # the disguise coming off describes the real look
        ("hair_color", "He removed the wig, revealing black hair.", "baseline"),
        ("eye_color", "Back in his true appearance, his eyes were black.", "baseline"),
        # makeup alone is a mark, not a disguise (existing eyeshadow behaviour)
        ("distinguishing_features", "Daly's blue eyeshadow shone.", "state"),
    ],
)
def test_disguise_precedence(attribute: str, quote: str, scope: str) -> None:
    assert fact_scope(attribute, quote) == scope


def test_the_context_is_the_stating_sentence_and_the_one_before_it() -> None:
    quote = "His hair was brown and his eyes blue."
    cue = "He had disguised himself as a merchant."
    assert classify_scope("hair_color", quote, cue) == ("disguise", True)  # previous sentence: counted, in doubt
    assert classify_scope("hair_color", quote, "He sat down. The word disguise came up later.")[0] == "disguise"
    # a disguise two sentences back, or somewhere else in the chapter, is not looked at: `before` is only one sentence
    assert classify_scope("hair_color", quote, "He sat down.") == ("baseline", False)
    assert classify_scope("hair_color", quote, "") == ("baseline", False)
    assert classify_scope("hair_color", quote, "Without any disguise he sat down.") == ("baseline", False)


def test_a_disguise_in_a_sentence_naming_others_is_written_bounded_and_counted_as_doubt() -> None:
    # Subject attribution inside a sentence does not exist at this point: another character's disguise in the same
    # sentence bounds this character's fact to a chapter (never baseline) and is counted.
    assert classify_scope("hair_color", "Tom had black hair while Ann was disguised.", shared=True) == ("disguise", True)
    assert classify_scope("hair_color", "Tom had black hair.", shared=True) == ("baseline", False)


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    store.add_self(Self(id="n:self:tom", novel_id="n", canonical_label="Tom", prominence=Prominence.RECURRING,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    return store


def _read(store: Store, number: int, text: str, attribute: str, value: str, quote: str) -> fp.FactsReport:
    chapter = Chapter(novel_id="n", number=float(number), title="T", source_href="a",
                      blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)])
    store.add_chapter(chapter)
    stub = StubProvider()
    stub.register_response("reader", {"appearance": [
        {"character": "Tom", "attribute": attribute, "value": value, "quote": quote}], "identities": [], "ages": []})
    return fp.read_chapter_facts(store, ModelClient(provider_override=stub), chapter)


def _look(store: Store, position: int, read_through: int) -> dict[str, str]:
    """What `state_of` returns for a picture at `position` once chapters up to `read_through` have been read. The
    reader stamps its facts with observer "reader" (facts_pass.OBSERVER_READER), not core's "READER", so the default
    observer of `StateResolver` sees none of them: see the report."""
    res = StateResolver(store, "n")
    knowledge = DiscoursePosition(chapter=read_through, offset=10**6)
    return res.state_of("n:self:tom:body1", target_kind=TargetKind.PERSONA, position=position + 0.5,
                        knowledge_pos=knowledge, observer_id="reader").attributes


def _panel(store: Store, chapter: int) -> dict[str, str]:
    """The look a panel or reference picture of `chapter` reads."""
    return appearance_of(store, "n:self:tom:body1", position=chapter, standing_only=False)


def test_innate_traits_stated_late_reach_chapter_one_but_not_the_reader_before_they_are_read() -> None:
    store = _store()
    report = _read(store, 12, "Tom had black eyes and black hair.", "eye_color", "black", "Tom had black eyes")
    assert (report.scope_baseline, report.scope_disguise) == (1, 0)
    assert _panel(store, 1)["eye_color"] == "black"  # the chapter-1 picture has it
    assert _look(store, 1, read_through=12)["eye_color"] == "black"
    assert "eye_color" not in _look(store, 1, read_through=11)  # the reader view does not, before chapter 12
    known = DiscoursePosition(chapter=11, offset=10**6)
    assert "eye_color" not in standing_values(store, "n:self:tom:body1", known_by=known)


def test_a_burned_scar_exists_only_from_the_chapter_that_states_it_and_survives_an_innate_restatement() -> None:
    store = _store()
    _read(store, 30, "Tom got a burned scar across his cheek.", "distinguishing_features", "burned scar",
          "Tom got a burned scar across his cheek")
    assert "distinguishing_features" not in _panel(store, 29)
    assert _panel(store, 30)["distinguishing_features"] == "burned scar"
    assert "distinguishing_features" not in _look(store, 29, read_through=40)
    assert _look(store, 30, read_through=40)["distinguishing_features"] == "burned scar"
    _read(store, 35, "Tom had black hair.", "hair_color", "black", "Tom had black hair")
    assert _panel(store, 36)["distinguishing_features"] == "burned scar"
    assert _look(store, 36, read_through=40)["distinguishing_features"] == "burned scar"


def test_a_disguise_shows_only_while_it_holds_and_never_touches_the_innate_look() -> None:
    store = _store()
    _read(store, 3, "Tom had black hair and black eyes.", "hair_color", "black", "Tom had black hair")
    report = _read(store, 10, "Tom, disguised as a merchant, had brown hair.", "hair_color", "brown",
                   "Tom, disguised as a merchant, had brown hair")
    assert (report.scope_disguise, report.scope_baseline) == (1, 0)
    for chapter in (1, 9, 10, 11, 50):  # panels and reference sheets never see the costume
        assert _panel(store, chapter)["hair_color"] == "black"
    assert _look(store, 9, read_through=20)["hair_color"] == "black"
    assert "disguise:hair_color" not in _look(store, 9, read_through=20)
    assert _look(store, 10, read_through=20)["disguise:hair_color"] == "brown"
    assert _look(store, 10, read_through=20)["hair_color"] == "black"
    assert "disguise:hair_color" not in _look(store, 11, read_through=20)  # it ends with its chapter
    (disguise,) = [a for a in store.get_attributes(TargetKind.PERSONA, "n:self:tom:body1") if a.value == "brown"]
    assert disguise.is_standing and not disguise.interval.is_open  # closed by interval, not retracted


def test_a_disguise_value_does_not_make_the_same_real_value_known_later() -> None:
    store = _store()
    _read(store, 10, "Tom, disguised as a merchant, had brown hair.", "hair_color", "brown",
          "Tom, disguised as a merchant, had brown hair")
    report = _read(store, 20, "Tom had brown hair.", "hair_color", "brown", "Tom had brown hair")
    assert report.duplicates == 0 and report.scope_baseline == 1
    assert _panel(store, 1)["hair_color"] == "brown"


def test_a_disguise_cue_only_in_the_previous_sentence_is_bounded_and_counted_as_doubt() -> None:
    store = _store()
    report = _read(store, 10, "Tom had disguised himself as a merchant. Tom's hair was brown.", "hair_color", "brown",
                   "Tom's hair was brown")
    assert (report.scope_disguise, report.scope_doubt, report.scope_baseline) == (1, 1, 0)
    assert "hair_color" not in _panel(store, 10)
