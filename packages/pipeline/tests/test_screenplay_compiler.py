"""Tests for Screenplay compiler and cinematic invariant enforcement."""

from __future__ import annotations


import pytest

from echotales.core.models import CharacterBibleEntry, LocationBibleEntry, StoryBibleSnapshot
from echotales.pipeline.screenplay.compiler import (
    compile_screenplay,
    estimate_speech_duration_s,
)
from echotales.pipeline.screenplay.schema import (
    CameraMove,
    RenderTier,
    ShotSize,
)
from echotales.pipeline.screenplay.validator import (
    MAX_STILL_DURATION_S,
    ValidationSeverity,
    validate_screenplay,
)


@pytest.fixture
def hound_snapshot() -> StoryBibleSnapshot:
    return StoryBibleSnapshot(
        novel_id="hound",
        chapter=1.0,
        characters={
            "char:holmes": CharacterBibleEntry(
                self_id="char:holmes",
                canonical_label="Sherlock Holmes",
                active_persona_id="body:holmes",
                active_outfit="dressing_gown",
                aliases=["Holmes", "Mr. Holmes"],
            ),
            "char:watson": CharacterBibleEntry(
                self_id="char:watson",
                canonical_label="Dr. John Watson",
                active_persona_id="body:watson",
                active_outfit="morning_suit",
                aliases=["Watson", "Dr. Watson"],
            ),
            "char:mortimer": CharacterBibleEntry(
                self_id="char:mortimer",
                canonical_label="Dr. James Mortimer",
                active_persona_id="body:mortimer",
                aliases=["Mortimer", "Dr. Mortimer"],
            ),
        },
        locations={
            "loc:baker_st": LocationBibleEntry(
                location_id="loc:baker_st",
                canonical_name="221B Baker Street",
                description="Victorian sitting room, fireplace, gas lamps",
            )
        },
    )


def test_estimate_speech_duration() -> None:
    assert estimate_speech_duration_s("") == 0.0
    dur_short = estimate_speech_duration_s("Well, Watson, what do you make of it?")
    assert 1.2 <= dur_short <= 4.0
    dur_long = estimate_speech_duration_s("This is a much longer explanation of the events " * 5)
    assert dur_long > dur_short


def test_compile_screenplay_cinematic_invariants(hound_snapshot: StoryBibleSnapshot) -> None:
    # Use real Chapter 1 excerpt from showcase novel
    sample_text = """
    Mr. Sherlock Holmes, who was usually very late in the mornings, was seated at the breakfast table.
    I stood upon the hearth-rug and picked up the stick which our visitor had left behind him the night before.

    “Well, Watson, what do you make of it?”

    Holmes was sitting with his back to me, and I had given him no sign of my occupation.

    “How did you know what I was doing? I believe you have eyes in the back of your head.”

    “I have, at least, a well-polished, silver-plated coffee-pot in front of me,” said he.
    """

    episode = compile_screenplay(
        novel_id="hound",
        episode_number=1,
        chapters=[1.0],
        chapter_text=sample_text,
        snapshot=hound_snapshot,
        default_render_tier=RenderTier.PARALLAX_2_5D,
    )

    assert episode.novel_id == "hound"
    assert episode.episode_id == "hound_ep01"
    assert episode.chapter_range == (1.0, 1.0)
    assert len(episode.scenes) == 1
    shots = episode.all_shots
    assert len(shots) >= 4

    # 1. Opening hook check
    assert shots[0].shot_size == ShotSize.ESTABLISHING
    assert shots[0].camera_move == CameraMove.SLOW_PUSH_IN

    # 2. Closing cliffhanger check
    assert shots[-1].shot_size == ShotSize.EXTREME_CLOSE

    # 3. Invariant: No still shot > 6.0s
    for shot in shots:
        if shot.render_tier == RenderTier.STILL:
            assert shot.duration_s <= MAX_STILL_DURATION_S

    # 4. Invariant: Valid bible IDs for all characters and locations
    valid_chars = set(hound_snapshot.characters.keys())
    valid_locs = set(hound_snapshot.locations.keys())
    for shot in shots:
        assert shot.location_id in valid_locs
        for c in shot.characters:
            assert c.self_id in valid_chars
            assert c.persona_id == hound_snapshot.characters[c.self_id].active_persona_id

    # 5. Invariant: Audio duration coverage
    for shot in shots:
        total_audio = sum(d.duration_s or 0.0 for d in shot.dialogue)
        if total_audio > 0:
            assert shot.duration_s >= total_audio

    # 6. Strict validator execution: zero errors
    errors = validate_screenplay(
        episode,
        valid_character_ids=valid_chars,
        valid_location_ids=valid_locs,
    )
    hard_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    assert len(hard_errors) == 0, f"Screenplay validation errors: {hard_errors}"
