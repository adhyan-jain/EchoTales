"""E6. Prefix causality of the persona (trait) stage. Pre-declaration:
docs/research/ENGINEERING_NOVELTY_PROBE/E6_persona_stage_prefix_causality.md (written before this ran).

LABEL PROVENANCE: SYSTEM-INTERNAL (no labels). Scratch copies; CPU only; deterministic persona path (client=None); no LLM.
Counts and ids only; trait values are closed vocabularies (not novel text) and are summarised as counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eng_probe_common as C  # noqa: E402
from eng_probe_e1_prefix_causality import wilson  # noqa: E402
from echotales.core.enums import TargetKind  # noqa: E402
from echotales.core.models import DiscoursePosition as DP  # noqa: E402
from echotales.core.state import StateResolver  # noqa: E402
from echotales.pipeline.persona.build import build_personas  # noqa: E402

TRAITS = ("age_band", "gender", "register", "archetype", "big_five")


def prepare(db: str, nid: str, k: int | None) -> None:
    import sqlite3

    con = sqlite3.connect(db)
    if k is not None:
        for table, col in (("chapter", "number"), ("span", "chapter"), ("mention", "chapter"), ("narrative_segment", "chapter_from")):
            con.execute(f"DELETE FROM {table} WHERE novel_id=? AND {col} > ?", (nid, k))
    con.execute("DELETE FROM attribute WHERE novel_id=?", (nid,))
    con.execute("DELETE FROM persona WHERE novel_id=?", (nid,))
    con.commit()
    con.close()


def build(src: Path, work: Path, nid: str, name: str, k: int | None):
    db = C.fresh_copy(src, work, name)
    prepare(db, nid, k)
    n_ch = len(C.Store(db).chapter_numbers(nid))
    C.run_resolve(db, nid, chapters=C.ChapterRange(0, n_ch + 1000))
    store = C.Store(db)
    rep = build_personas(nid, store)
    store.conn.commit()
    return store, rep


def read_state(store, nid: str, k: int) -> dict:
    res = StateResolver(store, nid)
    out = {}
    for s in store.all_selves(nid):
        if not s.kind.is_person:
            continue
        # End of chapter k: story position k + 0.5 with knowledge taken at the end of chapter k. position=k+1 was the first
        # version and was a probe artefact: it admits facts stamped (k+1, 0) that exist only in the full graph (E4 granularity).
        kn = DP(chapter=k, offset=10**6)
        st = res.state_of(s.id, position=k + 0.5, knowledge_pos=kn)
        persona_attrs = {}
        for pid in st.persona_ids:
            persona_attrs[pid] = res.state_of(pid, target_kind=TargetKind.PERSONA, position=k + 0.5, knowledge_pos=kn).attributes
        out[s.id] = dict(aliases=sorted(st.aliases), personas=sorted(st.persona_ids), attrs=persona_attrs)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--ks", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    nid = args.novel
    work = C.SCRATCH / "eng"
    src = C.DBS[nid]
    out: dict = dict(probe="E6 persona-stage prefix causality", label_provenance="SYSTEM-INTERNAL, no labels", novel=nid, by_k={})
    full_store, full_rep = build(src, work, nid, f"{nid}_e6full", None)
    out["full_personas"] = full_rep.personas
    for k in [int(x) for x in args.ks.split(",")]:
        tr_store, tr_rep = build(src, work, nid, f"{nid}_e6k{k}", k)
        fs, ts = read_state(full_store, nid, k), read_state(tr_store, nid, k)
        common = sorted(set(fs) & set(ts))
        key_total: Counter = Counter()
        key_diff: Counter = Counter()
        ent_any = 0
        ent_with_facts = 0
        alias_diff = persona_diff = 0
        examples = []
        for e in common:
            if fs[e]["aliases"] != ts[e]["aliases"]:
                alias_diff += 1
            if fs[e]["personas"] != ts[e]["personas"]:
                persona_diff += 1
            # compare the first persona's attributes (the drawn body), same id in both graphs
            pids = sorted(set(fs[e]["attrs"]) & set(ts[e]["attrs"]))
            if not pids:
                continue
            ent_with_facts += 1
            any_diff = False
            for pid in pids:
                for key in TRAITS:
                    a, b = fs[e]["attrs"][pid].get(key), ts[e]["attrs"][pid].get(key)
                    if a is None and b is None:
                        continue
                    key_total[key] += 1
                    if a != b:
                        key_diff[key] += 1
                        any_diff = True
                        if len(examples) < 12:
                            examples.append(dict(entity=e, key=key, full_graph_value=str(a)[:40], prefix_graph_value=str(b)[:40]))
            ent_any += int(any_diff)
        out["by_k"][str(k)] = dict(
            entities_in_both=len(common), entities_only_in_full=len(set(fs) - set(ts)), entities_only_in_prefix=len(set(ts) - set(fs)),
            entities_with_persona_facts_compared=ent_with_facts, entities_with_any_trait_difference=ent_any,
            entity_difference_rate=round(ent_any / ent_with_facts, 4) if ent_with_facts else None,
            entity_difference_wilson=wilson(ent_any, ent_with_facts),
            per_key={key: dict(compared=key_total[key], differ=key_diff[key],
                               rate=round(key_diff[key] / key_total[key], 4) if key_total[key] else None,
                               wilson=wilson(key_diff[key], key_total[key])) for key in TRAITS},
            alias_sets_differ=alias_diff, persona_id_sets_differ=persona_diff, examples=examples)
        r = out["by_k"][str(k)]
        print(nid, "k=", k, "common", r["entities_in_both"], "compared", ent_with_facts, "any-diff", ent_any,
              {key: (v["differ"], v["compared"]) for key, v in r["per_key"].items()}, "alias-diff", alias_diff, "persona-diff", persona_diff, flush=True)
    Path(args.out).write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
