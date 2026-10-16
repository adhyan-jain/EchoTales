"""Validate a CHIMERA pilot sheet returned by the annotator.

Rejects anything that could let a model-made or tampered row pass as a human
label (the Checkpoint 2 rule: LLM output is never ground truth, and an
annotator field that is blank or a model name is an error). It also checks
that the frozen item columns were not edited, using a hash of the pristine
sheet's item columns stored in the manifest by `--freeze`.

Usage:
    python scripts/chimera/validate_pilot_sheet.py --freeze        # once, on the pristine sheet
    python scripts/chimera/validate_pilot_sheet.py [--sheet PATH]  # on the returned sheet
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

SHEET = "data/eval/human_review_chimera_pilot.csv"
KEY = "data/eval/human_review_chimera_pilot_key.csv"
MANIFEST = "data/eval/chimera/pilot_manifest.json"

FROZEN = ("item_id", "batch", "novel", "chapter", "mention_offset", "mention_surface", "source_window", "candidates")
SPECIAL = {"NEW", "UNDETERMINED", "NOT_AN_ENTITY"}
# Anything that names a model, a vendor or an automated tool is not an annotator.
MODEL_NAME = re.compile(
    r"gpt|claude|anthropic|openai|sonnet|opus|haiku|gemini|llama|qwen|mistral|gemma|phi\d|ollama|"
    r"\bllm\b|\bmodel\b|\bbot\b|auto|script|gold-auto-builder|assistant|luna",
    re.I,
)


def frozen_hash(rows: list[dict]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update("\x1f".join(r[c] for c in FROZEN).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


def read(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def is_model_name(name: str) -> bool:
    return bool(MODEL_NAME.search(name))


def answer_ok(value: str, n_candidates: int) -> bool:
    v = value.strip()
    if not v:
        return False
    if v in SPECIAL:
        return True
    if re.fullmatch(r"[A-Z]", v):
        return ord(v) - 65 < n_candidates
    return True  # free text: any non-blank string that is not a bare out-of-range letter


def validate(rows: list[dict], key_ids: set[str], frozen_expected: str | None) -> tuple[list[str], dict]:
    errors: list[str] = []
    ids = [r["item_id"] for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate item_id values")
    if set(ids) != key_ids:
        errors.append(f"item ids differ from the key (extra={sorted(set(ids) - key_ids)[:3]}, missing={sorted(key_ids - set(ids))[:3]})")
    if frozen_expected is not None and frozen_hash(rows) != frozen_expected:
        errors.append("frozen item columns were edited (hash mismatch with the manifest)")

    labelled = 0
    for r in rows:
        iid = r["item_id"]
        touched = any(r[c].strip() for c in ("reader_warranted", "omniscient_id", "reader_evidence", "omniscient_evidence"))
        if not touched:
            continue  # an honestly unlabelled row; never filled in by a script
        labelled += 1
        n_cand = len([c for c in r["candidates"].split(" | ") if c.strip()])
        if not r["annotator"].strip():
            errors.append(f"{iid}: annotator is blank")
        elif is_model_name(r["annotator"]):
            errors.append(f"{iid}: annotator {r['annotator']!r} looks like a model or tool")
        if r["provenance"].strip() != "HUMAN":
            errors.append(f"{iid}: provenance must be the literal HUMAN, got {r['provenance']!r}")
        for col in ("reader_warranted", "omniscient_id"):
            if not answer_ok(r[col], n_cand):
                errors.append(f"{iid}: {col} is blank or an out-of-range letter ({r[col]!r})")
        if r["confidence_1to3"].strip() not in {"1", "2", "3"}:
            errors.append(f"{iid}: confidence_1to3 must be 1, 2 or 3")
        try:
            if float(r["minutes_spent"]) <= 0:
                raise ValueError
        except ValueError:
            errors.append(f"{iid}: minutes_spent must be a positive number")
        rc = r["reveal_chapter"].strip()
        if rc:
            try:
                float(rc)
            except ValueError:
                errors.append(f"{iid}: reveal_chapter must be a number or blank")
    summary = {"rows": len(rows), "labelled": labelled, "unlabelled": len(rows) - labelled}
    return errors, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", default=SHEET)
    ap.add_argument("--key", default=KEY)
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--freeze", action="store_true", help="record the pristine item-column hash in the manifest")
    args = ap.parse_args()

    rows = read(args.sheet)
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if args.freeze:
        manifest["frozen_cols_sha256"] = frozen_hash(rows)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print("frozen:", manifest["frozen_cols_sha256"])
        return 0
    key_ids = {r["item_id"] for r in read(args.key)}
    errors, summary = validate(rows, key_ids, manifest.get("frozen_cols_sha256"))
    print(json.dumps(summary))
    for e in errors:
        print("ERROR:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
