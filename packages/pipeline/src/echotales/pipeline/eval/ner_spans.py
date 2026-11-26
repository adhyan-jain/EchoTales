"""Span-level NER evaluation for romanized and unfamiliar names in English prose.

This is deliberately separate from the identity-resolution eval (`coref_score`, `gold`): it asks only "did the
detector find the right character spans", not "did it link them to the right entity". The detector layer
(`mentions/ner.py`) is where a missed hard name is lost for good (EVOLUTION 4.85/4.86: hard cases are lost at mention
detection, not retrieval), so it gets its own measurable surface.

Matching is 1:1 greedy per document, in two strictnesses:

- **exact**: same start and end.
- **overlap**: any shared character. A predicted span can match at most one gold span and vice versa; without the
  1:1 rule a single long prediction ("Heavenly Demon Sect elders") would "recover" three gold spans.

Each strictness is scored two ways: **span-only** (label ignored) and **label-aware**.

Label compatibility (`labels_match`): project NER labels are character/location/organization/item. Gold uses
person/title_epithet/location/organization/item. `character` is mapped to `person`, and `person` and
`title_epithet` are treated as one compatible group in both directions, because the project's NER prompt asks for a
single-holder office title ("the clan head") as a *character* candidate (ner.py `_NER_SYSTEM`); a detector that
returns it as `character` is doing the right thing and must not be scored as a label error.
"""

from __future__ import annotations

import itertools
import json
import platform
import subprocess
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from echotales.pipeline.mentions.ner import NerSpan

GOLD_LABELS = ("person", "title_epithet", "location", "organization", "item")
GOLD_CATEGORIES = (
    "ordinary", "unfamiliar_fantasy", "invented", "title", "alias_epithet",
    "word_like", "sentence_initial", "shared_title",
)
BACKGROUNDS = ("zh", "ko", "ja", "in", "eu", "invented", "mixed")
SOURCES = ("synthetic", "public_domain")
SPLITS = ("dev", "test")

#: Detector label -> gold label. Anything absent passes through unchanged (lower-cased).
DEFAULT_LABEL_MAP: dict[str, str] = {
    "character": "person",
    "person": "person",
    "title_epithet": "title_epithet",
    "location": "location",
    "organization": "organization",
    "item": "item",
}
_PERSONISH = frozenset({"person", "title_epithet"})

THRESHOLDS = tuple(round(0.1 + 0.05 * i, 2) for i in range(17))  # 0.10 .. 0.90

LabelMap = dict[str, str] | Callable[[str], str]


# ---------------------------------------------------------------------------
# Gold loading and validation
# ---------------------------------------------------------------------------


def validate_record(rec: dict[str, Any]) -> list[str]:
    """Return a list of problems with one gold record (empty when it is sound)."""
    errs: list[str] = []
    doc = rec.get("doc_id", "<missing doc_id>")
    for key in ("doc_id", "source", "background", "split", "text", "spans"):
        if key not in rec:
            errs.append(f"{doc}: missing {key}")
    if errs:
        return errs
    text = rec["text"]
    if rec["source"] not in SOURCES:
        errs.append(f"{doc}: bad source {rec['source']!r}")
    if rec["background"] not in BACKGROUNDS:
        errs.append(f"{doc}: bad background {rec['background']!r}")
    if rec["split"] not in SPLITS:
        errs.append(f"{doc}: bad split {rec['split']!r}")
    spans = rec["spans"]
    for i, s in enumerate(spans):
        tag = f"{doc}#{i}"
        if s.get("label") not in GOLD_LABELS:
            errs.append(f"{tag}: bad label {s.get('label')!r}")
        if s.get("category") not in GOLD_CATEGORIES:
            errs.append(f"{tag}: bad category {s.get('category')!r}")
        a, b = s.get("start"), s.get("end")
        if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= len(text)):
            errs.append(f"{tag}: bad offsets {a}-{b}")
            continue
        if text[a:b] != s.get("surface"):
            errs.append(f"{tag}: text[{a}:{b}]={text[a:b]!r} != surface {s.get('surface')!r}")
    # Two gold spans overlapping would make 1:1 matching ambiguous and double-count a name.
    ordered = sorted((s for s in spans if isinstance(s.get("start"), int)), key=lambda s: s["start"])
    for p, q in itertools.pairwise(ordered):
        if q["start"] < p["end"]:
            errs.append(f"{doc}: overlapping gold spans {p['surface']!r} / {q['surface']!r}")
    return errs


def load_gold(path: str | Path, split: str | None = None, *, strict: bool = True) -> list[dict[str, Any]]:
    """Load every `*.jsonl` under a directory (or one file), optionally filtered to a split."""
    p = Path(path)
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    docs: list[dict[str, Any]] = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                docs.append(json.loads(line))
    if strict:
        errors = [e for d in docs for e in validate_record(d)]
        if errors:
            raise ValueError("invalid gold:\n" + "\n".join(errors[:20]))
    if split is not None:
        docs = [d for d in docs if d["split"] == split]
    return docs


# ---------------------------------------------------------------------------
# Matching and scoring
# ---------------------------------------------------------------------------


def labels_match(gold_label: str, pred_label: str) -> bool:
    if gold_label == pred_label:
        return True
    return gold_label in _PERSONISH and pred_label in _PERSONISH


def _map_label(label: str, label_map: LabelMap | None) -> str:
    label = label.strip().lower()
    if callable(label_map):
        return label_map(label)
    return (label_map or DEFAULT_LABEL_MAP).get(label, label)


def match_spans(
    gold: Sequence[dict[str, Any]],
    pred: Sequence[NerSpan],
    *,
    mode: str,
    label_aware: bool,
) -> list[tuple[int, int]]:
    """Greedy 1:1 matching; returns (gold_index, pred_index) pairs.

    Candidates are taken best-first (largest character overlap, then the closest boundaries) so that a short
    prediction inside a long gold span cannot steal it from the prediction that actually covers it.
    """
    if mode not in ("exact", "overlap"):
        raise ValueError(mode)
    cands: list[tuple[int, int, int, int]] = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            if label_aware and not labels_match(g["label"], p.label):
                continue
            if mode == "exact":
                if g["start"] == p.start and g["end"] == p.end:
                    cands.append((0, 0, gi, pi))
                continue
            ov = min(g["end"], p.end) - max(g["start"], p.start)
            if ov > 0:
                slack = abs(g["start"] - p.start) + abs(g["end"] - p.end)
                cands.append((-ov, slack, gi, pi))
    cands.sort()
    used_g: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _, _, gi, pi in cands:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((gi, pi))
    return pairs


def _prf(tp: int, n_pred: int, n_gold: int) -> dict[str, float | int]:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": n_pred - tp, "fn": n_gold - tp, "precision": p, "recall": r, "f1": f}


def _dedupe(spans: Iterable[NerSpan]) -> list[NerSpan]:
    """Identical (start, end, label) triples are one prediction: windowed detectors can emit repeats."""
    seen: set[tuple[int, int, str]] = set()
    out: list[NerSpan] = []
    for s in sorted(spans, key=lambda s: (s.start, s.end)):
        key = (s.start, s.end, s.label)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def normalize_predictions(spans: Iterable[NerSpan], label_map: LabelMap | None = None) -> list[NerSpan]:
    return _dedupe(
        NerSpan(text=s.text, start=s.start, end=s.end, label=_map_label(s.label, label_map), score=s.score)
        for s in spans
    )


def score_predictions(
    docs: Sequence[dict[str, Any]],
    preds: dict[str, list[NerSpan]],
    *,
    label_map: LabelMap | None = None,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Score already-detected spans against gold. Pure: no detector, no timing."""
    norm: dict[str, list[NerSpan]] = {}
    for d in docs:
        spans = normalize_predictions(preds.get(d["doc_id"], []), label_map)
        if min_score is not None:
            spans = [s for s in spans if s.score >= min_score]
        norm[d["doc_id"]] = spans

    result: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    for mode in ("exact", "overlap"):
        for variant, label_aware in (("span_only", False), ("label_aware", True)):
            totals = {"tp": 0, "pred": 0, "gold": 0}
            by_bg: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "pred": 0, "gold": 0})
            by_label: dict[str, dict[str, int]] = defaultdict(lambda: {"gold": 0, "matched": 0})
            by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"gold": 0, "matched": 0})
            fps: list[dict[str, Any]] = []
            misses: list[dict[str, Any]] = []
            for d in docs:
                gold = d["spans"]
                pred = norm[d["doc_id"]]
                pairs = match_spans(gold, pred, mode=mode, label_aware=label_aware)
                matched_g = {g for g, _ in pairs}
                matched_p = {p for _, p in pairs}
                bg = by_bg[d["background"]]
                bg["tp"] += len(pairs)
                bg["pred"] += len(pred)
                bg["gold"] += len(gold)
                totals["tp"] += len(pairs)
                totals["pred"] += len(pred)
                totals["gold"] += len(gold)
                for gi, g in enumerate(gold):
                    hit = gi in matched_g
                    by_label[g["label"]]["gold"] += 1
                    by_label[g["label"]]["matched"] += hit
                    by_cat[g["category"]]["gold"] += 1
                    by_cat[g["category"]]["matched"] += hit
                    if not hit:
                        misses.append({"doc_id": d["doc_id"], "surface": g["surface"], "label": g["label"],
                                       "category": g["category"], "start": g["start"], "background": d["background"]})
                for pi, p in enumerate(pred):
                    if pi not in matched_p:
                        fps.append({"doc_id": d["doc_id"], "surface": p.text, "label": p.label, "start": p.start,
                                    "score": p.score, "background": d["background"]})
            result.setdefault(mode, {})[variant] = {
                "overall": _prf(totals["tp"], totals["pred"], totals["gold"]),
                "by_gold_label": {k: {**v, "recall": v["matched"] / v["gold"]} for k, v in sorted(by_label.items())},
                "by_category": {k: {**v, "recall": v["matched"] / v["gold"]} for k, v in sorted(by_cat.items())},
                "by_background": {k: _prf(v["tp"], v["pred"], v["gold"]) for k, v in sorted(by_bg.items())},
            }
            errors.setdefault(mode, {})[variant] = {"false_positives": fps, "missed": misses}
    return {"metrics": result, "errors": errors}


# ---------------------------------------------------------------------------
# Running a detector
# ---------------------------------------------------------------------------


def _peak_vram_reset() -> bool:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            return True
    except Exception:
        pass
    return False


def _peak_vram_mb() -> float | None:
    try:
        import torch

        if torch.cuda.is_available():
            return round(torch.cuda.max_memory_allocated() / 2**20, 1)
    except Exception:
        pass
    return None


def detect_all(detector: Any, docs: Sequence[dict[str, Any]]) -> tuple[dict[str, list[NerSpan]], dict[str, Any]]:
    """Run `detector.detect` over every document; return raw spans and runtime figures."""
    had_cuda = _peak_vram_reset()
    preds: dict[str, list[NerSpan]] = {}
    t0 = time.perf_counter()
    for d in docs:
        preds[d["doc_id"]] = list(detector.detect(d["text"]))
    wall = time.perf_counter() - t0
    tokens = sum(len(d["text"].split()) for d in docs)
    runtime = {
        "wall_seconds": round(wall, 3),
        "seconds_per_1k_tokens": round(wall / tokens * 1000, 4) if tokens else None,
        "whitespace_tokens": tokens,
        "peak_vram_mb": _peak_vram_mb() if had_cuda else None,
    }
    return preds, runtime


def evaluate(
    detector: Any,
    docs: Sequence[dict[str, Any]],
    *,
    label_map: LabelMap | None = None,
    threshold: float | None = None,
    detected: tuple[dict[str, list[NerSpan]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a detector and score it. `threshold` filters on `NerSpan.score` after detection.

    Pass `detected` (the `detect_all` result) to reuse one detection pass, e.g. for a sweep: an LLM detector is
    the expensive part and must not run twice.
    """
    preds, runtime = detected if detected is not None else detect_all(detector, docs)
    scored = score_predictions(docs, preds, label_map=label_map, min_score=threshold)
    return {
        "n_docs": len(docs),
        "n_gold_spans": sum(len(d["spans"]) for d in docs),
        "n_pred_spans": sum(len(normalize_predictions(v, label_map)) for v in preds.values()),
        "threshold": threshold,
        "runtime": runtime,
        **scored,
    }


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------


def sweep_thresholds(
    docs: Sequence[dict[str, Any]],
    preds: dict[str, list[NerSpan]],
    *,
    thresholds: Sequence[float] = THRESHOLDS,
    mode: str = "overlap",
    variant: str = "span_only",
    min_precision: float = 0.95,
    label_map: LabelMap | None = None,
) -> dict[str, Any]:
    """P/R/F1 at each threshold from one detection pass, and the chosen operating point.

    Chosen = the highest-recall threshold whose precision is at least `min_precision` (the project prefers
    precision over recall in local resolution, non-negotiable 9); if none reaches it, the max-F1 threshold. Ties
    go to the higher threshold. Defaults to overlap/span-only so the choice reflects "found the name" and is not
    swayed by boundary or label conventions that differ between detectors. Tune on dev only.
    """
    rows = []
    for t in thresholds:
        m = score_predictions(docs, preds, label_map=label_map, min_score=t)["metrics"][mode][variant]["overall"]
        rows.append({"threshold": t, "precision": m["precision"], "recall": m["recall"], "f1": m["f1"],
                     "tp": m["tp"], "fp": m["fp"], "fn": m["fn"]})
    ok = [r for r in rows if r["precision"] >= min_precision]
    if ok:
        best = max(ok, key=lambda r: (r["recall"], r["threshold"]))
        rule = f"highest recall with precision >= {min_precision}"
    else:
        best = max(rows, key=lambda r: (r["f1"], r["threshold"]))
        rule = f"max F1 (no threshold reached precision {min_precision})"
    return {"mode": mode, "variant": variant, "min_precision": min_precision, "rows": rows,
            "chosen": best, "rule": rule}


# ---------------------------------------------------------------------------
# Result writing
# ---------------------------------------------------------------------------


def _git_commit(cwd: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True,
                              check=True, timeout=10).stdout.strip()
    except Exception:
        return None


def hardware_info() -> dict[str, Any]:
    info: dict[str, Any] = {"platform": platform.platform(), "processor": platform.processor() or None,
                            "python": platform.python_version(), "gpu": None}
    try:
        import torch

        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return info


def write_result(path: str | Path, result: dict[str, Any], system_meta: dict[str, Any]) -> Path:
    """Write the result JSON with provenance. `system_meta` (model id, version/digest/revision, params,
    quantization, threshold) is whatever the caller knows; this function invents none of it."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "commit": _git_commit(Path(__file__).resolve().parent),
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "hardware": hardware_info(),
        "system": system_meta,
        **result,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
