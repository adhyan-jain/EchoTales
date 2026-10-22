"""Speaker attribution by a model that is shown the cast list, with an explicit answer per quoted line.

Why this replaces the regex ladder as the primary attributor (decisions D11): on LotM ch7 the existing pipeline
named the right speaker for 16 of 43 lines (37%) because it cannot hold a cast in mind; a local 7B model shown the
cast list got 25/43 with a loose prompt and **39/43 (91%)** once the prompt listed every tag that needed an answer
and re-asked for the ones the model skipped. The first 33 points were missing answers, not wrong ones, so the
output contract (one entry per tag, retry omissions) is the load-bearing part of this module.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from echotales.core.enums import AttributionMethod, Prominence, SpanType, TargetKind
from echotales.core.models import Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.reader.quotes import QUOTE, quote_starts, tag_block

#: Characters of tagged text per call. ~2,600 fit the local-low 4,096-token context with the cast list and the
#: answer; larger windows made the 7B model drop tags (measured on ch7).
WINDOW_CHARS = 2600
#: Re-asks for tags a response left out. Three covers the observed worst case (two rounds).
MAX_ATTEMPTS = 3
#: Largest cast shown to the model. Beyond this the list crowds out the passage.
MAX_CAST = 14
#: Confidence recorded on a model-attributed span: above the regex ladder's anonymous slots (0.2-0.35), below an
#: explicit "X said" (1.0), because it is one reading by a 7B model.
MODEL_CONFIDENCE = 0.8
#: A role slot is the model's reading of who an unnamed speaker is: weaker than a named one.
ROLE_CONFIDENCE = 0.5

#: Span types a quoted line can carry; the classifier mistypes dialogue as the last two.
_QUOTE_SPANS = frozenset({SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE, SpanType.CROWD_REACTION})

UNKNOWN = "unknown"
NOT_SPEECH = "none"


class SpeakerEntry(BaseModel):
    tag: str
    speaker: str


class SpeakerAnswers(BaseModel):
    lines: list[SpeakerEntry] = Field(default_factory=list)


@dataclass(slots=True)
class CastEntry:
    self_id: str
    name: str
    aliases: list[str] = field(default_factory=list)

    def surfaces(self) -> list[str]:
        return [self.name, *self.aliases]


@dataclass(slots=True)
class SpeakerReport:
    quotes: int = 0
    attributed: int = 0
    unknown: int = 0
    not_speech: int = 0
    unmapped: int = 0
    no_span: int = 0
    retried_tags: int = 0
    missing: int = 0
    minted: int = 0
    role_slots: int = 0
    cleared: int = 0
    retyped: int = 0


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower().replace("’", "'")).strip()


def build_cast(store: Store, novel_id: str, chapter_text: str, chapter: float) -> list[CastEntry]:
    """People who can speak in this chapter: kind SELF, already attested, and named somewhere in its text.

    Requiring a name in the text keeps the list short enough for a 7B prompt and keeps a character who has not
    appeared yet (a later-chapter alias) out of earlier chapters, the same no-look-ahead rule the Read page enforces.
    """
    haystack = _norm(chapter_text)
    rank = {"PRINCIPAL": 0, "RECURRING": 1}
    found: dict[str, CastEntry] = {}
    rows = store.conn.execute(
        # Rows written before `kind` existed hold NULL or '' and are people (ORV's whole cast); only an explicit
        # non-SELF kind (LOCATION, ORGANIZATION, ITEM) removes an entity from the cast.
        "SELECT id FROM self_entity WHERE novel_id=? AND (kind IS NULL OR kind='' OR kind=?)",
        (novel_id, TargetKind.SELF.value),
    ).fetchall()
    ordered: list[tuple[int, int, CastEntry]] = []
    for row in rows:
        entity = store.get_self(row["id"])
        if entity is None or entity.first_attested_pos.chapter > chapter:
            continue
        aliases = [a.alias for a in store.get_aliases_for(TargetKind.SELF, entity.id)]
        entry = CastEntry(entity.id, entity.canonical_label, [a for a in aliases if a != entity.canonical_label])
        if not any(len(_norm(s)) >= 3 and _norm(s) in haystack for s in entry.surfaces()):
            continue
        key = _norm(entry.name)
        if key in found:
            continue
        found[key] = entry
        ordered.append((rank.get(entity.prominence.value, 2), -len(entry.name), entry))
    ordered.sort(key=lambda t: (t[0], t[1]))
    return [e for _r, _l, e in ordered[:MAX_CAST]]


class NameIndex:
    """Maps a name the model wrote back to a cast entry, by full name first and then by a unique word."""

    def __init__(self, cast: list[CastEntry]) -> None:
        self._full: dict[str, CastEntry] = {}
        words: dict[str, list[CastEntry]] = {}
        for entry in cast:
            for surface in entry.surfaces():
                key = _norm(surface)
                if key:
                    self._full.setdefault(key, entry)
                for word in key.split():
                    if len(word) >= 4:
                        words.setdefault(word, []).append(entry)
        self._unique_word = {w: es[0] for w, es in words.items() if len({e.self_id for e in es}) == 1}

    def resolve(self, answer: str) -> CastEntry | None:
        key = _norm(answer)
        if key in self._full:
            return self._full[key]
        # "Mr. Fool" / "Miss Justice": drop a leading title word and try again, then a unique name word.
        parts = key.split()
        if parts and self._full.get(" ".join(parts[1:])):
            return self._full[" ".join(parts[1:])]
        hits = {self._unique_word[w].self_id: self._unique_word[w] for w in parts if w in self._unique_word}
        return next(iter(hits.values())) if len(hits) == 1 else None


def windows(chapter: Chapter, *, tagged: bool = True) -> list[str]:
    """Consecutive whole blocks up to `WINDOW_CHARS` per window.

    `tagged=True` inserts `[block.q]` before every quote and drops windows with no quote (the speaker pass);
    `tagged=False` keeps every window as plain text (the facts pass reads narration too)."""
    out: list[list[str]] = []
    current: list[str] = []
    size = 0
    for block in sorted(chapter.blocks, key=lambda b: b.index):
        text = tag_block(block.index, block.text) if tagged else block.text
        if size + len(text) > WINDOW_CHARS and current:
            out.append(current)
            current, size = [], 0
        current.append(f"#{block.index}: {text}")
        size += len(text)
    if current:
        out.append(current)
    return ["\n".join(w) for w in out if not tagged or "[" in "".join(w)]


_FIRST_PERSON = re.compile(r"(?<![A-Za-z])I(?![A-Za-z])")
#: "I" tokens in non-quoted text above which a chapter counts as first-person narrated. ORV ch2-5 have 60-200.
FIRST_PERSON_MIN = 12


def first_person_narrator(store: Store, novel_id: str, chapter: Chapter, cast: list[CastEntry]) -> CastEntry | None:
    """Who "I" is, in a chapter narrated in the first person: the cast member others address but narration rarely names.

    A first-person narrator is called by name only inside other people's quotes ("Dokja-ssi, what do you like?"); in
    narration they are "I". Most-mentioned-overall picked the wrong person on ORV ch2 (Yoo Sangah, who is named
    in narration constantly) and made scores worse, 50.7% -> 47.9%, so this uses where the name appears, not how often."""
    narration = " ".join(QUOTE.sub(" ", b.text) for b in chapter.blocks)
    if len(_FIRST_PERSON.findall(narration)) < FIRST_PERSON_MIN or not cast:
        return None
    quotes = " ".join(m.group(0) for b in chapter.blocks for m in QUOTE.finditer(b.text))
    best: tuple[int, CastEntry] | None = None
    for entry in cast:
        words = {w for surface in entry.surfaces() for w in _norm(surface).split() if len(w) >= 4}
        in_quotes = sum(_norm(quotes).count(w) for w in words)  # substring: 'Dokja-ssi' normalises to 'dokjassi'
        in_narration = sum(_norm(narration).count(w) for w in words)
        if in_quotes >= 2 and in_narration <= 2 and (best is None or in_quotes > best[0]):
            best = (in_quotes, entry)
    return best[1] if best else None


def _prompt(cast: list[CastEntry], text: str, tags: list[str], narrator: CastEntry | None = None) -> str:
    people = "\n".join(
        f"- {e.name}" + (f" (also called: {', '.join(e.aliases[:6])})" if e.aliases else "") for e in cast
    )
    voice = (
        f"This chapter is told in the first person by {narrator.name}: 'I', 'me' and 'my' in the narration mean "
        f"{narrator.name}, and the person who answers {narrator.name} is the other speaker.\n\n"
        if narrator
        else ""
    )
    return (
        f"Known characters (a person may be called by any of their names):\n{people}\n\n{voice}"
        "Below is a passage of a novel. Every quoted utterance is tagged [block.number] just before its opening "
        "quote mark.\n"
        f"For EACH of these tags, name who says or thinks it: {', '.join(tags)}. Give exactly one answer per tag.\n"
        "Use the cues in the text: said/asked, who is addressed, who just acted, and that two people talking to each "
        "other alternate lines. Use the character's name from the list above. A person who is only talked about in the "
        "passage is not the speaker. When unnamed people speak (a crowd, attackers, elders, onlookers) or the text "
        "never says who it is, answer UNKNOWN; do not guess a name from the list. If an unnamed speaker has a "
        "recognisable role (the clan head, an elder, a guard, the driver), answer UNKNOWN: followed by the role, for "
        "example UNKNOWN: academy elder; the same role must always be written the same way. If the speaker is a named person who is not in the list, write the name exactly as the text "
        "gives it. If the quote is not spoken or thought by a person (a sign, written text, a scare quote), "
        f"answer NONE.\n\n{text}\n\n"
        "Answer as JSON with one entry for every tag, like this (replace Name):\n"
        + '{"lines": [' + ", ".join(f'{{"tag": "{t}", "speaker": "Name"}}' for t in tags) + "]}"
    )


def ask_window(
    client: ModelClient,
    cast: list[CastEntry],
    text: str,
    report: SpeakerReport,
    novel_id: str,
    chapter: float,
    narrator: CastEntry | None = None,
) -> dict[str, str]:
    """Answers for every tag in one window, re-asking for omitted tags (the 58% -> 91% fix, decisions D11)."""
    wanted = re.findall(r"\[(\d+\.\d+)\]", text)
    answers: dict[str, str] = {}
    pending = list(wanted)
    for attempt in range(MAX_ATTEMPTS):
        if not pending:
            break
        if attempt:
            report.retried_tags += len(pending)
        result = client.complete(
            Task.READER, _prompt(cast, text, pending, narrator), SpeakerAnswers, novel_id=novel_id, chapter=chapter
        )
        for entry in result.value.lines:
            if entry.tag in pending:
                answers[entry.tag] = entry.speaker
        pending = [t for t in pending if t not in answers]
    report.missing += len(pending)
    return answers


def read_chapter_speakers(store: Store, client: ModelClient, chapter: Chapter) -> SpeakerReport:
    """Attribute every quoted line of one chapter and write the result onto the matching dialogue spans."""
    report = SpeakerReport()
    novel_id, number = chapter.novel_id, chapter.number
    cast = build_cast(store, novel_id, "\n".join(b.text for b in chapter.blocks), number)
    index = NameIndex(cast)
    narrator = first_person_narrator(store, novel_id, chapter, cast)
    answers: dict[str, str] = {}
    for text in windows(chapter):
        answers.update(ask_window(client, cast, text, report, novel_id, number, narrator))

    blocks = {b.index: b.text for b in chapter.blocks}
    spans = [s for s in store.get_spans(novel_id, number) if s.span_type in _QUOTE_SPANS]
    chapter_text = "\n".join(b.text for b in chapter.blocks)
    _mint_new_speakers(store, novel_id, number, answers, index, cast, chapter_text, report)
    for tag, speaker in answers.items():
        report.quotes += 1
        block_index, q = (int(x) for x in tag.split("."))
        starts = quote_starts(blocks.get(block_index, ""))
        if q >= len(starts):
            continue
        span = _span_at(spans, block_index, starts[q])
        if span is None:
            report.no_span += 1
            continue
        key = _norm(speaker)
        if key.startswith(UNKNOWN) and key != UNKNOWN:
            role = _role_slug(speaker)
            if role:
                # One slot per role per chapter, held across lines. The old ladder rotated slots line by line, so a
                # single elder got four voices (RI ch4: academy elder -> anon:4:s7:1/2/3 on consecutive lines).
                store.set_span_speaker(
                    novel_id, span.id, f"{novel_id}:anon:{number:g}:{role}",
                    AttributionMethod.EPITHET_SLOT.value, ROLE_CONFIDENCE,
                )
                report.role_slots += 1
                continue
            key = UNKNOWN
        if key in (UNKNOWN, ""):
            report.unknown += 1
            # The regex ladder's proximity and pronoun guesses named a wrong speaker for crowd lines (RI ch1: the
            # attackers became "Bai Ning Bing"), so only its explicit "X said" survives the model's "unknown".
            if span.attribution_method is not AttributionMethod.EXPLICIT and span.speaker_self_id:
                store.set_span_speaker(novel_id, span.id, None, AttributionMethod.UNRESOLVED.value, 0.0)
                report.cleared += 1
            continue
        if key == NOT_SPEECH:
            report.not_speech += 1
            store.set_span_speaker(novel_id, span.id, None, AttributionMethod.UNRESOLVED.value, 0.0)
            continue
        entry = index.resolve(speaker)
        if entry is None:
            report.unmapped += 1
            continue
        store.set_span_speaker(novel_id, span.id, entry.self_id, AttributionMethod.CONTEXTUAL_LLM.value, MODEL_CONFIDENCE)
        if span.span_type is SpanType.CROWD_REACTION:
            # A named person's line is not a crowd reaction; the classifier mistyped it (LotM ch7 block 39).
            store.set_span_type(novel_id, span.id, SpanType.DIALOGUE.value)
            report.retyped += 1
        report.attributed += 1
    store.conn.commit()
    return report


def _span_at(spans: list[Span], block_index: int, start: int) -> Span | None:
    return next((s for s in spans if s.block_index == block_index and s.start <= start < s.end), None)


def _role_slug(answer: str) -> str:
    """`UNKNOWN: the Academy Elder` -> `academy_elder`; empty when no usable role follows."""
    _head, _sep, role = answer.partition(":")
    words = [w for w in re.findall(r"[a-z]+", role.lower()) if w not in {"the", "a", "an"}]
    return "_".join(words[:3])


_GENERIC = frozenset({"the", "a", "an", "he", "she", "they", "someone", "voice", "man", "woman", "boy", "girl"})


def _mint_new_speakers(
    store: Store,
    novel_id: str,
    number: float,
    answers: dict[str, str],
    index: NameIndex,
    cast: list[CastEntry],
    chapter_text: str,
    report: SpeakerReport,
) -> None:
    """Add a person the model named who the entity table does not hold yet, so a missed character can speak.

    LotM's Daly (ch14, 18 lines) was never detected as a mention, so the cast list could not contain her and the
    model pinned her lines on Welch and Naya. A name is minted only when it is capitalised, appears verbatim in the
    chapter, is not generic, and does not already belong to a non-person entity: "Chanis Gate" spoke 18 lines in the
    old DB because a place was typed as a character, and minting from the model's word alone would repeat that.
    """
    existing = {
        _norm(r["canonical_label"]): r["kind"]
        for r in store.conn.execute(
            "SELECT canonical_label, kind FROM self_entity WHERE novel_id=?", (novel_id,)
        ).fetchall()
    }
    for raw in sorted({a for a in answers.values()}):
        key = _norm(raw)
        if key in (UNKNOWN, NOT_SPEECH, "") or index.resolve(raw) is not None:
            continue
        words = raw.replace("’s", "").split()
        if not (1 <= len(words) <= 4) or any(w[:1].islower() for w in words) or _norm(words[0]) in _GENERIC:
            continue
        if raw not in chapter_text or existing.get(key) not in (None, "", TargetKind.SELF.value):
            continue
        self_id = f"{novel_id}:self:{int(hashlib.sha1(key.encode()).hexdigest(), 16) % 10**10:010d}"
        if key not in existing:
            store.add_self(
                Self(
                    id=self_id, novel_id=novel_id, canonical_label=raw,
                    first_attested_pos=DiscoursePosition(chapter=int(number), offset=0),
                    prominence=Prominence.INCIDENTAL, kind=TargetKind.SELF,
                )
            )
            report.minted += 1
        entry = CastEntry(self_id if key not in existing else _id_of(store, novel_id, key), raw)
        cast.append(entry)
        index._full.setdefault(key, entry)  # noqa: SLF001 - same module family; avoids rebuilding the index


def _id_of(store: Store, novel_id: str, key: str) -> str:
    for r in store.conn.execute("SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (novel_id,)):
        if _norm(r["canonical_label"]) == key:
            return str(r["id"])
    return ""
