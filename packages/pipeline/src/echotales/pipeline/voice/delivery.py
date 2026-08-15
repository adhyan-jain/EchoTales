"""Turn a line's context into concrete synthesis parameters.

Chatterbox exposes two dials that matter here:

- **`exaggeration`** (0.0-1.0+) -- emotional intensity. 0.5 is neutral.
- **`cfg_weight`** (0.0-1.0) -- classifier-free guidance. Lower makes delivery
  slower and more deliberate; this is the documented compensation for the fact
  that raising `exaggeration` also speeds speech up. The two are therefore
  moved *together*, not independently.

**Non-negotiable #10 is enforced here, not just in extraction.**
`spans/delivery.py` exists because a protagonist described as
"expressionless" during the novel's most violent scenes must not be voiced
dramatically -- the contrast between his flatness and the carnage *is* the
characterisation. So a `FLAT` marker does not merely lower intensity, it
**overrides** the scene's own sentiment and the speaker's baseline
extraversion, which are exactly the two signals that would otherwise argue
for a dramatic read.

Pauses are inserted as text, not as a parameter, because that is the only
lever a TTS model of this class reliably honours: punctuation and line
breaks. `pace_text` is deliberately conservative -- an ellipsis already
present in the prose is a pause the author asked for, and does not need
help.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from echotales.core.enums import SpanType
from echotales.pipeline.persona.traits import TraitProfile
from echotales.pipeline.spans.delivery import DeliveryPolarity

#: Chatterbox's own documented neutral point.
NEUTRAL_EXAGGERATION = 0.5
NEUTRAL_CFG = 0.5


@dataclass(slots=True)
class DeliverySettings:
    exaggeration: float = NEUTRAL_EXAGGERATION
    cfg_weight: float = NEUTRAL_CFG
    #: Why these values -- carried into the manifest so a bad-sounding line
    #: can be traced to the decision that produced it rather than re-derived.
    rationale: str = "neutral"


#: Polarity -> (exaggeration, cfg_weight). `cfg_weight` moves opposite to
#: `exaggeration` for the pacing reason in the module docstring.
_BY_POLARITY: dict[DeliveryPolarity, tuple[float, float]] = {
    DeliveryPolarity.FLAT: (0.25, 0.65),
    DeliveryPolarity.HEIGHTENED: (0.85, 0.35),
    DeliveryPolarity.HUSHED: (0.40, 0.60),
    DeliveryPolarity.COLD: (0.35, 0.60),
    DeliveryPolarity.WARM: (0.60, 0.45),
    DeliveryPolarity.HESITANT: (0.45, 0.60),
}


def settings_for(
    *,
    span_type: SpanType,
    polarity: DeliveryPolarity | None = None,
    profile: TraitProfile | None = None,
    text: str = "",
) -> DeliverySettings:
    """Decide synthesis parameters for one line.

    Precedence, strongest first:

    1. **An explicit delivery marker** (non-negotiable #10). Overrides
       everything below, including the speaker's baseline.
    2. **Terminal punctuation** -- an exclamation is stated intensity.
    3. **The speaker's baseline** from Big Five, as a gentle offset only.
    """
    if polarity is not None and polarity in _BY_POLARITY:
        exaggeration, cfg = _BY_POLARITY[polarity]
        return DeliverySettings(exaggeration, cfg, f"delivery marker: {polarity.value}")

    exaggeration, cfg = NEUTRAL_EXAGGERATION, NEUTRAL_CFG
    reasons: list[str] = []

    # Narration is read, not performed -- kept measurably calmer than
    # performed dialogue is what makes a performed line audible *as* a
    # performance by contrast. Not neutral either, though: a flat read for
    # 70% of a chapter's runtime is its own complaint, distinct from the
    # dialogue-vs-narration contrast this design protects. Nudged warmer
    # than the original (0.40, 0.55), still well short of a performed
    # baseline (0.50/0.50).
    if span_type in (
        SpanType.NARRATION_ACTION,
        SpanType.NARRATION_DESCRIPTION,
        SpanType.NARRATION_EXPOSITION,
    ):
        exaggeration, cfg = 0.46, 0.52
        reasons.append("narration: read, calmer than performed")
        if profile is not None and profile.register == "formal":
            cfg = _clamp(cfg - 0.08)
            reasons.append("formal register: measured pace")
        return DeliverySettings(_clamp(exaggeration), _clamp(cfg), "; ".join(reasons))

    if span_type is SpanType.INNER_MONOLOGUE:
        exaggeration, cfg = 0.45, 0.60
        reasons.append("inner monologue: closer, slower")

    stripped = text.strip()
    if stripped.endswith("!") or stripped.endswith("!”") or stripped.endswith('!"'):
        exaggeration, cfg = 0.75, 0.40
        reasons.append("exclamation")
    elif stripped.endswith("?") or stripped.endswith("?”") or stripped.endswith('?"'):
        exaggeration = max(exaggeration, 0.55)
        reasons.append("question")

    # Baseline: bounded to ±0.10 on purpose. A character's disposition
    # colours every line they speak, so a large offset would make their
    # *neutral* lines sound permanently agitated -- the trait should be
    # audible across a scene, not shouted in every sentence.
    if profile is not None:
        offset = (profile.extraversion - 0.5) * 0.2
        exaggeration = _clamp(exaggeration + offset)
        if abs(offset) >= 0.02:
            reasons.append(f"extraversion {profile.extraversion:.2f}")
        # A formal register (clan elders, authority figures) reads as
        # measured and deliberate, not merely calm -- lower cfg_weight is
        # the documented lever for slower, weightier pacing (module
        # docstring). Register has no bank-voice equivalent (VCTK carries
        # no register metadata, `voice/bank.py`'s own docstring says so),
        # so this is the one lever available to make an elder's line land
        # differently from a young disciple's line in the same bucket.
        if profile.register == "formal":
            cfg = _clamp(cfg - 0.08)
            reasons.append("formal register: measured pace")

    return DeliverySettings(
        _clamp(exaggeration), _clamp(cfg), "; ".join(reasons) or "neutral"
    )


def _clamp(value: float, low: float = 0.05, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 3)


#: A dash used as an interruption ("—" mid-sentence) reads as a hard cut.
_EM_DASH_BREAK = re.compile(r"\s*—\s*(?=\S)")
#: Sentence end followed immediately by more text, with no space to breathe.
_TIGHT_SENTENCE = re.compile(r"([.!?])\s+(?=[A-Z“\"'])")


def pace_text(text: str, *, span_type: SpanType = SpanType.DIALOGUE) -> str:
    """Insert pause cues a TTS model actually honours: punctuation.

    Conservative by design. Prose already contains the author's own pauses --
    an ellipsis, a comma, a paragraph break -- and adding to them makes a
    reading sound mannered. This only marks two cases the raw text leaves
    implicit:

    - an em-dash interruption, which otherwise runs straight through;
    - a sentence boundary inside a long narration run, where a model given
      one breathless paragraph tends to drop the boundary entirely.

    Returns the text unchanged for short spans, where the model's own
    phrasing is already correct and intervention only adds artefacts.
    """
    if len(text) < 80:
        return text

    out = _EM_DASH_BREAK.sub(" — ", text)
    if span_type in (
        SpanType.NARRATION_ACTION,
        SpanType.NARRATION_DESCRIPTION,
        SpanType.NARRATION_EXPOSITION,
    ):
        out = _TIGHT_SENTENCE.sub(r"\1  ", out)
    return out
