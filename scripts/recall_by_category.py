"""Retriever recall@K on the SILVER hard cases, broken down by hard-case category.

Complements `echotales eval --gold ...hardcases.jsonl`, which breaks recall
down by alias type. The categories (`[body_change]`, `[reveal]`,
`[title_transfer]`, `[disguise]`, `[relational_deictic]`) are the annotator's
own labels for *why* a case is hard, read from the `note` prefix.

Cases come from the CLI's own builder (`build_gold_retrieval_cases`), and the
index is built with production's `_context_for`. The *query* context is
reported two ways, because they disagree and the difference is itself a
finding:

  - `snippet`    -- the gold record's ~70-char evidence snippet, which is what
                    `echotales eval` has always used for the query;
  - `production` -- `_context_for` over the chapter, which is what the real
                    resolver queries with.

An earlier draft of this script used a 400-char window and called it "exactly
as the CLI builds it"; it was neither, and produced 95.6% @10 where the CLI
reported 84.4%.

Note what this measures: retrieval *given the gold span*. Most hard-case spans
are never detected as mentions in the real pipeline (docs/SCORER_DIAGNOSIS.md
Section 4), so this is an upper bound on what retrieval could contribute.

SILVER -- LLM-derived reference set (Claude), not human gold; no IAA.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval.calibrate import _identity_to_target
from echotales.pipeline.eval.gold import SILVER_BANNER, read_gold
from echotales.pipeline.eval.retriever_eval import build_gold_retrieval_cases
from echotales.pipeline.resolve.retrieve import CandidateRetriever
from echotales.pipeline.resolve.runner import _context_for

DB = "data/reruns/ner-window-ri.db"
NOVEL = "reverend-insanity"
KS = (1, 5, 10, 20)


def category(note: str) -> str:
    return note[1:note.index("]")] if note.startswith("[") and "]" in note else "uncategorised"


def main() -> int:
    store = Store(DB)
    gold = read_gold("data/gold/reverend-insanity-hardcases.jsonl", novel_id=NOVEL).silver_only.entities_only
    mapping, _unmapped = _identity_to_target(store, NOVEL, gold)

    texts: dict[float, str] = {}

    def story(ch: float) -> str:
        if ch not in texts:
            c = store.get_chapter(NOVEL, ch)
            texts[ch] = c.story_text if c else ""
        return texts[ch]

    retriever = CandidateRetriever()
    for m in store.get_mentions(NOVEL, resolved_only=True):
        if m.target_id:
            retriever.observe(m.target_id, m.text, _context_for(m, story(m.chapter)), m.chapter, label=m.text)

    cases, _unmapped = build_gold_retrieval_cases(gold, store, NOVEL)
    mapped = [g for g in gold.mentions if g.identity and mapping.get(g.identity)]
    assert len(mapped) == len(cases), "case order must match gold order"

    class _Q:  # the one attribute _context_for reads
        def __init__(self, text: str) -> None:
            self.text = text

    hits: dict[str, dict[str, list[int | None]]] = {"snippet": defaultdict(list), "production": defaultdict(list)}
    for g, case in zip(mapped, cases, strict=True):
        for mode, ctx in (("snippet", case.context),
                          ("production", _context_for(_Q(case.surface), story(g.chapter)))):  # type: ignore[arg-type]
            ranked = [c.target_id for c in retriever.retrieve(case.surface, ctx, k=max(KS))]
            rank = ranked.index(case.expected_target_id) + 1 if case.expected_target_id in ranked else None
            hits[mode][category(g.note)].append(rank)
            hits[mode]["ALL"].append(rank)

    table = {
        mode: {
            cat: {"n": len(r), **{f"@{k}": round(sum(1 for x in r if x and x <= k) / len(r), 3) for k in KS}}
            for cat, r in sorted(by_cat.items())
        }
        for mode, by_cat in hits.items()
    }
    out = Path("data/eval/recall_by_category.json")
    out.write_text(json.dumps({"banner": SILVER_BANNER, "db": DB, "recall": table}, indent=2) + "\n")
    print(SILVER_BANNER)
    for mode, rows in table.items():
        print(f"\nquery context = {mode}")
        print(f"{'category':22} {'n':>4} " + " ".join(f"{'@'+str(k):>7}" for k in KS))
        for cat, row in rows.items():
            print(f"{cat:22} {row['n']:>4} " + " ".join(f"{row['@'+str(k)]:>7.1%}" for k in KS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
