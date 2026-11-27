"""Measure look-by-epoch on one novel's chapter: dump every named character's looks and count distinct pairs before/after.

Usage: python scripts/eval/look_by_epoch.py <db> <novel-id> <chapter> <out.json> [--model-calls]
The DB is opened as given: pass a scratch copy, never data/db/. Without --model-calls only cached reads and the
deterministic cues are used (no GPU).

"Before" is what `persona/identity_lock.py` produced for a character with no scene look: the persona's stored facts
completed by `choose_defaults`. "After" is `persona/looks.py`. A pair of characters in one scene window is distinct when
their descriptions differ on at least 2 of: hair, age band, clothes, build/face.
"""

from __future__ import annotations

import itertools
import json
import sys

from echotales.core.store import Store
from echotales.pipeline.persona import identity_lock as il
from echotales.pipeline.persona import looks as lk
from echotales.pipeline.render.compiler import genre_direction


def _norm(s: str) -> str:
    return " ".join(s.casefold().replace(",", " ").split())


def before_lock(store: Store, novel_id: str, entity_id: str, chapter: float, manhua: bool) -> dict[str, str]:
    from echotales.pipeline.persona.reference_gen import appearance_of
    from echotales.pipeline.persona.split import persona_at

    pid = persona_at(store, entity_id, chapter + 0.99)
    facts = {k: v for k, v in appearance_of(store, pid, standing_only=False, position=chapter + 0.99).items() if v}
    gender = facts.get("gender", "male") if facts.get("gender") in ("male", "female") else "male"
    d = il.choose_defaults(entity_id, gender, manhua)
    lock = il.build_lock(pid, facts, d, gender=gender)
    return {"hair": lock.hair, "age_band": "adult", "clothes": lock.outfit, "build_face": lock.build}


def distinct(a: dict[str, str], b: dict[str, str]) -> tuple[int, list[str]]:
    same = [k for k in ("hair", "age_band", "clothes", "build_face") if _norm(a[k]) == _norm(b[k])]
    return 4 - len(same), same


def main() -> None:
    db, novel_id, chapter, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    store = Store(db)
    client = None
    if "--model-calls" in sys.argv:
        from echotales.pipeline.llm.client import ModelClient

        client = ModelClient(store=store)
    from echotales.pipeline.persona.genre import use_store_genre

    use_store_genre(store, novel_id)
    chap = store.get_chapter(novel_id, chapter)
    manhua = genre_direction(novel_id)[2]
    ents = [r["id"] for r in store.conn.execute(
        "SELECT e.id FROM self_entity e WHERE e.novel_id=? AND e.kind='SELF' AND (EXISTS (SELECT 1 FROM mention m WHERE"
        " m.target_id=e.id AND m.chapter=?) OR e.id LIKE '%:title:%') ORDER BY e.first_chapter, e.first_offset", (novel_id, chapter))]
    report: dict = {"novel": novel_id, "chapter": chapter, "characters": {}, "windows": [], "pairs": []}
    present_by_window: dict[tuple[int, int], list[str]] = {}
    per_look: dict[str, list[lk.Look]] = {}
    for eid in ents:
        names = lk.surface_names(store, novel_id, eid, chapter)
        present = lk._present_blocks(store, novel_id, eid, chapter, chap.blocks, names)
        if not present:
            continue
        looks = lk.looks_for_chapter(store, novel_id, eid, chapter, client=client)
        per_look[eid] = looks
        report["characters"][eid] = {
            "name": store.get_self(eid).canonical_label, "names": names, "present_blocks": present,
            "looks": [lk_.model_dump() for lk_ in looks],
        }
        for w in lk._cut_windows(chap.blocks, present):
            if w.present:
                present_by_window.setdefault((w.first, w.last), []).append(eid)
    before = {e: before_lock(store, novel_id, e, chapter, manhua) for e in per_look}
    tot = {"pairs": 0, "before_ok": 0, "after_ok": 0}
    for (a, b), eids in sorted(present_by_window.items()):
        report["windows"].append({"blocks": [a, b], "present": eids})
        for x, y in itertools.combinations(eids, 2):
            lx, ly = lk.look_at(store, novel_id, x, chapter=chapter, block=a, client=None), lk.look_at(store, novel_id, y, chapter=chapter, block=a, client=None)
            fx = {"hair": lx.hair, "age_band": lx.age_band, "clothes": lx.outfit, "build_face": f"{lx.build} {lx.face}"}
            fy = {"hair": ly.hair, "age_band": ly.age_band, "clothes": ly.outfit, "build_face": f"{ly.build} {ly.face}"}
            nb, sb = distinct(before[x], before[y])
            na, sa = distinct(fx, fy)
            tot["pairs"] += 1
            tot["before_ok"] += nb >= 2
            tot["after_ok"] += na >= 2
            report["pairs"].append({
                "window": [a, b], "a": x, "b": y, "before_distinct_dims": nb, "before_same": sb,
                "after_distinct_dims": na, "after_same": sa,
            })
    report["before"] = before
    report["totals"] = tot
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)
    for eid, c in report["characters"].items():
        print(f"== {c['name']}  names={c['names']}")
        for look in c["looks"]:
            print(f"   [{look['block_from']}-{look['block_to']}] {look['look_id']} {look['epoch_label']} gender={look['gender']}")
            print(f"      {look['description']}")
        print(f"   BEFORE: {before[eid]}")
    print(tot)


if __name__ == "__main__":
    main()
