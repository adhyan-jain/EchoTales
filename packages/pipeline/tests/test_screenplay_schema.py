"""Tests for Episode Screenplay shot schema and invariant validator."""

from __future__ import annotations

import json

from echotales.pipeline.screenplay.schema import (
    CameraMove,
    CharacterAppearanceRef,
    RenderTier,
    ScreenplayEpisode,
    ScreenplayScene,
    ScreenplayShot,
    ShotDialogue,
    ShotSize,
    TimeOfDay,
    Transition,
)
from echotales.pipeline.screenplay.validator import (
    ValidationSeverity,
    validate_screenplay,
)


def _build_sample_episode(still_duration: float = 4.0) -> ScreenplayEpisode:
    shot1 = ScreenplayShot(
        shot_index=1,
        scene_id="scene_bedroom",
        location_id="loc_bedroom",
        characters=[
            CharacterAppearanceRef(
                self_id="self_zhou",
                persona_id="self_zhou:body1",
                expression="shocked",
                screen_position="center",
            )
        ],
        shot_size=ShotSize.MEDIUM,
        camera_move=CameraMove.SLOW_PUSH_IN,
        axis_angle=30.0,
        action="touches the wound at his temple",
        props=["revolver"],
        duration_s=still_duration,
        render_tier=RenderTier.PARALLAX_2_5D,
        dialogue=[
            ShotDialogue(
                speaker_id="self_zhou",
                text="A bullet... through my head?",
                emotion="shock",
                intensity=3,
                nonverbal=["gasp"],
                duration_s=3.2,
            )
        ],
        sfx=["heartbeat"],
        onomatopoeia=None,
        transition_to_next=Transition.CUT,
    )

    shot2 = ScreenplayShot(
        shot_index=2,
        scene_id="scene_bedroom",
        location_id="loc_bedroom",
        characters=[],
        shot_size=ShotSize.CLOSE,
        camera_move=CameraMove.STATIC,
        axis_angle=150.0,
        action="the cylinder of the revolver reflects moonlight",
        props=["revolver"],
        duration_s=2.5,
        render_tier=RenderTier.STILL,
        dialogue=[],
        sfx=["clock_ticking"],
        onomatopoeia=None,
        transition_to_next=Transition.CUT,
    )

    scene = ScreenplayScene(
        scene_id="scene_bedroom",
        scene_index=1,
        location_id="loc_bedroom",
        time_of_day=TimeOfDay.NIGHT,
        mood="tense",
        ambience_sfx="wind_outside",
        music_bed_style="eerie_strings",
        shots=[shot1, shot2],
    )

    return ScreenplayEpisode(
        episode_id="ep_1",
        novel_id="lotm",
        chapter_range=(1.0, 1.0),
        title="Crimson Moon",
        target_duration_s=60.0,
        scenes=[scene],
    )


def test_screenplay_serialization_roundtrip() -> None:
    episode = _build_sample_episode()
    data = episode.to_dict()
    serialized = json.dumps(data)
    loaded = json.loads(serialized)
    restored = ScreenplayEpisode.from_dict(loaded)

    assert restored.episode_id == episode.episode_id
    assert restored.shot_count == 2
    assert restored.scenes[0].shots[0].characters[0].self_id == "self_zhou"
    assert restored.scenes[0].shots[0].dialogue[0].intensity == 3
    assert restored.scenes[0].shots[0].dialogue[0].nonverbal == ["gasp"]


def test_validator_detects_still_held_past_ceiling() -> None:
    episode = _build_sample_episode()
    # Change shot2 (still tier) to exceed MAX_STILL_DURATION_S (6.0s)
    episode.scenes[0].shots[1].duration_s = 8.5

    errors = validate_screenplay(
        episode,
        valid_character_ids={"self_zhou"},
        valid_location_ids={"loc_bedroom"},
    )
    still_errors = [e for e in errors if e.code == "STILL_HELD_TOO_LONG"]
    assert len(still_errors) == 1
    assert still_errors[0].severity == ValidationSeverity.ERROR
    assert still_errors[0].shot_index == 2


def test_validator_detects_dialogue_longer_than_shot() -> None:
    episode = _build_sample_episode()
    # Shot 1 duration 3.0s, but dialogue duration 4.5s
    episode.scenes[0].shots[0].duration_s = 3.0
    episode.scenes[0].shots[0].dialogue[0].duration_s = 4.5

    errors = validate_screenplay(
        episode,
        valid_character_ids={"self_zhou"},
        valid_location_ids={"loc_bedroom"},
    )
    diag_errors = [e for e in errors if e.code == "DIALOGUE_EXCEEDS_SHOT_DURATION"]
    assert len(diag_errors) == 1
    assert diag_errors[0].severity == ValidationSeverity.ERROR


def test_validator_detects_unknown_entities() -> None:
    episode = _build_sample_episode()

    errors = validate_screenplay(
        episode,
        valid_character_ids={"unknown_other"},
        valid_location_ids={"unknown_room"},
    )
    codes = {e.code for e in errors}
    assert "UNKNOWN_LOCATION" in codes
    assert "UNKNOWN_CHARACTER" in codes
    assert "UNKNOWN_SPEAKER" in codes


def test_validator_detects_180_axis_jump() -> None:
    # Build two conversational shots between Zhou and Inspector
    shot1 = ScreenplayShot(
        shot_index=1,
        scene_id="scene_talk",
        location_id="loc_room",
        axis_angle=30.0,
        dialogue=[ShotDialogue(speaker_id="zhou", text="Hello")],
        duration_s=3.0,
    )
    shot2 = ScreenplayShot(
        shot_index=2,
        scene_id="scene_talk",
        location_id="loc_room",
        axis_angle=35.0,  # Nearly identical angle for conversation partner violates 180-degree rule
        dialogue=[ShotDialogue(speaker_id="inspector", text="Who are you?")],
        duration_s=3.0,
    )
    scene = ScreenplayScene(
        scene_id="scene_talk",
        scene_index=1,
        location_id="loc_room",
        shots=[shot1, shot2],
    )
    episode = ScreenplayEpisode(
        episode_id="ep_axis",
        novel_id="lotm",
        chapter_range=(1.0, 1.0),
        title="Interrogation",
        scenes=[scene],
    )

    errors = validate_screenplay(
        episode,
        valid_character_ids={"zhou", "inspector"},
        valid_location_ids={"loc_room"},
    )
    axis_warnings = [e for e in errors if e.code == "AXIS_COLLISION_180"]
    assert len(axis_warnings) == 1
    assert axis_warnings[0].severity == ValidationSeverity.WARNING
