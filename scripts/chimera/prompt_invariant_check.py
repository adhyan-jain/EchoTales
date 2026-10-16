"""Prompt-boundary invariant audit (Track S diagnostic, read-only, no labels, no model, no spend).

Invariant under test: a brief built for position c (reader observer) must not name an entity through a link the
reader has not yet been told. Two measurements on a SCRATCH copy of a novel database:

  1. mention level: a linked mention whose chapter is earlier than the earliest READER alias binding learned for
     the same (entity, normalised surface). Counted by resolution method.
  2. brief level: for sampled chapters, run the real `world.context.story_context` per block and count PRESENT
     characters that appear only through a mention counted in (1).

LABEL PROVENANCE: system-internal consistency only. There are NO reference labels and nothing here is accuracy.
It audits; it changes nothing (existing code is imported, not edited).

    python scripts/chimera/prompt_invariant_check.py --db <scratch copy> --novel reverend-insanity --out data/eval/chimera/prompt_invariant_ri.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from math import sqrt
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"

from echotales.core.enums import ReferenceMode  # noqa: E402
from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.ingest.normalize import comparison_key  # noqa: E402
from echotales.pipeline.world.context import story_context  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, (c - r) / d), min(1.0, (c + r) / d)]


def row(k: int, n: int) -> dict:
    return dict(k=k, n=n, rate=(k / n if n else None), wilson95=wilson(k, n))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--novel", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--brief-chapters", default="1-12,20,40,60,80,100,120,140,160,180")
    args = ap.parse_args()
    store = Store(args.db)
    nid = args.novel

    learned: dict[tuple[str, str], int] = {}
    for b in store.all_aliases(nid):
        if b.observer_id != "READER":
            continue
        k = (b.target_id, comparison_key(b.alias))
        learned[k] = min(learned.get(k, 10**9), b.learned_at_pos.chapter)

    by_method: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # linked, early, no_binding
    early_ids: set[str] = set()
    early_examples = []
    for m in store.get_mentions(nid):
        if not m.target_id:
            continue
        meth = m.method.value if m.method else "NULL"
        by_method[meth][0] += 1
        lc = learned.get((m.target_id, comparison_key(m.text)))
        if lc is None:
            by_method[meth][2] += 1
        elif m.chapter < lc:
            by_method[meth][1] += 1
            early_ids.add(m.id)
            if len(early_examples) < 8:
                early_examples.append(dict(mention_chapter=m.chapter, binding_learned_chapter=lc, method=meth,
                                           alias_type=m.alias_type.value))
    total_linked = sum(v[0] for v in by_method.values())
    total_early = sum(v[1] for v in by_method.values())

    chapters: list[float] = []
    for part in args.brief_chapters.split(","):
        if "-" in part:
            a, b = part.split("-")
            chapters += [float(x) for x in range(int(a), int(b) + 1)]
        else:
            chapters.append(float(part))
    have = set(store.chapter_numbers(nid))
    briefs = leak_briefs = leak_slots = 0
    brief_examples = []
    for ch in chapters:
        if ch not in have:
            continue
        mentions = store.get_mentions(nid, ch)
        blocks = sorted({m.block_index for m in mentions if m.target_id})
        for bi in blocks:
            ctx = story_context(nid, store, ch, [bi], include_appearance=False)
            if not ctx.characters:
                continue
            briefs += 1
            present_ok: set[str] = set()
            present_early: set[str] = set()
            for m in mentions:
                if m.block_index != bi or not m.target_id or m.reference_mode is not ReferenceMode.PRESENT:
                    continue
                (present_early if m.id in early_ids else present_ok).add(m.target_id)
            leaked = present_early - present_ok
            if leaked:
                leak_briefs += 1
                leak_slots += len(leaked)
                if len(brief_examples) < 5:
                    brief_examples.append(dict(chapter=ch, block=bi, leaked_entities=len(leaked)))

    res = dict(
        label_provenance="NO LABELS: system-internal consistency audit (no reference labels, not accuracy)",
        novel=nid,
        mention_level={
            "linked_mentions": total_linked,
            "linked_before_reader_binding_learned": row(total_early, total_linked),
            "by_method": {k: dict(linked=v[0], before_binding=v[1], no_binding_for_surface=v[2])
                          for k, v in by_method.items()},
            "examples_numbers_only": early_examples,
        },
        brief_level=dict(
            note="briefs built by the real story_context (include_appearance=False); PRESENT characters reached "
                 "only through a mention linked before the reader was told",
            chapters_sampled=len([c for c in chapters if c in have]),
            briefs_with_characters=briefs,
            briefs_naming_an_entity_early=row(leak_briefs, briefs),
            leaked_entity_slots=leak_slots,
            examples_numbers_only=brief_examples,
        ),
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
