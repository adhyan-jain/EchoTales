"""Controlled vocabularies for the narrative knowledge graph.

Every value here is load-bearing. In particular see `EventType`, where `RETRACT`
and `CLOSE_INTERVAL` are deliberately distinct members: plans.md Section 4.3 makes the
distinction non-negotiable, and collapsing them silently corrupts the graph.
"""

from __future__ import annotations

from enum import StrEnum


class TargetKind(StrEnum):
    """What a fact attaches to.

    Attributes route by kind: appearance/age/attire/voice-timbre belong to a
    PERSONA (the body that gets drawn and voiced); role/status/relationships/
    knowledge belong to a SELF (the continuity of consciousness).

    MOB_GROUP is neither: "a crowd of disciples" is not one continuity of
    consciousness and never becomes one, so it must never be minted as a
    `Self` the way an individual character is -- see
    `spans/scene.py::detect_mobs`, which deliberately never mints a `Mention`
    or entity row at all, only a scene-scoped descriptor for panel casting.
    This member exists so a future consumer (voice/persona casting) has a
    real value to tag a background element with, distinct from an unnamed
    individual (see `speakers/runner.py::_assign_anonymous_slots`, which is
    the anonymous-*individual* case and is unrelated to this one).
    """

    SELF = "SELF"
    PERSONA = "PERSONA"
    MOB_GROUP = "MOB_GROUP"

    #: Non-person entities. Phase 6 mints an entity row for every resolved
    #: name regardless of what it denotes, because a name is a name; these
    #: members are what stop a place or a plot item from then *behaving* like
    #: a character downstream (Section 10 item 5). Nothing is deleted -- "the Gu Yue
    #: clan" and "the Spring Autumn Cicada" are real, retrievable entities
    #: worth resolving, they simply must never be cast a speaking voice or
    #: drawn as a person. `is_person` is the check consumers should use.
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    ITEM = "ITEM"

    @property
    def is_person(self) -> bool:
        """Whether facts about appearance, voice and speech make sense here.

        The one question every downstream consumer (voice casting, panel
        casting, the review cast list) actually needs answered. `MOB_GROUP`
        is excluded deliberately: a crowd is people, but it is not *a*
        person, and it has no single voice or face to bind.
        """
        return self in (TargetKind.SELF, TargetKind.PERSONA)


class AliasType(StrEnum):
    """plans.md Section 4.1.

    `GENERIC_DESCRIPTOR` is the important one: it is *not* a binding and must
    never reach the graph. Keeping it out eliminates the largest class of false
    matches and false title transfers.
    """

    RIGID_NAME = "RIGID_NAME"
    TRANSFERABLE_TITLE = "TRANSFERABLE_TITLE"
    RELATIONAL_DEICTIC = "RELATIONAL_DEICTIC"
    EPITHET = "EPITHET"
    PATHWAY_TITLE = "PATHWAY_TITLE"
    TAROT_TITLE = "TAROT_TITLE"
    GENERIC_DESCRIPTOR = "GENERIC_DESCRIPTOR"

    @property
    def enters_graph(self) -> bool:
        """Whether a binding of this type may be persisted. See non-negotiable #4."""
        return self is not AliasType.GENERIC_DESCRIPTOR

    @property
    def is_transfer_eligible(self) -> bool:
        """Whether this alias can move between holders over time."""
        return self in (
            AliasType.TRANSFERABLE_TITLE,
            AliasType.PATHWAY_TITLE,
            AliasType.TAROT_TITLE,
        )

    @property
    def is_speaker_relative(self) -> bool:
        """Whether resolution requires knowing who is speaking."""
        return self is AliasType.RELATIONAL_DEICTIC


class SpanType(StrEnum):
    """plans.md Section 5. Drives both generation pipelines."""

    DIALOGUE = "DIALOGUE"
    NARRATION_ACTION = "NARRATION_ACTION"
    NARRATION_DESCRIPTION = "NARRATION_DESCRIPTION"
    NARRATION_EXPOSITION = "NARRATION_EXPOSITION"
    INNER_MONOLOGUE = "INNER_MONOLOGUE"
    CROWD_REACTION = "CROWD_REACTION"
    SYSTEM_WINDOW = "SYSTEM_WINDOW"
    NON_DIEGETIC = "NON_DIEGETIC"

    @property
    def is_spoken_aloud(self) -> bool:
        return self is SpanType.DIALOGUE

    @property
    def is_renderable_visually(self) -> bool:
        """NARRATION_EXPOSITION is kept in audio but skipped in panels."""
        return self in (
            SpanType.DIALOGUE,
            SpanType.NARRATION_ACTION,
            SpanType.NARRATION_DESCRIPTION,
        )


class ReferenceMode(StrEnum):
    """Whether a mention denotes someone physically in the scene.

    Only PRESENT characters get drawn in panels and only PRESENT characters
    count for voice-collision avoidance. Without this, a chapter that merely
    *names* nine characters produces a panel containing nine characters, most
    of them absent or dead.
    """

    PRESENT = "PRESENT"
    DIALOGUE_REFERENCE = "DIALOGUE_REFERENCE"
    NARRATOR_REFERENCE = "NARRATOR_REFERENCE"
    MEMORY_REFERENCE = "MEMORY_REFERENCE"
    INNER_THOUGHT_REFERENCE = "INNER_THOUGHT_REFERENCE"

    @property
    def is_physically_present(self) -> bool:
        return self is ReferenceMode.PRESENT


class TruthStatus(StrEnum):
    """plans.md Section 4.3.

    FABRICATED means an identity invented wholesale rather than impersonating
    a real person -- Fang Yuan's "Wu Yi Hai" is fabricated, not a disguise
    *of* an existing Wu Yi Hai.
    """

    TRUE = "TRUE"
    CLAIMED = "CLAIMED"
    CONTESTED = "CONTESTED"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"
    FABRICATED = "FABRICATED"
    INFERRED = "INFERRED"


class AssertedBy(StrEnum):
    """Provenance of an assertion, used to weight and to filter."""

    NARRATOR = "NARRATOR"
    CHARACTER = "CHARACTER"
    RUMOUR = "RUMOUR"
    SYSTEM_WINDOW = "SYSTEM_WINDOW"
    INFERENCE = "INFERENCE"


class SegmentType(StrEnum):
    """plans.md Section 2.4."""

    MAIN = "MAIN"
    FLASHBACK_OWN = "FLASHBACK_OWN"
    DREAM_OTHER = "DREAM_OTHER"
    VISION = "VISION"
    PROPHECY = "PROPHECY"
    HEARSAY = "HEARSAY"
    REGRESSION_PRIOR_LOOP = "REGRESSION_PRIOR_LOOP"
    ILLUSION = "ILLUSION"


class NarrativeLayer(StrEnum):
    """Generation-facing grouping: determines visual style and cast scoping."""

    MAIN = "MAIN"
    FLASHBACK_OWN = "FLASHBACK_OWN"
    DREAM_OTHER = "DREAM_OTHER"
    VISION = "VISION"
    PROPHECY = "PROPHECY"


class Canonicity(StrEnum):
    """VOIDED spans stay queryable for 'what did the reader believe then'."""

    CANONICAL = "CANONICAL"
    VOIDED = "VOIDED"
    DISPUTED = "DISPUTED"


class BlockType(StrEnum):
    """Phase 0 block-level classification (plans.md Section 6 Phase 0)."""

    PROSE = "PROSE"
    DIALOGUE = "DIALOGUE"
    SYSTEM_WINDOW = "SYSTEM_WINDOW"
    AUTHOR_NOTE = "AUTHOR_NOTE"
    TRANSLATOR_NOTE = "TRANSLATOR_NOTE"
    NON_DIEGETIC = "NON_DIEGETIC"
    HEADING = "HEADING"

    @property
    def is_story_content(self) -> bool:
        """Whether this block feeds identity processing."""
        return self in (BlockType.PROSE, BlockType.DIALOGUE, BlockType.SYSTEM_WINDOW)


class EventType(StrEnum):
    """Append-only log vocabulary (plans.md Section 5).

    RETRACT vs CLOSE_INTERVAL is the distinction that matters most:

    - CLOSE_INTERVAL -- "was true, then stopped being true" (title transferred)
    - RETRACT        -- "was NEVER true; we were misinformed" (impostor unmasked)
    """

    NEW_ENTITY = "new_entity"
    NEW_PERSONA = "new_persona"
    LINK = "link"
    MERGE = "merge"
    SPLIT = "split"
    REBIND = "rebind"
    RETRACT = "retract"
    CLOSE_INTERVAL = "close_interval"
    VOID_SPAN = "void_span"
    REMAP_SEGMENT = "remap_segment"
    PERSONA_BIND = "persona_bind"
    PERSONA_UNBIND = "persona_unbind"
    ATTRIBUTE_UPDATE = "attribute_update"
    RELATION_UPDATE = "relation_update"
    REPUTATION_SPREAD = "reputation_spread"
    TIME_SKIP = "time_skip"
    DEATH = "death"
    RESURRECTION = "resurrection"


class Decision(StrEnum):
    """Three-way gate output from the global resolver (plans.md Section 6 Phase 6)."""

    LINK = "LINK"
    NEW = "NEW"
    DEFER = "DEFER"


class Prominence(StrEnum):
    """plans.md Section 6 Phase 8. Determines generation budget per entity."""

    PRINCIPAL = "PRINCIPAL"
    RECURRING = "RECURRING"
    INCIDENTAL = "INCIDENTAL"


class Provenance(StrEnum):
    """Annotation provenance.

    The dataset is machine-generated (silver). Only HUMAN_VERIFIED records may
    back reported evaluation numbers -- scoring the resolver against its own
    output measures self-consistency, not accuracy.
    """

    MACHINE = "MACHINE"
    HUMAN_VERIFIED = "HUMAN_VERIFIED"
    HUMAN_AUTHORED = "HUMAN_AUTHORED"


class AttributionMethod(StrEnum):
    """Which tier of the speaker-attribution ladder produced an answer."""

    EXPLICIT = "EXPLICIT"
    PROXIMAL = "PROXIMAL"
    #: Legacy only -- the tier that produced this (`attribute_turn_taking`)
    #: was removed (Section 3.3, 2026-09-05): empirically wrong 82.9% of the
    #: time against RI ch1-59 (n=105), see `speakers/attribution.py`'s module
    #: docstring. Kept in the enum only so a span written before this change
    #: still deserialises; no code path produces this value anymore.
    TURN_TAKING = "TURN_TAKING"
    CONTEXTUAL_LLM = "CONTEXTUAL_LLM"
    JOINT = "JOINT"
    UNATTRIBUTED_CHORUS = "UNATTRIBUTED_CHORUS"
    POV_INFERRED = "POV_INFERRED"
    UNRESOLVED = "UNRESOLVED"
    #: A turn-taking guess assigned no real identity, only a locally-scoped
    #: "not the same speaker as the last line" slot -- see
    #: `speakers/runner.py::_assign_anonymous_slots`. Distinct from
    #: UNRESOLVED so a consumer can tell "genuinely nobody" from "some
    #: consistent nobody in particular."
    ANONYMOUS_SLOT = "ANONYMOUS_SLOT"
    #: A role-title speaker tag with no proper name attached ("the clan head
    #: instructed") -- see `speakers/attribution.py::attribute_epithet`.
    #: Distinct from ANONYMOUS_SLOT: the text itself names *who*, just by
    #: title rather than name, so this gets one stable id keyed by the title
    #: instead of a round-robin slot -- distinct from EXPLICIT too, since a
    #: title is never promoted into the entity graph the way a name is.
    EPITHET_SLOT = "EPITHET_SLOT"


class ResolutionMethod(StrEnum):
    """How an identity decision was reached. Feeds the escalation-ladder metric."""

    GAZETTEER_EXACT = "GAZETTEER_EXACT"
    DECLARATION = "DECLARATION"
    SCORED = "SCORED"
    LLM_ADJUDICATED = "LLM_ADJUDICATED"
    DEFERRED_RERESOLVED = "DEFERRED_RERESOLVED"
    MANUAL = "MANUAL"


# The observer whose knowledge-time equals the discourse position: the reader
# knows a fact the moment it is narrated.
OBSERVER_READER = "READER"

# The omniscient observer, used for evaluation and debugging. SYSTEM sees facts
# whose truth_status is FALSE, which no in-world observer may.
OBSERVER_SYSTEM = "SYSTEM"
