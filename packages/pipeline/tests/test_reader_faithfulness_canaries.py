"""FORMAL.md P9-P10 on toy systems: suffix canaries never raise a false alarm, and never see a selection leak.

A volume is a list of chapters, each a list of tokens; "A" is an alias and "ID" an identity name. Three toy systems serve a
reader at chapter c: a whole-volume card (content from every chapter mentioning A), a prefix card (the versioned build), and
merged-entity retrieval (a whole-volume index merges A with ID when some chapter after c names both, then serves only prefix
chapters mentioning either). The canary test replaces every suffix token with a fresh one and looks for fresh tokens in the
output; truncate-and-rebuild compares the output with the build from chapters <= c. Real measurements: RF-E2E addenda 12, 13.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

VOCAB = ["A", "ID", "x", "y", "z", "w"]
chapter = st.lists(st.sampled_from(VOCAB), min_size=1, max_size=6)
volume = st.lists(chapter, min_size=2, max_size=8)


def whole_card(vol, c):
    return {t for ch in vol if "A" in ch for t in ch}


def prefix_card(vol, c):
    return {t for ch in vol[:c] if "A" in ch for t in ch}


def merged_retrieval(vol, c):
    merged = any("A" in ch and "ID" in ch for ch in vol[c:])  # the index reads the whole volume
    keys = {"A", "ID"} if merged else {"A"}
    return {t for ch in vol[:c] if keys & set(ch) for t in ch}  # but serves only chapters before the reader


def canary(vol, c):
    """Fresh token per suffix position; returns the canaried volume and the set of planted tokens."""
    planted, out = set(), [list(ch) for ch in vol[:c]]
    for i, ch in enumerate(vol[c:]):
        new = [f"canary{i}_{j}" if t != "A" else t for j, t in enumerate(ch)]  # keep the alias so the system still finds it
        planted |= {t for t in new if t.startswith("canary")}
        out.append(new)
    return out, planted


def canary_fires(system, vol, c):
    vol2, planted = canary(vol, c)
    return bool(system(vol2, c) & planted)


def rebuild_differs(system, vol, c):
    return system(vol, c) != system(vol[:c], c)


cuts = st.integers(1, 7)


@settings(max_examples=400, deadline=None)
@given(volume, cuts)
def test_p9_a_canary_hit_is_always_a_real_violation(vol, c):
    c = min(c, len(vol) - 1)
    for system in (whole_card, prefix_card, merged_retrieval):
        if canary_fires(system, vol, c):
            vol2, _ = canary(vol, c)
            assert rebuild_differs(system, vol2, c)


@settings(max_examples=400, deadline=None)
@given(volume, cuts)
def test_p10_canaries_never_fire_on_a_selection_only_system(vol, c):
    c = min(c, len(vol) - 1)
    assert not canary_fires(merged_retrieval, vol, c)
    assert not canary_fires(prefix_card, vol, c)


def test_p10_the_selection_leak_is_real_and_only_rebuild_sees_it():
    vol = [["A", "x"], ["ID", "y"], ["A", "ID", "z"]]  # ID is named before the cut; the reveal (A with ID) comes after it
    c = 2
    assert rebuild_differs(merged_retrieval, vol, c)  # served {"A","x","ID","y"} against {"A","x"}
    assert not canary_fires(merged_retrieval, vol, c)  # and the canaried reveal no longer links A to ID at all
    assert canary_fires(whole_card, vol, c)  # the content leak is seen by both oracles
    assert rebuild_differs(whole_card, vol, c)
