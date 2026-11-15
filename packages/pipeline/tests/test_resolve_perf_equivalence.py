"""The resolver speed-up caches must give exactly what the uncached code gave.

Each reference below is the pre-change computation, kept here as the oracle: the incremental
ambiguous-token table, the BM25 postings and the cached context norm (EVOLUTION: resolve at
whole-book scale) are only allowed to be faster, never different.
"""

from __future__ import annotations

import math
from collections import Counter

from echotales.core.enums import TargetKind
from echotales.pipeline.ingest import normalize
from echotales.pipeline.resolve.retrieve import (
    BM25Index,
    CandidateRetriever,
    EntityProfile,
    _cosine,
)
from hypothesis import given, settings
from hypothesis import strategies as st

_WORDS = ["wang", "kim", "dokja", "elder", "the", "fool", "klein", "moretti", "gu", "yue", "bei", "mr", "miss"]
_surface = st.lists(st.sampled_from(_WORDS), min_size=1, max_size=3).map(" ".join)
_ids = st.sampled_from([f"e{i}" for i in range(6)])


def _fresh_ambiguous(retriever: CandidateRetriever) -> frozenset[str]:
    owners: dict[str, set[str]] = {}
    for profile in retriever.profiles.values():
        for alias in profile.aliases:
            for token in normalize.name_tokens(alias):
                owners.setdefault(token, set()).add(profile.target_id)
    return frozenset(t for t, ids in owners.items() if len(ids) > 1)


_op = st.one_of(
    st.tuples(st.just("observe"), _ids, _surface),
    st.tuples(st.just("add"), _ids, st.lists(_surface, max_size=3)),
)


@settings(max_examples=150, deadline=None)
@given(st.lists(_op, max_size=40))
def test_ambiguous_tokens_equal_a_fresh_computation_after_every_change(ops) -> None:
    retriever = CandidateRetriever()
    for op in ops:
        if op[0] == "observe":
            retriever.observe(op[1], op[2], "some context", 1.0)
        else:
            # Replacing an existing id exercises the full-rebuild branch.
            retriever.add_entity(
                EntityProfile(op[1], TargetKind.SELF, op[1], aliases=set(op[2]))
            )
        assert retriever.ambiguous_tokens() == _fresh_ambiguous(retriever)


def _scan_search(index: BM25Index, query: list[str], k: int) -> list[tuple[str, float]]:
    scored = [(t, s) for t in index._docs if (s := index.score(query, t)) > 0]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored[:k]


_tokens = st.lists(st.sampled_from(_WORDS), max_size=6)


@settings(max_examples=150, deadline=None)
@given(st.lists(st.tuples(_ids, _tokens), max_size=30), st.lists(_tokens, min_size=1, max_size=5))
def test_bm25_postings_search_equals_a_full_scan(docs, queries) -> None:
    index = BM25Index()
    for target_id, tokens in docs:  # repeated ids are re-adds, as `_reindex` does
        index.add(target_id, tokens)
    for query in queries:
        assert index.search(query, k=10) == _scan_search(index, query, 10)
        assert index._avg_len == (
            sum(len(d) for d in index._docs.values()) / len(index._docs) if index._docs else 0.0
        )


def _reference_cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[t] * b[t] for t in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


@settings(max_examples=150, deadline=None)
@given(st.lists(_tokens, max_size=6), _tokens)
def test_cached_context_norm_gives_the_same_cosine(contexts, query_terms) -> None:
    profile = EntityProfile("e", TargetKind.SELF, "e")
    query = Counter(query_terms)
    for text in contexts:
        profile.observe("wang", " ".join(text) + " lantern", 1.0)
        # The cache must be dropped by observe, or the second pass reads a stale norm.
        assert _cosine(query, profile.context_terms, norm_b=profile.context_norm()) == _reference_cosine(
            query, profile.context_terms
        )
        assert _cosine(query, profile.context_terms) == _reference_cosine(query, profile.context_terms)


def test_name_tokens_ignore_family_tokens_and_return_a_fresh_list() -> None:
    before = normalize.name_tokens("Mr. Bennet's")
    try:
        normalize.set_family_tokens({"bennet"})
        assert normalize.name_tokens("Mr. Bennet's") == before
    finally:
        normalize.set_family_tokens(())
    before.append("mutated")
    assert normalize.name_tokens("Mr. Bennet's") != before
    # comparison_key is not cached precisely because it does depend on them.
    normalize.set_family_tokens({"bennet"})
    try:
        assert normalize.comparison_key("Mr. Bennet") == "mr:bennet"
    finally:
        normalize.set_family_tokens(())
    assert normalize.comparison_key("Mr. Bennet") == "bennet"
