"""Statistics for the arena: re-exports the pipeline's bootstrap and adds the
few tests experiments here need that it lacks.

The pipeline's `eval/stats.py` already carries the project's stated choices
(example-level percentile bootstrap, paired resampling for A-vs-B, bootstrap
p-values described as such); reusing it rather than re-deriving keeps one
convention across product eval and research.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

import numpy as np
from scipy import optimize

from echotales.pipeline.eval.stats import (  # noqa: F401  (re-exported)
    Interval,
    PairedComparison,
    bootstrap_ci,
    paired_bootstrap,
    rate,
)


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score interval: honest at small n and at 0 or n successes, where
    the normal approximation collapses to a zero-width interval."""
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def permutation_test(
    a: Sequence[float], b: Sequence[float], *, resamples: int = 5000, seed: int = 20261002
) -> float:
    """Two-sided permutation p-value for a difference in means (unpaired)."""
    a, b = list(a), list(b)
    observed = abs(np.mean(b) - np.mean(a)) if a and b else 0.0
    pooled = a + b
    rng = random.Random(seed)
    hits = 0
    for _ in range(resamples):
        rng.shuffle(pooled)
        pa, pb = pooled[: len(a)], pooled[len(a):]
        if abs(np.mean(pb) - np.mean(pa)) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (resamples + 1)


def expected_calibration_error(
    confidences: Sequence[float], correct: Sequence[bool], *, bins: int = 10
) -> tuple[float, list[dict[str, float]]]:
    """ECE with equal-width bins, plus the reliability table it came from.

    The table is returned because ECE alone hides *where* miscalibration is;
    for a tiered system (a handful of constant confidences) the per-bin rows
    are effectively per-tier accuracy, which is the actual finding.
    """
    conf = np.asarray(confidences, dtype=float)
    hit = np.asarray(correct, dtype=float)
    n = len(conf)
    table: list[dict[str, float]] = []
    ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf >= lo) & ((conf < hi) if i < bins - 1 else (conf <= hi))
        k = int(mask.sum())
        if k == 0:
            continue
        acc, mean_conf = float(hit[mask].mean()), float(conf[mask].mean())
        ece += (k / n) * abs(acc - mean_conf)
        table.append({"lo": float(lo), "hi": float(hi), "n": k,
                      "accuracy": acc, "mean_confidence": mean_conf})
    return float(ece), table


def bradley_terry(
    items: Sequence[str], wins: Sequence[tuple[str, str]], *, l2: float = 1e-3
) -> dict[str, float]:
    """Bradley-Terry strengths (log-scale, mean-centred) from (winner, loser)
    pairs, by penalised maximum likelihood. Small L2 keeps a never-losing item
    finite rather than diverging -- common in small pilot studies."""
    idx = {it: i for i, it in enumerate(items)}
    w = np.array([idx[x] for x, _ in wins])
    lo = np.array([idx[y] for _, y in wins])

    def nll(theta: np.ndarray) -> float:
        diff = theta[w] - theta[lo]
        return float(np.sum(np.logaddexp(0.0, -diff)) + l2 * np.sum(theta**2))

    res = optimize.minimize(nll, np.zeros(len(items)), method="L-BFGS-B")
    theta = res.x - res.x.mean()
    return {it: float(theta[idx[it]]) for it in items}
