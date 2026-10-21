"""E4. Discourse-position semantics on real data. Pre-declaration:
docs/research/ENGINEERING_PROBES.md (written before this ran).

LABEL PROVENANCE: SYSTEM-INTERNAL (real scratch DB copies, opened read-only; no labels). Counts and ids only.

    python scripts/chimera/eng_probe_e4_discourse_position.py --novel reverend-insanity --out <json>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eng_probe_common as C  # noqa: E402
from echotales.core.enums import TargetKind, TruthStatus  # noqa: E402
from echotales.core.models import DiscoursePosition as DP  # noqa: E402
from echotales.core.state import StateResolver  # noqa: E402

from eng_probe_e1_prefix_causality import wilson  # noqa: E402


def concordance(items: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    """items = (block_index, offset) in TRUE text order key; DiscoursePosition order uses offset only.

    Returns (concordant, discordant, tied_in_discourse_position_but_distinct_in_text, pairs)."""
    n = len(items)
    if n < 2:
        return 0, 0, 0, 0
    b = np.array([x[0] for x in items])
    o = np.array([x[1] for x in items])
    iu = np.triu_indices(n, k=1)
    tb = np.sign(b[iu[1]] - b[iu[0]])
    to = np.sign(o[iu[1]] - o[iu[0]])
    # true order sign: block first, then offset within block
    true = np.where(tb != 0, tb, to)
    distinct = true != 0
    dp = to
    conc = int(np.sum(distinct & (dp == true)))
    disc = int(np.sum(distinct & (dp == -true)))
    tied = int(np.sum(distinct & (dp == 0)))
    return conc, disc, tied, int(np.sum(distinct))


def offset_unit_test(db: str, nid: str) -> dict:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    by_ch: dict[float, list[tuple[int, int]]] = defaultdict(list)
    for r in con.execute("select chapter, block_index, offset from mention where novel_id=?", (nid,)):
        by_ch[r["chapter"]].append((r["block_index"], r["offset"]))
    tot = np.zeros(4, dtype=np.int64)
    for items in by_ch.values():
        tot += np.array(concordance(items))
    conc, disc, tied, pairs = (int(x) for x in tot)
    mention_level = dict(
        pairs_with_distinct_text_positions=pairs, concordant=conc, discordant=disc, tied_offsets=tied,
        concordant_rate=round(conc / pairs, 4) if pairs else None, concordant_wilson=wilson(conc, pairs),
        discordant_rate=round(disc / pairs, 4) if pairs else None,
        a_random_order_would_give_concordance_about=0.5)
    # the facts themselves: alias bindings' learned position, joined to the founding mention by (chapter, offset, target)
    mention_blocks: dict[tuple, set] = defaultdict(set)
    for r in con.execute("select chapter, block_index, offset, target_id from mention where novel_id=? and target_id is not null", (nid,)):
        mention_blocks[(int(r["chapter"]), r["offset"], r["target_id"])].add(r["block_index"])
    fact_by_ch: dict[int, list[tuple[int, int]]] = defaultdict(list)
    unmatched = ambiguous = 0
    for r in con.execute("select target_id, learned_chapter, learned_offset from alias_binding where novel_id=? and observer_id='READER'", (nid,)):
        blocks = mention_blocks.get((r["learned_chapter"], r["learned_offset"], r["target_id"]))
        if not blocks:
            unmatched += 1
            continue
        if len(blocks) > 1:
            ambiguous += 1
        fact_by_ch[r["learned_chapter"]].append((min(blocks), r["learned_offset"]))
    ft = np.zeros(4, dtype=np.int64)
    for items in fact_by_ch.values():
        ft += np.array(concordance(items))
    fc, fd, ftd, fp = (int(x) for x in ft)
    fact_level = dict(
        alias_bindings_matched_to_a_founding_mention=sum(len(v) for v in fact_by_ch.values()),
        unmatched=unmatched, ambiguous_block=ambiguous,
        same_chapter_fact_pairs_distinct_in_text=fp, concordant=fc, discordant=fd, tied_offsets=ftd,
        concordant_rate=round(fc / fp, 4) if fp else None, concordant_wilson=wilson(fc, fp))
    # share of positions that use a non-zero offset at all
    shares = {}
    for table in ("alias_binding", "attribute", "self_persona_binding"):
        row = con.execute(f"select count(*), sum(learned_offset>0) from {table}").fetchone()
        shares[table] = dict(rows=row[0], with_nonzero_offset=row[1] or 0)
    con.close()
    return dict(mention_level=mention_level, fact_level=fact_level, nonzero_offset_share=shares)


def chapter_lag(db: str, nid: str, max_entities: int = 10**9) -> dict:
    store = C.Store(db)
    res = StateResolver(store, nid)
    selves = [s for s in store.all_selves(nid) if s.kind.is_person][:max_entities]
    chapters_total = len(store.chapter_numbers(nid))
    q = diff_alias = diff_attr = 0
    q_attr = 0
    first_chapter_missing = n_with_alias = 0
    for s in selves:
        al = store.get_aliases_for(TargetKind.SELF, s.id)
        if not al:
            continue
        ch0 = min(b.learned_at_pos.chapter for b in al)
        n_with_alias += 1
        # lifetime = first learned chapter .. last learned chapter of any of its aliases
        ch1 = chapters_total
        for c in range(ch0, ch1 + 1):
            a = res.state_of(s.id, position=float(c))
            b = res.state_of(s.id, position=float(c), knowledge_pos=DP(chapter=c, offset=10**6))
            q += 1
            if sorted(a.aliases) != sorted(b.aliases):
                diff_alias += 1
            if c == ch0 and not a.aliases and b.aliases:
                first_chapter_missing += 1
        # persona attributes
        for b in store.get_self_persona_bindings(self_id=s.id):
            pid = b.persona_id
            pa = store.get_attributes(TargetKind.PERSONA, pid)
            if not pa:
                continue
            a0 = min(x.learned_at_pos.chapter for x in pa)
            a1 = chapters_total
            for c in range(a0, a1 + 1):
                x = res.state_of(pid, target_kind=TargetKind.PERSONA, position=float(c))
                y = res.state_of(pid, target_kind=TargetKind.PERSONA, position=float(c),
                                 knowledge_pos=DP(chapter=c, offset=10**6))
                q_attr += 1
                if x.attributes != y.attributes:
                    diff_attr += 1
    store.close()
    return dict(
        entities_with_aliases=n_with_alias, alias_queries_span_first_learned_to_end_of_volume=q, alias_queries_that_change_with_end_of_chapter_knowledge=diff_alias,
        alias_change_rate=round(diff_alias / q, 4) if q else None, alias_change_wilson=wilson(diff_alias, q),
        entities_whose_own_name_is_missing_at_their_first_chapter=first_chapter_missing,
        persona_attribute_queries=q_attr, persona_attribute_queries_that_change=diff_attr,
        persona_attr_change_rate=round(diff_attr / q_attr, 4) if q_attr else None,
        persona_attr_change_wilson=wilson(diff_attr, q_attr), chapters_in_novel=chapters_total)


def attribute_conflicts(db: str, nid: str) -> dict:
    """Real-data prevalence of the winner rule's tie case (E3/I8) and of same-chapter conflicts (block-relative offsets)."""
    store = C.Store(db)
    rows = []
    for pid in {r[0] for r in store.conn.execute("select distinct target_id from attribute where novel_id=? and target_kind='PERSONA'", (nid,))}:
        rows.extend(store.get_attributes(TargetKind.PERSONA, pid))
    by_key: dict[tuple, list] = defaultdict(list)
    for a in rows:
        by_key[(a.target_id, a.key)].append(a)
    q = conflict = tie = same_chapter = 0
    groups_with_multi_value = 0
    n_ch = len(store.chapter_numbers(nid))
    for (_pid, _key), lst in by_key.items():
        if len({a.value for a in lst}) < 2:
            continue
        groups_with_multi_value += 1
        for c in range(1, n_ch + 1):
            kp = DP(chapter=c)
            cand = [a for a in lst if a.learned_at_pos <= kp and a.interval.contains(float(c)).is_possible
                    and a.truth_status is not TruthStatus.FALSE and a.retracted_at is None]
            vals = {a.value for a in cand}
            if len(vals) < 2:
                continue
            q += 1
            conflict += 1
            top = max((a.learned_at_pos.chapter, a.learned_at_pos.offset) for a in cand)
            top_vals = {a.value for a in cand if (a.learned_at_pos.chapter, a.learned_at_pos.offset) == top}
            if len(top_vals) > 1:
                tie += 1
            top_ch = max(a.learned_at_pos.chapter for a in cand)
            if len({a.value for a in cand if a.learned_at_pos.chapter == top_ch}) > 1:
                same_chapter += 1
    store.close()
    return dict(
        persona_key_groups=len(by_key), groups_with_two_or_more_distinct_values=groups_with_multi_value,
        queries_with_conflicting_admissible_values=conflict, of_which_winner_decided_by_exact_tie=tie,
        of_which_winner_decided_inside_one_chapter_by_block_relative_offset=same_chapter)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    nid = args.novel
    db = C.fresh_copy(C.DBS[nid], C.SCRATCH / "eng", f"{nid}_e4")  # copy: even reads never touch the source scratch DB
    out = dict(probe="E4 discourse-position semantics (real data)", label_provenance="SYSTEM-INTERNAL, no labels",
               novel=nid, offset_unit=offset_unit_test(db, nid), chapter_lag=chapter_lag(db, nid),
               attribute_conflicts=attribute_conflicts(db, nid))
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
