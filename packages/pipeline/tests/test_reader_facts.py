"""The reader pass's facts stage: evidence must be real text, values must look like their key (stub provider)."""

from __future__ import annotations

import json

from echotales.core.enums import BlockType, Prominence, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.reader import facts_pass as fp

TEXT = (
    "Daly wore a hooded black robe and blue eyeshadow. Audrey had just turned seventeen. "
    "“My designation shall be ‘Justice!’” Audrey said, and Tom was thinly built."
)


def _store() -> tuple[Store, Chapter]:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    chapter = Chapter(novel_id="n", number=1.0, title="T", source_href="a",
                      blocks=[Block(index=0, block_type=BlockType.PROSE, text=TEXT)])
    store.add_chapter(chapter)
    for sid, name in (("n:self:daly", "Daly"), ("n:self:audrey", "Audrey"), ("n:self:tom", "Tom")):
        store.add_self(Self(id=sid, novel_id="n", canonical_label=name, prominence=Prominence.RECURRING,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    return store, chapter


def _run(payload: dict) -> tuple[Store, fp.FactsReport]:  # type: ignore[type-arg]
    store, chapter = _store()
    stub = StubProvider()
    stub.register_response("reader", payload)
    return store, fp.read_chapter_facts(store, ModelClient(provider_override=stub), chapter)


def _attrs(store: Store, self_id: str) -> dict[str, str]:
    return {a.key: a.value for a in store.get_attributes(TargetKind.PERSONA, f"{self_id}:body1")}


def test_verified_grounded_claims_are_stored_with_their_quote() -> None:
    store, report = _run({
        "appearance": [
            {"character": "Daly", "attribute": "typical_attire", "value": "black robe", "quote": "a hooded black robe"},
            {"character": "Tom", "attribute": "height_build", "value": "thin", "quote": "Tom was thinly built"},
        ],
        "identities": [], "ages": [],
    })
    assert _attrs(store, "n:self:daly")["typical_attire"] == "black robe"
    assert _attrs(store, "n:self:tom")["height_build"] == "thin"
    assert report.appearance == 2
    stored = next(a for a in store.get_attributes(TargetKind.PERSONA, "n:self:daly:body1"))
    assert stored.evidence == "a hooded black robe"


def test_makeup_is_a_mark_not_an_eye_colour_and_nonsense_build_is_rejected() -> None:
    store, report = _run({
        "appearance": [
            {"character": "Daly", "attribute": "eye_color", "value": "blue eyeshadow", "quote": "blue eyeshadow"},
            {"character": "Tom", "attribute": "height_build", "value": "quivered", "quote": "Tom was thinly built"},
        ],
        "identities": [], "ages": [],
    })
    assert _attrs(store, "n:self:daly") == {"distinguishing_features": "blue eyeshadow"}
    assert "height_build" not in _attrs(store, "n:self:tom")
    assert report.rejected_value + report.rejected_ungrounded >= 1


def test_a_quote_not_in_the_passage_is_rejected_and_a_paraphrase_is_repaired() -> None:
    store, report = _run({
        "appearance": [
            {"character": "Daly", "attribute": "hair_color", "value": "black", "quote": "her midnight black hair spilled"},
            {"character": "Daly", "attribute": "typical_attire", "value": "black robe", "quote": "dressed in a black robe"},
        ],
        "identities": [], "ages": [],
    })
    assert "hair_color" not in _attrs(store, "n:self:daly")  # no sentence of the passage states it
    assert _attrs(store, "n:self:daly")["typical_attire"] == "black robe"  # repaired to the real sentence
    assert report.repaired == 1
    repaired = next(a for a in store.get_attributes(TargetKind.PERSONA, "n:self:daly:body1") if a.key == "typical_attire")
    assert repaired.evidence.startswith("Daly wore a hooded black robe")


def test_a_new_name_becomes_an_alias_and_an_unwritten_age_is_refused() -> None:
    store, report = _run({
        "appearance": [],
        "identities": [{"character": "Audrey", "name": "Justice", "quote": "My designation shall be ‘Justice!’"}],
        "ages": [
            {"character": "Audrey", "age": 17, "quote": "Audrey had just turned seventeen"},
            {"character": "Tom", "age": 25, "quote": "Tom was thinly built"},
        ],
    })
    aliases = {a.alias for a in store.get_aliases_for(TargetKind.SELF, "n:self:audrey")}
    assert "Justice" in aliases
    assert _attrs(store, "n:self:audrey")["age"] == "17"
    assert "age" not in _attrs(store, "n:self:tom")  # 25 appears nowhere in the evidence
    assert (report.identities, report.ages) == (1, 1)


def test_validator_helpers() -> None:
    assert fp.check_attribute("hair_color", "black") == ("hair_color", "black")
    assert fp.check_attribute("eye_color", "blue eyeshadow") == ("distinguishing_features", "blue eyeshadow")
    assert fp.check_attribute("height_build", "quivered") is None
    assert fp.age_in_quote(17, "had just turned seventeen") and not fp.age_in_quote(25, "had just turned seventeen")
    assert fp.grounded("thin", "thinly built") and not fp.grounded("emerald", "thinly built")
    assert "brown eyes" in fp.cue_passage("He sat. She had brown eyes. They left.")


def test_the_names_prompt_has_no_placeholder_a_model_could_copy_as_a_quote() -> None:
    """gemma2:9b copied the literal '...' from the answer template as the evidence quote for 'Justice' and
    'The Hanged Man', so both claims failed the quote check (LotM ch7 persona links 5/5 -> 3/5)."""
    prompt = fp._names_prompt([], "x")
    assert '"quote": "..."' not in prompt and "..." not in prompt.split("Example.")[1]


def test_the_naming_passage_keeps_the_lines_that_answer_the_cue() -> None:
    text = "Intro line. My designation shall be 'Justice!' What about you, Mister? The Hanged Man. Filler one. Filler two. Filler three. Unrelated end."
    focus = fp.name_passage(text)
    assert "The Hanged Man." in focus and "Intro line." in focus
    assert fp.name_passage("Nothing to see here. Just walking.") == ""


def test_persona_name_matching_ignores_articles_and_titles() -> None:
    from echotales.pipeline.eval.reader_gold import _bare

    assert _bare("Mr. Fool") == _bare("The Fool") == "fool"
    assert _bare("Miss Justice") == _bare("Justice")


def test_a_wrong_evidence_pointer_for_a_new_name_is_repaired_to_the_sentence_that_names_it() -> None:
    store, chapter = _store()
    stub = StubProvider()
    stub.register_response("reader", {
        "appearance": [], "ages": [],
        "identities": [{"character": "Audrey", "name": "Justice", "quote": "It's nothing at all, truly."}],
    })
    report = fp.read_chapter_facts(store, ModelClient(provider_override=stub), chapter)
    assert report.identities == 1 and report.repaired == 1
    alias = next(a for a in store.get_aliases_for(TargetKind.SELF, "n:self:audrey") if a.alias == "Justice")
    assert "designation shall be" in alias.evidence  # the real sentence, not the model's pointer


def test_a_look_about_her_is_not_stored_for_a_male_character() -> None:
    """LotM ch3: Melissa's 'her skin remained lustrous' became Klein's skin tone."""
    assert fp.gender_conflict("male", "her skin remained lustrous as it exuded youth")
    assert fp.gender_conflict("female", "his eyes were gray")
    assert not fp.gender_conflict("male", "his eyes were gray")
    assert not fp.gender_conflict("male", "the gray-eyed inspector")  # no pronoun, no signal
    assert not fp.gender_conflict("", "her skin")  # unknown gender: nothing to contradict


def test_a_rough_age_stage_needs_a_cue_in_its_evidence_and_an_exact_age_implies_one() -> None:
    text = "Old Neil laughed. Audrey had just turned seventeen. A sturdy man waited."
    store, chapter = _store()
    store.add_self(Self(id="n:self:neil", novel_id="n", canonical_label="Old Neil", prominence=Prominence.RECURRING,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.conn.execute("UPDATE chapter SET blocks_json=? WHERE novel_id='n'",
                       (json.dumps([{"index": 0, "block_type": "PROSE", "text": text, "italic_ranges": [], "system_fields": {}}]),))
    store.conn.commit()
    chapter = store.get_chapter("n", 1.0)
    stub = StubProvider()
    stub.register_response("reader", {
        "appearance": [], "identities": [],
        "ages": [{"character": "Audrey", "age": 17, "quote": "Audrey had just turned seventeen"}],
        "age_stages": [
            {"character": "Old Neil", "stage": "elderly", "approx_years": 68, "quote": "Old Neil laughed"},
            {"character": "Tom", "stage": "elderly", "approx_years": 70, "quote": "A sturdy man waited"},  # no age cue
        ],
    })
    report = fp.read_chapter_facts(store, ModelClient(provider_override=stub), chapter)
    assert _attrs(store, "n:self:neil")["age_stage"] == "elderly" and _attrs(store, "n:self:neil")["age_estimate"] == "about 68"
    assert "age_stage" not in _attrs(store, "n:self:tom")  # 'A sturdy man' says nothing about age
    assert _attrs(store, "n:self:audrey")["age_stage"] == "teen"  # 17 implies a stage
    assert report.age_stages == 1


def test_age_stage_becomes_an_image_tag_and_an_exact_age_is_the_fallback() -> None:
    from echotales.core.models import CharacterBibleEntry
    from echotales.pipeline.assets.turnaround import look_clauses

    def char(**attrs: str) -> CharacterBibleEntry:
        return CharacterBibleEntry(self_id="x", canonical_label="X", active_persona_id="x:body1", attributes=attrs)

    assert "elderly, old man" in look_clauses(char(gender="male", age_stage="elderly"))
    assert "middle-aged woman" in look_clauses(char(gender="female", age_stage="middle_aged"))
    assert "teenager" in look_clauses(char(gender="female", age="17"))
    assert not any("adult" in c or "teen" in c for c in look_clauses(char(gender="male", age_band="adult")))  # the default band says nothing


def test_check_attribute_rejects_hats_as_hair_and_moustaches_on_women() -> None:
    from echotales.pipeline.reader.facts_pass import check_attribute

    assert check_attribute("hair_style", "silk hat") is None
    assert check_attribute("hair_style", "mustache", "female") is None
    assert check_attribute("hair_style", "mustache", "male") == ("distinguishing_features", "mustache")
    assert check_attribute("hair_style", "long braided hair") == ("hair_style", "long braided hair")


def test_check_attribute_attire_must_be_a_garment_phrase() -> None:
    from echotales.pipeline.reader.facts_pass import check_attribute

    assert check_attribute("typical_attire", "such clothes") is None
    assert check_attribute("typical_attire", "smilingly shook his hand") is None
    assert check_attribute("typical_attire", "black-hooded robe") is not None


def test_about_character_needs_the_sentence_to_name_them() -> None:
    from echotales.pipeline.reader.facts_pass import about_character
    from echotales.pipeline.reader.speakers_pass import CastEntry, NameIndex

    audrey, klein = CastEntry("a", "Audrey Hall"), CastEntry("k", "Klein Moretti")
    index = NameIndex([audrey, klein])
    passage = "Audrey Hall smiled. Klein Moretti wore a dark brown waistcoat. He frowned."
    assert about_character(klein, "wore a dark brown waistcoat", passage, index)
    assert not about_character(audrey, "wore a dark brown waistcoat", passage, index)
    # a pronoun-only sentence belongs to the one person named just before it
    assert about_character(klein, "He frowned", passage, index)


def test_about_character_handles_description_before_name_and_other_people_in_sentence() -> None:
    from echotales.pipeline.reader.facts_pass import about_character
    from echotales.pipeline.reader.speakers_pass import CastEntry, NameIndex

    daly, klein = CastEntry("d", "Daly"), CastEntry("k", "Klein Moretti")
    index = NameIndex([daly, klein])
    gender = {"d": "female", "k": "male"}.get
    # a description that comes before the name (LotM ch14): the first named person after it owns it
    ahead = "A lady in a hooded black robe wore blue eyeshadow. The air was cold. Daly, the medium, nodded."
    assert about_character(daly, "wore blue eyeshadow", ahead, index, lambda s: gender(s, ""))
    # "her" with only a man named: the woman named just before is the owner
    other = "Daly took out a bottle. Her emerald eyes smiled at Klein Moretti."
    assert about_character(daly, "Her emerald eyes smiled", other, index, lambda s: gender(s, ""))
    assert not about_character(klein, "Her emerald eyes smiled", other, index, lambda s: gender(s, ""))
    # a possessive still names its owner
    assert about_character(daly, "blue eyeshadow", "Daly's blue eyeshadow shone.", index, lambda s: gender(s, ""))
