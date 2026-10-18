"""Tests for LLM-first speaker attribution and benchmark evaluator."""

from __future__ import annotations

import pytest

from echotales.pipeline.bible.schema import CharacterBibleEntry, StoryBibleSnapshot
from echotales.pipeline.voice.attribution import (
    DialogueLine,
    SpeakerAttributionResult,
    build_attribution_prompt,
    evaluate_speaker_attribution,
    parse_attribution_response,
)


def _sample_snapshot() -> StoryBibleSnapshot:
    return StoryBibleSnapshot(
        novel_id="lotm",
        chapter=1.0,
        characters={
            "lotm:self:zhou": CharacterBibleEntry(
                self_id="lotm:self:zhou",
                canonical_label="Zhou Mingrui",
                active_persona_id="lotm:self:zhou:body1",
                aliases=["Klein", "Klein Moretti"],
                attributes={"role": "transmigrator", "gender": "male"},
            ),
            "lotm:self:melissa": CharacterBibleEntry(
                self_id="lotm:self:melissa",
                canonical_label="Melissa Moretti",
                active_persona_id="lotm:self:melissa:body1",
                aliases=["Melissa"],
                attributes={"role": "sister", "gender": "female"},
            ),
        },
    )


def test_build_attribution_prompt() -> None:
    snapshot = _sample_snapshot()
    lines = [
        DialogueLine(
            line_index=0,
            text="Klein, breakfast is ready.",
            surrounding_context="A young girl with dark hair called from the kitchen.",
        ),
        DialogueLine(
            line_index=1,
            text="I'll be right there.",
            surrounding_context="Zhou rubbed his aching forehead and replied.",
        ),
    ]

    system, user_prompt = build_attribution_prompt(lines, snapshot)

    assert "Zhou Mingrui" in user_prompt
    assert "Melissa Moretti" in user_prompt
    assert "Klein, breakfast is ready." in user_prompt
    assert "I'll be right there." in user_prompt
    assert "JSON" in system


def test_parse_attribution_response() -> None:
    snapshot = _sample_snapshot()
    lines = [
        DialogueLine(line_index=0, text="Klein, breakfast is ready."),
        DialogueLine(line_index=1, text="I'll be right there."),
    ]

    # Model returned alias "Melissa" for line 0 and full self_id for line 1
    raw_response = '```json\n{"0": "Melissa", "1": "lotm:self:zhou"}\n```'

    results = parse_attribution_response(raw_response, lines, snapshot)

    assert len(results) == 2
    assert results[0].speaker_id == "lotm:self:melissa"  # resolved from alias "Melissa"
    assert results[1].speaker_id == "lotm:self:zhou"


def test_evaluate_speaker_attribution() -> None:
    gold = {
        0: "lotm:self:melissa",
        1: "lotm:self:zhou",
        2: "lotm:self:benson",
    }
    predicted = [
        SpeakerAttributionResult(line_index=0, speaker_id="lotm:self:melissa"),
        SpeakerAttributionResult(line_index=1, speaker_id="lotm:self:zhou"),
        SpeakerAttributionResult(line_index=2, speaker_id="lotm:self:zhou"),  # Error: predicted zhou instead of benson
    ]

    metrics = evaluate_speaker_attribution(gold, predicted)

    assert metrics.total_lines == 3
    assert metrics.correct_lines == 2
    assert abs(metrics.accuracy - 2 / 3) < 0.001
    assert ("lotm:self:benson", "lotm:self:zhou", 1) in metrics.confusion_pairs
