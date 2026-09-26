"""Why does the learned scorer link nothing? Evidence, not argument.

Read-only. Joins the captured evidence cache (`scoring_evidence`, one row per
(mention, candidate) pair the resolver actually scored) to the non-trivial
SILVER hard-case set, and answers, per gold mention:

  - was the correct entity among the retrieved candidates at all?  (retrieval)
  - if so, did the scorer rank it first?                           (ranking)
  - if first, was its probability high enough to link?             (threshold/
                                                                     calibration)
  - do the features separate correct from incorrect at all?        (features)

The starvation hypothesis is already closed (docs/results/NER_WINDOWING_RESULT.md): the
scorer links nothing on a 57% larger cache. This script asks what *does*
explain it, and must not presuppose the answer.

**Gold -> entity mapping, and why it is not `calibrate._identity_to_target`.**
That helper votes over the system's own links for a gold identity's mentions.
Hard-case identities carry 1-3 records each, so for them "the gold entity" would
largely be whatever the system linked -- circular for a ranking diagnosis. Here
an identity's base name (parenthetical note stripped) is mapped by majority
vote across the *entire* silver corpus, thousands of records, independent of any
single hard-case link. Identities with no silver support elsewhere are reported
as unmapped rather than guessed.

SILVER -- LLM-derived reference set (Claude), not human gold; no IAA.

Usage:
    python3 scripts/eval/scorer_diagnosis.py [--db data/db/reverend-insanity.db]
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from echotales.core.models import EvidenceVector
from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import _block_starts
from echotales.pipeline.eval.gold import SILVER_BANNER, read_gold
from echotales.pipeline.resolve.score import PrefilterVerdict, ScoringModel, prefilter

NOVEL = "reverend-insanity"
LINK_THRESHOLD = 0.80
FEATURES = [
    "declaration_match", "gazetteer_exact_match", "name_containment",
    "surface_similarity", "context_embedding_similarity",
    "speech_partner_compatibility", "temporal_validity", "co_presence_violation",
    "audience_scope_compatibility", "relationship_deictic_resolution",
    "first_attested_soft_prior",
]


def base_name(identity: str) -> str:
    return identity.split(" (")[0].strip().casefold()


def category(note: str) -> str:
    return note[1:note.index("]")] if note.startswith("[") and "]" in note else "uncategorised"


def auc(pos: list[float], neg: list[float]) -> float | None:
    """Mann-Whitney AUC: P(random positive > random negative), ties = 0.5."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))] if xs else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/db/reverend-insanity.db")
    ap.add_argument("--gold", nargs="+", default=[
        "data/gold/reverend-insanity-hardcases.jsonl",
        "data/gold/reverend-insanity-c1-c5.jsonl",
        "data/gold/reverend-insanity.jsonl"])
    ap.add_argument("--out", default="data/eval/scorer_diagnosis")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    store = Store(args.db)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    # --- system mentions in chapter-absolute coordinates ------------------
    mentions_by_ch: dict[float, list[tuple[int, str, str, str | None]]] = defaultdict(list)
    for ch in {r[0] for r in conn.execute("select distinct chapter from mention where novel_id=?", (NOVEL,))}:
        starts = _block_starts(store, NOVEL, ch)
        for mid, bi, off, text, tgt in conn.execute(
            "select id, block_index, offset, text, target_id from mention where novel_id=? and chapter=?",
            (NOVEL, ch),
        ):
            if bi in starts:
                mentions_by_ch[ch].append((starts[bi] + off, mid, text, tgt))

    def align(ch: float, offset: int, surface: str) -> list[tuple[str, str | None]]:
        """System mentions whose span overlaps the gold span.

        Overlap, not exact surface: an exact-match rule missed 11 of 68 hard
        cases whose system span only differed at the boundary -- gold
        `Chi Chen` vs system `Gu Yue Chi Chen`, gold `his uncle` vs `uncle`.
        Those are the same mention; boundary disagreement is not detection
        failure. Nearest-start first, so a long gold span picks its head.
        """
        g_lo, g_hi = offset, offset + len(surface)
        hits = [(abs(abs_off - offset), mid, tgt) for abs_off, mid, text, tgt in mentions_by_ch.get(ch, [])
                if abs_off < g_hi and abs_off + len(text) > g_lo]
        return [(mid, tgt) for _d, mid, tgt in sorted(hits)]

    # --- independent identity -> entity mapping over the whole silver corpus
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for path in ("data/gold/reverend-insanity.jsonl", "data/gold/reverend-insanity-c1-c5.jsonl"):
        for m in read_gold(path, novel_id=NOVEL).silver_only.entities_only.mentions:
            for _mid, tgt in align(m.chapter, m.offset, m.surface):
                if tgt:
                    votes[base_name(m.identity)][tgt] += 1
    name_to_target = {n: c.most_common(1)[0][0] for n, c in votes.items()}

    # --- evidence cache ---------------------------------------------------
    evidence: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    for mid, cand, fj in conn.execute(
        "select mention_id, candidate_id, features_json from scoring_evidence where novel_id=?", (NOVEL,)
    ):
        evidence[mid].append((cand, json.loads(fj)))

    model = ScoringModel()
    # Every silver file, each record tagged with its source. The hard-case
    # file is the only non-trivial one; the others are reported beside it so
    # the scorer can be diagnosed on enough pairs to mean something, never
    # blended into a single headline.
    hard, source = [], []
    for path in args.gold:
        for m in read_gold(path, novel_id=NOVEL).silver_only.entities_only.mentions:
            hard.append(m)
            source.append(Path(path).stem.replace("reverend-insanity", "ri") or "ri")

    cand_rows, case_rows = [], []
    all_scores, gold_scores, best_wrong_scores, margins = [], [], [], []
    feat_gold: dict[str, list[float]] = defaultdict(list)
    feat_wrong: dict[str, list[float]] = defaultdict(list)
    outcome = Counter()

    for i, g in enumerate(hard):
        cat, alias = category(g.note), g.alias_type.value
        gold_target = name_to_target.get(base_name(g.identity))
        aligned = align(g.chapter, g.offset, g.surface)
        row = {"case_id": i, "source": source[i], "chapter": g.chapter, "surface": g.surface, "category": cat,
               "alias_type": alias, "gold_target": gold_target or "", "system_target": "",
               "n_candidates": 0, "gold_rank": "", "gold_score": "", "best_wrong_score": "",
               "margin": "", "gold_prefilter": "", "outcome": ""}
        if not aligned:
            row["outcome"] = "mention_not_detected"
        elif gold_target is None:
            row["outcome"] = "gold_unmapped"
            row["system_target"] = aligned[0][1] or ""
        else:
            mid, sys_tgt = aligned[0]
            row["system_target"] = sys_tgt or ""
            cands = evidence.get(mid, [])
            row["n_candidates"] = len(cands)
            if not cands:
                row["outcome"] = "not_scored"
            else:
                scored = []
                for cand, feats in cands:
                    ev = EvidenceVector(**feats)
                    p = model.probability(ev)
                    verdict = prefilter(ev).verdict
                    is_gold = cand == gold_target
                    scored.append((p, cand, is_gold, verdict))
                    all_scores.append(p)
                    cand_rows.append({"case_id": i, "candidate": cand, "is_gold": int(is_gold),
                                      "prefilter": verdict.value, "raw_score": round(p, 4),
                                      **{f: feats.get(f, "") for f in FEATURES}})
                    for f in FEATURES:
                        (feat_gold if is_gold else feat_wrong)[f].append(float(feats.get(f, 0.0)))
                scored.sort(key=lambda t: -t[0])
                golds = [t for t in scored if t[2]]
                wrongs = [t for t in scored if not t[2]]
                if not golds:
                    row["outcome"] = "retrieval_failure"
                else:
                    gp = golds[0][0]
                    rank = [t[1] for t in scored].index(gold_target) + 1
                    bw = wrongs[0][0] if wrongs else 0.0
                    row.update(gold_rank=rank, gold_score=round(gp, 4),
                               best_wrong_score=round(bw, 4), margin=round(gp - bw, 4),
                               gold_prefilter=golds[0][3].value)
                    gold_scores.append(gp)
                    best_wrong_scores.append(bw)
                    margins.append(gp - bw)
                    if golds[0][3] is PrefilterVerdict.FORCE_LINK:
                        row["outcome"] = "prefilter_force_link"
                    elif golds[0][3] is PrefilterVerdict.BLOCK:
                        row["outcome"] = "prefilter_blocks_gold"
                    elif rank > 1:
                        row["outcome"] = "ranking_failure"
                    elif gp < LINK_THRESHOLD:
                        row["outcome"] = "ranked_first_below_threshold"
                    else:
                        row["outcome"] = "would_link"
        outcome[row["outcome"]] += 1
        case_rows.append(row)

    with (out / "candidates.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cand_rows[0].keys()) if cand_rows else ["case_id"])
        w.writeheader()
        w.writerows(cand_rows)
    with (out / "cases.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(case_rows[0].keys()))
        w.writeheader()
        w.writerows(case_rows)

    def dist(xs: list[float]) -> dict[str, float | int]:
        return {"n": len(xs), "min": round(min(xs), 4) if xs else None,
                "p50": round(pct(xs, .5), 4) if xs else None, "p90": round(pct(xs, .9), 4) if xs else None,
                "max": round(max(xs), 4) if xs else None,
                "mean": round(statistics.fmean(xs), 4) if xs else None}

    by_cat: dict[str, Counter[str]] = defaultdict(Counter)
    by_alias: dict[str, Counter[str]] = defaultdict(Counter)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for r in case_rows:
        by_source[r["source"]][r["outcome"]] += 1
        if r["source"] == "ri-hardcases":
            by_cat[r["category"]][r["outcome"]] += 1
            by_alias[r["alias_type"]][r["outcome"]] += 1

    summary = {
        "banner": SILVER_BANNER,
        "db": args.db, "hard_cases": len(hard), "link_threshold": LINK_THRESHOLD,
        "weights": model.weights, "bias": model.bias,
        "identities_mapped_independently": len(name_to_target),
        "outcomes": dict(outcome),
        "outcomes_by_source": {k: dict(v) for k, v in by_source.items()},
        "hardcases_outcomes_by_category": {k: dict(v) for k, v in by_cat.items()},
        "hardcases_outcomes_by_alias_type": {k: dict(v) for k, v in by_alias.items()},
        "score_distribution": {"gold": dist(gold_scores), "best_wrong": dist(best_wrong_scores),
                               "all_candidates": dist(all_scores), "margin": dist(margins)},
        "score_auc_gold_vs_wrong": auc(gold_scores, best_wrong_scores),
        "feature_auc_gold_vs_wrong": {f: auc(feat_gold[f], feat_wrong[f]) for f in FEATURES},
        "feature_mean_gold": {f: round(statistics.fmean(feat_gold[f]), 4) if feat_gold[f] else None for f in FEATURES},
        "feature_mean_wrong": {f: round(statistics.fmean(feat_wrong[f]), 4) if feat_wrong[f] else None for f in FEATURES},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("outcomes_by_source", "hardcases_outcomes_by_category", "score_distribution", "feature_auc_gold_vs_wrong",
                      "score_auc_gold_vs_wrong", "identities_mapped_independently")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
