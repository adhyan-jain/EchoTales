"""Join the legacy and hybrid JSON written by `ner_realdata_compare.py` into one comparison plus entity-change counts.

Entity change: an entity in one run counts as unchanged if the other run has an entity with the same normalised
canonical alias set overlap (Jaccard >= 0.5 over lowercased alias surfaces); everything else is only-in-that-run.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def entities(db: str, novel: str) -> dict[str, set[str]]:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out: dict[str, set[str]] = {}
    for eid, kind in c.execute("SELECT id, kind FROM self_entity WHERE novel_id=?", (novel,)):
        out[eid] = {r[0].casefold() for r in c.execute(
            "SELECT DISTINCT alias FROM alias_binding WHERE target_id=? AND novel_id=?", (eid, novel))}
    return out


def only(a: dict[str, set[str]], b: dict[str, set[str]]) -> list[set[str]]:
    res = []
    for ea in a.values():
        if not ea:
            continue
        if not any(len(ea & eb) / len(ea | eb) >= 0.5 for eb in b.values() if eb):
            res.append(ea)
    return res


def main(d: str) -> None:
    base = Path(d)
    rows = []
    for leg in sorted(base.glob("*-legacy.json")):
        hyb = Path(str(leg).replace("-legacy.json", "-hybrid.json"))
        if not hyb.exists():
            continue
        L, H = json.loads(leg.read_text()), json.loads(hyb.read_text())
        ls, hs = L["surface_counts"], H["surface_counts"]
        only_h = sorted(((s, n) for s, n in hs.items() if s not in ls), key=lambda x: -x[1])
        only_l = sorted(((s, n) for s, n in ls.items() if s not in hs), key=lambda x: -x[1])
        el, eh = entities(L["db"], L["novel"]), entities(H["db"], H["novel"])
        slim = lambda r: {k: r[k] for k in ("mentions", "distinct_surfaces", "mention_wall_s", "resolve_wall_s", "ollama_models_seen", "gpu_peak_mib", "detector_name")} | {
            k: r["resolve"][k] for k in ("groups", "linked", "created", "deferred", "escalated", "unresolved", "entities", "by_method")}
        rows.append({
            "novel": L["novel"], "chapters": L["chapters"], "legacy": slim(L), "hybrid": slim(H),
            "only_hybrid_top30": only_h[:30], "only_hybrid_total": len(only_h),
            "only_legacy_top30": only_l[:30], "only_legacy_total": len(only_l),
            "entities_only_legacy": len(only(el, eh)), "entities_only_hybrid": len(only(eh, el)),
            "entities_only_legacy_examples": [sorted(x)[:3] for x in only(el, eh)[:15]],
            "entities_only_hybrid_examples": [sorted(x)[:3] for x in only(eh, el)[:15]],
        })
    json.dump(rows, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
