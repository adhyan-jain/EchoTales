"""Episode Screenplay shot schema and data contracts.

Represents an adapted web-novel episode ready for multi-asset rendering
(character turnarounds, location plates, keyframes, audio performance,
and 2.5D / video composition).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ShotSize(StrEnum):
    """Camera framing distances."""

    ESTABLISHING = "establishing"
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE = "close"
    EXTREME_CLOSE = "extreme_close"
    REACTION = "reaction"
    INSERT = "insert"


class CameraMove(StrEnum):
    """Camera motion primitives."""

    STATIC = "static"
    SLOW_PUSH_IN = "slow_push_in"
    PULL_OUT = "pull_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    RACK_FOCUS = "rack_focus"
    IMPACT_SHAKE = "impact_shake"


class RenderTier(StrEnum):
    """Visual engine selected for a shot."""

    PARALLAX_2_5D = "2.5d"
    VIDEO = "video"
    STILL = "still"


class Transition(StrEnum):
    """Cut transition to subsequent shot."""

    CUT = "cut"
    FLASH_CUT = "flash_cut"
    DISSOLVE = "dissolve"
    WHIP_PAN = "whip_pan"


class TimeOfDay(StrEnum):
    """Scene lighting and temporal condition."""

    DAY = "day"
    NIGHT = "night"
    DUSK = "dusk"
    DAWN = "dawn"
    INTERIOR_LIT = "interior_lit"
    DIM = "dim"


@dataclass(slots=True)
class CharacterAppearanceRef:
    """Character reference in frame with specific persona and expression."""

    self_id: str
    persona_id: str
    outfit_id: str | None = None
    expression: str = "neutral"  # neutral, angry, shocked, crying, smirking, shouting, in_pain
    pose: str = "standing"
    screen_position: str = "center"  # left, center, right, foreground, background

    def to_dict(self) -> dict[str, Any]:
        return {
            "self_id": self.self_id,
            "persona_id": self.persona_id,
            "outfit_id": self.outfit_id,
            "expression": self.expression,
            "pose": self.pose,
            "screen_position": self.screen_position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterAppearanceRef:
        return cls(
            self_id=data["self_id"],
            persona_id=data["persona_id"],
            outfit_id=data.get("outfit_id"),
            expression=data.get("expression", "neutral"),
            pose=data.get("pose", "standing"),
            screen_position=data.get("screen_position", "center"),
        )


@dataclass(slots=True)
class ShotDialogue:
    """A line of spoken dialogue or voiceover within a shot."""

    speaker_id: str
    text: str
    emotion: str = "neutral"
    intensity: int = 0  # 0: subtle/flat, 1: conversational, 2: emotional, 3: peak/exclamation
    nonverbal: list[str] = field(default_factory=list)  # ["gasp", "shout", "sigh", "chuckle", "sob"]
    audio_path: str | None = None
    duration_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "text": self.text,
            "emotion": self.emotion,
            "intensity": self.intensity,
            "nonverbal": list(self.nonverbal),
            "audio_path": self.audio_path,
            "duration_s": self.duration_s,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShotDialogue:
        return cls(
            speaker_id=data["speaker_id"],
            text=data["text"],
            emotion=data.get("emotion", "neutral"),
            intensity=int(data.get("intensity", 0)),
            nonverbal=list(data.get("nonverbal", [])),
            audio_path=data.get("audio_path"),
            duration_s=float(data["duration_s"]) if data.get("duration_s") is not None else None,
        )


@dataclass(slots=True)
class ScreenplayShot:
    """An individual storyboarded shot within a scene."""

    shot_index: int
    scene_id: str
    location_id: str
    characters: list[CharacterAppearanceRef] = field(default_factory=list)
    shot_size: ShotSize = ShotSize.MEDIUM
    camera_move: CameraMove = CameraMove.STATIC
    axis_angle: float = 0.0  # 180-degree axis angle: [-180.0, 180.0]
    action: str = ""
    props: list[str] = field(default_factory=list)
    duration_s: float = 3.5
    render_tier: RenderTier = RenderTier.PARALLAX_2_5D
    dialogue: list[ShotDialogue] = field(default_factory=list)
    sfx: list[str] = field(default_factory=list)
    onomatopoeia: str | None = None
    transition_to_next: Transition = Transition.CUT

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_index": self.shot_index,
            "scene_id": self.scene_id,
            "location_id": self.location_id,
            "characters": [c.to_dict() for c in self.characters],
            "shot_size": str(self.shot_size),
            "camera_move": str(self.camera_move),
            "axis_angle": self.axis_angle,
            "action": self.action,
            "props": list(self.props),
            "duration_s": self.duration_s,
            "render_tier": str(self.render_tier),
            "dialogue": [d.to_dict() for d in self.dialogue],
            "sfx": list(self.sfx),
            "onomatopoeia": self.onomatopoeia,
            "transition_to_next": str(self.transition_to_next),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenplayShot:
        return cls(
            shot_index=int(data["shot_index"]),
            scene_id=data["scene_id"],
            location_id=data["location_id"],
            characters=[CharacterAppearanceRef.from_dict(c) for c in data.get("characters", [])],
            shot_size=ShotSize(data.get("shot_size", ShotSize.MEDIUM)),
            camera_move=CameraMove(data.get("camera_move", CameraMove.STATIC)),
            axis_angle=float(data.get("axis_angle", 0.0)),
            action=data.get("action", ""),
            props=list(data.get("props", [])),
            duration_s=float(data.get("duration_s", 3.5)),
            render_tier=RenderTier(data.get("render_tier", RenderTier.PARALLAX_2_5D)),
            dialogue=[ShotDialogue.from_dict(d) for d in data.get("dialogue", [])],
            sfx=list(data.get("sfx", [])),
            onomatopoeia=data.get("onomatopoeia"),
            transition_to_next=Transition(data.get("transition_to_next", Transition.CUT)),
        )


@dataclass(slots=True)
class ScreenplayScene:
    """A dramatic scene set in a single location and continuous time."""

    scene_id: str
    scene_index: int
    location_id: str
    time_of_day: TimeOfDay = TimeOfDay.DAY
    mood: str = "neutral"
    ambience_sfx: str | None = None
    music_bed_style: str | None = None
    shots: list[ScreenplayShot] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return sum(s.duration_s for s in self.shots)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "scene_index": self.scene_index,
            "location_id": self.location_id,
            "time_of_day": str(self.time_of_day),
            "mood": self.mood,
            "ambience_sfx": self.ambience_sfx,
            "music_bed_style": self.music_bed_style,
            "shots": [s.to_dict() for s in self.shots],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenplayScene:
        return cls(
            scene_id=data["scene_id"],
            scene_index=int(data["scene_index"]),
            location_id=data["location_id"],
            time_of_day=TimeOfDay(data.get("time_of_day", TimeOfDay.DAY)),
            mood=data.get("mood", "neutral"),
            ambience_sfx=data.get("ambience_sfx"),
            music_bed_style=data.get("music_bed_style"),
            shots=[ScreenplayShot.from_dict(s) for s in data.get("shots", [])],
        )


@dataclass(slots=True)
class ScreenplayEpisode:
    """A complete compiled episode screenplay (60-180 seconds)."""

    episode_id: str
    novel_id: str
    chapter_range: tuple[float, float]
    title: str
    format_type: str = "dramatized"  # dramatized | recap
    aspect_ratio: str = "9:16"  # 9:16 | 16:9
    target_duration_s: float = 90.0
    scenes: list[ScreenplayScene] = field(default_factory=list)

    @property
    def total_duration_s(self) -> float:
        return sum(scene.duration_s for scene in self.scenes)

    @property
    def all_shots(self) -> list[ScreenplayShot]:
        return [shot for scene in self.scenes for shot in scene.shots]

    @property
    def shot_count(self) -> int:
        return sum(len(scene.shots) for scene in self.scenes)

    @property
    def cuts_per_minute(self) -> float:
        total_m = self.total_duration_s / 60.0
        if total_m <= 0.0:
            return 0.0
        return self.shot_count / total_m

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "novel_id": self.novel_id,
            "chapter_range": list(self.chapter_range),
            "title": self.title,
            "format_type": self.format_type,
            "aspect_ratio": self.aspect_ratio,
            "target_duration_s": self.target_duration_s,
            "total_duration_s": self.total_duration_s,
            "shot_count": self.shot_count,
            "cuts_per_minute": self.cuts_per_minute,
            "scenes": [s.to_dict() for s in self.scenes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenplayEpisode:
        return cls(
            episode_id=data["episode_id"],
            novel_id=data["novel_id"],
            chapter_range=(float(data["chapter_range"][0]), float(data["chapter_range"][1])),
            title=data.get("title", ""),
            format_type=data.get("format_type", "dramatized"),
            aspect_ratio=data.get("aspect_ratio", "9:16"),
            target_duration_s=float(data.get("target_duration_s", 90.0)),
            scenes=[ScreenplayScene.from_dict(s) for s in data.get("scenes", [])],
        )
