"""Measured effect of the scope-A adapters on a SCRATCH copy of the real RI database (counts only, no labels).

  B1  re-gated deferred LINKs that the old code counted as "recovered" without writing a link
      (new default: regated_link_not_applied, case stays queued; `apply_deferred_links=True` writes them)
  B2  a prefix run (`chapters=1-20`) resolves only those chapters and skips the non-causal volume passes
  A7  `causal_titles=True` removes the retroactive chapter-1 "the clan head" links

LABEL PROVENANCE: system-internal consistency; no reference labels; nothing here is accuracy.

    python scripts/chimera/adapters_before_after.py --db <SCRATCH copy of the RI db> --workdir <scratch dir> --out data/eval/chimera/adapters_before_after.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.ingest.adapters import ChapterRange  # noqa: E402
from echotales.pipeline.ingest.normalize import comparison_key  # noqa: E402
from echotales.pipeline.ingest.sources import get_source  # noqa: E402
from echotales.pipeline.mentions.induce import load_or_seed  # noqa: E402
from echotales.pipeline.resolve import resolve_novel  # noqa: E402

NOVEL = "reverend-insanity"


def fresh(src: str, work: Path, name: str) -> Store:
    dst = work / f"{name}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(dst) + suffix).unlink(missing_ok=True)
    shutil.copy(src, dst)
    return Store(str(dst))


def summarise(store: Store) -> dict:
    ments = store.get_mentions(NOVEL)
    linked = [m for m in ments if m.target_id]
    learned: dict[tuple[str, str], int] = {}
    for b in store.all_aliases(NOVEL):
        if b.observer_id == "READER":
            k = (b.target_id, comparison_key(b.alias))
            learned[k] = min(learned.get(k, 10**9), b.learned_at_pos.chapter)
    early = sum(1 for m in linked if (lc := learned.get((m.target_id, comparison_key(m.text)))) is not None
                and m.chapter < lc)
    return dict(mentions=len(ments), linked=len(linked),
                by_method=dict(Counter(m.method.value for m in linked if m.method)),
                linked_before_reader_binding=early, chapters_with_links=len({m.chapter for m in linked}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    lex = load_or_seed(get_source(NOVEL).lexicon)
    res: dict = dict(label_provenance="NO LABELS: system-internal counts on a scratch copy of the RI database")

    s = fresh(args.db, work, "default")
    r = resolve_novel(NOVEL, s, lexicon=lex, force_rewipe=True)
    res["B1_default_run"] = dict(
        recovered_from_deferral=r.recovered_from_deferral, regated_link_not_applied=r.regated_link_not_applied,
        unresolved=r.unresolved, deferred=r.deferred,
        old_code_would_have_reported=dict(recovered=r.recovered_from_deferral + r.regated_link_not_applied,
                                          unresolved=r.unresolved - r.regated_link_not_applied),
        summary_counts=summarise(s))
    s = fresh(args.db, work, "apply")
    r2 = resolve_novel(NOVEL, s, lexicon=lex, force_rewipe=True, apply_deferred_links=True)
    res["B1_apply_deferred_links_run"] = dict(
        recovered_from_deferral=r2.recovered_from_deferral, regated_link_not_applied=r2.regated_link_not_applied,
        unresolved=r2.unresolved, summary_counts=summarise(s))

    s = fresh(args.db, work, "prefix")
    r3 = resolve_novel(NOVEL, s, lexicon=lex, force_rewipe=True, chapters=ChapterRange.parse("1-20"))
    res["B2_prefix_1_20"] = dict(
        summary_counts=summarise(s),
        max_chapter_with_a_link=max((m.chapter for m in s.get_mentions(NOVEL) if m.target_id), default=None),
        groups_resolved=r3.groups)

    s = fresh(args.db, work, "causal")
    resolve_novel(NOVEL, s, lexicon=lex, force_rewipe=True, causal_titles=True)
    res["A7_causal_titles"] = dict(summary_counts=summarise(s))
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
