"""Span-level NER bake-off on the romanized-name gold set.

    python scripts/eval/ner_bakeoff.py --system heuristic --split dev --out data/eval/ner/
    python scripts/eval/ner_bakeoff.py --system qwen-llm:qwen2.5:7b --split dev --sweep
    python scripts/eval/ner_bakeoff.py --system gliner:urchade/gliner_medium-v2.1 --split test --threshold 0.4
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
        mod = _need("hybrid", spec)
        return mod.HybridDetector(), {"system": spec, "model": "hybrid"}
    raise SystemExit(f"unknown system {spec!r}")


def slug(spec: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", spec).strip("-").lower()


def _print_summary(result: dict) -> None:
    for mode in ("exact", "overlap"):
        for variant in ("span_only", "label_aware"):
            o = result["metrics"][mode][variant]["overall"]
            print(f"{mode:7s} {variant:11s} P={o['precision']:.3f} R={o['recall']:.3f} F1={o['f1']:.3f}")
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
    result = ns.rescore_payload(payload, docs, threshold=args.threshold, sweep=args.sweep)
    result.update({"split": args.split, "gold": gold, "source": payload.get("source")})
    meta = {**payload.get("system", {}), "threshold": args.threshold, "rescored_from": str(src)}
    suffix = f"-t{args.threshold}" if args.threshold is not None else "-rescored"
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

    detected = ns.detect_all(detector, docs)
    if args.system.partition(":")[0] == "qwen-llm":
        # Sampled right after detection: the model is still loaded and its VRAM is reported by /api/ps.
        meta.update(ns.ollama_model_meta(args.system.partition(":")[2]))
    result = ns.evaluate(detector, docs, threshold=args.threshold, detected=detected)
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
