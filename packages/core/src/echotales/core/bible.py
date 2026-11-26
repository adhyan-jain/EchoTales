"""The Director's Bible: Volume-wide narrative and visual ground truth.

Built once per volume and stored alongside the story graph. Supplies the storyboard director
with character appearance epochs, backstory reveals, setup/payoff indices, and segment palettes.
"""

from __future__ import annotations

from echotales.core.interval import FuzzyInterval, StoryPos
from echotales.core.models import DiscoursePosition
from pydantic import BaseModel, Field


class AppearanceEpoch(BaseModel):
    """How a character's physical embodiment and presentation looks during a time interval."""

    self_id: str
    persona_id: str
    epoch_label: str
    interval: FuzzyInterval
    age_band: str = "adult"  # child, youth, adult, elder
    hair_desc: str = ""
    eye_desc: str = ""
    facial_desc: str = ""
    base_build: str = ""
    default_attire: str = ""
    condition_notes: str = ""
    features: dict[str, str] = Field(default_factory=dict)

    def summary_prompt_clause(self) -> str:
        parts: list[str] = []
        if self.age_band and self.age_band != "adult":
            parts.append(self.age_band)
        if self.hair_desc:
            parts.append(self.hair_desc)
        if self.facial_desc:
            parts.append(self.facial_desc)
        if self.base_build:
            parts.append(self.base_build)
        if self.default_attire:
            parts.append(self.default_attire)
        if self.condition_notes:
            parts.append(self.condition_notes)
        return ", ".join(parts)


class RevealEvent(BaseModel):
    """A backstory fact or plot revelation and when the reader learns it."""

    event_id: str
    story_time: StoryPos
    revealed_at: DiscoursePosition
    involved_self_ids: list[str] = Field(default_factory=list)
    short_summary: str
    visual_motifs: list[str] = Field(default_factory=list)
    eligible_for_memory_montage: bool = True


class SetupPayoffEntry(BaseModel):
    """A recurring prop, weapon, location or symbol that sets up future events."""

    entity_id: str
    entity_name: str
    introduced_at: DiscoursePosition
    payoff_at: DiscoursePosition
    narrative_weight: float = 1.0
    visual_motif: str = ""
    category: str = "prop"  # prop, weapon, relic, location, gesture, symbol


class SegmentPalette(BaseModel):
    """Visual color mood and rendering tones for a scene segment."""

    palette_id: str
    name: str
    mood: str
    primary_color: str
    accent_color: str
    lighting_style: str
    contrast_level: str = "high"  # low, medium, high, harsh
    prompt_keywords: list[str] = Field(default_factory=list)


class VolumeBible(BaseModel):
    """The volume-wide director's bible."""

    novel_id: str
    volume_index: int = 1
    epochs_by_self: dict[str, list[AppearanceEpoch]] = Field(default_factory=dict)
    reveals: list[RevealEvent] = Field(default_factory=list)
    setup_payoffs: list[SetupPayoffEntry] = Field(default_factory=list)
    palettes: dict[str, SegmentPalette] = Field(default_factory=dict)

    def get_look_at(self, self_id: str, pos: DiscoursePosition) -> AppearanceEpoch | None:
        """Find the valid appearance epoch for self_id at discourse position pos."""
        epochs = self.epochs_by_self.get(self_id, [])
        if not epochs:
            return None
        story_val = float(pos.chapter)
        for ep in epochs:
            if ep.interval.contains(story_val).is_possible:
                return ep
        return epochs[0]

    def get_eligible_montages(self, pos: DiscoursePosition) -> list[RevealEvent]:
        """Get all backstory events revealed by position pos for memory montages."""
        return [r for r in self.reveals if r.eligible_for_memory_montage and r.revealed_at <= pos]

    def get_active_payoffs(self, pos: DiscoursePosition) -> list[SetupPayoffEntry]:
        """Get setup/payoff items active around position pos."""
        return [
            s for s in self.setup_payoffs
            if s.introduced_at.chapter <= pos.chapter <= s.payoff_at.chapter
        ]

    def get_palette(self, palette_id: str) -> SegmentPalette | None:
        return self.palettes.get(palette_id)
