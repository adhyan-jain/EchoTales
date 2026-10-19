"""Cross-novel replication on scratch copies of the LOTM and ORV databases (and RI as the reference).

  audit  re-resolves a scratch copy with the CURRENT code and reports: link-method shares (is the scorer linking
         anything?), links stamped before the reader's alias binding, and reveal-pattern coverage on real narration
         (raw REVEAL_PATTERNS matches, and matches that resolve to a known character).
  t4     applies the frozen T4 v5 rules (PREREG_T4_v5_addendum_2_crossnovel.md) to a novel: the v3 token-level
         renamer and the v5 letter cipher are built from the novel's vocabulary and run through the same commutation
         gate; if v5 passes, runs O1, O2, I, R on fresh resolves. No negative control (not registered for these novels).

LABEL PROVENANCE: system-internal; NO reference labels; nothing here is accuracy. CPU only; no model; no spend; no
novel text is written (counts only). Existing code is imported unchanged.

    python scripts/chimera/cross_novel_replication.py audit --db <scratch copy> --novel <id> --workdir <dir> --out <json>
    python scripts/chimera/cross_novel_replication.py t4    --db <scratch copy> --novel <id> --workdir <dir> --out <json>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import t4_renaming as T4  # noqa: E402
import t4_renaming_v4 as V4  # noqa: E402
import t4_renaming_v5 as V5  # noqa: E402

from echotales.core.enums import SpanType  # noqa: E402
from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.ingest.normalize import comparison_key  # noqa: E402
from echotales.pipeline.ingest.sources import get_source  # noqa: E402
from echotales.pipeline.mentions.induce import load_or_seed  # noqa: E402
from echotales.pipeline.resolve import resolve_novel  # noqa: E402
from echotales.pipeline.resolve.detect_reveals import REVEAL_PATTERNS, find_reveals  # noqa: E402


def fresh(src: str, workdir: Path, name: str) -> str:
    dst = workdir / f"{name}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(dst) + suffix).unlink(missing_ok=True)
    shutil.copy(src, dst)
    return str(dst)


def audit(args) -> None:
    nid = args.novel
    path = fresh(args.db, Path(args.workdir), f"{nid}_audit")
    store = Store(path)
    chapters = len(store.chapter_numbers(nid))
    lex = load_or_seed(get_source(nid).lexicon)
    report = resolve_novel(nid, store, lexicon=lex, force_rewipe=True)
    ments = store.get_mentions(nid)
    linked = [m for m in ments if m.target_id]
    by_method = Counter(m.method.value for m in linked if m.method)
    learned: dict[tuple[str, str], int] = {}
    for b in store.all_aliases(nid):
        if b.observer_id == "READER":
            k = (b.target_id, comparison_key(b.alias))
            learned[k] = min(learned.get(k, 10**9), b.learned_at_pos.chapter)
    early = [m for m in linked if (lc := learned.get((m.target_id, comparison_key(m.text)))) is not None
             and m.chapter < lc]
    # groups tagged SCORED, split into "founds a new entity" vs "links to an entity that already had a mention"
    first_by_ent: dict[str, tuple] = {}
    groups: dict[str, list] = {}
    for m in linked:
        k = (m.chapter, m.block_index, m.offset)
        first_by_ent[m.target_id] = min(first_by_ent.get(m.target_id, k), k)
        g = groups.setdefault(m.local_group_id or m.id, [m.target_id, m.method.value if m.method else None, k])
        g[2] = min(g[2], k)
    scored = [v for v in groups.values() if v[1] == "SCORED"]
    scored_groups = dict(
        groups=len(groups), tagged_SCORED=len(scored),
        found_a_new_entity=sum(1 for v in scored if v[2] == first_by_ent[v[0]]),
        link_to_an_existing_entity=sum(1 for v in scored if v[2] > first_by_ent[v[0]]),
        non_SCORED_groups=len(groups) - len(scored))
    raw = 0
    for row in store.conn.execute("select text from span where novel_id=? and span_type in (?, ?)",
                                  (nid, SpanType.NARRATION_DESCRIPTION.value, SpanType.NARRATION_ACTION.value)):
        for pat in REVEAL_PATTERNS:
            raw += len(list(pat.finditer(str(row["text"]))))
    resolved = len(find_reveals(store, nid))
    res = dict(
        label_provenance="NO LABELS: system-internal counts on a scratch copy re-resolved with the current code",
        novel=nid, chapters_in_database=chapters, mentions=len(ments), linked=len(linked),
        link_methods=dict(by_method),
        scored_tag_note=("the SCORED tag is the gate's default for every path that reaches the scorer, including "
                         "minting a NEW entity; use scored_groups_* below for scorer decisions"),
        scored_groups=scored_groups,
        resolve_report=dict(deferred=report.deferred, recovered=report.recovered_from_deferral,
                            regated_link_not_applied=report.regated_link_not_applied, unresolved=report.unresolved),
        links_before_reader_binding=len(early),
        reveal_patterns=dict(raw_matches_in_narration=raw, matches_resolving_to_a_known_character=resolved,
                             note="REVEAL_PATTERNS = six stock phrases; counted over NARRATION spans only"),
    )
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


def t4(args) -> None:
    nid = args.novel
    T4.NOVEL = nid  # the frozen T4 machinery reads this module global at call time
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    out: dict = dict(prereg="PREREG_T4_v5_addendum_2_crossnovel.md (frozen v5 rules; single attempt)", novel=nid,
                     label_provenance="NO LABELS (system-internal)")
    pi3, prot3, _vocab3, surf3 = T4.build_pi(args.db)
    g3 = T4.commutation_gate(pi3, surf3, prot3)
    out["v3_token_level_gate"] = dict(surfaces=g3["surfaces"], G1=g3["G1_count"], G2=g3["G2_count"], G3=g3["G3_count"],
                                      passed=g3["passed"])
    pi, protected, _vocab, surfaces, _existing = V5.build_v5(args.db)
    gate = V4.full_gate(pi, surfaces, protected, args.db)
    gate["closure_passes"], gate["closure_stable"] = pi.closure_passes, pi.closure_stable
    gate["passed"] = bool(gate["passed"] and pi.closure_stable)
    out["v5_gate"] = {k: v for k, v in gate.items() if k.endswith("count") or k in
                      ("surfaces", "passed", "vocab_tokens_changed", "vocab_tokens", "closure_passes",
                       "closure_stable")}
    if not gate["passed"]:
        out["status"] = "V5_GATE_FAILED_NO_RUN"
        out["violation_classes"] = V4.classify_violations(gate, surfaces)
        Path(args.out).write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        return
    plan = {"O1": None, "O2": None, "I": T4.Renamer({}), "R": pi}
    runs = {n: T4.run_condition(n, args.db, work, rn, broken=False, smoke=0) for n, rn in plan.items()}
    base = runs["O1"]["decisions"]
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    mention_text = {mid: t for mid, t in con.execute("select id, text from mention where novel_id=?", (nid,))}
    con.close()
    keys = set(pi.mapping)
    out["mentions"] = len(base)
    out["conditions"] = {}
    for n, rn in plan.items():
        if n == "O1":
            continue
        flags = runs[n].get("flags", {})
        cmp = T4.compare(base, runs[n]["decisions"], None if n == "O2" else rn, flags, protected, keys)
        cls = T4.classify(cmp["changed_ids"], mention_text, flags, protected, keys, base=base,
                          run=runs[n]["decisions"], ren=None if n == "O2" else rn.rename)
        e = {k: v for k, v in cmp.items() if k != "changed_ids"}
        e["changed"] = len(cmp["changed_ids"])
        e["changed_classification"] = dict(cls)
        out["conditions"][n] = e
    out["status"] = "COMPLETE_NO_NEGATIVE_CONTROL"
    c = out["conditions"]
    out["verdict"] = (f"gate passed; O2 and I at 100%: {c['O2']['agreement'] == 1.0 and c['I']['agreement'] == 1.0}; "
                      f"R agreement {c['R']['agreement']:.5f}; negative control N not run: NOT a full PASS")
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "conditions"}, indent=2))
    for n, e in c.items():
        print(n, json.dumps({k: e[k] for k in ("n", "agree", "agreement", "wilson95", "changed_classification")}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["audit", "t4"])
    ap.add_argument("--db", required=True)
    ap.add_argument("--novel", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    Path(args.workdir).mkdir(parents=True, exist_ok=True)
    (audit if args.mode == "audit" else t4)(args)


if __name__ == "__main__":
    main()
