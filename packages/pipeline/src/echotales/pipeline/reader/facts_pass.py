"""Appearance, age and new-name facts read from the chapter text, each carrying the quote that proves it.

Why this exists: the audit found **0 appearance attributes for 93 LotM entities** while the text states them plainly
("Black hair, brown eyes, a linen shirt, thinly built", ch1; Dunn's gray eyes, ch12; Daly's emerald eyes and blue
eyeshadow, ch14), and **no second names** -- "Fool", "Justice" and "The Hanged Man" were never linked to Klein, Audrey
and Alger. Nothing in the extractor asked "what does this person look like now" or "did they just take a new name".

A claim is stored only if its evidence quote is verifiably in the passage and its value is grounded in that quote, the
same citation discipline as `resolve/appearance_extract.py::_verify_citations`: a model's unsupported guess never
becomes a fact.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from echotales.core.enums import AliasType, AssertedBy, TargetKind, TruthStatus
from echotales.core.models import AliasBinding, Attribute, Chapter, DiscoursePosition, FuzzyInterval
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.persona.split import persona_at
from echotales.pipeline.reader.speakers_pass import CastEntry, NameIndex, build_cast, windows
from echotales.pipeline.resolve.appearance_extract import APPEARANCE_KEYS

OBSERVER_READER = "reader"
#: Confidence of a fact one 7B reading produced and a validator accepted: below an explicit declaration (1.0).
FACT_CONFIDENCE = 0.8


class AppearanceClaim(BaseModel):
    character: str
    attribute: str
    value: str
    quote: str


class IdentityClaim(BaseModel):
    character: str
    name: str
    quote: str


class AgeClaim(BaseModel):
    character: str
    age: int
    quote: str


class AppearanceOut(BaseModel):
    appearance: list[AppearanceClaim] = Field(default_factory=list)


class AgeStageClaim(BaseModel):
    character: str
    stage: str
    approx_years: int | None = None
    quote: str


class StatusClaim(BaseModel):
    character: str
    status: str
    quote: str


class NamesOut(BaseModel):
    identities: list[IdentityClaim] = Field(default_factory=list)
    ages: list[AgeClaim] = Field(default_factory=list)
    age_stages: list[AgeStageClaim] = Field(default_factory=list)
    statuses: list[StatusClaim] = Field(default_factory=list)


@dataclass(slots=True)
class FactsReport:
    windows: int = 0
    appearance: int = 0
    identities: int = 0
    ages: int = 0
    rejected_quote: int = 0
    rejected_ungrounded: int = 0
    rejected_character: int = 0
    rejected_key: int = 0
    rejected_value: int = 0
    rejected_subject: int = 0
    statuses: int = 0
    genders: int = 0
    duplicates: int = 0
    repaired: int = 0
    age_stages: int = 0


_KEY_HELP = (
    "hair_color, hair_style, eye_color, skin_tone, height_build (height or build), "
    "distinguishing_features (scars, marks, eyeshadow), typical_attire (clothing worn), "
    "current_condition (wounds or injuries now)"
)


def _norm_text(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_passage(quote: str, passage: str) -> bool:
    """Whether the quote appears verbatim in the passage, ignoring case, whitespace and quote style."""
    q = _norm_text(quote).strip(" .,;:\"'…")
    return len(q) >= 8 and q in _norm_text(passage)


def grounded(value: str, quote: str) -> bool:
    """At least one content word of the value shares a four-letter stem with the quote ("thin" in "thinly built")."""
    q = _norm_text(quote)
    stems = {w[:4] for w in re.findall(r"[a-z]{3,}", _norm_text(value)) if w not in {"and", "the", "with"}}
    stems |= {w for w in re.findall(r"[a-z0-9]+", _norm_text(value)) if w.isdigit()}
    return any(stem in q for stem in stems)


def _people(cast: list[CastEntry]) -> str:
    return "\n".join(f"- {e.name}" + (f" (also: {', '.join(e.aliases[:5])})" if e.aliases else "") for e in cast)


def _appearance_prompt(cast: list[CastEntry], text: str) -> str:
    """Appearance gets its own call and a worked example: asked for appearance, identities and ages in one JSON object,
    the 7B model returned empty lists for "the gray-eyed police inspector" and "a hooded black robe" (LotM ch12, ch14)."""
    return (
        f"Known characters:\n{_people(cast)}\n\n"
        "List every physical description of a named character in the passage: hair, eyes, skin, height or build, "
        "marks, the clothes they wear, and injuries. A descriptive phrase counts: 'the gray-eyed inspector' states gray "
        "eyes, 'a hooded black robe' states clothing. One item per trait.\n"
        f"attribute must be one of: {_KEY_HELP}. quote is a short phrase copied EXACTLY from the passage.\n"
        "Example. Passage: 'Tom, a red-haired man in a leather coat, frowned.' Answer: "
        '{"appearance": [{"character": "Tom", "attribute": "hair_color", "value": "red", "quote": "red-haired man"}, '
        '{"character": "Tom", "attribute": "typical_attire", "value": "leather coat", "quote": "in a leather coat"}]}\n'
        "Only facts the passage states; no outside knowledge. If it describes nobody, answer {\"appearance\": []}.\n\n"
        f"Passage:\n{text}"
    )


def _names_prompt(cast: list[CastEntry], text: str) -> str:
    return (
        f"Known characters:\n{_people(cast)}\n\n"
        "identities: a new name, code name, title or disguise the passage newly gives a character "
        "(for example 'My designation shall be Justice' gives Audrey the name Justice). Do not list names the "
        "character already has.\n"
        "ages: an exact age stated for a character (for example 'had just turned seventeen' is 17).\n"
        "age_stages: a rough life stage a character is described as (stage is one of child, teen, young_adult, adult, "
        "middle_aged, elderly; approx_years is your best guess or null), for example 'a middle-aged appearance' is "
        "middle_aged and 'recent graduate' is young_adult. Only when the passage describes their age.\n"
        "statuses: how well off a character is, when the passage says it (status is one of poor, modest, comfortable, "
        "wealthy, noble), for example 'the family could barely afford meat' is poor and 'daughter of a count' is noble.\n"
        "quote is a short phrase copied EXACTLY from the passage. Only facts the passage states.\n"
        "Example. Passage: 'Call me the Wolf from now on,' said Tom, who had just turned seventeen. Answer: "
        '{"identities": [{"character": "Tom", "name": "the Wolf", "quote": "Call me the Wolf from now on"}], '
        '"ages": [{"character": "Tom", "age": 17, "quote": "had just turned seventeen"}], '
        '"age_stages": [{"character": "Tom", "stage": "teen", "approx_years": 17, "quote": "had just turned seventeen"}]}\n'
        'Use empty lists if the passage states none: {"identities": [], "ages": []}.\n\n'
        f"Passage:\n{text}"
    )


#: Words that signal a physical description. Pre-filtering to these sentences (plus the one before, for who "she" is)
#: shrinks the appearance call from a 2,600-character window to a few sentences: on a long window the 7B model skipped
#: "her brown eyes" and "to her vest" even when told to list every trait (LotM ch3: 9/14 recall).
_CUE = re.compile(
    r"\b(hair|haired|eyes?|eyed|eyebrows?|brows?|eyeshadow|blush|skin|complexion|face|faced|tall|short|thin|thinly|slim|"
    r"slender|plump|fat|build|built|stout|sturdy|beard|moustache|sideburns|bald|scar|scars|wound|bleeding|blood|"
    r"robes?|coat|jacket|shirt|dress|gown|suit|uniform|trousers|wore|wearing|worn|dressed|clothed|clothes|hat|cap|"
    r"cloak|cape|armou?r|bracelet|pendant|lips|pale|tanned|bronze|graying|grey|gray|golden|blonde|black-haired)\b",
    re.IGNORECASE,
)


def cue_passage(text: str) -> str:
    """The sentences of a window that describe someone's body or clothes, each with the sentence before it."""
    sentences = [x for x in re.split(r"(?<=[.!?\"”])\s+|\n+", text) if x.strip()]
    keep: list[int] = []
    for i, sentence in enumerate(sentences):
        if _CUE.search(sentence):
            keep += [j for j in (i - 1, i) if j >= 0 and j not in keep]
    return " ".join(sentences[i] for i in keep)


_COSMETIC = re.compile(r"shadow|liner|blush|lipstick|makeup|rouge|powder", re.IGNORECASE)
_BUILD = re.compile(
    r"\b(tall|short|thin|thinly|slim|slender|plump|fat|stout|sturdy|muscular|lean|burly|build|built|small|big|large|"
    r"petite|towering|average|medium|broad|stocky|skinny|frail|gaunt|heavy)\b",
    re.IGNORECASE,
)
_COLOUR = re.compile(
    r"\b(black|brown|blond|blonde|golden|gold|red|white|grey|gray|silver|blue|green|emerald|amber|hazel|violet|purple|"
    r"pink|crimson|dark|pale|jet|chestnut|auburn|raven|midnight|bronze|tan|tanned|fair|olive|ivory|ruddy|sallow|"
    r"lustrous|graying)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70,
}


_GARMENT = re.compile(
    r"\b(robe|robes|coat|tailcoat|overcoat|jacket|shirt|blouse|dress|gown|suit|waistcoat|vest|cravat|tie|trousers|pants|"
    r"skirt|uniform|cloak|cape|hat|cap|bonnet|veil|headdress|gloves?|scarf|shawl|apron|corset|boots?|shoes|collar|"
    r"cassock|armou?r|tunic|sweater|hood|hooded|clothes|clothing|attire|outfit|garb|fabric|cotton|linen|silk|wool|"
    r"velvet|lace|leather)\b",
    re.IGNORECASE,
)
_HAIR_WORDS = re.compile(r"\b(hair|haired|bald|braid\w*|ponytail|bun|bangs|fringe|curls?|curly|locks|ringlets|bob|"
                         r"cropped|tied|parted|swept|slicked|wavy|straight|shoulder[- ]length|long|short)\b", re.IGNORECASE)
_FACIAL_HAIR = re.compile(r"\b(mustache|moustache|beard|sideburns|stubble|goatee)\b", re.IGNORECASE)
_VAGUE = re.compile(r"\b(such|those|these|that|this|same|some|other|his|her)\b", re.IGNORECASE)


def check_attribute(attribute: str, value: str, gender: str = "") -> tuple[str, str] | None:
    """Deterministic sanity on one appearance claim, or None to reject it (A4 validators).

    Measured on LotM after the first facts run: Daly's `eye_color` was "blue eyeshadow", Klein's `height_build` was
    "quivered", and `skin_tone` was "average-looking features". A key's value has to look like that kind of value."""
    if attribute in {"hair_color", "eye_color", "skin_tone"}:
        if _COSMETIC.search(value):
            return "distinguishing_features", value  # makeup on the eyes is a mark, not an eye colour
        return (attribute, value) if _COLOUR.search(value) else None
    if attribute == "height_build":
        return (attribute, value) if _BUILD.search(value) else None
    if attribute == "hair_style":
        # A hat is clothing, not a haircut (LotM: "veil hat", "silk hat" stored as hair_style), and a moustache is a
        # facial mark that a woman's record cannot take (LotM: Audrey Hall had hair_style "mustache").
        if _FACIAL_HAIR.search(value):
            return None if gender == "female" else ("distinguishing_features", value)
        return (attribute, value) if _HAIR_WORDS.search(value) and not _GARMENT.search(value) else None
    if attribute == "distinguishing_features" and gender == "female" and _FACIAL_HAIR.search(value):
        return None
    if attribute == "typical_attire":
        # Reader noise: "smilingly shook his hand", "such clothes", "halved top hat". Attire is a short noun phrase that
        # names a garment and does not point back at something earlier ("such", "those").
        words = value.split()
        if not _GARMENT.search(value) or len(words) > 7 or _VAGUE.search(value) or any(w.lower().endswith("ly") for w in words):
            return None
    return attribute, value


def _split(passage: str) -> list[str]:
    return [re.sub(r"^#\d+:\s*", "", x).strip() for x in _SENTENCE.split(passage) if x.strip()]


#: How far ahead a description may run before the text names its owner ("a lady in a hooded black robe ..." and, five
#: sentences later, "Daly, the medium"). Measured on LotM ch14, where every one of Daly's looks was introduced this way.
_NAME_LOOKAHEAD = 6


def _side(sentence: str) -> str:
    female, male = bool(_FEMALE.search(sentence)), bool(_MALE.search(sentence))
    return "female" if female and not male else "male" if male and not female else ""


def about_character(
    entry: CastEntry, quote: str, passage: str, index: NameIndex, gender_of: Callable[[str], str] | None = None
) -> bool:
    """Whether the sentence of `quote` is about `entry` rather than someone else nearby.

    The model's quote only had to exist in the window, so a description of Klein's clothes could be filed under Audrey
    whenever she was the named person in view (LotM ch3, full-volume run 2026-10-23: Audrey Hall carried a mustache and
    a waistcoat). The first version of this check demanded the sentence name the character, and reference-chapter
    scoring showed it cost real facts (appearance 11 of 17 fell to 8): Daly's looks are written "a lady in a hooded
    black robe" before her name, "her emerald eyes smiled at Klein" names someone else, and "Daly's blue eyeshadow" lost
    its name to the possessive. So: the sentence names the character, or names only people whose recorded gender
    contradicts its pronoun (then the owner is whoever the text named last), or names nobody (then the owner is the
    one person named just before, or, failing that, just after). Anything ambiguous is still rejected."""
    sentences = _split(passage)
    needle = _norm_text(quote).strip(" .,;:\"'…")
    at = next((i for i, x in enumerate(sentences) if needle and needle in _norm_text(x)), None)
    if at is None:
        return False
    here = index.mentioned_in(sentences[at])
    side = _side(sentences[at])
    if entry.self_id in here:
        # Named is not owned: in "her eyes smiled at Klein" Klein is only the object.
        return not (gender_of and side and gender_of(entry.self_id) not in ("", "unknown", side))
    if here:
        others_contradict = bool(gender_of) and bool(side) and all(gender_of(o) not in ("", "unknown", side) for o in here)
        if not (others_contradict and gender_of(entry.self_id) == side):
            return False
    for back in (1, 2):
        if at - back < 0:
            break
        earlier = index.mentioned_in(sentences[at - back])
        if earlier:
            return earlier == {entry.self_id}
    for ahead in range(1, _NAME_LOOKAHEAD + 1):
        if at + ahead >= len(sentences):
            break
        later = index.mentioned_in(sentences[at + ahead])
        if later:
            return later == {entry.self_id}
    return False


def age_in_quote(age: int, quote: str) -> bool:
    """The age has to be written in the evidence ("seventeen", "17 years old"), not merely implied."""
    low = quote.lower()
    words = {n for w, n in _NUMBER_WORDS.items() if re.search(rf"\b{w}\b", low)}
    digits = {int(d) for d in re.findall(r"\b(\d{1,3})\b", low)}
    return age in words | digits


#: Words that announce a new name, code name or age. Used the way `_CUE` is for appearance, but with the sentences that
#: FOLLOW the cue kept too: "My designation shall be 'Justice!'" is followed two lines later by the other speaker's
#: bare answer "The Hanged Man.", which has no cue word of its own (LotM ch7: that link was missed with gemma2:9b).
_NAME_CUE = re.compile(
    r"\b(designation|code ?name|call me|address me|known as|my name|name is|named|called|title|alias|pseudonym|"
    r"disguise|I am|I\'m|I’m|years old|turned|aged|birthday|young|youth|teen\w*|middle[- ]aged|elderly|old man|old woman|"
    r"graduate|student|twenties|thirties|forties|fifties|sixties|poor|poverty|wealthy|rich|noble|aristocrat\w*|"
    r"viscount|earl|count|baron|duke|marquis|family|servant|maid|salary|pounds)\b",
    re.IGNORECASE,
)


def name_passage(text: str, before: int = 1, after: int = 8) -> str:
    """Sentences around a naming or age cue: one before it and the next few after it."""
    sentences = [x for x in re.split(r"(?<=[.!?\"”])\s+|\n+", text) if x.strip()]
    keep: set[int] = set()
    for i, sentence in enumerate(sentences):
        if _NAME_CUE.search(sentence):
            keep.update(j for j in range(i - before, i + after + 1) if 0 <= j < len(sentences))
    return " ".join(sentences[i] for i in sorted(keep))


_SENTENCE = re.compile(r"(?<=[.!?\"”])\s+|\n+")


#: A repaired quote must mention the kind of thing the attribute is about; "black" alone matched a robe sentence for a
#: hair-colour claim in the first test of this function.
_KEY_CUE = {
    "hair_color": re.compile(r"\b(hair|haired|bald)\b", re.IGNORECASE),
    "hair_style": re.compile(r"\b(hair|haired|bald|braid|ponytail|bun)\b", re.IGNORECASE),
    "eye_color": re.compile(r"\b(eyes?|eyed|gaze|irises)\b", re.IGNORECASE),
    "skin_tone": re.compile(r"\b(skin|complexion|face|faced)\b", re.IGNORECASE),
}


def repair_quote(claim_quote: str, value: str, passage: str, attribute: str = "") -> str | None:
    """The passage sentence that actually states the claim, when the model's quote is a paraphrase.

    The evidence stays real text: the stored quote is always a sentence of the passage, never the model's words."""
    stems = {w[:4] for w in re.findall(r"[a-z]{3,}", _norm_text(value)) if w not in {"and", "the", "with"}}
    if not stems:
        return None
    hints = {w[:4] for w in re.findall(r"[a-z]{4,}", _norm_text(claim_quote))}
    best: tuple[int, str] | None = None
    for raw in _SENTENCE.split(passage):
        sentence = re.sub(r"^#\d+:\s*", "", raw)  # the window's own block marker is not part of the evidence
        low = _norm_text(sentence)
        if not stems <= {w[:4] for w in re.findall(r"[a-z]{3,}", low)}:
            continue
        if attribute in _KEY_CUE and not _KEY_CUE[attribute].search(sentence):
            continue
        score = len(hints & {w[:4] for w in re.findall(r"[a-z]{4,}", low)})
        if best is None or score > best[0]:
            best = (score, sentence.strip())
    return best[1][:240] if best else None


def read_chapter_facts(store: Store, client: ModelClient, chapter: Chapter) -> FactsReport:
    """Extract, validate and store this chapter's appearance, age and new-name facts."""
    report = FactsReport()
    novel_id, number = chapter.novel_id, chapter.number
    cast = build_cast(store, novel_id, "\n".join(b.text for b in chapter.blocks), number)
    index = NameIndex(cast)
    pos = DiscoursePosition(chapter=int(number), offset=0)
    # First, so this chapter's own pronoun checks already know who is a "he".
    infer_genders(store, novel_id, "\n".join(b.text for b in chapter.blocks), index, number, report)
    for text in windows(chapter, tagged=False):
        report.windows += 1
        try:  # one malformed window must not stop the chapter
            focus = cue_passage(text)
            appearance = (
                client.complete(
                    Task.READER, _appearance_prompt(cast, focus), AppearanceOut, novel_id=novel_id, chapter=number
                ).value
                if focus
                else AppearanceOut()
            )
            focus_names = name_passage(text)
            names = (
                client.complete(Task.READER, _names_prompt(cast, focus_names), NamesOut, novel_id=novel_id, chapter=number).value
                if focus_names
                else NamesOut()
            )
        except Exception:  # noqa: BLE001
            continue
        for claim in appearance.appearance:
            _store_appearance(store, novel_id, number, pos, claim, text, index, report)
        for age in names.ages:
            _store_age(store, novel_id, number, pos, age, text, index, report)
        for stage in names.age_stages:
            _store_age_stage(store, novel_id, number, pos, stage, text, index, report)
        for status in names.statuses:
            _store_status(store, novel_id, number, pos, status, text, index, report)
        for identity in names.identities:
            _store_identity(store, novel_id, pos, identity, text, index, report)
    store.conn.commit()
    return report


def _resolve(index: NameIndex, name: str, report: FactsReport) -> CastEntry | None:
    entry = index.resolve(name)
    if entry is None:
        report.rejected_character += 1
    return entry


def _attribute(
    target_kind: TargetKind, target_id: str, key: str, value: str, quote: str, number: float, pos: DiscoursePosition
) -> Attribute:
    return Attribute(
        target_kind=target_kind,
        target_id=target_id,
        key=key,
        value=value,
        # Open-ended from the chapter that states it: a later contradicting attestation lands as its own row
        # rather than replacing this one (same rule as `appearance_extract._write_appearance`).
        interval=FuzzyInterval.open_ended(int(number), last_evidence=int(number)),
        learned_at_pos=pos,
        observer_id=OBSERVER_READER,
        asserted_by=AssertedBy.INFERENCE,
        truth_status=TruthStatus.TRUE,
        evidence=quote,
        confidence=FACT_CONFIDENCE,
    )


def _known(store: Store, target_id: str, key: str, value: str) -> bool:
    return any(
        a.key == key and a.value.strip().lower() == value.strip().lower() and a.is_standing
        for a in store.get_attributes(TargetKind.PERSONA, target_id)
    )


def _store_appearance(
    store: Store, novel_id: str, number: float, pos: DiscoursePosition, claim: AppearanceClaim, passage: str,
    index: NameIndex, report: FactsReport,
) -> None:
    if claim.attribute not in APPEARANCE_KEYS:
        report.rejected_key += 1
        return
    quote = claim.quote
    if not quote_in_passage(quote, passage):
        # A paraphrase is repaired to the passage sentence that states the value, or rejected.
        repaired = repair_quote(quote, claim.value, passage, claim.attribute)
        if repaired is None:
            report.rejected_quote += 1
            return
        quote = repaired
        report.repaired += 1
    if not grounded(claim.value, quote):
        report.rejected_ungrounded += 1
        return
    entry = _resolve(index, claim.character, report)
    if entry is None:
        return
    checked = check_attribute(claim.attribute, claim.value.strip(), _recorded_gender(store, entry.self_id))
    if checked is None:
        report.rejected_value += 1
        return
    attribute, value = checked
    if not about_character(entry, quote, passage, index, lambda sid: _recorded_gender(store, sid)):
        report.rejected_subject += 1
        return
    if gender_conflict(_recorded_gender(store, entry.self_id), quote):
        report.rejected_value += 1
        return
    persona_id = persona_at(store, entry.self_id, number + 0.5)
    if _known(store, persona_id, attribute, value):
        report.duplicates += 1
        return
    store.add_attribute(novel_id, _attribute(TargetKind.PERSONA, persona_id, attribute, value, quote, number, pos))
    report.appearance += 1


def _store_age_stage(
    store: Store, novel_id: str, number: float, pos: DiscoursePosition, claim: AgeStageClaim, passage: str,
    index: NameIndex, report: FactsReport,
) -> None:
    stage = claim.stage.strip().lower().replace("-", "_").replace(" ", "_")
    quote = claim.quote
    # A free-form age phrase has no safe repair target, so a quote that is not in the passage is rejected, and so is a
    # stage whose quote contains none of that stage's cue words.
    if not quote_in_passage(quote, passage) or not stage_grounded(stage, quote):
        report.rejected_value += 1
        return
    entry = _resolve(index, claim.character, report)
    if entry is None:
        return
    if gender_conflict(_recorded_gender(store, entry.self_id), quote) or not about_character(entry, quote, passage, index, lambda sid: _recorded_gender(store, sid)):
        report.rejected_value += 1
        return
    persona_id = persona_at(store, entry.self_id, number + 0.5)
    if _known(store, persona_id, "age_stage", stage):
        report.duplicates += 1
        return
    store.add_attribute(novel_id, _attribute(TargetKind.PERSONA, persona_id, "age_stage", stage, quote, number, pos))
    if claim.approx_years and 0 < claim.approx_years < 120 and stage_of_years(claim.approx_years) == stage:
        store.add_attribute(novel_id, _attribute(
            TargetKind.PERSONA, persona_id, "age_estimate", f"about {claim.approx_years}", quote, number, pos))
    report.age_stages += 1


_STATUSES = ("poor", "modest", "comfortable", "wealthy", "noble")
_STATUS_CUES = {
    "poor": re.compile(r"\b(poor|poverty|barely|shabby|threadbare|worn|cheap|beggar|starv\w+|destitute)\b", re.I),
    "modest": re.compile(r"\b(modest|ordinary|plain|salary|clerk|worker|tenant|renter|graduate|average|common)\b", re.I),
    "comfortable": re.compile(r"\b(comfortable|middle class|respectable|merchant|well[- ]off|steady)\b", re.I),
    "wealthy": re.compile(r"\b(wealthy|rich|fortune|luxur\w+|expensive|extravagant|lavish|gorgeous|fine|servants|estate)\b", re.I),
    "noble": re.compile(r"\b(noble|aristocra\w+|viscount|earl|count|baron|duke|marquis|lord|lady|countess)\b", re.I),
}


def _store_status(
    store: Store, novel_id: str, number: float, pos: DiscoursePosition, claim: StatusClaim, passage: str,
    index: NameIndex, report: FactsReport,
) -> None:
    """How well off a character is, so clothes can differ within one era (owner, 2026-10-23: Klein and Melissa are poor
    and dress plainly, Audrey is rich). The status must be one of five and its quote must hold a cue for it."""
    status = claim.status.strip().lower()
    if status not in _STATUSES or not quote_in_passage(claim.quote, passage) or not _STATUS_CUES[status].search(claim.quote):
        report.rejected_value += 1
        return
    entry = _resolve(index, claim.character, report)
    if entry is None:
        return
    if not about_character(entry, claim.quote, passage, index, lambda sid: _recorded_gender(store, sid)):
        report.rejected_subject += 1
        return
    persona_id = persona_at(store, entry.self_id, number + 0.5)
    if _known(store, persona_id, "social_status", status):
        report.duplicates += 1
        return
    store.add_attribute(novel_id, _attribute(TargetKind.PERSONA, persona_id, "social_status", status, claim.quote, number, pos))
    report.statuses += 1


_SUBJECT_PRONOUN = re.compile(r"^[\"“]?\s*(he|she)\b", re.IGNORECASE)


def infer_genders(store: Store, novel_id: str, text: str, index: NameIndex, number: float, report: FactsReport) -> None:
    """Record a gender for entries that have none, from narration: a sentence that opens with "he" or "she" is about the
    one entry named in the sentence before it. Needs three agreeing sentences and 80% agreement, so one stray pronoun
    never decides it. (Full-volume LotM run: Klein and Dunn Smith were left `unknown`, so the pronoun checks and the
    image prompt's 1boy/1girl had nothing to use.)"""
    votes: dict[str, dict[str, int]] = {}
    sentences = _split(text)
    for i in range(1, len(sentences)):
        m = _SUBJECT_PRONOUN.match(sentences[i])
        named = index.mentioned_in(sentences[i - 1])
        if m and len(named) == 1:
            who = next(iter(named))
            side = "male" if m.group(1).lower() == "he" else "female"
            votes.setdefault(who, {}).setdefault(side, 0)
            votes[who][side] += 1
    for self_id, tally in votes.items():
        total = sum(tally.values())
        gender, n = max(tally.items(), key=lambda kv: kv[1])
        if total < 3 or n / total < 0.8 or _recorded_gender(store, self_id) not in ("", "unknown"):
            continue
        pos = DiscoursePosition(chapter=int(number), offset=0)
        persona_id = persona_at(store, self_id, number + 0.5)
        store.add_attribute(novel_id, _attribute(
            TargetKind.PERSONA, persona_id, "gender", gender,
            f"{n} of {total} sentences that continue about them use {'he' if gender == 'male' else 'she'}", number, pos))
        report.genders += 1


def _store_age(
    store: Store, novel_id: str, number: float, pos: DiscoursePosition, claim: AgeClaim, passage: str,
    index: NameIndex, report: FactsReport,
) -> None:
    if not 0 < claim.age < 130 or not quote_in_passage(claim.quote, passage):
        report.rejected_quote += 1
        return
    if not age_in_quote(claim.age, claim.quote):
        report.rejected_value += 1
        return
    entry = _resolve(index, claim.character, report)
    if entry is None:
        return
    persona_id = persona_at(store, entry.self_id, number + 0.5)
    if _known(store, persona_id, "age", str(claim.age)):
        report.duplicates += 1
        return
    store.add_attribute(novel_id, _attribute(TargetKind.PERSONA, persona_id, "age", str(claim.age), claim.quote, number, pos))
    store.add_attribute(novel_id, _attribute(
        TargetKind.PERSONA, persona_id, "age_stage", stage_of_years(claim.age), claim.quote, number, pos))
    report.ages += 1


#: Rough life stages, and the words that make a quote evidence for each. A stage is stored only when its quote contains
#: one of its cue words, so the model cannot call someone elderly on a hunch. "boy"/"girl" are not cues on their own.
AGE_STAGES = ("child", "teen", "young_adult", "adult", "middle_aged", "elderly")
_STAGE_CUES = {
    "child": re.compile(r"\b(child|kid|toddler|infant|little (?:boy|girl)|\d{1,2}[- ]year[- ]old|years old|[3-9] years)\b", re.I),
    "teen": re.compile(r"\b(teen\w*|adolescent|youth|schoolgirl|schoolboy|student|(?:thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)\b|1[3-9])", re.I),
    "young_adult": re.compile(r"\b(young|youth|graduate|twenties|twenty|youthful|recent graduate|2\d)\b", re.I),
    "adult": re.compile(r"\b(adult|man|woman|grown)\b", re.I),
    "middle_aged": re.compile(r"\b(middle[- ]aged|forties|fifties|forty|fifty|4\d|5\d|graying|greying|sideburns)\b", re.I),
    "elderly": re.compile(r"\b(old|elderly|aged|grandfather|grandmother|grandma|grandpa|ancient|wrinkle\w*|white[- ]haired|\d0s|sixt\w+|seventy|eighty|6\d|7\d|8\d)\b", re.I),
}


def stage_of_years(years: int) -> str:
    """Life stage for an exact age."""
    return "child" if years < 13 else "teen" if years < 20 else "young_adult" if years < 30 else "adult" if years < 45 else (
        "middle_aged" if years < 62 else "elderly")


def stage_grounded(stage: str, quote: str) -> bool:
    return stage in _STAGE_CUES and bool(_STAGE_CUES[stage].search(quote))


_FEMALE = re.compile(r"\b(she|her|hers|herself)\b", re.IGNORECASE)
_MALE = re.compile(r"\b(he|his|him|himself)\b", re.IGNORECASE)


def gender_conflict(gender: str, quote: str) -> bool:
    """A quote that is about "her" cannot describe a character recorded as male, and the reverse.

    LotM ch3: "her skin remained lustrous" (Melissa) was stored as Klein's skin tone because the nearest named male was
    Klein. Only a clear one-sided pronoun signal counts; a quote with both, or neither, is left alone."""
    female, male = bool(_FEMALE.search(quote)), bool(_MALE.search(quote))
    return (gender == "male" and female and not male) or (gender == "female" and male and not female)


def _recorded_gender(store: Store, self_id: str) -> str:
    for target in (TargetKind.SELF, TargetKind.PERSONA):
        for tid in (self_id, f"{self_id}:body1"):
            for a in store.get_attributes(target, tid):
                if a.key == "gender":
                    return a.value.strip().lower()
    return ""


def repair_name_quote(core: str, passage: str) -> str | None:
    """The passage sentence that actually contains the new name, preferring one with a naming cue.

    gemma2:9b named Zhou Mingrui's new identity correctly but quoted an unrelated line ("It's nothing.") as evidence on
    some runs and the right line on others; the claim was valid, the evidence pointer wasn't. The stored quote is always a
    real sentence of the passage."""
    best: tuple[int, str] | None = None
    for raw in re.split(r"(?<=[.!?\"”])\s+|\n+", passage):
        sentence = re.sub(r"^#\d+:\s*", "", raw).strip()
        if len(sentence) < 8 or core not in _norm_text(sentence):
            continue
        score = 2 if _NAME_CUE.search(sentence) else 1
        if best is None or score > best[0]:
            best = (score, sentence[:240])
    return best[1] if best else None


def _store_identity(
    store: Store, novel_id: str, pos: DiscoursePosition, claim: IdentityClaim, passage: str, index: NameIndex,
    report: FactsReport,
) -> None:
    name = claim.name.strip()
    # "Mr. Fool" vs the quote's "The Fool": the code name is the same; only the article or title differs.
    core = re.sub(r"^(?:the|a|an|mr\.?|mrs\.?|miss|ms\.?|lord|lady|sir)\s+", "", _norm_text(name))
    quote = claim.quote
    if not quote_in_passage(quote, passage) or core not in _norm_text(quote):
        quote = repair_name_quote(core, passage) or ""
        if not quote:
            report.rejected_quote += 1
            return
        report.repaired += 1
    entry = _resolve(index, claim.character, report)
    if entry is None or index.resolve(name) is entry:
        # A name the character already answers to is not a new identity.
        if entry is not None:
            report.duplicates += 1
        return
    store.add_alias_binding(
        novel_id,
        AliasBinding(
            alias=name,
            alias_type=AliasType.EPITHET,
            target_kind=TargetKind.SELF,
            target_id=entry.self_id,
            interval=FuzzyInterval.open_ended(pos.chapter, last_evidence=pos.chapter),
            learned_at_pos=pos,
            observer_id=OBSERVER_READER,
            asserted_by=AssertedBy.INFERENCE,
            truth_status=TruthStatus.TRUE,
            evidence=quote,
            confidence=FACT_CONFIDENCE,
        ),
    )
    report.identities += 1
