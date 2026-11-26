"""Span-level NER evaluation for romanized and unfamiliar names in English prose.

This is deliberately separate from the identity-resolution eval (`coref_score`, `gold`): it asks only "did the
detector find the right character spans", not "did it link them to the right entity". The detector layer
(`mentions/ner.py`) is where a missed hard name is lost for good (EVOLUTION 4.85/4.86: hard cases are lost at mention
detection, not retrieval), so it gets its own measurable surface.

Matching is 1:1 greedy per document, in three strictnesses:

- **exact**: same start and end.
- **boundary** (the headline): overlapping spans whose surfaces are equal once a leading article and attached
  honorifics are trimmed (`ingest.normalize.strip_honorifics`, the project's own list). Gold and detectors follow
  different conventions ("the Emperor" vs "Emperor", "Dokja" vs "Dokja-ssi"); measured on gemma2:9b dev, most of the
  99 exact-mode FP / 115 misses were such mismatches, not detection failures.
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

from echotales.pipeline.ingest.normalize import strip_honorifics
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

MODES = ("boundary", "exact", "overlap")

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


def boundary_key(surface: str) -> str:
    """Comparison key for the boundary mode: trimmed, article- and honorific-stripped, case-folded.

    Falls back to the plain trimmed surface when stripping would leave nothing ("Sir" alone), so a bare honorific
    still matches itself rather than everything.
    """
    plain = surface.strip(" \t\n.,;:!?\"'")
    return (strip_honorifics(plain, strip_articles=True) or plain).casefold()


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
    if mode not in MODES:
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
            if mode == "boundary" and (ov <= 0 or boundary_key(g["surface"]) != boundary_key(p.text)):
                continue
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
    # A span strictly inside a longer one is the same mention reported twice: an LLM that returns both "Bai Ningbing"
    # and "Bai" gets "Bai" located inside every "Bai Ningbing" (and "Dokja" inside "Dokja-ssi"). The same rule is in
    # QwenNerDetector._locate; applying it here lets result files written before that fix be rescored fairly.
    return [s for s in out
            if not any(o is not s and o.start <= s.start and s.end <= o.end and (o.end - o.start) > (s.end - s.start)
                       for o in out)]


def normalize_predictions(spans: Iterable[NerSpan], label_map: LabelMap | None = None) -> list[NerSpan]:
    return _dedupe(
        NerSpan(text=s.text, start=s.start, end=s.end, label=_map_label(s.label, label_map), score=s.score)
        for s in spans
    )


def apply_pipeline_filters(spans: Iterable[NerSpan]) -> list[NerSpan]:
    """Drop what the production mention path drops before a detector span can become a mention.

    Reuses the two real predicates, no list of its own: `chapter_ner.plausible_name` (the post-filter on detector
    output: copied sentences, punctuation fragments, all-lowercase non-titles) and `normalize.non_name_reason`
    (`mentions/runner.py::rejected`, which for a person-like span refuses pronouns and interjections). Called after
    label normalisation, so person/title_epithet stand for the runner's "character".
    """
    from echotales.pipeline.ingest.normalize import non_name_reason
    from echotales.pipeline.mentions.chapter_ner import plausible_name

    kept = []
    for s in spans:
        if not plausible_name(s.text):
            continue
        if s.label in _PERSONISH and non_name_reason(s.text) in ("pronoun", "interjection"):
            continue
        kept.append(s)
    return kept


def score_predictions(
    docs: Sequence[dict[str, Any]],
    preds: dict[str, list[NerSpan]],
    *,
    label_map: LabelMap | None = None,
    min_score: float | None = None,
    include_generic: bool = False,
    pipeline_filters: bool = False,
) -> dict[str, Any]:
    """Score already-detected spans against gold. Pure: no detector, no timing.

    Gold spans flagged `generic_role` (bare role nouns such as "the dean") are left out of the name metrics by
    default, and a prediction that matches one is not a false positive: EchoTales keeps generic descriptors out of
    the graph (non-negotiable 4), so a detector that skips them is right. They are reported separately as
    `generic_role` recall. `include_generic=True` scores them as ordinary gold.
    """
    norm: dict[str, list[NerSpan]] = {}
    for d in docs:
        spans = normalize_predictions(preds.get(d["doc_id"], []), label_map)
        if min_score is not None:
            spans = [s for s in spans if s.score >= min_score]
        if pipeline_filters:
            spans = apply_pipeline_filters(spans)
        norm[d["doc_id"]] = spans

    result: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    for mode in MODES:
        for variant, label_aware in (("span_only", False), ("label_aware", True)):
            totals = {"tp": 0, "pred": 0, "gold": 0}
            by_bg: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "pred": 0, "gold": 0})
            by_label: dict[str, dict[str, int]] = defaultdict(lambda: {"gold": 0, "matched": 0})
            by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"gold": 0, "matched": 0})
            fps: list[dict[str, Any]] = []
            misses: list[dict[str, Any]] = []
            generic = {"gold": 0, "matched": 0}
            for d in docs:
                all_gold = d["spans"]
                pred_all = norm[d["doc_id"]]
                pairs_all = match_spans(all_gold, pred_all, mode=mode, label_aware=label_aware)
                if include_generic:
                    gold, pred, pairs = all_gold, pred_all, pairs_all
                else:
                    gen_g = {i for i, g in enumerate(all_gold) if g.get("generic_role")}
                    # Also drop an unmatched prediction that merely overlaps a generic gold span: under exact mode
                    # "the dean" vs gold "dean" would otherwise be charged as a false positive for skipping nothing.
                    gen_p = {pi for gi, pi in pairs_all if gi in gen_g} | {
                        pi for pi, p in enumerate(pred_all)
                        if any(min(all_gold[gi]["end"], p.end) > max(all_gold[gi]["start"], p.start) for gi in gen_g)}
                    generic["gold"] += len(gen_g)
                    generic["matched"] += sum(1 for gi, _ in pairs_all if gi in gen_g)
                    keep_g = [i for i in range(len(all_gold)) if i not in gen_g]
                    keep_p = [i for i in range(len(pred_all)) if i not in gen_p]
                    gold = [all_gold[i] for i in keep_g]
                    pred = [pred_all[i] for i in keep_p]
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
                "generic_role": {**generic, "recall": generic["matched"] / generic["gold"] if generic["gold"] else None},
            }
            errors.setdefault(mode, {})[variant] = {"false_positives": fps, "missed": misses}
    return {"metrics": result, "errors": errors}


def _metrics_by_source(
    docs: Sequence[dict[str, Any]],
    preds: dict[str, list[NerSpan]],
    *,
    label_map: LabelMap | None = None,
    min_score: float | None = None,
    include_generic: bool = False,
    pipeline_filters: bool = False,
) -> dict[str, Any]:
    """The same metrics structure as `score_predictions`, filtered per record source (no re-detection)."""
    return {
        src: score_predictions([d for d in docs if d.get("source") == src], preds,
                               label_map=label_map, min_score=min_score, include_generic=include_generic,
                               pipeline_filters=pipeline_filters)["metrics"]
        for src in SOURCES
    }


def _raw_predictions(preds: dict[str, list[NerSpan]]) -> dict[str, list[list[Any]]]:
    """Unthresholded detector output as JSON-safe rows, so a result can be re-scored without the detector."""
    return {doc: [[s.start, s.end, s.label, s.score, s.text] for s in spans] for doc, spans in preds.items()}


def _predictions_from_json(raw: dict[str, list[list[Any]]]) -> dict[str, list[NerSpan]]:
    return {
        doc: [NerSpan(text=t, start=a, end=b, label=lab, score=sc) for a, b, lab, sc, t in rows]
        for doc, rows in raw.items()
    }


def rescore_payload(
    payload: dict[str, Any],
    docs: Sequence[dict[str, Any]],
    *,
    threshold: float | None = None,
    sweep: bool = False,
    label_map: LabelMap | None = None,
    include_generic: bool = False,
    pipeline_filters: bool = False,
) -> dict[str, Any]:
    """Score a saved result's stored predictions against `docs` (the same split/source). No detector runs.

    Refuses a result without stored predictions, or one that does not cover every gold doc, rather than silently
    scoring the missing docs as empty.
    """
    if "predictions" not in payload:
        raise ValueError("result has no stored predictions (written before predictions were recorded)")
    raw = payload["predictions"]
    missing = [d["doc_id"] for d in docs if d["doc_id"] not in raw]
    if missing:
        raise ValueError(f"{len(missing)} gold docs missing from stored predictions, e.g. {missing[:3]}")
    preds = _predictions_from_json(raw)
    result = evaluate(None, docs, label_map=label_map, threshold=threshold,
                      detected=(preds, payload.get("runtime") or {}), include_generic=include_generic,
                      pipeline_filters=pipeline_filters)
    if sweep:
        result["sweep"] = sweep_thresholds(docs, preds, label_map=label_map)
    return result


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
    include_generic: bool = False,
    pipeline_filters: bool = False,
) -> dict[str, Any]:
    """Run a detector and score it. `threshold` filters on `NerSpan.score` after detection.

    Pass `detected` (the `detect_all` result) to reuse one detection pass, e.g. for a sweep: an LLM detector is
    the expensive part and must not run twice.
    """
    preds, runtime = detected if detected is not None else detect_all(detector, docs)
    scored = score_predictions(docs, preds, label_map=label_map, min_score=threshold, include_generic=include_generic,
                              pipeline_filters=pipeline_filters)
    return {
        "n_docs": len(docs),
        "n_gold_spans": sum(len(d["spans"]) for d in docs),
        "n_pred_spans": sum(len(normalize_predictions(v, label_map)) for v in preds.values()),
        "pipeline_filters": pipeline_filters,
        "threshold": threshold,
        "runtime": runtime,
        "metrics_by_source": _metrics_by_source(docs, preds, label_map=label_map, min_score=threshold,
                                                include_generic=include_generic, pipeline_filters=pipeline_filters),
        "include_generic": include_generic,
        "predictions": _raw_predictions(preds),
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


OLLAMA_URL = "http://localhost:11434"


def _ollama_call(url: str, body: dict[str, Any] | None, timeout: float) -> Any:
    import urllib.request

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_model_meta(tag: str, *, base_url: str = OLLAMA_URL, timeout: float = 5.0) -> dict[str, Any]:
    """Digest, parameter size and quantization from /api/show, and the VRAM the model holds right now from /api/ps.

    Call it right after detection, while the model is still loaded (ollama unloads after its keep-alive). Every
    field is None when ollama is unreachable or the tag is not known; this never raises, so a bake-off cannot be
    lost to a metadata lookup. /api/show is POST: the daemon answers GET with 405.
    """
    meta: dict[str, Any] = {"digest": None, "parameter_size": None, "quantization_level": None, "size_vram": None}
    try:
        show = _ollama_call(f"{base_url}/api/show", {"model": tag}, timeout)
        details = show.get("details") or {}
        meta["digest"] = show.get("digest") or details.get("digest")
        meta["parameter_size"] = details.get("parameter_size")
        meta["quantization_level"] = details.get("quantization_level")
    except Exception:
        pass
    try:
        ps = _ollama_call(f"{base_url}/api/ps", None, timeout)
        names = {tag, f"{tag}:latest"}
        for entry in ps.get("models") or []:
            if {entry.get("name"), entry.get("model")} & names:
                meta["size_vram"] = entry.get("size_vram")
                break
    except Exception:
        pass
    return meta


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
