"""Span-level NER bake-off on the romanized-name gold set.

    python scripts/eval/ner_bakeoff.py --system heuristic --split dev --out data/eval/ner/
    python scripts/eval/ner_bakeoff.py --system qwen-llm:qwen2.5:7b --split dev --sweep
    python scripts/eval/ner_bakeoff.py --system gliner:urchade/gliner_medium-v2.1 --split test --threshold 0.4
    python scripts/eval/ner_bakeoff.py --system fast --split test --pipeline-filters   # the production fast detector
    python scripts/eval/ner_bakeoff.py --rescore data/eval/ner/bakeoff-qwen-llm-qwen2.5-7b-dev.json --split dev --sweep

Tune thresholds on `--split dev` only (`--sweep`), then run `--split test` once with the chosen `--threshold`.
`--rescore` re-scores a saved result's stored predictions on the same split with no detector run (no LLM, no GPU).
Systems are built lazily so a missing optional dependency only breaks its own system.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class NotImplementedYet(SystemExit):
    pass


def _need(module: str, what: str):
    import importlib

    try:
        return importlib.import_module(f"echotales.pipeline.mentions.{module}")
    except ImportError as exc:
        raise NotImplementedYet(f"system {what!r} is not implemented yet ({module}: {exc})") from exc


def build_system(spec: str, threshold: float | None):
    """Return (detector, system_meta). `threshold` is passed to detectors that take one natively."""
    name, _, arg = spec.partition(":")
    if name == "heuristic":
        from echotales.pipeline.mentions.ner import HeuristicDetector

        return HeuristicDetector(), {"system": spec, "model": None, "kind": "regex/capitalisation baseline"}
    if name == "qwen-llm":
        if not arg:
            raise SystemExit("qwen-llm needs an ollama tag, e.g. qwen-llm:qwen2.5:7b")
        from echotales.pipeline.llm.client import ModelClient
        from echotales.pipeline.llm.ollama import OllamaProvider
        from echotales.pipeline.mentions.ner import QwenNerDetector, ner_pass_fingerprint

        # provider_override pins the model to the requested tag for every task; NER's profile temperature is 0.0
        # (llm/tasks.py), which is what a reproducible bake-off needs.
        client = ModelClient(provider_override=OllamaProvider(model=arg))
        return QwenNerDetector(client), {
            "system": spec, "model": arg, "provider": "ollama", "temperature": 0.0,
            "prompt_fingerprint": ner_pass_fingerprint(),
        }
    if name == "gliner":
        mod = _need("gliner_ner", spec)
        kwargs = {"model_id": arg} if arg else {}
        if threshold is not None:
            kwargs["threshold"] = threshold
        det = mod.GlinerDetector(**kwargs)
        return det, {"system": spec, "model": arg or "default", "native_threshold": threshold}
    if name == "spacy":
        mod = _need("spacy_ner", spec)
        det = mod.SpacyDetector(model_name=arg) if arg else mod.SpacyDetector()
        return det, {"system": spec, "model": arg or "en_core_web_sm"}
    if name == "nametag3":
        mod = _need("nametag_ner", spec)
        return mod.NameTagDetector(), {"system": spec, "model": "nametag3"}
    if name == "hybrid":
        return build_hybrid(spec)
    if name == "fast":
        return build_fast()
    raise SystemExit(f"unknown system {spec!r}")


#: GLiNER-medium weights are read from a local directory (no network). The revision and file hash identify them in
#: every result; they are the values recorded when the weights were copied in, not re-derived per run.
GLINER_LOCAL = Path.home() / ".cache/huggingface/local/gliner_medium-v2.1"
GLINER_REVISION = "40ec419335d09393f298636f471328b722c6da9e"
GLINER_SHA256 = "922214c0c60f7835bb5c00f52ad1769d38518d5183f85de7bc03893a8403c023"
CLASSIFY_CACHE_DIR = ROOT / "data/scratch/ner_classify_cache"


def build_fast():
    """Exactly the production `mentions.detector = "fast"` detector: the same builder the runner calls, with the local
    GLiNER-medium weights. Its own routing rule (any GLiNER vote at 0.4) is what is measured, so a difference from the
    plain `gliner:...` system at 0.4 is the hybrid's candidate merge and span trimming, not a different model."""
    from echotales.pipeline.config import LLMMode, Settings
    from echotales.pipeline.mentions.hybrid import FAST_GLINER_THRESHOLD, build_hybrid_detector

    det = build_hybrid_detector(
        Settings(llm_mode=LLMMode.LOCAL, mentions_gliner_model=str(GLINER_LOCAL)), client=None, fast=True
    )
    if det is None:
        raise SystemExit("the fast detector needs the `ml` extra (gliner is not importable)")
    meta = {
        "system": "fast", "model": "gliner-medium", "gliner_threshold": FAST_GLINER_THRESHOLD, "classifier": None,
        "gliner_model_id": str(GLINER_LOCAL), "gliner_hf_revision": GLINER_REVISION,
        "gliner_safetensors_sha256": GLINER_SHA256,
        "gazetteer": "none (the eval corpus has no roster)",
    }
    return det, meta


def run_fast(det, docs, ns) -> tuple[tuple[dict, dict], dict]:
    """GLiNER over ALL docs in one load (`precompute` unloads it once), then the routing pass; timed as one figure."""
    import time

    t0 = time.perf_counter()
    det.precompute([d["text"] for d in docs])
    t_enc = time.perf_counter() - t0
    preds, runtime = ns.detect_all(det, docs)
    total = t_enc + runtime["wall_seconds"]
    runtime["wall_seconds"] = round(total, 3)
    runtime["seconds_per_1k_tokens"] = round(total / runtime["whitespace_tokens"] * 1000, 4)
    return (preds, runtime), {"encoder_seconds": round(t_enc, 3), "route_counts": dict(det.route_counts)}


def parse_hybrid_spec(spec: str) -> tuple[str, float, float]:
    """`hybrid:<llm tag>:<tau_high>:<tau_low>` -> (tag, tau_high, tau_low).

    The tag may itself contain colons (`qwen3:8b`), so the two thresholds are split off from the right.
    """
    name, _, rest = spec.partition(":")
    if name != "hybrid" or rest.count(":") < 2:
        raise SystemExit("hybrid spec is hybrid:<llm tag>:<tau_high>:<tau_low>, e.g. hybrid:qwen3:8b:0.7:0.3")
    tag, hi, lo = rest.rsplit(":", 2)
    try:
        tau_high, tau_low = float(hi), float(lo)
    except ValueError as exc:
        raise SystemExit(f"hybrid thresholds must be numbers: {spec!r}") from exc
    if not tag or not 0.0 <= tau_low <= tau_high <= 1.0:
        raise SystemExit(f"hybrid needs a tag and 0 <= tau_low <= tau_high <= 1: {spec!r}")
    return tag, tau_high, tau_low


def build_hybrid(spec: str, *, client=None, gliner=None, spacy=None, cache_dir: Path | None = None):
    """GLiNER (cut at tau_low, so the reject band is reachable) + spaCy + the context classifier.

    No gazetteer and no seed names: the eval corpus has no roster, so the gazetteer-accept route never fires and the
    result measures the encoders plus the classifier alone, not a run that has already learned a cast. `client`,
    `gliner` and `spacy` are injectable for tests.
    """
    tag, tau_high, tau_low = parse_hybrid_spec(spec)
    from echotales.pipeline.mentions.gliner_ner import GlinerDetector
    from echotales.pipeline.mentions.hybrid import HybridDetector
    from echotales.pipeline.mentions.ner_classify import ClassifyCache, LlmNameClassifier
    from echotales.pipeline.mentions.spacy_ner import SpacyDetector

    if client is None:
        from echotales.pipeline.llm.client import ModelClient
        from echotales.pipeline.llm.ollama import OllamaProvider

        client = ModelClient(provider_override=OllamaProvider(model=tag))
    gliner = gliner or GlinerDetector(str(GLINER_LOCAL), threshold=tau_low)
    spacy = spacy or SpacyDetector("en_core_web_sm")
    cache = ClassifyCache((cache_dir or CLASSIFY_CACHE_DIR) / f"{slug(tag)}.json", model=tag)
    classifier = LlmNameClassifier(client, cache=cache)
    det = HybridDetector(gliner=gliner, spacy=spacy, classifier=classifier, tau_high=tau_high, tau_low=tau_low)
    meta = {
        "system": spec, "model": "hybrid", "classifier_model": tag, "provider": "ollama", "temperature": 0.0,
        "tau_high": tau_high, "tau_low": tau_low,
        "gliner_model_id": str(GLINER_LOCAL), "gliner_hf_revision": GLINER_REVISION,
        "gliner_safetensors_sha256": GLINER_SHA256, "spacy_model": "en_core_web_sm",
        "gazetteer": "none (the eval corpus has no roster; the gazetteer-accept route cannot fire)",
        "classify_cache": str(cache.path),
    }
    return det, meta


def run_hybrid(det, docs, ns) -> tuple[tuple[dict, dict], dict]:
    """GLiNER then spaCy over ALL docs (GLiNER unloaded inside `precompute`), then routing and classifier calls.

    Two timed phases so the cost of the classifier is visible on its own; `seconds_per_1k_tokens` covers both.
    Returns (detected, extra_meta).
    """
    import time

    cache = det.classifier.cache
    before = len(cache._data)
    t0 = time.perf_counter()
    det.precompute([d["text"] for d in docs])
    t_enc = time.perf_counter() - t0
    preds, runtime = ns.detect_all(det, docs)
    t_cls = runtime["wall_seconds"]
    cache.flush()
    total = t_enc + t_cls
    runtime["wall_seconds"] = round(total, 3)
    runtime["seconds_per_1k_tokens"] = round(total / runtime["whitespace_tokens"] * 1000, 4)
    extra = {
        "encoder_seconds": round(t_enc, 3), "route_and_classifier_seconds": round(t_cls, 3),
        "classifier_calls": det.classifier.calls, "classifier_new_verdicts_cached": len(cache._data) - before,
        "route_counts": dict(det.route_counts),
    }
    return (preds, runtime), extra


def slug(spec: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", spec).strip("-").lower()


def _print_summary(result: dict) -> None:
    for mode in ("boundary", "exact", "overlap"):
        for variant in ("span_only", "label_aware"):
            o = result["metrics"][mode][variant]["overall"]
            print(f"{mode:7s} {variant:11s} P={o['precision']:.3f} R={o['recall']:.3f} F1={o['f1']:.3f}")
    g = result["metrics"]["boundary"]["span_only"].get("generic_role", {})
    if g.get("gold"):
        print(f"generic_role_recall (boundary) {g['matched']}/{g['gold']} = {g['recall']:.3f}")
    if "sweep" in result:
        c = result["sweep"]["chosen"]
        print(f"sweep chose threshold {c['threshold']} ({result['sweep']['rule']}): "
              f"P={c['precision']:.3f} R={c['recall']:.3f}")


def _rescore(ap: argparse.ArgumentParser, args, ns) -> Path:
    src = Path(args.rescore).resolve()
    payload = json.loads(src.read_text(encoding="utf-8"))
    if payload.get("split") != args.split:
        ap.error(f"{src.name} is split {payload.get('split')!r}; --split must match")
    gold = payload.get("gold") or args.gold
    gold_dir = Path(gold)
    docs = ns.load_gold(gold_dir if gold_dir.is_absolute() else ROOT / gold_dir, args.split)
    if payload.get("source"):
        docs = [d for d in docs if d["source"] == payload["source"]]
    result = ns.rescore_payload(payload, docs, threshold=args.threshold, sweep=args.sweep,
                              include_generic=args.include_generic,
                                pipeline_filters=args.pipeline_filters)
    result.update({"split": args.split, "gold": gold, "source": payload.get("source")})
    meta = {**payload.get("system", {}), "threshold": args.threshold, "rescored_from": str(src)}
    suffix = f"-t{args.threshold}" if args.threshold is not None else "-rescored"
    if args.pipeline_filters:
        suffix += "-filtered"
    out_dir = Path(args.out) if args.out else src.parent
    out_dir = out_dir if out_dir.is_absolute() else ROOT / out_dir
    out_path = ns.write_result(out_dir / f"{src.stem}{suffix}.json", result, meta)
    _print_summary(result)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", default="data/gold/ner_romanized")
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--system", default=None, help="required unless --rescore is given")
    ap.add_argument("--rescore", metavar="RESULT_JSON", default=None,
                    help="re-score this result's stored predictions on the same split; runs no detector")
    ap.add_argument("--threshold", type=float, default=None,
                    help="drop predictions scoring below this (also passed to detectors with a native threshold)")
    ap.add_argument("--sweep", action="store_true", help="threshold sweep from one detection pass (use on dev)")
    ap.add_argument("--source", choices=["synthetic", "public_domain"], default=None,
                    help="score only records of this source (synthetic text is too clean to be the only yardstick)")
    ap.add_argument("--include-generic", action="store_true",
                    help="score generic_role gold spans (bare role nouns) as ordinary names; default excludes them")
    ap.add_argument("--pipeline-filters", action="store_true",
                    help="drop predictions the production mention path drops (chapter_ner.plausible_name, "
                         "normalize.non_name_reason) before scoring; report filtered next to unfiltered")
    ap.add_argument("--out", default=None,
                    help="output directory (default data/eval/ner/; with --rescore, the input file's directory)")
    args = ap.parse_args()

    from echotales.pipeline.eval import ner_spans as ns

    if args.rescore:
        out_path = _rescore(ap, args, ns)
        print("wrote", out_path, file=sys.stderr)
        return
    if not args.system:
        ap.error("--system is required unless --rescore is given")

    gold_dir = Path(args.gold)
    docs = ns.load_gold(gold_dir if gold_dir.is_absolute() else ROOT / gold_dir, args.split)
    if args.source:
        docs = [d for d in docs if d["source"] == args.source]
    detector, meta = build_system(args.system, args.threshold)
    meta["threshold"] = args.threshold

    if args.system.partition(":")[0] == "hybrid":
        detected, hybrid_extra = run_hybrid(detector, docs, ns)
        meta.update(hybrid_extra)
        meta.update(ns.ollama_model_meta(meta["classifier_model"]))
    elif args.system == "fast":
        detected, fast_extra = run_fast(detector, docs, ns)
        meta.update(fast_extra)
    else:
        detected = ns.detect_all(detector, docs)
    if args.system.partition(":")[0] == "qwen-llm":
        # Sampled right after detection: the model is still loaded and its VRAM is reported by /api/ps.
        meta.update(ns.ollama_model_meta(args.system.partition(":")[2]))
    result = ns.evaluate(detector, docs, threshold=args.threshold, detected=detected,
                         include_generic=args.include_generic, pipeline_filters=args.pipeline_filters)
    result.update({"split": args.split, "gold": args.gold, "source": args.source})
    if args.sweep:
        result["sweep"] = ns.sweep_thresholds(docs, detected[0])

    out_dir = Path(args.out or "data/eval/ner/")
    out_path = ns.write_result((out_dir if out_dir.is_absolute() else ROOT / out_dir)
                               / f"bakeoff-{slug(args.system)}-{args.split}{'-' + args.source if args.source else ''}.json", result, meta)
    _print_summary(result)
    print("wrote", out_path, file=sys.stderr)


if __name__ == "__main__":
    main()
