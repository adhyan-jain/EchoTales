"""A comic's understanding written into the store as a novel, so casting, voice, review and corrections work
unchanged.

One episode is one chapter; every bubble that is spoken or narrated is one block with one span, in reading order.
Sound effects are not story text and are not written (they stay in `understanding.json`). A speaker cluster becomes
a `Self` with a resolved mention, which is the join `voice/runner.py::speaker_index` uses from a span's speaker label
to its entity.

Speakers come from a colour-signature heuristic on the bubble tail, so every attribution is PROXIMAL with moderate
confidence and a bubble with no tail stays UNRESOLVED: a reviewer's correction (stored as HUMAN) overrides either.
"""

from __future__ import annotations

from dataclasses import dataclass

from echotales.core.enums import (
    AliasType,
    AttributionMethod,
    BlockType,
    Prominence,
    ReferenceMode,
    ResolutionMethod,
    SpanType,
    TargetKind,
)
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.comic.bubbles import Bubble
from echotales.pipeline.comic.understand import ComicUnderstanding

#: Below the voice stage's own floor for a confirmed character voice, deliberately: a tail heuristic is a guess and
#: the voice stage then casts an "unconfirmed" stand-in rather than the character's voice. Raised to 1.0 by a human.
HEURISTIC_CONFIDENCE = 0.6
#: What `trust_speakers=True` writes: the PROXIMAL tier's own confidence (0.75), above the voice floor of 0.7. For a
#: person who has looked at the clusters and found them right.
TRUSTED_CONFIDENCE = 0.75


@dataclass(slots=True)
class ComicGraphReport:
    novel_id: str
    chapter: float
    blocks: int = 0
    spans: int = 0
    speakers: int = 0
    unattributed: int = 0
    sfx_skipped: int = 0


def story_bubbles(und: ComicUnderstanding) -> list[Bubble]:
    """The bubbles that become blocks, in order. `build` maps blocks back to panels with this same function."""
    return [b for b in und.bubbles() if b.kind in ("speech", "narration")]


def comic_to_store(
    store: Store,
    und: ComicUnderstanding,
    novel_id: str,
    title: str,
    *,
    chapter: float = 1.0,
    chapter_title: str | None = None,
    source: str = "",
    trust_speakers: bool = False,
) -> ComicGraphReport:
    from echotales.pipeline.persona import build_personas

    store.add_novel(novel_id, title, source, "comic", content_type="comic")
    bubbles = story_bubbles(und)
    report = ComicGraphReport(novel_id, chapter, sfx_skipped=sum(1 for b in und.bubbles() if b.kind == "sfx"))
    blocks, spans = [], []
    for i, b in enumerate(bubbles):
        is_speech = b.kind == "speech"
        blocks.append(Block(index=i, block_type=BlockType.DIALOGUE if is_speech else BlockType.PROSE, text=b.text))
        attributed = is_speech and b.speaker is not None
        spans.append(Span(
            id=f"{novel_id}:c{chapter:g}:{b.id}", novel_id=novel_id, chapter=chapter, block_index=i, start=0,
            end=len(b.text), span_type=SpanType.DIALOGUE if is_speech else SpanType.NARRATION_DESCRIPTION,
            text=b.text, speaker_self_id=b.speaker if attributed else None,
            attribution_method=AttributionMethod.PROXIMAL if attributed else AttributionMethod.UNRESOLVED,
            confidence=(TRUSTED_CONFIDENCE if trust_speakers else HEURISTIC_CONFIDENCE) if attributed else 1.0,
        ))
        if is_speech and not attributed:
            report.unattributed += 1
    store.add_chapter(Chapter(novel_id=novel_id, number=chapter, title=chapter_title or f"Episode {chapter:g}",
                              source_href=source or "comic", blocks=blocks))
    # `add_spans` only overwrites ids the new batch produces; a re-understand with fewer or renumbered bubbles left the
    # old run's spans in the chapter and the voice stage spoke them too.
    store.delete_spans_for_chapter(novel_id, chapter)
    store.add_spans(spans)

    first_block = {}
    for i, b in enumerate(bubbles):
        if b.speaker and b.speaker not in first_block:
            first_block[b.speaker] = i
    for n, label in enumerate(sorted(first_block, key=first_block.get)):
        self_id = f"{novel_id}:self{n + 1}"
        store.add_self(Self(
            id=self_id, novel_id=novel_id, canonical_label=label, kind=TargetKind.SELF,
            first_attested_pos=DiscoursePosition(chapter=int(chapter), offset=0),
            prominence=Prominence.PRINCIPAL if n == 0 else Prominence.RECURRING,
        ))
        store.add_mentions([Mention(
            id=f"{novel_id}:m{n + 1}", novel_id=novel_id, segment_id="comic", chapter=chapter, offset=0,
            block_index=first_block[label], text=label, alias_type=AliasType.RIGID_NAME,
            span_type=SpanType.DIALOGUE, reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF,
            target_id=self_id, method=ResolutionMethod.GAZETTEER_EXACT,
        )])
    store.conn.commit()
    build_personas(novel_id, store)
    store.conn.commit()
    report.blocks, report.spans, report.speakers = len(blocks), len(spans), len(first_block)
    return report
