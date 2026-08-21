"""Retriever recall@k (plans.md Section 8.2).

**The scorer cannot exceed the retriever.** If the correct entity is not in the
top-k candidates, no amount of scoring quality recovers it — recall@10 of 60%
means a system ceiling of 60% regardless of everything downstream. So this is
built before scorer tuning, and it is a **decision gate**, not a diagnostic:

> If recall@10 on `TRANSFERABLE_TITLE` is below 80%, candidate retrieval is the
> research problem and the scorer is not worth tuning.

Two evaluation modes, because they answer different questions.

**`gold` mode** takes annotated mention→entity pairs and is the real
measurement. It is the only mode that can score the flagship case — two aliases
of one character used in different regions, sharing no surface form — because
only a human annotator knows they are the same person.

**`self_retrieval` mode** needs no annotations. For each entity, it asks whether
a mention of a surface form that entity is *already known by* retrieves that
entity. This is the **easy case by construction**, so it establishes a ceiling
rather than a score: whatever recall@k it reports, true recall on hard cases is
lower. Its value is catching catastrophic retrieval failure (indexing bugs,
tokenisation mismatches) before gold exists — a system that cannot retrieve an
entity by its own name is broken in a way no annotation is needed to see.

Never report self-retrieval numbers as recall@k results. They are a smoke test.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

from echotales.core.enums import AliasType
from echotales.pipeline.resolve.retrieve import CandidateRetriever

DEFAULT_KS: tuple[int, ...] = (1, 5, 10, 20)

#: The gate from plans.md Section 8.2.
GATE_ALIAS_TYPE = AliasType.TRANSFERABLE_TITLE
GATE_K = 10
GATE_THRESHOLD = 0.80


class EvalMode(StrEnum):
    GOLD = "gold"
    SELF_RETRIEVAL = "self_retrieval"


@dataclass(slots=True)
class RetrievalCase:
    """One mention whose correct entity is known."""

    surface: str
    context: str
    expected_target_id: str
    alias_type: AliasType = AliasType.RIGID_NAME
    chapter: float = 0.0


@dataclass(slots=True)
class RecallResult:
    mode: EvalMode
    total: int = 0
    #: k -> number of cases where the expected entity was in the top-k.
    hits_at_k: dict[int, int] = field(default_factory=dict)
    #: alias_type -> (k -> hits), and alias_type -> total.
    by_alias_type: dict[str, dict[int, int]] = field(default_factory=dict)
    by_alias_type_total: dict[str, int] = field(default_factory=dict)
    #: Cases where the entity was not retrieved at any k. The interesting ones.
    misses: list[RetrievalCase] = field(default_factory=list)

    def recall_at(self, k: int) -> float:
        return self.hits_at_k.get(k, 0) / self.total if self.total else 0.0

    def recall_at_by_type(self, alias_type: str, k: int) -> float:
        total = self.by_alias_type_total.get(alias_type, 0)
        if not total:
            return 0.0
        return self.by_alias_type.get(alias_type, {}).get(k, 0) / total

    @property
    def gate_passes(self) -> bool | None:
        """Whether recall@10 on transferable titles clears 80%.

        `None` when there are no cases of that type to judge — which is itself
        worth reporting, since it means the gate has not actually been tested.
        """
        total = self.by_alias_type_total.get(GATE_ALIAS_TYPE.value, 0)
        if not total:
            return None
        return self.recall_at_by_type(GATE_ALIAS_TYPE.value, GATE_K) >= GATE_THRESHOLD

    def summary(self, ks: tuple[int, ...] = DEFAULT_KS) -> str:
        if not self.total:
            return f"{self.mode.value}: no cases evaluated"

        lines = [f"retriever recall@k — mode={self.mode.value}, {self.total:,} cases"]
        overall = "  ".join(f"@{k}={self.recall_at(k):.1%}" for k in ks)
        lines.append(f"  overall:  {overall}")

        for alias_type in sorted(self.by_alias_type_total):
            n = self.by_alias_type_total[alias_type]
            per_k = "  ".join(
                f"@{k}={self.recall_at_by_type(alias_type, k):.1%}" for k in ks
            )
            lines.append(f"  {alias_type:20s} (n={n:5,d})  {per_k}")

        gate = self.gate_passes
        if gate is None:
            lines.append(
                f"  GATE: untested — no {GATE_ALIAS_TYPE.value} cases in this set"
            )
        else:
            verdict = "PASS" if gate else "FAIL"
            actual = self.recall_at_by_type(GATE_ALIAS_TYPE.value, GATE_K)
            lines.append(
                f"  GATE: {verdict} — recall@{GATE_K} on {GATE_ALIAS_TYPE.value} "
                f"= {actual:.1%} (threshold {GATE_THRESHOLD:.0%})"
            )
            if not gate:
                lines.append(
                    "        Candidate retrieval is the research problem. "
                    "Scorer tuning is premature."
                )

        if self.mode is EvalMode.SELF_RETRIEVAL:
            lines.append(
                "  NOTE: self-retrieval is the easy case by construction. "
                "These are a ceiling and a smoke test, not recall@k results."
            )
        return "\n".join(lines)


def evaluate_recall(
    retriever: CandidateRetriever,
    cases: list[RetrievalCase],
    *,
    ks: tuple[int, ...] = DEFAULT_KS,
    mode: EvalMode = EvalMode.GOLD,
    keep_misses: int = 50,
) -> RecallResult:
    """Measure recall@k over a set of cases."""
    result = RecallResult(mode=mode)
    max_k = max(ks)

    for case in cases:
        candidates = retriever.retrieve(case.surface, case.context, k=max_k)
        ranked = [c.target_id for c in candidates]

        try:
            rank = ranked.index(case.expected_target_id) + 1
        except ValueError:
            rank = None

        result.total += 1
        key = case.alias_type.value
        result.by_alias_type_total[key] = result.by_alias_type_total.get(key, 0) + 1
        result.by_alias_type.setdefault(key, {})

        for k in ks:
            result.hits_at_k.setdefault(k, 0)
            result.by_alias_type[key].setdefault(k, 0)
            if rank is not None and rank <= k:
                result.hits_at_k[k] += 1
                result.by_alias_type[key][k] += 1

        if rank is None and len(result.misses) < keep_misses:
            result.misses.append(case)

    return result


def build_self_retrieval_cases(
    retriever: CandidateRetriever,
    *,
    max_per_entity: int = 3,
    min_mentions: int = 2,
) -> list[RetrievalCase]:
    """Build a no-annotation smoke-test set from the retriever's own profiles.

    For each entity, take surface forms it is already known by and ask whether
    querying one retrieves that entity. Entities seen only once are skipped:
    with a single mention there is no independent context to query with, and
    the case degenerates into asking whether a string matches itself.

    Again: this is the **easy case**. It cannot fail in the way the flagship
    case fails, because it never asks the retriever to connect two surface
    forms that share nothing.
    """
    cases: list[RetrievalCase] = []
    for profile in retriever.profiles.values():
        if profile.mention_count < min_mentions:
            continue
        # Query context is the entity's own accumulated context terms, which
        # stands in for the neighbourhood a real mention would carry.
        context = " ".join(term for term, _ in profile.context_terms.most_common(40))
        for surface in sorted(profile.aliases, key=len, reverse=True)[:max_per_entity]:
            cases.append(
                RetrievalCase(
                    surface=surface,
                    context=context,
                    expected_target_id=profile.target_id,
                    alias_type=AliasType.RIGID_NAME,
                    chapter=profile.first_chapter,
                )
            )
    return cases


def load_gold_cases(path: str) -> list[RetrievalCase]:
    """Load annotated mention→entity pairs from JSONL.

    Expected fields per line: `surface`, `context`, `target_id`, and optionally
    `alias_type` and `chapter`. This is the format `tools/annotate.py` writes.
    """
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return []

    cases: list[RetrievalCase] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        cases.append(
            RetrievalCase(
                surface=row["surface"],
                context=row.get("context", ""),
                expected_target_id=row["target_id"],
                alias_type=AliasType(row.get("alias_type", AliasType.RIGID_NAME.value)),
                chapter=float(row.get("chapter", 0.0)),
            )
        )
    return cases


def miss_report(result: RecallResult, limit: int = 15) -> str:
    """The cases the retriever never surfaced.

    Worth reading directly rather than only in aggregate: a cluster of misses
    sharing an alias type or a surface shape usually names the actual defect.
    """
    if not result.misses:
        return "no misses"
    by_type: dict[str, list[str]] = defaultdict(list)
    for case in result.misses[:limit]:
        by_type[case.alias_type.value].append(case.surface)
    lines = [f"{len(result.misses)} miss(es), first {min(limit, len(result.misses))}:"]
    for alias_type, surfaces in sorted(by_type.items()):
        lines.append(f"  {alias_type}: {', '.join(repr(s) for s in surfaces)}")
    return "\n".join(lines)
