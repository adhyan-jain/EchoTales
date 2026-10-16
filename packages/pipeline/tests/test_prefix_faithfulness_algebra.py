"""Mechanical check of the leak/loss algebra in docs/research/PREFIX_FAITHFULNESS/FORMAL.md.

A derivation D maps the evidence of chapters 1..k to a value, with `u` the neutral "unknown". r_k = D(prefix k) is what a
prefix build holds. Three ways to serve a derived fact at cut k: the status quo (the full-volume value, stamped early),
hide-only (suppress the fact until its evidence horizon H, then serve the full-volume value), and versioned (serve the
value derived from the prefix). The toy D below reads only the first W chapters, like persona traits do, so H = min(n, W).
This checks the propositions on random inputs; it says nothing about the real stage, which is covered in
test_persona_prefix_causal.py.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

U = "unknown"
FLOOR = 3
MAJORITY = 0.7


def derive(evidence: list[tuple[int, int]], width: int) -> str:
    """Gender from pronoun counts (male, female) in the first `width` chapters of evidence, with a floor and a majority."""
    window = evidence[:width]
    male = sum(m for m, _ in window)
    female = sum(f for _, f in window)
    total = male + female
    if total < FLOOR:
        return U
    if male / total >= MAJORITY:
        return "male"
    if female / total >= MAJORITY:
        return "female"
    return U


evidence_strategy = st.lists(st.tuples(st.integers(0, 4), st.integers(0, 4)), min_size=1, max_size=30)
width_strategy = st.integers(1, 12)


def serve_all(evidence, width):
    n = len(evidence)
    horizon = min(n, width)  # chapter of the last piece of evidence D reads
    r = {k: derive(evidence[:k], width) for k in range(1, n + 1)}
    status_quo = {k: r[n] for k in r}
    hide_only = {k: (U if k < horizon else r[n]) for k in r}
    versioned = {k: r[k] for k in r}
    return n, horizon, r, status_quo, hide_only, versioned


def divergence(served, r):
    return sum(1 for k in r if served[k] != r[k])


@settings(max_examples=400, deadline=None)
@given(evidence_strategy, width_strategy)
def test_no_divergence_at_or_after_the_horizon(evidence, width):
    """Soundness of the exposure screen: if D reads only chapters <= H, every cut k >= H already holds the final value."""
    n, horizon, r, status_quo, *_ = serve_all(evidence, width)
    assert all(r[k] == r[n] for k in range(horizon, n + 1))
    assert all(status_quo[k] == r[k] for k in range(horizon, n + 1))


@settings(max_examples=400, deadline=None)
@given(evidence_strategy, width_strategy)
def test_status_quo_diverges_exactly_where_the_prefix_is_not_final(evidence, width):
    n, horizon, r, status_quo, *_ = serve_all(evidence, width)
    assert divergence(status_quo, r) == sum(1 for k in range(1, horizon) if r[k] != r[n])


@settings(max_examples=400, deadline=None)
@given(evidence_strategy, width_strategy)
def test_hide_only_minus_status_quo_is_B_minus_A(evidence, width):
    """hide-only beats the status quo iff fewer in-window prefixes already hold the final value (B) than the neutral value (A)."""
    n, horizon, r, status_quo, hide_only, _ = serve_all(evidence, width)
    window = range(1, horizon)
    a = sum(1 for k in window if r[k] == U)
    b = sum(1 for k in window if r[k] == r[n])
    assert divergence(hide_only, r) - divergence(status_quo, r) == b - a


@settings(max_examples=400, deadline=None)
@given(evidence_strategy, width_strategy)
def test_versioned_never_diverges(evidence, width):
    *_, versioned = serve_all(evidence, width)
    n = len(evidence)
    assert divergence(versioned, {k: derive(evidence[:k], width) for k in range(1, n + 1)}) == 0


def test_hide_only_can_be_strictly_worse_than_doing_nothing():
    """The case measured on the three serials, in miniature: the value is established in chapter 1 and the evidence window is wide."""
    evidence = [(4, 0)] + [(0, 0)] * 5  # chapter 1 already settles "male"; later chapters add nothing
    n, horizon, r, status_quo, hide_only, versioned = serve_all(evidence, 6)
    assert horizon == 6 and r[1] == "male" == r[n]
    assert divergence(status_quo, r) == 0
    assert divergence(hide_only, r) == horizon - 1  # hides five correct values
    assert divergence(versioned, r) == 0
