"""Static exposure and dynamic divergence of persona facts, per (entity, key, cut). PREREG.md H1-H4.

    PYTHONPATH=<worktree>/packages/core/src:<worktree>/packages/pipeline/src \
      python scripts/prefix_audit/audit.py --novel lord-of-the-mysteries --repair off

LABEL PROVENANCE: SYSTEM-INTERNAL (no labels). Deterministic persona path (client=None), stub LLM mode, CPU only.

Dynamic oracle (same as E6): build the full-volume graph and, per cut k, a graph from chapters <= k only, then compare
state_of(READER) at the end of chapter k (position k + 0.5, knowledge taken at the end of chapter k) for every person
present in both. Static side: a fact is *exposed* at k when its stored stamp is <= k but the chapters its value was
computed from reach beyond k. The per-key horizons below were derived by reading persona/build.py and persona/traits.py
(see PREREG.md); the static side is computed only on the unrepaired stage, where one stamp per fact exists.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from echotales.core.enums import TargetKind  # noqa: E402
from echotales.core.models import DiscoursePosition as DP  # noqa: E402
from echotales.core.state import StateResolver  # noqa: E402
from echotales.pipeline.persona import build as persona_build  # noqa: E402

TRAITS = ("age_band", "gender", "register", "archetype", "big_five")
PERSONA_SET = "persona_set"  # body splits: the set of persona ids bound to the self at the query position
SHORT_HORIZON_KEYS = ("gender", "age_band", "register", "archetype")


def prepare(db: str, nid: str, k: int | None) -> None:
    con = sqlite3.connect(db)
    if k is not None:
        for table, col in (("chapter", "number"), ("span", "chapter"), ("mention", "chapter"), ("narrative_segment", "chapter_from")):
            con.execute(f"DELETE FROM {table} WHERE novel_id=? AND {col} > ?", (nid, k))
    con.execute("DELETE FROM attribute WHERE novel_id=?", (nid,))
    con.execute("DELETE FROM persona WHERE novel_id=?", (nid,))
    con.commit()
    con.close()


def build(nid: str, src: Path, tag: str, k: int | None, repair: bool, anchored: tuple[int, float] | None = None):
    db = C.fresh_copy(src, f"{nid}_{tag}")
    prepare(db, nid, k)  # resolution is held fixed (PREREG Amendment 1): no re-resolve, stored mention targets are kept
    store = C.Store(db)
    kwargs = {"prefix_causal": True} if repair else {}
    if anchored:  # PREREG_ANCHORED.md: the same extractor on the full build and on every truncated build
        kwargs["anchored_gender"] = anchored
    t0 = time.time()
    persona_build.build_personas(nid, store, **kwargs)
    store.conn.commit()
    return store, time.time() - t0


def read_state(store, nid: str, k: int) -> dict:
    res = StateResolver(store, nid)
    kn = DP(chapter=k, offset=10**6)
    out = {}
    for s in store.all_selves(nid):
        if not s.kind.is_person:
            continue
        st = res.state_of(s.id, position=k + 0.5, knowledge_pos=kn)
        attrs = {
            pid: res.state_of(pid, target_kind=TargetKind.PERSONA, position=k + 0.5, knowledge_pos=kn).attributes
            for pid in st.persona_ids
        }
        out[s.id] = dict(personas=sorted(st.persona_ids), attrs=attrs)
    return out


def horizons(store, nid: str, eid: str) -> dict | None:
    """Evidence horizon per fact key for the UNREPAIRED stage, from the same calls build_personas makes."""
    att = store.chapters_for_target(nid, eid)
    if not att:
        return None
    h12, last = max(att[:12]), max(att)
    dialogue_total = persona_build._gather_evidence(store, nid, eid)[3]
    h = {k: h12 for k in SHORT_HORIZON_KEYS}
    # extraversion divides dialogue lines by the WHOLE-volume mention count, but only when dialogue lines > 0.
    h["big_five"] = last if dialogue_total > 0 else h12
    h[PERSONA_SET] = last
    return dict(h=h, h12=h12, last=last, dialogue_total=dialogue_total, n_attested=len(att))


def stamps(store, nid: str) -> dict:
    """Earliest stored stamp chapter per (entity, key), and for the persona set the latest binding stamp."""
    out: dict = {}
    for s in store.all_selves(nid):
        if not s.kind.is_person:
            continue
        per_key: dict = {}
        bindings = store.get_self_persona_bindings(self_id=s.id)
        for b in bindings:
            for a in store.get_attributes(TargetKind.PERSONA, b.persona_id):
                ch = a.learned_at_pos.chapter
                per_key[a.key] = ch if a.key not in per_key else min(per_key[a.key], ch)
        if bindings:
            per_key[PERSONA_SET] = max(b.learned_at_pos.chapter for b in bindings)
        out[s.id] = per_key
    return out


def summarise(rows: list[dict]) -> dict:
    out = {}
    for key in (*TRAITS, PERSONA_SET, "ALL_TRAITS"):
        sel = [r for r in rows if (r["key"] in TRAITS if key == "ALL_TRAITS" else r["key"] == key)]
        n = len(sel)
        div = sum(r["diverge"] for r in sel)
        has_static = [r for r in sel if r["exposed"] is not None]
        exp = sum(bool(r["exposed"]) for r in has_static)
        both = sum(bool(r["exposed"]) and r["diverge"] for r in has_static)
        out[key] = dict(
            compared=n, diverge=div, diverge_wilson=C.wilson(div, n),
            static_scored=len(has_static), exposed=exp,
            diverge_and_exposed=both,
            diverge_not_exposed=sum((not r["exposed"]) and r["diverge"] for r in has_static),  # H1 violations
            exposed_not_diverge=exp - both,
            screen_precision=round(both / exp, 4) if exp else None,
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--repair", choices=("off", "on"), required=True)
    ap.add_argument("--ks", default=None, help="comma-separated cuts; default = the E6 cuts for this serial")
    ap.add_argument("--out", default=None)
    ap.add_argument("--anchored", default=None, help="MIN_OBS,MAJORITY of the anchored pronoun cue (PREREG_ANCHORED.md)")
    args = ap.parse_args()
    nid, repair = args.novel, args.repair == "on"
    parts = args.anchored.split(",") if args.anchored else []
    anchored = (int(parts[0]), float(parts[1])) + tuple(parts[2:3]) if parts else None  # optional third field: window variant, e.g. v2
    atag = f"_a{anchored[0]}_{round(anchored[1] * 100)}{'_' + anchored[2] if len(anchored) > 2 else ''}" if anchored else ""
    ks = [int(x) for x in args.ks.split(",")] if args.ks else C.CUTS[nid]
    out_path = Path(args.out) if args.out else C.RESULTS / f"audit_repair-{args.repair}_{nid}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    src = C.snapshot_source(nid)
    full, full_secs = build(nid, src, f"full_{args.repair}{atag}", None, repair, anchored)
    full_attr_rows = full.conn.execute("SELECT COUNT(*) AS n FROM attribute WHERE novel_id=?", (nid,)).fetchone()["n"]
    full_stamps = stamps(full, nid)
    hz = {s.id: horizons(full, nid, s.id) for s in full.all_selves(nid) if s.kind.is_person}
    result: dict = dict(
        audit="prefix-faithfulness", repair=repair, novel=nid, label_provenance="SYSTEM-INTERNAL, no labels",
        persona_stage_seconds_full=round(full_secs, 2), attribute_rows_full=full_attr_rows, by_k={},
    )
    all_rows: list[dict] = []
    for k in ks:
        pre, _ = build(nid, src, f"k{k}_{args.repair}{atag}", k, repair, anchored)
        fs, ts = read_state(full, nid, k), read_state(pre, nid, k)
        # An entity first mentioned after k still has a self_entity row here (nothing was re-resolved) but no evidence in
        # the prefix; counting it would pad every denominator with identical empty states.
        common = sorted(e for e in set(fs) & set(ts) if pre.chapters_for_target(nid, e))
        rows: list[dict] = []
        known = Counter()
        for e in common:
            pids = sorted(set(fs[e]["attrs"]) & set(ts[e]["attrs"]))
            for pid in pids:
                g_full, g_pre = fs[e]["attrs"][pid].get("gender"), ts[e]["attrs"][pid].get("gender")
                if g_full is not None or g_pre is not None:
                    known["n"] += 1
                    known["unknown_full"] += g_full in (None, "unknown")
                    known["unknown_prefix"] += g_pre in (None, "unknown")
                for key in TRAITS:
                    a, b = fs[e]["attrs"][pid].get(key), ts[e]["attrs"][pid].get(key)
                    if a is None and b is None:
                        continue
                    rows.append(_row(e, key, k, a != b, full_stamps, hz, repair, a, b))
            rows.append(_row(e, PERSONA_SET, k, fs[e]["personas"] != ts[e]["personas"], full_stamps, hz, repair))
        all_rows += rows
        result["by_k"][str(k)] = dict(
            entities_in_both=len(common), summary=summarise(rows),
            gender_availability=dict(known), attribute_rows_prefix=pre.conn.execute(
                "SELECT COUNT(*) AS n FROM attribute WHERE novel_id=?", (nid,)).fetchone()["n"],
        )
        s = result["by_k"][str(k)]["summary"]["ALL_TRAITS"]
        print(nid, f"repair={args.repair}", "k=", k, "common", len(common), "trait-facts", s["compared"], "diverge", s["diverge"],
              "exposed", s["exposed"], "div&exposed", s["diverge_and_exposed"], "H1-violations", s["diverge_not_exposed"],
              "persona-set diverge", result["by_k"][str(k)]["summary"][PERSONA_SET]["diverge"], flush=True)
        pre.close()
    result["pooled"] = summarise(all_rows)
    result["rows"] = all_rows
    out_path.write_text(json.dumps(result, indent=1))
    print("wrote", out_path)


def _row(e: str, key: str, k: int, diverge: bool, full_stamps: dict, hz: dict, repair: bool,
         full_value: str | None = None, prefix_value: str | None = None) -> dict:
    exposed = None
    h = hz.get(e)
    stamp = full_stamps.get(e, {}).get(key)
    if not repair and h is not None and stamp is not None:
        exposed = bool(stamp <= k < h["h"][key])
    # Values are closed vocabularies (gender, age band, ...), not novel text; kept so the hide-only ablation can be scored.
    return dict(entity=e, key=key, k=k, diverge=bool(diverge), exposed=exposed,
                stamp=stamp, horizon=(h["h"].get(key) if h else None),
                full_value=None if full_value is None else str(full_value)[:40],
                prefix_value=None if prefix_value is None else str(prefix_value)[:40])


if __name__ == "__main__":
    main()
