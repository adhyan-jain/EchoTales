"""Audit the reader stage's output for look-ahead: does a line at chapter k point at someone the reader of k cannot name yet?

    python scripts/eval/reader_faithfulness_audit.py <db> <novel_id> [--chapters 1,3,7]

What this can and cannot see (docs/research/PREFIX_FAITHFULNESS/FORMAL.md P10, EVOLUTION 4.103): a full
truncate-and-rebuild is not possible here because the cast is drawn from a resolve-stage database built over the whole
volume, so any dependence on later chapters would arrive as a *selection* leak, which a truncated copy of this stage
alone cannot expose. This audit instead measures the one selection channel the reader opens deliberately (decisions D20):
a quoted line at chapter k attributed to an entity whose name is first learned after k. That is not itself a spoiler,
provided what is **served** to the reader at k is the title the book used then and not the later name. For each such line
it checks whether a title alias valid at k exists for the entity (so the label can be gated to the title) and reports the
rest as exposed: the entity's own name would be shown early.

It also checks the facts the stage wrote: no reader-stamped attribute or alias may be learned after the chapter it was
read in.
"""

from __future__ import annotations

import sys
from collections import Counter

from echotales.core.enums import AliasType, TargetKind
from echotales.core.store import Store

QUOTE_TYPES = ("DIALOGUE", "INNER_MONOLOGUE", "CROWD_REACTION")


def audit(store: Store, novel_id: str, chapters: set[int] | None) -> int:
    marks = ",".join("?" for _ in QUOTE_TYPES)
    rows = store.conn.execute(
        f"SELECT chapter, id, speaker_self_id FROM span WHERE novel_id=? AND speaker_self_id IS NOT NULL "
        f"AND attribution_method IN ('CONTEXTUAL_LLM','EPITHET_SLOT') AND span_type IN ({marks})",
        (novel_id, *QUOTE_TYPES),
    ).fetchall()
    tally: Counter[str] = Counter()
    exposed: Counter[tuple[int, str]] = Counter()
    for r in rows:
        chapter = int(r["chapter"])
        if chapters and chapter not in chapters:
            continue
        entity = store.get_self(r["speaker_self_id"])
        if entity is None:
            tally["slot_or_unknown_id"] += 1
            continue
        if entity.first_attested_pos.chapter <= chapter:
            tally["name_already_known"] += 1
            continue
        titles = [
            a for a in store.get_aliases_for(TargetKind.SELF, entity.id)
            if a.alias_type is AliasType.TRANSFERABLE_TITLE and a.retracted_at is None
            and a.interval.from_lb <= chapter <= a.interval.to_ub
        ]
        if titles:
            tally["ahead_but_servable_by_title"] += 1
        else:
            tally["EXPOSED_name_before_it_is_known"] += 1
            exposed[(chapter, entity.canonical_label)] += 1
    # reader-written facts must not be learned after the chapter they were read in (stamped at the stating chapter)
    bad = store.conn.execute(
        "SELECT COUNT(*) FROM attribute WHERE novel_id=? AND asserted_by='INFERENCE' AND learned_chapter > story_from_lb",
        (novel_id,),
    ).fetchone()[0]
    print(f"{novel_id}: {sum(tally.values())} reader-attributed lines" + (f" in chapters {sorted(chapters)}" if chapters else ""))
    for key, n in tally.most_common():
        print(f"  {key:34s} {n}")
    for (ch, label), n in sorted(exposed.items())[:12]:
        print(f"  exposed: ch{ch} -> {label!r} x{n}")
    print(f"  reader attributes learned later than they start: {bad}")
    return tally["EXPOSED_name_before_it_is_known"]


if __name__ == "__main__":
    wanted = {int(x) for x in sys.argv[sys.argv.index("--chapters") + 1].split(",")} if "--chapters" in sys.argv else None
    sys.exit(0 if audit(Store(sys.argv[1]), sys.argv[2], wanted) == 0 else 1)
