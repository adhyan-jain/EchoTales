"""Tolerance scoring of scene cuts (segment v5).

Why a second metric: v4 scored exact block against exact block, so qwen3's RI ch1 answer {31, 80} against gold {31, 79}
counted as one false positive AND one false negative, although a reader would call 80 a hit. Boundary placement within
a block or two is ambiguous in a translated novel (a scene header, a blank line, a one-line establishing shot), and the
standard segmentation evaluation (WindowDiff-style tolerance) allows a small margin. Exact stays reported next to it.

Matching is one-to-one: one gold cut can absorb only one prediction, so two predictions beside the same gold cut give one
true positive and one false positive, not two hits.
"""

from __future__ import annotations


def match_cuts(gold: set[int], pred: set[int], tol: int = 0) -> list[tuple[int, int]]:
    """Maximum one-to-one matching of gold to predicted cuts within `tol` blocks, as (gold, pred) pairs.

    On a line with a fixed tolerance, taking the sorted cuts left to right and pairing the earliest still-unmatched
    ones that are within `tol` is optimal, so no assignment search is needed. Exact matches (tol 0) are the set
    intersection.
    """
    g, p = sorted(gold), sorted(pred)
    pairs: list[tuple[int, int]] = []
    i = j = 0
    while i < len(g) and j < len(p):
        if abs(g[i] - p[j]) <= tol:
            pairs.append((g[i], p[j]))
            i += 1
            j += 1
        elif g[i] < p[j]:
            i += 1
        else:
            j += 1
    return pairs


def score_cuts(gold: set[int], pred: set[int], tol: int = 0, *, ignore: set[int] | None = None) -> tuple[int, int, int]:
    """(TP, FP, FN) with one-to-one tolerance matching.

    `ignore` holds ambiguous gold positions (an annotator could not decide); a leftover prediction within `tol` of one is
    neither a hit nor a false positive, as in the exact scorer where such predictions were dropped.
    """
    pairs = match_cuts(gold, pred, tol)
    matched_p = {b for _, b in pairs}
    left = pred - matched_p
    if ignore:
        left = {b for b in left if not any(abs(b - a) <= tol for a in ignore)}
    return len(pairs), len(left), len(gold) - len(pairs)
