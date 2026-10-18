"""LLM-first speaker attribution with cast and alias knowledge.

Paper benchmark: Michel et al., NAACL 2025 (PDNC benchmark: Llama-3 8B scored 90.6%
attribution accuracy given cast + alias lists, whereas heuristic rule-based attribution
identifies only ~45.5% in EchoTales, open defect 3).

Architecture:
1. Primary: Frontier / 8B+ LLM attribution with bitemporal Story Bible cast & aliases.
2. Fallback: Explicit verb and proximal action heuristics (speakers/attribution.py).
3. Eval metrics: Accuracy %, precision/recall/F1 per character, same-scene collision rate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from echotales.pipeline.bible.schema import StoryBibleSnapshot


@dataclass(slots=True)
class DialogueLine:
    """A quote or spoken span within a scene block."""

    line_index: int
    text: str
    surrounding_context: str = ""
    block_index: int = 0
    chapter: float = 1.0


@dataclass(slots=True)
class SpeakerAttributionResult:
    """Attributed speaker for a line."""

    line_index: int
    speaker_id: str  # self_id, or "NARRATOR" / "ANONYMOUS" / "CHORUS"
    confidence: float = 1.0
    method: str = "llm"  # "llm" | "explicit" | "proximal" | "tiebreak"
    reasoning: str = ""


class AttributionLLM(Protocol):
    def complete(self, prompt: str, system: str | None = None) -> str:
        ...


def build_attribution_prompt(
    lines: list[DialogueLine],
    snapshot: StoryBibleSnapshot,
) -> tuple[str, str]:
    """Generate prompt and system prompt for LLM speaker attribution."""
    system = (
        "You are an expert literary dialogue annotator. Given the following novel scene "
        "and the known cast of characters with their aliases, attribute each numbered dialogue "
        "line to the character who speaks it.\n"
        "Output ONLY a valid JSON object mapping string line numbers to self_id strings.\n"
        "If a line is spoken by the narrator, use 'NARRATOR'. If spoken by an anonymous crowd "
        "or unintroduced background speaker, use 'ANONYMOUS'."
    )

    cast_descriptions: list[str] = []
    for self_id, char in snapshot.characters.items():
        aliases_str = ", ".join(char.aliases) if char.aliases else "none"
        attrs_str = ", ".join(f"{k}={v}" for k, v in char.attributes.items())
        cast_descriptions.append(
            f"- self_id: {self_id} | Name: {char.canonical_label} | Aliases: [{aliases_str}] | Details: {attrs_str}"
        )

    cast_block = "\n".join(cast_descriptions)

    lines_block = "\n\n".join(
        f"Line [{line.line_index}]: \"{line.text}\"\nContext: {line.surrounding_context}"
        for line in lines
    )

    user_prompt = (
        f"### Known Cast List & Aliases\n{cast_block}\n\n"
        f"### Dialogue Lines to Attribute\n{lines_block}\n\n"
        "Attribute each line index to the speaker's self_id. Example JSON format:\n"
        "{\n  \"0\": \"lotm:self:zhou\",\n  \"1\": \"lotm:self:inspector\"\n}"
    )

    return system, user_prompt


def parse_attribution_response(
    raw_response: str,
    lines: list[DialogueLine],
    snapshot: StoryBibleSnapshot,
) -> list[SpeakerAttributionResult]:
    """Parse JSON mapping from LLM output into SpeakerAttributionResult list."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {}

    results: list[SpeakerAttributionResult] = []
    for line in lines:
        str_idx = str(line.line_index)
        assigned = data.get(str_idx)
        if assigned:
            # Resolve if LLM returned a name/alias instead of self_id
            resolved = snapshot.resolve_alias(assigned) or assigned
            results.append(
                SpeakerAttributionResult(
                    line_index=line.line_index,
                    speaker_id=resolved,
                    confidence=0.95,
                    method="llm",
                )
            )
        else:
            results.append(
                SpeakerAttributionResult(
                    line_index=line.line_index,
                    speaker_id="ANONYMOUS",
                    confidence=0.0,
                    method="fallback",
                )
            )

    return results


@dataclass(slots=True)
class AttributionMetrics:
    """Benchmark evaluation results against ground truth."""

    total_lines: int
    correct_lines: int
    accuracy: float
    per_speaker_correct: dict[str, int] = field(default_factory=dict)
    per_speaker_total: dict[str, int] = field(default_factory=dict)
    confusion_pairs: list[tuple[str, str, int]] = field(default_factory=list)


def evaluate_speaker_attribution(
    gold_map: dict[int, str],
    predicted: list[SpeakerAttributionResult],
) -> AttributionMetrics:
    """Evaluate predicted speaker attributions against gold annotations."""
    total = len(gold_map)
    if total == 0:
        return AttributionMetrics(total_lines=0, correct_lines=0, accuracy=0.0)

    correct = 0
    per_speaker_correct: dict[str, int] = {}
    per_speaker_total: dict[str, int] = {}
    confusions: dict[tuple[str, str], int] = {}

    pred_map = {p.line_index: p.speaker_id for p in predicted}

    for line_idx, gold_speaker in gold_map.items():
        per_speaker_total[gold_speaker] = per_speaker_total.get(gold_speaker, 0) + 1
        pred_speaker = pred_map.get(line_idx, "UNATTRIBUTED")
        if pred_speaker == gold_speaker:
            correct += 1
            per_speaker_correct[gold_speaker] = per_speaker_correct.get(gold_speaker, 0) + 1
        else:
            pair = (gold_speaker, pred_speaker)
            confusions[pair] = confusions.get(pair, 0) + 1

    confusion_list = [(g, p, count) for (g, p), count in sorted(confusions.items(), key=lambda x: x[1], reverse=True)]

    return AttributionMetrics(
        total_lines=total,
        correct_lines=correct,
        accuracy=correct / total,
        per_speaker_correct=per_speaker_correct,
        per_speaker_total=per_speaker_total,
        confusion_pairs=confusion_list,
    )
