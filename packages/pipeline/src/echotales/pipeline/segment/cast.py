"""Cast continuity from the graph, and the fusion with the outline cuts (segment v4).

Why a structural signal next to the model: the outline pass is one model's reading, and the 8B models used here make
different mistakes from a count of who is on stage. A scene change is, by the classic definition, a change of people
as much as of place, and the graph already knows who acts or speaks in every block (resolved mentions and speaker
attributions). So the boundary score is how little the cast of the K cast-bearing blocks before a position overlaps the
cast of the K after it. No model, no word list.

Blocks with no person in them (landscape, a one-line header) are skipped when the K blocks are collected: RI ch1
blocks 31-35 describe a mountain village and name nobody, and a window that counted them would see "nobody" on one
side and say nothing about the cut. Because the skipped blocks make every position in the gap score the same, a cast
cut is placed right after the last block of the old cast (the descriptive lead-in belongs to the new scene).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from echotales.core.models import Chapter, Mention
from echotales.pipeline.segment.discontinuity import _fallback_entities
from echotales.pipeline.segment.judge import story_blocks

#: Reported speech and thought name people who are not on stage (RI ch1 31-78: the elders discuss Fang Yuan).
REFERENCE_WEIGHT = 0.3
_REFERENCE_MODES = ("DIALOGUE_REFERENCE", "INNER_THOUGHT_REFERENCE")
_NOT_PEOPLE = {"item", "location", "organization", "category"}


def _surface_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^(?:the|a|an)\s+", "", text.strip().lower()))


def block_casts(
    chapter: Chapter,
    mentions: list[Mention] | None,
    spans: list[Any] | None = None,
) -> dict[int, dict[str, float]]:
    """Weighted entities per story block. Acting, speaking and narrated people weigh 1, quoted ones REFERENCE_WEIGHT.

    A chapter with no mentions at all (the public-domain novels in the eval have none) falls back to the capitalised
    runs the discontinuity scorer already uses, all weighted 1.
    """
    out: dict[int, dict[str, float]] = {}

    def add(b: int, key: str, w: float) -> None:
        if len(key) >= 3:
            d = out.setdefault(b, {})
            d[key] = max(d.get(key, 0.0), w)

    people = [m for m in mentions or [] if (m.entity_label or "").lower() not in _NOT_PEOPLE]
    if people or spans:
        for m in people:
            key = m.target_id or f"u:{_surface_key(m.text)}"
            add(m.block_index, key, REFERENCE_WEIGHT if m.reference_mode.value in _REFERENCE_MODES else 1.0)
        for sp in spans or []:
            sid = getattr(sp, "speaker_self_id", None)
            if sid and ":anon:" not in sid:
                add(sp.block_index, sid, 1.0)
    else:
        for b in chapter.blocks:
            if b.block_type.is_story_content:
                persons, _ = _fallback_entities(b.text)
                for p in persons:
                    add(b.index, p, 1.0)
    return out


def _wjaccard(a: dict[str, float], b: dict[str, float]) -> float:
    keys = a.keys() | b.keys()
    den = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys) / den if den else 1.0


def cast_scores(chapter: Chapter, casts: dict[int, dict[str, float]], k: int) -> dict[int, float]:
    """Cast discontinuity (0 = same people, 1 = nobody in common) before each story block but the first.

    0 where either side has no cast at all: no evidence, not a cut.
    """
    order = story_blocks(chapter)
    bearing = [b for b in order if casts.get(b)]
    out: dict[int, float] = {}
    for r, pos in enumerate(order):
        if r == 0:
            continue
        before = [b for b in bearing if b < pos][-k:]
        after = [b for b in bearing if b >= pos][:k]
        if not before or not after:
            out[pos] = 0.0
            continue
        va: dict[str, float] = {}
        vb: dict[str, float] = {}
        for b in before:
            for e, w in casts[b].items():
                va[e] = max(va.get(e, 0.0), w)
        for b in after:
            for e, w in casts[b].items():
                vb[e] = max(vb.get(e, 0.0), w)
        out[pos] = round(1.0 - _wjaccard(va, vb), 4)
    return out


def separator_positions(chapter: Chapter) -> set[int]:
    """Story blocks preceded by a non-substantive or non-story block (a rule, a lone symbol, a one-line header)."""
    order = story_blocks(chapter)
    return {b for a, b in pairwise(order) if b - a > 1}


def cast_cuts(order: list[int], scores: dict[int, float], theta: float, min_gap: int) -> list[int]:
    """Positions whose cast discontinuity reaches `theta`: the earliest of each plateau, then `min_gap` spacing."""
    rank = {b: i for i, b in enumerate(order)}
    kept: list[int] = []
    run: list[int] = []

    def flush() -> None:
        if run:
            peak = max(scores[b] for b in run)
            first = next(b for b in run if scores[b] >= peak - 1e-9)
            if all(abs(rank[first] - rank[o]) >= min_gap for o in kept):
                kept.append(first)

    for b in order[1:]:
        if scores.get(b, 0.0) >= theta and (not run or rank[b] - rank[run[-1]] == 1):
            run.append(b)
        else:
            flush()
            run = [b] if scores.get(b, 0.0) >= theta else []
    flush()
    return sorted(kept)


@dataclass(slots=True)
class FusionParams:
    """How the outline cuts and the cast signal combine; chosen on the learn chapters (scripts/eval/segment_v4_eval.py).

    mode "outline": the model's cuts alone. "and": an outline cut is kept only when the cast also changes within
    `window` story blocks of it (score >= `theta`) or, with `use_sep`, a separator sits at it. "or": the outline cuts
    plus cast cuts that are both strong (>= `theta`) and at a separator. "cast": the cast cuts alone.
    """

    mode: str = "outline"
    cast_k: int = 3
    theta: float = 0.5
    window: int = 2
    use_sep: bool = True
    min_gap: int = 3


def fuse(
    chapter: Chapter,
    outline_cuts: list[int],
    scores: dict[int, float],
    separators: set[int],
    p: FusionParams,
) -> list[int]:
    order = story_blocks(chapter)
    rank = {b: i for i, b in enumerate(order)}
    if p.mode == "cast":
        cuts = cast_cuts(order, scores, p.theta, p.min_gap)
    elif p.mode == "outline":
        cuts = sorted(set(outline_cuts))
    elif p.mode == "and":
        cuts = []
        for c in sorted(set(outline_cuts)):
            r = rank.get(c)
            if r is None:
                continue
            near = [order[i] for i in range(max(1, r - p.window), min(len(order), r + p.window + 1))]
            if max((scores.get(b, 0.0) for b in near), default=0.0) >= p.theta or (p.use_sep and c in separators):
                cuts.append(c)
    elif p.mode == "or":
        extra = [b for b in cast_cuts(order, scores, p.theta, p.min_gap) if b in separators]
        cuts = sorted(set(outline_cuts) | set(extra))
    else:
        raise ValueError(p.mode)
    kept: list[int] = []
    for c in cuts:
        if all(abs(rank.get(c, 0) - rank.get(o, 0)) >= p.min_gap for o in kept):
            kept.append(c)
    return kept
