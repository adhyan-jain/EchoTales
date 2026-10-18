"""Tests for Story Bible delta validator, ambiguous merge reviewer, and extractor."""

from __future__ import annotations

import pytest

from echotales.core.enums import Prominence, TargetKind
from echotales.core.models import DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.bible.delta import (
    build_bible_delta_prompt,
    extract_bible_delta,
    heuristic_extract_bible_delta,
    parse_bible_delta_response,
)
from echotales.pipeline.bible.schema import (
    BibleDelta,
    EntityDelta,
    LocationDelta,
    PersonaShiftDelta,
    PersonaShiftReason,
)
from echotales.pipeline.bible.validator import apply_bible_delta


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def test_apply_bible_delta_fresh_entities(store: Store) -> None:
    delta = BibleDelta(
        novel_id="hound",
        chapter=1.0,
        new_entities=[
            EntityDelta(
                self_id="hound:char:sherlock",
                canonical_label="Sherlock Holmes",
                kind="SELF",
                aliases=["Holmes", "Mr. Holmes"],
                initial_attributes={"occupation": "Consulting Detective"},
                suggested_voice_profile="baritone_british_sharp",
            )
        ],
        location_deltas=[
            LocationDelta(
                location_id="hound:loc:baker_st",
                canonical_name="221B Baker Street",
                description="Victorian sitting room, coal fireplace",
                ambience_sound="hearth_and_carriage_wheels",
            )
        ],
        summary="Holmes introduced at Baker St.",
    )

    result = apply_bible_delta(store, delta)
    assert len(result.new_self_ids) == 1
    assert result.new_self_ids[0] == "hound:char:sherlock"
    assert len(result.flagged_review_items) == 0

    snap = store.bible_at("hound", 1.0)
    assert "hound:char:sherlock" in snap.characters
    char = snap.characters["hound:char:sherlock"]
    assert char.canonical_label == "Sherlock Holmes"
    assert "Holmes" in char.aliases
    assert char.attributes["occupation"] == "Consulting Detective"
    assert char.voice_id == "baritone_british_sharp"

    assert "hound:loc:baker_st" in snap.locations
    loc = snap.locations["hound:loc:baker_st"]
    assert loc.canonical_name == "221B Baker Street"
    assert loc.ambience_sound == "hearth_and_carriage_wheels"


def test_apply_bible_delta_ambiguous_merge_flags_review_item(store: Store) -> None:
    # Existing character
    store.add_self(
        Self(
            id="hound:char:sherlock",
            novel_id="hound",
            canonical_label="Sherlock Holmes",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
            prominence=Prominence.PRINCIPAL,
        )
    )

    # Incoming delta with similar name but different ID
    delta = BibleDelta(
        novel_id="hound",
        chapter=2.0,
        new_entities=[
            EntityDelta(
                self_id="hound:char:sherlock_h",
                canonical_label="Sherlock H. Holmes",
                kind="SELF",
            )
        ],
    )

    result = apply_bible_delta(store, delta)
    assert len(result.flagged_review_items) == 1
    rev = result.flagged_review_items[0]
    assert rev.kind == "ambiguous_entity_merge"
    assert rev.candidates[0]["self_id"] == "hound:char:sherlock"

    # Review item is persisted in store
    items = store.list_review_items("hound", resolved=False)
    assert len(items) == 1
    assert items[0].id == rev.id


def test_apply_bible_delta_conflicting_attribute_flags_review_item(store: Store) -> None:
    # Character with known hair color
    delta1 = BibleDelta(
        novel_id="lotm",
        chapter=1.0,
        new_entities=[
            EntityDelta(
                self_id="lotm:char:klein",
                canonical_label="Klein Moretti",
                initial_attributes={"hair_color": "black"},
            )
        ],
    )
    apply_bible_delta(store, delta1)

    # Conflicting attribute in chapter 2 without a PersonaShift
    delta2 = BibleDelta(
        novel_id="lotm",
        chapter=2.0,
        new_entities=[
            EntityDelta(
                self_id="lotm:char:klein",
                canonical_label="Klein Moretti",
                initial_attributes={"hair_color": "bright_golden_blonde"},
            )
        ],
    )
    result = apply_bible_delta(store, delta2)
    assert len(result.conflicts) == 1
    assert len(result.flagged_review_items) == 1
    assert result.flagged_review_items[0].kind == "conflicting_attribute"


def test_apply_bible_delta_persona_shift_success(store: Store) -> None:
    # Base character
    delta1 = BibleDelta(
        novel_id="lotm",
        chapter=1.0,
        new_entities=[
            EntityDelta(
                self_id="lotm:char:zhou",
                canonical_label="Zhou Mingrui",
            )
        ],
    )
    apply_bible_delta(store, delta1)

    # Transmigration persona shift
    delta2 = BibleDelta(
        novel_id="lotm",
        chapter=2.0,
        persona_shifts=[
            PersonaShiftDelta(
                self_id="lotm:char:zhou",
                persona_id="lotm:persona:klein_body",
                reason=PersonaShiftReason.TRANSMIGRATION,
                description="Young man in linen shirt with temple wound",
                outfit_id="bloodied_tweed_suit",
                appearance_overrides={"wound": "left_temple"},
            )
        ],
    )
    result = apply_bible_delta(store, delta2)
    assert "lotm:persona:klein_body" in result.applied_shifts

    snap = store.bible_at("lotm", 2.0)
    assert snap.characters["lotm:char:zhou"].active_persona_id == "lotm:persona:klein_body"
    assert snap.characters["lotm:char:zhou"].active_outfit == "bloodied_tweed_suit"


def test_extract_bible_delta_heuristic_and_llm() -> None:
    sample_text = (
        "Mr. Sherlock Holmes sat in his armchair at 221B Baker Street. "
        "Dr. John Watson handed him the walking stick."
    )
    delta = heuristic_extract_bible_delta("hound", 1.0, sample_text)
    labels = [e.canonical_label for e in delta.new_entities]
    assert "Sherlock Holmes" in labels
    assert "Dr. John Watson" in labels
    assert len(delta.location_deltas) == 1
    assert delta.location_deltas[0].canonical_name == "221B Baker Street"

    # LLM response parser test
    mock_json = """
    ```json
    {
      "novel_id": "hound",
      "chapter": 1.0,
      "new_entities": [
        {
          "self_id": "hound:char:mortimer",
          "canonical_label": "Dr. James Mortimer",
          "kind": "SELF",
          "aliases": ["Mortimer"],
          "initial_attributes": {"profession": "Doctor"}
        }
      ],
      "persona_shifts": [],
      "location_deltas": [],
      "summary": "Mortimer arrives."
    }
    ```
    """
    parsed = parse_bible_delta_response(mock_json, "hound", 1.0)
    assert len(parsed.new_entities) == 1
    assert parsed.new_entities[0].canonical_label == "Dr. James Mortimer"
