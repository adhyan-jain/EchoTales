"""Trending Short-Form Reels/TikTok Visual & Motion Preset Engine.

Provides automated visual direction, dynamic pacing, 9:16 vertical crop composition,
kinetic caption placement, and visual hook styling tailored for web novel video adaptations.
Designed to operate fully autonomously without requiring human-in-the-loop verification
or external reference image providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ReelStylePreset(StrEnum):
    DARK_FANTASY_ANIME = "dark_fantasy_anime"
    MANHWA_ACTION = "manhwa_action"
    MYSTIC_NOIR = "mystic_noir"
    EPIC_CULTIVATION = "epic_cultivation"


class CameraMotionType(StrEnum):
    SLOW_ZOOM_IN = "slow_zoom_in"
    QUICK_PAN_RIGHT = "quick_pan_right"
    DUTCH_ANGLE_SHAKE = "dutch_angle_shake"
    STATIC_DRAMATIC = "static_dramatic"


@dataclass(frozen=True, slots=True)
class ReelBeatSpec:
    beat_index: int
    duration_sec: float
    aspect_ratio: str = "9:16"
    style_preset: ReelStylePreset = ReelStylePreset.DARK_FANTASY_ANIME
    camera_motion: CameraMotionType = CameraMotionType.SLOW_ZOOM_IN
    lighting_cue: str = "dramatic side rim lighting, dark atmospheric mist"
    kinetic_caption_style: str = "bold yellow center-bottom punch"


@dataclass(slots=True)
class ReelCompositionPlan:
    novel_id: str
    chapter: float
    target_aspect_ratio: str = "9:16"
    beats: list[ReelBeatSpec] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(b.duration_sec for b in self.beats)


def derive_reel_pacing(beat_type: str, text_length: int) -> float:
    """Calculate dynamic short-form reel beat duration in seconds.

    Ensures fast-paced engagement for short-form video algorithms:
    - High-action beats: 1.2s - 2.0s
    - Dramatic monologue / reveal: 2.5s - 3.5s
    """
    if beat_type in ("ACTION", "COMBAT", "CROWD_REACTION"):
        return max(1.2, min(2.0, 1.0 + text_length * 0.02))
    elif beat_type in ("INNER_MONOLOGUE", "REVEAL"):
        return max(2.2, min(3.5, 1.8 + text_length * 0.03))
    return max(1.5, min(2.8, 1.2 + text_length * 0.025))


def select_reel_style(novel_id: str) -> ReelStylePreset:
    """Select the optimal visual style preset based on novel theme."""
    lower = novel_id.lower()
    if "reverend" in lower:
        return ReelStylePreset.EPIC_CULTIVATION
    elif "mysteries" in lower:
        return ReelStylePreset.MYSTIC_NOIR
    elif "viewpoint" in lower or "orv" in lower:
        return ReelStylePreset.MANHWA_ACTION
    return ReelStylePreset.DARK_FANTASY_ANIME


def build_reel_plan_for_chapter(
    novel_id: str,
    chapter: float,
    beats: list[dict],
) -> ReelCompositionPlan:
    """Generate an automated 9:16 reel composition plan for a chapter's beats.

    Applies dynamic camera movement, atmospheric lighting prompts, and kinetic subtitle timing.
    """
    style = select_reel_style(novel_id)
    plan_beats: list[ReelBeatSpec] = []

    for idx, beat in enumerate(beats):
        beat_type = str(beat.get("type", "NARRATION_ACTION"))
        text = str(beat.get("text", ""))
        duration = derive_reel_pacing(beat_type, len(text))

        # Motion selection rule
        if beat_type in ("ACTION", "COMBAT"):
            motion = CameraMotionType.DUTCH_ANGLE_SHAKE if idx % 2 == 0 else CameraMotionType.QUICK_PAN_RIGHT
        elif beat_type in ("INNER_MONOLOGUE", "REVEAL"):
            motion = CameraMotionType.SLOW_ZOOM_IN
        else:
            motion = CameraMotionType.STATIC_DRAMATIC

        lighting = (
            "intense volumetric lighting, high contrast shadows"
            if style is ReelStylePreset.MANHWA_ACTION
            else "mystical glowing fog, deep obsidian atmosphere"
        )

        plan_beats.append(
            ReelBeatSpec(
                beat_index=idx,
                duration_sec=duration,
                aspect_ratio="9:16",
                style_preset=style,
                camera_motion=motion,
                lighting_cue=lighting,
                kinetic_caption_style="center-weighted bold uppercase",
            )
        )

    return ReelCompositionPlan(
        novel_id=novel_id,
        chapter=chapter,
        target_aspect_ratio="9:16",
        beats=plan_beats,
    )
