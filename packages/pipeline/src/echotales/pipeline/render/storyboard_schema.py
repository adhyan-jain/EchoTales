"""Structured schema for the Storyboard Director (P2).

Replaces the legacy one-panel-per-block approach with hierarchical,
beat-aware, multi-angle storyboard sequence planning.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class NarrativeFunction(StrEnum):
    """Cohn-style Visual Narrative Grammar + adaptation functions."""

    ESTABLISHING = "establishing"
    INITIAL = "initial"
    PROLONGATION = "prolongation"
    PEAK = "peak"
    RELEASE = "release"
    REACTION = "reaction"
    INSERT_DETAIL = "insert_detail"
    SYMBOLIC = "symbolic"
    MEMORY_MONTAGE = "memory_montage"
    TIME_TRANSITION = "time_transition"
    SFX_TITLE = "sfx_title"


class ShotType(StrEnum):
    """Camera framing and shot scale."""

    EXTREME_WIDE = "extreme_wide"
    WIDE = "wide"
    MEDIUM_TWO_SHOT = "medium_two_shot"
    MEDIUM_PORTRAIT = "medium_portrait"
    OVER_THE_SHOULDER = "over_the_shoulder"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"


class CameraAngle(StrEnum):
    """Vertical camera perspective."""

    EYE_LEVEL = "eye_level"
    LOW_ANGLE = "low_angle"
    HIGH_ANGLE = "high_angle"
    DUTCH_TILT = "dutch_tilt"
    OVERHEAD = "overhead"


class ScreenDirection(StrEnum):
    """Character horizontal orientation on the virtual stage."""

    FACING_LEFT = "facing_left"
    FACING_RIGHT = "facing_right"
    FRONT = "front"
    BACK = "back"
    OVERHEAD = "overhead"


class ProseDisposition(StrEnum):
    """How a source novel text line is handled in the adaptation."""

    KEEP_TEXT = "keep_text"  # Kept as caption or speech balloon
    SHOW = "show"            # Translated directly into visual action / environment
    CUT = "cut"              # Safely omitted with an auditable rationale


class CaptionStyle(StrEnum):
    """Visual lettering taxonomy."""

    SPEECH = "speech"
    SHOUT = "shout"
    THOUGHT = "thought"
    NARRATOR = "narrator"
    MEMORY = "memory"
    FLASHBACK = "flashback"
    TIME_SKIP = "time_skip"
    POETRY = "poetry"
    SYSTEM_INTERFACE = "system_interface"
    CROWD_COLLECTIVE = "crowd_collective"
    NONE = "none"


class StoryboardPanel(BaseModel):
    """A single panel planned by the storyboard artist."""

    panel_id: str
    scene_id: str
    beat_id: str
    panel_index: int = 1
    narrative_function: NarrativeFunction = NarrativeFunction.PROLONGATION
    shot_type: ShotType = ShotType.MEDIUM_PORTRAIT
    camera_angle: CameraAngle = CameraAngle.EYE_LEVEL
    screen_direction: ScreenDirection = ScreenDirection.FRONT
    subjects: list[str] = Field(default_factory=list)
    speaking_character: str | None = None
    listening_character: str | None = None
    is_crowd_shot: bool = False
    action_visual: str = ""
    expression_visual: str = ""
    environment_visual: str = ""
    props_visible: list[str] = Field(default_factory=list)
    segment_palette: str = "battle_dusk"
    caption_style: CaptionStyle = CaptionStyle.NONE
    prose_disposition: ProseDisposition = ProseDisposition.SHOW
    source_span_ids: list[str] = Field(default_factory=list)
    dialogue_text: str | None = None
    sfx_text: str | None = None
    invented: bool = False
    invention_rationale: str | None = None

    @model_validator(mode="after")
    def _validate_dialogue_and_speech(self) -> StoryboardPanel:
        if self.dialogue_text and self.caption_style == CaptionStyle.NONE:
            self.caption_style = CaptionStyle.SPEECH
        if self.caption_style in (CaptionStyle.SPEECH, CaptionStyle.SHOUT) and not self.speaking_character and not self.is_crowd_shot:
            self.is_crowd_shot = True
        return self


class StoryboardSequence(BaseModel):
    """An ordered sequence of storyboard panels for one scene or beat."""

    scene_id: str
    beat_id: str
    segment_palette: str = "battle_dusk"
    panels: list[StoryboardPanel] = Field(default_factory=list)

    def total_panels(self) -> int:
        return len(self.panels)

    def reaction_panel_count(self) -> int:
        return sum(1 for p in self.panels if p.narrative_function == NarrativeFunction.REACTION)

    def insert_panel_count(self) -> int:
        return sum(1 for p in self.panels if p.narrative_function == NarrativeFunction.INSERT_DETAIL)
