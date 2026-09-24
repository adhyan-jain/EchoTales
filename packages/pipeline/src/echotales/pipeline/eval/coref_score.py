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

from echotales.core.models import Mention
from echotales.core.store import Store
from echotales.pipeline.eval.gold import GoldMention, GoldSet, MentionKey


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
) -> dict[MentionKey, str | None]:
    """Mention key -> system target_id, restricted to gold-annotated positions.

    None means either "no system mention there" or "a mention with no target";
    callers that must tell those apart use `align_system_mentions` directly.
    """
    return {
        key: (sm.target_id if sm is not None else None)
        for key, sm in align_system_mentions(store, novel_id, gold).items()
    }


def align_system_mentions(
    store: Store, novel_id: str, gold: GoldSet
) -> dict[MentionKey, Mention | None]:
    """Mention key -> the system mention aligned to it, or None if undetected.

    Matched by chapter-absolute offset after translating each system mention
    out of its block-local coordinates (see `_block_starts`). A small window is
    still allowed on top of that, since gold offsets come from a fresh
    `str.find` over `story_text` and a mention's stored surface can differ from
    the annotated one by trailing punctuation the tokenizer split differently.
    """
    gold_positions: dict[float, list[GoldMention]] = defaultdict(list)
    for m in gold.mentions:
        gold_positions[m.chapter].append(m)

    result: dict[MentionKey, Mention | None] = {}
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
            result[gm.key] = best
    return result


def score_b3(store: Store, novel_id: str, gold: GoldSet) -> B3Result:
    """B-cubed precision/recall/F1 of the system's partition against gold."""
    gold_clusters: dict[str, set[MentionKey]] = defaultdict(set)
    for m in gold.mentions:
        if m.identity:
            gold_clusters[m.identity].add(m.key)
    system_of = _system_partition(store, novel_id, gold)
    system_clusters: dict[str, set[MentionKey]] = defaultdict(set)
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


# ---------------------------------------------------------------------------
# Standard coreference metrics: MUC, B-cubed, CEAF-e, CoNLL F1
#
# `score_b3` above is this project's own variant and stays as it is: it reports
# against the resolver's real behaviour, where declining to link is a first-class
# outcome (non-negotiable #9, precision over recall), so it penalises an
# unresolved mention in the recall denominator and excludes it from precision.
# That asymmetry is deliberate and documented, and it makes the number
# incomparable to anything in the literature.
#
# The functions below are the textbook definitions instead, so a number computed
# here can sit beside BookNLP, LitBank and LINK-KG results without an asterisk.
# They differ from `score_b3` in exactly one modelling choice: a gold mention the
# system never linked becomes a **singleton system cluster**, which is what every
# published scorer does. Both views are worth having; silently blending them is
# not, which is why they are separate functions rather than a flag.
#
# These are pure partition math -- no Store, no database, no offsets. That is the
# point: `score_b3` had no test coverage for four months because exercising it
# required building a novel first, and a scoring bug invalidates every number
# downstream of it.
# ---------------------------------------------------------------------------

#: Re-exported under the scorer's short local name; the definition lives in
#: `eval/gold.py` so the key shape cannot drift between the two modules.
Key = MentionKey


@dataclass(frozen=True, slots=True)
class MetricScore:
    name: str
    precision: float
    recall: float
    #: The CoNLL figure is an average of three F1s and has no precision or
    #: recall of its own. Printing invented ones would invite someone to quote
    #: "CoNLL precision", which is not a quantity.
    f1_only: bool = False

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0

    def summary(self) -> str:
        if self.f1_only:
            return f"{self.name:<8} F1={self.f1:6.1%}  (mean of MUC/B3/CEAFe F1)"
        return (
            f"{self.name:<8} P={self.precision:6.1%}  R={self.recall:6.1%}  "
            f"F1={self.f1:6.1%}"
        )


def _grouped(partition: dict[Key, str]) -> list[set[Key]]:
    """Cluster-id -> member set, as a list of sets. Order is deterministic."""
    buckets: dict[str, set[Key]] = defaultdict(set)
    for key, cluster_id in partition.items():
        buckets[cluster_id].add(key)
    return [buckets[cid] for cid in sorted(buckets)]


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def muc(gold: dict[Key, str], system: dict[Key, str]) -> MetricScore:
    """Vilain et al. (1995) link-based F1.

    Counts the minimum number of merges needed to turn one partition into the
    other. It is reported because it is conventional, not because it is
    informative here: MUC is blind to singletons, so a system that correctly
    isolates a one-scene walk-on gets no credit for it. On a cast with a long
    tail of single-mention characters -- which is every chapter of this corpus --
    that is most of the decisions. Read it next to B-cubed, never alone.
    """

    def _side(a: list[set[Key]], b_of: dict[Key, str]) -> tuple[float, float]:
        num = den = 0.0
        for cluster in a:
            if len(cluster) < 2:
                continue  # contributes 0/0; MUC simply cannot see singletons
            partitions = len({b_of.get(k, f"__unlinked__{k}") for k in cluster})
            num += len(cluster) - partitions
            den += len(cluster) - 1
        return num, den

    r_num, r_den = _side(_grouped(gold), system)
    p_num, p_den = _side(_grouped(system), gold)
    return MetricScore("MUC", _ratio(p_num, p_den), _ratio(r_num, r_den))


def b_cubed(gold: dict[Key, str], system: dict[Key, str]) -> MetricScore:
    """Bagga & Baldwin (1998), the standard per-mention formulation.

    Unlike `score_b3`, both precision and recall average over the same mention
    set, and an unlinked mention is its own singleton rather than a special case.
    """
    gold_of = _index(gold)
    sys_of = _index(system)
    keys = sorted(set(gold) | set(system))
    precisions: list[float] = []
    recalls: list[float] = []
    for key in keys:
        g = gold_of.get(key, {key})
        s = sys_of.get(key, {key})
        overlap = len(g & s)
        precisions.append(_ratio(overlap, len(s)))
        recalls.append(_ratio(overlap, len(g)))
    n = len(keys)
    return MetricScore("B3", _ratio(sum(precisions), n), _ratio(sum(recalls), n))


def _index(partition: dict[Key, str]) -> dict[Key, set[Key]]:
    buckets: dict[str, set[Key]] = defaultdict(set)
    for key, cluster_id in partition.items():
        buckets[cluster_id].add(key)
    return {key: buckets[cid] for key, cid in partition.items()}


def ceafe(gold: dict[Key, str], system: dict[Key, str]) -> MetricScore:
    """Luo (2005) entity-based CEAF, φ₄ similarity.

    Each gold entity is aligned to at most one system entity, which is the one
    property MUC and B-cubed lack: it charges for inventing an entity and for
    dropping one, rather than scoring every mention independently. That matters
    for this project specifically, where the documented failure mode is
    over-splitting one character into several selves.
    """
    gold_clusters = _grouped(gold)
    sys_clusters = _grouped(system)
    if not gold_clusters or not sys_clusters:
        return MetricScore("CEAFe", 0.0, 0.0)
    weights = [
        [_ratio(2 * len(g & s), len(g) + len(s)) for s in sys_clusters]
        for g in gold_clusters
    ]
    total = _max_weight_matching(weights)
    return MetricScore("CEAFe", _ratio(total, len(sys_clusters)), _ratio(total, len(gold_clusters)))


def conll_f1(*scores: MetricScore) -> float:
    """The unweighted mean of MUC, B-cubed and CEAF-e F1 -- the CoNLL-2012 headline."""
    return sum(s.f1 for s in scores) / len(scores) if scores else 0.0


def _max_weight_matching(weights: list[list[float]]) -> float:
    """Maximum-weight one-to-one assignment (Jonker-Volgenant, O(n^3)).

    Written out rather than taken from `scipy.optimize.linear_sum_assignment`
    because scipy is not a declared dependency of this package -- it arrives
    transitively via the optional `ml`/`render` extras. A metric whose value
    depends on which optional extras happen to be installed is not a metric.
    """
    rows, cols = len(weights), len(weights[0]) if weights else 0
    if not rows or not cols:
        return 0.0
    size = max(rows, cols)
    inf = float("inf")
    # Minimise negated weight; pad to square with zero-cost dummy cells.
    cost = [[0.0] * size for _ in range(size)]
    for i in range(rows):
        for j in range(cols):
            cost[i][j] = -weights[i][j]

    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    match = [0] * (size + 1)  # column -> row
    way = [0] * (size + 1)
    for i in range(1, size + 1):
        match[0] = i
        j0 = 0
        minv = [inf] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = match[j0], inf, 0
            for j in range(1, size + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j], way[j] = cur, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(size + 1):
                if used[j]:
                    u[match[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if match[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            match[j0] = match[j1]
            j0 = j1

    total = 0.0
    for j in range(1, size + 1):
        i = match[j]
        if 1 <= i <= rows and 1 <= j <= cols:
            total += weights[i - 1][j - 1]
    return total


def score_all(store: Store, novel_id: str, gold: GoldSet) -> list[MetricScore]:
    """MUC, B-cubed and CEAF-e over one gold set, plus the CoNLL average.

    Uses the same offset-translated mention matching as `score_b3`, so the two
    disagree only where their definitions disagree, never because they looked at
    different mentions.
    """
    system_of = _system_partition(store, novel_id, gold)
    gold_partition: dict[Key, str] = {m.key: m.identity for m in gold.mentions if m.identity}
    system_partition: dict[Key, str] = {
        key: target_id
        for key, target_id in system_of.items()
        if target_id and key in gold_partition
    }
    scores = [
        muc(gold_partition, system_partition),
        b_cubed(gold_partition, system_partition),
        ceafe(gold_partition, system_partition),
    ]
    average = conll_f1(*scores)
    return [*scores, MetricScore("CoNLL", average, average, f1_only=True)]
