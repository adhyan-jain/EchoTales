"""7-layer identity architecture for consistent character progression across story intervals (P4).

Architecture:
1. SelfLayer: Core consciousness, persistent identifier (survives death/rebirth/possession).
2. BodyEpochLayer: Physiological body frame, biological age, stature, anatomical basis.
3. AppearanceLayer: Morphological state across intervals (hair, scars, eyes, permanent features).
4. OutfitLayer: Outer garments, robes, armor, uniform, cleanliness state.
5. ConditionLayer: Beat-level ephemeral physical state (blood, dirt, burns, exhaustion).
6. DisguiseLayer: Active facade, mask, observer-specific visibility.
7. VoiceLayer: Native timbre, pitch modulation, emotional delivery profile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from echotales.core.interval import FuzzyInterval
from echotales.core.store import Store
from echotales.pipeline.persona.split import bodies_of, standing_values

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SelfLayer:
    """Layer 1: True continuity of consciousness."""

    self_id: str
    canonical_label: str
    memory_anchor: str = ""
    soul_rebirth_count: int = 0


@dataclass(slots=True)
class BodyEpochLayer:
    """Layer 2: Base physiological anatomical frame."""

    persona_id: str
    gender: str = "unknown"
    age_band: str = "adult"  # child | youth | adult | middle_aged | elder
    age_years: int = 0
    stature: str = "average"  # slim, tall, burly, petite
    skin_tone: str = "pale"
    interval: FuzzyInterval | None = None


@dataclass(slots=True)
class AppearanceLayer:
    """Layer 3: Morphological state valid across story intervals."""

    hair_color: str = "black"
    hair_length: str = "long"
    hair_style: str = "topknot"
    eye_color: str = "dark brown"
    scars: list[str] = field(default_factory=list)
    distinctive_marks: list[str] = field(default_factory=list)
    build_description: str = ""

    def to_appearance_dict(self) -> dict[str, str]:
        out = {
            "hair_color": self.hair_color,
            "hair_style": f"{self.hair_length} {self.hair_style}".strip(),
            "eye_color": self.eye_color,
        }
        if self.scars:
            out["scar"] = ", ".join(self.scars)
        if self.distinctive_marks:
            out["mark"] = ", ".join(self.distinctive_marks)
        if self.build_description:
            out["build"] = self.build_description
        return out


@dataclass(slots=True)
class OutfitLayer:
    """Layer 4: Garments, armor, and attire state."""

    garments: str = "robes"
    style_category: str = "traditional"  # traditional, modern, armor, formal
    colors: list[str] = field(default_factory=lambda: ["dark green"])
    accessories: list[str] = field(default_factory=list)
    wear_condition: str = "clean"  # clean, tattered, soaked, shredded

    def description(self) -> str:
        color_str = " and ".join(self.colors) if self.colors else ""
        wear = f", {self.wear_condition}" if self.wear_condition != "clean" else ""
        acc = f", with {', '.join(self.accessories)}" if self.accessories else ""
        return f"{color_str} {self.garments}{wear}{acc}".strip()


@dataclass(slots=True)
class ConditionLayer:
    """Layer 5: Ephemeral physical condition at exact beat/panel."""

    wounds: list[str] = field(default_factory=list)
    blood_level: str = "none"  # none, light, heavy, soaked
    dirt_level: str = "none"   # none, dusty, soiled, mud-stained
    fatigue: str = "alert"     # alert, strained, exhausted, unconscious
    special_effects: list[str] = field(default_factory=list)  # glowing aura, smoking, frost

    def description(self) -> str:
        clauses = []
        if self.wounds:
            clauses.extend(self.wounds)
        if self.blood_level not in ("none", ""):
            clauses.append(f"{self.blood_level} blood")
        if self.dirt_level not in ("none", ""):
            clauses.append(f"{self.dirt_level}")
        if self.fatigue not in ("alert", ""):
            clauses.append(f"{self.fatigue}")
        if self.special_effects:
            clauses.extend(self.special_effects)
        return ", ".join(clauses)


@dataclass(slots=True)
class DisguiseLayer:
    """Layer 6: Active facade, mask, or shapeshifting."""

    active: bool = False
    facade_name: str = ""
    facade_appearance: dict[str, str] = field(default_factory=dict)
    facade_attire: str = ""
    revealed_to_observers: set[str] = field(default_factory=lambda: {"reader", "narrator"})

    def is_visible_to(self, observer_id: str) -> bool:
        """True if the observer sees through the disguise to the true identity."""
        if not self.active:
            return True
        return observer_id.lower() in {o.lower() for o in self.revealed_to_observers}


@dataclass(slots=True)
class VoiceLayer:
    """Layer 7: Audio timbre, pitch, and prosody profile."""

    speaker_id: str = ""
    timbre_descriptor: str = "calm, deep, steady"
    base_pitch_shift: float = 0.0
    base_tempo: float = 1.0
    disguised_pitch_shift: float | None = None


@dataclass(slots=True)
class CharacterState:
    """Composite 7-layer character state resolved at a specific story point."""

    self_layer: SelfLayer
    body_epoch: BodyEpochLayer
    appearance: AppearanceLayer
    outfit: OutfitLayer
    condition: ConditionLayer
    disguise: DisguiseLayer = field(default_factory=DisguiseLayer)
    voice: VoiceLayer = field(default_factory=VoiceLayer)

    def resolved_name(self, observer_id: str = "reader") -> str:
        if self.disguise.active and not self.disguise.is_visible_to(observer_id):
            return self.disguise.facade_name or self.self_layer.canonical_label
        return self.self_layer.canonical_label

    def resolved_appearance_dict(self, observer_id: str = "reader") -> dict[str, str]:
        if self.disguise.active and not self.disguise.is_visible_to(observer_id) and self.disguise.facade_appearance:
            return dict(self.disguise.facade_appearance)
        return self.appearance.to_appearance_dict()

    def resolved_attire(self, observer_id: str = "reader") -> str:
        if self.disguise.active and not self.disguise.is_visible_to(observer_id) and self.disguise.facade_attire:
            return self.disguise.facade_attire
        return self.outfit.description()

    def resolved_condition(self) -> str:
        return self.condition.description()

    def resolved_voice_parameters(self) -> tuple[float, float, str]:
        pitch = self.voice.disguised_pitch_shift if (self.disguise.active and self.voice.disguised_pitch_shift is not None) else self.voice.base_pitch_shift
        return (pitch, self.voice.base_tempo, self.voice.timbre_descriptor)

    def to_character_brief(self, *, lead: bool = False, stated_expression: str = "", observer_id: str = "reader") -> Any:
        from echotales.pipeline.render.compiler import CharacterBrief

        return CharacterBrief(
            name=self.resolved_name(observer_id),
            gender=self.body_epoch.gender,
            age_band=self.body_epoch.age_band,
            age_years=self.body_epoch.age_years,
            appearance=self.resolved_appearance_dict(observer_id),
            attire=self.resolved_attire(observer_id),
            condition=self.resolved_condition(),
            stated_expression=stated_expression,
            lead=lead,
        )


def resolve_character_state(
    store: Store,
    novel_id: str,
    self_id: str,
    story_pos: float,
    *,
    observer_id: str = "reader",
) -> CharacterState:
    """Build a resolved 7-layer `CharacterState` for `self_id` at `story_pos` from the store."""
    from echotales.core.enums import TargetKind

    entity = next((e for e in store.all_selves(novel_id) if e.id == self_id), None)
    canonical_label = entity.canonical_label if entity is not None else self_id
    self_layer = SelfLayer(self_id=self_id, canonical_label=canonical_label)

    bodies = bodies_of(store, self_id)
    active_body_id = f"{self_id}:body1"
    active_interval = None
    if bodies:
        for p_id, p_interval in bodies:
            if p_interval is not None and p_interval.contains(story_pos).is_possible:
                active_body_id, active_interval = p_id, p_interval
                break
        else:
            active_body_id, active_interval = bodies[0]

    standing = standing_values(store, active_body_id)
    raw_attrs = {a.key: a.value for a in store.get_attributes(TargetKind.PERSONA, active_body_id) if a.is_standing}

    gender = standing.get("gender", raw_attrs.get("gender", "unknown"))
    age_band = standing.get("age_band", raw_attrs.get("age_band", "adult"))
    stature = standing.get("build", raw_attrs.get("build", "average"))
    skin = standing.get("skin_tone", raw_attrs.get("skin_tone", "pale"))
    body_epoch = BodyEpochLayer(
        persona_id=active_body_id,
        gender=gender,
        age_band=age_band,
        stature=stature,
        skin_tone=skin,
        interval=active_interval,
    )

    hair_c = standing.get("hair_color", raw_attrs.get("hair_color", "black"))
    hair_s = standing.get("hair_style", raw_attrs.get("hair_style", "topknot"))
    eye_c = standing.get("eye_color", raw_attrs.get("eye_color", "dark brown"))
    scars = [standing["scar"]] if "scar" in standing else ([raw_attrs["scar"]] if "scar" in raw_attrs else [])
    appearance = AppearanceLayer(
        hair_color=hair_c,
        hair_style=hair_s,
        eye_color=eye_c,
        scars=scars,
        build_description=stature,
    )

    attire_val = standing.get("attire", raw_attrs.get("attire", "robes"))
    outfit = OutfitLayer(garments=attire_val)

    cond_val = standing.get("condition", raw_attrs.get("condition", ""))
    condition = ConditionLayer(wounds=[cond_val] if cond_val else [])

    disguise_active = "disguise" in standing or "disguise_alias" in standing
    disguise = DisguiseLayer(
        active=disguise_active,
        facade_name=standing.get("disguise_alias", ""),
        facade_attire=standing.get("disguise_attire", ""),
    )

    voice_id = standing.get("voice_override", raw_attrs.get("voice_override", ""))
    voice = VoiceLayer(speaker_id=voice_id)

    return CharacterState(
        self_layer=self_layer,
        body_epoch=body_epoch,
        appearance=appearance,
        outfit=outfit,
        condition=condition,
        disguise=disguise,
        voice=voice,
    )
