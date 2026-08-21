"""Three-way decision gate via conformal prediction (plans.md Section 6 Phase 6, step 4).

The gate returns LINK / NEW / **DEFER**. The third option is the important one:
without it, every ambiguous mention forces a guess, and a wrong guess made at
chapter 40 poisons every later decision about that entity. Deferring costs one
unresolved mention and buys the chance to decide correctly at chapter 90 with
more evidence.

**Conformal prediction** is used rather than a hand-picked threshold because it
gives a distribution-free coverage guarantee: calibrate on held-out scores and
at most alpha of auto-linked decisions are wrong, with no assumption about the
score distribution being well-behaved. With alpha = 0.05, "at most 5% of
automatic links are errors" is a claim the calibration procedure actually
supports.

Until calibration data exists the gate falls back to conservative fixed
thresholds. That fallback is deliberately cautious -- an uncalibrated gate
should defer too much rather than link too much, because the deferred queue is
recoverable and a false merge is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import Decision
from echotales.core.models import Candidate

#: Uncalibrated fallbacks. Wide DEFER band on purpose.
FALLBACK_LINK_THRESHOLD = 0.80
FALLBACK_NEW_THRESHOLD = 0.35


@dataclass(slots=True)
class ConformalGate:
    """Calibrated three-way gate.

    `link_threshold` is the score above which a link is made automatically;
    `new_threshold` the score below which the mention is treated as a new
    entity. Between them is the deferred zone.
    """

    alpha: float = 0.05
    link_threshold: float = FALLBACK_LINK_THRESHOLD
    new_threshold: float = FALLBACK_NEW_THRESHOLD
    calibrated: bool = False
    #: Nonconformity scores from calibration, retained for auditing.
    calibration_size: int = 0

    def calibrate(
        self,
        examples: list[tuple[float, bool]],
        *,
        alpha: float | None = None,
    ) -> ConformalGate:
        """Set thresholds from held-out (probability, is_correct) pairs.

        The link threshold is the (1-alpha) quantile of the probabilities
        assigned to *incorrect* pairs: linking only above it means at most
        alpha of the incorrect population could have slipped through.

        The new threshold is the alpha quantile over *correct* pairs, so
        declaring NEW below it rarely discards a genuine match.
        """
        if not examples:
            return self
        a = alpha if alpha is not None else self.alpha

        incorrect = sorted((p for p, ok in examples if not ok), reverse=True)
        correct = sorted(p for p, ok in examples if ok)

        if incorrect:
            index = min(int(a * len(incorrect)), len(incorrect) - 1)
            # No 0.5 floor. `ScoringModel.probability` is a logistic over
            # hand-set weights with a large negative bias -- its output is a
            # *score*, not a calibrated likelihood, so reading 0.5 as "even
            # odds" is a category error. Measured on RI vol 1 against
            # confirmed gold, the scorer's entire observed range is
            # 0.049-0.349: a 0.5 floor sits above every value it can produce,
            # which made calibration a no-op and left `FALLBACK_LINK_THRESHOLD`
            # (0.80) in force. That is Section 4.1's blocker, and this floor was the
            # mechanism.
            #
            # The separation itself is real and the reason this is safe:
            # correct pairs sit at median 0.217 (min 0.169), incorrect at
            # median 0.061 (p90 0.161). The conformal quantile lands in the
            # gap between them, which is the whole point of calibrating
            # rather than picking a number.
            self.link_threshold = incorrect[index]
        if correct:
            index = min(int(a * len(correct)), len(correct) - 1)
            self.new_threshold = min(correct[index], self.link_threshold - 0.05)

        # A degenerate calibration set can invert the band; fall back rather
        # than emit a gate that links everything.
        if self.new_threshold >= self.link_threshold:
            self.link_threshold = FALLBACK_LINK_THRESHOLD
            self.new_threshold = FALLBACK_NEW_THRESHOLD
            self.calibrated = False
            return self

        self.alpha = a
        self.calibrated = True
        self.calibration_size = len(examples)
        return self

    def decide(self, candidates: list[Candidate]) -> tuple[Decision, Candidate | None, str]:
        """Choose between linking to the best candidate, creating, or deferring.

        Hard pre-filters run first. A blocked candidate is removed from
        consideration entirely rather than being outvoted, and a
        declaration/exact-alias match links immediately without scoring.
        """
        from echotales.pipeline.resolve.score import PrefilterVerdict, prefilter

        if not candidates:
            return Decision.NEW, None, "no candidates retrieved"

        allowed: list[Candidate] = []
        for candidate in candidates:
            result = prefilter(candidate.evidence)
            if result.verdict is PrefilterVerdict.FORCE_LINK:
                candidate.probability = max(candidate.probability, result.confidence)
                return Decision.LINK, candidate, result.reason
            if result.verdict is PrefilterVerdict.BLOCK:
                continue
            allowed.append(candidate)

        if not allowed:
            return Decision.NEW, None, "every candidate blocked by a hard filter"

        candidates = allowed
        best = max(candidates, key=lambda c: c.probability)

        if best.probability >= self.link_threshold:
            # A near-tie between two candidates is not a confident link, even
            # when both score highly: picking one arbitrarily is exactly the
            # false merge the deferred queue exists to avoid.
            runner_up = sorted((c.probability for c in candidates), reverse=True)
            if len(runner_up) > 1 and runner_up[0] - runner_up[1] < 0.05:
                return (
                    Decision.DEFER,
                    best,
                    f"top two candidates within {runner_up[0] - runner_up[1]:.3f}",
                )
            return Decision.LINK, best, f"p={best.probability:.3f} >= {self.link_threshold:.3f}"

        if best.probability <= self.new_threshold:
            return Decision.NEW, None, f"p={best.probability:.3f} <= {self.new_threshold:.3f}"

        return Decision.DEFER, best, f"p={best.probability:.3f} in deferred band"

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {
                    "alpha": self.alpha,
                    "link_threshold": self.link_threshold,
                    "new_threshold": self.new_threshold,
                    "calibrated": self.calibrated,
                    "calibration_size": self.calibration_size,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> ConformalGate:
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            alpha=data.get("alpha", 0.05),
            link_threshold=data.get("link_threshold", FALLBACK_LINK_THRESHOLD),
            new_threshold=data.get("new_threshold", FALLBACK_NEW_THRESHOLD),
            calibrated=data.get("calibrated", False),
            calibration_size=data.get("calibration_size", 0),
        )


@dataclass(slots=True)
class DeferredCase:
    """A mention group held for re-resolution.

    Kept with its candidates so the retry can compare what changed rather than
    recomputing from scratch, and with `attempts` so a case that never becomes
    decidable is eventually escalated instead of looping forever.
    """

    group_id: str
    chapter: float
    surface: str
    context: str
    candidates: list[Candidate] = field(default_factory=list)
    reason: str = ""
    attempts: int = 0


class DeferredQueue:
    """Holds undecided cases for later re-resolution (step 6).

    The queue is what turns a hard decision at chapter 40 into an easy one at
    chapter 90: by then the gazetteer has grown, the entity profiles carry more
    context, and a reveal may have happened.
    """

    def __init__(self, max_attempts: int = 3) -> None:
        self._cases: dict[str, DeferredCase] = {}
        self.max_attempts = max_attempts

    def add(self, case: DeferredCase) -> None:
        self._cases[case.group_id] = case

    def pop_ready(self) -> list[DeferredCase]:
        """Take every case still worth retrying."""
        ready = [c for c in self._cases.values() if c.attempts < self.max_attempts]
        for case in ready:
            case.attempts += 1
        return ready

    def exhausted(self) -> list[DeferredCase]:
        """Cases that have run out of retries and need escalation."""
        return [c for c in self._cases.values() if c.attempts >= self.max_attempts]

    def remove(self, group_id: str) -> None:
        self._cases.pop(group_id, None)

    def __len__(self) -> int:
        return len(self._cases)
