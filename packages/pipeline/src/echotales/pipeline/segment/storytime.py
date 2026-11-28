"""Chapter-level story-time pass over the finished segments (segment v3).

Why after segmentation and over the whole chapter: RI ch1 shows the time relation of a segment is revealed far from
its start. The cliff (blocks 0-30) is only known to be the life that ended once block 80 says "500 years ago"; v2.1
flagged time per block and put that on the wrong segment (the anchor landed on block 80, not on segment 0). With one
line per segment plus the chapter's own time statements the model can place each segment against the chapter's main
present line in a single call.

The model must quote the phrase it relied on, and the code checks the quote is in the chapter. An answer whose quote
cannot be found is downgraded to "present, unknown": a small model asked to classify layers will otherwise call a
flashback on a feeling and never be caught.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from echotales.core.models import Chapter
from echotales.pipeline.llm import LLMRequest
from echotales.pipeline.segment.cuts import TimeRelation
from echotales.pipeline.segment.implicit import _segment_ranges
from echotales.pipeline.segment.judge import story_blocks
from pydantic import BaseModel, Field

LAYERS = ("past", "memory", "dream", "imagined", "present")
RELATIONS = {"earlier": TimeRelation.EARLIER, "later": TimeRelation.LATER, "same": TimeRelation.SAME, "parallel": TimeRelation.SAME}

SYSTEM = (
    "You place the segments of one novel chapter on the story timeline. First find the MAIN PRESENT LINE: the "
    "segment the chapter's story continues from. A chapter normally ends on its main line, so start from the last "
    "segment; choose an earlier one only when the last segment is itself a flashback, a memory or a dream. The main "
    "line is not always the first segment: a chapter can open on a scene that a later time statement shows to be an "
    "earlier life, an earlier loop or an earlier iteration of the same person (a death before a rebirth, a regression "
    "to years ago). Read all the TIME STATEMENTS, each tagged with the segment it appears in, before you decide. "
    "For every other segment give its layer relative to the main line: past (earlier events shown straight as they "
    "happened, including a life a character lived before a rebirth or time loop, even when it is shown first in the "
    "chapter), memory (remembered by a character), dream, imagined, or present (the same story line as the main "
    "one, at the same time). Give its time_relation to the main line: earlier, later, same, parallel (happens at the "
    "same time elsewhere) or unknown. Answer exactly once per segment. Copy in `quote` the exact words (a few "
    "words, from the segment lines or the time statements) that you relied on; when nothing in the text states "
    "it, answer present and unknown with an empty quote."
)


class SegmentTime(BaseModel):
    segment: int = Field(description="segment number")
    layer: str = Field(default="present", description="past, memory, dream, imagined or present")
    time_relation: str = Field(default="unknown", description="earlier, later, same, parallel or unknown")
    quote: str = Field(default="", description="exact words from the text that this relies on")


class StoryTimeAnswer(BaseModel):
    main_line_reason: str = Field(default="", description="the time statement that shows which segment the story continues from")
    main_segment: int = Field(default=0, description="number of the main present line")
    segments: list[SegmentTime] = Field(default_factory=list)


@dataclass(slots=True)
class SegmentTimeLabel:
    segment: int
    layer: str = "present"
    time_relation: TimeRelation = TimeRelation.UNKNOWN
    quote: str = ""
    verified: bool = False


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def quote_in(text: str, quote: str) -> bool:
    """True when `quote` (punctuation and spacing ignored) is a contiguous part of `text`; very short quotes fail."""
    q = _norm(quote)
    return len(q.split()) >= 2 and q in _norm(text)


def segment_summary_line(chapter: Chapter, lo: int, hi: int, words: int = 45) -> str:
    """Opening of a segment, clipped: the model reads the lead, the full text stays out of the 4096 context."""
    text = {b.index: b.text for b in chapter.blocks}
    ids = [i for i in story_blocks(chapter) if lo <= i <= hi]
    lead = " ".join(" ".join(text[i].split()[:words]) for i in ids[:2])
    return " ".join(lead.split()[: words * 2])


def outline_segment_line(outline: list[Any], lo: int, hi: int) -> str:
    """A segment summarised from the whole-chapter outline (v4): its people, its places and every time statement."""
    rows = [ln for ln in outline if lo <= ln.block <= hi]

    def distinct(vals: list[str], n: int) -> list[str]:
        seen: list[str] = []
        for v in vals:
            for part in (x.strip() for x in v.split(",")):
                if part and part.lower() not in {y.lower() for y in seen}:
                    seen.append(part)
        return seen[:n]

    who = ", ".join(distinct([r.who for r in rows], 5))
    where = ", ".join(distinct([r.where for r in rows], 3))
    when = ", ".join(distinct([r.when for r in rows], 4))
    return "; ".join(x for x in (f"people: {who}" if who else "", f"places: {where}" if where else "", f"times: {when}" if when else "") if x)


def outline_time_statements(chapter: Chapter, outline: list[Any], limit: int = 8, words: int = 40) -> list[str]:
    """Blocks whose outline line states a time, with the block's own opening words so a quote can be copied from it."""
    text = {b.index: b.text for b in chapter.blocks}
    out = []
    for ln in outline:
        if ln.when and ln.block in text:
            out.append(f"[{ln.block}] " + " ".join(text[ln.block].split()[:words]))
        if len(out) >= limit:
            break
    return out


def explicit_time_statements(chapter: Chapter, ranges: list[tuple[int, int]], nlp: Any, limit: int = 10, before: int = 90, after: int = 70) -> list[str]:
    """Every explicit time statement in the chapter, wherever it occurs, tagged with the segment it falls in (segment v5b).

    RI ch1 v5: the pass was shown the `when` words of the first 8 blocks that had one ("late in the night", a name) as
    "TIME STATEMENTS" with the first 40 words of the block, so "500 years ago" in block 80 and "300 years ... 200 years"
    in block 20 reached the model only by luck. A numeric DATE entity (spaCy NER, no word list) with the text around it
    is the statement; the segment number lets the model tie a reveal in one segment to a scene shown in another.
    """
    if nlp is None:
        return []
    out: list[str] = []
    for b in chapter.blocks:
        if not b.block_type.is_story_content:
            continue
        seg = next((i for i, (lo, hi) in enumerate(ranges) if lo <= b.index <= hi), None)
        if seg is None:
            continue
        for ent in nlp(b.text).ents:
            if ent.label_ == "DATE" and any(t.like_num for t in ent):
                lo = max(0, ent.start_char - before)
                snip = " ".join(b.text[lo : ent.end_char + after].split())
                out.append(f"[block {b.index}, segment {seg}] ..." + snip + "...")
                break
        if len(out) >= limit:
            break
    return out


def story_time_pass(
    chapter: Chapter,
    cut_blocks: list[int],
    llm: Any,
    *,
    nlp: Any | None = None,
    outline: list[Any] | None = None,
    think: bool = False,
    max_tokens: int = 700,
) -> list[SegmentTimeLabel]:
    """Layer and time relation of every segment of the chapter; one model call, quotes verified in code.

    With `outline` (v4) each segment is described by the whole-chapter outline, not by its first two blocks, so a
    segment whose time is only revealed far away (RI ch1: the cliff, revealed by block 80) is seen next to the line
    that reveals it. `think` (v5b) lets the model reason before it answers; the model behind `llm` then needs the
    `outline.V5_NUM_CTX` context and `max_tokens` must hold the trace.
    """
    from echotales.pipeline.segment.cuts import SceneCut

    cuts = [SceneCut(chapter=chapter.number, block=b, source="judge") for b in sorted(cut_blocks)]
    ranges = _segment_ranges(chapter, cuts)
    if len(ranges) < 2:
        return [SegmentTimeLabel(0)]
    full = "\n".join(b.text for b in chapter.blocks)
    if outline:
        lines = [
            f"SEGMENT {i} (blocks {lo}-{hi}): {segment_summary_line(chapter, lo, hi, words=25)} || {outline_segment_line(outline, lo, hi)}"
            for i, (lo, hi) in enumerate(ranges)
        ]
    else:
        lines = [f"SEGMENT {i} (blocks {lo}-{hi}): {segment_summary_line(chapter, lo, hi)}" for i, (lo, hi) in enumerate(ranges)]
    stated = explicit_time_statements(chapter, ranges, nlp)
    if not stated and outline:
        stated = outline_time_statements(chapter, outline)
    prompt = "\n".join(lines) + ("\n\nTIME STATEMENTS:\n" + "\n".join(stated) if stated else "") + "\n\nGive every segment's layer and relation to the main present line."
    out = [SegmentTimeLabel(i) for i in range(len(ranges))]
    try:
        res = llm.complete(LLMRequest(stage="scene_story_time", prompt=prompt, system=SYSTEM, max_tokens=max_tokens, extra={"think": True} if think else {}), StoryTimeAnswer)
    except Exception:
        return out
    main = res.value.main_segment
    seen: set[int] = set()
    for item in res.value.segments:
        # One verified answer per segment, the first one: RI ch1 v5 had the model list a segment twice and the later,
        # unquoted "present" overwrote the quoted answer.
        if not (0 <= item.segment < len(ranges)) or item.segment == main or item.segment in seen:
            continue
        # The quote has to be words of the chapter itself.
        if not quote_in(full, item.quote):
            continue
        seen.add(item.segment)
        layer = item.layer.strip().lower()
        out[item.segment] = SegmentTimeLabel(
            item.segment,
            layer if layer in LAYERS else "present",
            RELATIONS.get(item.time_relation.strip().lower(), TimeRelation.UNKNOWN),
            item.quote.strip(),
            True,
        )
    return out


def prior_loop_segments(labels: list[SegmentTimeLabel]) -> set[int]:
    """Segments shown straight from an earlier time: the past layer with an earlier relation."""
    return {s.segment for s in labels if s.verified and s.layer == "past" and s.time_relation is TimeRelation.EARLIER}
