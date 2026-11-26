"""Unit tests for the 7-layer character identity architecture (P4)."""

from __future__ import annotations

from echotales.core.enums import OBSERVER_READER, AssertedBy, TargetKind, TruthStatus
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition, Self, SelfPersonaBinding
from echotales.core.store import Store
from echotales.pipeline.persona.layers import (
    AppearanceLayer,
    BodyEpochLayer,
    CharacterState,
    ConditionLayer,
    DisguiseLayer,
    OutfitLayer,
    SelfLayer,
    VoiceLayer,
    resolve_character_state,
)


def test_seven_layers_and_disguise_resolution() -> None:
    state = CharacterState(
        self_layer=SelfLayer(self_id="s1", canonical_label="Fang Yuan"),
        body_epoch=BodyEpochLayer(persona_id="s1:body1", gender="male", age_band="adult", stature="lean"),
        appearance=AppearanceLayer(hair_color="black", eye_color="dark brown", scars=["cheek scar"]),
        outfit=OutfitLayer(garments="green robes", colors=["deep green"]),
        condition=ConditionLayer(wounds=["slash on forearm"], blood_level="light"),
        disguise=DisguiseLayer(
            active=True,
            facade_name="Scholar Gu",
            facade_attire="grey scholar robes",
            revealed_to_observers={"reader", "narrator"},
        ),
        voice=VoiceLayer(speaker_id="p227", base_pitch_shift=-0.5, disguised_pitch_shift=1.2),
    )

    # Reader observer sees through disguise
    assert state.resolved_name(observer_id="reader") == "Fang Yuan"
    assert "deep green" in state.resolved_attire(observer_id="reader")
    brief_reader = state.to_character_brief(lead=True, observer_id="reader")
    assert brief_reader.name == "Fang Yuan"
    assert brief_reader.appearance["scar"] == "cheek scar"

    # Enemy/mortal observer does not see through disguise
    assert state.resolved_name(observer_id="mortal_villager") == "Scholar Gu"
    assert state.resolved_attire(observer_id="mortal_villager") == "grey scholar robes"
    brief_enemy = state.to_character_brief(lead=True, observer_id="mortal_villager")
    assert brief_enemy.name == "Scholar Gu"


def test_resolve_character_state_from_store(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    novel_id = "test_novel"
    store.add_novel(novel_id, "Test Novel", "/tmp/novel.txt", "standard")

    dp = DiscoursePosition(chapter=1, offset=0)
    store.add_self(Self(id="fy", novel_id=novel_id, kind=TargetKind.SELF, canonical_label="Fang Yuan", first_attested_pos=dp))

    interval = FuzzyInterval.point_known(1.0, 10.0)
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="fy",
            persona_id="fy:p1",
            interval=interval,
            learned_at_pos=dp,
            observer_id=OBSERVER_READER,
        )
    )

    for k, v in [("gender", "male"), ("age_band", "youth"), ("hair_color", "black"), ("attire", "hemp robes")]:
        store.add_attribute(
            novel_id,
            Attribute(
                target_kind=TargetKind.PERSONA,
                target_id="fy:p1",
                key=k,
                value=v,
                interval=interval,
                learned_at_pos=dp,
                observer_id=OBSERVER_READER,
                asserted_by=AssertedBy.INFERENCE,
                truth_status=TruthStatus.TRUE,
                evidence="text quote",
                confidence=0.9,
            ),
        )

    state = resolve_character_state(store, novel_id, "fy", 2.0)
    assert state.self_layer.canonical_label == "Fang Yuan"
    assert state.body_epoch.age_band == "youth"
    assert state.appearance.hair_color == "black"
    assert "hemp robes" in state.outfit.garments
