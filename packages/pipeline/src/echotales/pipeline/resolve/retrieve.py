"""Candidate retrieval for global resolution (plans.md §6 Phase 6, step 1).

Given a local mention group, produce the top-k entities it might denote. k=10
is enough: the point of retrieval is to bound the scoring work, not to decide
anything. Precision comes later, from the evidence vector.

Two complementary retrievers, because either alone fails on this content:

**Lexical (BM25 over known aliases).** Catches the ordinary case where a
mention shares surface form with a confirmed alias, and survives honorific
drift once the query is stripped ("Elder Wang" → "Wang").

**Contextual (embedding similarity).** Catches the case lexical retrieval
cannot: "Fang Yuan" and "Liu Guan Yi" share no characters at all, yet a
disguise identity appears in the same regions, with the same associates, doing
the same kinds of things. That contextual footprint is the only retrievable
signal linking them.

Sentence-transformers is an optional extra. Without it, a deterministic
bag-of-words cosine stands in — worse, but it keeps the ranking behaviour and
the whole pipeline runnable.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from echotales.core.enums import TargetKind
from echotales.core.models import Candidate
from echotales.pipeline.ingest.normalize import comparison_key, strip_honorifics

DEFAULT_K = 10


@dataclass(slots=True)
class EntityProfile:
    """What retrieval knows about one candidate entity.

    Grows as the entity is seen: every confirmed mention adds surface forms and
    context. This is the accumulation half of "incremental resolution with
    evidence accumulation".
    """

    target_id: str
    target_kind: TargetKind
    label: str
    aliases: set[str] = field(default_factory=set)
    #: Bag of context terms drawn from the entity's mention neighbourhoods.
    context_terms: Counter[str] = field(default_factory=Counter)
    first_chapter: float = 0.0
    last_chapter: float = 0.0
    mention_count: int = 0
    #: Selves seen speaking with this entity; feeds speech-partner scoring.
    speech_partners: Counter[str] = field(default_factory=Counter)

    def observe(self, surface: str, context: str, chapter: float) -> None:
        self.aliases.add(surface)
        self.context_terms.update(_terms(context))
        self.mention_count += 1
        if self.first_chapter == 0.0:
            self.first_chapter = chapter
        self.last_chapter = max(self.last_chapter, chapter)

    @property
    def alias_keys(self) -> set[str]:
        return {comparison_key(a) for a in self.aliases if comparison_key(a)}


_STOP = frozenset(
    ["the", "a", "an", "and", "or", "but", "if", "when", "while", "of", "to", "in", "on", "at", "by", "for", "with", "from", "as", "is", "was", "were", "are", "be", "been", "being", "he", "she", "it", "they", "them", "his", "her", "its", "their", "this", "that", "these", "those", "there", "here", "then", "now", "not", "no", "yes", "had", "has", "have", "do", "did", "does", "will", "would", "could", "should", "may", "might", "must", "one", "two", "said", "say", "says", "very", "much", "many", "more", "most"]
)


def _terms(text: str) -> list[str]:
    """Content words from a piece of context."""
    return [
        w
        for raw in text.lower().split()
        if (w := raw.strip(".,;:!?\"'“”‘’()[]—–-")) and len(w) > 2 and w not in _STOP
    ]


class BM25Index:
    """Minimal BM25 over entity alias sets.

    Implemented here rather than pulled from a library because the corpus is
    tiny (one short document per entity) and the tuning that matters is the
    tokenisation, not the ranking function.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: dict[str, list[str]] = {}
        self._df: Counter[str] = Counter()
        self._avg_len = 0.0

    def add(self, target_id: str, tokens: list[str]) -> None:
        if target_id in self._docs:
            for token in set(self._docs[target_id]):
                self._df[token] -= 1
        self._docs[target_id] = tokens
        for token in set(tokens):
            self._df[token] += 1
        if self._docs:
            self._avg_len = sum(len(d) for d in self._docs.values()) / len(self._docs)

    def score(self, query: list[str], target_id: str) -> float:
        doc = self._docs.get(target_id)
        if not doc:
            return 0.0
        n = len(self._docs)
        counts = Counter(doc)
        total = 0.0
        for token in query:
            df = self._df.get(token, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = counts.get(token, 0)
            if tf == 0:
                continue
            denom = tf + self.k1 * (1 - self.b + self.b * len(doc) / (self._avg_len or 1))
            total += idf * (tf * (self.k1 + 1)) / denom
        return total

    def search(self, query: list[str], k: int = DEFAULT_K) -> list[tuple[str, float]]:
        scored = [
            (target_id, score)
            for target_id in self._docs
            if (score := self.score(query, target_id)) > 0
        ]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    """Cosine over term counts.

    The fallback when sentence-transformers is unavailable. Weaker than a
    learned embedding at spotting paraphrase, but it does capture the signal
    that matters most here: shared associates, shared locations, shared
    vocabulary.
    """
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[t] * b[t] for t in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class CandidateRetriever:
    """Top-k retrieval over the accumulated entity profiles."""

    def __init__(self, k: int = DEFAULT_K) -> None:
        self.k = k
        self.profiles: dict[str, EntityProfile] = {}
        self._bm25 = BM25Index()
        #: See `_prominent`. `None` means "not built"; `_prominent_at` records
        #: the profile count it was built at, so entity creation invalidates it.
        self._prominent_cache: list[EntityProfile] | None = None
        self._prominent_at = -1

    def add_entity(self, profile: EntityProfile) -> None:
        self.profiles[profile.target_id] = profile
        self._reindex(profile)

    def observe(
        self,
        target_id: str,
        surface: str,
        context: str,
        chapter: float,
        *,
        target_kind: TargetKind = TargetKind.SELF,
        label: str | None = None,
    ) -> EntityProfile:
        """Record a confirmed mention against an entity, creating it if new."""
        profile = self.profiles.get(target_id)
        if profile is None:
            profile = EntityProfile(
                target_id=target_id,
                target_kind=target_kind,
                label=label or surface,
                first_chapter=chapter,
            )
            self.profiles[target_id] = profile
        profile.observe(surface, context, chapter)
        self._reindex(profile)
        return profile

    def _reindex(self, profile: EntityProfile) -> None:
        tokens: list[str] = []
        for alias in profile.aliases:
            bare = strip_honorifics(alias)
            tokens.extend(_terms(alias))
            if bare != alias:
                tokens.extend(_terms(bare))
            key = comparison_key(alias)
            if key:
                tokens.append(key)
        self._bm25.add(profile.target_id, tokens)

    def _prominent(self, want: int) -> list[EntityProfile]:
        """The most-mentioned entities, cached (§4.2).

        This ranking was the residual superlinear term: re-sorting every
        profile once per mention group made retrieval O(groups x entities
        log entities), measured at 7.6 -> 9.1 -> 11.7 ms/group across 20/40/80
        chapters after the shortlist fix had already removed the larger one.

        **A stale ranking is a correctness non-issue, which is what makes
        caching legitimate here.** This list is a recall *tail*: the shortlist
        above is the real answer, and these are appended so that a disguise
        identity sharing no surface form with its holder stays retrievable at
        all. Whether the 30th-most-mentioned entity is currently ranked 30th
        or 32nd changes nothing about that. Rebuilt whenever an entity is
        created (the only change that can introduce a genuinely new candidate)
        and on `refresh_prominent()` at window boundaries; mention-count drift
        between those points is deliberately tolerated.
        """
        if self._prominent_cache is None or self._prominent_at != len(self.profiles):
            self._prominent_cache = sorted(
                self.profiles.values(), key=lambda p: p.mention_count, reverse=True
            )
            self._prominent_at = len(self.profiles)
        return self._prominent_cache[:want]

    def refresh_prominent(self) -> None:
        """Drop the cached ranking so the next retrieval rebuilds it.

        Called at window boundaries, where accumulated mention counts have
        moved enough that the tolerated drift above is worth clearing.
        """
        self._prominent_cache = None

    def retrieve(
        self,
        surface: str,
        context: str,
        *,
        k: int | None = None,
    ) -> list[Candidate]:
        """Top-k candidates for a mention, blending lexical and contextual scores."""
        limit = k or self.k
        if not self.profiles:
            return []

        query_tokens = _terms(surface)
        bare = strip_honorifics(surface)
        if bare != surface:
            query_tokens.extend(_terms(bare))
        key = comparison_key(surface)
        if key:
            query_tokens.append(key)

        lexical = dict(self._bm25.search(query_tokens, k=limit * 3))
        max_lexical = max(lexical.values(), default=0.0)

        context_terms = Counter(_terms(context))

        # Only consider the lexical shortlist plus the most prominent entities.
        #
        # Scoring every profile made retrieval O(groups x entities): measured
        # 7.5 ms/group at 20 chapters rising to 15.3 ms/group at 40, which
        # times out well before a full volume. The prominent-entity tail is
        # kept because a disguise identity shares no surface form with its
        # holder and would never reach the BM25 shortlist -- dropping it
        # entirely would make the flagship case unretrievable.
        considered: dict[str, EntityProfile] = {
            tid: self.profiles[tid] for tid in lexical if tid in self.profiles
        }
        if len(considered) < limit * 3:
            for profile in self._prominent(limit * 3):
                considered.setdefault(profile.target_id, profile)

        scored: list[Candidate] = []
        for target_id, profile in considered.items():
            lex = lexical.get(target_id, 0.0) / max_lexical if max_lexical else 0.0
            ctx = _cosine(context_terms, profile.context_terms)
            # Neither signal is trusted alone: lexical alone misses disguise
            # identities entirely, contextual alone confuses everyone who
            # shares a setting.
            blended = 0.65 * lex + 0.35 * ctx
            if blended <= 0.0:
                continue
            scored.append(
                Candidate(
                    target_kind=profile.target_kind,
                    target_id=target_id,
                    label=profile.label,
                    retrieval_score=blended,
                )
            )

        scored.sort(key=lambda c: c.retrieval_score, reverse=True)
        return scored[:limit]

    def __len__(self) -> int:
        return len(self.profiles)
