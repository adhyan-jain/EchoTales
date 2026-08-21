"""Log-linear scoring over the evidence vector (plans.md Section 6 Phase 6, step 3; Section 7).

A linear model on interpretable features, not a black box. Two reasons that
matters here beyond taste:

- Every decision can be explained by naming which feature carried it, which is
  what makes the resolution event log auditable at chapter 190 for a link made
  at chapter 40.
- The ablations plans.md requires (no temporal scoping, no alias typing, no
  self/persona split) are implemented by zeroing named weights, rather than by
  retraining a different model each time.

Weights are hand-initialised from the priors in plans.md and then fitted by
logistic regression on gold. Hand-initialisation is not a placeholder: it makes
the system work sensibly on a novel with no annotations yet, which is the
normal state when a new source is added.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from echotales.core.models import SCORED_FEATURES, Candidate, EvidenceVector

#: Hand-initialised weights over the five *scored* features.
#:
#: `surface_similarity` is weighted far lower than it first deserves, because
#: Jaro-Winkler between genuinely unrelated short names is routinely 0.6-0.7
#: in this corpus (measured: Klein/Leonard 0.676, Audrey/Alger 0.630). Treating
#: it as strong evidence linked half the cast together. It is now a weak
#: signal that must be corroborated by context or speech partners.
#:
#: `first_attested_soft_prior` stays small so a late reveal can override it
#: (plans.md Section 4.4).
DEFAULT_WEIGHTS: dict[str, float] = {
    "surface_similarity": 1.2,
    "context_embedding_similarity": 2.0,
    "speech_partner_compatibility": 1.5,
    "temporal_validity": 1.0,
    "first_attested_soft_prior": 0.4,
}

#: Strongly negative so that an uncorroborated pair sits well below the LINK
#: threshold. The previous -2.0 left unrelated candidates at p≈0.77, one weak
#: feature away from an automatic link.
#:
#: **Do not "fix" this to reach the LINK threshold without calibrating first.**
#: An orphaned edit to -2.5 (rationale: "-4.0 made it impossible for even a
#: maximal evidence vector to cross 0.80") was measured on RI vol 1 and cost
#: 23 entities to false merges -- `Chi Shan` into `Bai Ning Bing`, `Ren Zu`
#: into the `Gu Yue` clan, `Qing Shu` into `Dong Tu`, all method=SCORED. The
#: premise was right and the conclusion wrong: the scorer genuinely cannot
#: reach 0.80 (Section 4.1), but the answer is `ConformalGate.calibrate()` against
#: confirmed gold, not hand-moving one end of an uncalibrated pair until
#: links appear. Moving it lets the scorer link on *weak* evidence, which is
#: exactly what Section 4.1 says the pre-filters exist to avoid.
DEFAULT_BIAS = -4.0

#: Surface similarity below this contributes nothing. Short romanised names
#: collide by chance far too often for the raw score to be usable at the low
#: end, and the model has no way to tell chance collision from real evidence.
SURFACE_SIMILARITY_FLOOR = 0.80

#: `normalize.name_containment` returns >= 0.80 only when one name is the other
#: with a leading house prefix removed, and only when the shared tail is two or
#: more tokens. That is categorical rather than gradual — it is the same
#: personal name — so it belongs with the pre-filters and not in the scorer.
#:
#: It has to be a pre-filter to have any effect at all: measured on this
#: corpus, the scorer's most confident possible output is p=0.71 against a 0.80
#: link threshold (see `gate.FALLBACK_LINK_THRESHOLD`), so *no* combination of
#: weighted features can produce a link. Every link the system makes today
#: comes through this function.
#:
#: Set just below 0.875, the value the 2-of-4-token case produces.
NAME_CONTAINMENT_FLOOR = 0.86


class PrefilterVerdict(StrEnum):
    """Outcome of the hard pre-filter stage, which runs before scoring."""

    #: An explicit identity assertion or a confirmed exact alias. Link now.
    FORCE_LINK = "FORCE_LINK"
    #: Simultaneously present and distinct, or temporally impossible. Never link.
    BLOCK = "BLOCK"
    #: No hard evidence either way; fall through to the scorer.
    SCORE = "SCORE"


@dataclass(frozen=True, slots=True)
class PrefilterResult:
    verdict: PrefilterVerdict
    reason: str = ""
    confidence: float = 1.0


def prefilter(evidence: EvidenceVector) -> PrefilterResult:
    """Decide the cases that do not need a model, before scoring.

    Three signals are categorical rather than gradual, and treating them as
    weighted features was actively harmful:

    **`declaration_match`** -- "his true name was X" is not evidence *for* a
    link, it *is* the link. Near-perfect precision, so it short-circuits.

    **`gazetteer_exact_match`** -- a confirmed alias matched exactly. As a
    weighted feature at 2.5 this drove probability to 0.96 unaided, and since
    every link grows the entity's alias set, each wrong link made the next
    easier. Runaway self-reinforcement. As a pre-filter it still links
    immediately, but it can be gated on *confirmed* aliases rather than on
    everything an entity has absorbed.

    **`co_presence_violation`** -- two mentions simultaneously present doing
    different things cannot be one persona. A near-certain negative; letting
    five positive features outvote it discards that certainty.

    Blockers are checked first: a hard negative must beat a hard positive,
    because a co-present pair that also matches a declaration is far more
    likely to be a detector error than a genuine identity.
    """
    if evidence.co_presence_violation >= 1.0:
        return PrefilterResult(
            PrefilterVerdict.BLOCK,
            "co-present and distinct: cannot be one persona",
        )
    if evidence.temporal_validity <= 0.0:
        return PrefilterResult(
            PrefilterVerdict.BLOCK,
            "candidate's binding is not temporally valid here",
        )
    if evidence.declaration_match >= 1.0:
        return PrefilterResult(
            PrefilterVerdict.FORCE_LINK,
            "explicit identity declaration in context",
            confidence=0.98,
        )
    if evidence.gazetteer_exact_match >= 1.0:
        return PrefilterResult(
            PrefilterVerdict.FORCE_LINK,
            "exact match on a confirmed alias",
            confidence=0.95,
        )
    if evidence.name_containment >= NAME_CONTAINMENT_FLOOR:
        return PrefilterResult(
            PrefilterVerdict.FORCE_LINK,
            "name contained as a suffix: same personal name, house prefix dropped",
            confidence=0.90,
        )
    return PrefilterResult(PrefilterVerdict.SCORE)


@dataclass(slots=True)
class ScoringModel:
    """Log-linear model over the fixed feature order."""

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    bias: float = DEFAULT_BIAS
    #: Platt scaling parameters, fitted on held-out gold to turn the raw score
    #: into a usable probability rather than a monotone-but-uncalibrated one.
    platt_a: float = 1.0
    platt_b: float = 0.0

    def raw_score(self, evidence: EvidenceVector) -> float:
        """Score over the five dense features only.

        The pre-filter features (`declaration_match`, `gazetteer_exact_match`)
        and the hard blocker (`co_presence_violation`) are deliberately absent:
        they are handled by `prefilter()` before scoring is reached.
        """
        total = self.bias
        for name in SCORED_FEATURES:
            value = getattr(evidence, name, 0.0)
            if name == "surface_similarity" and value < SURFACE_SIMILARITY_FLOOR:
                # Chance collision between short romanised names, not evidence.
                continue
            total += self.weights.get(name, 0.0) * value
        return total

    def probability(self, evidence: EvidenceVector) -> float:
        """Calibrated probability that the mention denotes the candidate."""
        z = self.platt_a * self.raw_score(evidence) + self.platt_b
        return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))

    def explain(self, evidence: EvidenceVector) -> list[tuple[str, float]]:
        """Per-feature contributions, largest magnitude first.

        This is what makes a decision auditable: "linked because
        context similarity contributed +1.4" is a reviewable claim in a way
        that a bare 0.93 is not.
        """
        contributions = [
            (name, self.weights.get(name, 0.0) * getattr(evidence, name, 0.0))
            for name in SCORED_FEATURES
        ]
        contributions.sort(key=lambda kv: abs(kv[1]), reverse=True)
        return contributions

    def score_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        """Score and sort candidates in place-ish (returns a sorted copy)."""
        for candidate in candidates:
            candidate.score = self.raw_score(candidate.evidence)
            candidate.probability = self.probability(candidate.evidence)
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    # ---- ablations ---------------------------------------------------

    def ablate(self, *feature_names: str) -> ScoringModel:
        """Return a copy with the named features zeroed.

        The mechanism behind the Section 8 ablation table: "no temporal scoping" is
        `ablate("temporal_validity")`, not a separately trained model.
        """
        weights = dict(self.weights)
        for name in feature_names:
            weights[name] = 0.0
        return ScoringModel(
            weights=weights, bias=self.bias, platt_a=self.platt_a, platt_b=self.platt_b
        )

    # ---- fitting ------------------------------------------------------

    def fit(
        self,
        examples: list[tuple[EvidenceVector, bool]],
        *,
        epochs: int = 200,
        learning_rate: float = 0.1,
        l2: float = 0.01,
    ) -> ScoringModel:
        """Fit by gradient descent on logistic loss.

        Written out rather than delegated to scikit-learn so that fitting works
        without the optional `ml` extra, and so the hand-initialised weights are
        the starting point rather than being discarded.
        """
        if not examples:
            return self

        for _ in range(epochs):
            grad = dict.fromkeys(SCORED_FEATURES, 0.0)
            grad_bias = 0.0
            for evidence, label in examples:
                predicted = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, self.raw_score(evidence)))))
                error = predicted - (1.0 if label else 0.0)
                for name in SCORED_FEATURES:
                    grad[name] += error * getattr(evidence, name, 0.0)
                grad_bias += error

            n = len(examples)
            for name in SCORED_FEATURES:
                self.weights[name] -= learning_rate * (
                    grad[name] / n + l2 * self.weights[name]
                )
            self.bias -= learning_rate * grad_bias / n

        return self

    def calibrate(self, examples: list[tuple[EvidenceVector, bool]]) -> ScoringModel:
        """Fit Platt scaling on held-out examples.

        A monotone score is enough to rank, but the conformal gate needs the
        numbers to mean something -- an uncalibrated 0.9 and a calibrated 0.9
        support very different decisions.
        """
        if not examples:
            return self
        scores = [self.raw_score(e) for e, _ in examples]
        labels = [1.0 if label else 0.0 for _, label in examples]

        a, b = 1.0, 0.0
        for _ in range(200):
            ga = gb = 0.0
            for score, label in zip(scores, labels, strict=True):
                z = a * score + b
                p = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))
                ga += (p - label) * score
                gb += p - label
            n = len(scores)
            a -= 0.05 * ga / n
            b -= 0.05 * gb / n

        self.platt_a, self.platt_b = a, b
        return self

    # ---- persistence ----------------------------------------------------

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {
                    "weights": self.weights,
                    "bias": self.bias,
                    "platt_a": self.platt_a,
                    "platt_b": self.platt_b,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> ScoringModel:
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            weights={**DEFAULT_WEIGHTS, **data.get("weights", {})},
            bias=data.get("bias", DEFAULT_BIAS),
            platt_a=data.get("platt_a", 1.0),
            platt_b=data.get("platt_b", 0.0),
        )
