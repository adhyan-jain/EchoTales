"""Command line for the public benchmark: `python -m eval.run_benchmark public ...` and `echotales benchmark ...`.

    status                         how much of each reference a person has checked
    lines --reference F            print the items to attribute (id, offset, text from YOUR local copy) as JSON
    score --reference F --predictions P [--out O]
    check --reference F            walk the items and record accept / edit
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from eval.public import check, refs, score, sources


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="benchmark", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench-dir", default=str(refs.BENCH_DIR), help="where the reference files live")
    ap.add_argument("--sources-dir", default="data/raw", help="where your own copies of the public-domain texts are")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("status", help="checked / unchecked counts per reference file")
    p = sub.add_parser("lines", help="the items a system must answer, with text from your local copy")
    p.add_argument("--reference", required=True)
    p = sub.add_parser("score", help="score a predictions JSON against a reference")
    p.add_argument("--reference", required=True)
    p.add_argument("--predictions", required=True, help="JSON: speaker {item id: name}; identity {panel id: [names]}; scene {scene id: description}")
    p.add_argument("--out", default=None)
    p = sub.add_parser("check", help="walk a reference and record a person's accept or edit per item")
    p.add_argument("--reference", required=True)
    return ap


def _score(doc: dict[str, Any], predictions: dict[str, Any]) -> dict[str, Any]:
    task = doc["task"]
    if task == "speaker":
        return score.score_speaker(doc["items"], predictions)
    if task == "identity":
        return score.score_identity({i["panel"]: i["characters"] for i in doc["items"]}, predictions)
    return score.score_scenes(doc["items"], predictions)


def run(args: argparse.Namespace) -> int:
    if args.action == "status":
        files = refs.find(args.bench_dir)
        if not files:
            print(f"no reference files in {args.bench_dir}")
        for path in files:
            doc = refs.load(path)
            print(f"{path.name}: {refs.banner(refs.status(doc))}")
        return 0

    path = Path(args.reference)
    doc = refs.load(path)
    refs.validate(doc)
    source_id = doc["source"]["id"]
    needs_text = doc["task"] == "speaker" or (doc["task"] == "scene" and any("offset" in i for i in doc["items"]))

    if args.action == "lines":
        canonical = sources.canonical_text(source_id, args.sources_dir)
        bad = [i["id"] for i in doc["items"] if "offset" in i and not sources.verify_slice(canonical, i)]
        if bad:
            print(f"your copy does not match the reference ({len(bad)} items, first {bad[0]}); wrong edition?", file=sys.stderr)
            return 2
        out = [{"id": i["id"], "offset": i["offset"], "length": i["length"],
                "text": canonical[i["offset"]:i["offset"] + i["length"]]} for i in doc["items"] if "offset" in i]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.action == "score":
        predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
        result = _score(doc, predictions)
        result["reference"] = {"file": path.name, "task": doc["task"], "source": source_id, **refs.status(doc),
                               "banner": refs.banner(refs.status(doc))}
        text = json.dumps(result, indent=2, ensure_ascii=False)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(text)
        print(result["reference"]["banner"], file=sys.stderr)
        return 0

    canonical = sources.canonical_text(source_id, args.sources_dir) if needs_text else None
    n = check.walk(path, canonical, ask=input, say=print)
    print(f"recorded {n} checks; {refs.banner(refs.status(refs.load(path)))}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
