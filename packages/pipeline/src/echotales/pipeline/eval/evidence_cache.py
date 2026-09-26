"""Capture every scored (mention, candidate) evidence vector to the database.

`docs/design/details.md` and `docs/design/plans.md` have claimed since the design phase that ablations
"cost no additional LLM passes because they re-score cached evidence vectors."
**No such cache existed.** `EvidenceVector` was built inside `resolve_group`,
consumed by the scorer, and dropped when the group finished, so every ablation
condition meant a full re-resolve of the volume (EVOLUTION 4.78).

The capture reuses the monkeypatch shape `eval/calibrate.py::collect_samples`
already uses -- wrapping `resolve.runner.score_evidence` for the duration of a
run -- rather than adding a `capture=` parameter to the scoring path. That is
deliberate: the resolver's hot loop should not grow an evaluation concern it
carries on every production run, and the patch site is a single module-level
name that both callers already treat as an interception point.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

from echotales.core.models import FEATURE_ORDER, EvidenceVector
from echotales.core.store import Store

#: Rows buffered before a flush. The cache exists because writing it is
#: cheaper than recomputing it, so it must not turn one resolve into tens of
#: thousands of individual INSERTs either.
FLUSH_EVERY = 2_000


@contextmanager
def capture_evidence(
    store: Store, novel_id: str, *, run_tag: str = "", replace: bool = True
) -> Iterator[dict[str, int]]:
    """Record every evidence vector scored inside the `with` block.

    Yields a mutable counter dict so the caller can report how much was
    captured without reaching back into the database.
    """
    from echotales.pipeline.resolve import runner as resolve_runner

    if replace:
        store.clear_scoring_evidence(novel_id, run_tag)

    stats = {"captured": 0}
    buffer: list[tuple[str, str, float, str, str, str, str, str]] = []
    original = resolve_runner.score_evidence

    def flush() -> None:
        if buffer:
            store.add_scoring_evidence(buffer)
            store.conn.commit()
            buffer.clear()

    def traced(mention, candidate, profile, ctx):  # type: ignore[no-untyped-def]
        vector = original(mention, candidate, profile, ctx)
        buffer.append(
            (
                novel_id,
                run_tag,
                float(mention.chapter),
                str(mention.id or ""),
                str(mention.text or ""),
                str(candidate.target_id or ""),
                str(candidate.label or ""),
                json.dumps({name: getattr(vector, name) for name in FEATURE_ORDER}),
            )
        )
        stats["captured"] += 1
        if len(buffer) >= FLUSH_EVERY:
            flush()
        return vector

    resolve_runner.score_evidence = traced  # type: ignore[assignment]
    try:
        yield stats
    finally:
        # Restored in `finally`, not after the yield: a resolve that dies
        # mid-volume must not leave a traced `score_evidence` installed for
        # the rest of the process, which would keep appending to a table the
        # caller believes it finished writing.
        resolve_runner.score_evidence = original  # type: ignore[assignment]
        flush()


def load_evidence(
    store: Store, novel_id: str, *, run_tag: str = ""
) -> list[tuple[float, str, str, str, EvidenceVector]]:
    """Read the cache back as (chapter, mention_id, surface, candidate_id, vector)."""
    out: list[tuple[float, str, str, str, EvidenceVector]] = []
    for chapter, mention_id, surface, candidate_id, _label, features in (
        store.iter_scoring_evidence(novel_id, run_tag)
    ):
        try:
            values = json.loads(features)
        except ValueError:
            continue
        out.append(
            (
                chapter,
                mention_id,
                surface,
                candidate_id,
                EvidenceVector(**{k: v for k, v in values.items() if k in FEATURE_ORDER}),
            )
        )
    return out
