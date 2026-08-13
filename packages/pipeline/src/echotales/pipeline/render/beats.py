"""Beat segmentation: how many panels a chapter actually deserves.

**One panel per block was the wrong unit, and it is why a chapter produced
89 images that were mostly repeated backgrounds.** A block is a paragraph;
paragraphs are not panels. A chapter of a web novel contains on the order of
ten *moments worth drawing* -- an arrival, a confrontation, a blow landing, a
death -- and the prose between them is the same moment continuing. Drawing
every paragraph produces near-duplicates, spends the entire render budget on
scenery, and still misses the moments, because each panel only ever sees one
paragraph's worth of context.

This is `plans.md` Phase 10's beat segmentation, which that section always
specified and which the first implementation skipped.

**A beat starts where the picture would change**, on any of:

- a narrative segment boundary (`spans/scene.py` already knows these),
- the cast changing -- someone arrives or leaves,
- a hard shift in what kind of prose it is (description -> action),
- enough narration having accumulated that the moment has moved on.

Everything inside a beat shares one panel, held across all of its lines by
`timeline.py`'s existing carry-forward. That is the whole mechanism: this
module decides *where* panels are generated, and nothing downstream needs to
change.

The payoff is not only fewer files. A beat's prompt is built from all of its
narration rather than one paragraph, so the panel that gets drawn is the
moment, not the sentence.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from echotales.core.enums import SpanType
from echotales.core.models import NarrativeSegment, Span

#: Once a beat has accumulated this much narration it has almost certainly
#: moved on to a new moment, even with no other signal.
_MAX_BEAT_CHARS = 900

#: Never merge more than this many blocks into one panel, so a long
#: uneventful stretch still gets a fresh picture eventually.
_MAX_BEAT_BLOCKS = 14

#: A chapter gets at most this many panels. The binding constraint is
#: quality, not count: a handful of well-composed images beats a hundred
#: variations on an empty courtyard, and the render budget is better spent
#: on more steps per image than on more images.
DEFAULT_MAX_PANELS = 14


@dataclass(slots=True)
class Beat:
    """One drawable moment, and every block it covers."""

    index: int
    blocks: list[int] = field(default_factory=list)
    text: str = ""

    @property
    def lead_block(self) -> int:
        """The block the panel is filed under."""
        return self.blocks[0]


def _kind(spans: list[Span]) -> str:
    """Coarse prose type for a block: what sort of picture it wants."""
    kinds = {s.span_type for s in spans}
    if kinds & {SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE}:
        return "talk"
    if SpanType.NARRATION_ACTION in kinds:
        return "action"
    return "describe"


def segment_beats(
    chapter_spans: list[Span],
    segments: list[NarrativeSegment] | None = None,
    *,
    max_panels: int = DEFAULT_MAX_PANELS,
    max_beat_chars: int = _MAX_BEAT_CHARS,
    max_beat_blocks: int = _MAX_BEAT_BLOCKS,
) -> list[Beat]:
    """Group a chapter's blocks into the moments worth drawing."""
    by_block: dict[int, list[Span]] = {
        b: list(g)
        for b, g in itertools.groupby(chapter_spans, key=lambda s: s.block_index)
    }
    if not by_block:
        return []

    boundaries = {
        int(seg.offset_from) for seg in (segments or []) if seg.offset_from is not None
    }

    beats: list[Beat] = []
    current = Beat(index=0)
    prev_kind: str | None = None
    prev_cast: set[str] = set()

    for block_index in sorted(by_block):
        spans = by_block[block_index]
        kind = _kind(spans)
        cast = {s.speaker_self_id for s in spans if s.speaker_self_id}
        text = " ".join(s.text for s in spans)

        starts_beat = (
            not current.blocks
            or block_index in boundaries
            or (prev_kind is not None and kind != prev_kind and kind != "talk")
            or (cast and prev_cast and cast != prev_cast)
            or len(current.text) >= max_beat_chars
            or len(current.blocks) >= max_beat_blocks
        )

        if starts_beat and current.blocks:
            beats.append(current)
            current = Beat(index=len(beats))

        current.blocks.append(block_index)
        current.text = f"{current.text} {text}".strip()
        prev_kind, prev_cast = kind, cast or prev_cast

    if current.blocks:
        beats.append(current)

    return _merge_to_budget(beats, max_panels)


def _merge_to_budget(beats: list[Beat], max_panels: int) -> list[Beat]:
    """Fold the shortest neighbouring beats together until the chapter fits.

    Merging the *shortest* first means the moments that survive are the ones
    the prose spends the most words on, which is the best available proxy
    for what matters in the chapter.
    """
    if max_panels <= 0 or len(beats) <= max_panels:
        return _renumber(beats)

    working = list(beats)
    while len(working) > max_panels:
        shortest = min(
            range(len(working) - 1), key=lambda i: len(working[i].text) + len(working[i + 1].text)
        )
        merged = Beat(
            index=shortest,
            blocks=working[shortest].blocks + working[shortest + 1].blocks,
            text=f"{working[shortest].text} {working[shortest + 1].text}".strip(),
        )
        working[shortest : shortest + 2] = [merged]

    return _renumber(working)


def _renumber(beats: list[Beat]) -> list[Beat]:
    for i, beat in enumerate(beats):
        beat.index = i
    return beats
