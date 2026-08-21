"""Phase 7: evaluation harness.

Moved ahead of scorer work per plans.md Section 13: measure the retriever ceiling and
get a baseline metric before tuning anything downstream of them.
"""

from echotales.pipeline.eval.retriever_eval import (
    DEFAULT_KS,
    GATE_ALIAS_TYPE,
    GATE_K,
    GATE_THRESHOLD,
    EvalMode,
    RecallResult,
    RetrievalCase,
    build_self_retrieval_cases,
    evaluate_recall,
    load_gold_cases,
    miss_report,
)

__all__ = [
    "DEFAULT_KS",
    "GATE_ALIAS_TYPE",
    "GATE_K",
    "GATE_THRESHOLD",
    "EvalMode",
    "RecallResult",
    "RetrievalCase",
    "build_self_retrieval_cases",
    "evaluate_recall",
    "load_gold_cases",
    "miss_report",
]
