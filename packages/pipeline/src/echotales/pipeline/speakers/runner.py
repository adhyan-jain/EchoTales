"""Phase 4 orchestration: run the attribution ladder over a novel.

Chapter-scoped state. `recent_speakers` resets at every chapter boundary and at
every scene break, because turn-taking alternation says nothing across a scene
change -- carrying it over would confidently attribute the first line of a new
scene to someone who is no longer present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.enums import AliasType, AttributionMethod, SpanType
from echotales.core.models import Chapter, Span
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key
from echotales.pipeline.spans import classify_chapter
from echotales.pipeline.speakers.attribution import (
    Attribution,
    attribute_span,
    detect_pov_holder,
)

#: Characters of narration either side of a line that the tiers may consult.
_WINDOW = 220

#: Anonymous slots cycle within this cap rather than growing unboundedly --
#: a chapter with a dozen unresolved lines in a row is one confused scene,
#: not a dozen distinct background speakers.
_MAX_ANON_SLOTS = 4


@dataclass(slots=True)
class AttributionReport:
    novel_id: str
    chapters: int = 0
    dialogue_spans: int = 0
    attributed: int = 0
    by_method: dict[str, int] = field(default_factory=dict)
    pov_chapters: int = 0
    #: Dialogue given a voice-differentiation slot but no real identity --
    #: never counted in `attributed`/`coverage`. See `_assign_anonymous_slots`.
    anonymous_slots: int = 0

    @property
    def coverage(self) -> float:
        return self.attributed / self.dialogue_spans if self.dialogue_spans else 0.0

    def summary(self) -> str:
        methods = ", ".join(f"{k}={v}" for k, v in sorted(self.by_method.items()))
        return (
            f"{self.novel_id}: {self.attributed:,}/{self.dialogue_spans:,} speech spans "
            f"attributed ({self.coverage:.1%})\n"
            f"  anonymous voice slots (no identity, distinct voice): {self.anonymous_slots:,}\n"
            f"  by method: {methods}\n"
            f"  chapters with a detected POV holder: {self.pov_chapters}/{self.chapters}"
        )


def attribute_chapter(
    chapter: Chapter,
    *,
    spans: list[Span] | None = None,
    known_names: frozenset[str] = frozenset(),
    pov_holder: str | None = None,
) -> list[Attribution]:
    """Attribute every speech span in one chapter."""
    spans = spans if spans is not None else classify_chapter(chapter)
    by_block: dict[int, list[Span]] = {}
    for span in spans:
        by_block.setdefault(span.block_index, []).append(span)

    out: list[Attribution] = []
    recent: list[str] = []
    ordered_blocks = sorted(chapter.blocks, key=lambda b: b.index)

    for position, block in enumerate(ordered_blocks):
        block_spans = sorted(by_block.get(block.index, []), key=lambda s: s.start)

        # A scene break invalidates alternation: the next line belongs to a new
        # scene whose cast may share nobody with the previous one.
        if block.text.strip() == "* * *":
            recent.clear()
            continue

        # Narration from the neighbouring blocks. Roughly 15% of speech spans
        # occupy a paragraph of their own, with the attribution sitting in the
        # block before or after; confining the window to the current block
        # makes those unattributable no matter how explicit the text is.
        prev_block = ordered_blocks[position - 1].text if position > 0 else ""
        next_block = (
            ordered_blocks[position + 1].text if position + 1 < len(ordered_blocks) else ""
        )

        for i, span in enumerate(block_spans):
            if span.span_type not in (
                SpanType.DIALOGUE,
                SpanType.INNER_MONOLOGUE,
                SpanType.CROWD_REACTION,
            ):
                continue

            in_block_before = " ".join(s.text for s in block_spans[:i])
            in_block_after = " ".join(s.text for s in block_spans[i + 1 :])

            # In-block narration is nearer the line and therefore stronger
            # evidence, so it is placed closest to the quote in each window.
            preceding = (prev_block + " " + in_block_before)[-_WINDOW:]
            following = (in_block_after + " " + next_block)[:_WINDOW]

            attribution = attribute_span(
                span,
                preceding=preceding,
                following=following,
                recent_speakers=recent,
                known_names=known_names,
                pov_holder=pov_holder,
            )
            out.append(attribution)

            # Only confident, genuinely spoken lines update the alternation
            # state. Seeding it from a guess makes the next guess worse.
            if (
                attribution.speaker
                and span.span_type is SpanType.DIALOGUE
                and attribution.method
                in (AttributionMethod.EXPLICIT, AttributionMethod.JOINT)
            ):
                recent.append(attribution.speaker)
                recent = recent[-6:]

    return out


def _assign_anonymous_slots(novel_id: str, chapter_number: float, spans: list[Span]) -> None:
    """Give unresolved dialogue a locally-distinct voice slot, not an identity.

    Downstream synthesis needs two different unattributed lines to *sound*
    different far more often than it needs to know *who* they are -- a scene
    with two unnamed guards trading lines is wrong read in one voice, but
    minting a `Self` for either of them clutters the graph with someone who
    may never be named or seen again. `Persona` (appearance/voice) already
    exists separately from `Self` (identity/memory) for exactly this reason
    ("This is what image generation and TTS bind to") -- an anonymous slot is
    the lightest thing that could work in that gap: an id, scoped to this
    chapter, never written as a `Self` row.

    Turn-taking only, and deliberately not claiming to be coreference:
    consecutive unresolved dialogue alternates slots, and any resolved line
    (a real speaker, or a scene break already having cleared upstream state)
    restarts the count at slot 1. That encodes one fact confidently -- "the
    same nobody twice in a row is the less likely reading of ordinary
    back-and-forth dialogue" -- and claims nothing beyond it.
    """
    slot = 0
    fresh_run = True
    for span in spans:
        if span.span_type is not SpanType.DIALOGUE:
            continue
        if span.speaker_self_id or span.attribution_method is not AttributionMethod.UNRESOLVED:
            fresh_run = True
            continue
        slot = 1 if fresh_run else (slot % _MAX_ANON_SLOTS) + 1
        span.speaker_self_id = f"{novel_id}:anon:{chapter_number:g}:{slot}"
        span.attribution_method = AttributionMethod.ANONYMOUS_SLOT
        span.confidence = 0.2
        fresh_run = False


def attribute_novel(
    novel_id: str,
    store: Store,
    *,
    commit_every: int = 25,
) -> AttributionReport:
    """Run attribution over a whole novel and persist the spans."""
    report = AttributionReport(novel_id=novel_id)

    # Accumulated across the novel rather than rebuilt per chapter: a character
    # introduced in chapter 5 still speaks in chapter 12 whether or not the
    # detector re-fired on them there. Both the surface form and its
    # honorific-stripped key are stored so "Wang" matches a recorded
    # "Elder Wang".
    known_names: set[str] = set()

    for i, chapter in enumerate(store.iter_chapters(novel_id), start=1):
        spans = classify_chapter(chapter)
        mentions = store.get_mentions(novel_id, chapter.number)
        for mention in mentions:
            if mention.alias_type is AliasType.RIGID_NAME:
                known_names.add(mention.text)
                key = comparison_key(mention.text)
                if key:
                    known_names.add(key)
        known = frozenset(known_names)

        pov = detect_pov_holder(mentions, spans)
        if pov:
            report.pov_chapters += 1

        attributions = attribute_chapter(
            chapter, spans=spans, known_names=known, pov_holder=pov
        )
        by_id = {a.span_id: a for a in attributions}

        for span in spans:
            attribution = by_id.get(span.id)
            if attribution is None:
                continue
            span.speaker_self_id = attribution.speaker
            span.attribution_method = attribution.method
            span.co_speaker_self_ids = attribution.co_speakers
            if attribution.speaker:
                span.confidence = attribution.confidence

        # Runs after the ladder, over what the ladder left UNRESOLVED. Never
        # counted in `report.attributed` -- that number means "linked to a
        # known identity," and an anonymous slot deliberately is not one.
        _assign_anonymous_slots(novel_id, chapter.number, spans)

        store.add_spans(spans)

        # Tallied from the spans' *final* state, after the anonymous-slot
        # pass -- not from `attributions`, which is a snapshot from before
        # that pass ran and would double-book every slot assignment as
        # UNRESOLVED. `report.attributed` keeps its original meaning ("linked
        # to a known identity"): ANONYMOUS_SLOT is tracked separately and
        # never counted there, deliberately -- it is not one.
        report.chapters += 1
        eligible_types = (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE, SpanType.CROWD_REACTION)
        for span in spans:
            if span.span_type not in eligible_types:
                continue
            report.dialogue_spans += 1
            method = span.attribution_method
            report.by_method[method.value] = report.by_method.get(method.value, 0) + 1
            if method is AttributionMethod.ANONYMOUS_SLOT:
                report.anonymous_slots += 1
            elif span.speaker_self_id or method is AttributionMethod.UNATTRIBUTED_CHORUS:
                report.attributed += 1

        if i % commit_every == 0:
            store.conn.commit()

    store.conn.commit()
    return report
