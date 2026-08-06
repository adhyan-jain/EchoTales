"""LLM fallback for implicit narrative boundaries (plans.md §6 Phase 2).

**One call per chapter, and only for chapters the rules found ambiguous.**

That restriction follows the measured budget: a per-span pass over this corpus
is 34.5 hours locally, a per-chapter pass is 19 minutes, and gating on ambiguity
cuts even that by roughly an order of magnitude. The rules already resolve the
formulaic transitions -- dream entry in this genre is announced verbatim -- so
the model is asked only about the boundaries that are genuinely implicit.

The prompt sends **block summaries, not full chapter text**: block index, first
and last few words, and the sub-threshold markers found. That keeps the prompt
inside an 8k context on an 8 GB card and keeps the model's attention on
structure rather than on plot.
"""

from __future__ import annotations

from echotales.core.models import Chapter
from echotales.pipeline.llm import LLMRequest, LLMRouter
from echotales.pipeline.segment.markers import ENTRY_KINDS, Marker
from pydantic import BaseModel, Field

SYSTEM = (
    "You analyse the narrative structure of translated web-novel chapters. "
    "You identify where a chapter shifts out of present-time narration into a "
    "dream, a flashback, a vision, or a prophecy, and where it shifts back. "
    "You are conservative: if a passage is ordinary present-time narration that "
    "merely mentions the past, it is NOT a flashback."
)


class BoundaryProposal(BaseModel):
    """One proposed non-linear segment."""

    start_block: int = Field(description="index of the first block inside the segment")
    end_block: int = Field(description="index of the last block inside the segment")
    kind: str = Field(description="one of DREAM, FLASHBACK, VISION, PROPHECY")
    reason: str = Field(default="", description="the textual cue that signals it")


class SegmentationResponse(BaseModel):
    boundaries: list[BoundaryProposal] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def _block_digest(chapter: Chapter, *, head: int = 12, tail: int = 6) -> str:
    """Compact structural view of a chapter.

    Full text would blow the context window and bias the model toward
    summarising the story. Boundaries are visible from the seams between
    blocks, which is all this needs.
    """
    lines: list[str] = []
    for block in chapter.blocks:
        words = block.text.split()
        if len(words) <= head + tail:
            body = " ".join(words)
        else:
            body = " ".join(words[:head]) + " … " + " ".join(words[-tail:])
        lines.append(f"[{block.index}] {body}")
    return "\n".join(lines)


def needs_llm_pass(markers: list[Marker], *, threshold: float = 0.7) -> bool:
    """Whether a chapter is ambiguous enough to be worth a call.

    True when there is suggestive evidence of a boundary that did not clear the
    promotion threshold. A chapter with no markers at all is linear and gets no
    call; a chapter with a confident marker was already resolved by the rules.
    """
    entry_markers = [m for m in markers if m.kind in ENTRY_KINDS]
    if not entry_markers:
        return False
    return all(m.confidence < threshold for m in entry_markers)


def propose_boundaries(
    chapter: Chapter,
    router: LLMRouter,
    *,
    novel_id: str = "",
) -> SegmentationResponse:
    """Ask the model where a chapter changes narrative layer."""
    prompt = (
        f"Chapter {chapter.number:g}: {chapter.title}\n\n"
        "Below is one line per paragraph block, abbreviated.\n\n"
        f"{_block_digest(chapter)}\n\n"
        "Identify any spans of blocks that are NOT present-time narration -- "
        "that is, dream sequences, flashbacks, visions or prophecies. "
        "Return an empty list if the whole chapter is present-time narration, "
        "which is the usual case. Do not report a flashback merely because the "
        "text mentions the past."
    )
    result = router.complete(
        LLMRequest(stage="segment", prompt=prompt, system=SYSTEM, max_tokens=800),
        SegmentationResponse,
        novel_id=novel_id or chapter.novel_id,
        chapter=chapter.number,
    )
    return result.value
