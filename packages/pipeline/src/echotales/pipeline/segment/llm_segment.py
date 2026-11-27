"""Whole-chapter scene segmentation by a local model.

Why this replaces the per-boundary judge (docs/results/SCENE_INDUCTION.md, v1
held-out F1 .40 / .36 / 0 / .20): `implicit.judge_cut` showed the model three
blocks either side of one candidate and asked "is this a cut?". That is the wrong
shape. A scene is a stretch of text with one place and one cast, and the only way
to see where it ends is to read the stretch, so the model is now given the chapter
as numbered blocks and asked to LIST the scenes. RI ch1's cut at block 80 ranked
11th by score and was never judged in v1; a list-the-scenes pass does not depend
on the score ranking at all.

Long blocks are cut to their first `BLOCK_WORDS` words (the opening of a block is
where a place or time change is stated). Chapters longer than `WINDOW` blocks are
read in overlapping windows; a window is told who was on stage when the previous
one ended, and a cut is trusted from the window in which it sits furthest from an
edge, because a model asked about the first blocks of a window has no context.

Nothing here names a novel's convention. Separator lines (`* * *`, a bare `...`,
a one-line place header) are shown to the model as ordinary numbered blocks and
it decides what they mean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from echotales.core.models import Chapter
from echotales.pipeline.llm import LLMRequest
from echotales.pipeline.segment.cuts import CutType, TimeRelation
from pydantic import BaseModel, Field

#: First words of each block shown to the model. 40 keeps a 60-block window near 3.5k tokens, inside the 8k
#: context of an 8 GB card with room for the answer.
BLOCK_WORDS = 40
WINDOW = 60
OVERLAP = 15
#: A cut closer than this to the start of a window is read without context and is judged by the next window.
EDGE_CONTEXT = 4

SEGMENT_SYSTEM = (
    "You split part of a chapter of a translated novel into scenes. Blocks are numbered. A new scene begins where "
    "the place changes, where story time jumps or goes back, or where the people on stage change, with no "
    "continuous action across the point. Continuous action in one place with the same people is ONE scene even "
    "across many paragraphs, dialogue, inner thoughts, pauses, ellipses or a character walking from one room to the "
    "next. Separator lines such as a row of symbols or a one-line heading are not story: a scene starts at the "
    "first story block after them. Do not split a scene because the topic of the conversation changes. "
    "Only call a person present if they are in the place during the scene (speaking, acting, or described there); "
    "people who are only talked about, remembered or thought about are not present. "
    "For each scene give the number of its first block, its place, who is present, how its story time relates to "
    "the scene before it (EARLIER, LATER, SAME, or UNKNOWN when the text shown does not say), and whether it shows a "
    "life or loop that a later scene says the character was reborn, regressed or sent back from. "
    "Scenes are long: a part of 60 blocks usually holds one to three scenes and very often just one, so a new "
    "paragraph, a new speaker, a new topic or a change of mood is NOT a new scene. Start a new scene only when the "
    "place is different from the previous scene's place, or the text itself says time has passed or jumped. "
    "Be conservative: when unsure, keep one scene."
)


class SceneItem(BaseModel):
    start: int = Field(description="number of the first block of the scene")
    place: str = Field(default="", description="where the scene happens, a few words")
    present: list[str] = Field(default_factory=list, description="people physically in the scene")
    time_relation: str = Field(
        default="UNKNOWN", description="story time relative to the scene before it: EARLIER, LATER, SAME or UNKNOWN"
    )
    prior_loop: bool = Field(default=False, description="shows a life or loop a later scene says the character left")


class SceneList(BaseModel):
    scenes: list[SceneItem] = Field(default_factory=list)


@dataclass(slots=True)
class LLMScene:
    start: int
    place: str = ""
    present: list[str] = field(default_factory=list)
    time_relation: TimeRelation = TimeRelation.UNKNOWN
    prior_loop: bool = False
    window: int = 0


def _clip_words(text: str, n: int) -> str:
    w = text.split()
    return " ".join(w[:n]) + (" ..." if len(w) > n else "")


def _relation(value: str) -> TimeRelation:
    try:
        return TimeRelation(value.strip().upper())
    except ValueError:
        return TimeRelation.UNKNOWN


def _windows(indices: list[int]) -> list[tuple[int, int]]:
    """Positions [lo, hi) into the block list; one window when the chapter fits."""
    n = len(indices)
    if n <= WINDOW:
        return [(0, n)]
    out: list[tuple[int, int]] = []
    lo = 0
    step = WINDOW - OVERLAP
    while True:
        hi = min(n, lo + WINDOW)
        out.append((lo, hi))
        if hi >= n:
            return out
        lo += step


def _ask_window(
    chapter: Chapter,
    shown: list[int],
    blocks: dict[int, str],
    llm: Any,
    carry: str,
    first: bool,
) -> list[SceneItem]:
    lines = "\n".join(f"[{i}] {_clip_words(blocks[i], BLOCK_WORDS)}" for i in shown)
    head = (
        f"Chapter blocks {shown[0]} to {shown[-1]}"
        + ("" if first else " (a middle part of a longer chapter; the first scene shown is already in progress)")
        + ".\n"
    )
    if carry:
        head += f"Before block {shown[0]} the scene was: {carry}\n"
    prompt = (
        f"{head}\n{lines}\n\nList the scenes in reading order. The first scene starts at block {shown[0]}. "
        "Each later scene starts at a block in the list above."
    )
    try:
        res = llm.complete(
            LLMRequest(stage="scene_segment", prompt=prompt, system=SEGMENT_SYSTEM, max_tokens=900), SceneList
        )
    except Exception:  # unreachable or malformed answer: this window contributes no cuts, never guessed ones
        return []
    valid = set(shown)
    items = [s for s in res.value.scenes if s.start in valid]
    return sorted(items, key=lambda s: s.start)


def segment_chapter_llm(chapter: Chapter, llm: Any) -> list[LLMScene]:
    """Scenes of a chapter in reading order; the first always starts at the first shown block.

    Blocks of every type are shown except headings, so separators reach the model as text.
    """
    shown_all = [b.index for b in chapter.blocks if b.block_type.name != "HEADING" and b.text.strip()]
    blocks = {b.index: b.text for b in chapter.blocks}
    if len(shown_all) < 2:
        return [LLMScene(start=shown_all[0] if shown_all else 0)]
    wins = _windows(shown_all)
    per_window: list[list[SceneItem]] = []
    carry = ""
    for w, (lo, hi) in enumerate(wins):
        items = _ask_window(chapter, shown_all[lo:hi], blocks, llm, carry, first=w == 0)
        per_window.append(items)
        if items:
            last = items[-1]
            carry = f"{last.place or 'unknown place'}; present: {', '.join(last.present) or 'unknown'}"
    return _reconcile(shown_all, wins, per_window)


def _reconcile(shown: list[int], wins: list[tuple[int, int]], per_window: list[list[SceneItem]]) -> list[LLMScene]:
    pos_of = {b: i for i, b in enumerate(shown)}
    # A window's first scene always "starts" at its first block, so only items[1:] are cut proposals.
    proposals: list[dict[int, SceneItem]] = [{s.start: s for s in items[1:]} for items in per_window]
    first = per_window[0][0] if per_window and per_window[0] else SceneItem(start=shown[0])
    out = [LLMScene(shown[0], first.place, first.present, _relation(first.time_relation), first.prior_loop, 0)]
    for start in sorted({s for d in proposals for s in d}):
        p = pos_of[start]
        covering = [w for w, (lo, hi) in enumerate(wins) if lo <= p < hi]
        # The window that sees the most context on both sides of the point decides it; the others only
        # saw it near an edge, where RI-style unmarked cuts are the first thing a model loses.
        best = max(covering, key=lambda w: min(p - wins[w][0], wins[w][1] - 1 - p))
        hit = next((s for s in proposals[best].values() if abs(pos_of[s.start] - p) <= 1), None)
        if hit is None or pos_of[hit.start] != p:
            continue
        if p - pos_of[out[-1].start] <= 1:
            continue  # the same cut seen at two nearby blocks
        if _same_place(out[-1].place, hit.place) and _relation(hit.time_relation) in (TimeRelation.SAME, TimeRelation.UNKNOWN):
            # qwen3:8b on learn chapters listed one "scene" per beat with an unchanged place (LotM ch2: 17 scenes
            # in 76 blocks). A scene whose place equals the previous one's and whose time is not stated to move is
            # the model contradicting its own definition, so it is not a cut.
            continue
        out.append(LLMScene(start, hit.place, hit.present, _relation(hit.time_relation), hit.prior_loop, best))
    return out


def _same_place(a: str, b: str) -> bool:
    ta, tb = set(a.lower().replace(",", " ").split()), set(b.lower().replace(",", " ").split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5


def cut_type_for(scene: LLMScene) -> CutType:
    if scene.time_relation is TimeRelation.EARLIER:
        return CutType.FLASHBACK
    if scene.time_relation is TimeRelation.LATER:
        return CutType.TIME_JUMP
    return CutType.NEW_SCENE
