"""T4 v4: letter-cipher renaming control (implements PREREG_T4_renaming_validity_v4.md; single attempt, no v5).

A case-preserving, length-preserving letter substitution fixing s, u, i, applied to name letter runs, leaving
protected words (and protected substrings of 4+ letters inside glued names) unchanged. Reuses the T4 v3 machinery
(vocabulary build, commutation gate G1-G3, DB transformation, runs, comparison) by import, unedited. CPU only,
no model, no spend, no novel text in any output.

    python scripts/chimera/t4_renaming_v4.py --base-db <SCRATCH RI copy> --workdir <scratch dir> [--smoke N] [--gate-only]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import string
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t4_renaming as T4  # noqa: E402
from renaming import PRONOUNS, TOKEN  # noqa: E402

from echotales.pipeline.ingest.normalize import (  # noqa: E402
    _HONORIFIC_PREFIXES,
    _HONORIFIC_SUFFIXES,
    comparison_key,
)

FIXED = {"s", "u", "i"}


class IdMap:
    def map_offset(self, pos: int) -> int:
        return pos


class CipherRenamer:
    """pi_v4 (PREREG_T4 v4 section 1)."""

    def __init__(self, vocab: set[str], protected: set[str], seed: int, *, broken_yuan: bool = False) -> None:
        self.vocab_cf = {t.casefold() for t in vocab}
        self.vocab_orig = set(vocab)
        self.P = {p.casefold() for p in protected}
        q = sorted((p for p in self.P if len(p) >= 4 and p.isalpha()), key=lambda x: (-len(x), x))
        self.Q = re.compile("|".join(re.escape(p) for p in q), re.IGNORECASE) if q else None
        letters = sorted(set(string.ascii_lowercase) - FIXED)
        perm = letters[:]
        random.Random(seed).shuffle(perm)
        self.sigma = dict(zip(letters, perm))
        perm2 = letters[:]
        random.Random(seed + 1).shuffle(perm2)
        self.sigma2 = dict(zip(letters, perm2))
        self.broken_yuan = broken_yuan

    def _cipher(self, w: str, table: dict[str, str]) -> str:
        out = []
        for ch in w:
            c = table.get(ch.lower(), ch.lower())
            out.append(c.upper() if ch.isupper() else c)
        return "".join(out)

    def _run(self, w: str) -> str:
        lw = w.casefold()
        if lw in self.P or lw not in self.vocab_cf or w in PRONOUNS:
            return w
        table = self.sigma2 if (self.broken_yuan and "yuan" in lw) else self.sigma
        if self.Q is None:
            return self._cipher(w, table)
        out, pos = [], 0
        for m in self.Q.finditer(w):
            out.append(self._cipher(w[pos : m.start()], table))
            out.append(m.group(0))  # protected substring preserved
            pos = m.end()
        out.append(self._cipher(w[pos:], table))
        return "".join(out)

    def rename(self, text: str) -> str:
        return TOKEN.sub(lambda m: self._run(m.group(0)), text)

    def rename_with_map(self, text: str):
        return self.rename(text), IdMap()

    @property
    def mapping(self) -> dict[str, str]:
        return {t: self.rename(t) for t in self.vocab_orig}


def honorific_words() -> set[str]:
    w = {x for h in _HONORIFIC_PREFIXES for x in h.rstrip(".").lower().split()}
    w |= {s.lstrip("-").lower() for s in _HONORIFIC_SUFFIXES} | {"the", "a", "an"}
    return w


def corpus_lower_tokens(db: str) -> set[str]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    toks: set[str] = set()
    for (bj,) in con.execute("select blocks_json from chapter where novel_id=?", (T4.NOVEL,)):
        for b in json.loads(bj):
            toks.update(t.lower() for t in TOKEN.findall(b["text"]))
    con.close()
    return toks


def squash(s: str) -> str:
    return re.sub(r"[\s\-_']", "", s).casefold().rstrip("s")


def classify_violations(gate: dict, surfaces: set[str]) -> dict:
    by_key: dict[str, list[str]] = defaultdict(list)
    for s in sorted(surfaces):
        by_key[comparison_key(s)].append(s)
    cls: Counter = Counter()
    for v in gate["G2_violations"]:
        m = re.match(r"(orig|renamed)-class '(.*)' (splits|merges)", v)
        if m and m.group(1) == "orig":
            mem = by_key.get(m.group(2), [])
            cls["engine" if len(mem) > 1 and len({squash(x) for x in mem}) == 1 else "renamer"] += 1
        else:
            cls["renamer"] += 1
    for s in gate["G1_display_violations"]:
        cls["engine" if len(by_key.get(comparison_key(s), [])) > 1 else "renamer"] += 1
    return dict(cls)


def build(db: str):
    _pi3, protected, vocab, surfaces = T4.build_pi(db)  # protected already includes common lower-case words
    protected = set(protected) | honorific_words()
    pi = CipherRenamer(vocab, protected, T4.SEED)
    return pi, protected, vocab, surfaces


def full_gate(pi: CipherRenamer, surfaces: set[str], protected: set[str], db: str) -> dict:
    g = T4.commutation_gate(pi, surfaces, protected)
    seen: dict[str, str] = {}
    g4 = []
    for t in sorted(pi.vocab_cf):
        r = pi.rename(t)
        if r in seen and seen[r] != t:
            g4.append(f"{seen[r]!r} and {t!r} -> same")
        seen[r] = t
    existing = corpus_lower_tokens(db)
    changed = [t for t in pi.vocab_cf if pi.rename(t) != t]
    g5 = [t for t in changed if pi.rename(t) in existing or pi.rename(t) in pi.P]
    g.update(G4_injectivity_violations=g4[:50], G4_count=len(g4), G5_collision_count=len(g5),
             vocab_tokens_changed=len(changed), vocab_tokens=len(pi.vocab_cf))
    g["passed"] = bool(g["passed"] and not g4 and not g5)
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-db", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--gate-only", action="store_true")
    ap.add_argument("--out", default="data/eval/chimera/t4_v4_results.json")
    args = ap.parse_args()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    pi, protected, vocab, surfaces = build(args.base_db)
    gate = full_gate(pi, surfaces, protected, args.base_db)
    summary = {k: v for k, v in gate.items()
               if k.endswith("count") or k in ("surfaces", "passed", "vocab_tokens_changed", "vocab_tokens")}
    print("commutation gate v4:", json.dumps(summary), flush=True)
    head = {"prereg": "PREREG_T4_renaming_validity_v4.md (single attempt; no v5)", "commutation_gate": gate}
    if not gate["passed"]:
        head["violation_classes_engine_vs_renamer"] = classify_violations(gate, surfaces)
        head["status"] = "GATE_FAILED_NO_RUN"
        Path(args.out).write_text(json.dumps(head, indent=2) + "\n")
        print("GATE FAILED: no resolver run; T4 closed (no v5). classes:", head["violation_classes_engine_vs_renamer"])
        return 2
    if args.gate_only:
        head["status"] = "GATE_PASSED_GATE_ONLY"
        Path(args.out).write_text(json.dumps(head, indent=2) + "\n")
        print("gate passed (gate-only mode)")
        return 0
    ident = T4.Renamer({})
    broken = CipherRenamer(vocab, protected, T4.SEED, broken_yuan=True)
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
