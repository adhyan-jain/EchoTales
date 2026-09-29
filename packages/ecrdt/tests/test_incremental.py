"""Differential correctness proof (empirical) for IncrementalReplica against
the reference Replica: same op sequence, same merge pattern (including
reordered/delayed/duplicate merges), materialize() must agree at every
checkpoint. This is the actual verification of Theorem 6 (order-independence
of concurrent event effects) -- see IPR_REVIEW.md Phase 7.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ecrdt.replica import Replica
from ecrdt.incremental import IncrementalReplica


def _apply_same_op(ref, inc, op, args):
    """Apply an identical operation to both implementations; both must
    accept or reject it identically."""
    ref_err = inc_err = None
    ref_result = inc_result = None
    try:
        ref_result = getattr(ref, op)(*args)
    except ValueError as e:
        ref_err = str(e)
    try:
        inc_result = getattr(inc, op)(*args)
    except ValueError as e:
        inc_err = str(e)
    assert (ref_err is None) == (inc_err is None), (
        f"reference/incremental disagreed on whether op {op}{args} is valid: "
        f"ref_err={ref_err!r} inc_err={inc_err!r}"
    )


def _assert_equivalent(ref: Replica, inc: IncrementalReplica, label: str = ""):
    ref_known, _ = ref.materialize()
    inc_known, _ = inc.materialize()
    assert ref_known == inc_known, f"{label}: materialize() diverged: ref={ref_known} inc={inc_known}"
    assert ref.W.facts() == inc.W.facts(), f"{label}: W diverged"


def test_incremental_matches_reference_in_order_single_replica():
    ref, inc = Replica("a"), IncrementalReplica("a")
    ops = [
        ("assert_world", ("p1",)),
        ("observe", ("p1",)),
        ("assert_world", ("p2",)),
        ("observe", ("p2",)),
        ("infer", ("derived", ["p1", "p2"])),
        ("assert_world", ("p3",)),
    ]
    for op, args in ops:
        _apply_same_op(ref, inc, op, args)
        _assert_equivalent(ref, inc, f"after {op}{args}")


def test_incremental_matches_reference_under_delayed_out_of_order_merge():
    """The exact scenario that broke naive per-dot caching: an INFER event
    delivered before its premise's OBSERVE event."""
    ref_src, inc_src = Replica("a"), IncrementalReplica("a")
    for op, args in [("assert_world", ("p1",)), ("observe", ("p1",)), ("infer", ("derived", ["p1"]))]:
        _apply_same_op(ref_src, inc_src, op, args)

    infer_dot = next(d for d, e in ref_src.E.items() if e.kind == "infer")
    observe_dot = next(d for d, e in ref_src.E.items() if e.kind == "observe")
    assert_dot = next(d for d, e in ref_src.E.items() if e.kind == "assert_world")

    ref_partial, inc_partial = Replica("a"), IncrementalReplica("a")
    ref_partial.E[infer_dot] = ref_src.E[infer_dot]
    ref_partial._dirty = True
    inc_partial.E[infer_dot] = inc_src.E[infer_dot]
    inc_partial._pending[infer_dot] = inc_src.E[infer_dot]
    inc_partial._drain()
    _assert_equivalent(ref_partial, inc_partial, "infer arrived alone, before its deps")
    assert "derived" not in ref_partial.materialize()[0]

    for d in (assert_dot, observe_dot):
        ref_partial.E[d] = ref_src.E[d]
        inc_partial.E[d] = inc_src.E[d]
        inc_partial._pending[d] = inc_src.E[d]
    ref_partial._dirty = True
    inc_partial._drain()
    _assert_equivalent(ref_partial, inc_partial, "deps arrived, should self-heal")
    assert "derived" in ref_partial.materialize()[0]


def test_incremental_matches_reference_under_randomized_reordered_merges():
    """The real proof: 500 random ops across 5 replicas, then propagate to
    a 6th 'observer' replica via merges delivered in random chunks and
    random order, checking equivalence after every single merge step."""
    rng = random.Random(2024)
    ids = [f"r{i}" for i in range(5)]
    refs = {r: Replica(r) for r in ids}
    incs = {r: IncrementalReplica(r) for r in ids}
    facts = [f"f{i}" for i in range(25)]

    for _ in range(500):
        r = rng.choice(ids)
        act = rng.choice(["assert", "observe", "infer", "communicate", "retract", "merge"])
        if act == "assert":
            f = rng.choice(facts)
            if f not in refs[r].W.facts():
                _apply_same_op(refs[r], incs[r], "assert_world", (f,))
        elif act == "observe":
            live = list(refs[r].W.facts())
            if live:
                f = rng.choice(live)
                _apply_same_op(refs[r], incs[r], "observe", (f,))
        elif act == "infer":
            known, _ = refs[r].materialize()
            if len(known) >= 2:
                premises = rng.sample(sorted(known), 2)
                _apply_same_op(refs[r], incs[r], "infer", (f"d_{'_'.join(premises)}", premises))
        elif act == "communicate":
            known, _ = refs[r].materialize()
            if known:
                other = rng.choice([x for x in ids if x != r])
                f = rng.choice(sorted(known))
                _apply_same_op(refs[r], incs[r], "communicate", (other, f))
        elif act == "retract":
            live = list(refs[r].W.facts())
            if live and rng.random() < 0.3:
                _apply_same_op(refs[r], incs[r], "retract_world", (rng.choice(live),))
        else:
            a, b = rng.sample(ids, 2)
            # deliver in a randomly-split, randomly-ordered chunk to stress
            # the pending-buffer drain logic, instead of one atomic merge
            other_dots = list(refs[b].E.keys())
            rng.shuffle(other_dots)
            split = rng.randrange(0, len(other_dots) + 1) if other_dots else 0
            for dots_chunk in (other_dots[:split], other_dots[split:]):
                if not dots_chunk:
                    continue
                for d in dots_chunk:
                    if d not in refs[a].E:
                        refs[a].E[d] = refs[b].E[d]
                        refs[a]._dirty = True
                    if d not in incs[a].E:
                        incs[a].E[d] = incs[b].E[d]
                        incs[a]._pending[d] = incs[b].E[d]
                refs[a].W = refs[a].W.join(refs[b].W)
                incs[a].W = incs[a].W.join(incs[b].W)
                incs[a]._drain()
        _assert_equivalent(refs[r] if act != "merge" else refs[a], incs[r] if act != "merge" else incs[a],
                            f"op={act}")

    # final full settle and check pending backlogs drained to zero
    for _ in range(3):
        for a in ids:
            for b in ids:
                if a != b:
                    refs[a].merge(refs[b])
                    incs[a].merge(incs[b])
    for r in ids:
        _assert_equivalent(refs[r], incs[r], f"final settle {r}")
        assert incs[r].pending_backlog() == 0, f"{r} has undelivered backlog after full settle: {incs[r]._pending}"


def test_incremental_is_actually_incremental_not_just_correct():
    """Sanity: total events *processed* across the replica's life should be
    O(|E|), not O(|E|^2) -- each event delivered exactly once."""
    inc = IncrementalReplica("a")
    n = 300
    for i in range(n):
        inc.assert_world(f"f{i}")
        inc.observe(f"f{i}")
    assert inc.events_processed == 2 * n, "every event should be delivered exactly once"
    assert inc.pending_backlog() == 0
