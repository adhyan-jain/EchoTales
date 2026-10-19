"""T4 renaming-validity runner (implements PREREG_T4_renaming_validity.md v1).

Runs the repo's deterministic resolver (no LLM) on scratch copies of the RI
database under five conditions and compares per-mention decisions. The owner's
database is never opened for writing: every run starts from a fresh copy of
`--base-db`, which must itself be a scratch copy. Detection is held fixed: the
resolver is run on the existing detected mentions.

Conditions (PREREG_T4 section 4):
    O1  original            baseline decisions
    O2  original, 2nd copy  determinism: must equal O1 exactly
    I   identity pi         transformation-code sanity: must equal O1 exactly
    R   renamed (pi)        the test
    N   broken pi           non-compositional negative control

Nothing here tunes pi on a result. The seed and the vocabulary rules are the
ones frozen in the pre-registration.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from math import sqrt
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renaming import PRONOUNS, TOKEN, BrokenYuanRenamer, Renamer  # noqa: E402

from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.anaphora.local import _KINSHIP_TERMS  # noqa: E402
from echotales.pipeline.ingest.sources import get_source  # noqa: E402
from echotales.pipeline.ingest.normalize import (  # noqa: E402
    _HONORIFIC_PREFIXES,
    _HONORIFIC_SUFFIXES,
    comparison_key,
    display_label,
    strip_honorifics,
)
from echotales.pipeline.mentions.alias_type import _ROLE_NOUNS, _TRANSFERABLE_TITLE_NOUNS  # noqa: E402
from echotales.pipeline.mentions.gazetteer import AMBIGUITY_BLOCKLIST  # noqa: E402
from echotales.pipeline.mentions.induce import load_or_seed  # noqa: E402
from echotales.pipeline.resolve import resolve_novel  # noqa: E402

NOVEL = "reverend-insanity"
SEED = 20261015
STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "by", "for", "with", "from", "as", "is", "was",
    "are", "were", "be", "been", "it", "its", "this", "that", "these", "those", "if", "then", "so", "no", "not", "yes",
    "who", "what", "when", "where", "why", "how", "all", "one", "two", "three", "chapter", "sir", "madam", "mr", "mrs",
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d, (c + r) / d


# ---- vocabulary and pi -------------------------------------------------------
def build_pi(db: str) -> tuple[Renamer, set[str], set[str], set[str]]:
    """pi per PREREG_T4 v2 section 1; also returns every distinct name surface for the gate."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    vocab: set[str] = set()
    surfaces: set[str] = set()
    for sql in (
        "select canonical_label from self_entity where novel_id=?",
        "select alias from alias_binding where novel_id=?",
        "select text from mention where novel_id=? and alias_type='RIGID_NAME'",
    ):
        for (s,) in con.execute(sql, (NOVEL,)):
            surfaces.add(s)
            vocab.update(TOKEN.findall(s))
    vocab = {t for t in vocab if t[:1].isupper() and len(t) >= 2}
    existing: set[str] = {t.lower() for t in vocab}
    lower_counts: Counter = Counter()
    for (bj,) in con.execute("select blocks_json from chapter where novel_id=?", (NOVEL,)):
        for b in json.loads(bj):
            toks = TOKEN.findall(b["text"])
            existing.update(t.lower() for t in toks)
            lower_counts.update(t for t in toks if t[:1].islower())
    con.close()
    # PREREG_T4 v3 section 1 item 2: words that occur 5+ times as ordinary
    # lower-case tokens are common words, never renamed.
    common_lower = {w for w, c in lower_counts.items() if c >= 5}
    # Honorific/article words the repo's normaliser strips (v2 section 1 item 3):
    # never renamed, and never produced as a replacement.
    honorific_words = {w for h in _HONORIFIC_PREFIXES for w in h.rstrip(".").lower().split()}
    honorific_words |= {s.lstrip("-").lower() for s in _HONORIFIC_SUFFIXES} | {"the", "a", "an"}
    honorific_tokens = {t.lower() for t in vocab if strip_honorifics(t + " x", strip_articles=True) != t + " x"}
    protected = (
        {w.lower() for w in AMBIGUITY_BLOCKLIST}
        | {w for t in _TRANSFERABLE_TITLE_NOUNS for w in t.split()}
        | {w.lower() for w in _ROLE_NOUNS}
        | {w.lower() for w in _KINSHIP_TERMS}
        | STOP
        | honorific_tokens
    )
    pi = Renamer.build(
        vocab, protected_lower=protected, existing_lower=existing | honorific_words, seed=SEED,
        common_lower=common_lower,
    )
    return pi, protected | common_lower, vocab, surfaces


def commutation_gate(pi: Renamer, surfaces: set[str], protected: set[str]) -> dict:
    """PREREG_T4 v2 section 2: pi must commute with the repo's normalisers.

    G1 display_label([pi(s)]) == pi(display_label([s])) for every surface.
    G2 comparison_key classes map one-to-one under pi.
    G3 whole-token containment of one surface in another survives pi.
    Run BEFORE any resolver call; any violation stops the run.
    """
    g1 = [s for s in sorted(surfaces) if display_label([pi.rename(s)]) != pi.rename(display_label([s]))]
    fwd: dict[str, set[str]] = defaultdict(set)
    back: dict[str, set[str]] = defaultdict(set)
    for s in surfaces:
        ko, kr = comparison_key(s), comparison_key(pi.rename(s))
        fwd[ko].add(kr)
        back[kr].add(ko)
    g2 = sorted(
        {f"orig-class {k!r} splits" for k, v in fwd.items() if len(v) > 1}
        | {f"renamed-class {k!r} merges" for k, v in back.items() if len(v) > 1}
    )
    tokset = {s: tuple(TOKEN.findall(s)) for s in surfaces}
    by_len = sorted((t for t in set(tokset.values()) if t), key=len)
    g3: list[str] = []
    seen = set(by_len)
    for t in by_len:
        for i in range(len(t)):
            for j in range(i + 1, len(t) + 1):
                sub = t[i:j]
                if sub != t and sub in seen:
                    rt, rs = tuple(pi.rename(x) for x in t), tuple(pi.rename(x) for x in sub)
                    if not any(rt[k : k + len(rs)] == rs for k in range(len(rt) - len(rs) + 1)):
                        g3.append(f"{' '.join(sub)!r} in {' '.join(t)!r}")
    return {
        "surfaces": len(surfaces),
        "G1_display_violations": g1[:50],
        "G1_count": len(g1),
        "G2_violations": g2[:50],
        "G2_count": len(g2),
        "G3_violations": g3[:50],
        "G3_count": len(g3),
        "passed": not (g1 or g2 or g3),
    }


# ---- database transformation ---------------------------------------------------
def transform_db(path: str, pi: Renamer, *, broken: bool = False) -> dict:
    """Rewrite blocks, mentions and spans of a SCRATCH database under pi.

    Offsets are recomputed through a monotone offset map. A mention whose
    original offset already fails to index its own text (a measured repo
    defect: `Mention.offset` is sometimes one character early) is counted as
    `preexisting_offset_defect`, never as a defect of pi.
    """
    con = sqlite3.connect(path)
    maps: dict[tuple[float, int], tuple[str, str, object]] = {}
    for num, bj in con.execute("select number, blocks_json from chapter where novel_id=?", (NOVEL,)).fetchall():
        blocks = json.loads(bj)
        for b in blocks:
            old = b["text"]
            new, omap = pi.rename_with_map(old)
            maps[(float(num), b["index"])] = (old, new, omap)
            b["text"] = new
            if b.get("italic_ranges"):
                b["italic_ranges"] = [[omap.map_offset(s), omap.map_offset(e)] for s, e in b["italic_ranges"]]
        con.execute("update chapter set blocks_json=? where novel_id=? and number=?", (json.dumps(blocks), NOVEL, num))

    stats: Counter = Counter()
    flags: dict[str, str] = {}
    for mid, ch, bi, off, text in con.execute(
        "select id, chapter, block_index, offset, text from mention where novel_id=?", (NOVEL,)
    ).fetchall():
        old, new, omap = maps[(float(ch), bi)]
        if old[off : off + len(text)] == text:
            ns, ne = omap.map_offset(off), omap.map_offset(off + len(text))
            nt = new[ns:ne]
            if not broken and nt != pi.rename(text):
                flags[mid] = "offset_error"
                stats["offset_error"] += 1
            else:
                stats["clean"] += 1
        else:
            ns, nt = omap.map_offset(off), pi.rename(text)
            flags[mid] = "preexisting_offset_defect"
            stats["preexisting_offset_defect"] += 1
        con.execute("update mention set text=?, offset=? where id=?", (nt, ns, mid))
    for sid, ch, bi, s, e in con.execute("select id, chapter, block_index, start, end from span where novel_id=?", (NOVEL,)).fetchall():
        if (float(ch), bi) not in maps:
            continue
        _, new, omap = maps[(float(ch), bi)]
        ns, ne = omap.map_offset(s), omap.map_offset(e)
        con.execute("update span set start=?, end=?, text=? where id=?", (ns, ne, new[ns:ne], sid))
    con.commit()
    con.close()
    return {"counts": dict(stats), "flags": flags}


def transform_lexicon(lex, pi: Renamer):
    kw = {}
    for f in dataclasses.fields(lex):
        v = getattr(lex, f.name)
        if isinstance(v, set):
            kw[f.name] = {pi.rename(x) for x in v}
        elif isinstance(v, tuple) and v and isinstance(v[0], str):
            kw[f.name] = tuple(pi.rename(x) for x in v)
        else:
            kw[f.name] = v
    return type(lex)(**kw)


# ---- one run -----------------------------------------------------------------------
def run_condition(name: str, base_db: str, workdir: Path, pi: Renamer | None, *, broken: bool, smoke: int) -> dict:
    work = workdir / f"{name}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(work) + suffix).unlink(missing_ok=True)
    shutil.copy(base_db, work)
    if smoke:
        con = sqlite3.connect(work)
        for t in ("mention", "span", "chapter"):
            col = "number" if t == "chapter" else "chapter"
            con.execute(f"delete from {t} where {col} > ?", (smoke,))
        con.commit()
        con.close()
    info = {"counts": {}, "flags": {}}
    lex = load_or_seed(get_source(NOVEL).lexicon)
    if pi is not None:
        info = transform_db(str(work), pi, broken=broken)
        lex = transform_lexicon(lex, pi)
    store = Store(str(work))
    t0 = time.time()
    report = resolve_novel(NOVEL, store, lexicon=lex, force_rewipe=True)
    secs = time.time() - t0
    labels = {r[0]: r[1] for r in store.conn.execute("select id, canonical_label from self_entity where novel_id=?", (NOVEL,))}
    decisions = {}
    for mid, tid, method, conf in store.conn.execute("select id, target_id, method, confidence from mention where novel_id=?", (NOVEL,)):
        decisions[mid] = (labels.get(tid) if tid else None, method, round(conf or 0.0, 3))
    store.close()
    return {"decisions": decisions, "seconds": round(secs, 1), "summary": report.summary(), **info}


# ---- comparison --------------------------------------------------------------------------
def compare(o: dict, r: dict, pi: Renamer | None, flags: dict, protected: set[str], mapping_keys: set[str]) -> dict:
    ids = sorted(set(o) & set(r))
    ren = (lambda s: pi.rename(s)) if pi is not None else (lambda s: s)
    agree, changed = [], []
    for i in ids:
        lo, _mo, _co = o[i]
        lr, _mr, _cr = r[i]
        same = (lo is None) == (lr is None) and (lo is None or lr == ren(lo))
        (agree if same else changed).append(i)
    n = len(ids)
    # B-cubed over mentions resolved in both runs
    both = [i for i in ids if o[i][0] is not None and r[i][0] is not None]
    co_o, co_r = defaultdict(set), defaultdict(set)
    for i in both:
        co_o[o[i][0]].add(i)
        co_r[r[i][0]].add(i)
    p = rc = 0.0
    for i in both:
        a, b = co_o[o[i][0]], co_r[r[i][0]]
        inter = len(a & b)
        p += inter / len(b)
        rc += inter / len(a)
    b3 = (2 * (p / len(both)) * (rc / len(both)) / ((p + rc) / len(both))) if both else 1.0
    return {
        "n": n,
        "agree": len(agree),
        "agreement": len(agree) / n,
        "wilson95": [round(x, 4) for x in wilson(len(agree), n)],
        "bcubed_f1": round(b3, 4),
        "same_method_share": round(sum(o[i][1] == r[i][1] for i in ids) / n, 4),
        "mean_abs_conf_change": round(sum(abs(o[i][2] - r[i][2]) for i in ids) / n, 5),
        "changed_ids": changed,
    }


def classify(
    changed: list[str], mentions: dict[str, str], flags: dict, protected: set[str], mapping_keys: set[str],
    base: dict | None = None, run: dict | None = None, ren=None,
) -> Counter:
    """PREREG_T4 v2 sections 3: offset error, pre-existing offset defect,
    morphology artefact (label differs from pi(label) only by a trailing "s"),
    lexicon gap, evidence loss -- in that order."""
    out: Counter = Counter()
    for i in changed:
        f = flags.get(i)
        lo = base[i][0] if base else None
        lr = run[i][0] if run else None
        if f == "offset_error":
            out["offset_error"] += 1
        elif f == "preexisting_offset_defect":
            out["preexisting_offset_defect"] += 1
        elif lo and lr and ren and {ren(lo), lr} and abs(len(ren(lo)) - len(lr)) == 1 and (
            ren(lo) == lr + "s" or lr == ren(lo) + "s"
        ):
            out["morphology_artefact"] += 1
        else:
            toks = [t for t in TOKEN.findall(mentions.get(i, "")) if t[:1].isupper() and len(t) >= 2]
            if any(t not in mapping_keys and t.lower() not in protected and t not in PRONOUNS for t in toks):
                out["lexicon_gap"] += 1
            else:
                out["evidence_loss"] += 1
    return out


def clustered_bootstrap(o: dict, ids_changed: set[str], draws: int = 2000) -> list[float]:
    groups: dict[str, list[str]] = defaultdict(list)
    for i, (lab, _, _) in o.items():
        groups[lab or f"__unresolved__{i}"].append(i)
    keys = sorted(groups)
    sizes = [len(groups[k]) for k in keys]
    bad = [sum(1 for i in groups[k] if i in ids_changed) for k in keys]
    rng = random.Random(SEED)
    vals = []
    for _ in range(draws):
        pick = [rng.randrange(len(keys)) for _ in keys]
        tot = sum(sizes[j] for j in pick)
        vals.append(1 - sum(bad[j] for j in pick) / tot)
    vals.sort()
    return [round(vals[int(0.025 * draws)], 4), round(vals[int(0.975 * draws)], 4)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-db", required=True, help="a SCRATCH copy of the RI database")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--smoke", type=int, default=0, help="restrict to chapters <= N; runtime check only, not used for any decision")
    ap.add_argument("--conditions", default="O1,O2,I,R,N")
    ap.add_argument("--out", default="data/eval/chimera/t4_results.json")
    args = ap.parse_args()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    pi, protected, _vocab, surfaces = build_pi(args.base_db)
    gate = commutation_gate(pi, surfaces, protected)
    print("commutation gate:", json.dumps({k: v for k, v in gate.items() if k.endswith("count") or k in ("surfaces", "passed")}), flush=True)
    if not gate["passed"]:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"prereg": "PREREG_T4 v3 (sha256 15573544f317f772bab9f4e2358afbc1bb2bf6cae4974884e18f75697af267c4)", "commutation_gate": gate, "status": "GATE_FAILED_NO_RUN"}, indent=2) + "\n")
        print("GATE FAILED: no resolver run (PREREG_T4 v2 section 2). Report as a pi defect; fix only in v3.")
        return 2
    ident = Renamer({})
    broken = BrokenYuanRenamer(dict(pi.mapping))
    plan = {"O1": (None, False), "O2": (None, False), "I": (ident, False), "R": (pi, False), "N": (broken, True)}
    runs: dict[str, dict] = {}
    for name in args.conditions.split(","):
        renamer, is_broken = plan[name]
        t0 = time.time()
        runs[name] = run_condition(name, args.base_db, workdir, renamer, broken=is_broken, smoke=args.smoke)
        print(f"{name}: {runs[name]['seconds']}s resolve, {time.time() - t0:.0f}s total, mentions={len(runs[name]['decisions'])}", flush=True)

    base = runs["O1"]["decisions"]
    mention_text = {}
    con = sqlite3.connect(f"file:{args.base_db}?mode=ro", uri=True)
    for mid, text in con.execute("select id, text from mention where novel_id=?", (NOVEL,)):
        mention_text[mid] = text
    con.close()
    keys = set(pi.mapping)
    result = {
        "prereg": "docs/research/preregistrations/PREREG_T4_renaming_validity_v3.md (sha256 15573544f317f772bab9f4e2358afbc1bb2bf6cae4974884e18f75697af267c4)",
        "commutation_gate": gate,
        "smoke_chapters": args.smoke or None,
        "pi_vocabulary_size": len(pi.mapping),
        "pi_seed": SEED,
        "conditions": {},
    }
    for name, (renamer, is_broken) in plan.items():
        if name == "O1" or name not in runs:
            continue
        flags = runs[name].get("flags", {})
        cmp = compare(base, runs[name]["decisions"], None if name == "O2" else renamer, flags, protected, keys)
        cls = classify(
            cmp["changed_ids"], mention_text, flags, protected, keys,
            base=base, run=runs[name]["decisions"], ren=None if name == "O2" else renamer.rename,
        )
        entry = {k: v for k, v in cmp.items() if k != "changed_ids"}
        entry["changed"] = len(cmp["changed_ids"])
        entry["changed_classification"] = dict(cls)
        entry["transform_counts"] = runs[name].get("counts")
        entry["entity_clustered_bootstrap95"] = clustered_bootstrap(base, set(cmp["changed_ids"]))
        entry["resolve_seconds"] = runs[name]["seconds"]
        entry["example_changed_ids"] = cmp["changed_ids"][:20]
        result["conditions"][name] = entry
        print(name, json.dumps({k: entry[k] for k in ("n", "agree", "agreement", "wilson95", "bcubed_f1", "changed_classification")}), flush=True)
    result["o1_resolve_seconds"] = runs["O1"]["seconds"]
    result["o1_summary"] = runs["O1"]["summary"]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print("written", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
