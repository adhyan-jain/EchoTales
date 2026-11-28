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


@dataclass(slots=True)
class OutlineOptions:
    """How the whole-chapter segmentation call runs (segment v5). The defaults are the v4 call."""

    #: Let the model reason before answering; the call then goes out without a schema `format` (see llm/ollama.py).
    think: bool = False
    #: Output cap; with `think` it must also hold the reasoning trace (measured 3000-6500 tokens on qwen3:8b).
    max_tokens: int = 300
    #: A different (usually larger) model for this call only; the outline lines still come from the chapter model.
    segment_llm: Any | None = None
    #: Opening words of every block shown next to its outline line (0: the outline alone, as in v4). Needs a context
    #: of 8192 or more; the words per block shrink until the prompt fits `RAW_TOKEN_BUDGET`.
    raw_words: int = 0
    #: Cache suffix separating configurations that share one outline cache.
    tag: str = ""
    #: v5b: after fusion, ask the (4096-context, non-thinking) chapter model where each cut sits within one block. Off: on the
    #: 34 learn chapters it moved none of 13 cuts and kept the RI ch1 cut one block late (SCENE_INDUCTION.md, v5b).
    refine: bool = False


#: Context the segmentation model must be served with for `v5_options`: a prompt of up to ~5.5k tokens plus a reasoning
#: trace of 3-6.5k tokens (qwen3:8b, 100% GPU at 12288 on the 8 GB development card, `ollama ps`).
V5_NUM_CTX = 12288


def v5_options(segment_llm: Any | None = None) -> OutlineOptions:
    """The segment v5 call, chosen on the learn split (docs/results/SCENE_INDUCTION.md, v5): thinking on, the opening 40
    words of every block next to its outline line. The provider behind the segmentation model needs `num_ctx=V5_NUM_CTX`."""
    return OutlineOptions(think=True, max_tokens=6500, segment_llm=segment_llm, raw_words=40, tag="think_raw40")


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


#: Token budget of the outline-plus-text prompt (a context of 8192 also holds the instructions and the answer).
RAW_TOKEN_BUDGET = 4800


def raw_outline_prompt(lines: list[OutlineLine], chapter: Chapter, raw_words: int) -> str:
    """Outline rows with the opening words of each block's own text, so the model reads the prose and not only the summary.

    The summary line loses the narration's own markers ("the next morning", "in the meantime"); `LEAD_WORDS` kept 7 of them
    and v4's cut-off there was the context. The words per block shrink (never the rows) until the prompt fits the budget.
    """
    text = {b.index: b.text for b in chapter.blocks}
    for words in range(raw_words, 6, -4):
        rows = []
        for ln in lines:
            fields = " | ".join(x for x in (", ".join(ln.who.split(",")[:3]).strip(), ln.where, ln.when) if x)
            body = _clip(text.get(ln.block, ""), words)
            rows.append(f"[{ln.block}] {body}" + (f"  <{fields}>" if fields else ""))
        if _est_tokens("\n".join(rows)) <= RAW_TOKEN_BUDGET:
            break
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
    def __init__(self, root: Path | str, model: str, tag: str = "") -> None:
        # `tag` separates segmentation configurations (thinking on, raw text shown) that share one outline cache.
        self.dir = Path(root) / (f"{model.replace(':', '_')}_{OUTLINE_VERSION}_{SEGMENT_VERSION}_l{LEAD_WORDS}" + (f"_{tag}" if tag else ""))

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
    think: bool = False,
    max_tokens: int = 300,
    raw_words: int = 0,
) -> list[tuple[int, str, int]]:
    """(scene start block, reason, confidence) from one call over the whole outline; [] means one scene.

    `think` lets the model reason before it answers (v5, this call only); `max_tokens` must then also hold the trace,
    otherwise the cap cuts the model off before the JSON and the chapter silently gets no cut.
    """
    if cache is not None:
        hit = cache.get(novel_id, chapter.number)
        if hit is not None:
            return hit
    if len(lines) < 4:
        return []
    if raw_words:
        prompt = f"CHAPTER (block number, opening words of the block, then <who | where | when>):\n{raw_outline_prompt(lines, chapter, raw_words)}\n\nList the blocks where a new scene starts."
    else:
        prompt = f"CHAPTER OUTLINE (block | who | where | when):\n{outline_prompt(lines)}\n\nList the blocks where a new scene starts."
    try:
        req = LLMRequest(stage="scene_segment", prompt=prompt, system=SEGMENT_SYSTEM, max_tokens=max_tokens, extra={"think": True} if think else {})
        res = llm.complete(req, SegmentAnswer)
    except Exception:  # an unreachable or malformed answer must not invent a cut
        return []
    starts = validate_starts(res.value.scene_starts, lines)
    if cache is not None:
        cache.put(novel_id, chapter.number, starts)
    return starts



REFINE_SYSTEM = (
    "You place the exact first block of a new scene in a translated novel. You see four consecutive numbered blocks; "
    "the block marked CUT is where a scene change was first placed. For each of two blocks say whether it CONTINUES "
    "the block just before it or turns to something NEW. A block turns to something new when its narration is about "
    "other people, another place or another time than the block before, or looks at the same things from another "
    "viewpoint, even if it does not name the person yet. It continues when it is still about the same people at the "
    "same place and time, for example the next line of the same conversation."
)


class RefineAnswer(BaseModel):
    before_cut: str = Field(default="continues", description="'new' or 'continues': the block just before CUT, compared with the block before it")
    at_cut: str = Field(default="new", description="'new' or 'continues': the block marked CUT, compared with the block before it")


def refine_cut(chapter: Chapter, cut: int, llm: Any, *, words: int = 70) -> int:
    """Move one scene start by at most one block (segment v5b); the cut itself if the call fails or the neighbours are missing.

    RI ch1: the whole-chapter call places the start at block 80 where the owner gold has 79. Block 79 opens the new scene
    without naming the person and block 80 names them, so a cut placed on the first block that names the person is one
    block late. Each of the two neighbouring blocks is compared with its own predecessor (no thinking, 4 blocks): the
    scene starts at the first block that turns to something new. When neither does, the cut sat one block early.
    """
    order = story_blocks(chapter)
    if cut not in order:
        return cut
    r = order.index(cut)
    if r < 2 or r + 1 >= len(order):
        return cut
    text = {b.index: b.text for b in chapter.blocks}
    ids = order[r - 2 : r + 2]
    body = "\n".join(f"[{b}]{' CUT' if b == cut else ''} {_clip(text[b], words)}" for b in ids)
    prompt = (
        f"{body}\n\nCompared with block {order[r - 2]}, does block {order[r - 1]} turn to something NEW or CONTINUE (before_cut)? "
        f"Compared with block {order[r - 1]}, does block {cut} turn to something new or continue (at_cut)?"
    )
    try:
        v = llm.complete(LLMRequest(stage="scene_refine", prompt=prompt, system=REFINE_SYSTEM, max_tokens=60), RefineAnswer).value
    except Exception:
        return cut
    if v.before_cut.strip().lower().startswith("new"):
        return order[r - 1]
    if v.at_cut.strip().lower().startswith("cont"):
        return order[r + 1]
    return cut


class RefineCache:
    """Refined position per (model, novel, chapter, cut block), so a rerun of the learn grid costs no GPU time."""

    def __init__(self, root: Path | str, model: str) -> None:
        self.path = Path(root) / f"refine_{model.replace(':', '_')}.json"
        try:
            self.data: dict[str, int] = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def refine(self, chapter: Chapter, novel: str, cut: int, llm: Any) -> int:
        key = f"{novel}:{chapter.number:g}:{cut}"
        if key not in self.data:
            self.data[key] = refine_cut(chapter, cut, llm)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data))
        return self.data[key]


def refine_cuts(chapter: Chapter, cuts: list[int], llm: Any, *, novel_id: str = "", cache: RefineCache | None = None) -> list[int]:
    """Every cut moved by `refine_cut`; two cuts that land on one block collapse to one."""
    out: list[int] = []
    for c in sorted(cuts):
        n = cache.refine(chapter, novel_id, c, llm) if cache is not None else refine_cut(chapter, c, llm)
        if n not in out:
            out.append(n)
    return sorted(out)
