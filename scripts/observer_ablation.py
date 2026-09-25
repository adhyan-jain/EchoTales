"""A1 / A2: does the observer axis causally change what an observer resolves and sees?

Pre-registered rules (fixed here, in code, before any number was computed):

  Reveal events   every (fact, learned chapter r) in `observation`; the fact is
                  an alias of a target Self.
  Observers       every Self recorded as observing that fact (witnesses), plus
                  the 20 most-mentioned Selves that are neither witnesses of
                  that fact nor its target (non-witnesses).
  Positions       r-1, r, 200 (story position = knowledge position unless an
                  ablation overrides knowledge).
  Should-know     observer o should resolve alias a at position p iff o has an
                  observation of that fact with learned_chapter <= p. This is
                  the system's own record; whether the record is *right* is the
                  witness-derivation precision question (human review), not
                  this experiment.
  Leak            a is returned for (o, p) although o should not know it.
  Under-exposure  a is not returned although o should know it.
  Wrong exposure  any returned alias that is not an alias binding of the target.
  Generation leak the render plan built for o at chapter p, with the target in
                  the cast, carries the target's persona (identity-conditioned
                  drawing) although o should not know the alias.

Conditions
  FULL  state_of(target, position=p, observer=o)
  A1    observer collapsed: state_of(..., observer=READER)   ("who" axis removed)
  A2    knowledge time removed: state_of(..., observer=o, knowledge_pos=+inf)
        ("when" axis removed; the observer filter itself is kept)

Because leak is defined against the system's own records, FULL scores 0 by
construction on the state level; the experiment measures how much output
changes when an axis is removed, which is the causal question.

Usage:
    python3 scripts/observer_ablation.py [--db data/reverend-insanity.db]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from echotales.core.enums import OBSERVER_READER
from echotales.core.models import DiscoursePosition
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.render.plan_builder import build_render_plan

NOVEL = "reverend-insanity"
N_NON_WITNESSES = 20
FAR = DiscoursePosition(chapter=10**6)


def reveal_events(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT fact_ref, MIN(learned_chapter) FROM observation GROUP BY fact_ref ORDER BY fact_ref"
    ).fetchall()
    events = []
    for fact_ref, first in rows:
        _, rest = fact_ref.split(":", 1)
        target, alias_norm = rest.rsplit(":", 1)
        chapters = [c for (c,) in conn.execute(
            "SELECT DISTINCT learned_chapter FROM observation WHERE fact_ref=? ORDER BY 1", (fact_ref,))]
        for r in chapters:
            events.append({"fact_ref": fact_ref, "target": target, "alias_norm": alias_norm,
                           "reveal_chapter": r, "first_learned": first})
    return events


def _resolver(store: Store, observer: str, knowledge_far: bool) -> StateResolver:
    resolver = StateResolver(store, NOVEL, default_observer=observer)
    if knowledge_far:
        orig = resolver.state_of

        def far(tid, _orig=orig, **kw):  # type: ignore[no-untyped-def]
            kw.setdefault("knowledge_pos", FAR)
            return _orig(tid, **kw)

        resolver.state_of = far  # type: ignore[method-assign]
    return resolver


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/reverend-insanity.db")
    ap.add_argument("--out", default="data/eval/observer_ablation.json")
    args = ap.parse_args()

    store = Store(args.db)
    conn = store.conn
    events = reveal_events(conn)
    mention_rank = [sid for (sid,) in conn.execute(
        "SELECT target_id FROM mention WHERE novel_id=? AND target_id LIKE ? "
        "GROUP BY target_id ORDER BY count(*) DESC", (NOVEL, f"{NOVEL}:self:%"))]
    target_aliases: dict[str, set[str]] = {}
    records: list[dict[str, Any]] = []
    conditions = ("FULL", "A1", "A2")
    setup = {"FULL": (None, False), "A1": (OBSERVER_READER, False), "A2": (None, True)}

    for ev in events:
        target, fact = ev["target"], ev["fact_ref"]
        if target not in target_aliases:
            target_aliases[target] = {a.casefold() for (a,) in conn.execute(
                "SELECT alias FROM alias_binding WHERE target_id=?", (target,))}
        learned = dict(conn.execute(
            "SELECT observer_id, MIN(learned_chapter) FROM observation WHERE fact_ref=? GROUP BY 1",
            (fact,)).fetchall())
        witnesses = sorted(learned)
        non_witnesses = [s for s in mention_rank if s not in learned and s != target][:N_NON_WITNESSES]
        r = ev["reveal_chapter"]
        for cls, observers in (("witness", witnesses), ("non_witness", non_witnesses)):
            for o in observers:
                for p in (r - 1, r, 200):
                    should = o in learned and learned[o] <= p
                    row: dict[str, Any] = {"fact": fact, "reveal_chapter": r, "observer": o,
                                           "observer_class": cls, "position": p, "should_know": should}
                    for cond in conditions:
                        forced_observer, knowledge_far = setup[cond]
                        observer = forced_observer or o
                        resolver = _resolver(store, observer, knowledge_far)
                        res = resolver.state_of(target, position=float(p))
                        visible = ev["alias_norm"] in {a.casefold() for a in res.aliases}
                        wrong = [a for a in res.aliases if a.casefold() not in target_aliases[target]]
                        plan = build_render_plan(
                            store, NOVEL, chapter=float(p), beat_id="ablation", panel_seq=0,
                            cast_self_ids=[target], lead_self_id=target, resolver=resolver)
                        drawn = any(c.self_id == target for c in plan.characters)
                        row[cond] = {"alias_visible": visible, "wrong_exposure": len(wrong),
                                     "identity_drawn": drawn}
                    records.append(row)
    store.close()

    def tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {"queries": len(rows), "should_know": sum(r["should_know"] for r in rows)}
        for cond in conditions:
            out[cond] = {
                "leak": sum(r[cond]["alias_visible"] and not r["should_know"] for r in rows),
                "under_exposure": sum((not r[cond]["alias_visible"]) and r["should_know"] for r in rows),
                "wrong_exposure": sum(r[cond]["wrong_exposure"] for r in rows),
                "generation_leak": sum(r[cond]["identity_drawn"] and not r["should_know"] for r in rows),
                "generation_drawn_when_known": sum(r[cond]["identity_drawn"] and r["should_know"] for r in rows),
            }
        return out

    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_event[f"{rec['fact']}@{rec['reveal_chapter']}"].append(rec)
        by_class[rec["observer_class"]].append(rec)
    report = {
        "db": args.db,
        "rules": (__doc__ or "").split("Pre-registered rules")[1].split("Usage:")[0].strip(),
        "reveal_events": len(events),
        "total": tally(records),
        "by_event": {k: tally(v) for k, v in sorted(by_event.items())},
        "by_observer_class": {k: tally(v) for k, v in sorted(by_class.items())},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    t = report["total"]
    print(f"reveal events: {len(events)}   queries: {t['queries']}   should-know: {t['should_know']}")
    for cond in conditions:
        c = t[cond]
        print(f"  {cond:4}  leak={c['leak']:4}  under={c['under_exposure']:4}  wrong={c['wrong_exposure']}  "
              f"gen_leak={c['generation_leak']:4}  gen_drawn_when_known={c['generation_drawn_when_known']}")
    for k, v in report["by_observer_class"].items():
        print(f"  [{k}] " + "  ".join(f"{c}: leak={v[c]['leak']} under={v[c]['under_exposure']} "
                                         f"gen_leak={v[c]['generation_leak']}" for c in conditions))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
