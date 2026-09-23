"""Confidence intervals and paired significance, by bootstrap resampling.

COMPLETION_PLAN Track 2 item 10. Every number this project has ever reported
was a point estimate with no interval, which is how a 52-point disagreement
between MUC/B3 and CEAF-e (EVOLUTION 4.75) and an 81%->93% compounding rise
(4.77) both arrive looking equally solid. One of those is a structural fact
about 6,238 mentions; the other is a difference between windows of 145 and 166
links. Only an interval distinguishes them.

**Example-level, and paired where a comparison is being made.** Resampling
*mentions* rather than *chapters* slightly understates variance, because
mentions within a chapter are not independent -- but the alternative on this
corpus is a bootstrap over 40-199 units, which is worse. Stated here rather
than left implicit, since it is the kind of choice a reviewer asks about.

Paired resampling (the same resampled indices scored under both systems) is
used for A-vs-B because the two share the same hard examples: an unpaired
comparison of two systems on one corpus mostly measures how hard the corpus
is, and its interval is far too wide to show a real difference.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: Enough for a stable 95% interval on the sample sizes here (thousands of
#: mentions) without making `eval` noticeably slower.
DEFAULT_RESAMPLES = 2_000

DEFAULT_SEED = 20260923


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with a percentile bootstrap interval."""

    point: float
    low: float
    high: float
    resamples: int
    confidence: float = 0.95

    def summary(self, *, percent: bool = True) -> str:
        if percent:
            return f"{self.point:.1%} [{self.low:.1%}, {self.high:.1%}]"
        return f"{self.point:.4f} [{self.low:.4f}, {self.high:.4f}]"


@dataclass(frozen=True, slots=True)
class PairedComparison:
    """A-vs-B on the same resampled examples."""

    delta: float
    low: float
    high: float
    #: Share of resamples where B did not beat A. This is a bootstrap p-value
    #: and is reported as such -- it is not a t-test and must not be described
    #: as one.
    p_value: float
    resamples: int

    @property
    def significant(self) -> bool:
        """The interval excludes zero. Not a claim about practical size."""
        return (self.low > 0.0) or (self.high < 0.0)

    def summary(self) -> str:
        verdict = "excludes 0" if self.significant else "includes 0 (not distinguishable)"
        return (
            f"delta={self.delta:+.1%} [{self.low:+.1%}, {self.high:+.1%}] "
            f"p={self.p_value:.3f} -- {verdict}"
        )


def bootstrap_ci(
    examples: Sequence[object],
    statistic: Callable[[Sequence[object]], float],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    confidence: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Percentile bootstrap interval for any statistic over examples."""
    point = statistic(examples)
    n = len(examples)
    if n < 2:
        # One example has no sampling distribution. Returned as a degenerate
        # interval rather than a fabricated one -- a [x, x] interval reads
        # honestly as "no spread estimable", where a normal-approximation
        # interval here would be invented.
        return Interval(point, point, point, 0, confidence)

    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(resamples):
        sample = [examples[rng.randrange(n)] for _ in range(n)]
        draws.append(statistic(sample))
    draws.sort()
    tail = (1.0 - confidence) / 2.0
    low = draws[min(len(draws) - 1, int(tail * len(draws)))]
    high = draws[min(len(draws) - 1, int((1.0 - tail) * len(draws)))]
    return Interval(point, low, high, resamples, confidence)


def paired_bootstrap(
    examples: Sequence[object],
    statistic_a: Callable[[Sequence[object]], float],
    statistic_b: Callable[[Sequence[object]], float],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    confidence: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> PairedComparison:
    """Is B better than A, on the same resampled examples?

    `p_value` is the share of resamples in which B did *not* improve on A. It
    is a bootstrap p-value: a statement about this resampling procedure on
    this corpus, not a frequentist test with distributional assumptions, and
    it must be reported in those words.
    """
    point = statistic_b(examples) - statistic_a(examples)
    n = len(examples)
    if n < 2:
        return PairedComparison(point, point, point, 1.0, 0)

    rng = random.Random(seed)
    deltas: list[float] = []
    not_better = 0
    for _ in range(resamples):
        sample = [examples[rng.randrange(n)] for _ in range(n)]
        delta = statistic_b(sample) - statistic_a(sample)
        deltas.append(delta)
        if delta <= 0.0:
            not_better += 1
    deltas.sort()
    tail = (1.0 - confidence) / 2.0
    low = deltas[min(len(deltas) - 1, int(tail * len(deltas)))]
    high = deltas[min(len(deltas) - 1, int((1.0 - tail) * len(deltas)))]
    return PairedComparison(point, low, high, not_better / resamples, resamples)


def rate(hits: Sequence[bool]) -> float:
    """The commonest statistic here: a share of boolean outcomes."""
    return sum(1 for h in hits if h) / len(hits) if hits else 0.0
