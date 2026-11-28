"""The model's answer for one window, kept small on purpose.

The model never retypes source text: it names lines by tag (`s12`) and the director copies the text. Two measured
reasons (qwen2.5 on RI ch1 in the render director, HANDOFF 4.51): a model that retypes a line paraphrases it, and the
retyped copy costs as many output tokens as the panel plan itself, which on an 8 GB card is the latency budget.
Only invented SFX and cards carry model-written text, and a validator caps and checks those.
"""

from __future__ import annotations

from echotales.pipeline.storyboard.schema import Layer, LetterKind, Purpose, Shape, Shot
from pydantic import BaseModel, Field


class LLetter(BaseModel):
    ref: str = Field(description="the line tag such as s12, copied from the passage; never the text itself")
    kind: LetterKind


class LPanel(BaseModel):
    purpose: Purpose
    shape: Shape
    shot: Shot
    layer: Layer
    cast: list[str] = Field(default_factory=list, description="names of people physically in the panel")
    visual: str = Field("", description="what is drawn, plain words, no style words, nothing the text does not state")
    letters: list[LLetter] = Field(default_factory=list, description="source lines this panel carries, by tag")
    sfx: list[str] = Field(default_factory=list, description="drawn sound words, each at most 3 words, e.g. THUD")
    card: str = Field("", description="caption text for a time_place_card or name_card panel, at most 6 words")
    blocks: list[int] = Field(default_factory=list, description="source block numbers this panel draws from")
    peak: bool = Field(False, description="true on the climax panel of a beat")
    invented: bool = Field(False, description="true when no source text covers the panel (an insert, a card)")
    reason: str = Field("", description="why an invented panel exists; starts with text:, dossier: or brief: and the cited item")
    emotion: str = Field("", description="the feeling this panel plays, one or two words")
    withheld: bool = Field(False, description="true when the text hides who this is yet: draw only the clue, no person")
    cut_signal: str = Field("", description="match on a transition panel that cuts to a parallel scene")
    beat: str = Field("", description="foreshadow or curiosity, only when the future brief says it and the text allows it")
    evidence: str = Field("", description="the source tag or brief item that justifies an invented panel")


class LSceneMark(BaseModel):
    """One scene start found by the chapter-level scene pass (`director._detect_scenes`)."""

    from_block: int
    place: str = ""
    story_time: str = ""
    layer: Layer = Layer.PRESENT
    cut_signal: str = Field("", description="card, match or establishing: how the cut into this scene is best shown")


class LSceneList(BaseModel):
    scenes: list[LSceneMark]


class LPresence(BaseModel):
    present: list[str] = Field(default_factory=list, description="people (or groups such as 'elders') physically in the scene")
    referenced: list[str] = Field(default_factory=list, description="people only talked about, remembered or planned for")


class LCutLine(BaseModel):
    ref: str
    reason: str


class LWindow(BaseModel):
    panels: list[LPanel]
    cut_lines: list[LCutLine] = Field(default_factory=list, description="spoken lines deliberately left out, with why")
