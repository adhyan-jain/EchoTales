"""Character traits: the vocabulary voice casting and image generation share.

`4b` committed to the shape and the reasoning, which is not relitigated here:
demographics plus register decide the **archetype bucket** (a voice category),
and Big Five decides *which* voice inside that bucket and how it is delivered.
Five continuous traits do not cluster into voice categories; age, gender and
register do.

**One call per entity, above a mention-count floor -- never per mention.** The
§3 budget rule ("no stage may call a model per-span or per-mention at bulk")
applies here as everywhere, and this stage is naturally the cheapest kind:
there are ~80 entities in a 199-chapter novel against ~9,500 mentions.

**Deterministic fallback is a first-class path, not a degradation.** With no
model available, `infer_traits_deterministic` reads what the graph already
knows -- honorifics ("Elder", "Young Master", "Granny" are age statements),
attributed-dialogue volume, and prominence. That is genuinely weaker than a
model read, and it is the difference between a novel getting *some* voice
differentiation and getting none, so it is worth having and worth being
honest about. `TraitProfile.provenance` records which path produced a
profile so nothing downstream has to guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echotales.core.enums import Prominence

#: Coarse age bands. Deliberately coarse: a voice bank cannot honour "34" and
#: pretending otherwise invents precision the source text never states.
AGE_BANDS = ("child", "youth", "adult", "elder")

#: Register is how someone speaks, not who they are -- an educated commoner
#: and a crude aristocrat are both routine in this corpus, so this is tracked
#: separately from status rather than derived from it.
REGISTERS = ("formal", "neutral", "casual", "crude")

GENDERS = ("male", "female", "unknown")

#: Honorifics that assert an age band outright. The strongest deterministic
#: signal available without a model, and near-exact in this corpus: a
#: character addressed as "Granny" is not a youth.
_AGE_HONORIFICS: dict[str, str] = {
    "elder": "elder", "granny": "elder", "grandpa": "elder", "grandfather": "elder",
    "grandmother": "elder", "old": "elder", "ancestor": "elder", "patriarch": "elder",
    "matriarch": "elder", "venerable": "elder",
    "young master": "youth", "young lady": "youth", "young": "youth",
    "junior": "youth", "boy": "child", "girl": "child", "child": "child",
    "senior": "adult", "master": "adult", "lord": "adult", "lady": "adult",
    "madam": "adult", "sir": "adult",
}

#: Gendered address terms. Same principle: stated, not inferred.
_GENDER_TERMS: dict[str, str] = {
    "male": "male", "female": "female",
    "lord": "male", "sir": "male", "master": "male", "grandpa": "male",
    "grandfather": "male", "patriarch": "male", "boy": "male", "brother": "male",
    "uncle": "male", "father": "male", "son": "male", "king": "male",
    "emperor": "male", "young master": "male", "mr": "male",
    "lady": "female", "madam": "female", "granny": "female", "girl": "female",
    "grandmother": "female", "matriarch": "female", "sister": "female",
    "aunt": "female", "mother": "female", "daughter": "female", "queen": "female",
    "empress": "female", "young lady": "female", "miss": "female", "mrs": "female",
    "concubine": "female", "maiden": "female",
}


@dataclass(slots=True)
class TraitProfile:
    """What casting needs to know about one character.

    Big Five values are 0.0-1.0 with 0.5 meaning "no signal", so an
    uninformative profile sits at the neutral centre rather than at an
    extreme -- a deterministic profile that defaulted to 0.0 would read as a
    maximally introverted, maximally disagreeable character and would be cast
    accordingly.
    """

    target_id: str
    label: str = ""
    age_band: str = "adult"
    gender: str = "unknown"
    register: str = "neutral"
    prominence: Prominence = Prominence.INCIDENTAL

    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5

    #: "llm" or "deterministic" -- see the module docstring on why this is
    #: recorded rather than assumed.
    provenance: str = "deterministic"
    evidence: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def archetype(self) -> str:
        """The voice-bank bucket key (`4b` step 2, `architecture.md §8b`).

        Gender/age/register only. Big Five picks a voice *within* a bucket and
        shapes delivery; it deliberately does not partition the bank, because
        continuous traits do not form voice categories.
        """
        return f"{self.gender}:{self.age_band}:{self.register}"


def _honorific_signals(surfaces: list[str]) -> tuple[str | None, str | None]:
    """Age band and gender asserted by any address form among these surfaces.

    Whole-word matched. "Elder" inside "Elderberry Lane" is not an honorific,
    and multi-word keys ("young master") are checked before their single-word
    components so "young master" is not read as the weaker bare "young".
    """
    age: str | None = None
    gender: str | None = None
    blob = " ".join(surfaces).casefold()

    for table, out in ((_AGE_HONORIFICS, "age"), (_GENDER_TERMS, "gender")):
        for term in sorted(table, key=len, reverse=True):
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", blob):
                if out == "age" and age is None:
                    age = table[term]
                elif out == "gender" and gender is None:
                    gender = table[term]
                break
    return age, gender


#: Minimum pronoun observations before the ratio is trusted at all, and the
#: majority share required. A character with two nearby pronouns proves
#: nothing -- the surrounding narration is full of *other* people's pronouns,
#: which is exactly the noise these thresholds exist to absorb.
_PRONOUN_MIN = 6
_PRONOUN_MAJORITY = 0.70

_MALE_PRONOUNS = re.compile(r"(?<!\w)(?:he|him|his|himself)(?!\w)", re.IGNORECASE)
_FEMALE_PRONOUNS = re.compile(r"(?<!\w)(?:she|her|hers|herself)(?!\w)", re.IGNORECASE)


def gender_from_pronouns(passages: list[str]) -> tuple[str | None, str]:
    """Gender from third-person pronouns in narration about a character.

    Far denser than honorific evidence in this corpus: most names here carry
    no address form at all ("Fang Yuan" states nothing), while the narration
    around them is unavoidably gendered in English translation. Measured on
    RI vol 1, honorifics alone left 91% of the cast `unknown`.

    Deliberately a *ratio with a floor*, not a first-match: the passages are
    narration neighbourhoods, so other characters' pronouns are present too
    and a single stray "she" must not flip a male character. Returns `(None,
    reason)` when the evidence is too thin or too mixed to call, which is a
    real answer -- an unknown gender falls back to a gender-neutral voice
    rather than a coin flip.
    """
    blob = " ".join(passages)
    male = len(_MALE_PRONOUNS.findall(blob))
    female = len(_FEMALE_PRONOUNS.findall(blob))
    total = male + female
    if total < _PRONOUN_MIN:
        return None, f"only {total} pronouns, below floor {_PRONOUN_MIN}"
    if male / total >= _PRONOUN_MAJORITY:
        return "male", f"{male}/{total} male pronouns"
    if female / total >= _PRONOUN_MAJORITY:
        return "female", f"{female}/{total} female pronouns"
    return None, f"mixed pronouns ({male}m/{female}f), no majority"


def infer_traits_deterministic(
    target_id: str,
    label: str,
    *,
    surfaces: list[str] | None = None,
    dialogue_lines: int = 0,
    mention_count: int = 0,
    prominence: Prominence = Prominence.INCIDENTAL,
    pronoun_passages: list[str] | None = None,
) -> TraitProfile:
    """Traits from what the graph already knows, with no model call.

    Weaker than a model read and knowingly so -- see the module docstring.
    Everything it does assert is grounded in something the text states
    (an honorific, a count), never guessed from a name.
    """
    surfaces = surfaces or [label]
    age, gender = _honorific_signals(surfaces)

    # **Pronouns outrank honorifics for gender, and only for gender.**
    # Measured on RI vol 1: "Lord Yao Ji" is a female Gu Immortal, but
    # translated xianxia uses "Lord" and "Master" for both genders freely, so
    # the honorific table called her male. The narration around her does not
    # -- it says "she" -- and that is direct evidence about this character
    # rather than an inference from a title's usual connotation.
    #
    # Age keeps the opposite priority (honorific first, below): "Granny" is
    # an exact statement of age band with no pronoun equivalent.
    pronoun_reason = ""
    if pronoun_passages:
        from_pronouns, pronoun_reason = gender_from_pronouns(pronoun_passages)
        if from_pronouns is not None:
            gender = from_pronouns

    profile = TraitProfile(
        target_id=target_id,
        label=label,
        age_band=age or "adult",
        gender=gender or "unknown",
        prominence=prominence,
        provenance="deterministic",
    )

    # A character who speaks a great deal relative to how often they are
    # merely named reads as more extraverted. Bounded well short of the
    # extremes: this is a weak signal and must not outrank a model read or
    # push a voice to the edge of the bucket on its own.
    if mention_count > 0 and dialogue_lines > 0:
        talkativeness = min(1.0, dialogue_lines / mention_count)
        profile.extraversion = round(0.45 + 0.25 * talkativeness, 3)
        profile.notes.append(f"extraversion from {dialogue_lines}/{mention_count} speech ratio")

    if age:
        profile.notes.append(f"age band from honorific evidence in {surfaces[:3]}")
    if gender and pronoun_reason:
        profile.notes.append(f"gender from pronouns: {pronoun_reason}")
    elif gender:
        profile.notes.append(f"gender from address form in {surfaces[:3]}")
    elif pronoun_reason:
        profile.notes.append(f"gender undetermined: {pronoun_reason}")

    # An elder in this corpus speaks formally far more often than not; it is
    # the one register the honorific evidence genuinely supports.
    if profile.age_band == "elder":
        profile.register = "formal"

    return profile
