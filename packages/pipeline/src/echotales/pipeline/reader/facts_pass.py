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


class NamesOut(BaseModel):
    identities: list[IdentityClaim] = Field(default_factory=list)
    ages: list[AgeClaim] = Field(default_factory=list)


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
    duplicates: int = 0
    repaired: int = 0


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
        "quote is a short phrase copied EXACTLY from the passage. Only facts the passage states.\n"
        "Example. Passage: 'Call me the Wolf from now on,' said Tom, who had just turned seventeen. Answer: "
        '{"identities": [{"character": "Tom", "name": "the Wolf", "quote": "Call me the Wolf from now on"}], '
        '"ages": [{"character": "Tom", "age": 17, "quote": "had just turned seventeen"}]}\n'
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


def check_attribute(attribute: str, value: str) -> tuple[str, str] | None:
    """Deterministic sanity on one appearance claim, or None to reject it (A4 validators).

    Measured on LotM after the first facts run: Daly's `eye_color` was "blue eyeshadow", Klein's `height_build` was
    "quivered", and `skin_tone` was "average-looking features". A key's value has to look like that kind of value."""
    if attribute in {"hair_color", "eye_color", "skin_tone"}:
        if _COSMETIC.search(value):
            return "distinguishing_features", value  # makeup on the eyes is a mark, not an eye colour
        return (attribute, value) if _COLOUR.search(value) else None
    if attribute == "height_build":
        return (attribute, value) if _BUILD.search(value) else None
    return attribute, value


def age_in_quote(age: int, quote: str) -> bool:
    """The age has to be written in the evidence ("seventeen", "17 years old"), not merely implied."""
    low = quote.lower()
    words = {n for w, n in _NUMBER_WORDS.items() if re.search(rf"\b{w}\b", low)}
    digits = {int(d) for d in re.findall(r"\b(\d{1,3})\b", low)}
    return age in words | digits


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
            names = client.complete(
                Task.READER, _names_prompt(cast, text), NamesOut, novel_id=novel_id, chapter=number
            ).value
        except Exception:  # noqa: BLE001
            continue
        for claim in appearance.appearance:
            _store_appearance(store, novel_id, number, pos, claim, text, index, report)
        for age in names.ages:
            _store_age(store, novel_id, number, pos, age, text, index, report)
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
    checked = check_attribute(claim.attribute, claim.value.strip())
    if checked is None:
        report.rejected_value += 1
        return
    attribute, value = checked
    entry = _resolve(index, claim.character, report)
    if entry is None:
        return
    persona_id = persona_at(store, entry.self_id, number + 0.5)
    if _known(store, persona_id, attribute, value):
        report.duplicates += 1
        return
    store.add_attribute(novel_id, _attribute(TargetKind.PERSONA, persona_id, attribute, value, quote, number, pos))
    report.appearance += 1


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
    report.ages += 1


def _store_identity(
    store: Store, novel_id: str, pos: DiscoursePosition, claim: IdentityClaim, passage: str, index: NameIndex,
    report: FactsReport,
) -> None:
    name = claim.name.strip()
    if not quote_in_passage(claim.quote, passage) or _norm_text(name) not in _norm_text(claim.quote):
        report.rejected_quote += 1
        return
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
            evidence=claim.quote,
            confidence=FACT_CONFIDENCE,
        ),
    )
    report.identities += 1
