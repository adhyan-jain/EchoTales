"""Pydantic models for the narrative knowledge graph (plans.md Section 5).

Two ideas shape this module and are worth stating before the code.

**Chapter number is not a time coordinate.** A single chapter may contain
present action, a dream replaying someone else's past, the protagonist's own
past-life memories, and exposition about offscreen politics. So position is
split three ways: `DiscoursePosition` (where in the text -- always a total
order), story time (`timeline_id` + a `FuzzyInterval` -- only a partial order),
and knowledge time (`learned_at_pos` + `observer_id`).

**Self is not persona.** A `Self` is a continuity of consciousness and owns
memory, roles and relationships. A `Persona` is a body and owns appearance,
age and voice timbre. Generation binds to personas; the story binds to selves.
One self with several concurrent personas is a disguise or a clone; two selves
contesting one persona is possession.
"""

from __future__ import annotations

from typing import Annotated, Literal
from typing import Self as SelfType

from echotales.core.enums import (
    AliasType,
    AssertedBy,
    AttributionMethod,
    BlockType,
    Canonicity,
    Decision,
    EventType,
    NarrativeLayer,
    Prominence,
    Provenance,
    ReferenceMode,
    ResolutionMethod,
    SegmentType,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval, StoryPos
from pydantic import BaseModel, ConfigDict, Field, model_validator

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]

MAIN_TIMELINE = "MAIN_TIMELINE"


class DiscoursePosition(BaseModel):
    """Where in the text something occurs: `(chapter, paragraph_offset)`.

    Always a total order and never ambiguous -- unlike story time. Used for
    "when did the reader learn X", gazetteer growth ordering, and confidence
    decay.
    """

    model_config = ConfigDict(frozen=True)

    chapter: int
    offset: int = 0

    def __lt__(self, other: DiscoursePosition) -> bool:
        return (self.chapter, self.offset) < (other.chapter, other.offset)

    def __le__(self, other: DiscoursePosition) -> bool:
        return (self.chapter, self.offset) <= (other.chapter, other.offset)

    def __gt__(self, other: DiscoursePosition) -> bool:
        return (self.chapter, self.offset) > (other.chapter, other.offset)

    def __ge__(self, other: DiscoursePosition) -> bool:
        return (self.chapter, self.offset) >= (other.chapter, other.offset)

    def as_sortable(self) -> int:
        """Flatten to a single sortable integer for SQL ORDER BY / indexing."""
        return self.chapter * 1_000_000 + self.offset

    @classmethod
    def from_sortable(cls, value: int) -> DiscoursePosition:
        return cls(chapter=value // 1_000_000, offset=value % 1_000_000)

    def __str__(self) -> str:
        return f"ch{self.chapter}:{self.offset}"


# ---------------------------------------------------------------------------
# Phase 0 ingestion products
# ---------------------------------------------------------------------------


class Block(BaseModel):
    """A classified block of a chapter, before span-level analysis.

    `text` is the extracted plain text. `italic_ranges` records character
    offsets that were emphasised in the source markup -- an independent signal
    for inner monologue that only survives because ingestion is EPUB-based.
    """

    index: int
    block_type: BlockType
    text: str
    italic_ranges: list[tuple[int, int]] = Field(default_factory=list)
    # Populated only for SYSTEM_WINDOW blocks: the parsed key-value payload,
    # which is the highest-precision attribute source in the whole novel.
    system_fields: dict[str, str] = Field(default_factory=dict)


class Chapter(BaseModel):
    """One ingested chapter.

    `number` comes from the table of contents, never from the source filename:
    the RI export names Chapter 1 as `page-0.html`, and split chapters like
    45.1 have no filename representation at all.
    """

    novel_id: str
    number: float
    title: str
    source_href: str
    blocks: list[Block]

    @property
    def story_text(self) -> str:
        """Concatenated text of blocks that feed identity processing."""
        return "\n\n".join(b.text for b in self.blocks if b.block_type.is_story_content)


class Span(BaseModel):
    """A classified span within a chapter (plans.md Section 6 Phase 1)."""

    id: str
    novel_id: str
    chapter: float
    block_index: int
    start: int
    end: int
    span_type: SpanType
    text: str
    speaker_self_id: str | None = None
    attribution_method: AttributionMethod = AttributionMethod.UNRESOLVED
    # Additional speakers for joint attribution ("X and Y both replied").
    co_speaker_self_ids: list[str] = Field(default_factory=list)
    # Delivery markers ("said calmly", "expressionless") override scene-level
    # sentiment at synthesis time. Non-negotiable #10.
    delivery_markers: list[str] = Field(default_factory=list)
    confidence: Confidence = 1.0

    @property
    def position(self) -> DiscoursePosition:
        return DiscoursePosition(chapter=int(self.chapter), offset=self.start)


# ---------------------------------------------------------------------------
# Narrative segmentation
# ---------------------------------------------------------------------------


class NarrativeSegment(BaseModel):
    """Maps a discourse span onto a story-time span (plans.md Section 2.4).

    Default behaviour is one chapter -> one MAIN segment with
    `story_seq = chapter index`, which reduces the whole temporal apparatus to
    naive behaviour for linear novels. Non-linear segments are an override,
    applied only on high confidence: a missed flashback costs one temporal
    misattribution, while a false flashback costs that *plus* a spurious
    timeline that later facts get attached to.
    """

    id: str
    novel_id: str
    chapter_from: float
    offset_from: int
    chapter_to: float
    offset_to: int
    timeline_id: str = MAIN_TIMELINE
    story_seq_from: StoryPos
    story_seq_to: StoryPos
    segment_type: SegmentType = SegmentType.MAIN
    narrative_layer: NarrativeLayer = NarrativeLayer.MAIN
    canonicity: Canonicity = Canonicity.CANONICAL
    confidence: Confidence = 1.0

    def contains(self, pos: DiscoursePosition) -> bool:
        lo = (self.chapter_from, self.offset_from)
        hi = (self.chapter_to, self.offset_to)
        return lo <= (float(pos.chapter), pos.offset) <= hi


class SceneState(BaseModel):
    """The shared, scene-level ground truth a panel/voice/etc. consumer reads
    as a floor, not a final answer -- local, per-beat detail may refine or
    override it without mutating the stored row (query-time override, not
    a write).

    Deliberately vocabulary-free: `location`, `crowd_mood` and
    `default_severity` are opaque tags a *consumer* defines an ordering/
    vocabulary for (e.g. the render pipeline's locale strings, or its
    condition-ladder tiers) -- this model does not know what a "crowd" or a
    "robe" is, matching `NarrativeSegment`'s own segment_type/layer being
    enums *consumers* interpret, not this module inventing genre concepts.
    """

    id: str
    novel_id: str
    segment_id: str
    location: str = ""
    crowd_mood: str | None = None
    default_severity: str = ""
    extra: dict[str, str] = Field(default_factory=dict)
    set_at_position: DiscoursePosition
    closed: bool = False


# ---------------------------------------------------------------------------
# Entities: self / persona
# ---------------------------------------------------------------------------


class Self(BaseModel):
    """A continuity of consciousness.

    Survives reincarnation, body-swap and disguise. Owns memory, relationships,
    roles and knowledge state -- never appearance.

    **`kind` is the exception to that description, and it is deliberate.**
    Phase 6 resolves every recurring *name* into a row here, and not every
    name denotes a person -- "the Gu Yue clan" and "the Spring Autumn Cicada"
    are real, retrievable, worth-resolving entities that are not continuities
    of consciousness. Deleting them was tried and over-deleted real content
    (see `mentions/runner.py::rejected`), so instead they are kept and
    *typed*, and `kind.is_person` is what stops them being cast a voice or
    drawn as a character. A row whose `kind` is not `SELF` is an entity that
    happens to live in this table, not a claim that a place has a mind.
    """

    id: str
    novel_id: str
    canonical_label: str
    first_attested_pos: DiscoursePosition
    prominence: Prominence = Prominence.INCIDENTAL
    notes: str = ""
    kind: TargetKind = TargetKind.SELF


class Persona(BaseModel):
    """A physical embodiment.

    Owns appearance, age, attire and voice timbre. This is what image
    generation and TTS bind to.
    """

    id: str
    novel_id: str
    body_label: str
    first_attested_pos: DiscoursePosition
    notes: str = ""


class SelfPersonaBinding(BaseModel):
    """Which body a consciousness inhabits, over a story-time interval.

    Concurrent bindings for one self are legitimate and load-bearing: they are
    how clones, soul avatars and sustained parallel disguises are represented.
    Overlapping bindings from *different* selves onto one persona represent
    possession.
    """

    self_id: str
    persona_id: str
    timeline_id: str = MAIN_TIMELINE
    interval: FuzzyInterval
    learned_at_pos: DiscoursePosition
    observer_id: str
    truth_status: TruthStatus = TruthStatus.TRUE
    confidence: Confidence = 1.0


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


class TemporalFact(BaseModel):
    """Fields shared by every time-and-observer-scoped assertion.

    `retracted_at` is *not* an interval end. An interval end says the fact was
    true and stopped; a retraction says it was never true and we were
    misinformed. Two different questions, two different fields, two different
    event types.
    """

    timeline_id: str = MAIN_TIMELINE
    interval: FuzzyInterval
    learned_at_pos: DiscoursePosition
    observer_id: str
    asserted_by: AssertedBy = AssertedBy.NARRATOR
    truth_status: TruthStatus = TruthStatus.TRUE
    retracted_at: DiscoursePosition | None = None
    evidence: str = ""
    confidence: Confidence = 1.0

    @property
    def is_standing(self) -> bool:
        return self.retracted_at is None


class AliasBinding(TemporalFact):
    """A surface form bound to an entity over an interval.

    Alias -> target is one-to-many at any given time: "Elder", "Senior Brother"
    and "Young Master" are each held by many people simultaneously. The
    temporal index is therefore a candidate-set *filter*, not a resolver; it
    narrows the pool and contextual scoring decides.
    """

    alias: str
    alias_type: AliasType
    target_kind: TargetKind
    target_id: str

    @model_validator(mode="after")
    def _reject_generic_descriptors(self) -> SelfType:
        """Non-negotiable #4, enforced at the type level.

        Generic descriptors ("the innkeeper", "that woman") are scene-local and
        never enter the graph. Blocking construction here means no call site
        can persist one by accident.
        """
        if not self.alias_type.enters_graph:
            raise ValueError(
                f"{self.alias_type} may never be persisted as a binding "
                f"(alias={self.alias!r}); generic descriptors are scene-local only"
            )
        return self


class Attribute(TemporalFact):
    """A key-value property of a self or persona.

    Routing is by `target_kind`: appearance/age/attire on personas, role/status/
    knowledge on selves. Getting this wrong means a disguised character's
    reference image inherits their true face.
    """

    target_kind: TargetKind
    target_id: str
    key: str
    value: str


class Relation(TemporalFact):
    """A typed relationship between two selves (never personas)."""

    src_self: str
    dst_self: str
    type: str


class Mention(BaseModel):
    """One textual reference to an entity."""

    id: str
    novel_id: str
    segment_id: str
    chapter: float
    #: Character offset within the block. NOT comparable with a
    #: NarrativeSegment's offset_from/offset_to, which are block indices --
    #: conflating the two units silently mis-assigns mentions to timelines.
    offset: int
    text: str
    alias_type: AliasType
    span_type: SpanType
    reference_mode: ReferenceMode
    speaker_self_id: str | None = None
    target_kind: TargetKind | None = None
    target_id: str | None = None
    local_group_id: str | None = None
    confidence: Confidence = 1.0
    method: ResolutionMethod | None = None
    provenance: Provenance = Provenance.MACHINE
    #: Index of the containing block. Segments express their bounds in block
    #: indices, so this -- not `offset` -- is what timeline lookup must use.
    block_index: int = 0
    #: NER's own semantic label ("character"/"location"/"organization"),
    #: when the mention came from the LLM layer. `None` for mentions from the
    #: gazetteer or other sources that never had one to give. Not used to
    #: gate what enters the graph (see `mentions/runner.py`'s `rejected()`
    #: docstring on why a blunt kind filter over-deletes real entities like a
    #: clan name or a plot item) -- only to flag a newly-created `Self` for
    #: human review when it was founded mostly on non-character mentions.
    entity_label: str | None = None

    @property
    def position(self) -> DiscoursePosition:
        return DiscoursePosition(chapter=int(self.chapter), offset=self.offset)


class Observation(BaseModel):
    """Who learned which fact, and when."""

    observer_id: str
    fact_ref: str
    learned_at_pos: DiscoursePosition


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


class ResolutionEvent(BaseModel):
    """One entry in the append-only log.

    `read_set_hash` records which graph facts the decision consulted. Cache
    invalidation is then a set intersection against the facts a later event
    changed, rather than a full reprocess.
    """

    id: str
    seq: int
    type: EventType
    payload: dict[str, object]
    cause_pos: DiscoursePosition
    read_set_hash: str = ""
    method: ResolutionMethod | None = None
    confidence: Confidence = 1.0


# ---------------------------------------------------------------------------
# Resolver intermediate products
# ---------------------------------------------------------------------------


class EvidenceVector(BaseModel):
    """Structured evidence for one (mention, candidate) pair.

    Deliberately a vector rather than a scalar similarity. Clustering on a
    single similarity score fails on this content in both directions: "Fang
    Yuan" and "Liu Guan Yi" share no surface form yet are one self, while two
    unrelated "Elder Wang"s share every character.

    `temporal_validity` is a filter rather than a scorer, and
    `first_attested_soft_prior` is deliberately weak so a late reveal can
    override it (plans.md Section 4.4).
    """

    declaration_match: float = 0.0
    gazetteer_exact_match: float = 0.0
    surface_similarity: float = 0.0
    #: One name is the other with a leading house prefix dropped, sharing a
    #: two-or-more-token tail. Kept separate from `surface_similarity` because
    #: it is categorical and pre-filtered, while character-level similarity is
    #: gradual and scored — folding them into one field would let an ordinary
    #: high Jaro-Winkler score between two different names force a link.
    name_containment: float = 0.0
    context_embedding_similarity: float = 0.0
    speech_partner_compatibility: float = 0.0
    temporal_validity: float = 1.0
    co_presence_violation: float = 0.0
    audience_scope_compatibility: float = 0.0
    relationship_deictic_resolution: float = 0.0
    first_attested_soft_prior: float = 0.0

    def as_ordered_pairs(self) -> list[tuple[str, float]]:
        """Feature order is fixed so weights stay aligned across runs."""
        return [(name, getattr(self, name)) for name in FEATURE_ORDER]

    def as_list(self) -> list[float]:
        return [getattr(self, name) for name in FEATURE_ORDER]


FEATURE_ORDER: tuple[str, ...] = (
    "declaration_match",
    "gazetteer_exact_match",
    "name_containment",
    "surface_similarity",
    "context_embedding_similarity",
    "speech_partner_compatibility",
    "temporal_validity",
    "co_presence_violation",
    "audience_scope_compatibility",
    "relationship_deictic_resolution",
    "first_attested_soft_prior",
)

#: The features actually fed to the log-linear model.
#:
#: Deliberately five, not ten. Three of the original features were removed from
#: scoring because they are *decisions*, not evidence, and scoring them was the
#: direct cause of runaway over-merging:
#:
#: - `declaration_match` and `gazetteer_exact_match` are now hard pre-filters.
#:   As weighted features they drove probability to 0.96 on their own, and
#:   because an entity's alias set grows with every link, each wrong link made
#:   the next one easier. Self-reinforcing error.
#: - `co_presence_violation` is now a hard blocker. Two entities simultaneously
#:   present doing different things is one of the few near-certain negatives
#:   available; letting other features outvote it wastes that certainty.
#:
#: The remaining five are dense — they take meaningful values on most pairs —
#: so a weight fitted on a realistic number of gold instances is defensible.
#: The rejected ones are rare and high-weight, where "learned" would have meant
#: "hand-initialised with a few dozen examples of noise on top".
SCORED_FEATURES: tuple[str, ...] = (
    "surface_similarity",
    "context_embedding_similarity",
    "speech_partner_compatibility",
    "temporal_validity",
    "first_attested_soft_prior",
)


class Candidate(BaseModel):
    """A retrieved entity under consideration for a mention."""

    target_kind: TargetKind
    target_id: str
    label: str
    retrieval_score: float
    evidence: EvidenceVector = Field(default_factory=EvidenceVector)
    score: float = 0.0
    probability: float = 0.0


class ResolutionOutcome(BaseModel):
    """The gate's verdict for one local mention group."""

    group_id: str
    decision: Decision
    target_kind: TargetKind | None = None
    target_id: str | None = None
    probability: float = 0.0
    method: ResolutionMethod = ResolutionMethod.SCORED
    candidates: list[Candidate] = Field(default_factory=list)
    rationale: str = ""


class StateOfResult(BaseModel):
    """The answer to the central query.

    `certainty` is the aggregate over the facts that produced it, so callers
    can distinguish "we know this" from "this is the best reading available".
    """

    target_kind: TargetKind
    target_id: str
    timeline_id: str
    position: StoryPos
    observer_id: str
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    relationships: list[tuple[str, str]] = Field(default_factory=list)
    persona_ids: list[str] = Field(default_factory=list)
    truth_status: TruthStatus = TruthStatus.TRUE
    certainty: Literal["CERTAIN", "PLAUSIBLE", "EXCLUDED"] = "CERTAIN"
    read_set: list[str] = Field(default_factory=list)
