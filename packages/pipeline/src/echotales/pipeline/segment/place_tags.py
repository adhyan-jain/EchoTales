"""Scene cuts from per-block place and time tags (segment v2.1).

Why this replaces "list the scenes" (docs/results/SCENE_INDUCTION.md, v2 HANDOFF): asked for scenes, qwen3:8b
proposed one per beat (unfiltered precision .03-.08 on the learn chapters) because "scene" is a fuzzy word to a
7-9B model and every new speaker or topic looks like one. A scene here is a change of PLACE or a jump in TIME and
nothing else, so the model is asked a narrower, local question for each block: where is this, and did time move?
The cut decision then lives in code, where it can be tuned on the learn chapters and capped by a per-novel prior,
instead of inside a prompt.

The model must reuse the previous place string while the place is unchanged (it is shown it), so noise is a
differently-worded name for the same room. Cuts are therefore scored by the distance between the place strings
just before and just after a block (embedding, or token overlap when no embedder is up), averaged over a few
blocks on each side so a one-block aside does not register.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from echotales.core.models import Chapter
from echotales.pipeline.llm import LLMRequest
from echotales.pipeline.segment.cuts import TimeRelation
from echotales.pipeline.segment.discontinuity import canonical_position
from echotales.pipeline.segment.embed import cosine_distance
from echotales.pipeline.segment.llm_segment import LLMScene
from pydantic import BaseModel, Field

#: Blocks tagged per request, and words of each block shown. 25 x 35 words stays inside a 4096-token context
#: (gemma2:9b at 8192 spills 21% to CPU on the 8 GB card; qwen3:8b and gemma2:9b both stay on GPU at 4096).
TAG_WINDOW = 25
TAG_WORDS = 35
TAG_CTX = 4096

#: Bumps when TAG_SYSTEM changes; the tag caches in scripts/eval are keyed by it so old tags never score a new prompt.
PROMPT_VERSION = "p4"

# p1 measured on RI ch1 (owner gold cuts {31, 79}): blocks 0-30 got place "unknown", the cut at 79 was missed because
# the model kept the region ("same mountain") while the action moved to another room at the same moment, and many
# blocks were marked LATER with no stated jump. Each rule below answers one of those failures, in general terms.
TAG_SYSTEM = (
    "You label the blocks of a translated novel chapter with WHERE each block happens and whether STORY TIME "
    "moved. For every numbered block give: place, a short noun phrase naming the ROOM or BUILDING or street where "
    "the action is, never a region (not 'the mountain', 'the city', 'the country': say which room or building in "
    "it); time_shift relative to the block before it; and time_anchor, a few words naming when it is, or empty. "
    "Always give a concrete place: when the text does not name one, infer it from what the characters are doing "
    "and holding (a bed, a table, a road), never 'unknown'. "
    "PLACE RULES. While the action stays in one room, repeat the previous place string EXACTLY; do not reword it. "
    "Dialogue or thought keeps the place of the block before it. Two rooms or buildings in the same town, "
    "estate or mountain are two places. If the text cuts to somewhere else where something happens at the same "
    "time (a phrase like 'at that very moment', 'at the same time', 'meanwhile', 'elsewhere'), that is a new "
    "place: name where THAT person or group is (their own room), not the place of the block before, even if "
    "they look at the same thing or the surroundings seem close. If it introduces a person by description only "
    "(a pair of eyes, a figure, a voice) and the block before centred on someone else, that is a new place. Remembered, imagined or described places are not the place of the "
    "block unless the action is shown there. A one-line heading or separator keeps the place before it. Do not "
    "change the place because the topic, mood or speaker changed. "
    "TIME RULES. time_shift is SAME unless the text itself states or clearly implies a jump: LATER when it says "
    "time has passed or skips ahead (a new day, 'after a while', a season or years later); EARLIER when the text "
    "goes back in time and shows it as action (a flashback, a past life, 'years ago'). Walking, talking, "
    "thinking and the next few minutes are SAME. When in doubt answer SAME."
)


class BlockTag(BaseModel):
    i: int = Field(description="block number")
    place: str = Field(default="", description="short location phrase; repeat the previous one if unchanged")
    time_shift: str = Field(default="SAME", description="SAME, LATER or EARLIER relative to the previous block")
    time_anchor: str = Field(default="", description="a few words saying when, or empty")


class BlockTagList(BaseModel):
    tags: list[BlockTag] = Field(default_factory=list)


@dataclass(slots=True)
class TaggedBlock:
    block: int
    place: str
    time_shift: TimeRelation = TimeRelation.SAME
    time_anchor: str = ""


def _clip(text: str, n: int) -> str:
    w = text.split()
    return " ".join(w[:n]) + (" ..." if len(w) > n else "")


def _shift(value: str) -> TimeRelation:
    try:
        r = TimeRelation(value.strip().upper())
    except ValueError:
        return TimeRelation.SAME
    return r if r in (TimeRelation.LATER, TimeRelation.EARLIER) else TimeRelation.SAME


def tag_chapter(chapter: Chapter, llm: Any) -> list[TaggedBlock]:
    """One place/time tag per non-heading block, windows of TAG_WINDOW carrying the last place forward."""
    shown = [b.index for b in chapter.blocks if b.block_type.name != "HEADING" and b.text.strip()]
    text = {b.index: b.text for b in chapter.blocks}
    out: list[TaggedBlock] = []
    prev_place, prev_anchor = "", ""
    for lo in range(0, len(shown), TAG_WINDOW):
        win = shown[lo : lo + TAG_WINDOW]
        lines = "\n".join(f"[{i}] {_clip(text[i], TAG_WORDS)}" for i in win)
        head = (
            (
                f"The previous block's place was: {prev_place}"
                + (f"; time: {prev_anchor}" if prev_anchor else "")
                + ".\n"
                if prev_place
                # p2 measured: "unknown (this is the start...)" was copied verbatim onto blocks 0-30 of RI ch1.
                else "This is the start of the chapter: name the place from the text itself.\n"
            )
        )
        prompt = f"{head}\n{lines}\n\nGive one entry for every block number above, in order."
        got: dict[int, BlockTag] = {}
        try:
            res = llm.complete(
                LLMRequest(stage="scene_tag", prompt=prompt, system=TAG_SYSTEM, max_tokens=1600), BlockTagList
            )
            got = {t.i: t for t in res.value.tags if t.i in set(win)}
        except Exception:  # unreachable or malformed answer: those blocks inherit the previous place, no cut is invented
            got = {}
        for i in win:
            t = got.get(i)
            place = (t.place.strip() if t and t.place.strip() else prev_place) or "unknown"
            out.append(
                TaggedBlock(i, place, _shift(t.time_shift) if t else TimeRelation.SAME, t.time_anchor.strip() if t else "")
            )
            prev_place = place
            if t and t.time_anchor.strip():
                prev_anchor = t.time_anchor.strip()
    return out


@dataclass(slots=True)
class PlaceCutParams:
    """Tuned on the learn chapters only (scripts/eval/segment_v2_eval.py)."""

    threshold: float = 0.35
    #: Score given to a block the model marked as a time jump, as a fraction of a full place change.
    time_weight: float = 0.6
    #: Blocks on each side averaged when comparing places.
    side: int = 3
    #: Cuts closer than this to the previous kept cut are dropped (learned scene-length prior).
    min_gap: int = 4
    #: Cap on cuts for a chapter of `n` blocks: ceil(cap_rate * n); None disables.
    cap_rate: float | None = None
    cap_min: int = 1
    #: "Both" rule: cut only where the place string changed AND the model flagged a time jump. Measured on the learn
    #: chapters (qwen3:8b, tags p4): place change alone is 0 hits in 25 candidates (a walk through a street and a
    #: bakery changes the place every few blocks and is one scene), a time flag alone 2 of 22, both together 11 of 31.
    both: bool = True


@dataclass(slots=True)
class PlaceCandidate:
    block: int
    score: float
    place_distance: float
    time_jump: bool
    index: int = 0


def _distance_fn(places: list[str], embedder: Any | None):
    """Pairwise distance between place strings: embedding cosine, else token-set Jaccard distance."""
    vecs: dict[str, list[float]] | None = None
    if embedder is not None:
        uniq = sorted(set(places))
        got = embedder.embed(uniq)
        if got is not None:
            vecs = dict(zip(uniq, got, strict=True))
    if vecs is not None:
        scale = 1.0

        def emb(a: str, b: str) -> float:
            return 0.0 if a == b else min(1.0, cosine_distance(vecs[a], vecs[b]) * scale)

        return emb

    def toks(s: str) -> set[str]:
        return set(s.lower().replace(",", " ").replace("'s", "").split())

    def jac(a: str, b: str) -> float:
        if a == b:
            return 0.0
        ta, tb = toks(a), toks(b)
        return 1.0 - len(ta & tb) / len(ta | tb) if ta | tb else 0.0

    return jac


def place_candidates(tags: list[TaggedBlock], embedder: Any | None = None, *, side: int = 3) -> list[PlaceCandidate]:
    """Every block after the first, with the place distance across it; peaks are picked later by `select_cuts`."""
    n = len(tags)
    if n < 2:
        return []
    dist = _distance_fn([t.place for t in tags], embedder)
    out: list[PlaceCandidate] = []
    for j in range(1, n):
        left = tags[max(0, j - side) : j]
        right = tags[j : j + side]
        d = sum(dist(a.place, b.place) for a in left for b in right) / (len(left) * len(right))
        out.append(PlaceCandidate(tags[j].block, d, d, tags[j].time_shift is not TimeRelation.SAME, j))
    return out


def _norm_place(place: str) -> str:
    """Letters and single spaces only: the model sometimes re-emits a place with a stray comma ('his, chair')."""
    return " ".join("".join(ch if ch.isalpha() else " " for ch in place.lower()).split())


def rule_cuts(chapter: Chapter, tags: list[TaggedBlock], p: PlaceCutParams) -> list[PlaceCandidate]:
    """Blocks where the place changed and a time jump was flagged, spaced by `min_gap` (first one wins)."""
    out: list[PlaceCandidate] = []
    for j in range(1, len(tags)):
        a, b = tags[j - 1], tags[j]
        if _norm_place(a.place) == _norm_place(b.place) or b.time_shift is TimeRelation.SAME:
            continue
        pos = canonical_position(chapter, b.block)
        if all(abs(pos - canonical_position(chapter, o.block)) >= p.min_gap for o in out):
            out.append(PlaceCandidate(b.block, 1.0, 1.0, True, j))
    return out


def select_cuts(chapter: Chapter, cands: list[PlaceCandidate], p: PlaceCutParams, n_blocks: int) -> list[PlaceCandidate]:
    """Peaks of the combined place/time score above the threshold, spaced and capped by the learned priors."""
    scored = [
        PlaceCandidate(c.block, max(c.place_distance, p.time_weight if c.time_jump else 0.0), c.place_distance, c.time_jump, c.index)
        for c in cands
    ]
    peaks: list[PlaceCandidate] = []
    for k, c in enumerate(scored):
        near = scored[max(0, k - 2) : k + 3]
        # A plateau (equal score on adjacent blocks) keeps its first block, where the new place is first said.
        if c.score > 0 and c.score >= max(x.score for x in near) and not (k and scored[k - 1].score == c.score):
            peaks.append(c)
    keep = [c for c in peaks if c.score >= p.threshold]
    if p.cap_rate is not None:
        keep = sorted(keep, key=lambda c: -c.score)[: max(p.cap_min, math.ceil(p.cap_rate * n_blocks))]
    out: list[PlaceCandidate] = []
    for c in sorted(keep, key=lambda c: -c.score):
        pos = canonical_position(chapter, c.block)
        if all(abs(pos - canonical_position(chapter, o.block)) >= p.min_gap for o in out):
            out.append(c)
    return sorted(out, key=lambda c: c.block)


def scenes_from_tags(
    chapter: Chapter,
    tags: list[TaggedBlock],
    params: PlaceCutParams,
    embedder: Any | None = None,
) -> list[LLMScene]:
    """The model's tags as scenes (first scene at the first block), so downstream code is unchanged."""
    if not tags:
        return [LLMScene(start=0)]
    if params.both:
        chosen = rule_cuts(chapter, tags, params)
    else:
        chosen = select_cuts(chapter, place_candidates(tags, embedder, side=params.side), params, len(tags))
    place_at = {t.block: t for t in tags}
    scenes = [LLMScene(start=tags[0].block, place=tags[0].place)]
    for c in chosen:
        t = place_at[c.block]
        scenes.append(LLMScene(start=c.block, place=t.place, time_relation=t.time_shift))
    return scenes
