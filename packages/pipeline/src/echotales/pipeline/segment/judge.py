"""Pairwise boundary judge for scene cuts (segment v3).

Why this replaces absolute place tags (docs/results/SCENE_INDUCTION.md, v2.1 held-out section): asked "where is this
block", qwen3:8b relabelled one continuous scene ("Qing Mao Mountain" then "Gu Yue Village", RI ch1 blocks 31-78) and
the tag change fired a false cut at 35 while the real cut at 79 (a parallel action, time SAME) never fired. Absolute
labels drift; a comparison of the text before a candidate boundary with the text after it does not have a label to
drift. The model therefore answers three relational questions and the cut decision stays in code, learned on the
learn chapters (scripts/eval/segment_v3_eval.py).

The classic scene definition is continuity of time, place and characters, so each question maps to one axis. The
place question is deliberately lenient: the same people walking on into the next room is NOT a cut (RI ch1: the clan
head walks to his garret at block 75 and the gold keeps the scene), while a cut to other people elsewhere is, even
when time does not move (RI ch1 block 79, "at the very same moment").
"""

from __future__ import annotations

import hashlib
import json
import re
from itertools import pairwise
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from echotales.core.models import Chapter, Mention
from echotales.pipeline.llm import LLMRequest
from echotales.pipeline.segment.discontinuity import (
    Boundary,
    canonical_position,
    is_substantive,
)
from pydantic import BaseModel, Field

PROMPT_VERSION = "j1"
#: Blocks of context on each side of the candidate, and words of each shown; 3 x 2 x 90 words stays well inside 4096.
SIDE_BLOCKS = 3
BLOCK_WORDS = 90
JUDGE_CTX = 4096

JUDGE_SYSTEM = (
    "You decide whether a possible scene break in a translated novel chapter is a real one. You see BEFORE (the "
    "last blocks before the break) and AFTER (the first blocks after it). Answer relative questions about how AFTER "
    "relates to BEFORE; never name an absolute place. "
    "time_continuous: yes when AFTER carries straight on from BEFORE, in the same moment or the next few minutes; "
    "no when there is a jump: time passes or skips ahead, the story goes back to an earlier time, or AFTER happens "
    "at the same moment as BEFORE but somewhere else with other people (parallel action); unclear when you cannot "
    "tell. "
    "same_location: yes when the action is in the same place in both parts, OR the same people simply move on "
    "together into the next room, street or building; no when the narration goes to somewhere else, or to other "
    "people elsewhere. "
    "same_people_in_focus: yes when the same person or group is the one acting or followed in both parts; no when "
    "AFTER centres on different people (people only talked about in BEFORE do not count as being followed). "
    "reason: one short sentence."
)


class JudgeAnswer(BaseModel):
    time_continuous: str = Field(default="unclear", description="yes, no or unclear")
    same_location: str = Field(default="yes", description="yes or no")
    same_people_in_focus: str = Field(default="yes", description="yes or no")
    reason: str = Field(default="", description="one short sentence")


@dataclass(slots=True)
class BoundaryJudgement:
    block: int
    time_continuous: str = "unclear"
    same_location: str = "yes"
    same_people_in_focus: str = "yes"
    reason: str = ""
    sources: list[str] = field(default_factory=list)
    separator: bool = False

    @classmethod
    def from_answer(cls, block: int, a: JudgeAnswer) -> BoundaryJudgement:
        def yn(v: str, default: str, allow: tuple[str, ...]) -> str:
            v = v.strip().lower()
            return v if v in allow else default

        return cls(
            block,
            yn(a.time_continuous, "unclear", ("yes", "no", "unclear")),
            yn(a.same_location, "yes", ("yes", "no")),
            yn(a.same_people_in_focus, "yes", ("yes", "no")),
            a.reason.strip()[:200],
        )


def _clip(text: str, n: int) -> str:
    w = text.split()
    return " ".join(w[:n]) + (" ..." if len(w) > n else "")


def story_blocks(chapter: Chapter) -> list[int]:
    return [b.index for b in chapter.blocks if b.block_type.is_story_content and is_substantive(b.text)]


def people_near(chapter: Chapter, mentions: list[Mention] | None, pos: int, *, limit: int = 6) -> list[str]:
    """Names of people mentioned in the story blocks just before `pos`, most recent first.

    Without mentions (public-domain novels in the eval have none) capitalised words that do not open a sentence stand in.
    """
    idx = [i for i in story_blocks(chapter) if i < pos][-SIDE_BLOCKS - 3 :]
    names: list[str] = []
    seen: set[str] = set()

    def add(n: str) -> None:
        k = re.sub(r"^(?:the|a|an)\s+", "", n.strip().lower())
        if len(k) >= 3 and k not in seen:
            seen.add(k)
            names.append(n.strip())

    by_block: dict[int, list[Mention]] = {}
    for m in mentions or []:
        if m.block_index in idx and (m.entity_label or "").lower() not in {"item", "location", "organization", "category"}:
            by_block.setdefault(m.block_index, []).append(m)
    text = {b.index: b.text for b in chapter.blocks}
    for i in reversed(idx):
        if by_block:
            for m in by_block.get(i, []):
                add(m.text)
        else:
            for mt in re.finditer(r"(?<![.!?“\"]\s)(?<!^)\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)", text.get(i, "")):
                add(mt.group(1))
    return names[:limit]


def build_prompt(chapter: Chapter, pos: int, people: list[str]) -> str:
    story = story_blocks(chapter)
    text = {b.index: b.text for b in chapter.blocks}
    before = [i for i in story if i < pos][-SIDE_BLOCKS:]
    after = [i for i in story if i >= pos][:SIDE_BLOCKS]
    fmt = lambda ids: "\n".join(f"- {_clip(text[i], BLOCK_WORDS)}" for i in ids)  # noqa: E731
    who = ", ".join(people) if people else "not known"
    return (
        f"People named in BEFORE: {who}\n\nBEFORE:\n{fmt(before)}\n\nAFTER:\n{fmt(after)}\n\n"
        "Answer time_continuous, same_location, same_people_in_focus and reason."
    )


class JudgeCache:
    """Answers per (model, prompt version, novel, chapter, boundary), so a rerun costs no GPU time."""

    def __init__(self, root: Path | str, model: str) -> None:
        self.dir = Path(root) / f"{model.replace(':', '_')}_{PROMPT_VERSION}"

    def path(self, novel: str, chapter: float, block: int) -> Path:
        return self.dir / f"{novel}_{chapter:g}_{block}.json"

    def get(self, novel: str, chapter: float, block: int) -> BoundaryJudgement | None:
        p = self.path(novel, chapter, block)
        if not p.exists():
            return None
        try:
            return BoundaryJudgement(**json.loads(p.read_text()))
        except (OSError, ValueError, TypeError):
            return None

    def put(self, novel: str, chapter: float, j: BoundaryJudgement) -> None:
        p = self.path(novel, chapter, j.block)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(j)))


def judge_boundary(
    chapter: Chapter,
    pos: int,
    llm: Any,
    *,
    novel_id: str = "",
    mentions: list[Mention] | None = None,
    cache: JudgeCache | None = None,
) -> BoundaryJudgement:
    if cache is not None:
        hit = cache.get(novel_id, chapter.number, pos)
        if hit is not None:
            return hit
    prompt = build_prompt(chapter, pos, people_near(chapter, mentions, pos))
    try:
        res = llm.complete(LLMRequest(stage="scene_judge", prompt=prompt, system=JUDGE_SYSTEM, max_tokens=200), JudgeAnswer)
        j = BoundaryJudgement.from_answer(pos, res.value)
    except Exception:  # an unreachable or malformed answer must not invent a cut: all-continuous
        return BoundaryJudgement(pos, reason="judge failed")
    if cache is not None:
        cache.put(novel_id, chapter.number, j)
    return j


@dataclass(slots=True)
class CandidateBoundary:
    position: int
    sources: set[str] = field(default_factory=set)
    separator: bool = False


def candidate_boundaries(
    chapter: Chapter,
    boundaries: list[Boundary],
    tags: list[Any] | None = None,
    *,
    disc_rate: float = 0.10,
    extra_cuts: list[int] | None = None,
    spread: int = 1,
) -> list[CandidateBoundary]:
    """Union of every proposer, recall first: the judge and the learned rule do the precision.

    Proposers: `tag` (v2.1 place string changed or a time jump was flagged), `disc` (top `disc_rate` of the
    discontinuity/embedding score), `sep` (a non-story block such as a rule or a lone symbol sits in the gap, a
    structural fact with no word list) and `conv` (a convention induced on the learn chapters).
    """
    out: dict[int, CandidateBoundary] = {}

    def add(pos: int, src: str, sep: bool = False) -> None:
        pos = canonical_position(chapter, pos)
        c = out.setdefault(pos, CandidateBoundary(pos))
        c.sources.add(src)
        c.separator = c.separator or sep

    story = set(story_blocks(chapter))
    first = min(story) if story else 0
    for b in boundaries:
        if b.position == first:
            continue
        if any(m for m in b.marker_blocks):
            add(b.position, "sep", True)
    if boundaries:
        k = max(2, round(disc_rate * len(boundaries)))
        for b in sorted(boundaries, key=lambda b: -b.score)[:k]:
            add(b.position, "disc")
    if tags:
        for a, b in pairwise(tags):
            norm = lambda s: " ".join("".join(ch if ch.isalpha() else " " for ch in s.lower()).split())  # noqa: E731
            if norm(a.place) != norm(b.place) or b.time_shift.value != "SAME":
                add(b.block, "tag")
    for pos in extra_cuts or []:
        add(pos, "conv")
    # Each proposer names the block where IT first notices the change; measured on the learn chapters, 7 of 9 missed
    # gold cuts had a candidate one or two blocks away (tags notice a new place late, the score peaks early), and
    # gold needs the exact block. So the neighbours in reading order are judged too, and `decide_cuts` keeps the
    # one where the judge is most sure (the answers peak at the true boundary and blur one block either side).
    rank = {b: i for i, b in enumerate(sorted(story))}
    order = sorted(story)
    merged: dict[int, CandidateBoundary] = {}
    for c in sorted(out.values(), key=lambda c: c.position):
        r = rank.get(c.position)
        if r is None:
            continue
        for d in range(-spread, spread + 1):
            if 0 <= r + d < len(order) and order[r + d] != first:
                n = merged.setdefault(order[r + d], CandidateBoundary(order[r + d]))
                n.sources |= c.sources if d == 0 else {"near"}
                n.separator = n.separator or (c.separator and d == 0)
    return sorted(merged.values(), key=lambda c: c.position)


@dataclass(slots=True)
class CutRule:
    """One interpretable rule over the judge answers, chosen on the learn split (see RULES)."""

    name: str
    use_separator: bool
    time_no: bool
    place_and_people: bool
    place_alone: bool = False
    min_gap: int = 1

    def fires(self, j: BoundaryJudgement) -> bool:
        if self.use_separator and j.separator:
            return True
        if self.time_no and j.time_continuous == "no":
            return True
        if self.place_and_people and j.same_location == "no" and j.same_people_in_focus == "no":
            return True
        return bool(self.place_alone and j.same_location == "no")


def rule_grid() -> list[CutRule]:
    out = []
    for sep in (True, False):
        for t in (True, False):
            for pp in (True, False):
                for pa in (True, False):
                    if not (t or pp or pa):
                        continue
                    if pa and pp:
                        continue  # place_alone already contains place-and-people
                    for gap in (1, 3, 5):
                        name = "+".join(n for n, on in (("sep", sep), ("time_no", t), ("place&people", pp), ("place", pa)) if on)
                        out.append(CutRule(name, sep, t, pp, pa, gap))
    return out


def strength(j: BoundaryJudgement) -> int:
    """How many axes of continuity the judge says are broken (a separator counts double)."""
    return (2 if j.separator else 0) + (j.time_continuous == "no") + (j.same_location == "no") + (j.same_people_in_focus == "no")


def decide_cuts(judgements: list[BoundaryJudgement], rule: CutRule, chapter: Chapter) -> list[int]:
    """One cut per run of adjacent firing boundaries (its most clearly broken one), then `min_gap` spacing."""
    story = story_blocks(chapter)
    rank = {b: i for i, b in enumerate(story)}
    fired = sorted((j for j in judgements if rule.fires(j)), key=lambda j: rank.get(j.block, 0))
    clusters: list[list[BoundaryJudgement]] = []
    for j in fired:
        if clusters and rank.get(j.block, 0) - rank.get(clusters[-1][-1].block, 0) <= 1:
            clusters[-1].append(j)
        else:
            clusters.append([j])
    # Ties go to the earliest block: the answers blur one block either side of the true boundary, never before it.
    peaks = [max(c, key=lambda j: (strength(j), -rank.get(j.block, 0))) for c in clusters]
    kept: list[int] = []
    for j in peaks:
        r = rank.get(j.block, 0)
        if all(abs(r - rank.get(o, 0)) >= rule.min_gap for o in kept):
            kept.append(j.block)
    return kept


def digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
