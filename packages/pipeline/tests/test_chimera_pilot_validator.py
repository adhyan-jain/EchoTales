"""The CHIMERA pilot validator must not let a model or a tampered row pass as human.

Synthetic rows only: no novel text and no real sheet is read.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "chimera" / "validate_pilot_sheet.py"


@pytest.fixture(scope="module")
def v():
    spec = importlib.util.spec_from_file_location("validate_pilot_sheet", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def row(i="CP-001", **kw):
    base = dict(
        item_id=i, batch="1", novel="n", chapter="1.0", mention_offset="5", mention_surface="X",
        source_window="a [[X]] b", candidates="A. One [aaaa] | B. Two [bbbb]",
        reader_warranted="", reader_evidence="", omniscient_id="", omniscient_evidence="",
        reveal_chapter="", confidence_1to3="", minutes_spent="", notes="", annotator="", provenance="",
    )
    base.update(kw)
    return base


def good(i="CP-001", **kw):
    return row(i, reader_warranted="A", omniscient_id="B", confidence_1to3="2", minutes_spent="6",
               annotator="Dana Owner", provenance="HUMAN", **kw)


def errs(v, rows, frozen=None):
    return v.validate(rows, {r["item_id"] for r in rows}, frozen)[0]


def test_clean_labelled_and_unlabelled_rows_pass(v):
    assert errs(v, [good("CP-001"), row("CP-002")]) == []


@pytest.mark.parametrize("name", ["", "   ", "gpt-5.6-luna", "claude-opus-5", "Qwen2.5 7B", "gold-auto-builder", "auto", "my script"])
def test_blank_or_model_annotator_is_rejected(v, name):
    r = good()
    r["annotator"] = name
    assert any("annotator" in e for e in errs(v, [r]))


def test_provenance_must_be_exactly_human(v):
    r = good()
    r["provenance"] = "model"
    assert any("provenance" in e for e in errs(v, [r]))


def test_out_of_range_candidate_letter_is_rejected_but_free_text_and_specials_pass(v):
    r = good()
    r["reader_warranted"] = "Z"
    assert any("reader_warranted" in e for e in errs(v, [r]))
    for ok in ("NEW", "UNDETERMINED", "NOT_AN_ENTITY", "Gu Yue Bo"):
        r = good()
        r["omniscient_id"] = ok
        assert errs(v, [r]) == []


@pytest.mark.parametrize("col,val", [("confidence_1to3", "4"), ("confidence_1to3", ""), ("minutes_spent", "0"), ("minutes_spent", "abc")])
def test_confidence_and_minutes_are_checked(v, col, val):
    r = good()
    r[col] = val
    assert any(col in e for e in errs(v, [r]))


def test_item_ids_must_match_the_key(v):
    rows = [good("CP-001")]
    errors, _ = v.validate(rows, {"CP-001", "CP-002"}, None)
    assert any("differ from the key" in e for e in errors)


def test_editing_a_frozen_column_is_detected(v):
    rows = [good("CP-001"), row("CP-002")]
    frozen = v.frozen_hash(rows)
    assert errs(v, rows, frozen) == []
    rows[0]["source_window"] = "a [[Y]] b"
    assert any("frozen item columns" in e for e in errs(v, rows, frozen))


def test_partially_filled_row_counts_as_labelled_and_must_be_complete(v):
    r = row(reader_warranted="A")
    assert errs(v, [r]) != []
