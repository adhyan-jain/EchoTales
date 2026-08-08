"""Phase 6: global resolution -- the heart of the system.

Incremental entity resolution with evidence accumulation. Retrieve top-k
candidates, score a structured evidence vector, gate to LINK / NEW / DEFER via
conformal prediction, and revisit deferrals as evidence grows.
"""

from echotales.pipeline.resolve.adjudicate import (
    AdjudicationRequest,
    AdjudicationResponse,
    adjudicate,
)
from echotales.pipeline.resolve.detectors import (
    DetectorHit,
    DetectorKind,
    detect_deaths,
    detect_deceptions,
    detect_reputation,
    detect_reveals,
    detect_transfers,
    run_detectors,
)
from echotales.pipeline.resolve.evidence import (
    EvidenceContext,
    detect_declaration,
    jaro_winkler,
    score_evidence,
)
from echotales.pipeline.resolve.gate import (
    ConformalGate,
    DeferredCase,
    DeferredQueue,
)
from echotales.pipeline.resolve.retrieve import (
    BM25Index,
    CandidateRetriever,
    EntityProfile,
)
from echotales.pipeline.resolve.runner import (
    GlobalResolver,
    ResolveReport,
    resolve_novel,
)
from echotales.pipeline.resolve.score import DEFAULT_WEIGHTS, ScoringModel
from echotales.pipeline.resolve.wiki import (
    EntitySummary,
    build_focused_wiki,
    build_wiki,
    summarise_entity,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "AdjudicationRequest",
    "AdjudicationResponse",
    "BM25Index",
    "CandidateRetriever",
    "ConformalGate",
    "DeferredCase",
    "DeferredQueue",
    "DetectorHit",
    "DetectorKind",
    "EntityProfile",
    "EntitySummary",
    "EvidenceContext",
    "GlobalResolver",
    "ResolveReport",
    "ScoringModel",
    "adjudicate",
    "build_focused_wiki",
    "build_wiki",
    "detect_deaths",
    "detect_deceptions",
    "detect_declaration",
    "detect_reputation",
    "detect_reveals",
    "detect_transfers",
    "jaro_winkler",
    "resolve_novel",
    "run_detectors",
    "score_evidence",
    "summarise_entity",
]
