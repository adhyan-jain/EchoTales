"""Ablation harness: re-score cached evidence under one condition at a time.

`plans.md` and `details.md` have claimed since the design phase that ablations
"cost no additional LLM passes because they re-score cached evidence vectors."
That is now true (`eval/evidence_cache.py`, EVOLUTION 4.78); it was not before,
because no cache existed.

**What an ablation here can and cannot say.** Re-scoring the cache answers
"how would the *decision* have differed under this condition, given the same
evidence". It cannot answer questions where the condition changes what
evidence exists at all -- notably "no gazetteer compounding" in the
*detection* sense, since a gazetteer that never grew would have produced
different mentions, not merely different links. Those conditions need a real
re-resolve and are reported as such rather than faked from the cache. Saying
this in the module rather than in a paper footnote is the point: the
difference between the two is exactly where an ablation result stops being
honest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.enums import ResolutionMethod
from echotales.core.models import EvidenceVector
from echotales.core.store import Store
from echotales.pipeline.resolve.score import (
    PREFILTER_GATES,
    PrefilterVerdict,
    ScoringModel,
    prefilter,
)

#: Conditions this harness can express from the cache alone. Each maps to the
#: pre-filter gates it switches off; an empty tuple is the control.
CONDITIONS: dict[str, tuple[str, ...]] = {
    "full": (),
    "no-gazetteer-compounding": ("gazetteer_exact_match",),
    "no-declaration": ("declaration_match",),
    "no-name-containment": ("name_containment",),
    "no-relational-copresence": ("relationship_deictic_resolution",),
    "no-temporal-scoping": ("temporal_validity",),
    "no-copresence-blocking": ("co_presence_violation",),
    "no-prefilters-at-all": PREFILTER_GATES,
}

#: Conditions a reader might expect that this harness deliberately does NOT
#: offer, with the reason. Listed in code so the gap is visible at the call
#: site rather than discovered when a number looks surprising.
REQUIRES_RERESOLVE: dict[str, str] = {
    "no-alias-typing": (
        "alias_type is assigned in the mentions stage, upstream of any evidence"
        " vector -- the cache has no record of what the alternative would be"
    ),
    "no-self-persona-split": (
        "changes which entities exist, not how a pair scores"
    ),
    "no-truth-status": (
        "changes what state_of returns, which the resolver never consulted"
    ),
}


@dataclass(slots=True)
class AblationRow:
    condition: str
    pairs: int = 0
    force_links: int = 0
    blocks: int = 0
    scored: int = 0
    links_above_threshold: int = 0
    by_method: dict[str, int] = field(default_factory=dict)

    @property
    def force_link_share(self) -> float:
        return self.force_links / self.pairs if self.pairs else 0.0

    def summary(self) -> str:
        methods = ", ".join(f"{k}={v}" for k, v in sorted(self.by_method.items())) or "none"
        return (
            f"{self.condition:<26} pairs={self.pairs:>7,}  "
            f"force-link={self.force_links:>6,} ({self.force_link_share:.1%})  "
            f"blocked={self.blocks:>5,}  reached-scorer={self.scored:>7,}  "
            f"scorer-would-link={self.links_above_threshold:>6,}\n"
            f"{'':<26} methods: {methods}"
        )


def run_condition(
    vectors: list[EvidenceVector],
    *,
    condition: str,
    model: ScoringModel | None = None,
    link_threshold: float = 0.8,
) -> AblationRow:
    """Replay the pre-filter + scorer decision for one condition."""
    disabled = frozenset(CONDITIONS.get(condition, ()))
    scorer = model or ScoringModel()
    row = AblationRow(condition=condition)
    for vector in vectors:
        row.pairs += 1
        result = prefilter(vector, disabled_prefilters=disabled)
        if result.verdict is PrefilterVerdict.FORCE_LINK:
            row.force_links += 1
            key = result.method.value
            row.by_method[key] = row.by_method.get(key, 0) + 1
            continue
        if result.verdict is PrefilterVerdict.BLOCK:
            row.blocks += 1
            continue
        row.scored += 1
        if scorer.probability(vector) >= link_threshold:
            row.links_above_threshold += 1
            key = ResolutionMethod.SCORED.value
            row.by_method[key] = row.by_method.get(key, 0) + 1
    return row


def run_ablations(
    store: Store,
    novel_id: str,
    *,
    run_tag: str = "",
    conditions: list[str] | None = None,
    link_threshold: float = 0.8,
) -> list[AblationRow]:
    from echotales.pipeline.eval.evidence_cache import load_evidence

    cached = load_evidence(store, novel_id, run_tag=run_tag)
    vectors = [vector for *_rest, vector in cached]
    wanted = conditions or list(CONDITIONS)
    return [
        run_condition(vectors, condition=name, link_threshold=link_threshold)
        for name in wanted
        if name in CONDITIONS
    ]
