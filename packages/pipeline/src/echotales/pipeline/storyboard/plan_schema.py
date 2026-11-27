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
    ref: str = Field("", description="REQUIRED for any text that exists in the passage: its line tag such as s12 (never retype the text); empty only for an invented SFX or card")
    kind: LetterKind
    text: str = Field("", description="only for an invented sfx / time_place / name_card letter, at most 6 words")


class LPanel(BaseModel):
    purpose: Purpose
    shape: Shape
    shot: Shot
    layer: Layer
    cast: list[str] = Field(default_factory=list, description="names of people physically in the panel")
    visual: str = Field("", description="what is drawn, plain words, no style words, nothing the text does not state")
    letters: list[LLetter] = Field(default_factory=list)
    blocks: list[int] = Field(default_factory=list, description="source block numbers this panel draws from")
    peak: bool = Field(False, description="true on the climax panel of a beat")
    invented: bool = Field(False, description="true when no source text covers the panel (an insert, a card)")
    reason: str = Field("", description="why an invented panel exists, one short phrase")


class LScene(BaseModel):
    from_block: int
    new_scene: bool = Field(False, description="true when a new place or time begins at from_block")
    place: str = ""
    story_time: str = ""
    layer: Layer = Layer.PRESENT
    cut_signal: str = Field("", description="card, match or establishing: how the cut into this scene is shown")
    present: list[str] = Field(default_factory=list, description="people physically in the scene")
    referenced: list[str] = Field(default_factory=list, description="people only talked about, not in the scene")


class LCutLine(BaseModel):
    ref: str
    reason: str


class LWindow(BaseModel):
    scenes: list[LScene]
    panels: list[LPanel]
    cut_lines: list[LCutLine] = Field(default_factory=list, description="spoken lines deliberately left out, with why")
