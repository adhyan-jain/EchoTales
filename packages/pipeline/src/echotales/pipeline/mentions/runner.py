"""Phase 3 orchestration: the three-layer mention detector.

Layer 1 (NER) and layer 2 (gazetteer) run over every chapter; layer 3 (LLM
sweep) is gated. The layers are merged with the gazetteer winning on overlap:
a confirmed alias matched exactly is higher-precision evidence than a
statistical span, and it also carries a target id the NER span does not.

The gazetteer is rebuilt at window boundaries rather than per chapter. That is
the compounding mechanism -- as the confirmed alias set grows, an increasing
share of mentions resolve by exact match at zero cost.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import (
    AliasType,
    ReferenceMode,
    ResolutionMethod,
    SpanType,
)
from echotales.core.models import Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.config import Settings, get_settings
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.mentions.alias_type import classify_alias_type
from echotales.pipeline.mentions.chapter_ner import (
    NameCache,
    VocabularyDetector,
    extract_chapter_names,
)
from echotales.pipeline.mentions.commonness import (
    CommonnessProfile,
    build_profile,
    credit_surfaces,
    looks_like_credit,
)
from echotales.pipeline.mentions.gazetteer import Gazetteer, seed_from_lexicon
from echotales.pipeline.mentions.lexicon import Lexicon
from echotales.pipeline.mentions.ner import MentionDetector, NerSpan, get_detector
from echotales.pipeline.mentions.parenthetical import (
    find_parentheticals,
)
from echotales.pipeline.mentions.seed import seed_from_volume
from echotales.pipeline.spans import classify_chapter

log = logging.getLogger(__name__)


@dataclass(slots=True)
class MentionReport:
    novel_id: str
    chapters: int = 0
    mentions: int = 0
    by_alias_type: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    dropped_generic: int = 0
    gazetteer_size: int = 0
    parentheticals: dict[str, int] = field(default_factory=dict)
    #: Share of mentions resolved by exact gazetteer match, per window. The
    #: compounding curve -- expected to rise as reading proceeds.
    gazetteer_hit_rate_by_window: list[tuple[int, float]] = field(default_factory=list)
    dropped_common_noun: int = 0
    dropped_credit: int = 0
    credit_surfaces: set[str] = field(default_factory=set)
    #: Layer 1 provenance. `llm_calls` is 0 on a deterministic run.
    detector_name: str = ""
    llm_calls: int = 0
    llm_surfaces: int = 0
    llm_rejected: int = 0

    def summary(self) -> str:
        lines = [
            f"{self.novel_id}: {self.mentions:,} mentions over {self.chapters} chapters",
            "  by alias type: "
            + ", ".join(f"{k}={v}" for k, v in sorted(self.by_alias_type.items())),
            "  by method: " + ", ".join(f"{k}={v}" for k, v in sorted(self.by_method.items())),
            f"  generic descriptors dropped: {self.dropped_generic:,}",
            f"  common nouns dropped: {self.dropped_common_noun:,}  "
            f"credits dropped: {self.dropped_credit:,}",
            f"  final gazetteer size: {self.gazetteer_size:,}",
            f"  layer 1: {self.detector_name or 'heuristic'}  "
            f"llm calls={self.llm_calls:,}  surfaces kept={self.llm_surfaces:,}  "
            f"rejected={self.llm_rejected:,}",
        ]
        if self.parentheticals:
            lines.append(
                "  parentheticals: "
                + ", ".join(f"{k}={v}" for k, v in sorted(self.parentheticals.items()))
            )
        if self.gazetteer_hit_rate_by_window:
            curve = "  ".join(
                f"w{w}:{r:.0%}" for w, r in self.gazetteer_hit_rate_by_window
            )
            lines.append(f"  gazetteer hit rate by window: {curve}")
        return "\n".join(lines)


#: Span types whose mentions denote someone physically in the scene.
_PRESENT_SPANS = frozenset(
    {SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION, SpanType.DIALOGUE}
)


def _reference_mode(span_type: SpanType) -> ReferenceMode:
    """Map a span type onto whether its mentions are physically present.

    Only `PRESENT` mentions get drawn in panels or counted for voice-collision
    avoidance. Without this, a chapter that merely *names* nine characters
    produces a panel containing nine, most of them absent or dead.
    """
    if span_type is SpanType.INNER_MONOLOGUE:
        return ReferenceMode.INNER_THOUGHT_REFERENCE
    if span_type is SpanType.NARRATION_EXPOSITION:
        return ReferenceMode.NARRATOR_REFERENCE
    if span_type is SpanType.DIALOGUE:
        # A name spoken inside dialogue usually refers to someone elsewhere;
        # presence is decided later from the scene cast, not from the mention.
        return ReferenceMode.DIALOGUE_REFERENCE
    if span_type in _PRESENT_SPANS:
        return ReferenceMode.PRESENT
    return ReferenceMode.NARRATOR_REFERENCE


def detect_mentions_in_chapter(
    chapter: Chapter,
    *,
    gazetteer: Gazetteer,
    lexicon: Lexicon,
    detector: MentionDetector,
    segment_id: str = "",
    known_entities: frozenset[str] = frozenset(),
    profile: CommonnessProfile | None = None,
    credits: set[str] | None = None,
) -> tuple[list[Mention], dict[str, int]]:
    """Run layers 1 and 2 over one chapter and merge them."""
    mentions: list[Mention] = []
    stats: dict[str, int] = {
        "generic": 0, "gazetteer": 0, "ner": 0, "parenthetical": 0,
        "common_noun": 0, "credit": 0,
    }
    credits = credits or set()

    def rejected(surface: str, *, label: str = "character") -> str | None:
        """Why a surface must not become an entity, or None.

        The determiner-rate test's premise is "a personal name is not preceded
        by 'the'/'a'" (commonness.py). That premise is specific to *people* --
        "the Spring Autumn Cicada" and "the Gu Yue clan" take a determiner as
        naturally as "the guard" does, because items, locations and
        organisations are ordinarily introduced with an article in English.
        Measured on RI ch1-5 gold: the filter deleted the central plot item
        (94.8% determiner rate) and the clan name (23.9%) outright, alongside
        the role nouns it was built to catch. `label` comes from layer 1's own
        classification, so this costs nothing extra to know -- it was already
        being computed and discarded at `_make_mention`.
        """
        if label == "character" and profile is not None and profile.is_common_noun(surface):
            return "common_noun"
        if surface in credits or looks_like_credit(surface):
            return "credit"
        return None

    for span in classify_chapter(chapter):
        if span.span_type in (SpanType.NON_DIEGETIC, SpanType.SYSTEM_WINDOW):
            continue

        text = span.text
        reference_mode = _reference_mode(span.span_type)

        # Layer 2 first: exact matches are higher precision and carry a target.
        gaz_hits = gazetteer.find(text)
        taken: list[tuple[int, int]] = [(h.start, h.end) for h in gaz_hits]

        for hit in gaz_hits:
            if not hit.alias_type.enters_graph:
                stats["generic"] += 1
                continue
            reason = rejected(hit.surface)
            if reason:
                stats[reason] += 1
                continue
            stats["gazetteer"] += 1
            mentions.append(
                _make_mention(
                    chapter,
                    span,
                    surface=hit.surface,
                    offset=span.start + hit.start,
                    alias_type=hit.alias_type,
                    reference_mode=reference_mode,
                    method=ResolutionMethod.GAZETTEER_EXACT,
                    target_id=hit.target_id,
                    confidence=0.95,
                    segment_id=segment_id,
                    index=len(mentions),
                )
            )

        # Layer 1: statistical spans, minus anything the gazetteer already has.
        for ner_span in detector.detect(text):
            if _overlaps(ner_span, taken):
                continue
            alias_type, confidence = classify_alias_type(ner_span.text, lexicon=lexicon)
            if not alias_type.enters_graph:
                stats["generic"] += 1
                continue
            reason = rejected(ner_span.text, label=ner_span.label)
            if reason:
                stats[reason] += 1
                continue
            stats["ner"] += 1
            taken.append((ner_span.start, ner_span.end))
            mentions.append(
                _make_mention(
                    chapter,
                    span,
                    surface=ner_span.text,
                    offset=span.start + ner_span.start,
                    alias_type=alias_type,
                    reference_mode=reference_mode,
                    method=ResolutionMethod.SCORED,
                    target_id=None,
                    confidence=min(confidence, ner_span.score),
                    segment_id=segment_id,
                    index=len(mentions),
                )
            )

        for paren in find_parentheticals(text, known_entities=known_entities):
            stats["parenthetical"] += 1
            stats[f"paren_{paren.kind.value}"] = stats.get(f"paren_{paren.kind.value}", 0) + 1

    return mentions, stats


def _overlaps(span: NerSpan, taken: list[tuple[int, int]]) -> bool:
    return any(s < span.end and span.start < e for s, e in taken)


def _make_mention(
    chapter: Chapter,
    span: object,
    *,
    surface: str,
    offset: int,
    alias_type: AliasType,
    reference_mode: ReferenceMode,
    method: ResolutionMethod,
    target_id: str | None,
    confidence: float,
    segment_id: str,
    index: int,
) -> Mention:
    span_type = getattr(span, "span_type", SpanType.NARRATION_ACTION)
    return Mention(
        block_index=getattr(span, "block_index", 0),
        id=f"{chapter.novel_id}:{chapter.number:g}:m{index}",
        novel_id=chapter.novel_id,
        segment_id=segment_id or f"{chapter.novel_id}:{chapter.number:g}:main0",
        chapter=chapter.number,
        offset=offset,
        text=surface,
        alias_type=alias_type,
        span_type=span_type,
        reference_mode=reference_mode,
        target_id=target_id,
        confidence=confidence,
        method=method,
    )


def detect_mentions(
    novel_id: str,
    store: Store,
    *,
    lexicon: Lexicon | None = None,
    detector: MentionDetector | None = None,
    settings: Settings | None = None,
    use_commonness_filter: bool = True,
    commit_every: int = 25,
    client: object | None = None,
) -> MentionReport:
    """Run mention detection over a whole novel.

    The gazetteer is seeded from the lexicon before reading starts, so
    transferable titles are recognised as titles from chapter one instead of
    being mistaken for names until evidence accumulates.

    When `client` is supplied, layer 1 becomes a two-step pass: one model call
    per chapter decides *which surface forms are names*, and those forms are
    then matched over the chapter's spans exactly. See `chapter_ner.py` for why
    the model is not asked for offsets.
    """
    cfg = settings or get_settings()
    lex = lexicon or Lexicon()
    report = MentionReport(novel_id=novel_id)

    #: Explicit detector wins; otherwise the model decides layer 1 per chapter.
    fixed_detector = detector or (None if client is not None else get_detector())
    chapter_ner = (
        get_detector(client, novel_id=novel_id) if client is not None and detector is None
        else None
    )
    report.detector_name = (
        chapter_ner.name if chapter_ner is not None else (fixed_detector or get_detector()).name
    )
    name_cache = (
        NameCache(
            Path(cfg.lexicon_path) / f"{novel_id}-ner-cache.json",
            model=getattr(client, "model_for", lambda _t: "")(Task.NER),
        )
        if chapter_ner is not None
        else None
    )

    # Grammatical pre-pass over the whole volume.
    #
    # Capitalisation cannot separate a role noun from a personal name in this
    # content -- both run ~0% lowercase. Determiner and plural *rates* can, and
    # both are corpus-derived, so this needs no model and no hand-written list.
    profile = None
    if use_commonness_filter:
        corpus = "\n".join(c.story_text for c in store.iter_chapters(novel_id))
        seeds, _ = seed_from_volume(novel_id, store, lexicon=lex)
        candidates = [c.surface for c in seeds.values()]
        profile = build_profile(corpus, candidates)
        report.credit_surfaces = credit_surfaces(corpus, candidates)

    gazetteer = Gazetteer()
    seed_from_lexicon(gazetteer, lex)
    gazetteer.build()

    known_entities: set[str] = set()
    #: Raw surfaces, for the model roster. `known_entities` holds comparison
    #: keys, which are normalised past the point of being readable in a prompt.
    known_entities_surface: set[str] = set()
    pending: list[Mention] = []
    window_index = 0
    window_gaz = 0
    window_total = 0

    for i, chapter in enumerate(store.iter_chapters(novel_id), start=1):
        segments = store.get_segments(novel_id, chapter.number)
        segment_id = segments[0].id if segments else ""

        det = fixed_detector
        if chapter_ner is not None:
            # The roster turns "find the characters" into "find the characters
            # not already listed", which is both easier and stops the model
            # re-deriving the same cast with a different spelling each chapter.
            names = extract_chapter_names(
                chapter_ner,
                chapter.story_text,
                known_names=sorted(known_entities_surface),
                chapter=chapter.number,
                cache=name_cache,
            )
            report.llm_calls += names.calls
            report.llm_surfaces += len(names.surfaces)
            report.llm_rejected += names.rejected
            det = VocabularyDetector(names.surfaces)

        assert det is not None
        mentions, stats = detect_mentions_in_chapter(
            chapter,
            gazetteer=gazetteer,
            lexicon=lex,
            detector=det,
            segment_id=segment_id,
            known_entities=frozenset(known_entities),
            profile=profile,
            credits=report.credit_surfaces,
        )

        pending.extend(mentions)
        report.chapters += 1
        report.mentions += len(mentions)
        report.dropped_generic += stats.get("generic", 0)
        report.dropped_common_noun += stats.get("common_noun", 0)
        report.dropped_credit += stats.get("credit", 0)
        window_gaz += stats.get("gazetteer", 0)
        window_total += stats.get("gazetteer", 0) + stats.get("ner", 0)

        for key, value in stats.items():
            if key.startswith("paren_"):
                name = key.removeprefix("paren_")
                report.parentheticals[name] = report.parentheticals.get(name, 0) + value

        for mention in mentions:
            report.by_alias_type[mention.alias_type.value] = (
                report.by_alias_type.get(mention.alias_type.value, 0) + 1
            )
            if mention.method:
                report.by_method[mention.method.value] = (
                    report.by_method.get(mention.method.value, 0) + 1
                )

        # Grow the vocabulary from rigid names seen this chapter. In the full
        # system the resolver confirms these; here they are provisional, which
        # is why they enter the gazetteer without a target id.
        for mention in mentions:
            if mention.alias_type is AliasType.RIGID_NAME and mention.confidence >= 0.7:
                lex.learn(mention.text)
                gazetteer.add(mention.text, AliasType.RIGID_NAME)
                from echotales.pipeline.ingest.normalize import comparison_key

                known_entities.add(comparison_key(mention.text))
                known_entities_surface.add(mention.text)

        # Window boundary: rebuild the automaton and record the hit rate.
        if i % cfg.window_size == 0:
            gazetteer.build()
            window_index += 1
            rate = window_gaz / window_total if window_total else 0.0
            report.gazetteer_hit_rate_by_window.append((window_index, rate))
            window_gaz = window_total = 0

        if i % commit_every == 0:
            store.add_mentions(pending)
            store.conn.commit()
            pending.clear()
            # Flushed on the same cadence as the store commit, not only at the
            # end. A 199-chapter run is ~35 minutes of GPU time; losing it to
            # an interruption at chapter 175 because the cache only wrote once
            # at the very end happened once already during this project.
            if name_cache is not None:
                name_cache.flush()

    if pending:
        store.add_mentions(pending)
    store.conn.commit()

    if window_total:
        window_index += 1
        report.gazetteer_hit_rate_by_window.append(
            (window_index, window_gaz / window_total)
        )
    if name_cache is not None:
        name_cache.flush()
    report.gazetteer_size = len(gazetteer)
    return report
