"""LLM trait extraction: one call per prominent entity (`4b` step 1).

The input is the entity's *accumulated evidence* -- attributed dialogue and
the narration around its mentions -- not raw chapter text, so the call size is
bounded by a sample rather than by the novel's length.

Hallucination handling mirrors `speakers/contextual.py`: an answer outside the
controlled vocabulary is discarded rather than coerced, because a silently
coerced value is indistinguishable from a real one downstream. A discarded
field falls back to the deterministic profile's value, so a partially bad
answer costs only the fields it got wrong.
"""

from __future__ import annotations

from dataclasses import replace

from echotales.pipeline.persona.traits import (
    AGE_BANDS,
    GENDERS,
    REGISTERS,
    TraitProfile,
)
from pydantic import BaseModel, Field

SYSTEM = (
    "You profile a character from a translated web novel for voice casting. "
    "Answer only from the evidence given -- if it does not indicate a field, "
    "say 'unknown' for gender and leave the trait at 0.5. Never invent "
    "biography that is not in the evidence."
)

#: Sample sizes for the evidence block. Enough to characterise a voice
#: without turning a per-entity call into a per-chapter one.
_MAX_DIALOGUE = 12
_MAX_NARRATION = 6


class CharacterProfileResponse(BaseModel):
    age_band: str = Field(default="adult", description="child | youth | adult | elder")
    gender: str = Field(default="unknown", description="male | female | unknown")
    #: Named `speech_register` because a bare `register` shadows a BaseModel
    #: attribute in pydantic v2 (it warns, then behaves unpredictably). The
    #: alias keeps the wire/schema name the model actually sees as "register",
    #: which is the word the prompt uses.
    speech_register: str = Field(
        default="neutral",
        alias="register",
        description="formal | neutral | casual | crude",
    )

    model_config = {"populate_by_name": True}
    openness: float = Field(default=0.5, ge=0.0, le=1.0)
    conscientiousness: float = Field(default=0.5, ge=0.0, le=1.0)
    extraversion: float = Field(default=0.5, ge=0.0, le=1.0)
    agreeableness: float = Field(default=0.5, ge=0.0, le=1.0)
    neuroticism: float = Field(default=0.5, ge=0.0, le=1.0)


def build_prompt(label: str, dialogue: list[str], narration: list[str]) -> str:
    lines = [f"Character: {label}", ""]
    if dialogue:
        lines.append("Lines they speak:")
        lines += [f"  - {d.strip()}" for d in dialogue[:_MAX_DIALOGUE]]
        lines.append("")
    if narration:
        lines.append("Narration mentioning them:")
        lines += [f"  - {n.strip()}" for n in narration[:_MAX_NARRATION]]
        lines.append("")
    lines.append(
        "Give their age band, gender, speech register, and Big Five traits "
        "(0.0-1.0, 0.5 if the evidence says nothing)."
    )
    return "\n".join(lines)


def extract_traits(
    base: TraitProfile,
    *,
    dialogue: list[str],
    narration: list[str],
    client: object,
    novel_id: str = "",
) -> TraitProfile:
    """Refine a deterministic profile with a model read.

    Takes the deterministic profile as `base` rather than starting empty, so
    every field the model declines or fluffs keeps a grounded value instead of
    a default one. Returns `base` unchanged on any failure -- this stage can
    only improve a profile, never invalidate one.
    """
    if not dialogue and not narration:
        return base

    from echotales.pipeline.llm.tasks import Task

    try:
        result = client.complete(  # type: ignore[attr-defined]
            Task.CHARACTER_PROFILE,
            build_prompt(base.label, dialogue, narration),
            CharacterProfileResponse,
            system=SYSTEM,
            novel_id=novel_id,
        )
    except Exception:
        return base

    value = result.value
    # `replace` rather than reconstructing from __dict__: TraitProfile is a
    # slots dataclass and has no __dict__ at all.
    out = replace(base, provenance="llm", notes=list(base.notes))

    # Controlled vocabularies: an off-vocabulary answer is a hallucination and
    # is dropped, keeping the deterministic value.
    if value.age_band in AGE_BANDS:
        out.age_band = value.age_band
    else:
        out.notes.append(f"llm age_band {value.age_band!r} off-vocabulary, kept {base.age_band!r}")
    if value.gender in GENDERS:
        out.gender = value.gender
    if value.speech_register in REGISTERS:
        out.register = value.speech_register

    out.openness = value.openness
    out.conscientiousness = value.conscientiousness
    out.extraversion = value.extraversion
    out.agreeableness = value.agreeableness
    out.neuroticism = value.neuroticism
    out.evidence = f"{len(dialogue)} spoken lines, {len(narration)} narration samples"
    return out
