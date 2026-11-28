"""Whole-chapter outline segmentation (segment v4).

Why this replaces the per-boundary judge (docs/results/SCENE_INDUCTION.md, v3): with a 3-block window the 8B judge
said "different location" at almost every boundary it saw (held-out precision .06, 186 false cuts), because a window
has no idea that real cuts are rare (0-3 per chapter). The model cannot know what is unusual without seeing the
chapter, so v4 shows it all of it:

1. `outline_chapter` compresses every story block to one short line (who acts or speaks, where if stated, when if
   stated), in chunks that fit a 4096 context. The lines are cached per (model, novel, chapter).
2. `segment_outline` gives the model the whole numbered outline in one call and asks for the scene starts only.
   The answer is validated in code (blocks in range, sorted, not the first).

Nothing here names a novel's convention; separators and cast continuity are combined in `cast.py`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from echotales.core.models import Chapter, Mention
from echotales.pipeline.llm import LLMRequest
from echotales.pipeline.segment.judge import story_blocks
from pydantic import BaseModel, Field

OUTLINE_VERSION = "o1"
SEGMENT_VERSION = "s3"
#: Words of each block shown to the outline model, and the per-call budget (words of block text, and blocks).
BLOCK_WORDS = 50
CHUNK_WORDS = 800
CHUNK_BLOCKS = 24
#: Estimated token budget of the numbered outline in the segmentation call; the 4096 context also holds the
#: instructions, the schema and the answer.
OUTLINE_TOKEN_BUDGET = 2600
#: Opening words of each block kept in the outline line. Narration states a change in its first words ("At the very
#: same moment,", "The next morning") and the compressed who/where/when line loses them. 0 turns it off.
LEAD_WORDS = 7

OUTLINE_SYSTEM = (
    "You condense a chapter of a translated novel into one very short line per numbered block. For every block give "
    "three fields. who: the people who act or speak in that block, by name (use the names listed after the block "
    "when they fit); people only talked about, remembered or thought about do not count; empty when no person acts "
    "or speaks. where: the place, only when the block states it or moves to a new one, otherwise empty. when: a time "
    "expression, only when the block states one (for example 'that night', 'three days later', '500 years ago'), "
    "otherwise empty. Use names and 1-4 words, never sentences. Answer every block number you are given, in order."
)

SEGMENT_SYSTEM = (
    "You mark where the scenes of a novel chapter start. You see one numbered line per block of the chapter: who "
    "acts or speaks, the place if stated, the time if stated. Scenes are few: a typical chapter has one to three "
    "scene changes, and many have none. A scene changes only when the narration leaves the current place AND the "
    "current people, or jumps in time. The same people moving on into another room, street or building is NOT a "
    "change. A new speaker, a new topic, a change of mood, a flashback inside a conversation or a missing 'where' "
    "is NOT a change. A parallel action 'at the same moment' somewhere else with other people IS a change, and so "
    "is a stated jump such as 'the next morning' or 'three days later'. When unsure, do not mark a change. "
    "Answer with the block number where each new scene starts (never the first block), a confidence from 1 to 5 "
    "(5: the narration clearly leaves the place and the people, or states a jump in time; 3: probably; 1: a guess) "
    "and a one-line reason. Most chapters are ONE scene or two: when nothing in the outline clearly leaves the "
    "place and the people, answer an empty list. Never mark a start just because the speaker changes."
)


class OutlineItem(BaseModel):
    n: int = Field(description="block number")
    who: str = Field(default="", description="names of people who act or speak, comma separated")
    where: str = Field(default="", description="place, only if stated")
    when: str = Field(default="", description="time expression, only if stated")


class OutlineAnswer(BaseModel):
    lines: list[OutlineItem] = Field(default_factory=list)


class SceneStart(BaseModel):
    block: int = Field(description="number of the first block of a new scene")
    confidence: int = Field(default=3, description="1 (a guess) to 5 (certain)")
    reason: str = Field(default="", description="one short sentence")


class SegmentAnswer(BaseModel):
    scene_starts: list[SceneStart] = Field(default_factory=list)


@dataclass(slots=True)
class OutlineLine:
    block: int
    who: str = ""
    where: str = ""
    when: str = ""
    #: First words of the block itself, filled by `outline_chapter` (not by the model).
    lead: str = ""


def _clip(text: str, n: int) -> str:
    w = text.split()
    return " ".join(w[:n]) + (" ..." if len(w) > n else "")


def name_hints(
    chapter: Chapter,
    mentions: list[Mention] | None,
    spans: list[Any] | None = None,
    labels: dict[str, str] | None = None,
    *,
    limit: int = 4,
) -> dict[int, list[str]]:
    """Resolved names per block from the graph (speaker attributions first, then person mentions)."""
    labels = labels or {}
    out: dict[int, list[str]] = {}

    def add(b: int, name: str) -> None:
        name = name.strip()
        lst = out.setdefault(b, [])
        if name and name.lower() not in {x.lower() for x in lst} and len(lst) < limit:
            lst.append(name)

    for sp in spans or []:
        sid = getattr(sp, "speaker_self_id", None)
        if sid and sid in labels:
            add(sp.block_index, labels[sid])
    for m in mentions or []:
        if (m.entity_label or "").lower() in {"item", "location", "organization", "category"}:
            continue
        if m.reference_mode.value in ("DIALOGUE_REFERENCE", "INNER_THOUGHT_REFERENCE"):
            continue
        add(m.block_index, labels.get(m.target_id or "", m.text))
    return out


def _chunks(blocks: list[int], text: dict[int, str]) -> list[list[int]]:
    out: list[list[int]] = []
    cur: list[int] = []
    words = 0
    for b in blocks:
        w = min(len(text[b].split()), BLOCK_WORDS)
        if cur and (words + w > CHUNK_WORDS or len(cur) >= CHUNK_BLOCKS):
            out.append(cur)
            cur, words = [], 0
        cur.append(b)
        words += w
    if cur:
        out.append(cur)
    return out


class OutlineCache:
    """Outline lines per (model, prompt version, novel, chapter), so a rerun costs no GPU time."""

    def __init__(self, root: Path | str, model: str) -> None:
        self.dir = Path(root) / f"{model.replace(':', '_')}_{OUTLINE_VERSION}"

    def path(self, novel: str, chapter: float) -> Path:
        return self.dir / f"{novel}_{chapter:g}.json"

    def get(self, novel: str, chapter: float) -> list[OutlineLine] | None:
        p = self.path(novel, chapter)
        if not p.exists():
            return None
        try:
            return [OutlineLine(**d) for d in json.loads(p.read_text())]
        except (OSError, ValueError, TypeError):
            return None

    def put(self, novel: str, chapter: float, lines: list[OutlineLine]) -> None:
        p = self.path(novel, chapter)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([{k: v for k, v in asdict(x).items() if k != "lead"} for x in lines]))


def outline_chapter(
    chapter: Chapter,
    llm: Any,
    *,
    novel_id: str = "",
    hints: dict[int, list[str]] | None = None,
    cache: OutlineCache | None = None,
) -> list[OutlineLine]:
    """One short line per story block. A chunk the model fails on yields empty lines, never invented ones."""
    if cache is not None:
        hit = cache.get(novel_id, chapter.number)
        if hit is not None:
            return fill_lead(hit, chapter)
    text = {b.index: b.text for b in chapter.blocks}
    blocks = story_blocks(chapter)
    got: dict[int, OutlineLine] = {}
    ok = True
    for chunk in _chunks(blocks, text):
        body = "\n".join(
            f"[{b}] {_clip(text[b], BLOCK_WORDS)}" + (f"  (names: {'; '.join(hints[b])})" if hints and hints.get(b) else "")
            for b in chunk
        )
        prompt = f"{body}\n\nGive who, where and when for each of the block numbers {chunk[0]} to {chunk[-1]} listed above."
        try:
            res = llm.complete(LLMRequest(stage="scene_outline", prompt=prompt, system=OUTLINE_SYSTEM, max_tokens=60 * len(chunk)), OutlineAnswer)
        except Exception:
            ok = False
            continue
        for it in res.value.lines:
            if it.n in chunk and it.n not in got:
                got[it.n] = OutlineLine(it.n, _short(it.who, 40), _short(it.where, 30), _short(it.when, 30))
    lines = [got.get(b, OutlineLine(b)) for b in blocks]
    fill_lead(lines, chapter)
    if cache is not None and ok:
        cache.put(novel_id, chapter.number, lines)
    return lines


def fill_lead(lines: list[OutlineLine], chapter: Chapter) -> list[OutlineLine]:
    text = {b.index: b.text for b in chapter.blocks}
    for ln in lines:
        ln.lead = " ".join(text.get(ln.block, "").split()[:LEAD_WORDS])
    return lines


def _short(s: str, n: int) -> str:
    s = " ".join(s.split())
    return "" if s.lower() in {"none", "n/a", "unknown", "-", "null", "not stated"} else s[:n]


def _est_tokens(s: str) -> int:
    return int(len(s) / 3.2) + 1


def outline_prompt(lines: list[OutlineLine], lead_words: int | None = None) -> str:
    """The whole numbered outline. Over budget (very long chapters) the opening words go first, then fields, then runs."""
    lead_words = LEAD_WORDS if lead_words is None else lead_words
    for lead_n, who_n, keep_when in ((lead_words, 3, True), (0, 3, True), (0, 2, True), (0, 2, False)):
        rows = []
        for ln in lines:
            who = ", ".join(ln.who.split(",")[:who_n]).strip()
            lead = " ".join(ln.lead.split()[:lead_n])
            parts = [x for x in (who, ln.where, ln.when if keep_when else "") if x]
            rows.append(f"{ln.block} | " + (f'"{lead}" ' if lead else "") + ("| " if lead and parts else "") + " | ".join(parts))
        if _est_tokens("\n".join(rows)) <= OUTLINE_TOKEN_BUDGET:
            break
    else:
        rows = _merge_runs(lines)
    return "\n".join(rows)


def _merge_runs(lines: list[OutlineLine]) -> list[str]:
    rows: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and (lines[j + 1].who, lines[j + 1].where, lines[j + 1].when) == (lines[i].who, lines[i].where, lines[i].when):
            j += 1
        lab = f"{lines[i].block}" + (f"-{lines[j].block}" if j > i else "")
        rows.append(f"{lab} | " + " | ".join(x for x in (", ".join(lines[i].who.split(",")[:2]), lines[i].where, lines[i].when) if x))
        i = j + 1
    return rows


def validate_starts(starts: list[SceneStart], lines: list[OutlineLine]) -> list[tuple[int, str, int]]:
    """(block, reason, confidence) of scene starts that are real outline blocks (not the first), sorted and unique."""
    valid = {ln.block for ln in lines}
    if not valid:
        return []
    first = min(valid)
    out: dict[int, tuple[str, int]] = {}
    for s in starts:
        if s.block in valid and s.block != first and s.block not in out:
            out[s.block] = (s.reason.strip()[:160], min(5, max(1, s.confidence)))
    return [(b, r, c) for b, (r, c) in sorted(out.items())]


class SegmentCache:
    def __init__(self, root: Path | str, model: str) -> None:
        self.dir = Path(root) / f"{model.replace(':', '_')}_{OUTLINE_VERSION}_{SEGMENT_VERSION}_l{LEAD_WORDS}"

    def path(self, novel: str, chapter: float) -> Path:
        return self.dir / f"{novel}_{chapter:g}.json"

    def get(self, novel: str, chapter: float) -> list[tuple[int, str, int]] | None:
        p = self.path(novel, chapter)
        if not p.exists():
            return None
        try:
            return [(int(a), str(b), int(c)) for a, b, c in json.loads(p.read_text())]
        except (OSError, ValueError, TypeError):
            return None

    def put(self, novel: str, chapter: float, starts: list[tuple[int, str, int]]) -> None:
        p = self.path(novel, chapter)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(starts))


def segment_outline(
    chapter: Chapter,
    lines: list[OutlineLine],
    llm: Any,
    *,
    novel_id: str = "",
    cache: SegmentCache | None = None,
) -> list[tuple[int, str, int]]:
    """(scene start block, reason, confidence) from one call over the whole outline; [] means one scene."""
    if cache is not None:
        hit = cache.get(novel_id, chapter.number)
        if hit is not None:
            return hit
    if len(lines) < 4:
        return []
    prompt = f"CHAPTER OUTLINE (block | who | where | when):\n{outline_prompt(lines)}\n\nList the blocks where a new scene starts."
    try:
        res = llm.complete(LLMRequest(stage="scene_segment", prompt=prompt, system=SEGMENT_SYSTEM, max_tokens=300), SegmentAnswer)
    except Exception:  # an unreachable or malformed answer must not invent a cut
        return []
    starts = validate_starts(res.value.scene_starts, lines)
    if cache is not None:
        cache.put(novel_id, chapter.number, starts)
    return starts

