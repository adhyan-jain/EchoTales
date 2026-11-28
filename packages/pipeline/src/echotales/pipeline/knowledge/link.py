"""Link mentions the resolver left unbound, by exact name against the people the novel knows. Reversible.

RI ch1: "Bai Ning Bing" is named three times but is first a known person only later in the volume, so the three mentions
carry an empty target and every per-entity read (dossiers, presence) skipped them. The link is an exact normalised match
of the surface to ONE person's canonical label or bound alias; a surface two people share stays unlinked (precision over
recall). Each link keeps its evidence and the prior value in `evidence_json`, so `unlink_kb_links` restores the DB."""

from __future__ import annotations

import json

from echotales.core.store import Store
from echotales.pipeline.knowledge.common import norm

METHOD = "KB_NAME_LINK"  # the evidence_json tag; the method column is an enum, an exact name match is GAZETTEER_EXACT


def link_name_mentions(store: Store, novel_id: str, chapters: list[float] | None = None) -> int:
    people: dict[str, set[str]] = {}
    for e in store.all_selves(novel_id):
        if e.kind.is_person:
            people.setdefault(norm(e.canonical_label), set()).add(e.id)
    for r in store.conn.execute(
            "SELECT alias_norm, target_id FROM alias_binding WHERE novel_id=? AND alias_type='RIGID_NAME' AND retracted_chapter IS NULL",
            (novel_id,)):
        if any(r["target_id"] in ids for ids in people.values()):
            people.setdefault(norm(r["alias_norm"]), set()).add(r["target_id"])
    rows = store.conn.execute(
        "SELECT id, chapter, block_index, text FROM mention WHERE novel_id=? AND alias_type='RIGID_NAME' "
        "AND (target_id IS NULL OR target_id='')", (novel_id,)).fetchall()
    done = 0
    for r in rows:
        if chapters is not None and r["chapter"] not in chapters:
            continue
        ids = people.get(norm(r["text"]), set())
        if len(ids) != 1:
            continue
        (sid,) = ids
        evidence = {"link": METHOD, "prior_target_id": "", "matched": r["text"], "label": store.get_self(sid).canonical_label,
                    "chapter": r["chapter"], "block": r["block_index"]}
        store.conn.execute(
            "UPDATE mention SET target_kind='SELF', target_id=?, method=?, evidence_json=? WHERE id=?",
            (sid, "GAZETTEER_EXACT", json.dumps(evidence), r["id"]))
        done += 1
    store.conn.commit()
    return done


def unlink_kb_links(store: Store, novel_id: str) -> int:
    n = store.conn.execute(
        "UPDATE mention SET target_kind=NULL, target_id='', method=NULL, evidence_json=NULL WHERE novel_id=? AND evidence_json LIKE ?",
        (novel_id, f'%"link": "{METHOD}"%')).rowcount
    store.conn.commit()
    return n
