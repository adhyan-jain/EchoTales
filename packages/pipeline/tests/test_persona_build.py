"""Persona construction and trait inference (Section 10 item 4, `4b` step 1).

Until `build.py` existed, `architecture.md Section 4`'s self/persona split had no
code on the persona side: nothing constructed a `Persona`, so nothing
consumed `SelfPersonaBinding` and voice/image work had nothing to bind to.
"""

from __future__ import annotations

from echotales.core.enums import Prominence, TargetKind
from echotales.pipeline.persona.traits import (
    gender_from_pronouns,
    infer_traits_deterministic,
    self_reference_gender,
)


class TestGenderFromPronouns:
    """Denser than honorific evidence in this corpus: most names here carry no
    address form, but the surrounding English narration is unavoidably
    gendered. Honorifics alone left 91% of RI vol 1's cast `unknown`."""

    def test_clear_male_majority(self) -> None:
        passages = [
            "He drew his sword.",
            "He stepped back, and his robe caught.",
            "He steadied himself, his gaze on his blade.",
        ]
        assert gender_from_pronouns(passages)[0] == "male"

    def test_clear_female_majority(self) -> None:
        passages = [
            "She raised her hand.",
            "Her voice was calm as she spoke.",
            "She steadied herself, her sleeve at her side.",
        ]
        assert gender_from_pronouns(passages)[0] == "female"

    def test_too_few_pronouns_is_undetermined(self) -> None:
        """Two pronouns prove nothing -- an unknown gender falls back to a
        neutral voice, which is a better outcome than a coin flip."""
        assert gender_from_pronouns(["He nodded."])[0] is None

    def test_mixed_pronouns_are_undetermined(self) -> None:
        """These passages are narration *neighbourhoods*, so other characters
        share the paragraph. A stray pronoun must not flip a character."""
        passages = ["He spoke to her.", "She answered him.", "He and she left."]
        assert gender_from_pronouns(passages)[0] is None

    def test_pronoun_inside_a_word_does_not_count(self) -> None:
        passages = ["Sheathed blades and hershey bars lined the shelf."] * 6
        assert gender_from_pronouns(passages)[0] is None


class TestSelfReferenceGender:
    """A line addressed entirely in second person states nothing
    grammatically about its own speaker -- `gender_from_pronouns`'s
    narration-window signal cannot see this, only the line's own wording
    can. Bounded to "this <term>" specifically so a bare honorific
    addressing someone *else* in the same line is not misread as the
    speaker's own gender."""

    def test_self_reference_male(self) -> None:
        assert self_reference_gender("This king will not kneel before you!") == "male"

    def test_self_reference_female(self) -> None:
        assert self_reference_gender("This humble maiden begs your forgiveness.") == "female"

    def test_second_person_only_line_is_undetermined(self) -> None:
        assert self_reference_gender("You demon, you took what was mine!") is None

    def test_honorific_addressing_someone_else_is_not_self_reference(self) -> None:
        assert self_reference_gender("Elder, please forgive this disciple.") is None

    def test_modifier_between_this_and_the_term_still_matches(self) -> None:
        assert self_reference_gender("This old master has seen enough.") == "male"


class TestDeterministicTraits:
    def test_age_band_from_honorific(self) -> None:
        p = infer_traits_deterministic("e1", "Granny Ma", surfaces=["Granny Ma"])
        assert p.age_band == "elder"
        assert p.register == "formal"

    def test_multiword_honorific_beats_its_component(self) -> None:
        """"young master" must not be read as the weaker bare "young"."""
        p = infer_traits_deterministic("e1", "Young Master Gu", surfaces=["Young Master Gu"])
        assert p.age_band == "youth"

    def test_pronouns_outrank_honorific_for_gender(self) -> None:
        """Measured on RI: "Lord Yao Ji" is a female Gu Immortal, but
        translated xianxia uses "Lord" for both genders. The narration says
        "she", and that is direct evidence about this character."""
        p = infer_traits_deterministic(
            "e1",
            "Lord Yao Ji",
            surfaces=["Lord Yao Ji"],
            pronoun_passages=[
                "She smiled.",
                "Her sleeve brushed as she turned.",
                "She held herself still, her eyes on him.",
            ],
        )
        assert p.gender == "female"

    def test_honorific_still_used_when_pronouns_are_silent(self) -> None:
        p = infer_traits_deterministic("e1", "Granny Ma", surfaces=["Granny Ma"])
        assert p.gender == "female"

    def test_unknown_gender_when_nothing_says(self) -> None:
        p = infer_traits_deterministic("e1", "Fang Yuan", surfaces=["Fang Yuan"])
        assert p.gender == "unknown"

    def test_big_five_defaults_are_neutral_not_zero(self) -> None:
        """A profile with no signal must sit at the centre; defaulting to 0.0
        would read as maximally introverted and be cast that way."""
        p = infer_traits_deterministic("e1", "X")
        assert p.openness == 0.5 and p.agreeableness == 0.5

    def test_archetype_is_gender_age_register_only(self) -> None:
        """Big Five picks a voice *within* a bucket and shapes delivery; it
        deliberately does not partition the bank (`architecture.md Section 8b`)."""
        p = infer_traits_deterministic("e1", "Granny Ma", surfaces=["Granny Ma"])
        assert p.archetype == "female:elder:formal"


class TestBuildPersonas:
    def test_builds_binds_and_profiles(self, tmp_path) -> None:
        store = _seeded_store(tmp_path)
        from echotales.pipeline.persona import build_personas

        report = build_personas("t", store)
        assert report.personas == 1
        assert report.bindings == 1

        entity = store.all_selves("t")[0]
        persona = store.get_persona(f"{entity.id}:body1")
        assert persona is not None
        assert store.get_self_persona_bindings(self_id=entity.id)

    def test_non_person_entities_are_skipped(self, tmp_path) -> None:
        """Section 10 item 5's typing doing the job it was added for: a location has
        no body to draw and no voice to cast."""
        store = _seeded_store(tmp_path, kind=TargetKind.LOCATION)
        from echotales.pipeline.persona import build_personas

        report = build_personas("t", store)
        assert report.personas == 0
        assert report.skipped_non_person == 1

    def test_traits_round_trip_through_attributes(self, tmp_path) -> None:
        store = _seeded_store(tmp_path)
        from echotales.pipeline.persona import build_personas, load_trait_profiles

        build_personas("t", store)
        profiles = load_trait_profiles("t", store)
        assert len(profiles) == 1
        only = next(iter(profiles.values()))
        assert only.archetype.count(":") == 2
        assert only.provenance == "deterministic"


def _seeded_store(tmp_path, kind: TargetKind = TargetKind.SELF):
    from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self
    from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
    from echotales.core.store import Store

    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="Fang Yuan stood.")],
        )
    )
    store.add_self(
        Self(
            id="t:self1",
            novel_id="t",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
            kind=kind,
        )
    )
    store.add_mentions(
        [
            Mention(
                id="m1",
                novel_id="t",
                segment_id="s",
                chapter=1.0,
                offset=0,
                block_index=0,
                text="Fang Yuan",
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF,
                target_id="t:self1",
            )
        ]
    )
    store.conn.commit()
    return store
