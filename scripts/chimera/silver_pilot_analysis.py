"""Silver (model-labelled) analysis of the 72-item CHIMERA pilot sheet. Zero spend, no model call, no key.

LABEL PROVENANCE (do not remove): every reference label used here is SILVER.
  * `gold_identity` comes from data/gold/reverend-insanity-hardcases.jsonl, a model draft
    (drafted_by claude-sonnet-5-gold-hardcases, confirmed=false). It is not human truth.
  * For system-sourced items (3 clan-head, 30 plain controls) there is NO independent label:
    the "label" is the system's own target, so those rows only test sheet integrity.
  * No reader-warranted label exists at all (it would need a human, or a model that may
    remember the novel). Nothing here is a reader-view accuracy.
Human labels from the weekend replace `gold_identity`; rerun this script on the validated sheet.

    python scripts/chimera/silver_pilot_analysis.py --db <SCRATCH COPY of RI db> --out data/eval/chimera/silver_pilot_results.json
"""

from __future__ import annotations

import argparse
import os
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from math import sqrt
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"

from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.eval.coref_score import _block_starts  # noqa: E402

NOVEL = "reverend-insanity"
SHEET = "data/eval/human_review_chimera_pilot.csv"
KEY = "data/eval/human_review_chimera_pilot_key.csv"


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, (c - r) / d), min(1.0, (c + r) / d)]


def row(k: int, n: int) -> dict:
    return dict(k=k, n=n, rate=(k / n if n else None), wilson95=wilson(k, n))


def norm(s: str) -> str:
    return re.sub(r"[^a-z ]", "", s.lower().split(" (")[0]).strip()


def label_match(system_label: str, silver: str) -> tuple[bool, bool]:
    """(strict, loose). strict = equal after normalisation; loose = one's tokens contain the other's."""
    a, b = norm(system_label), norm(silver)
    if not a or not b:
        return False, False
    ta, tb = set(a.split()), set(b.split())
    return a == b, bool(ta and tb and (ta <= tb or tb <= ta))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    store = Store(args.db)  # a SCRATCH copy; only read
    con = store.conn

    sheet = {r["item_id"]: r for r in csv.DictReader(open(SHEET, encoding="utf-8"))}
    key = {r["item_id"]: r for r in csv.DictReader(open(KEY, encoding="utf-8"))}
    labels = dict(con.execute("select id, canonical_label from self_entity where novel_id=?", (NOVEL,)).fetchall())

    cache: dict[float, list[tuple]] = {}

    def mentions(ch: float):
        if ch not in cache:
            st = _block_starts(store, NOVEL, ch)
            rows = con.execute(
                "select id, offset, text, block_index, target_id, alias_type, method from mention "
                "where novel_id=? and chapter=?", (NOVEL, ch)).fetchall()
            cache[ch] = [(i, st.get(b, 0) + o, t, tgt, at, me) for i, o, t, b, tgt, at, me in rows]
        return cache[ch]

    outcome = defaultdict(Counter)
    outcome_cat = defaultdict(Counter)
    per_item = []
    integrity = Counter()
    for iid, k in key.items():
        s = sheet[iid]
        ch, off, surf = float(s["chapter"]), int(s["mention_offset"]), s["mention_surface"]
        span = (off, off + len(surf))
        hits = [m for m in mentions(ch) if m[1] < span[1] and m[1] + len(m[2]) > span[0]]
        if k["source"] == "system":
            ok = any(m[3] == k["system_target"] for m in hits)
            integrity[(k["category"], ok)] += 1
            per_item.append(dict(item=iid, tier=k["tier"], category=k["category"], source="system", recovered=ok,
                                 system_target_id=k["system_target"]))
            continue
        sys_target = None
        if k["category"] == "not_entity_control":
            res = "not-entity (no mention expected)" if not hits else "mention-on-non-entity"
        elif not hits:
            res = "not-detected"
        else:
            best = max(hits, key=lambda m: (m[3] is not None, len(m[2])))
            sys_target = best[3]
            if best[3] is None:
                res = "detected-unresolved"
            else:
                strict, loose = label_match(labels.get(best[3], ""), k["gold_identity"])
                res = "linked-matches-silver" if loose else "linked-differs-from-silver"
        outcome[k["tier"]][res] += 1
        outcome_cat[k["category"]][res] += 1
        per_item.append(dict(item=iid, tier=k["tier"], category=k["category"], source="gold", result=res,
                             system_target_id=sys_target))

    # real-RI title events: per-mention LINK event stamped before the holder binding's learned chapter?
    learned = {}
    for tid, lc in con.execute(
        "select target_id, min(learned_chapter) from alias_binding where novel_id=? and alias_norm like '%clan head%' "
        "and alias_type='TRANSFERABLE_TITLE' group by target_id", (NOVEL,)):
        learned[tid] = lc
    ev_total = ev_early = 0
    early_examples = []
    for payload, cc in con.execute("select payload, cause_chapter from resolution_event where method='TITLE_HOLDER'"):
        p = json.loads(payload)
        if "title" not in p or p.get("target_id") not in learned:
            continue
        ev_total += 1
        if cc < learned[p["target_id"]]:
            ev_early += 1
            if len(early_examples) < 5:
                early_examples.append(dict(event_cause_chapter=cc, holder_binding_learned_chapter=learned[p["target_id"]]))

    p_gold = [x for x in per_item if x.get("tier") == "P" and x.get("source") == "gold"]
    linked_p = [x for x in p_gold if x.get("result") in ("linked-matches-silver", "linked-differs-from-silver")]
    n_pre = sum(1 for k in key.values() if k["tier"] == "P")
    n_match = sum(1 for x in p_gold if x.get("result") == "linked-matches-silver")

    def zero_event_upper(n: int) -> float:
        return 1 - 0.05 ** (1 / n) if n else float("nan")  # exact one-sided 95% bound for 0 events in n

    res = dict(
        label_provenance="SILVER (model-drafted hard-case gold, confirmed=false) for gold-sourced items; system-sourced items have no independent label. NO human labels. NO reader-view labels.",
        n_items=len(key),
        outcome_by_tier_gold_sourced={t: dict(c) for t, c in outcome.items()},
        outcome_by_category_gold_sourced={t: dict(c) for t, c in outcome_cat.items()},
        sheet_integrity_system_sourced={f"{c}|recovered={ok}": n for (c, ok), n in integrity.items()},
        real_RI_title_events=dict(
            note="system-internal consistency; no reference labels involved",
            title_holder_link_events_stamped_before_holder_binding=row(ev_early, ev_total), examples=early_examples),
        premature_resolution_eligibility=dict(
            note="items that could even yield a premature-resolution count once a human reader label exists",
            tier_P_items=n_pre,
            tier_P_gold_items=len(p_gold),
            tier_P_gold_linked_by_system=len(linked_p),
            tier_P_gold_linked_to_silver_omniscient_identity=n_match,
            exact_95_upper_bound_if_zero_events_of_linked=zero_event_upper(len(linked_p)),
            exact_95_upper_bound_if_zero_events_of_23=zero_event_upper(23),
        ),
        per_item=per_item,
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "per_item"}, indent=2, default=str))


if __name__ == "__main__":
    main()
