"""The committed public-benchmark reference files: valid, text-free, honest about being unchecked, and aligned with the
local copies of the public-domain sources when those are present (they are gitignored, so CI skips that half)."""
from __future__ import annotations

from pathlib import Path

import pytest

from eval.public import refs, score, sources

REPO = Path(__file__).resolve().parents[3]
BENCH = REPO / "data" / "eval" / "benchmark"
RAW = REPO / "data" / "raw"


def test_committed_references_are_valid_and_carry_no_text() -> None:
    files = refs.find(BENCH)
    assert {p.name.split("__")[0] for p in files} == {"speaker", "identity", "scene"}
    for path in files:
        doc = refs.load(path)
        refs.validate(doc)
        for item in doc["items"]:
            # offsets and hashes only: a "text" field would be book text in the repository
            assert "text" not in item and "quote" not in item, (path.name, item["id"])
        st = refs.status(doc)
        assert st["fully_checked"] or "NOT human-verified" in refs.banner(st)


def test_committed_references_score_perfectly_against_themselves() -> None:
    """A scorer that cannot give the reference itself 1.0 is broken, whatever it gives a real system."""
    for path in refs.find(BENCH):
        doc = refs.load(path)
        if doc["task"] == "speaker":
            assert score.score_speaker(doc["items"], {i["id"]: i["speaker"] for i in doc["items"]})["accuracy"] == 1.0
        elif doc["task"] == "identity":
            gold = {i["panel"]: i["characters"] for i in doc["items"]}
            assert score.score_identity(gold, gold)["macro_f1"] == 1.0
        else:
            descriptions = {i["id"]: " ".join(r["any_of"][0] for r in i["required"]) for i in doc["items"]}
            out = score.score_scenes(doc["items"], descriptions)
            assert out["mean_score"] == 1.0 and out["scenes_forbidden_hit"] == 0, path.name


def test_score_cli_prints_the_unverified_banner(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    from eval.public.cli import main

    ref = BENCH / "identity__pepper-carrot.json"
    gold = {i["panel"]: i["characters"] for i in refs.load(ref)["items"]}
    preds = tmp_path / "p.json"
    preds.write_text(json.dumps(gold))
    assert main(["score", "--reference", str(ref), "--predictions", str(preds)]) == 0
    cap = capsys.readouterr()
    assert json.loads(cap.out)["macro_f1"] == 1.0
    assert "NOT human-verified" in cap.err and "NOT human-verified" in json.loads(cap.out)["reference"]["banner"]


@pytest.mark.skipif(not (RAW / "gutenberg" / "pride-and-prejudice.epub").exists(), reason="local Pride and Prejudice not present")
def test_pride_and_prejudice_offsets_match_the_local_copy() -> None:
    canonical = sources.canonical_text("pride-and-prejudice", RAW)
    for name in ("speaker__pride-and-prejudice.json", "scene__pride-and-prejudice.json"):
        assert all(sources.verify_slice(canonical, i) for i in refs.load(BENCH / name)["items"]), name


@pytest.mark.skipif(not (RAW / "pd_gutenberg" / "pg1661.txt").exists(), reason="local Sherlock Holmes text not present")
def test_sherlock_offsets_match_the_local_copy() -> None:
    canonical = sources.canonical_text("sherlock-holmes-adventures", RAW)
    for name in ("speaker__sherlock-holmes-adventures.json", "scene__sherlock-holmes-adventures.json"):
        assert all(sources.verify_slice(canonical, i) for i in refs.load(BENCH / name)["items"]), name


@pytest.mark.skipif(not (RAW / "comics" / "pepper-carrot").exists(), reason="local Pepper&Carrot pages not present")
def test_pepper_carrot_image_hashes_match_the_local_copy() -> None:
    for item in refs.load(BENCH / "identity__pepper-carrot.json")["items"]:
        assert sources.file_sha256(RAW / "comics" / "pepper-carrot" / item["image"]) == item["image_sha256"]
