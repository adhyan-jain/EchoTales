"""Unit tests for scripts/review/llm_annotate.py."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure scripts/review is importable
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "review"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from llm_annotate import (
    VALID_LABELS,
    annotate_dataset,
    build_system_prompt,
    build_user_prompt,
    estimate_cost,
    validate_annotations,
)


def test_build_system_prompt() -> None:
    prompt_mentions = build_system_prompt("mentions")
    assert "predicted_entity" in prompt_mentions
    assert "'correct'" in prompt_mentions
    assert "'incorrect'" in prompt_mentions
    assert "'unresolved'" in prompt_mentions
    assert "untrusted fiction data" in prompt_mentions

    prompt_hardcases = build_system_prompt("hardcases")
    assert "reference_set_decision" in prompt_hardcases
    assert "untrusted fiction data" in prompt_hardcases


def test_build_user_prompt() -> None:
    items = [
        {
            "sample_id": "R001",
            "chapter": "1",
            "category": "easy_name",
            "mention": "Fang Yuan",
            "predicted_entity": "Fang Yuan",
            "candidate_entities": "Fang Yuan",
            "reference_set_decision": "Fang Yuan",
            "source_text": "Fang Yuan looked up at the moon.",
        }
    ]
    user_prompt = build_user_prompt(items, sheet_type="mentions")
    assert "R001" in user_prompt
    assert "Fang Yuan" in user_prompt
    assert "<novel_excerpt sample_id=\"R001\">" in user_prompt
    assert "</novel_excerpt>" in user_prompt


def test_validate_annotations_valid() -> None:
    raw_json = {
        "annotations": [
            {
                "sample_id": "R001",
                "reviewer_label": "correct",
                "reviewer_notes": "Fang Yuan is the protagonist described.",
            },
            {
                "sample_id": "R002",
                "reviewer_label": "incorrect",
                "reviewer_notes": "Refers to Fang Zheng, not Fang Yuan.",
            },
        ]
    }
    expected_ids = ["R001", "R002"]
    valid_dict, errors = validate_annotations(raw_json, expected_ids)
    assert len(errors) == 0
    assert valid_dict["R001"] == ("correct", "Fang Yuan is the protagonist described.")
    assert valid_dict["R002"] == ("incorrect", "Refers to Fang Zheng, not Fang Yuan.")


def test_validate_annotations_malformed_and_missing() -> None:
    raw_json = {
        "annotations": [
            {
                "sample_id": "R001",
                "reviewer_label": "invalid_label",
                "reviewer_notes": "Note.",
            },
            {
                "sample_id": "UNKNOWN_ID",
                "reviewer_label": "correct",
                "reviewer_notes": "Note.",
            },
        ]
    }
    expected_ids = ["R001", "R002"]
    valid_dict, errors = validate_annotations(raw_json, expected_ids)
    # Invalid label should be caught and defaulted to unresolved
    assert valid_dict["R001"][0] == "unresolved"
    # Missing R002 should be marked unresolved
    assert valid_dict["R002"][0] == "unresolved"
    # Errors should record the issues
    assert any("Invalid label" in e for e in errors)
    assert any("Unexpected sample_id" in e for e in errors)
    assert any("Missing annotations" in e for e in errors)


def test_estimate_cost() -> None:
    cost = estimate_cost("gpt-5.6-luna", 1000, 500)
    # 1000 * 0.25/1M + 500 * 1.00/1M = 0.00025 + 0.00050 = 0.00075
    assert abs(cost - 0.00075) < 1e-6


def test_annotate_dataset_dry_run(tmp_path: Path) -> None:
    csv_file = tmp_path / "sample.csv"
    out_file = tmp_path / "sample_annotated.csv"

    fieldnames = [
        "sample_id", "chapter", "source_text", "mention", "predicted_entity",
        "candidate_entities", "system_decision", "reference_set_decision",
        "category", "reviewer_label", "reviewer_notes"
    ]
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "sample_id": "R001", "chapter": "1", "source_text": "text", "mention": "FY",
            "predicted_entity": "FY", "candidate_entities": "FY", "system_decision": "LINK",
            "reference_set_decision": "FY", "category": "easy_name", "reviewer_label": "",
            "reviewer_notes": ""
        })

    res = annotate_dataset(csv_file, out_file, dry_run=True)
    assert res["status"] == "dry_run"
    assert res["items_to_annotate"] == 1
    assert res["estimated_cost_usd"] < 0.01


def test_annotate_dataset_refuses_overwrite(tmp_path: Path) -> None:
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("sample_id,reviewer_label,reviewer_notes\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot overwrite"):
        annotate_dataset(csv_file, csv_file, dry_run=True)


def test_annotate_dataset_mock_execution(tmp_path: Path) -> None:
    csv_file = tmp_path / "sample.csv"
    out_file = tmp_path / "sample_out.csv"

    fieldnames = [
        "sample_id", "chapter", "source_text", "mention", "predicted_entity",
        "candidate_entities", "system_decision", "reference_set_decision",
        "category", "reviewer_label", "reviewer_notes"
    ]
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i in range(1, 4):
            writer.writerow({
                "sample_id": f"R{i:03d}", "chapter": "1", "source_text": f"text {i}", "mention": "FY",
                "predicted_entity": "FY", "candidate_entities": "FY", "system_decision": "LINK",
                "reference_set_decision": "FY", "category": "easy_name", "reviewer_label": "",
                "reviewer_notes": ""
            })

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "annotations": [
            {"sample_id": "R001", "reviewer_label": "correct", "reviewer_notes": "Entity matches text."},
            {"sample_id": "R002", "reviewer_label": "incorrect", "reviewer_notes": "Entity is wrong."},
            {"sample_id": "R003", "reviewer_label": "unresolved", "reviewer_notes": "Ambiguous."},
        ]
    })
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 250
    mock_resp.usage.completion_tokens = 60
    mock_resp.usage.total_tokens = 310
    mock_client.chat.completions.create.return_value = mock_resp

    res = annotate_dataset(csv_file, out_file, client=mock_client)
    assert res["status"] == "completed"
    assert res["total_annotated"] == 3
    assert out_file.exists()

    with out_file.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 3
        assert rows[0]["reviewer_label"] == "correct"
        assert rows[1]["reviewer_label"] == "incorrect"
        assert rows[2]["reviewer_label"] == "unresolved"
