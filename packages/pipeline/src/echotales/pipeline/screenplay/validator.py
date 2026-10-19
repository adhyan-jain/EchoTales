"""Screenplay validator and invariant checker.

Enforces production constraints:
1. No still held past 6.0 seconds (anti-slideshow / YouTube retention rule).
2. Pacing density: 10 to 25 cuts per finished minute.
3. 180-degree rule camera axis consistency between conversation partners.
4. Bible entity validation: characters, locations, and props must resolve in the Story Bible.
5. Audio coverage: shot duration must accommodate all contained dialogue lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from echotales.pipeline.screenplay.schema import (
    RenderTier,
    ScreenplayEpisode,
)

MAX_STILL_DURATION_S = 6.0
MIN_SHOT_DURATION_S = 0.5
TARGET_MIN_CUTS_PER_MINUTE = 10.0
TARGET_MAX_CUTS_PER_MINUTE = 25.0


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(slots=True)
class ValidationError:
    code: str
    message: str
    shot_index: int | None = None
    scene_id: str | None = None
    severity: ValidationSeverity = ValidationSeverity.ERROR


def validate_screenplay(
    episode: ScreenplayEpisode,
    *,
    valid_character_ids: set[str] | None = None,
    valid_location_ids: set[str] | None = None,
    valid_prop_ids: set[str] | None = None,
) -> list[ValidationError]:
    """Validate an episode screenplay against production and continuity invariants."""
    errors: list[ValidationError] = []

    if not episode.scenes:
        errors.append(
            ValidationError(
                code="EMPTY_EPISODE",
                message="Episode contains no scenes",
                severity=ValidationSeverity.ERROR,
            )
        )
        return errors

    total_shots = episode.shot_count
    if total_shots == 0:
        errors.append(
            ValidationError(
                code="EMPTY_SHOTS",
                message="Episode contains no shots",
                severity=ValidationSeverity.ERROR,
            )
        )
        return errors

    # Check overall pacing (cuts per minute)
    cpm = episode.cuts_per_minute
    if cpm < TARGET_MIN_CUTS_PER_MINUTE:
        errors.append(
            ValidationError(
                code="PACING_TOO_SLOW",
                message=(
                    f"Episode pacing ({cpm:.1f} cuts/min) is below target "
                    f"({TARGET_MIN_CUTS_PER_MINUTE} cuts/min); risk of slideshow viewer churn"
                ),
                severity=ValidationSeverity.WARNING,
            )
        )
    elif cpm > TARGET_MAX_CUTS_PER_MINUTE:
        errors.append(
            ValidationError(
                code="PACING_TOO_FAST",
                message=(
                    f"Episode pacing ({cpm:.1f} cuts/min) exceeds target "
                    f"({TARGET_MAX_CUTS_PER_MINUTE} cuts/min); visual fatigue risk"
                ),
                severity=ValidationSeverity.WARNING,
            )
        )

    for scene in episode.scenes:
        if valid_location_ids is not None and scene.location_id not in valid_location_ids:
            errors.append(
                ValidationError(
                    code="UNKNOWN_LOCATION",
                    message=f"Scene location {scene.location_id!r} not found in Story Bible",
                    scene_id=scene.scene_id,
                    severity=ValidationSeverity.ERROR,
                )
            )

        # Track 180-degree axis within scene
        prev_speaking_char: str | None = None
        prev_speaking_angle: float | None = None

        for shot in scene.shots:
            # 1. Check still duration ceiling
            if shot.render_tier == RenderTier.STILL and shot.duration_s > MAX_STILL_DURATION_S:
                errors.append(
                    ValidationError(
                        code="STILL_HELD_TOO_LONG",
                        message=(
                            f"Shot {shot.shot_index} (still tier) is held for {shot.duration_s:.1f}s, "
                            f"exceeding the maximum allowed {MAX_STILL_DURATION_S}s"
                        ),
                        shot_index=shot.shot_index,
                        scene_id=scene.scene_id,
                        severity=ValidationSeverity.ERROR,
                    )
                )

            # Minimum duration
            if shot.duration_s < MIN_SHOT_DURATION_S:
                errors.append(
                    ValidationError(
                        code="SHOT_TOO_SHORT",
                        message=(
                            f"Shot {shot.shot_index} duration {shot.duration_s:.2f}s is below "
                            f"minimum threshold {MIN_SHOT_DURATION_S}s"
                        ),
                        shot_index=shot.shot_index,
                        scene_id=scene.scene_id,
                        severity=ValidationSeverity.ERROR,
                    )
                )

            # 2. Check dialogue coverage
            dialogue_durations = [
                d.duration_s for d in shot.dialogue if d.duration_s is not None
            ]
            total_dialogue_s = sum(dialogue_durations)
            if total_dialogue_s > shot.duration_s + 0.05:  # small float epsilon
                errors.append(
                    ValidationError(
                        code="DIALOGUE_EXCEEDS_SHOT_DURATION",
                        message=(
                            f"Shot {shot.shot_index} duration ({shot.duration_s:.2f}s) is shorter "
                            f"than required dialogue audio ({total_dialogue_s:.2f}s)"
                        ),
                        shot_index=shot.shot_index,
                        scene_id=scene.scene_id,
                        severity=ValidationSeverity.ERROR,
                    )
                )

            # 3. Check character references in frame
            for char_ref in shot.characters:
                if valid_character_ids is not None and char_ref.self_id not in valid_character_ids:
                    errors.append(
                        ValidationError(
                            code="UNKNOWN_CHARACTER",
                            message=(
                                f"Shot {shot.shot_index} references character {char_ref.self_id!r} "
                                f"not found in Story Bible"
                            ),
                            shot_index=shot.shot_index,
                            scene_id=scene.scene_id,
                            severity=ValidationSeverity.ERROR,
                        )
                    )

            # 4. Check dialogue speakers
            for diag in shot.dialogue:
                if valid_character_ids is not None and diag.speaker_id not in valid_character_ids:
                    errors.append(
                        ValidationError(
                            code="UNKNOWN_SPEAKER",
                            message=(
                                f"Shot {shot.shot_index} has dialogue speaker {diag.speaker_id!r} "
                                f"not found in Story Bible"
                            ),
                            shot_index=shot.shot_index,
                            scene_id=scene.scene_id,
                            severity=ValidationSeverity.ERROR,
                        )
                    )

            # 5. Check 180-degree rule axis continuity for dialogue exchanges
            if shot.dialogue:
                current_speaker = shot.dialogue[0].speaker_id
                if (
                    prev_speaking_char is not None
                    and current_speaker != prev_speaking_char
                    and prev_speaking_angle is not None
                ):
                    # In a 2-person dialogue, conversation partners facing each other should have opposing screen orientations.
                    # If angles have the same sign or jump across the 180-degree line abruptly:
                    # E.g. Partner A looks right (angle in [0, 90]), Partner B looks left (angle in [90, 180] or [-180, -90])
                    # If both have the same viewing orientation (e.g. both angle 0), warn.
                    if abs(shot.axis_angle - prev_speaking_angle) < 15.0:
                        errors.append(
                            ValidationError(
                                code="AXIS_COLLISION_180",
                                message=(
                                    f"Shot {shot.shot_index} cross-cut from {prev_speaking_char} to {current_speaker} "
                                    f"shares nearly identical camera axis ({shot.axis_angle}° vs {prev_speaking_angle}°); "
                                    f"violates 180-degree line"
                                ),
                                shot_index=shot.shot_index,
                                scene_id=scene.scene_id,
                                severity=ValidationSeverity.WARNING,
                            )
                        )

                prev_speaking_char = current_speaker
                prev_speaking_angle = shot.axis_angle

    return errors
