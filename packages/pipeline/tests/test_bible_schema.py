"""Tests for Story Bible structured deltas and point-in-time snapshots."""

from __future__ import annotations

import json

from echotales.pipeline.bible.schema import (
    BibleDelta,
    CharacterBibleEntry,
    EntityDelta,
    LocationBibleEntry,
    LocationDelta,
    PersonaShiftDelta,
    PersonaShiftReason,
    StoryBibleSnapshot,
)


def test_bible_delta_serialization_roundtrip() -> None:
    delta = BibleDelta(
        novel_id="lotm",
        chapter=1.0,
        new_entities=[
            EntityDelta(
                self_id="lotm:self:zhou",
                canonical_label="Zhou Mingrui",
                kind="SELF",
                aliases=["Klein Moretti", "Klein"],
                initial_attributes={"hair_color": "black", "eye_color": "brown"},
                suggested_voice_profile="scholar_young_male",
            )
        ],
        persona_shifts=[
            PersonaShiftDelta(
                self_id="lotm:self:zhou",
                persona_id="lotm:self:zhou:body1",
                reason=PersonaShiftReason.TRANSMIGRATION,
                description="Wakes in Klein Moretti's body with gunshot wound at temple",
                outfit_id="bloodied_linen_shirt",
                appearance_overrides={"wound": "left_temple_bullet_entry"},
            )
        ],
        location_deltas=[
            LocationDelta(
                location_id="lotm:loc:klein_bedroom",
                canonical_name="Klein's Apartment Bedroom",
                description="Small Victorian room, gas lamp, wooden desk, revolver, bloodied notebook",
                sub_areas=["desk", "bed", "window"],
                ambience_sound="wind_and_gas_hiss",
            )
        ],
        summary="Zhou Mingrui awakens as Klein Moretti in Backlund.",
    )

    data = delta.to_dict()
    serialized = json.dumps(data)
    loaded = json.loads(serialized)
    restored = BibleDelta.from_dict(loaded)

    assert restored.novel_id == "lotm"
    assert restored.chapter == 1.0
    assert len(restored.new_entities) == 1
    assert restored.new_entities[0].canonical_label == "Zhou Mingrui"
    assert restored.persona_shifts[0].reason == PersonaShiftReason.TRANSMIGRATION
    assert restored.location_deltas[0].canonical_name == "Klein's Apartment Bedroom"


def test_story_bible_snapshot_alias_resolution() -> None:
    snapshot = StoryBibleSnapshot(
        novel_id="lotm",
        chapter=1.0,
        characters={
            "lotm:self:zhou": CharacterBibleEntry(
                self_id="lotm:self:zhou",
                canonical_label="Zhou Mingrui",
                active_persona_id="lotm:self:zhou:body1",
                active_outfit="linen_shirt",
                aliases=["Klein Moretti", "Klein", "Zhou"],
                voice_id="voice_klein",
                attributes={"hair": "black"},
            )
        },
        locations={
            "lotm:loc:bedroom": LocationBibleEntry(
                location_id="lotm:loc:bedroom",
                canonical_name="Klein's Bedroom",
                description="Small room with wooden desk",
            )
        },
    )

    # Resolves canonical label
    assert snapshot.resolve_alias("Zhou Mingrui") == "lotm:self:zhou"
    assert snapshot.resolve_alias("zhou mingrui") == "lotm:self:zhou"

    # Resolves aliases
    assert snapshot.resolve_alias("Klein") == "lotm:self:zhou"
    assert snapshot.resolve_alias("klein moretti") == "lotm:self:zhou"

    # Unknown alias returns None
    assert snapshot.resolve_alias("Audrey Hall") is None
