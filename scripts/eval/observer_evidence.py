"""One persisted artifact for the observer-conditioned state claim.

STATE_OF_VALIDATION.md showed the numbers by hand-run CLI queries. This makes
the same demonstration a single re-runnable file, and adds the part a
reviewer will ask about: that it is the *same* fact, with the *same*
identity, whose visibility differs -- not two different facts, and not a
redaction applied after the query.

  same narrative fact     one alias fact on one Self (Bai Ning Bing's name),
                          identified by `observable_ref`, derived from the
                          fact rather than a row id
  same underlying identity  every query targets the same self_id
  different observer / knowledge time  READER, SYSTEM, a witness to the
                          ch166 reveal, a non-witness; the witness again,
                          asking from ch150 / 166 / 200
  different visible result  the aliases each query returns

Usage:
    python3 scripts/eval/observer_evidence.py [--db data/db/reverend-insanity.db]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from echotales.core.models import DiscoursePosition
from echotales.core.state import OBSERVER_READER, OBSERVER_SYSTEM, StateResolver
from echotales.core.store import Store

NOVEL = "reverend-insanity"
TARGET_LABEL = "Bai Ning Bing"
REVEAL_CHAPTER = 166
POSITION = 200.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/db/reverend-insanity.db")
    ap.add_argument("--out", default="data/eval/observer_evidence.json")
    args = ap.parse_args()

    store = Store(args.db)
    conn = store.conn
    (self_id,) = conn.execute(
        "SELECT id FROM self_entity WHERE novel_id=? AND canonical_label=?", (NOVEL, TARGET_LABEL)
    ).fetchone()
    fact_ref = f"alias:{self_id}:{TARGET_LABEL.casefold()}"

    witnesses = [
        r[0] for r in conn.execute(
            "SELECT observer_id FROM observation WHERE fact_ref=? AND learned_chapter=? "
            "ORDER BY observer_id", (fact_ref, REVEAL_CHAPTER),
        )
    ]
    if not witnesses:
        print(f"no witness recorded for {fact_ref} at ch{REVEAL_CHAPTER}; run `observations` first")
        return 2
    witness = witnesses[0]
    observed = {r[0] for r in conn.execute("SELECT observer_id FROM observation WHERE fact_ref=?", (fact_ref,))}
    # A non-witness who is a real, frequently mentioned character -- the most
    # mentioned Self that never observed the fact -- rather than an arbitrary id.
    non_witness = next(
        sid for (sid,) in conn.execute(
            "SELECT target_id FROM mention WHERE novel_id=? AND target_id LIKE ? "
            "GROUP BY target_id ORDER BY count(*) DESC", (NOVEL, f"{NOVEL}:self:%"),
        )
        if sid not in observed and sid != self_id
    )
    label = {sid: lab for sid, lab in conn.execute(
        "SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (NOVEL,)
    )}

    rows = [
        {"id": r[0], "alias": r[1], "story_from_lb": r[2], "learned_chapter": r[3], "observer_id": r[4]}
        for r in conn.execute(
            "SELECT id, alias, story_from_lb, learned_chapter, observer_id FROM alias_binding "
            "WHERE novel_id=? AND target_id=? ORDER BY id", (NOVEL, self_id),
        )
    ]

    resolver = StateResolver(store, NOVEL)

    def query(axis: str, observer: str, knowledge_chapter: int | None) -> dict[str, Any]:
        kp = DiscoursePosition(chapter=knowledge_chapter) if knowledge_chapter is not None else None
        r = resolver.state_of(self_id, position=POSITION, observer_id=observer, knowledge_pos=kp)
        return {
            "axis": axis,
            "observer": observer,
            "observer_label": label.get(observer, observer),
            "target_id": r.target_id,
            "position": POSITION,
            "knowledge_chapter": knowledge_chapter,
            "aliases": r.aliases,
            "alias_read_set": sorted(x for x in r.read_set if x.startswith("alias:")),
        }

    queries = [
        query("who is asking", OBSERVER_READER, None),
        query("who is asking", OBSERVER_SYSTEM, None),
        query("who is asking", witness, None),
        query("who is asking", non_witness, None),
        query("asking from when", witness, 150),
        query("asking from when", witness, REVEAL_CHAPTER),
        query("asking from when", witness, 200),
    ]
    store.close()

    n = [len(q["aliases"]) for q in queries]
    checks = {
        "same_identity_in_every_query": len({q["target_id"] for q in queries}) == 1,
        "reader_2_witness_1_nonwitness_0": (n[0], n[2], n[3]) == (2, 1, 0),
        "witness_learns_at_reveal_0_1_1": (n[4], n[5], n[6]) == (0, 1, 1),
        "witness_sees_subset_of_reader": set(queries[2]["aliases"]) <= set(queries[0]["aliases"]),
        # The read-set key is novel-scoped (`alias_ref`), the observation key
        # Self-scoped (`observable_ref`); both are derived from the fact.
        "witness_read_set_records_the_alias": f"alias:{NOVEL}:{TARGET_LABEL.casefold()}"
        in queries[2]["alias_read_set"],
        "non_witness_read_set_omits_it": f"alias:{NOVEL}:{TARGET_LABEL.casefold()}"
        not in queries[3]["alias_read_set"],
    }

    payload = {
        "db": args.db,
        "target": {"self_id": self_id, "label": TARGET_LABEL},
        "fact": {"fact_ref": fact_ref, "reveal_chapter": REVEAL_CHAPTER, "alias_binding_rows": rows},
        "observers": {
            "witness": {"id": witness, "label": label.get(witness)},
            "non_witness": {"id": non_witness, "label": label.get(non_witness)},
            "all_witnesses": witnesses,
        },
        "queries": queries,
        "checks": checks,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2, default=str) + "\n")

    for q in queries:
        kc = q["knowledge_chapter"] if q["knowledge_chapter"] is not None else "=pos"
        print(f"  {q['axis']:16} {str(q['observer_label'])[:18]:18} knows-from={kc!s:>4} "
              f"-> {q['aliases']}")
    for name, ok in checks.items():
        print(f"  [{'ok' if ok else 'FAIL'}] {name}")
    print(f"written: {args.out}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
