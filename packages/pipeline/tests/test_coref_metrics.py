"""Hand-computed checks on the coreference metrics.

`score_b3` shipped with zero test coverage and every number this project has
reported flowed through it. A scoring bug does not announce itself -- it just
produces a plausible number -- so each expectation below is worked out by hand
from the metric's definition in the comment above it, not captured from a run.
"""

import math

import pytest

from echotales.pipeline.eval.coref_score import (
    MetricScore,
    _max_weight_matching,
    b_cubed,
    ceafe,
    conll_f1,
    muc,
)


def part(**clusters: list[int]) -> dict[tuple[str, float, int], str]:
    """{"A": [1,2,3]} -> {key(1): "A", key(2): "A", ...}"""
    return {("n", 1.0, i): name for name, members in clusters.items() for i in members}


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)


# --- perfect and degenerate cases ------------------------------------------

def test_identical_partitions_score_one_everywhere():
    p = part(A=[1, 2, 3], B=[4, 5])
    for score in (muc(p, p), b_cubed(p, p), ceafe(p, p)):
        assert close(score.precision, 1.0) and close(score.recall, 1.0)
        assert close(score.f1, 1.0)
    assert close(conll_f1(muc(p, p), b_cubed(p, p), ceafe(p, p)), 1.0)


def test_empty_partitions_do_not_divide_by_zero():
    empty: dict[tuple[str, float, int], str] = {}
    assert ceafe(empty, empty).f1 == 0.0
    assert muc(empty, empty).f1 == 0.0
    assert b_cubed(empty, empty).f1 == 0.0


# --- over-merging: gold {1..5},{6,7} vs system one cluster of all 7 ---------

@pytest.fixture
def overmerged():
    return part(A=[1, 2, 3, 4, 5], B=[6, 7]), part(X=[1, 2, 3, 4, 5, 6, 7])


def test_muc_on_overmerge(overmerged):
    # recall: (5-1)+(2-1) over (5-1)+(2-1) = 5/5 -> gold links all recovered
    # precision: (7-2) over (7-1) = 5/6 -> one spurious merge across two entities
    gold, system = overmerged
    s = muc(gold, system)
    assert close(s.recall, 1.0)
    assert close(s.precision, 5 / 6)


def test_b_cubed_on_overmerge(overmerged):
    # every mention sits in a system cluster of 7.
    # the five A mentions: p=5/7, r=1;  the two B mentions: p=2/7, r=1
    # precision = (5*(5/7) + 2*(2/7)) / 7 = 29/49
    gold, system = overmerged
    s = b_cubed(gold, system)
    assert close(s.precision, 29 / 49)
    assert close(s.recall, 1.0)


def test_ceafe_on_overmerge(overmerged):
    # phi4(A,X) = 2*5/(5+7) = 5/6 ; phi4(B,X) = 2*2/(2+7) = 4/9
    # one system cluster, so the alignment takes the better: 5/6
    # precision = (5/6)/1 system cluster ; recall = (5/6)/2 gold clusters
    gold, system = overmerged
    s = ceafe(gold, system)
    assert close(s.precision, 5 / 6)
    assert close(s.recall, 5 / 12)


# --- over-splitting: gold {1,2,3,4} vs system {1,2},{3,4} -------------------

@pytest.fixture
def oversplit():
    return part(A=[1, 2, 3, 4]), part(X=[1, 2], Y=[3, 4])


def test_muc_on_oversplit(oversplit):
    # recall: (4-2)/(4-1) = 2/3 ; precision: each system cluster is pure -> 1
    gold, system = oversplit
    s = muc(gold, system)
    assert close(s.recall, 2 / 3)
    assert close(s.precision, 1.0)


def test_b_cubed_on_oversplit(oversplit):
    # every mention: overlap 2, |S|=2, |G|=4 -> p=1, r=1/2
    gold, system = oversplit
    s = b_cubed(gold, system)
    assert close(s.precision, 1.0)
    assert close(s.recall, 0.5)


def test_ceafe_on_oversplit(oversplit):
    # phi4(A,X) = phi4(A,Y) = 2*2/(4+2) = 2/3; only one can be aligned
    gold, system = oversplit
    s = ceafe(gold, system)
    assert close(s.precision, (2 / 3) / 2)
    assert close(s.recall, 2 / 3)


def test_the_two_failure_modes_are_distinguishable():
    """Over-merge and over-split must not produce the same score, or the metric
    cannot tell the resolver's documented failure mode from its opposite."""
    merged = b_cubed(part(A=[1, 2], B=[3, 4]), part(X=[1, 2, 3, 4]))
    split = b_cubed(part(A=[1, 2, 3, 4]), part(X=[1, 2], Y=[3, 4]))
    assert merged.precision < merged.recall
    assert split.recall < split.precision


# --- documented property: MUC cannot see singletons ------------------------

def test_muc_is_blind_to_singletons_and_b_cubed_is_not():
    """Why MUC is reported but never alone. A cast with a long tail of
    one-scene walk-ons is most of this corpus."""
    gold = part(A=[1, 2], B=[3], C=[4], D=[5])
    perfect = part(A=[1, 2], B=[3], C=[4], D=[5])
    # System merges all three singletons into one wrong entity.
    botched = part(A=[1, 2], WRONG=[3, 4, 5])
    assert close(muc(gold, perfect).f1, muc(gold, botched).recall)  # recall untouched
    assert b_cubed(gold, botched).f1 < b_cubed(gold, perfect).f1


# --- the assignment step ----------------------------------------------------

def test_max_weight_matching_picks_the_true_optimum_not_the_greedy_one():
    # Greedy takes 9 (row0,col0) then is forced to 1 -> 10.
    # The optimum is 8 + 7 = 15.
    weights = [[9.0, 8.0], [7.0, 1.0]]
    assert close(_max_weight_matching(weights), 15.0)


def test_max_weight_matching_handles_rectangular_input():
    assert close(_max_weight_matching([[1.0, 5.0, 3.0]]), 5.0)
    assert close(_max_weight_matching([[1.0], [5.0], [3.0]]), 5.0)


def test_max_weight_matching_agrees_with_scipy_on_random_matrices():
    """Cross-check against a reference implementation. scipy is a dev-only
    transitive dependency, which is exactly why the shipped code cannot use it."""
    linear_sum_assignment = pytest.importorskip(
        "scipy.optimize", reason="reference implementation not installed"
    ).linear_sum_assignment
    import random

    import numpy as np

    rng = random.Random(20260923)
    for _ in range(25):
        rows, cols = rng.randint(1, 6), rng.randint(1, 6)
        w = [[rng.uniform(0, 1) for _ in range(cols)] for _ in range(rows)]
        arr = np.array(w)
        r, c = linear_sum_assignment(-arr)
        assert close(_max_weight_matching(w), float(arr[r, c].sum()))


# --- CoNLL average ----------------------------------------------------------

def test_conll_f1_is_the_unweighted_mean_of_the_three():
    a = MetricScore("a", 1.0, 1.0)      # F1 1.0
    b = MetricScore("b", 0.5, 0.5)      # F1 0.5
    c = MetricScore("c", 0.0, 0.0)      # F1 0.0
    assert close(conll_f1(a, b, c), 0.5)
