"""Cuts with no marker at all, and what story-time relation each one has.

Why an LLM here, and why it only sees the top of the score list: RI ch1 has two
unmarked cuts (blocks 31 and 80). No shape separates them from ordinary
paragraph breaks, so the only evidence is the change score
(`discontinuity.py`) and a reader's judgement of the two sides. The pass is
conservative on purpose: a spurious cut splits one scene's cast in two
(docs/design/adaptation_director_plan.md P0.5), a missed one merges two.

The relation between a cut's two sides is a separate question and is often
unanswerable at the cut. At RI block 31 nothing says the ritual happens 500
years before the cliff; block 80 ("this is 500 years ago?!") says it, far from
the cut that first needed it. So `judge_cut` may answer UNKNOWN, and
`resolve_story_order` revisits the relations once the whole chapter is in view.
"""

from __future__ import annotations

from typing import Any

from echotales.core.models import Chapter
from echotales.pipeline.llm import LLMRequest
from echotales.pipeline.segment.cuts import CutType, SceneCut, TimeRelation
from echotales.pipeline.segment.discontinuity import Boundary, is_substantive, load_nlp
from pydantic import BaseModel, Field

JUDGE_SYSTEM = (
    "You decide whether a chapter of a translated novel changes scene at a given point. A scene change means a "
    "different place, a different time, or different people on stage, with no continuous action across the point. "
    "Walking from one room to the next inside one continuous action is NOT a scene change; a new paragraph about "
    "the same people in the same place is NOT a scene change. You are conservative. For the story-time relation of "
    "the text after the point to the text before it, answer UNKNOWN unless the shown text states it or clearly "
    "implies it."
)


class CutJudgement(BaseModel):
    is_cut: bool = Field(description="true only if the text after the point is a new scene")
    cut_type: str = Field(
        default="NEW_SCENE",
        description="NEW_SCENE, TIME_JUMP, FLASHBACK, PRIOR_LOOP, POV_SWITCH or LORE",
    )
    time_relation: str = Field(
        default="UNKNOWN",
        description="story time of the text AFTER the point relative to the text BEFORE: EARLIER, LATER, SAME or UNKNOWN",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


def _enum_or(enum_cls: Any, value: str, default: Any) -> Any:
    try:
        return enum_cls(value.strip().upper())
    except ValueError:
        return default


def _clip(text: str, n: int, tail: bool = False) -> str:
    t = " ".join(text.split())
    if len(t) <= n:
        return t
    return "..." + t[-n:] if tail else t[:n] + "..."


def cut_context(chapter: Chapter, position: int, n: int = 3) -> tuple[str, str]:
    story = [b for b in chapter.blocks if b.block_type.is_story_content and is_substantive(b.text)]
    before = [b for b in story if b.index < position][-n:]
    after = [b for b in story if b.index >= position][:n]
    return (
        "\n".join(f"[{b.index}] {_clip(b.text, 380, tail=True)}" for b in before),
        "\n".join(f"[{b.index}] {_clip(b.text, 380)}" for b in after),
    )


def judge_cut(chapter: Chapter, boundary: Boundary, llm: Any) -> CutJudgement:
    before, after = cut_context(chapter, boundary.position)
    ev = boundary.evidence
    hints = []
    if ev.get("new_people"):
        hints.append("names appearing only after: " + ", ".join(ev["new_people"]))
    if ev.get("new_places"):
        hints.append("places appearing only after: " + ", ".join(ev["new_places"]))
    if ev.get("dates"):
        hints.append("time expressions at the start: " + ", ".join(ev["dates"]))
    prompt = (
        f"TEXT BEFORE THE POINT:\n{before}\n\n--- POINT (before block {boundary.position}) ---\n\n"
        f"TEXT AFTER THE POINT:\n{after}\n\n"
        + (("Automatic hints: " + "; ".join(hints) + "\n\n") if hints else "")
        + "Is the point a scene change? If so, which kind, and what is the story-time relation?"
    )
    res = llm.complete(
        LLMRequest(stage="scene_cut_judge", prompt=prompt, system=JUDGE_SYSTEM, max_tokens=300), CutJudgement
    )
    return res.value


def propose_implicit_cuts(
    chapter: Chapter,
    boundaries: list[Boundary],
    taken: set[int],
    llm: Any,
    *,
    threshold: float,
    priority: set[int] | None = None,
    max_cuts: int = 4,
    min_confidence: float = 0.6,
) -> list[SceneCut]:
    """Ask the model about the highest-scoring boundaries not already cut by a convention.

    `taken` blocks and their immediate substantive neighbours are skipped: the
    window overlap makes the next boundary over score almost as high as a real
    cut, and asking about it would re-propose the same cut one block late.
    """
    story_positions = [b.position for b in boundaries]
    near: set[int] = set()
    for t in taken:
        near.add(t)
        if t in story_positions:
            i = story_positions.index(t)
            near.update(story_positions[max(0, i - 1) : i + 2])
    priority = priority or set()
    ranked = [
        b
        for b in sorted(boundaries, key=lambda b: (b.position not in priority, -b.score))
        if (b.score >= threshold or b.position in priority) and (b.position not in near or b.position in priority)
    ]
    cuts: list[SceneCut] = []
    for b in ranked[: max_cuts * 2]:
        if len(cuts) >= max_cuts:
            break
        if any(abs(c.block - b.position) <= 1 for c in cuts):
            continue
        try:
            j = judge_cut(chapter, b, llm)
        except Exception:  # an unreachable or malformed answer is "no cut", never a guessed one
            continue
        if not j.is_cut or j.confidence < min_confidence:
            continue
        cuts.append(
            SceneCut(
                chapter=chapter.number,
                block=b.position,
                source="implicit:llm",
                score=round(b.score, 3),
                cut_type=_enum_or(CutType, j.cut_type, CutType.NEW_SCENE),
                time_relation=_enum_or(TimeRelation, j.time_relation, TimeRelation.UNKNOWN),
                confidence=j.confidence,
                evidence=[j.reason[:160]],
            )
        )
    return sorted(cuts, key=lambda c: c.block)


# --------------------------------------------------------------------- story order


class OrderItem(BaseModel):
    segment: int
    relative_to_previous: str = Field(description="EARLIER, LATER, SAME or UNKNOWN")
    prior_loop: bool = Field(
        default=False,
        description="true if this segment shows a life or loop that a LATER segment's text says the character "
        "was reborn, regressed or sent back from",
    )
    reason: str = ""


class OrderResponse(BaseModel):
    items: list[OrderItem] = Field(default_factory=list)


ORDER_SYSTEM = (
    "You order the scenes of one chapter in story time. Scenes are numbered in reading order. For each scene after "
    "the first, say whether it happens EARLIER than, LATER than, or at the SAME time as the scene before it, using "
    "only what the text states (a stated number of years, 'back then', a reborn or regressed character). If it is "
    "not stated, say UNKNOWN. Mark a scene prior_loop only when a later scene's text shows the character was "
    "reborn, regressed or sent back and this scene is the life or loop that ended."
)


def _segment_ranges(chapter: Chapter, cuts: list[SceneCut]) -> list[tuple[int, int]]:
    last = chapter.blocks[-1].index if chapter.blocks else 0
    starts = [0] + [c.block for c in sorted(cuts, key=lambda c: c.block)]
    return [(s, (starts[i + 1] - 1) if i + 1 < len(starts) else last) for i, s in enumerate(starts)]


def _stated_times(chapter: Chapter, lo: int, hi: int, nlp: Any, limit: int = 3) -> list[str]:
    """Sentences carrying a numeric DATE expression; the only place a relation is ever stated."""
    out: list[str] = []
    if nlp is None:
        return out
    for b in chapter.blocks:
        if not (lo <= b.index <= hi) or not b.block_type.is_story_content:
            continue
        doc = nlp(b.text)
        for ent in doc.ents:
            if ent.label_ == "DATE" and any(t.like_num for t in ent):
                out.append(f"[{b.index}] {_clip(b.text, 220)}")
                break
        if len(out) >= limit:
            break
    return out


def resolve_story_order(
    chapter: Chapter,
    cuts: list[SceneCut],
    llm: Any,
    *,
    nlp: Any | None = None,
) -> set[int]:
    """Fill UNKNOWN time relations from the whole chapter; return prior-loop segment indices.

    One call per chapter that has at least one cut with an UNKNOWN relation, so
    the unmarked-cut chapters that need it (RI ch1) pay for it and the linear
    ones do not.
    """
    cuts.sort(key=lambda c: c.block)
    if not cuts or all(c.time_relation is not TimeRelation.UNKNOWN for c in cuts):
        return set()
    nlp = nlp if nlp is not None else load_nlp()
    ranges = _segment_ranges(chapter, cuts)
    blocks = {b.index: b for b in chapter.blocks}
    parts: list[str] = []
    for i, (lo, hi) in enumerate(ranges):
        lead = " ".join(blocks[j].text for j in range(lo, min(hi, lo + 2) + 1) if j in blocks)
        stated = _stated_times(chapter, lo, hi, nlp)
        parts.append(
            f"SCENE {i} (blocks {lo}-{hi}): {_clip(lead, 420)}"
            + ("\n  time statements: " + " | ".join(stated) if stated else "")
        )
    prompt = "\n\n".join(parts) + "\n\nGive the story-time relation of each scene after the first to the scene before it."
    try:
        res = llm.complete(LLMRequest(stage="scene_story_order", prompt=prompt, system=ORDER_SYSTEM, max_tokens=500), OrderResponse)
    except Exception:
        return set()
    prior: set[int] = set()
    for item in res.value.items:
        if item.prior_loop and 0 <= item.segment < len(ranges):
            prior.add(item.segment)
        if 1 <= item.segment <= len(cuts):
            cut = cuts[item.segment - 1]
            rel = _enum_or(TimeRelation, item.relative_to_previous, TimeRelation.UNKNOWN)
            if cut.time_relation is TimeRelation.UNKNOWN:
                cut.time_relation = rel
                if item.reason:
                    cut.evidence.append(f"order: {item.reason[:120]}")
    return prior
