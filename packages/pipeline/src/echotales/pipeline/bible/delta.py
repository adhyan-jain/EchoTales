"""Frontier LLM structured Story Bible delta extractor.

Extracts structured updates (new entities, persona body/outfit shifts, location plates)
from raw novel chapter text using strict JSON conformity to BibleDelta.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from echotales.core.models import StoryBibleSnapshot
from echotales.pipeline.bible.schema import (
    BibleDelta,
    EntityDelta,
    LocationDelta,
)


class BibleExtractorLLM(Protocol):
    """Protocol for LLM client handling Story Bible extraction."""

    def complete(self, prompt: str, system: str | None = None) -> str:
        ...


def build_bible_delta_prompt(
    novel_id: str,
    chapter: float,
    chapter_text: str,
    prior_snapshot: StoryBibleSnapshot | None = None,
) -> tuple[str, str]:
    """Generate system and user prompts for frontier LLM BibleDelta extraction."""
    system = (
        "You are an expert narrative continuity director and world-building archivist. "
        "Analyze the provided chapter text and extract structured Story Bible updates.\n"
        "Output ONLY a valid JSON object matching the BibleDelta specification:\n"
        "{\n"
        "  \"novel_id\": str,\n"
        "  \"chapter\": float,\n"
        "  \"new_entities\": [\n"
        "    {\n"
        "      \"self_id\": str (e.g. \"novel:self:name\"),\n"
        "      \"canonical_label\": str,\n"
        "      \"kind\": \"SELF\" | \"FACTION\" | \"CREATURE\",\n"
        "      \"aliases\": [str],\n"
        "      \"initial_attributes\": {\"gender\": str, \"hair\": str, ...},\n"
        "      \"suggested_voice_profile\": str\n"
        "    }\n"
        "  ],\n"
        "  \"persona_shifts\": [\n"
        "    {\n"
        "      \"self_id\": str,\n"
        "      \"persona_id\": str,\n"
        "      \"reason\": \"transmigration\" | \"disguise\" | \"injury\" | \"aging\" | \"outfit_change\" | \"power_up\",\n"
        "      \"description\": str,\n"
        "      \"outfit_id\": str | null,\n"
        "      \"appearance_overrides\": dict\n"
        "    }\n"
        "  ],\n"
        "  \"location_deltas\": [\n"
        "    {\n"
        "      \"location_id\": str,\n"
        "      \"canonical_name\": str,\n"
        "      \"description\": str,\n"
        "      \"sub_areas\": [str],\n"
        "      \"ambience_sound\": str | null\n"
        "    }\n"
        "  ],\n"
        "  \"summary\": str\n"
        "}"
    )

    known_cast_str = "None (first chapter)"
    if prior_snapshot and prior_snapshot.characters:
        lines = []
        for sid, char in prior_snapshot.characters.items():
            lines.append(f"- {sid}: {char.canonical_label} (aliases: {', '.join(char.aliases)})")
        known_cast_str = "\n".join(lines)

    user_prompt = (
        f"Novel ID: {novel_id}\n"
        f"Chapter: {chapter}\n\n"
        f"### Currently Known Cast (Do not re-add as new_entities unless alias/shift):\n"
        f"{known_cast_str}\n\n"
        f"### Chapter Text\n"
        f"{chapter_text[:12000]}\n\n"
        f"Extract all new entities, persona shifts, and locations as a strict JSON BibleDelta."
    )

    return system, user_prompt


def parse_bible_delta_response(raw_json: str, novel_id: str, chapter: float) -> BibleDelta:
    """Parse raw LLM response into a typed BibleDelta."""
    cleaned = raw_json.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {"novel_id": novel_id, "chapter": chapter}

    # Ensure novel_id and chapter are consistent
    data["novel_id"] = data.get("novel_id") or novel_id
    data["chapter"] = float(data.get("chapter", chapter))

    return BibleDelta.from_dict(data)


_HONORIFIC = r"(?:Mr|Mrs|Miss|Ms|Dr|Sir|Lady|Lord|Captain|Inspector)\.?"
_NAME_RE = re.compile(rf"\b(?:{_HONORIFIC}\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
_PLACE_RE = re.compile(r"\b((?:\d+[A-Z]?\s+)?[A-Z][a-z]+\s+(?:Street|Road|Lane|Square|Hall|House|Inn|Bridge))\b")
_NOT_NAMES = {"The", "A", "An", "He", "She", "It", "They", "I", "In", "On", "At", "But", "And"}


def _candidate_names(text: str) -> list[str]:
    found: list[str] = []
    for m in _NAME_RE.finditer(text):
        words = [w for w in m.group(1).split() if w not in _NOT_NAMES]
        name = " ".join(words)
        if len(words) >= 2 and not _PLACE_RE.fullmatch(name) and name not in found:
            found.append(name)
    return found


def _candidate_places(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _PLACE_RE.finditer(text)))


def heuristic_extract_bible_delta(
    novel_id: str,
    chapter: float,
    chapter_text: str,
    prior_snapshot: StoryBibleSnapshot | None = None,
) -> BibleDelta:
    """Deterministic offline fallback for CI and stub runs."""
    new_entities: list[EntityDelta] = []
    location_deltas: list[LocationDelta] = []

    # Offline stand-in for the LLM: any run of two or more capitalised words is a candidate name, any "<Name> Street /
    # Road / Square ..." a place. It was a list of Holmes, Watson and Klein, so it only ever worked on those books.
    for name in _candidate_names(chapter_text):
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if prior_snapshot and prior_snapshot.resolve_alias(name):
            continue
        new_entities.append(
            EntityDelta(
                self_id=f"{novel_id}:char:{slug}",
                canonical_label=name,
                kind="SELF",
                aliases=[name.split()[-1]],
                initial_attributes={},
            )
        )

    for place in _candidate_places(chapter_text):
        slug = re.sub(r"[^a-z0-9]+", "_", place.lower()).strip("_")
        loc_id = f"{novel_id}:loc:{slug}"
        if not prior_snapshot or loc_id not in prior_snapshot.locations:
            location_deltas.append(LocationDelta(location_id=loc_id, canonical_name=place, description=""))

    return BibleDelta(
        novel_id=novel_id,
        chapter=chapter,
        new_entities=new_entities,
        persona_shifts=[],
        location_deltas=location_deltas,
        summary=f"Automated extraction for {novel_id} chapter {chapter}.",
    )


def extract_bible_delta(
    novel_id: str,
    chapter: float,
    chapter_text: str,
    llm: BibleExtractorLLM | None = None,
    prior_snapshot: StoryBibleSnapshot | None = None,
) -> BibleDelta:
    """Extract Story Bible updates using provided LLM or deterministic fallback."""
    if llm is not None:
        system, user_prompt = build_bible_delta_prompt(
            novel_id, chapter, chapter_text, prior_snapshot
        )
        response = llm.complete(user_prompt, system=system)
        return parse_bible_delta_response(response, novel_id, chapter)

    return heuristic_extract_bible_delta(novel_id, chapter, chapter_text, prior_snapshot)
