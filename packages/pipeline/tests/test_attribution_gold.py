"""Tests for gold speaker attribution benchmark dataset and evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path


from echotales.core.models import CharacterBibleEntry, StoryBibleSnapshot
from echotales.pipeline.voice.attribution import (
    DialogueLine,
    SpeakerAttributionResult,
    build_attribution_prompt,
    evaluate_speaker_attribution,
    parse_attribution_response,
)

GOLD_PATH = Path("data/eval/attribution/showcase_ch1_gold.json")


def test_gold_dataset_format_and_coverage() -> None:
    assert GOLD_PATH.exists(), "Gold dataset must exist"
    data = json.loads(GOLD_PATH.read_text(encoding="utf-8"))

    assert data["novel_id"] == "hound"
    assert data["chapter"] == 1.0
    assert data["total_lines"] == 69
    assert len(data["lines"]) == 69
    assert "char:holmes" in data["characters"]
    assert "char:watson" in data["characters"]
    assert "char:mortimer" in data["characters"]

    # Every line has non-empty text, valid speaker_id, and context
    for line in data["lines"]:
        assert line["text"].strip()
        assert line["speaker_id"] in ("char:holmes", "char:watson", "char:mortimer")
        assert "surrounding_context" in line


def test_evaluate_speaker_attribution_metrics() -> None:
    gold_map = {0: "char:holmes", 1: "char:watson", 2: "char:holmes"}

    # Perfect prediction
    perfect = [
        SpeakerAttributionResult(line_index=0, speaker_id="char:holmes"),
        SpeakerAttributionResult(line_index=1, speaker_id="char:watson"),
        SpeakerAttributionResult(line_index=2, speaker_id="char:holmes"),
    ]
    m_perf = evaluate_speaker_attribution(gold_map, perfect)
    assert m_perf.accuracy == 1.0
    assert m_perf.correct_lines == 3
    assert len(m_perf.confusion_pairs) == 0

    # With one confusion (Watson predicted as Holmes)
    imperfect = [
        SpeakerAttributionResult(line_index=0, speaker_id="char:holmes"),
        SpeakerAttributionResult(line_index=1, speaker_id="char:holmes"),  # wrong!
        SpeakerAttributionResult(line_index=2, speaker_id="char:holmes"),
    ]
    m_imp = evaluate_speaker_attribution(gold_map, imperfect)
    assert round(m_imp.accuracy, 2) == 0.67
    assert m_imp.correct_lines == 2
    assert len(m_imp.confusion_pairs) == 1
    gold_spk, pred_spk, count = m_imp.confusion_pairs[0]
    assert gold_spk == "char:watson"
    assert pred_spk == "char:holmes"
    assert count == 1


def test_build_and_parse_with_gold_snapshot() -> None:
    snapshot = StoryBibleSnapshot(
        novel_id="hound",
        chapter=1.0,
        characters={
            "char:holmes": CharacterBibleEntry(
                self_id="char:holmes",
                canonical_label="Sherlock Holmes",
                active_persona_id="char:holmes:body1",
                aliases=["Holmes", "Mr. Holmes"],
            ),
            "char:watson": CharacterBibleEntry(
                self_id="char:watson",
                canonical_label="Dr. John Watson",
                active_persona_id="char:watson:body1",
                aliases=["Watson", "Dr. Watson"],
            ),
        },
    )

    lines = [
        DialogueLine(line_index=0, text="Well, Watson, what do you make of it?"),
        DialogueLine(line_index=1, text="How did you know what I was doing?"),
    ]

    _system, user_prompt = build_attribution_prompt(lines, snapshot)
    assert "Sherlock Holmes" in user_prompt
    assert "Dr. John Watson" in user_prompt
    assert "Line [0]" in user_prompt

    # Simulated LLM response returning alias "Holmes" instead of self_id
    raw_response = '{"0": "Holmes", "1": "char:watson"}'
    results = parse_attribution_response(raw_response, lines, snapshot)
    assert len(results) == 2
    # Alias "Holmes" resolved to self_id
    assert results[0].speaker_id == "char:holmes"
    assert results[1].speaker_id == "char:watson"
