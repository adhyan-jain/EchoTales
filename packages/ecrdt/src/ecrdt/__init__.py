"""E-CRDT: research prototype for world convergence with provable epistemic non-interference.

Standalone package. Imports nothing from echotales-core or echotales-pipeline.
See README.md at the package root for the formal model, proofs, prior-art map,
and benchmark results.
"""

from .audit import audit_non_interference
from .baselines import ACLReplica, NaiveUnionReplica
from .model import Dot, Event
from .replica import Replica

__all__ = [
    "ACLReplica",
    "Dot",
    "Event",
    "NaiveUnionReplica",
    "Replica",
    "audit_non_interference",
]
