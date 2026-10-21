"""E1. Prefix causality of the incremental resolver on real serials. Pre-declaration:
docs/research/ENGINEERING_PROBES.md (written before this ran).

LABEL PROVENANCE: SYSTEM-INTERNAL (no reference labels). Scratch copies only; CPU only; counts and ids only.

    python scripts/chimera/eng_probe_e1_prefix_causality.py --novel lord-of-the-mysteries --ks 5,10,20,30 --out <json>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eng_probe_common as C  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 5), round(min(1.0, c + h), 5)]


def ari(a: list, b: list) -> float:
    n = len(a)
    if n < 2:
        return 1.0
    cont: Counter = Counter(zip(a, b, strict=True))
    ra: Counter = Counter(a)
    rb: Counter = Counter(b)
    c2 = lambda x: x * (x - 1) / 2  # noqa: E731
    s_ij = sum(c2(v) for v in cont.values())
    s_a = sum(c2(v) for v in ra.values())
    s_b = sum(c2(v) for v in rb.values())
    exp = s_a * s_b / c2(n)
    mx = (s_a + s_b) / 2
    return 1.0 if mx == exp else (s_ij - exp) / (mx - exp)


def compare(pre: dict, full: dict, k: float) -> dict:
    ids = [i for i, v in pre["mentions"].items() if v[0] <= k]
    fm, pm = full["mentions"], pre["mentions"]
    same = 0
    cats: Counter = Counter()
    by_chapter: Counter = Counter()
    examples = []
    for i in ids:
        pt, ft = pm[i][1], fm[i][1]
        if pt == ft:
            same += 1
            continue
        if pt is None:
            cat = "unlinked_in_prefix__linked_in_full"
        elif ft is None:
            cat = "linked_in_prefix__unlinked_in_full"
        else:
            cat = "linked_to_different_entity"
        cats[(cat, pm[i][2], fm[i][2])] += 1
        by_chapter[int(pm[i][0])] += 1
        if len(examples) < 30:
            examples.append([i, pm[i][0], cat, pm[i][2], fm[i][2]])
    la = [pm[i][1] or f"U{i}" for i in ids]
    lb = [fm[i][1] or f"U{i}" for i in ids]
    pa = Counter((a[0], a[1], a[2], a[4]) for a in pre["aliases"] if a[2] <= k)
    fa = Counter((a[0], a[1], a[2], a[4]) for a in full["aliases"] if a[2] <= k)
    only_pre = sum((pa - fa).values())
    only_full = sum((fa - pa).values())
    n = len(ids)
    return dict(
        k=k, mentions_leq_k=n, same_target=same, disagree=n - same,
        disagree_rate=round((n - same) / n, 5) if n else None, disagree_wilson=wilson(n - same, n),
        ari=round(ari(la, lb), 5),
        linked_in_prefix=sum(1 for i in ids if pm[i][1]), linked_in_full=sum(1 for i in ids if fm[i][1]),
        categories=[[*key, v] for key, v in sorted(cats.items(), key=lambda kv: -kv[1])],
        disagree_by_chapter=dict(sorted(by_chapter.items())),
        alias_bindings_learned_leq_k=dict(prefix=sum(pa.values()), full=sum(fa.values()), only_in_prefix=only_pre,
                                          only_in_full=only_full),
        examples_mention_id_chapter_category_methods=examples,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--ks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default=str(C.SCRATCH / "eng"))
    args = ap.parse_args()
    nid = args.novel
    work = Path(args.workdir)
    src = C.DBS[nid]
    n_ch = len(C.Store(str(src)).chapter_numbers(nid))
    allch = C.ChapterRange(1, n_ch + 1000)
    ks = [int(x) for x in args.ks.split(",")]
    out: dict = dict(
        probe="E1 prefix causality of the resolver (graph level)", label_provenance="SYSTEM-INTERNAL, no labels",
        novel=nid, chapters=n_ch, ks=ks,
    )
    f0a = C.run_resolve(C.fresh_copy(src, work, f"{nid}_f0a"), nid, chapters=allch)
    f0b = C.run_resolve(C.fresh_copy(src, work, f"{nid}_f0b"), nid, chapters=allch)
    out["determinism_F0_twice"] = compare(f0a, f0b, 10**9) | {"examples_mention_id_chapter_category_methods": None}
    f1 = C.run_resolve(C.fresh_copy(src, work, f"{nid}_f1"), nid, chapters=None)  # standard run, volume passes on
    nowin = C.run_resolve(C.fresh_copy(src, work, f"{nid}_nowin"), nid, chapters=allch, window_size=10**6)
    out["F0_report"] = f0a["report"] | {"by_window": f0a["report"]["by_window"]}
    out["by_k"] = {}
    for k in ks:
        pk = C.run_resolve(C.fresh_copy(src, work, f"{nid}_p{k}"), nid, chapters=C.ChapterRange(1, k))
        out["by_k"][str(k)] = dict(
            prefix_vs_F0=compare(pk, f0a, k),
            prefix_vs_F0_single_final_sweep_only=compare(pk, nowin, k),
            F1_volume_passes_vs_F0_restricted=compare(f1, f0a, k),
            prefix_report={x: pk["report"][x] for x in ("groups", "linked", "created", "deferred", "recovered", "unresolved", "entities")},
        )
        r = out["by_k"][str(k)]["prefix_vs_F0"]
        print(nid, "k=", k, "n=", r["mentions_leq_k"], "disagree=", r["disagree"], "ari=", r["ari"],
              "alias only_pre/full:", r["alias_bindings_learned_leq_k"]["only_in_prefix"], r["alias_bindings_learned_leq_k"]["only_in_full"],
              flush=True)
    Path(args.out).write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
