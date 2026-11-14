"""Review items for mention groups the gate could not decide (non-negotiable 7).

The deferred queue is in memory and discarded when the run ends, so a named character the gate could not place used
to stay unlinked with no trace: 13 groups on Lord of the Mysteries, 23 on Omniscient Reader's Viewpoint, 12 on
Reverend Insanity (deterministic builds), 2 on the canonical Reverend Insanity database. A bounded, measurable queue
needs each of them recorded.

Rules (also tested in test_resolve_review_items.py):
- id = kind + novel + first mention id + short hash of the surface key: stable across re-runs, never clock-derived.
- An open item of the same id is refreshed in place (created_at kept); no duplicate is ever added.
- A reviewer-resolved item stays resolved unless the evidence fingerprint (reason kind + candidate ids) changed.
- An item the machine closed ("auto:" resolution) is reopened if the case returns.
- An open item whose case is gone (the group now links) is closed with an "auto:" resolution, not deleted, so the
  history of what was once undecided survives.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from echotales.core.models import Mention, ReviewItem
from echotales.core.store import Store, normalize_alias
from echotales.pipeline.resolve.gate import DeferredCase

KIND = "resolve_deferred"
AUTO_CLOSED = "auto:linked_on_rerun"


def reason_kind(reason: str) -> str:
    if reason.startswith("top two candidates within"):
        return "tie_margin"
    if "deferred band" in reason:
        return "below_link_above_new"
    return "other"


def item_id(novel_id: str, case: DeferredCase, first_mention_id: str) -> str:
    digest = hashlib.sha1(normalize_alias(case.surface).encode("utf-8")).hexdigest()[:8]
    return f"{KIND}:{novel_id}:{first_mention_id}:{digest}"


def _fingerprint(kind: str, case: DeferredCase) -> str:
    # Ids and reason kind, not scores: scores drift in the last decimals with any gazetteer change and would
    # re-open a reviewer's decision for nothing.
    raw = kind + "|" + ",".join(sorted(c.target_id for c in case.candidates))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@dataclass(slots=True)
class ReviewOutcome:
    written: int = 0
    closed: int = 0


def build_item(
    novel_id: str,
    case: DeferredCase,
    open_mentions: list[Mention],
    *,
    link_threshold: float,
    new_threshold: float,
) -> ReviewItem:
    kind = reason_kind(case.reason)
    surfaces = sorted({m.text for m in open_mentions})
    ranked = sorted(case.candidates, key=lambda c: c.probability, reverse=True)
    group = {
        "role": "group",
        "surfaces": surfaces,
        "mention_ids": [m.id for m in open_mentions],
        "group_id": case.group_id,
        "reason_kind": kind,
        "reason": case.reason,
        "adjudication": case.adjudication,
        "link_threshold": round(link_threshold, 4),
        "new_threshold": round(new_threshold, 4),
        "evidence_hash": _fingerprint(kind, case),
        "excerpt": case.context[:200],
    }
    candidates = [
        {
            "role": "candidate",
            "target_id": c.target_id,
            "label": c.label,
            "probability": round(c.probability, 4),
            "retrieval_score": round(c.retrieval_score, 4),
        }
        for c in ranked[:5]
    ]
    best = f"; best candidate {ranked[0].label!r} p={ranked[0].probability:.3f}" if ranked else "; no candidates"
    return ReviewItem(
        id=item_id(novel_id, case, open_mentions[0].id),
        novel_id=novel_id,
        chapter=case.chapter,
        kind=KIND,
        message=(
            f"{', '.join(repr(s) for s in surfaces)} ({len(open_mentions)} mention(s)) left unlinked: "
            f"{case.reason}{best}"
        ),
        candidates=[group, *candidates],
    )


def upsert(store: Store, item: ReviewItem, existing: ReviewItem | None) -> bool:
    """Write `item` honouring a prior decision. Returns True when a row was written."""
    if existing is None:
        item.created_at = time.time()
        store.add_review_item(item)
        return True
    item.created_at = existing.created_at
    if existing.resolved:
        old = existing.candidates[0].get("evidence_hash") if existing.candidates else None
        new = item.candidates[0]["evidence_hash"]
        machine = (existing.resolution or "").startswith("auto:")
        if old == new and not machine:
            return False
    store.add_review_item(item)
    return True


def close_stale(store: Store, novel_id: str, live_ids: set[str]) -> int:
    closed = 0
    for old in store.list_review_items(novel_id, resolved=False):
        if old.kind == KIND and old.id not in live_ids:
            store.resolve_review_item(old.id, AUTO_CLOSED)
            closed += 1
    return closed
