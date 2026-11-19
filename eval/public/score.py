"""Deterministic scorers for the three public-benchmark tasks. No model, no network, no randomness.

Each takes the reference items and the system's predictions as plain dicts, so any tool can be scored by writing JSON.
"""

from __future__ import annotations

import re
from typing import Any


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", name.lower())).strip()


def _whole_word(term: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", text.lower()) is not None


def score_speaker(items: list[dict[str, Any]], predictions: dict[str, str]) -> dict[str, Any]:
    """Accuracy over the reference lines. A line with no prediction is wrong, and `accuracy_on_answered` is reported
    beside it so a system that abstains cannot hide behind a high precision."""
    known = {i["id"] for i in items}
    correct = answered = 0
    per: dict[str, dict[str, int]] = {}
    for item in items:
        accepted = {_norm(item["speaker"]), *(_norm(a) for a in item.get("aliases", []))}
        row = per.setdefault(item["speaker"], {"lines": 0, "correct": 0})
        row["lines"] += 1
        guess = predictions.get(item["id"])
        if guess is None or not guess.strip():
            continue
        answered += 1
        if _norm(guess) in accepted:
            correct += 1
            row["correct"] += 1
    n = len(items)
    return {
        "lines": n, "answered": answered, "correct": correct,
        "accuracy": correct / n if n else 0.0,
        "accuracy_on_answered": correct / answered if answered else 0.0,
        "per_speaker": per,
        "unmatched_predictions": sorted(set(predictions) - known),
    }


def score_identity(gold: dict[str, list[str]], predicted: dict[str, list[str]]) -> dict[str, Any]:
    """Which characters are in which panel, scored per character (precision, recall, F1) and per panel (exact set).

    A panel the system gave no answer for counts as "nobody found" and is listed, so dropping panels costs recall."""
    chars = sorted({c for cs in gold.values() for c in cs})
    per: dict[str, dict[str, float]] = {}
    for c in chars:
        tp = sum(1 for p, cs in gold.items() if c in cs and c in predicted.get(p, []))
        fp = sum(1 for p, cs in predicted.items() if c in cs and c not in gold.get(p, []))
        fn = sum(1 for p, cs in gold.items() if c in cs and c not in predicted.get(p, []))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                  "support": tp + fn}
    exact = sum(1 for p, cs in gold.items() if sorted(set(predicted.get(p, []))) == sorted(set(cs)))
    return {
        "per_character": per,
        "macro_f1": sum(v["f1"] for v in per.values()) / len(per) if per else 0.0,
        "panel_exact_match": exact / len(gold) if gold else 0.0,
        "panels": len(gold),
        "panels_without_prediction": sorted(p for p in gold if p not in predicted),
    }


def score_scene(scene: dict[str, Any], description: str) -> dict[str, Any]:
    """Share of a scene's required elements the system's description contains (whole words, any synonym counts).

    Forbidden elements (a contradiction, such as outdoors for an interior) are reported apart rather than subtracted,
    because how much a contradiction costs is a judgement the reader of the table should make."""
    satisfied = [r["element"] for r in scene["required"] if any(_whole_word(t, description) for t in r["any_of"])]
    missing = [r["element"] for r in scene["required"] if r["element"] not in satisfied]
    hit = [f["element"] for f in scene.get("forbidden", []) if any(_whole_word(t, description) for t in f["any_of"])]
    total = len(scene["required"])
    return {"id": scene["id"], "score": len(satisfied) / total if total else 0.0,
            "satisfied": satisfied, "missing": missing, "forbidden_hit": hit}


def score_scenes(scenes: list[dict[str, Any]], descriptions: dict[str, str]) -> dict[str, Any]:
    rows = [score_scene(s, descriptions.get(s["id"], "")) for s in scenes]
    return {
        "scenes": rows,
        "mean_score": sum(r["score"] for r in rows) / len(rows) if rows else 0.0,
        "scenes_forbidden_hit": sum(1 for r in rows if r["forbidden_hit"]),
        "scenes_without_description": sorted(s["id"] for s in scenes if s["id"] not in descriptions),
    }
