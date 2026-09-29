"""Ground-truth non-interference auditor.

Independent of the E-CRDT's own materialization logic, this walks a
replica's *known-valid* disclosure history (tracked out-of-band by the
benchmark harness as "ground truth: which replica really received which
fact via a real OBSERVE/COMMUNICATE/INFER") and flags any replica whose
apparent knowledge (per the system under test) contains a fact absent from
that ground truth. This is what makes "unauthorized knowledge propagation"
a measured number rather than an assertion.
"""
from __future__ import annotations

from typing import Dict, Set


def audit_non_interference(
    apparent_knowledge: Dict[str, Set[str]],
    ground_truth_disclosures: Dict[str, Set[str]],
) -> Dict[str, Set[str]]:
    """Return {replica_id: set of facts it apparently knows but was never
    causally disclosed}. Empty dict-of-empty-sets == no violations."""
    violations: Dict[str, Set[str]] = {}
    for replica_id, facts in apparent_knowledge.items():
        allowed = ground_truth_disclosures.get(replica_id, set())
        bad = facts - allowed
        if bad:
            violations[replica_id] = bad
    return violations


def total_violation_count(violations: Dict[str, Set[str]]) -> int:
    return sum(len(v) for v in violations.values())
