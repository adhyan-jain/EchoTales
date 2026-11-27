"""Convention-free change score for every block boundary of a chapter.

Why this exists (owner rule, 2026-11-27: "we cant simply do regex since it'll be
different from author to author"): RI marks a scene change with nothing at all
(ch1 blocks 31 and 80), LotM with a one-line place header after a "..." block,
ORV with `* * *`, Pride and Prejudice with a chapter-long single scene. A
detector keyed on any of those marks fails on the next novel. What every scene
change shares is that *something about the story* changes: who is on stage,
where, when, in what tense, and what the words are about. This module measures
those changes and nothing else, so it can be run on a novel nobody has seen.

Boundaries are keyed by *canonical position*: the first substantive block at or
after the gap. A one-line header ("Southern Border"), a `...` block or a symbol
line carries no story content, so the windows on either side of it are identical
whether the cut is placed before or after it. Collapsing them to one boundary
(with the marker blocks recorded in `marker_blocks`) is what lets induction ask
"which shapes sit on the high-scoring boundaries" without double counting.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from echotales.core.models import Chapter, Mention
from echotales.pipeline.segment.embed import cosine_distance, mean_vector

#: A block with fewer words than this carries no scene content of its own. 4 is
#: where the measured RI/LotM/ORV one-line headers, ellipsis blocks and symbol
#: lines (1-3 words) separate from ordinary prose and dialogue (docs/results/
#: SCENE_INDUCTION.md, "substantive threshold").
SUBSTANTIVE_MIN_WORDS = 4

#: Blocks per side of a boundary. A 120-word budget per side was tried and
#: ranked the gold cuts worse (recall in the top 8 boundaries fell from 11/22 to
#: 9/22; docs/results/SCENE_INDUCTION.md, "window"), so the plain block window stays.
WINDOW = 3

#: Cosine distances between adjacent nomic-embed-text windows sit in roughly 0.05-0.35, while the TF-IDF
#: distance spans 0.3-1.0; the scale puts the embedding feature on the same footing in the weighted sum.
EMBED_TOPIC_SCALE = 2.5

#: Non-maximum suppression radius, in boundaries.
PEAK_RADIUS = 2

#: Feature weights. Cast and location carry the most weight because a changed
#: stage is the one signal every cut in the gold set shares; topic is the only
#: one that fires on a cut where the same people stay on stage.
DEFAULT_WEIGHTS: dict[str, float] = {
    "cast": 0.35,
    "location": 0.25,
    "time": 0.15,
    "tense": 0.10,
    "topic": 0.15,
}

_QUOTE_SPANS = re.compile(r"[“\"][^”\"]*[”\"]")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'’-]{2,}")


@dataclass(slots=True)
class BlockSignals:
    """What one block says about stage, place, time and tense."""

    persons: frozenset[str] = frozenset()
    places: frozenset[str] = frozenset()
    dates: tuple[str, ...] = ()
    past: int = 0
    present: int = 0
    pluperfect: int = 0
    terms: Counter[str] = field(default_factory=Counter)


@dataclass(slots=True)
class Boundary:
    """One candidate scene boundary, before the block at `position`."""

    position: int
    marker_blocks: list[int]  # non-substantive blocks sitting in the gap
    features: dict[str, float]
    score: float
    evidence: dict[str, Any]


@lru_cache(maxsize=1)
def load_nlp() -> Any | None:
    """spaCy small English model without the parser, or None when absent.

    The parser is the slow part and nothing here needs sentences; NER gives the
    entities and DATE/TIME spans, the tagger gives tense. Absent model means the
    capitalised-run fallback below, which is weaker but still convention-free.
    """
    try:
        import spacy

        return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
    except Exception:
        return None


def is_substantive(text: str) -> bool:
    return len(text.split()) >= SUBSTANTIVE_MIN_WORDS


def canonical_position(chapter: Chapter, block: int) -> int:
    """First substantive block at or after `block`; the last block if none."""
    for b in chapter.blocks:
        if b.index >= block and b.block_type.is_story_content and is_substantive(b.text):
            return b.index
    return chapter.blocks[-1].index if chapter.blocks else block


def _token_set(surface: str) -> frozenset[str]:
    # Honorific stubs ("Mr.", "Dr.") are shared by unrelated people and would
    # make two different men look like one cast member.
    return frozenset(
        t.lower() for t in re.findall(r"[A-Za-z][A-Za-z'’]*\.?", surface) if not (t.endswith(".") and len(t) <= 4)
    )


def _fallback_entities(text: str) -> tuple[set[str], set[str]]:
    """Capitalised runs that do not open a sentence; no model required."""
    persons: set[str] = set()
    for m in re.finditer(r"(?<![.!?“\"]\s)(?<!^)\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)", text):
        persons |= set(_token_set(m.group(1)))
    return persons, set()


def analyse_blocks(
    chapter: Chapter,
    mentions: list[Mention] | None = None,
    nlp: Any | None = None,
) -> dict[int, BlockSignals]:
    """Per-block stage/place/time/tense signals.

    Mentions, when the pipeline has already produced them, add the resolved
    surface forms NER misses (RI's "Gu Yue clan head"). They are optional
    because segmentation runs before mention extraction in the normal pipeline.
    """
    nlp = nlp if nlp is not None else load_nlp()
    out: dict[int, BlockSignals] = {}
    by_block: dict[int, list[Mention]] = {}
    for m in mentions or []:
        by_block.setdefault(m.block_index, []).append(m)

    texts = [b.text for b in chapter.blocks]
    docs = list(nlp.pipe(texts, batch_size=64)) if nlp is not None else [None] * len(texts)
    for block, doc in zip(chapter.blocks, docs, strict=True):
        persons: set[str] = set()
        places: set[str] = set()
        dates: list[str] = []
        past = present = pluperfect = 0
        if doc is not None:
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    persons |= set(_token_set(ent.text))
                elif ent.label_ in ("GPE", "LOC", "FAC"):
                    places |= set(_token_set(ent.text))
                elif ent.label_ in ("DATE", "TIME"):
                    dates.append(ent.text)
            # Dialogue is present tense in every novel; counting it would make
            # every talky scene look like a tense shift against its narration.
            narration_ids = _narration_token_ids(block.text, doc)
            toks = list(doc)
            for i, tok in enumerate(toks):
                if tok.i not in narration_ids:
                    continue
                if tok.tag_ in ("VBD",):
                    past += 1
                elif tok.tag_ in ("VBP", "VBZ"):
                    present += 1
                if tok.lower_ == "had" and any(t.tag_ == "VBN" for t in toks[i + 1 : i + 4]):
                    pluperfect += 1
        else:
            fp, _ = _fallback_entities(block.text)
            persons |= fp
        for m in by_block.get(block.index, []):
            label = (m.entity_label or "").lower()
            if label == "location":
                places |= set(_token_set(m.text))
            elif label in ("", "character") and m.target_kind is not None and m.target_kind.value == "SELF":
                persons |= set(_token_set(m.text))
        terms = Counter(t.lower() for t in _TOKEN.findall(block.text))
        out[block.index] = BlockSignals(
            frozenset(persons), frozenset(places), tuple(dates), past, present, pluperfect, terms
        )
    return out


def _narration_token_ids(text: str, doc: Any) -> set[int]:
    quoted = [(m.start(), m.end()) for m in _QUOTE_SPANS.finditer(text)]
    if not quoted:
        return {t.i for t in doc}
    return {t.i for t in doc if not any(a <= t.idx < b for a, b in quoted)}


class TopicModel:
    """TF-IDF cosine between two block windows.

    A sentence-embedding model would be better, but none is installed
    (`sentence_transformers` is absent from .venv) and the project rule is not
    to download models for a feature this size. IDF fitted on the volume does
    the job a stopword list would otherwise do, without naming any words.
    """

    def __init__(self) -> None:
        self.idf: dict[str, float] = {}
        self.default_idf = 1.0

    def fit(self, documents: list[Counter[str]]) -> TopicModel:
        n = max(len(documents), 1)
        df: Counter[str] = Counter()
        for d in documents:
            df.update(d.keys())
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        self.default_idf = math.log(1 + n) + 1.0
        return self

    def distance(self, a: Counter[str], b: Counter[str]) -> float:
        va = {t: c * self.idf.get(t, self.default_idf) for t, c in a.items()}
        vb = {t: c * self.idf.get(t, self.default_idf) for t, c in b.items()}
        na = math.sqrt(sum(v * v for v in va.values()))
        nb = math.sqrt(sum(v * v for v in vb.values()))
        if na == 0 or nb == 0:
            return 0.5
        dot = sum(v * vb.get(t, 0.0) for t, v in va.items())
        return 1.0 - dot / (na * nb)


def _set_distance(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard distance; one empty side is 0.5 (unknown), two empty is 0."""
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.5
    return 1.0 - len(a & b) / len(a | b)


def _union(signals: list[BlockSignals], attr: str) -> frozenset[str]:
    out: set[str] = set()
    for s in signals:
        out |= getattr(s, attr)
    return frozenset(out)


def _past_fraction(signals: list[BlockSignals]) -> float | None:
    past = sum(s.past for s in signals)
    total = past + sum(s.present for s in signals)
    return past / total if total >= 2 else None


def score_chapter(
    chapter: Chapter,
    mentions: list[Mention] | None = None,
    *,
    nlp: Any | None = None,
    topic: TopicModel | None = None,
    weights: dict[str, float] | None = None,
    embedder: Any | None = None,
) -> list[Boundary]:
    """Score every canonical boundary of a chapter, in reading order.

    `topic` should be fitted on the whole volume; without it the chapter's own
    blocks are used, which is enough for tests but gives noisier IDF.

    With `embedder` (segment/embed.py) the topic feature is the cosine distance
    of the mean block embeddings of the two windows; when the embedder cannot be
    reached the TF-IDF feature is used, so the score never depends on a daemon.
    """
    weights = weights or DEFAULT_WEIGHTS
    signals = analyse_blocks(chapter, mentions, nlp)
    story = [b for b in chapter.blocks if b.block_type.is_story_content and is_substantive(b.text)]
    if len(story) < 2:
        return []
    topic = topic or TopicModel().fit([signals[b.index].terms for b in story])

    boundaries: list[Boundary] = []
    story_idx = [b.index for b in story]
    vec_of: dict[int, list[float]] = {}
    if embedder is not None:
        vecs = embedder.embed([b.text for b in story])
        if vecs is not None:
            vec_of = {i: v for i, v in zip(story_idx, vecs, strict=True)}
    for k in range(1, len(story)):
        pos = story_idx[k]
        before = [signals[i] for i in story_idx[max(0, k - WINDOW) : k]]
        after = [signals[i] for i in story_idx[k : k + WINDOW]]
        gap = [b.index for b in chapter.blocks if story_idx[k - 1] < b.index < pos]

        people_b, people_a = _union(before, "persons"), _union(after, "persons")
        cast = _set_distance(people_b, people_a)
        place_b, place_a = _union(before, "places"), _union(after, "places")
        # A place named only on the new side is the strongest location signal
        # ("Empress Borough, Backlund" opening a scene); a place that merely
        # drops out is weaker because narration stops naming a setting it has
        # already established.
        location = 1.0 if place_a and not (place_a & place_b) else _set_distance(place_b, place_a) * 0.6
        opening = signals[pos]
        time_expr = 1.0 if opening.dates else 0.0
        pb, pa = _past_fraction(before), _past_fraction(after)
        tense = abs(pb - pa) if pb is not None and pa is not None else 0.0
        if opening.pluperfect and not any(s.pluperfect for s in before):
            tense = max(tense, 0.5)
        term_b, term_a = Counter(), Counter()
        for s in before:
            term_b.update(s.terms)
        for s in after:
            term_a.update(s.terms)
        if vec_of:
            topic_d = min(1.0, cosine_distance(
                mean_vector([vec_of[i] for i in story_idx[max(0, k - WINDOW) : k]]),
                mean_vector([vec_of[i] for i in story_idx[k : k + WINDOW]]),
            ) * EMBED_TOPIC_SCALE)
        else:
            topic_d = topic.distance(term_b, term_a)

        features = {"cast": cast, "location": location, "time": time_expr, "tense": tense, "topic": topic_d}
        score = sum(weights[k_] * features[k_] for k_ in weights)
        boundaries.append(
            Boundary(
                position=pos,
                marker_blocks=gap,
                features=features,
                score=score,
                evidence={
                    "new_people": sorted(people_a - people_b)[:6],
                    "new_places": sorted(place_a - place_b)[:6],
                    "dates": list(opening.dates)[:3],
                    "past_before": pb,
                    "past_after": pa,
                },
            )
        )
    return _suppress_non_peaks(boundaries)


def _suppress_non_peaks(boundaries: list[Boundary]) -> list[Boundary]:
    """Halve the score of any boundary that is not the local maximum of its neighbourhood.

    Windows overlap, so the boundaries next to a real cut inherit most of its
    change; without this the top of the ranking was a cluster around each cut
    (RI ch1: 34 and 35 outranked 80) and one cut cost three false positives.
    """
    raw = [b.score for b in boundaries]
    for i, b in enumerate(boundaries):
        lo, hi = max(0, i - PEAK_RADIUS), min(len(raw), i + PEAK_RADIUS + 1)
        if raw[i] < max(raw[lo:hi]):
            b.score = raw[i] * 0.5
    return boundaries
