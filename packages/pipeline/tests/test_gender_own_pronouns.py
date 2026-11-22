"""Gender for the women of Pride and Prejudice ch1-3, and casting that respects what the text leans to (2026-11-22).

7 of 16 characters (Elizabeth, Jane, Kitty, Lydia, Maria Lucas, Mary, Lizzy) had no gender after a real run and were
cast gender-blind, so a recorded-male voice read Lydia. Causes pinned here: (1) exposition narration was not read at
all ("Mary had heard herself mentioned ... the most accomplished girl"), (2) gemma2:9b answered female for Elizabeth but
quoted the wrong words ("towards him") and the quote check threw the right answer away, (3) one title mention ("the
eldest Miss Bennet") was not enough even with "her mother" next to the name, (4) casting never looked at the text
once the graph said `unknown`. Synthetic text only.
"""

from __future__ import annotations

from types import SimpleNamespace

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.persona import build_personas, load_trait_profiles
from echotales.pipeline.persona.gender import gender_lean, infer_missing_genders, own_pronoun_vote
from echotales.pipeline.voice.bank import VoiceBank, parse_speaker_info
from echotales.pipeline.voice.casting import cast_voices


def _book(tmp_path, paragraphs: list[str], surface: str, *, span_type=SpanType.NARRATION_EXPOSITION, label: str | None = None):
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t", number=1.0, title="T", source_href="a.html",
            blocks=[Block(index=i, block_type=BlockType.PROSE, text=p) for i, p in enumerate(paragraphs)],
        )
    )
    store.add_spans(
        [
            Span(id=f"t:1:{i}:0", novel_id="t", chapter=1.0, block_index=i, start=0, end=len(p), span_type=span_type, text=p)
            for i, p in enumerate(paragraphs)
        ]
    )
    store.add_self(
        Self(id="t:self1", novel_id="t", canonical_label=label or surface, kind=TargetKind.SELF,
             first_attested_pos=DiscoursePosition(chapter=1, offset=0))
    )
    store.add_mentions(
        [
            Mention(
                id=f"m{i}", novel_id="t", segment_id="s", chapter=1.0, offset=p.index(surface), block_index=i,
                text=surface, alias_type=AliasType.RIGID_NAME, span_type=span_type,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:self1",
            )
            for i, p in enumerate(paragraphs)
        ]
    )
    store.conn.commit()
    build_personas("t", store)
    return store


def _gender(store) -> str:
    return load_trait_profiles("t", store)["t:self1"].gender


class _Model:
    def __init__(self, gender: str, quote: str) -> None:
        self.gender, self.quote, self.calls = gender, quote, 0

    def complete(self, task, prompt, schema, *, system="", novel_id=""):
        self.calls += 1
        return SimpleNamespace(value=schema.model_validate({"gender": self.gender, "quote": self.quote, "confident": True}))


def test_own_pronoun_votes_only_for_the_character_the_clause_is_about() -> None:
    assert own_pronoun_vote(" had heard herself mentioned as the most accomplished girl.") == "female"
    assert own_pronoun_vote(", till, catching her eye, he withdrew his own") == "female"
    # an object pronoun after the name names someone else
    assert own_pronoun_vote(" remained with no cordial feelings towards him. She told the story.") is None
    # the sentence turns to another name before any pronoun
    assert own_pronoun_vote(" felt the pleasure. Mary had heard herself mentioned") is None


def test_exposition_narration_is_read_and_the_model_decides(tmp_path) -> None:
    store = _book(tmp_path, ["Mary had heard herself mentioned as the most accomplished girl in the room."] * 4, "Mary")
    client = _Model("female", "heard herself mentioned as the most accomplished girl")
    infer_missing_genders("t", store, client)
    assert _gender(store) == "female"


def test_a_right_answer_with_the_wrong_quote_stands_when_the_own_pronouns_agree(tmp_path) -> None:
    paragraphs = ["Eve turned, catching her breath, and said nothing more."] * 2 + ["Eve stood by the door."] * 2
    store = _book(tmp_path, paragraphs, "Eve", span_type=SpanType.NARRATION_ACTION)
    report = infer_missing_genders("t", store, _Model("female", "stood by the door and watched him"))
    assert _gender(store) == "female"
    assert report.by_pronoun_and_model == 1


def test_a_wrong_quote_with_no_pronoun_support_is_still_rejected(tmp_path) -> None:
    store = _book(tmp_path, ["Eve stood by the door."] * 4, "Eve", span_type=SpanType.NARRATION_ACTION)
    infer_missing_genders("t", store, _Model("female", "stood by the door and watched him"))
    assert _gender(store) == "unknown"


def test_a_model_answer_against_the_own_pronouns_is_not_taken(tmp_path) -> None:
    paragraphs = ["Eve turned, catching her breath.", "Eve stood by the door."] * 2
    store = _book(tmp_path, paragraphs, "Eve", span_type=SpanType.NARRATION_ACTION)
    infer_missing_genders("t", store, _Model("male", "turned and said nothing more at all"))
    assert _gender(store) == "unknown"


def test_the_pronoun_rule_decides_alone_only_with_enough_agreeing_votes(tmp_path) -> None:
    text = ["Anna sat down, folding her hands in her lap."] * 3
    store = _book(tmp_path, text, "Anna", span_type=SpanType.NARRATION_ACTION)
    infer_missing_genders("t", store, None)
    assert _gender(store) == "female"


def test_two_votes_alone_do_not_decide_without_a_model(tmp_path) -> None:
    store = _book(tmp_path, ["Anna sat down, folding her hands."] * 2 + ["Anna waited."] * 2, "Anna", span_type=SpanType.NARRATION_ACTION)
    infer_missing_genders("t", store, None)
    assert _gender(store) == "unknown"


def test_lean_points_one_way_only_when_no_vote_disagrees(tmp_path) -> None:
    store = _book(tmp_path, ["Kay laughed, shaking her head."], "Kay", span_type=SpanType.NARRATION_ACTION)
    assert gender_lean(store, "t", {"t:self1"}) == {"t:self1": "female"}


def test_one_disagreeing_pronoun_cancels_the_lean(tmp_path) -> None:
    store = _book(
        tmp_path, ["Kay laughed, shaking her head.", "Kay sighed, rubbing his eyes."], "Kay", span_type=SpanType.NARRATION_ACTION
    )
    assert gender_lean(store, "t", {"t:self1"}) == {}


BANK = "ID  AGE  GENDER  ACCENTS  REGION\n" + "".join(
    f"p{300 + i}  30  {g}    English    Surrey\n" for i, g in enumerate("FFMMMM")
)


def test_a_character_the_text_leans_female_is_never_given_a_male_voice(tmp_path) -> None:
    store = _book(tmp_path, ["Kay laughed, shaking her head."], "Kay", span_type=SpanType.NARRATION_ACTION)
    profiles = load_trait_profiles("t", store)
    assert profiles["t:self1"].gender == "unknown"
    bank = VoiceBank(voices=parse_speaker_info(BANK))
    lean = gender_lean(store, "t", {"t:self1"})
    assignments, report = cast_voices("t", profiles, bank, store=store, lean=lean)
    voice = next(v for v in bank.voices if v.speaker_id == assignments["t:self1"].speaker_id)
    assert voice.gender == "female"
    assert report.leaning == {"Kay": "female"}
    assert report.unknown_gender == []


def test_a_character_with_no_lean_is_listed_as_cast_from_the_age_pool(tmp_path) -> None:
    store = _book(tmp_path, ["Kay waited."], "Kay", span_type=SpanType.NARRATION_ACTION)
    profiles = load_trait_profiles("t", store)
    bank = VoiceBank(voices=parse_speaker_info(BANK))
    _, report = cast_voices("t", profiles, bank, store=store, lean={})
    assert report.unknown_gender == ["Kay"]
    assert "age-appropriate pool" in report.summary()
