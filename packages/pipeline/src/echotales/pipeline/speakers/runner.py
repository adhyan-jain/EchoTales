"""Phase 4 orchestration: run the attribution ladder over a novel.

Chapter-scoped state. `recent_speakers` resets at every chapter boundary and at
every scene break, because turn-taking alternation says nothing across a scene
change -- carrying it over would confidently attribute the first line of a new
scene to someone who is no longer present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echotales.core.enums import AliasType, AttributionMethod, SpanType
from echotales.core.models import Chapter, Span
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key
from echotales.pipeline.spans import classify_chapter
from echotales.pipeline.render.scenes import group_scenes
from echotales.pipeline.spans.scene import ActiveScene, build_active_scenes
from echotales.pipeline.speakers.attribution import (
    _ROLE_EPITHETS,
    Attribution,
    attribute_pronoun_epithet,
    attribute_span,
    detect_pov_holder,
    epithet_mentioned,
)
from echotales.pipeline.speakers.contextual import attribute_contextual

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

    # Who a bare pronoun ("he faced the clan elders and said,") currently
    # refers to, when nobody's been named. Updated from every block's own
    # narration (`epithet_mentioned`, speech-verb-adjacency not required --
    # "the clan head curled up his lips" still tells the *next* line who
    # "he" is), and cleared the moment a *different*, named character is
    # confidently established as speaking -- a real name always wins over a
    # standing title, and carrying the title past that point would
    # misattribute the named character's own lines to the epithet instead.
    current_epithet: str | None = None

    # A single combined pattern for every known character name, so a block's
    # narration can be checked for "does this mention someone by name" in
    # one pass. Longest-first so "Fang Zheng" doesn't shadow inside a longer
    # name that happens to contain it. This is what actually clears
    # `current_epithet` in practice -- confirmed on RI ch1, where nothing
    # between the clan head's last epithet-tagged line (block 68) and Fang
    # Yuan's own line (block 84) ever got an EXPLICIT-tier resolution, so
    # the EXPLICIT-only reset above never fired and "he slowly closed his
    # eyes... He sighed" -- narration plainly about Fang Yuan, established
    # by name two blocks earlier -- was about to be misattributed to "the
    # clan head" by the pronoun tier. Sorted names, not raw `known_names`,
    # since that set also holds folded comparison keys that are not valid
    # regex-safe surface forms to alternate on.
    named_re: re.Pattern[str] | None = None
    surface_names = sorted(
        (n for n in known_names if n and n[:1].isupper()), key=len, reverse=True
    )
    if surface_names:
        named_re = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in surface_names) + r")\b")

    for position, block in enumerate(ordered_blocks):
        block_spans = sorted(by_block.get(block.index, []), key=lambda s: s.start)

        # A scene break invalidates alternation: the next line belongs to a new
        # scene whose cast may share nobody with the previous one.
        if block.text.strip() == "* * *":
            recent.clear()
            current_epithet = None
            continue

        if mentioned := epithet_mentioned(block.text):
            current_epithet = mentioned
        elif current_epithet is not None and named_re is not None and named_re.search(block.text):
            # A different, named character is now what this block's
            # narration is actually about -- the epithet no longer applies
            # to the next bare pronoun until it's mentioned again.
            current_epithet = None

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

            if attribution.method is AttributionMethod.UNRESOLVED:
                pronoun_hit = attribute_pronoun_epithet(
                    span,
                    preceding=preceding,
                    following=following,
                    current_epithet=current_epithet,
                )
                if pronoun_hit is not None:
                    attribution = pronoun_hit

            out.append(attribution)

            # A real name speaking clears the standing title -- see
            # `current_epithet`'s own comment above the loop.
            if (
                attribution.speaker
                and attribution.method is AttributionMethod.EXPLICIT
                and attribution.speaker not in _ROLE_EPITHETS
            ):
                current_epithet = None

            # Only confident, genuinely spoken lines update the alternation
            # state. Seeding it from a guess makes the next guess worse.
            if (
                attribution.speaker
                and span.span_type is SpanType.DIALOGUE
                and attribution.method
                in (
                    AttributionMethod.EXPLICIT,
                    AttributionMethod.JOINT,
                    AttributionMethod.PROXIMAL,
                )
            ):
                recent.append(attribution.speaker)
                recent = recent[-6:]

    return out


def _scene_roster(
    block_index: int, scenes: list[ActiveScene], fallback_roster: list[str]
) -> list[str]:
    """Narrow the tier-4 candidate pool to who's actually in the room.

    `xyz.md` Step 3 asked for a separate scene-constrained LLM pass; per
    `HANDOFF.md` this instead feeds `spans/scene.py`'s registry into the
    existing tier 4 (`speakers/contextual.py`) rather than duplicating it --
    same problem, same call site, only the roster changes. A roster of 2-4
    active names is a much easier disambiguation than the full chapter cast,
    and the two solve the same problem the fallback already handles when no
    scene applies (segment boundaries not covering this chapter, or an empty
    cast -- e.g. a scene with no `ReferenceMode.PRESENT` mentions yet).
    """
    for scene in scenes:
        if scene.block_from <= block_index <= scene.block_to and scene.active_selves:
            # Preserve chapter-wide frequency order among the scene's cast --
            # a more-mentioned character is a likelier default guess than one
            # named once in passing, even within the same scene.
            active = scene.active_selves
            ranked = [name for name in fallback_roster if name in active]
            return ranked or sorted(active)
    return fallback_roster


def _attribute_contextual_pass(
    novel_id: str,
    chapter: Chapter,
    spans: list[Span],
    *,
    known_names: frozenset[str],
    roster: list[str],
    scenes: list[ActiveScene],
    client: object | None,
) -> None:
    """Tier 4: give the LLM one shot at what tiers 1-3 left UNRESOLVED.

    Runs over the same block-neighbourhood windows `attribute_chapter` used,
    recomputed here rather than threaded through it -- this pass is optional
    and only reaches a handful of lines per cold-start chapter, so a second
    pass over the chapter's blocks is cheap next to a model call per span.
    """
    if client is None or not roster:
        return

    by_block: dict[int, list[Span]] = {}
    for span in spans:
        by_block.setdefault(span.block_index, []).append(span)
    ordered_blocks = sorted(chapter.blocks, key=lambda b: b.index)

    for position, block in enumerate(ordered_blocks):
        if block.text.strip() == "* * *":
            continue
        block_spans = sorted(by_block.get(block.index, []), key=lambda s: s.start)
        prev_block = ordered_blocks[position - 1].text if position > 0 else ""
        next_block = (
            ordered_blocks[position + 1].text if position + 1 < len(ordered_blocks) else ""
        )

        for i, span in enumerate(block_spans):
            if span.span_type not in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE):
                continue
            if span.speaker_self_id or span.attribution_method is not AttributionMethod.UNRESOLVED:
                continue

            in_block_before = " ".join(s.text for s in block_spans[:i])
            in_block_after = " ".join(s.text for s in block_spans[i + 1 :])
            preceding = (prev_block + " " + in_block_before)[-_WINDOW:]
            following = (in_block_after + " " + next_block)[:_WINDOW]

            attribution = attribute_contextual(
                span,
                preceding=preceding,
                following=following,
                known_names=known_names,
                roster=_scene_roster(span.block_index, scenes, roster),
                client=client,
                novel_id=novel_id,
                chapter=chapter.number,
            )
            if attribution is None or not attribution.speaker:
                continue
            span.speaker_self_id = attribution.speaker
            span.attribution_method = attribution.method
            span.confidence = attribution.confidence


def _scene_key(block_index: int, scene_bounds: list[tuple[int, int]]) -> str:
    """A short, stable label for the scene a block sits in.

    Keyed by the block index the scene starts at, not by a segment id:
    segment ids are not stable across re-runs, and this string ends up
    inside a speaker id that corrections files reference by name.
    """
    for first, last in scene_bounds:
        if first <= block_index <= last:
            return f"s{first}"
    return "s0"


def _assign_anonymous_slots(
    novel_id: str,
    chapter_number: float,
    spans: list[Span],
    scene_bounds: list[tuple[int, int]] | None = None,
) -> None:
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
    scene_bounds = scene_bounds or []
    current_scene = ""
    for span in spans:
        if span.span_type is not SpanType.DIALOGUE:
            continue
        if span.speaker_self_id or span.attribution_method is not AttributionMethod.UNRESOLVED:
            fresh_run = True
            continue
        scene_key = _scene_key(span.block_index, scene_bounds)
        if scene_key != current_scene:
            # A scene change restarts the numbering as well as the scope, so
            # each scene's unnamed speakers read "Unknown Speaker 1, 2" in
            # the viewer rather than continuing a chapter-long count.
            current_scene = scene_key
            fresh_run = True
        slot = 1 if fresh_run else (slot % _MAX_ANON_SLOTS) + 1
        # **Scoped to the scene, not the chapter.** The slot counter restarts
        # at 1 after every resolved line, so a chapter-scoped id makes
        # collisions systematic rather than rare: measured on RI ch1,
        # `anon:1:1` was a cultivator besieging Fang Yuan in block 0 *and* a
        # villager gossiping at a ceremony in block 45 -- different people,
        # different scenes, three hundred years apart in story time, read by
        # TTS in one voice. Two unnamed speakers in one scene are plausibly
        # the same person; two in different scenes are not.
        span.speaker_self_id = f"{novel_id}:anon:{chapter_number:g}:{scene_key}:{slot}"
        span.attribution_method = AttributionMethod.ANONYMOUS_SLOT
        span.confidence = 0.2
        fresh_run = False


def attribute_novel(
    novel_id: str,
    store: Store,
    *,
    commit_every: int = 25,
    client: object | None = None,
    llm_chapter_cutoff: float = 0.0,
) -> AttributionReport:
    """Run attribution over a whole novel and persist the spans.

    `client`/`llm_chapter_cutoff` enable tier 4 (`speakers/contextual.py`) on
    chapters up to and including the cutoff -- see that module for why cold
    start, specifically, is what it exists to fix. `client` is `None` by
    default, so every existing caller (including every test) keeps the
    deterministic-only behaviour unless it opts in.
    """
    report = AttributionReport(novel_id=novel_id)

    # Accumulated across the novel rather than rebuilt per chapter: a character
    # introduced in chapter 5 still speaks in chapter 12 whether or not the
    # detector re-fired on them there. Both the surface form and its
    # honorific-stripped key are stored so "Wang" matches a recorded
    # "Elder Wang".
    known_names: set[str] = set()
    #: Display roster for the LLM prompt: surface forms only, no folded keys
    #: (those exist purely for `_known`'s membership check and would read as
    #: near-duplicate garbage names to the model).
    display_roster: dict[str, int] = {}

    for i, chapter in enumerate(store.iter_chapters(novel_id), start=1):
        spans = classify_chapter(chapter)
        mentions = store.get_mentions(novel_id, chapter.number)
        for mention in mentions:
            # A mention the NER layer confidently tagged as a place or an
            # organisation must never become a speaker candidate -- both
            # `_known()`'s regex gate and tier 4's LLM roster otherwise treat
            # it exactly like a person, which is how "Qing Mao Mountain" (a
            # mountain) ended up as the attributed speaker of a shouted line
            # in RI ch1 (§4.34). `entity_label` is `None` for the much larger
            # deterministic/gazetteer layer that never classified at all --
            # that stays in, since "unlabelled" is not evidence of anything.
            if mention.entity_label in ("location", "organization"):
                continue
            # RELATIONAL_DEICTIC ("this one", "that person") is defined as
            # speaker-relative -- its referent depends on who is already
            # speaking, so it can never itself be a fixed name to attribute
            # *to*. Without this it entered the roster verbatim and the LLM
            # tier picked "this one" as a line's speaker, literally, in RI
            # ch1 (§4.34).
            if mention.alias_type is AliasType.RELATIONAL_DEICTIC:
                continue
            if mention.alias_type.enters_graph:
                known_names.add(mention.text)
                key = comparison_key(mention.text)
                if key:
                    known_names.add(key)
                display_roster[mention.text] = display_roster.get(mention.text, 0) + 1
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
            speaker = attribution.speaker
            if speaker and attribution.method is AttributionMethod.EPITHET_SLOT:
                # Keyed by the *role noun itself* ("clan head"), not the
                # whole matched phrase -- "the clan head" and "the Gu Yue
                # clan head" are the same title stated two ways, and must
                # collapse to the same stable id or the whole point (one
                # consistent voice per title) is lost. Never a graph `Self`:
                # a title is not a permanent identity.
                role = next(
                    (r for r in _ROLE_EPITHETS if r in speaker.casefold()), speaker.casefold()
                )
                speaker = f"{novel_id}:epithet:{chapter.number:g}:{role.replace(' ', '-')}"
            span.speaker_self_id = speaker
            span.attribution_method = attribution.method
            span.co_speaker_self_ids = attribution.co_speakers
            if attribution.speaker:
                span.confidence = attribution.confidence

        # Built for every chapter, not only the ones the LLM tier runs on:
        # anonymous slot ids are scene-scoped now, and a chapter that skipped
        # this would silently fall back to one scene for the whole chapter.
        # No model calls involved, so the cost is a pass over mentions.
        segments = store.get_segments(novel_id, chapter.number)
        scenes = build_active_scenes(chapter, mentions, segments, spans)
        # **`ActiveScene` is not a scene here, it is a narrative segment.**
        # Measured: segmentation produces exactly one MAIN segment per
        # chapter across all 199 (200 segments, 199 chapters), so scoping
        # anonymous slots to it would have been scoping them to the chapter
        # under a different name -- the bug it is meant to fix. The panel
        # renderer already splits chapters into real scenes on locale, cast
        # and time cues; that is the boundary a voice should reset at.
        scene_bounds = [
            (min(s.blocks), max(s.blocks))
            for s in group_scenes(novel_id, chapter, mentions, segments, spans)
            if s.blocks
        ]

        if chapter.number <= llm_chapter_cutoff:
            roster = [name for name, _ in sorted(display_roster.items(), key=lambda kv: -kv[1])]
            _attribute_contextual_pass(
                novel_id,
                chapter,
                spans,
                known_names=known,
                roster=roster,
                scenes=scenes,
                client=client,
            )

        # Runs after the ladder, over what the ladder left UNRESOLVED. Never
        # counted in `report.attributed` -- that number means "linked to a
        # known identity," and an anonymous slot deliberately is not one.
        _assign_anonymous_slots(novel_id, chapter.number, spans, scene_bounds)

        # Full re-derivation, not an incremental update -- clear the
        # chapter's existing rows first so a re-run that produces fewer
        # spans than a previous run (e.g. a block reclassified out of story
        # content) doesn't leave orphaned stale spans behind. See
        # `delete_spans_for_chapter`'s docstring; this is where §4.32's
        # phantom "Daoist Gu" speaker survived a re-ingest.
        store.delete_spans_for_chapter(novel_id, chapter.number)
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
