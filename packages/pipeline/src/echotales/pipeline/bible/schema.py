"""Story Bible structured delta schema and snapshot data contracts.

Represents frontier LLM structured extractions from chapters and the point-in-time
bible snapshot consumed by screenplay and asset generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PersonaShiftReason(StrEnum):
    """Why a character's visual appearance or identity shifted."""

    TRANSMIGRATION = "transmigration"
    DISGUISE = "disguise"
    INJURY = "injury"
    AGING = "aging"
    OUTFIT_CHANGE = "outfit_change"
    POWER_UP = "power_up"


@dataclass(slots=True)
class EntityDelta:
    """A new character, faction, or entity introduced in this chapter."""

    self_id: str
    canonical_label: str
    kind: str = "SELF"  # SELF | FACTION | CREATURE
    aliases: list[str] = field(default_factory=list)
    initial_attributes: dict[str, str] = field(default_factory=dict)  # e.g. {"hair_color": "black", "gender": "male"}
    suggested_voice_profile: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "self_id": self.self_id,
            "canonical_label": self.canonical_label,
            "kind": self.kind,
            "aliases": list(self.aliases),
            "initial_attributes": dict(self.initial_attributes),
            "suggested_voice_profile": self.suggested_voice_profile,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityDelta:
        return cls(
            self_id=data["self_id"],
            canonical_label=data["canonical_label"],
            kind=data.get("kind", "SELF"),
            aliases=list(data.get("aliases", [])),
            initial_attributes=dict(data.get("initial_attributes", {})),
            suggested_voice_profile=data.get("suggested_voice_profile"),
        )


@dataclass(slots=True)
class PersonaShiftDelta:
    """A visual body, outfit, or disguise shift for an existing character."""

    self_id: str
    persona_id: str
    reason: PersonaShiftReason
    description: str
    outfit_id: str | None = None
    appearance_overrides: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "self_id": self.self_id,
            "persona_id": self.persona_id,
            "reason": str(self.reason),
            "description": self.description,
            "outfit_id": self.outfit_id,
            "appearance_overrides": dict(self.appearance_overrides),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersonaShiftDelta:
        return cls(
            self_id=data["self_id"],
            persona_id=data["persona_id"],
            reason=PersonaShiftReason(data["reason"]),
            description=data.get("description", ""),
            outfit_id=data.get("outfit_id"),
            appearance_overrides=dict(data.get("appearance_overrides", {})),
        )


@dataclass(slots=True)
class LocationDelta:
    """A setting, building, or room introduced or modified."""

    location_id: str
    canonical_name: str
    description: str
    sub_areas: list[str] = field(default_factory=list)
    ambience_sound: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "sub_areas": list(self.sub_areas),
            "ambience_sound": self.ambience_sound,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LocationDelta:
        return cls(
            location_id=data["location_id"],
            canonical_name=data["canonical_name"],
            description=data.get("description", ""),
            sub_areas=list(data.get("sub_areas", [])),
            ambience_sound=data.get("ambience_sound"),
        )


@dataclass(slots=True)
class BibleDelta:
    """Structured delta extracted from a single chapter by a frontier LLM."""

    novel_id: str
    chapter: float
    new_entities: list[EntityDelta] = field(default_factory=list)
    persona_shifts: list[PersonaShiftDelta] = field(default_factory=list)
    location_deltas: list[LocationDelta] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "chapter": self.chapter,
            "new_entities": [e.to_dict() for e in self.new_entities],
            "persona_shifts": [p.to_dict() for p in self.persona_shifts],
            "location_deltas": [l.to_dict() for l in self.location_deltas],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BibleDelta:
        return cls(
            novel_id=data["novel_id"],
            chapter=float(data["chapter"]),
            new_entities=[EntityDelta.from_dict(e) for e in data.get("new_entities", [])],
            persona_shifts=[PersonaShiftDelta.from_dict(p) for p in data.get("persona_shifts", [])],
            location_deltas=[LocationDelta.from_dict(l) for l in data.get("location_deltas", [])],
            summary=data.get("summary", ""),
        )


@dataclass(slots=True)
class CharacterBibleEntry:
    """A character's active state at a given chapter."""

    self_id: str
    canonical_label: str
    active_persona_id: str
    active_outfit: str | None = None
    aliases: list[str] = field(default_factory=list)
    voice_id: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LocationBibleEntry:
    """A location's canonical appearance and ambience at a given chapter."""

    location_id: str
    canonical_name: str
    description: str
    master_plate_path: str | None = None
    ambience_sound: str | None = None


@dataclass(slots=True)
class StoryBibleSnapshot:
    """A point-in-time snapshot of the Story Bible for a specific chapter."""

    novel_id: str
    chapter: float
    characters: dict[str, CharacterBibleEntry] = field(default_factory=dict)
    locations: dict[str, LocationBibleEntry] = field(default_factory=dict)
    _alias_map: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._build_alias_index()

    def _build_alias_index(self) -> None:
        self._alias_map = {}
        for self_id, char in self.characters.items():
            self._alias_map[char.canonical_label.strip().lower()] = self_id
            for alias in char.aliases:
                self._alias_map[alias.strip().lower()] = self_id

    def resolve_alias(self, text: str) -> str | None:
        """Resolve a name mention or alias against the snapshot's character index."""
        cleaned = text.strip().lower()
        if cleaned in self._alias_map:
            return self._alias_map[cleaned]
        return None

    def get_character(self, self_id: str) -> CharacterBibleEntry | None:
        return self.characters.get(self_id)
