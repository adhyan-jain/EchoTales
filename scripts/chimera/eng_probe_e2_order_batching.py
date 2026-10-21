"""E2. Order, batching and re-run sensitivity of the incremental resolver. Pre-declaration:
docs/research/ENGINEERING_PROBES.md (written before this ran).

LABEL PROVENANCE: SYSTEM-INTERNAL. Scratch copies only; CPU only; counts and ids only.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eng_probe_common as C  # noqa: E402
from eng_probe_e1_prefix_causality import compare  # noqa: E402


def adjacent_swaps(nums: list[float], frac: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    out = list(nums)
    i = 0
    while i < len(out) - 1:
        if rng.random() < frac:
            out[i], out[i + 1] = out[i + 1], out[i]
            i += 2
        else:
            i += 1
    return out


def slim(c: dict) -> dict:
    keep = ("mentions_leq_k", "same_target", "disagree", "disagree_rate", "disagree_wilson", "ari", "linked_in_prefix",
            "linked_in_full", "categories", "disagree_by_chapter", "alias_bindings_learned_leq_k")
    d = {k: c[k] for k in keep}
    d["categories"] = d["categories"][:6]
    d["disagree_by_chapter"] = dict(list(d["disagree_by_chapter"].items())[:40])
    d["examples_first_10"] = c["examples_mention_id_chapter_category_methods"][:10]
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    nid = args.novel
    work = C.SCRATCH / "eng"
    src = C.DBS[nid]
    nums = [float(x) for x in C.Store(str(src)).chapter_numbers(nid)]
    allch = C.ChapterRange(0, max(nums) + 1000)
    out: dict = dict(probe="E2 order/batching/re-run sensitivity", label_provenance="SYSTEM-INTERNAL, no labels",
                     novel=nid, chapters=len(nums))
    ref = C.run_resolve(C.fresh_copy(src, work, f"{nid}_e2ref"), nid, chapters=allch)
    out["reference"] = dict(entities=ref["report"]["entities"], linked=ref["report"]["linked"],
                            deferred=ref["report"]["deferred"], unresolved=ref["report"]["unresolved"])
    big = 10**9
    # idempotence: resolve twice in place on the same DB file
    db = C.fresh_copy(src, work, f"{nid}_e2idem")
    C.run_resolve(db, nid, chapters=allch)
    again = C.run_resolve(db, nid, chapters=allch)
    out["idempotence_second_run_in_place"] = slim(compare(again, ref, big)) | dict(partition=C.partition_diff(again, ref))
    out["window_size"] = {}
    for w in (10, 20, 10**6):
        r = C.run_resolve(C.fresh_copy(src, work, f"{nid}_e2w{w}"), nid, chapters=allch, window_size=w)
        out["window_size"][str(w)] = slim(compare(r, ref, big)) | dict(entities=r["report"]["entities"], deferred=r["report"]["deferred"], partition=C.partition_diff(r, ref))
    out["adjacent_swaps_10pct"] = {}
    for seed in (0, 1, 2):
        order = adjacent_swaps(nums, 0.10, seed)
        n_moved = sum(1 for a, b in zip(order, nums, strict=True) if a != b)
        r = C.run_resolve(C.fresh_copy(src, work, f"{nid}_e2s{seed}"), nid, chapters=allch, chapter_order=order)
        out["adjacent_swaps_10pct"][str(seed)] = slim(compare(r, ref, big)) | dict(
            chapters_displaced=n_moved, entities=r["report"]["entities"], partition=C.partition_diff(r, ref))
    r = C.run_resolve(C.fresh_copy(src, work, f"{nid}_e2rev"), nid, chapters=allch, chapter_order=list(reversed(nums)))
    out["control_reversed_order"] = slim(compare(r, ref, big)) | dict(entities=r["report"]["entities"], partition=C.partition_diff(r, ref))
    Path(args.out).write_text(json.dumps(out, indent=2))
    for key in ("idempotence_second_run_in_place",):
        print(nid, key, out[key]["disagree"], out[key]["ari"])
    for w, v in out["window_size"].items():
        print(nid, "window", w, v["disagree"], v["ari"], v["entities"])
    for s, v in out["adjacent_swaps_10pct"].items():
        print(nid, "swap seed", s, "chapters displaced", v["chapters_displaced"], "id-disagree", v["disagree"], v["disagree_rate"], "ari", v["ari"], "ents", v["entities"], "partition-moved", v["partition"]["moved_max"], v["partition"]["moved_rate_max"], "link-only var/ref", v["partition"]["linked_only_in_variant"], v["partition"]["linked_only_in_reference"])
    v = out["control_reversed_order"]
    print(nid, "reversed id-disagree", v["disagree"], v["disagree_rate"], "ari", v["ari"], "ents", v["entities"], "ref ents", out["reference"]["entities"], "partition-moved", v["partition"]["moved_max"], v["partition"]["moved_rate_max"], "link-only var/ref", v["partition"]["linked_only_in_variant"], v["partition"]["linked_only_in_reference"])


if __name__ == "__main__":
    main()
