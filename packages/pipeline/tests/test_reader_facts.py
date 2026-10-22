"""The reader pass's facts stage: evidence must be real text, values must look like their key (stub provider)."""

from __future__ import annotations

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
