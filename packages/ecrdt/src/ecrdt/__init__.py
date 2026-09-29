"""E-CRDT: research prototype for world convergence with provable epistemic non-interference.

Standalone package. Imports nothing from echotales-core or echotales-pipeline.
See README.md at the package root for the formal model, proofs, prior-art map,
and benchmark results.
"""

from .model import Dot, Event
from .replica import Replica
from .baselines import NaiveUnionReplica, ACLReplica
from .audit import audit_non_interference

__all__ = [
    "Dot",
    "Event",
    "Replica",
    "NaiveUnionReplica",
    "ACLReplica",
    "audit_non_interference",
]
