"""Public benchmark scoring on tiny fixtures: deterministic, no book text, no model.

Why fixtures and not the real references: the scorers must be checkable by hand. Each expected number below is
computed on paper from the fixture, so a scorer change that moves a number fails here with a reason.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.public import check, refs, score, sources

TEXT = 'He said, "Good day to you." She replied, "And to you, sir." Nobody spoke after.'


def _line(text: str, speaker: str, aliases: list[str] | None = None, *, checked: bool = False) -> dict:
    offset = TEXT.index(text)
    return {
        "id": f"l{offset}", "offset": offset, "length": len(text), "text_sha256": sources.slice_hash(text),
        "speaker": speaker, "aliases": aliases or [], "checked_by_human": checked,
    }


# ---- sources ----

def test_slice_hash_ignores_rewrapping() -> None:
    assert sources.slice_hash("a  b\nc") == sources.slice_hash("a b c")


def test_verify_slice_detects_a_different_text() -> None:
    item = _line("Good day to you.", "Mr. A")
    assert sources.verify_slice(TEXT, item)
    assert not sources.verify_slice(TEXT.replace("Good", "Evil"), item)
    assert not sources.verify_slice("short", item)


def test_gutenberg_txt_canonical_strips_licence_and_normalises_newlines(tmp_path: Path) -> None:
    raw = "header\r\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\r\nBody line.\r\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\r\nlicence"
    p = tmp_path / "pg1.txt"
    p.write_bytes(raw.encode())
    assert sources.canonical_gutenberg_txt(p) == "Body line."


def test_locate_reports_where_it_looked(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="pride-and-prejudice"):
        sources.locate("pride-and-prejudice", tmp_path)


# ---- speaker attribution ----

def test_speaker_score_counts_missing_and_alias_matches() -> None:
    items = [_line("Good day to you.", "Mr. Darcy", ["Darcy", "Mr Darcy"]), _line("And to you, sir.", "Elizabeth Bennet", ["Elizabeth", "Lizzy"])]
    pred = {items[0]["id"]: "darcy"}  # alias, case-insensitive; the second line has no prediction
    out = score.score_speaker(items, pred)
    assert out["lines"] == 2 and out["answered"] == 1 and out["correct"] == 1
    assert out["accuracy"] == 0.5 and out["accuracy_on_answered"] == 1.0
    assert out["per_speaker"]["Elizabeth Bennet"] == {"lines": 1, "correct": 0}


def test_speaker_score_wrong_answer() -> None:
    items = [_line("Good day to you.", "Mr. Darcy")]
    assert score.score_speaker(items, {items[0]["id"]: "Bingley"})["correct"] == 0


def test_speaker_prediction_for_unknown_line_is_reported_not_scored() -> None:
    items = [_line("Good day to you.", "Mr. Darcy")]
    out = score.score_speaker(items, {items[0]["id"]: "Mr. Darcy", "nope": "X"})
    assert out["unmatched_predictions"] == ["nope"] and out["correct"] == 1


# ---- cross-panel identity ----

GOLD_PANELS = {"p1": ["Pepper", "Carrot"], "p2": ["Pepper"], "p3": ["Carrot"], "p4": []}


def test_identity_perfect_and_empty_panels() -> None:
    out = score.score_identity(GOLD_PANELS, GOLD_PANELS)
    assert out["macro_f1"] == 1.0 and out["panel_exact_match"] == 1.0


def test_identity_partial() -> None:
    pred = {"p1": ["Pepper"], "p2": ["Pepper", "Carrot"], "p3": ["Carrot"], "p4": []}
    out = score.score_identity(GOLD_PANELS, pred)
    # Pepper: tp 2, fp 0, fn 0 -> 1.0.  Carrot: tp 1, fp 1, fn 1 -> p = r = 0.5, f1 = 0.5
    assert out["per_character"]["Pepper"]["f1"] == 1.0
    assert out["per_character"]["Carrot"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2}
    assert out["macro_f1"] == 0.75
    assert out["panel_exact_match"] == 0.5  # p3 and p4 exact


def test_identity_missing_panel_counts_as_nobody_found() -> None:
    out = score.score_identity(GOLD_PANELS, {"p1": ["Pepper", "Carrot"]})
    assert out["panels_without_prediction"] == ["p2", "p3", "p4"]
    assert out["per_character"]["Carrot"]["recall"] == 0.5


# ---- scene fidelity ----

SCENE = {
    "id": "s1",
    "required": [
        {"element": "lead", "any_of": ["pepper", "young witch"]},
        {"element": "cat", "any_of": ["cat", "carrot"]},
        {"element": "cauldron", "any_of": ["cauldron"]},
    ],
    "forbidden": [{"element": "outdoors", "any_of": ["meadow", "street"]}],
}


def test_scene_fidelity_whole_words_only() -> None:
    out = score.score_scene(SCENE, "Pepper stirs the cauldron while a category of potions waits")
    assert out["satisfied"] == ["lead", "cauldron"]  # "category" must not satisfy "cat"
    assert out["missing"] == ["cat"] and out["score"] == pytest.approx(2 / 3)
    assert out["forbidden_hit"] == []


def test_scene_fidelity_forbidden_is_reported_separately() -> None:
    out = score.score_scene(SCENE, "A young witch and Carrot by the cauldron in a meadow")
    assert out["score"] == 1.0 and out["forbidden_hit"] == ["outdoors"]


def test_scene_fidelity_aggregate() -> None:
    other = {"id": "s2", "required": [{"element": "x", "any_of": ["x"]}], "forbidden": []}
    out = score.score_scenes([SCENE, other], {"s1": "pepper cat cauldron", "s2": ""})
    assert out["mean_score"] == 0.5 and out["scenes_forbidden_hit"] == 0


# ---- references and the human-check state ----

def _ref_file(tmp_path: Path, items: list[dict]) -> Path:
    p = tmp_path / "speaker__x.json"
    p.write_text(json.dumps({"schema": 1, "task": "speaker", "source": {"id": "x"}, "drafted_by": "model", "items": items}))
    return p


def test_status_never_calls_unchecked_references_verified(tmp_path: Path) -> None:
    p = _ref_file(tmp_path, [_line("Good day to you.", "A"), _line("And to you, sir.", "B", checked=True)])
    st = refs.status(refs.load(p))
    assert st == {"items": 2, "checked": 1, "unchecked": 1, "fully_checked": False}
    assert "NOT human-verified" in refs.banner(st)


def test_validate_rejects_a_reference_that_claims_a_check_it_has_no_record_of(tmp_path: Path) -> None:
    item = _line("Good day to you.", "A", checked=True)  # no checked_on
    with pytest.raises(ValueError, match="checked_on"):
        refs.validate(refs.load(_ref_file(tmp_path, [item])))


# ---- the check walker ----

def test_check_walk_records_accept_edit_and_skip(tmp_path: Path) -> None:
    items = [_line("Good day to you.", "A"), _line("And to you, sir.", "B"), _line("Nobody spoke after.", "C")]
    path = _ref_file(tmp_path, items)
    answers = iter(["a", "e", "Dr. Z", "s"])
    out_lines: list[str] = []
    changed = check.walk(path, TEXT, ask=lambda _prompt: next(answers), say=out_lines.append, today="2026-11-20")
    doc = refs.load(path)
    first, second, third = doc["items"]
    assert changed == 2
    assert first["checked_by_human"] is True and first["checked_on"] == "2026-11-20" and first["speaker"] == "A"
    assert second["speaker"] == "Dr. Z" and second["edited_from"] == "B" and second["checked_by_human"] is True
    assert third["checked_by_human"] is False
    assert any("Good day to you." in line for line in out_lines)  # the text is shown at the prompt, never written to the file
    assert "Good day" not in path.read_text()


def test_check_walk_refuses_when_the_local_text_differs(tmp_path: Path) -> None:
    path = _ref_file(tmp_path, [_line("Good day to you.", "A")])
    with pytest.raises(ValueError, match="does not match"):
        check.walk(path, TEXT.replace("Good", "Evil"), ask=lambda _p: "a", say=lambda _s: None, today="2026-11-20")


def test_check_walk_quit_stops_early(tmp_path: Path) -> None:
    path = _ref_file(tmp_path, [_line("Good day to you.", "A"), _line("And to you, sir.", "B")])
    answers = iter(["a", "q"])
    assert check.walk(path, TEXT, ask=lambda _p: next(answers), say=lambda _s: None, today="2026-11-20") == 1
