"""E5. Does the gazetteer compound beyond repetition? Pre-declaration:
docs/research/ENGINEERING_NOVELTY_PROBE/E5_gazetteer_compounding_null_model.md (written before this ran).

LABEL PROVENANCE: SYSTEM-INTERNAL (no labels). Resolver loop only (volume passes off), stored mentions held fixed.
Counts, shares and ids only; no mention text is written (surface keys are used in memory and never serialised).
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eng_probe_common as C  # noqa: E402
from eng_probe_e1_prefix_causality import wilson  # noqa: E402
from echotales.pipeline.ingest.normalize import comparison_key  # noqa: E402


def spearman(x: list[float], y: list[float]) -> float:
    # average ranks for ties: argsort-of-argsort ranks broke ties by position and inflated rho on binary outcomes
    from scipy.stats import rankdata

    rx, ry = rankdata(x), rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def load_groups(db: str, nid: str) -> list[dict]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    groups: dict[tuple, dict] = {}
    for r in con.execute("select id, chapter, block_index, offset, text, local_group_id, target_id, method from mention "
                         "where novel_id=? order by chapter, block_index, offset", (nid,)):
        key = (r["chapter"], r["local_group_id"] or r["id"])
        g = groups.setdefault(key, dict(chapter=r["chapter"], keys=set(), target=r["target_id"], method=r["method"], n=0))
        g["keys"].add(comparison_key(r["text"]))
        g["n"] += 1
        if r["target_id"] and not g["target"]:
            g["target"], g["method"] = r["target_id"], r["method"]
    # final-graph ownership of each surface key by READER-stamped bindings
    owners: dict[str, set] = defaultdict(set)
    for r in con.execute("select alias, target_id from alias_binding where novel_id=? and observer_id='READER'", (nid,)):
        owners[comparison_key(r["alias"])].add(r["target_id"])
    con.close()
    ordered = sorted(groups.values(), key=lambda g: g["chapter"])  # stable: within a chapter, first-mention order
    return ordered, owners


def seen_before_flags(order: list[dict]) -> list[bool]:
    seen: set[str] = set()
    out = []
    for g in order:
        out.append(bool(g["keys"] & seen))
        if g["target"]:
            seen |= g["keys"]
    return out


def decile_shares(flags: list[bool], n_bins: int = 5) -> list[float]:
    edges = np.linspace(0, len(flags), n_bins + 1).astype(int)
    return [float(np.mean(flags[a:b])) if b > a else float("nan") for a, b in zip(edges[:-1], edges[1:], strict=True)]


def string_identity_baseline(db: str, nid: str) -> dict:
    """How much of the resolver's partition is just 'same normalised string -> same entity'?

    Id-free and label-free: compares the resolver's partition of its LINKED mentions with the partition by
    comparison_key(text) (the repo's own string normaliser). No text is stored.
    """
    from eng_probe_e1_prefix_causality import ari

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = [(comparison_key(r[0]), r[1], r[2]) for r in con.execute(
        "select text, target_id, method from mention where novel_id=? and target_id is not null", (nid,))]
    con.close()
    key_ents: dict[str, Counter] = defaultdict(Counter)
    ent_keys: dict[str, Counter] = defaultdict(Counter)
    for k, t, _m in rows:
        key_ents[k][t] += 1
        ent_keys[t][k] += 1
    n = len(rows)
    string_determined = sum(1 for k, t, _m in rows if key_ents[k].most_common(1)[0][0] == t)
    alias_mentions = [(k, t, m) for k, t, m in rows if ent_keys[t].most_common(1)[0][0] != k]
    return dict(
        linked_mentions=n, distinct_surface_keys=len(key_ents), entities=len(ent_keys),
        surface_keys_held_by_more_than_one_entity=sum(1 for c in key_ents.values() if len(c) > 1),
        mentions_whose_entity_is_the_majority_entity_of_their_surface=string_determined,
        string_determined_share=round(string_determined / n, 5), string_determined_wilson=wilson(string_determined, n),
        mentions_in_a_non_dominant_surface_of_their_entity=len(alias_mentions),
        non_dominant_surface_share=round(len(alias_mentions) / n, 5),
        non_dominant_surface_methods=dict(Counter(m for _k, _t, m in alias_mentions)),
        ari_resolver_vs_surface_key_partition=round(ari([t for _k, t, _m in rows], [k for k, _t, _m in rows]), 5),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--perms", type=int, default=200)
    args = ap.parse_args()
    nid = args.novel
    db = C.fresh_copy(C.DBS[nid], C.SCRATCH / "eng", f"{nid}_e5")
    n_ch = len(C.Store(db).chapter_numbers(nid))
    rep = C.run_resolve(db, nid, chapters=C.ChapterRange(0, n_ch + 1000))
    groups, owners = load_groups(db, nid)
    n_bins = 5
    resolved = [g for g in groups if g["target"]]
    exact = [g["method"] == "GAZETTEER_EXACT" for g in groups]
    linked = [bool(g["target"]) for g in groups]
    scored = [g["method"] == "SCORED" for g in groups]
    pred = seen_before_flags(groups)
    out: dict = dict(probe="E5 gazetteer compounding vs repetition null", label_provenance="SYSTEM-INTERNAL, no labels",
                     novel=nid, chapters=n_ch, groups=len(groups), groups_linked=sum(linked),
                     method_counts=dict(Counter(g["method"] for g in groups)))
    edges = np.linspace(0, len(groups), n_bins + 1).astype(int)
    rows = []
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        seg = groups[a:b]
        n = len(seg)
        ex = sum(1 for g in seg if g["method"] == "GAZETTEER_EXACT")
        sc = sum(1 for g in seg if g["method"] == "SCORED")
        sb = sum(pred[a:b])
        amb = sum(1 for g in seg if g["method"] == "GAZETTEER_EXACT"
                  and any(len(owners.get(k, ())) >= 2 for k in g["keys"]))
        rows.append(dict(
            chapters=[seg[0]["chapter"], seg[-1]["chapter"]], groups=n, exact_match=ex,
            exact_share=round(ex / n, 4), exact_wilson=wilson(ex, n), scorer_reached_share=round(sc / n, 4),
            seen_before_share=round(sb / n, 4), exact_given_seen_before=round(
                sum(1 for g, p in zip(seg, pred[a:b], strict=True) if p and g["method"] == "GAZETTEER_EXACT") / max(1, sb), 4),
            ambiguous_surface_exact_links=amb, ambiguous_share_of_exact=round(amb / ex, 4) if ex else None,
            ambiguous_wilson=wilson(amb, ex)))
    out["by_fifth_of_groups_in_reading_order"] = rows
    # trend with bootstrap over groups
    idx = np.arange(len(groups)) / len(groups)
    rho = spearman(list(idx), [float(e) for e in exact])
    rng = np.random.default_rng(20261016)
    boots = []
    arr_e = np.array(exact, dtype=float)
    for _ in range(500):
        s = rng.integers(0, len(groups), len(groups))
        boots.append(spearman(list(idx[s]), list(arr_e[s])))
    out["exact_match_trend_spearman_over_groups"] = dict(rho=round(rho, 4), boot95=[round(float(np.nanpercentile(boots, 2.5)), 4),
                                                                                     round(float(np.nanpercentile(boots, 97.5)), 4)])
    # null: permute whole chapters; the seen-before share by fifth of groups
    by_ch: dict[float, list[dict]] = defaultdict(list)
    for g in groups:
        by_ch[g["chapter"]].append(g)
    chs = sorted(by_ch)
    real = decile_shares(pred, n_bins)
    perm_rows = []
    prng = random.Random(7)
    for _ in range(args.perms):
        order = chs[:]
        prng.shuffle(order)
        flat = [g for c in order for g in by_ch[c]]
        perm_rows.append(decile_shares(seen_before_flags(flat), n_bins))
    pm = np.array(perm_rows)
    out["seen_before_share_null"] = dict(
        real=[round(x, 4) for x in real], permuted_mean=[round(float(x), 4) for x in pm.mean(0)],
        permuted_lo95=[round(float(x), 4) for x in np.percentile(pm, 2.5, axis=0)],
        permuted_hi95=[round(float(x), 4) for x in np.percentile(pm, 97.5, axis=0)],
        real_outside_band_fifths=[i for i in range(n_bins) if real[i] < np.percentile(pm[:, i], 2.5) or real[i] > np.percentile(pm[:, i], 97.5)],
        permutations=args.perms)
    # how much of the exact-match share is predicted by 'surface was linked before'
    seen_total = sum(pred)
    out["repetition_account"] = dict(
        groups_whose_surface_was_seen_before=seen_total, of_which_exact_match=sum(1 for g, p in zip(groups, pred, strict=True) if p and g["method"] == "GAZETTEER_EXACT"),
        exact_groups_total=sum(exact), exact_groups_whose_surface_was_not_seen_before=sum(1 for g, p in zip(groups, pred, strict=True) if (not p) and g["method"] == "GAZETTEER_EXACT"))
    out["resolve_report_by_window_gazetteer_share"] = {
        str(w): round(c.get("GAZETTEER_EXACT", 0) / max(1, sum(c.values())), 4) for w, c in rep["report"]["by_window"].items()}
    out["string_identity_baseline"] = string_identity_baseline(db, nid)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out["string_identity_baseline"], indent=1))
    print(json.dumps({k: out[k] for k in ("novel", "groups", "method_counts", "exact_match_trend_spearman_over_groups", "seen_before_share_null", "repetition_account")}, indent=1))
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
