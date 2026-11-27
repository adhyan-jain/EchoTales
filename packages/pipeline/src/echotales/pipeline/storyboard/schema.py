"""The storyboard contract: what the director decides and what pages/video render.

Why this exists (docs/results/MANHWA_DIRECTING_PATTERNS.md): v57 drew one 3:4
panel per text block, so panel count, shape, captions and cast all followed the
text's paragraphing. Real adapters decide those per beat. They put only the
people present in a scene into it, show people who are merely talked about as
insets, give each narrative layer its own look, and signal every scene cut.
Every field below is one of those decisions, made once by the director and
read by the composer, the lettering, the image prompt and the video, so that
none of them re-derives it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Layer(StrEnum):
    """Visual layer. Each layer gets one consistent treatment per work (grammar rule 2)."""

    PRESENT = "present"
    PAST = "past"  # earlier story time shown straight (a flashback scene, a prior loop)
    MEMORY = "memory"  # reminiscence or montage inside a character's head
    LORE = "lore"  # prologue or world history told by a narrator
    IMAGINED = "imagined"  # someone talked about or pictured, not present
    DREAM = "dream"


class Purpose(StrEnum):
    COLD_OPEN = "cold_open"  # hook before exposition: SFX spread or striking image
    TITLE_CARD = "title_card"
    TIME_PLACE_CARD = "time_place_card"  # text-only beat: "6 hours pass", "Gu Yue Village"
    ESTABLISHING = "establishing"
    BEAT = "beat"  # a story action
    DIALOGUE = "dialogue"
    REACTION = "reaction"  # the listener's face
    INSERT = "insert"  # hand, object, blood drop, lantern
    EXTREME_CLOSE = "extreme_close"  # eyes or mouth at a peak
    HERO = "hero"  # full-figure presentation of a key character
    CROWD_INDIVIDUAL = "crowd_individual"  # one face pulled out of an anonymous crowd
    REFERENCED_INSET = "referenced_inset"  # a person who is talked about, shown apart
    MONTAGE = "montage"
    SYMBOLIC = "symbolic"
    TRANSITION = "transition"  # graphic match carrying a scene cut
    NAME_CARD = "name_card"


class Shape(StrEnum):
    STANDARD = "standard"
    WIDE = "wide"  # full-width short strip: space, crowds, armies
    TALL = "tall"  # heroes, falls, explosions
    DIAGONAL = "diagonal"  # clashes, confrontations
    INSET = "inset"  # small, overlapping its neighbour: asides, referenced people
    BLEED = "bleed"  # borderless peak
    TEXT_ONLY = "text_only"  # caption or card on gutter colour, no image


class Shot(StrEnum):
    EXTREME_WIDE = "extreme_wide"
    WIDE = "wide"
    MEDIUM = "medium"
    MEDIUM_CLOSE = "medium_close"
    CLOSE = "close"
    EXTREME_CLOSE = "extreme_close"
    INSERT = "insert"
    OVERHEAD = "overhead"
    LOW_ANGLE = "low_angle"


class LetterKind(StrEnum):
    SPEECH = "speech"
    SHOUT = "shout"
    WHISPER = "whisper"
    DREAD = "dread"
    THOUGHT = "thought"
    MEMORY = "memory"
    NARRATION = "narration"
    TIME_PLACE = "time_place"
    NAME_CARD = "name_card"
    POEM = "poem"
    SFX = "sfx"  # drawn into the art by the lettering pass, not a balloon


class Letter(BaseModel):
    kind: LetterKind
    text: str
    speaker_id: str | None = None  # entity id; None for narration, cards and SFX
    source_span_id: str | None = None  # None only for invented SFX or cards


class CastMember(BaseModel):
    entity_id: str
    name: str
    #: The look this person has at this story time (look-by-epoch). The director
    #: copies it from the bible; it never invents one.
    look_id: str | None = None
    invented: bool = False  # an individualised crowd face; never a plot actor


class Panel(BaseModel):
    panel_id: str
    segment_id: str
    layer: Layer
    purpose: Purpose
    shape: Shape = Shape.STANDARD
    shot: Shot = Shot.MEDIUM
    #: Only people physically in this scene (grammar rule 4). People who are
    #: talked about go in a REFERENCED_INSET panel with layer IMAGINED.
    cast: list[CastMember] = Field(default_factory=list)
    visual: str = ""  # what is drawn, in plain words, no style words
    letters: list[Letter] = Field(default_factory=list)
    source_blocks: list[int] = Field(default_factory=list)
    invented: bool = False
    invented_reason: str = ""


class Segment(BaseModel):
    """One scene: a single place, time and layer."""

    segment_id: str
    chapter: float
    block_from: int
    block_to: int  # inclusive
    layer: Layer
    story_time: str = ""  # human-readable, e.g. "500 years before the cliff"
    place: str = ""
    present_cast: list[CastMember] = Field(default_factory=list)
    referenced_cast: list[CastMember] = Field(default_factory=list)
    palette: str = ""  # the layer or mood treatment key, see compiler palettes
    cut_signal: str = ""  # how the cut into this segment is shown: card, match, establishing


class Storyboard(BaseModel):
    novel_id: str
    chapter: float
    model_id: str = ""
    segments: list[Segment] = Field(default_factory=list)
    panels: list[Panel] = Field(default_factory=list)
