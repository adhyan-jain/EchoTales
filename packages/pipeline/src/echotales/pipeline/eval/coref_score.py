"""B-cubed coreference scoring against gold (plans.md Section 7/Section 8, HANDOFF Section 4.6/Section 4.9).

Every number in HANDOFF up to this point is either a mention count or a table a
person eyeballed for plausibility. Neither is falsifiable: "31 entities looks
about right for a 40-chapter cast" is a judgement call, and the same judgement
call cannot tell a genuine one-chapter walk-on from an over-split.

B-cubed answers the actual question -- for the mentions gold annotated, does the
system's partition agree with the annotator's -- per *mention*, which is what
makes it robust to entity-size skew that a per-cluster metric would distort.

For each mention `m` with system cluster `sys(m)` and gold cluster `gold(m)`:

    precision(m) = |sys(m) ∩ gold(m)| / |sys(m)|
    recall(m)    = |sys(m) ∩ gold(m)| / |gold(m)|

averaged over every gold-annotated mention that the system also resolved.
Precision answers "of what the system grouped with m, how much should have
been" -- low precision is over-merging. Recall answers "of what should have
been grouped with m, how much did the system find" -- low recall is
over-splitting, which is HANDOFF's current diagnosis. Reporting only one of the
two would hide whichever failure mode is not being tested for.

`kind` and `confirmed` filtering happens in the caller via `GoldSet`, not here --
this module answers one question (does the partition agree) and stays reusable
for the person-only view, the human-confirmed-only view, and the draft-quality
view over the same code path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from echotales.core.store import Store
from echotales.pipeline.eval.gold import GoldMention, GoldSet


@dataclass(slots=True)
class Disagreement:
    """One mention where system and gold clusters diverge, for the miss report."""

    surface: str
    chapter: float
    gold_identity: str
    system_target_id: str | None
    precision: float
    recall: float


@dataclass(slots=True)
class B3Result:
    novel_id: str
    precision: float
    recall: float
    f1: float
    #: Gold mentions actually scored -- excludes ones the system never resolved.
    scored: int
    #: Gold mentions the system produced no link for at all. Counted separately
    #: from a wrong link: an unresolved mention is a recall gap the retriever
    #: never got a chance at, not a scoring error.
    unresolved: int
    total_gold: int
    worst: list[Disagreement] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"{self.novel_id}: B-cubed over {self.scored}/{self.total_gold} gold mentions "
            f"({self.unresolved} unresolved by the system)",
            f"  precision={self.precision:.1%}  recall={self.recall:.1%}  "
            f"f1={self.f1:.1%}",
        ]
        if self.precision < self.recall - 0.05:
            lines.append("  precision < recall: net effect is over-merging on this sample")
        elif self.recall < self.precision - 0.05:
            lines.append("  recall < precision: net effect is over-splitting on this sample")
        return "\n".join(lines)

    def worst_report(self, limit: int = 10) -> str:
        if not self.worst:
            return "  no disagreements below the worst-N cutoff"
        lines = ["  worst disagreements (lowest combined precision+recall first):"]
        for d in self.worst[:limit]:
            sys_label = d.system_target_id or "(unresolved)"
            lines.append(
                f"    ch{d.chapter:g} {d.surface!r}: gold={d.gold_identity!r} "
                f"system={sys_label!r}  p={d.precision:.2f} r={d.recall:.2f}"
            )
        return "\n".join(lines)


def _block_starts(store: Store, novel_id: str, chapter: float) -> dict[int, int]:
    """Chapter-absolute start offset of each block, keyed by block index.

    `Mention.offset` is relative to the **block** it was found in (it comes
    from `span.start + hit.start`, and `Span.start` is block-local), while
    `Chapter.story_text` -- and therefore every gold offset -- is the
    `"\\n\\n"`-joined concatenation of blocks. The two are different coordinate
    systems, and a mention's offset is only comparable to a gold offset after
    translating through this map. Comparing them directly, as an earlier
    version of this scorer did, silently matches nothing past the chapter's
    first block and reports catastrophic recall on every chapter with more than
    one paragraph -- i.e. all of them.
    """
    chapter_obj = store.get_chapter(novel_id, chapter)
    if chapter_obj is None:
        return {}
    starts: dict[int, int] = {}
    pos = 0
    first = True
    for block in chapter_obj.blocks:
        if not block.block_type.is_story_content:
            continue
        if not first:
            pos += 2  # the "\n\n" join separator
        starts[block.index] = pos
        pos += len(block.text)
        first = False
    return starts


def _system_partition(
    store: Store, novel_id: str, gold: GoldSet
) -> dict[tuple[str, float, int], str | None]:
    """Mention key -> system target_id, restricted to gold-annotated positions.

    Matched by chapter-absolute offset after translating each system mention
    out of its block-local coordinates (see `_block_starts`). A small window is
    still allowed on top of that, since gold offsets come from a fresh
    `str.find` over `story_text` and a mention's stored surface can differ from
    the annotated one by trailing punctuation the tokenizer split differently.
    """
    gold_positions: dict[float, list[GoldMention]] = defaultdict(list)
    for m in gold.mentions:
        gold_positions[m.chapter].append(m)

    result: dict[tuple[str, float, int], str | None] = {}
    for chapter, wanted in gold_positions.items():
        block_starts = _block_starts(store, novel_id, chapter)
        mentions = store.get_mentions(novel_id, chapter=chapter)
        absolute = [
            (block_starts.get(sm.block_index, 0) + sm.offset, sm)
            for sm in mentions
            if sm.block_index in block_starts
        ]
        for gm in wanted:
            best = None
            best_dist = 8  # characters; tight now that coordinates actually agree
            for abs_offset, sm in absolute:
                if sm.text.strip().casefold() != gm.surface.strip().casefold():
                    continue
                dist = abs(abs_offset - gm.offset)
                if dist < best_dist:
                    best, best_dist = sm, dist
            result[gm.key] = best.target_id if best is not None else None
    return result


def score_b3(store: Store, novel_id: str, gold: GoldSet) -> B3Result:
    """B-cubed precision/recall/F1 of the system's partition against gold."""
    gold_clusters: dict[str, set[tuple[str, float, int]]] = defaultdict(set)
    for m in gold.mentions:
        if m.identity:
            gold_clusters[m.identity].add(m.key)
    system_of = _system_partition(store, novel_id, gold)
    system_clusters: dict[str, set[tuple[str, float, int]]] = defaultdict(set)
    for key, target_id in system_of.items():
        if target_id:
            system_clusters[target_id].add(key)

    scorable = [m for m in gold.mentions if m.identity]
    unresolved = sum(1 for m in scorable if not system_of.get(m.key))
    scored = [m for m in scorable if system_of.get(m.key)]

    disagreements: list[Disagreement] = []
    precisions: list[float] = []
    recalls: list[float] = []

    for m in scored:
        key = m.key
        target_id = system_of[key]
        assert target_id is not None
        sys_set = system_clusters[target_id]
        gold_set = gold_clusters[m.identity]
        overlap = len(sys_set & gold_set)
        p = overlap / len(sys_set) if sys_set else 0.0
        r = overlap / len(gold_set) if gold_set else 0.0
        precisions.append(p)
        recalls.append(r)
        if p < 1.0 or r < 1.0:
            disagreements.append(
                Disagreement(m.surface, m.chapter, m.identity, target_id, p, r)
            )

    for m in scorable:
        if not system_of.get(m.key):
            disagreements.append(Disagreement(m.surface, m.chapter, m.identity, None, 0.0, 0.0))

    avg_p = sum(precisions) / len(precisions) if precisions else 0.0
    avg_r = sum(recalls) / len(recalls) if recalls else 0.0
    # Unresolved mentions count as zero recall in the denominator too, or the
    # metric would reward the system for simply refusing hard cases.
    if scorable:
        avg_r = sum(recalls) / len(scorable)
    f1 = 2 * avg_p * avg_r / (avg_p + avg_r) if (avg_p + avg_r) else 0.0

    disagreements.sort(key=lambda d: d.precision + d.recall)

    return B3Result(
        novel_id=novel_id,
        precision=avg_p,
        recall=avg_r,
        f1=f1,
        scored=len(scored),
        unresolved=unresolved,
        total_gold=len(scorable),
        worst=disagreements,
    )
