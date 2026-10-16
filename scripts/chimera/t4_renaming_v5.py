"""T4 v5: letter-cipher renaming with class-level protection, piece splitting and collision closure
(implements PREREG_T4_renaming_validity_v5.md; single attempt, no v6).

Subclasses the v4 renamer; reuses the v4 gate (G1-G5) and the T4 run/compare machinery by import, unedited.
CPU only, no model, no spend, no novel text in any output.

    python scripts/chimera/t4_renaming_v5.py --base-db <SCRATCH RI copy> --workdir <scratch dir> [--gate-only]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t4_renaming as T4  # noqa: E402
import t4_renaming_v4 as V4  # noqa: E402

from echotales.pipeline.ingest.normalize import comparison_key  # noqa: E402

CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


class CipherRenamerV5(V4.CipherRenamer):
    def __init__(self, vocab, protected, seed, existing: set[str], *, broken_yuan: bool = False) -> None:
        super().__init__(vocab, protected, seed, broken_yuan=broken_yuan)
        # 1. class-level protection (comparison-key classes fold case, spacing and a trailing plural s)
        pkeys = {comparison_key(p) for p in self.P}
        pieces = {p.casefold() for t in vocab for p in CAMEL.split(t) if p}
        self.vocab_cf = self.vocab_cf | pieces
        for t in sorted(self.vocab_cf):
            if comparison_key(t) in pkeys:
                self.P.add(t)
        # 3. collision closure (deterministic, at most 10 passes)
        self.closure_passes = 0
        self.closure_stable = False
        for n in range(10):
            self.closure_passes = n + 1
            images: dict[str, list[str]] = {}
            for t in sorted(self.vocab_cf):
                if t in self.P:
                    continue
                images.setdefault(self._piece(t).casefold(), []).append(t)
            newly: set[str] = set()
            for img, toks in images.items():
                if img in existing or img in self.P or len(toks) > 1:
                    newly.update(t for t in toks if self._piece(t).casefold() != t)
                    if len(toks) > 1:
                        newly.update(toks)
            newly -= self.P
            if not newly:
                self.closure_stable = True
                break
            self.P |= newly

    def _piece(self, p: str) -> str:
        return V4.CipherRenamer._run(self, p)

    def _run(self, w: str) -> str:  # a letter run -> pieces split at lower->upper transitions
        return "".join(self._piece(p) for p in CAMEL.split(w) if p)


def build_v5(db: str):
    _pi3, protected, vocab, surfaces = T4.build_pi(db)
    protected = set(protected) | V4.honorific_words()
    existing = V4.corpus_lower_tokens(db)
    pi = CipherRenamerV5(vocab, protected, T4.SEED, existing)
    return pi, protected, vocab, surfaces, existing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-db", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--gate-only", action="store_true")
    ap.add_argument("--out", default="data/eval/chimera/t4_v5_results.json")
    args = ap.parse_args()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    pi, protected, vocab, surfaces, existing = build_v5(args.base_db)
    gate = V4.full_gate(pi, surfaces, protected, args.base_db)
    gate["closure_passes"], gate["closure_stable"] = pi.closure_passes, pi.closure_stable
    gate["passed"] = bool(gate["passed"] and pi.closure_stable)
    summary = {k: v for k, v in gate.items() if k.endswith("count") or k in
               ("surfaces", "passed", "vocab_tokens_changed", "vocab_tokens", "closure_passes", "closure_stable")}
    print("commutation gate v5:", json.dumps(summary), flush=True)
    head = {"prereg": "PREREG_T4_renaming_validity_v5.md (single attempt; no v6)", "commutation_gate": gate}
    if not gate["passed"]:
        head["violation_classes_engine_vs_renamer"] = V4.classify_violations(gate, surfaces)
        head["status"] = "GATE_FAILED_NO_RUN"
        Path(args.out).write_text(json.dumps(head, indent=2) + "\n")
        print("GATE FAILED: no resolver run; T4 closed (no v6). classes:", head["violation_classes_engine_vs_renamer"])
        return 2
    if args.gate_only:
        head["status"] = "GATE_PASSED_GATE_ONLY"
        Path(args.out).write_text(json.dumps(head, indent=2) + "\n")
        print("gate passed (gate-only mode)")
        return 0
    ident = T4.Renamer({})
    broken = CipherRenamerV5(vocab, protected, T4.SEED, existing, broken_yuan=True)
    plan = {"O1": (None, False), "O2": (None, False), "I": (ident, False), "R": (pi, False), "N": (broken, False)}
    runs: dict[str, dict] = {}
    for name, (renamer, is_broken) in plan.items():
        t0 = time.time()
        runs[name] = T4.run_condition(name, args.base_db, workdir, renamer, broken=is_broken, smoke=args.smoke)
        print(f"{name}: {runs[name]['seconds']}s resolve, {time.time() - t0:.0f}s total, "
              f"mentions={len(runs[name]['decisions'])}", flush=True)
    base = runs["O1"]["decisions"]
    con = sqlite3.connect(f"file:{args.base_db}?mode=ro", uri=True)
    mention_text = {mid: text for mid, text in
                    con.execute("select id, text from mention where novel_id=?", (T4.NOVEL,))}
    con.close()
    keys = set(pi.mapping)
    result = dict(head, smoke_chapters=args.smoke or None, pi_vocabulary_size=len(keys), pi_seed=T4.SEED,
                  conditions={})
    for name, (renamer, _b) in plan.items():
        if name == "O1":
            continue
        flags = runs[name].get("flags", {})
        cmp = T4.compare(base, runs[name]["decisions"], None if name == "O2" else renamer, flags, protected, keys)
        cls = T4.classify(cmp["changed_ids"], mention_text, flags, protected, keys, base=base,
                          run=runs[name]["decisions"], ren=None if name == "O2" else renamer.rename)
        entry = {k: v for k, v in cmp.items() if k != "changed_ids"}
        entry["changed"] = len(cmp["changed_ids"])
        entry["changed_classification"] = dict(cls)
        entry["transform_counts"] = runs[name].get("counts")
        entry["entity_clustered_bootstrap95"] = T4.clustered_bootstrap(base, set(cmp["changed_ids"]))
        entry["resolve_seconds"] = runs[name]["seconds"]
        result["conditions"][name] = entry
        print(name, json.dumps({k: entry[k] for k in
                                ("n", "agree", "agreement", "wilson95", "bcubed_f1", "changed_classification")}),
              flush=True)
    result["status"] = "COMPLETE"
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print("written", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
