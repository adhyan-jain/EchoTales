"""Speaker attribution by a model that is shown the cast list, with an explicit answer per quoted line.

Why this replaces the regex ladder as the primary attributor (decisions D11): on LotM ch7 the existing pipeline
named the right speaker for 16 of 43 lines (37%) because it cannot hold a cast in mind; a local 7B model shown the
cast list got 25/43 with a loose prompt and **39/43 (91%)** once the prompt listed every tag that needed an answer
and re-asked for the ones the model skipped. The first 33 points were missing answers, not wrong ones, so the
output contract (one entry per tag, retry omissions) is the load-bearing part of this module.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from echotales.core.enums import AliasType, AssertedBy, AttributionMethod, Prominence, SpanType, TargetKind, TruthStatus
from echotales.core.interval import FuzzyInterval
from echotales.core.models import AliasBinding, Chapter, DiscoursePosition, Self, Span
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

#: When a list, `read_chapter_speakers` appends one dict per tag (raw model answer, the post-check outcome, the baseline
#: row it replaced). The ablation sets it: v13's raw answers were never recorded, so its 57 misses had to be classified
#: by reading text (speaker_diag REPORT 0).
TRACE: list[dict] | None = None  # type: ignore[type-arg]

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
    role_resolved: int = 0
    role_rejected: int = 0
    cleared: int = 0
    retyped: int = 0
    human_kept: int = 0
    addressee_rejected: int = 0
    gender_rejected: int = 0
    split_quote: int = 0
    second_chance: int = 0
    explicit_kept: int = 0
    first_person: int = 0
    roles_merged: int = 0


#: Korean/Japanese honorific suffixes attached to a name. "Yoo Sangah-ssi" is Yoo Sangah, but without this the matcher saw a
#: new word, resolved nothing, and `_mint_new_speakers` created a duplicate entity that later chapters then answered with.
_HONORIFIC = re.compile(r"[-\s](ssi|nim|sama|san|kun|chan|senpai|sunbae|hyung|noona|oppa|unni)\b", re.IGNORECASE)
_HONORIFIC_SUFFIX = r"[-\s](?:ssi|nim|sama|san|kun|chan|senpai|sunbae|hyung|noona|oppa|unni)"


def _norm(text: str) -> str:
    text = _HONORIFIC.sub("", text.lower().replace("’", "'"))
    return re.sub(r"[^a-z0-9 ]+", "", text).strip()


def _valid_at(alias: AliasBinding, chapter: float) -> bool:
    """Whether the binding holds in story time at this chapter (knowledge time is a separate question)."""
    return alias.retracted_at is None and alias.interval.from_lb <= chapter <= alias.interval.to_ub


def build_cast(store: Store, novel_id: str, chapter_text: str, chapter: float) -> list[CastEntry]:
    """People who can speak in this chapter, shown the way a reader at this chapter knows them.

    Two clocks, kept apart (the research's point-in-time rule): **story time** decides who is on stage, **knowledge
    time** decides what they are called. RI calls its clan head "the clan head" for five chapters before anyone names
    him; the database holds that title bound to Gu Yue Bo from story chapter 1 but learned at chapter 6. A cast built
    from "first attested" dropped him from chapters 1-5, so his lines fell into anonymous slots and got their own
    voice. So an entity is on stage if one of its aliases is valid in story time here and appears in the text, and
    it is shown by its title until its personal name has been learned; a later name is never put in an earlier prompt.
    A title with several holders over time resolves to whoever's interval covers this chapter (transfer is not
    retraction), and one person may hold several titles at once (elder, then first elder).
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
        if entity is None:
            continue
        bindings = store.get_aliases_for(TargetKind.SELF, entity.id)
        titles = [a.alias for a in bindings if a.alias_type is AliasType.TRANSFERABLE_TITLE and _valid_at(a, chapter)]
        name_known = entity.first_attested_pos.chapter <= chapter
        names = [
            a.alias for a in bindings
            if a.alias_type is not AliasType.TRANSFERABLE_TITLE and a.learned_at_pos.chapter <= chapter
        ]
        if name_known:
            entry = CastEntry(entity.id, entity.canonical_label, [x for x in dict.fromkeys(names + titles) if x != entity.canonical_label])
        elif titles:
            shown = sorted(set(titles), key=len, reverse=True)
            entry = CastEntry(entity.id, shown[0], shown[1:])
        else:
            continue
        if not any(len(_norm(x)) >= 3 and _norm(x) in haystack for x in entry.surfaces()):
            continue
        key = _norm(entry.name)
        if key in found:
            continue
        found[key] = entry
        ordered.append((rank.get(entity.prominence.value, 2), -len(entry.name), entry))
    ordered.sort(key=lambda t: (t[0], t[1]))
    return [e for _r, _l, e in ordered[:MAX_CAST]]


def scene_cast(cast: list[CastEntry], seen_text: str, narrator: CastEntry | None) -> list[CastEntry]:
    """The cast members the chapter has introduced by the end of the current window.

    The chapter-wide cast pulled unnamed lines onto people who had not appeared yet: ORV ch3's "a big man in a suit"
    went to Han Myungoh, whom the text names only around b51-53 (speaker_diag REPORT 2 (f), 6.4). The first-person
    narrator stays: narration seldom names him. An empty result falls back to the full cast rather than an empty list."""
    haystack = _norm(seen_text)
    keep = [
        e for e in cast
        if (narrator is not None and e.self_id == narrator.self_id)
        or any(len(_norm(x)) >= 3 and _norm(x) in haystack for x in e.surfaces())
    ]
    return keep or cast


def turn_note(recent: list[str]) -> str:
    """One sentence on who spoke the last lines before this window ("Kim Dokja, unnamed, Yoo Sangah"), '' for the first."""
    if not any(recent):
        return ""
    said = [("an unnamed speaker" if _norm(r).startswith((UNKNOWN, NOT_SPEECH)) or not r else r) for r in recent]
    return f"The last lines before this passage were spoken by, oldest first: {', '.join(said)}. Two people talking alternate.\n\n"


class NameIndex:
    """Maps a name the model wrote back to a cast entry, by full name first and then by a unique word."""

    def __init__(self, cast: list[CastEntry]) -> None:
        self._full: dict[str, CastEntry] = {}
        words: dict[str, list[CastEntry]] = {}
        # Canonical names claim their key first, aliases only fill what is left. The database's alias table is
        # polluted (LotM's Zhou Mingrui carries an alias "Welch"), and with first-come-first-served the answer
        # "Welch" resolved to Zhou Mingrui and a dead man's name voiced Klein (ORV/LotM trace, 2026-10-22).
        for entry in cast:
            key = _norm(entry.name)
            if key:
                self._full.setdefault(key, entry)
        for entry in cast:
            for surface in entry.surfaces():
                key = _norm(surface)
                if key:
                    self._full.setdefault(key, entry)
                for word in key.split():
                    if len(word) >= 4:
                        words.setdefault(word, []).append(entry)
        self._unique_word = {w: es[0] for w, es in words.items() if len({e.self_id for e in es}) == 1}
        # What it takes to say a sentence is "about" an entry: any full surface of it, or a name word only it owns.
        self._mention = []
        for entry in cast:
            forms = {_norm(x) for x in entry.surfaces() if len(_norm(x)) >= 3}
            forms |= {w for w, e in self._unique_word.items() if e.self_id == entry.self_id}
            forms.discard("")
            if forms:
                self._mention.append((entry.self_id, re.compile(
                    r"\b(?:" + "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True)) + r")\b", re.IGNORECASE)))

    def mentioned_in(self, sentence: str) -> set[str]:
        """Self ids of the entries a sentence names."""
        # "Daly's blue eyeshadow" lost its subject when the possessive turned into "dalys" (LotM ch14, reference-chapter
        # scoring 2026-10-23), so the possessive is dropped before matching.
        low = _norm(re.sub(r"['’]s\b", "", sentence))
        return {sid for sid, rx in self._mention if rx.search(low)}

    def resolve(self, answer: str) -> CastEntry | None:
        key = _norm(answer)
        if key in self._full:
            return self._full[key]
        # "Mr. Fool" / "Miss Justice": drop a leading title word and try again, then a unique name word.
        parts = key.split()
        if parts and self._full.get(" ".join(parts[1:])):
            return self._full[" ".join(parts[1:])]
        # A name word inside a long phrase is not the person ("Many elders watching Fang Yuan in the dark", RI ch5 b25, went to
        # Fang Yuan): the word fallback is for "Mr. Fool" / "Klein-san" shaped answers only.
        if len(parts) > 3:
            return None
        hits = {self._unique_word[w].self_id: self._unique_word[w] for w in parts if w in self._unique_word}
        return next(iter(hits.values())) if len(hits) == 1 else None


def windows(chapter: Chapter, *, tagged: bool = True, require_quote: bool | None = None) -> list[str]:
    """Consecutive whole blocks up to `WINDOW_CHARS` per window.

    `tagged=True` inserts `[block.q]` before every quote and drops windows with no quote (the speaker pass);
    `tagged=False` keeps every window as plain text (the facts pass reads narration too). `require_quote=False` keeps
    the tags but also the quote-free windows (the delivery pass reads the mood of narration-only passages)."""
    if require_quote is None:
        require_quote = tagged
    # Local windows were sized for a 4-8k context; a hosted model with a longer one reads proportionally more per
    # call (fewer cuts through a conversation, so more speaker evidence per window). 1 locally: results unchanged.
    from echotales.pipeline.compute import policy

    limit = WINDOW_CHARS * policy().context_scale
    out: list[list[str]] = []
    current: list[str] = []
    size = 0
    for block in sorted(chapter.blocks, key=lambda b: b.index):
        text = tag_block(block.index, block.text) if tagged else block.text
        if size + len(text) > limit and current:
            out.append(current)
            current, size = [], 0
        current.append(f"#{block.index}: {text}")
        size += len(text)
    if current:
        out.append(current)
    return ["\n".join(w) for w in out if not require_quote or "[" in "".join(w)]


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


#: The first-person narrator last identified in each novel. A first-person book keeps its narrator: ORV's "I" is Kim
#: Dokja in every chapter, but ch3 never names him (he is not even in that chapter's cast) and ch4 names him once, so
#: per-chapter detection found him in 2 of 4 reference chapters and the prompt's narrator note was missing for the rest.
_NARRATORS: dict[str, CastEntry] = {}
NARRATOR_CARRY = os.environ.get("ECHOTALES_READER_NARRATOR_CARRY", "1") == "1"


def narrator_for(store: Store, novel_id: str, chapter: Chapter, cast: list[CastEntry]) -> CastEntry | None:
    """The narrator of a first-person chapter: found in this chapter, else the one the novel's earlier chapters found
    (added to `cast` so the model can answer with the name). None for a chapter not narrated in the first person."""
    found = first_person_narrator(store, novel_id, chapter, cast)
    if found is not None:
        _NARRATORS[novel_id] = found
        return found
    narration = " ".join(QUOTE.sub(" ", b.text) for b in chapter.blocks)
    earlier = _NARRATORS.get(novel_id)
    if not NARRATOR_CARRY or earlier is None or len(_FIRST_PERSON.findall(narration)) < FIRST_PERSON_MIN:
        return None
    if not any(e.self_id == earlier.self_id for e in cast):
        cast.append(earlier)
    return earlier


def _prompt(cast: list[CastEntry], text: str, tags: list[str], narrator: CastEntry | None = None, note: str = "") -> str:
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
        f"Known characters (a person may be called by any of their names):\n{people}\n\n{voice}{note}"
        "Below is a passage of a novel. Every quoted utterance is tagged [block.number] just before its opening "
        "quote mark.\n"
        f"For EACH of these tags, name who says or thinks it: {', '.join(tags)}. Give exactly one answer per tag.\n"
        "Use the cues in the text: said/asked, who is addressed, who just acted, and that two people talking to each "
        "other alternate lines. Use the character's name from the list above. A person who is only talked about in the "
        "passage is not the speaker. When unnamed people speak (a crowd, attackers, elders, onlookers) or the text "
        "never says who it is, answer UNKNOWN; do not guess a name from the list. "
        + (
            "A line with no speech tag, spoken by a group or by someone the passage only calls 'a man', 'a woman', 'a voice' "
            "or 'someone', is UNKNOWN even when a listed person stands nearby. A person the line calls by a noun or by "
            "a name ('Human,' 'Child,' 'Dokja-ssi.') is the one spoken TO, never the speaker. "
            if CROWD_RULE
            else ""
        )
        + "If an unnamed speaker is described by a role or title in the text, answer UNKNOWN: followed by those same words copied from the passage, for example UNKNOWN: old man; the same role must always be written the same way. If the speaker is a named person who is not in the list, write the name exactly as the text "
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
    only: list[str] | None = None,
    note: str = "",
) -> dict[str, str]:
    """Answers for every tag in one window, re-asking for omitted tags (the 58% -> 91% fix, decisions D11).

    `only` limits the question to those tags (the second chance for answers the checks rejected)."""
    wanted = only if only is not None else re.findall(r"\[(\d+\.\d+)\]", text)
    answers: dict[str, str] = {}
    pending = list(wanted)
    for attempt in range(MAX_ATTEMPTS):
        if not pending:
            break
        if attempt:
            report.retried_tags += len(pending)
        result = client.complete(
            Task.READER, _prompt(cast, text, pending, narrator, note), SpeakerAnswers, novel_id=novel_id, chapter=chapter
        )
        for entry in result.value.lines:
            if entry.tag in pending:
                answers[entry.tag] = entry.speaker
        pending = [t for t in pending if t not in answers]
    report.missing += len(pending)
    return answers


def addresses(quote: str, name: str) -> bool:
    """True when the quote opens by calling `name` ("My dear Mr. Bennet,", "Alice, come here!"): a vocative at the very
    start, ended by a comma, "!", "?" or a full stop, so a name later in the sentence or narration is not one.

    An honorific suffix may follow the name: ORV ch3 b51 `"Yoo Sangah-ssi. Isn't that Department Head Han..."` is
    spoken TO Sangah, and the old pattern (comma, "!" or "?" only) let it through as hers (speaker_diag REPORT 6.5)."""
    head = r"^[\W_]*(?:my\s+)?(?:dear\s+)?" + re.escape(name)
    if re.match(head + r"\s*[,!?]", quote, re.IGNORECASE):
        return True
    # A full stop counts only after an honorific ("Yoo Sangah-ssi."): a bare "Fang Yuan." is as often a speaker giving
    # their own name as a call, and a rule that is unsure must leave the line to the model.
    return re.match(head + _HONORIFIC_SUFFIX + r"\s*[,!?.]", quote, re.IGNORECASE) is not None


_SPEECH_VERBS = r"(?:said|cried|replied|returned|asked|answered|exclaimed|added|continued|observed|whispered|muttered|shouted)"
_TAG_SUBJECT = re.compile(
    rf"\b{_SPEECH_VERBS}\s+(she|he|his\s+(?:wife|lady)|her\s+husband)\b|\b(she|he)\s+{_SPEECH_VERBS}\b", re.IGNORECASE
)
_FEMALE_TITLES = frozenset({"mrs", "miss", "ms", "lady", "madam", "dame"})
_MALE_TITLES = frozenset({"mr", "sir", "lord", "master"})


def tag_gender(quote: str) -> str:
    """"female" or "male" when the speech tag after the quote names its speaker by pronoun or relation ("returned she",
    "cried his wife", "said he"), else "". `quote` starts just after the opening quotation mark."""
    close = min((i for i in (quote.find("”"), quote.find('"')) if i >= 0), default=-1)
    if close < 0:
        return ""
    found = _TAG_SUBJECT.search(quote[close + 1:close + 90])
    if not found:
        return ""
    subject = (found.group(1) or found.group(2)).lower()
    return "female" if subject in ("she",) or subject.startswith("his ") else "male"


def continues_after_tag(text: str, starts: list[int], q: int) -> bool:
    """Whether quote `q` resumes the previous quote's sentence after a short speech tag ending in a comma:
    “Come in,” said Alice to him, “and sit down.” One speaker's sentence cut by its tag. A tag that ends a sentence
    ("said Alice.") starts a new turn and does not count."""
    if q < 1 or q >= len(starts):
        return False
    closes = [i for i in (text.find("”", starts[q - 1] + 1), text.find('"', starts[q - 1] + 1)) if i >= 0]
    if not closes:
        return False
    gap = text[min(closes) + 1:starts[q]]
    return 0 < len(gap.strip()) <= 80 and gap.rstrip().endswith((",", ";", ":")) and re.search(_SPEECH_VERBS, gap, re.IGNORECASE) is not None


def title_gender(name: str) -> str:
    """The gender a name's honorific states ("Mr. Bennet" -> male, "Miss Bingley" -> female), else ""."""
    first = name.strip().split(" ", 1)[0].rstrip(".").casefold()
    return "female" if first in _FEMALE_TITLES else "male" if first in _MALE_TITLES else ""


def rejection(store: Store, entry: CastEntry, quote_text: str) -> tuple[str, str]:
    """("addressee" | "gender" | "", the gender the tag names) when `entry` cannot be who speaks `quote_text`.

    "addressee": the line opens by calling this person. "gender": the tag after the quote ("returned she") names the
    other gender than the entry's title or recorded gender."""
    # Any name the person is called by, not only the display name: "Dokja-ssi," addresses Kim Dokja.
    if any(addresses(quote_text, surface) for surface in entry.surfaces() if len(_norm(surface)) >= 3):
        return "addressee", ""
    side = tag_gender(quote_text)
    if side:
        from echotales.pipeline.reader.facts_pass import _recorded_gender

        known = title_gender(entry.name) or _recorded_gender(store, entry.self_id)
        if known in ("male", "female") and known != side:
            return "gender", known
    return "", ""


_TAG_VERBS = (
    r"(?:said|asked|replied|answered|responded|whispered|muttered|murmured|mumbled|shouted|yelled|cried|called|"
    r"exclaimed|inquired|continued|added|returned|observed|retorted)"
)
_FP_AFTER = re.compile(rf"^\W{{0,3}}I\s+(?:\w+\s+){{0,3}}?{_TAG_VERBS}\b", re.IGNORECASE)
_FP_BEFORE = re.compile(rf"(?<![A-Za-z])I\b[^.!?\"“”]{{0,90}}?\b{_TAG_VERBS}\b[^.!?\"“”]{{0,30}}$")


def _around_quote(block_text: str, q: int) -> tuple[str, str]:
    """(the clause just before quote `q`, the clause just after it), cut at the neighbouring quote or sentence end."""
    matches = list(QUOTE.finditer(block_text))
    if q >= len(matches):
        return "", ""
    m = matches[q]
    before = block_text[max(0, m.start() - 140):m.start()]
    cut = max(before.rfind(c) for c in '.!?”"')
    before = before[cut + 1:] if cut >= 0 else before
    after = block_text[m.end():m.end() + 140]
    ends = [i for i in (after.find("“"), after.find('"')) if i >= 0]
    after = after[:min(ends)] if ends else after
    return before, after


def first_person_tag(block_text: str, q: int) -> bool:
    """Whether quote `q` carries a first-person speech tag in its own block: `"...?" I asked`, `I turned and asked, "..."`.
    In a first-person chapter that line is the narrator's whatever the model said (ORV ch3 b15, speaker_diag 6.3)."""
    before, after = _around_quote(block_text, q)
    return bool(_FP_AFTER.match(after)) or bool(_FP_BEFORE.search(before))


def _speaker_words(store: Store, self_id: str) -> list[str]:
    entity = store.get_self(self_id)
    names = [entity.canonical_label] if entity else [self_id]
    names += [a.alias for a in store.get_aliases_for(TargetKind.SELF, self_id) if a.retracted_at is None]
    words = [w for n in list(names) for w in _norm(n).split() if len(w) >= 4]
    return [x for x in dict.fromkeys(_norm(n) for n in names + words) if len(x) >= 3]


def own_explicit_tag(store: Store, self_id: str, block_text: str, q: int) -> bool:
    """Whether the quote's own block tags `self_id` as its speaker: the name then a speech verb in the clause right after
    (`"..." Yoo Sangah replied proudly`) or right before (`Han said, "..."`), the name being the subject.

    The reader overwrote a correct EXPLICIT Yoo Sangah with Kim Dokja on ORV ch2 b27. An EXPLICIT row can also be a tag
    borrowed from the neighbouring paragraph (ORV ch4 b34, b36), and then the model may still overrule it."""
    before, after = _around_quote(block_text, q)
    before, after = _norm_keep(before), _norm_keep(after)
    for name in _speaker_words(store, self_id):
        n = r"\.?\s+".join(re.escape(w) for w in name.split())  # "mr bennet" must match the text's "Mr. Bennet"
        if re.match(rf"^\W{{0,3}}{_TAG_VERBS}\s+(?:the\s+)?{n}\b", after, re.IGNORECASE):
            return True
        for where, clause in (("after", after), ("before", before)):
            for m in re.finditer(rf"\b{n}\b", clause, re.IGNORECASE):
                if where == "after" and re.sub(r"(?i:the)|\W+", "", clause[:m.start()]):
                    continue  # after the quote the tag opens with the name
                # "she looked at Zhou Mingrui and said," names the listener: a name after a preposition is not the subject
                lead = clause[:m.start()].split()
                while lead and lead[-1][:1].isupper() and not lead[-1].endswith(","):
                    lead.pop()  # the match may be one word of a longer name ("at Zhou [Mingrui]")
                if lead and lead[-1].lower().strip(",") in _PREPOSITIONS:
                    continue
                found = re.match(rf"((?:\W+[\w'-]+){{0,3}}?)\W+{_TAG_VERBS}\b(.*)$", clause[m.end():], re.IGNORECASE | re.DOTALL)
                if not found or any(w.lower() in _PREPOSITIONS for w in re.findall(r"[\w'-]+", found.group(1))):
                    continue
                if where == "before" and len(found.group(2)) > 25:
                    continue  # the verb is not the one introducing this quote
                return True
    return False


_PREPOSITIONS = frozenset({"at", "to", "toward", "towards", "with", "from", "for", "of", "over", "by", "beside", "about", "upon", "on"})


def _norm_keep(text: str) -> str:
    """Lower-cased text with honorific suffixes dropped and punctuation that ends clauses kept."""
    return _HONORIFIC.sub("", text.replace("’", "'"))


def _merge_roles(role_spans: dict[str, list[Span]]) -> int:
    """One slot for a role the model wrote several ways in a chapter ("academy elder", "elder", "elder of the academy").

    RI ch4: the academy elder spoke 9 lines; the model's wording varied, each wording became its own title entity or
    anonymous slot, and he got a different voice per line (speaker_diag REPORT 2 (j), 6.2). A role merges into the
    role whose words contain all of its own, provided that target is unique: "first elder" and "second elder" stay two."""
    content = {r: frozenset(r.split("_")) - {"of", "the", ""} for r in role_spans}
    target: dict[str, str] = {}
    for r in role_spans:
        cands = [o for o in role_spans if content[o] >= content[r]]
        maximal = {content[o] for o in cands if not any(content[o] < content[p] for p in cands)}
        if len(maximal) != 1:
            continue
        group = [o for o in role_spans if content[o] == next(iter(maximal))]
        target[r] = max(group, key=lambda o: (len(role_spans[o]), len(o), o))
    merged: dict[str, list[Span]] = {}
    moved = 0
    for r, spans in role_spans.items():
        t = target.get(r, r)
        moved += t != r
        merged.setdefault(t, []).extend(spans)
    role_spans.clear()
    role_spans.update(merged)
    return moved


def _second_chance(
    store: Store, client: ModelClient, cast: list[CastEntry], index: NameIndex, narrator: CastEntry | None,
    answers: dict[str, str], tag_window: dict[str, str], quote_of: dict[str, str], report: SpeakerReport,
    novel_id: str, chapter: float,
) -> None:
    """Re-ask once, with the impossible people removed, for answers the addressee/gender checks would reject.

    Pride and Prejudice ch1: the model credits "My dear Mr. Bennet," and "returned she" to Mr. Bennet, the checks rightly
    refuse, and the line stayed unknown even once Mrs. Bennet was in the cast. Telling the model who it cannot be
    (not who it is) keeps the checks' precision and lets it find the wife."""
    if not SECOND_CHANCE:
        return
    groups: dict[tuple[str, frozenset[str]], list[str]] = {}
    for tag, speaker in answers.items():
        entry = index.resolve(speaker) if speaker else None
        if entry is None or tag not in quote_of:
            continue
        kind, known = rejection(store, entry, quote_of[tag])
        if not kind:
            continue
        banned = {entry.self_id}
        if kind == "gender":
            banned |= {e.self_id for e in cast if title_gender(e.name) == known}
        groups.setdefault((tag_window[tag], frozenset(banned)), []).append(tag)
    for (text, banned), tags in groups.items():
        smaller = [e for e in cast if e.self_id not in banned]
        if not smaller:
            continue
        report.second_chance += len(tags)
        gone = ", ".join(e.name for e in cast if e.self_id in banned)
        # Without this the model took the next name on the list: with Mr. Bennet removed, P&P ch1's lines went to Mrs.
        # Long, who is only talked about, because the chapter's cast cannot yet hold the wife ("his lady" until ch2).
        note = (
            f"A first reading of tags {', '.join(tags)} named {gone}, which cannot be right. The speaker may not be on this "
            "list at all: a husband, wife or relative only called 'his wife', 'his lady' or 'her husband' in this "
            "chapter is not listed yet. Pick a listed person only if the text clearly shows it; otherwise answer "
            "UNKNOWN: followed by those words copied from the passage.\n\n"
        )
        again = ask_window(client, smaller, text, report, novel_id, chapter, narrator, only=tags, note=note)
        for tag in tags:
            if tag in again:
                answers[tag] = again[tag]


def read_chapter_speakers(store: Store, client: ModelClient, chapter: Chapter) -> SpeakerReport:
    """Attribute every quoted line of one chapter and write the result onto the matching dialogue spans."""
    report = SpeakerReport()
    novel_id, number = chapter.novel_id, chapter.number
    cast = build_cast(store, novel_id, "\n".join(b.text for b in chapter.blocks), number)
    narrator = narrator_for(store, novel_id, chapter, cast)
    index = NameIndex(cast)
    answers: dict[str, str] = {}
    tag_window: dict[str, str] = {}
    seen_text = ""
    recent: list[str] = []
    for text in windows(chapter):
        seen_text += "\n" + text
        shown = scene_cast(cast, seen_text, narrator) if SCENE_CAST else cast
        got = ask_window(client, shown, text, report, novel_id, number, narrator, note=turn_note(recent) if PREV_SPEAKERS else "")
        answers.update(got)
        tags = re.findall(r"\[(\d+\.\d+)\]", text)
        for tag in tags:
            tag_window[tag] = text
        recent = [got.get(t, "") for t in tags][-3:]

    blocks = {b.index: b.text for b in chapter.blocks}
    quote_of: dict[str, str] = {}
    for tag in answers:
        block_index, q = (int(x) for x in tag.split("."))
        starts = quote_starts(blocks.get(block_index, ""))
        if q < len(starts):
            quote_of[tag] = blocks[block_index][starts[q]:].lstrip("“\"")
    raw_answers = dict(answers)
    _second_chance(store, client, cast, index, narrator, answers, tag_window, quote_of, report, novel_id, number)
    chapter_words = set(_norm("\n".join(blocks.values())).split())
    role_spans: dict[str, list[Span]] = {}
    spans = [s for s in store.get_spans(novel_id, number) if s.span_type in _QUOTE_SPANS]
    chapter_text = "\n".join(b.text for b in chapter.blocks)
    _mint_new_speakers(store, novel_id, number, answers, index, cast, chapter_text, report)
    for tag, speaker in answers.items():
        report.quotes += 1
        block_index, q = (int(x) for x in tag.split("."))
        starts = quote_starts(blocks.get(block_index, ""))
        if q >= len(starts):
            continue
        quote_text = blocks[block_index][starts[q]:].lstrip("“\"")
        if looks_written(quote_text):
            speaker = NOT_SPEECH
        span = _span_at(spans, block_index, starts[q])
        if span is None:
            report.no_span += 1
            continue

        fired: list[str] = []  # rule names that changed this line's outcome, for per-rule precision in the ablation

        def note(outcome: str, final: str | None = None, _tag: str = tag, _span: Span = span, _fired: list[str] = fired) -> None:
            if TRACE is not None:
                TRACE.append({
                    "chapter": number, "tag": _tag, "raw": raw_answers.get(_tag), "answer": answers[_tag],
                    "outcome": outcome, "final": final, "rules": list(_fired), "baseline_method": _span.attribution_method.value,
                    "baseline_speaker": _span.speaker_self_id, "quote": quote_text[:160],
                })

        if span.attribution_method is AttributionMethod.HUMAN:
            # A reviewer's decision outranks the model; the re-run used to overwrite it and the correction was
            # already marked applied, so it was never replayed.
            report.human_kept += 1
            note("human_kept")
            continue
        if span.attribution_method is AttributionMethod.EXPLICIT and span.speaker_self_id and own_explicit_tag(
            store, span.speaker_self_id, blocks.get(block_index, ""), q
        ):
            report.explicit_kept += 1
            fired.append("explicit_kept")
            note("explicit_kept", span.speaker_self_id)
            continue
        if narrator is not None and first_person_tag(blocks.get(block_index, ""), q):
            if _norm(speaker) != _norm(narrator.name):
                report.first_person += 1
                fired.append("first_person")
            speaker = narrator.name
        if continues_after_tag(blocks.get(block_index, ""), starts, q):
            # The second half of a quote cut by its tag has the first half's speaker, whatever the model answered for
            # it: with the first half left unknown (addressee or gender check) the model still credited the second to
            # the one name it knew (Pride and Prejudice ch1, Mr. Bennet).
            previous = _span_at(spans, block_index, starts[q - 1])
            if previous is not None:
                row = store.conn.execute(
                    "SELECT speaker_self_id FROM span WHERE novel_id=? AND id=?", (novel_id, previous.id)
                ).fetchone()
                report.split_quote += 1
                note("split_quote", row[0] if row else None)
                if row and row[0]:
                    store.set_span_speaker(novel_id, span.id, row[0], AttributionMethod.CONTEXTUAL_LLM.value, MODEL_CONFIDENCE)
                    report.attributed += 1
                elif span.attribution_method is not AttributionMethod.EXPLICIT and span.speaker_self_id:
                    store.set_span_speaker(novel_id, span.id, None, AttributionMethod.UNRESOLVED.value, 0.0)
                continue
        key = _norm(speaker)
        if not key.startswith((UNKNOWN, NOT_SPEECH)) and key and index.resolve(speaker) is None:
            kind = describes_a_speaker(speaker)
            if kind:
                fired.append("described_speaker")
                speaker = f"UNKNOWN: {speaker}" if kind == "role" else UNKNOWN
                key = _norm(speaker)
        if key.startswith(UNKNOWN) and key != UNKNOWN:
            # The model often writes a known person after UNKNOWN ("UNKNOWN: Dunn Smith", LotM ch14): the format
            # example invited a hybrid. If what follows is a cast member, that is the answer, not a role.
            named = index.resolve(speaker.partition(":")[2]) if ":" in speaker else None
            if named is not None:
                speaker, key = named.name, _norm(named.name)
        if key.startswith(UNKNOWN) and key != UNKNOWN:
            role = _role_slug(speaker)
            # The model copied "clan head" into an ORV chapter that has no clan head: its own prompt example. A
            # role it claims must be made of words the chapter actually contains.
            if role and not all(w in chapter_words for w in role.split("_")):
                report.role_rejected += 1
                role = ""
            if role:
                note("role_slot", role)
                # Written after the chapter-wide pass below: a role the chapter later names is that person, and
                # only a role nobody names becomes a title entity of its own.
                report.role_slots += 1
                role_spans.setdefault(role, []).append(span)
                continue
            key = UNKNOWN
        if key in (UNKNOWN, ""):
            report.unknown += 1
            # The regex ladder's proximity and pronoun guesses named a wrong speaker for crowd lines (RI ch1: the
            # attackers became "Bai Ning Bing"), so only its explicit "X said" survives the model's "unknown".
            if span.speaker_self_id and (
                span.attribution_method is not AttributionMethod.EXPLICIT
                # An EXPLICIT name that the line's own block never mentions was borrowed from a neighbouring paragraph
                # (ORV ch4 b34/b36, Lee Hyunsung); the model's UNKNOWN is then the better reading. A name in the block
                # still wins: that is a tag the rules may simply not have parsed.
                or not any(re.search(rf"\b{re.escape(w)}\b", _norm(blocks.get(block_index, ""))) for w in _speaker_words(store, span.speaker_self_id))
            ):
                if span.attribution_method is AttributionMethod.EXPLICIT:
                    fired.append("borrowed_explicit_cleared")
                store.set_span_speaker(novel_id, span.id, None, AttributionMethod.UNRESOLVED.value, 0.0)
                report.cleared += 1
            note("unknown")
            continue
        if key == NOT_SPEECH:
            note("not_speech")
            report.not_speech += 1
            store.set_span_speaker(novel_id, span.id, None, AttributionMethod.UNRESOLVED.value, 0.0)
            if span.span_type is SpanType.DIALOGUE:
                # Written text or a scare quote is narration, not a line to voice (audit: 5 scare-quote
                # sentences voiced as dialogue on LotM ch7).
                store.set_span_type(novel_id, span.id, SpanType.NARRATION_DESCRIPTION.value)
                report.retyped += 1
            continue
        entry = index.resolve(speaker)
        if entry is None:
            note("unmapped")
            report.unmapped += 1
            continue
        kind, _ = rejection(store, entry, quote_text)
        if kind:
            # "addressee": the line opens by calling this person, so they are who is spoken to, not who speaks.
            # "gender": "returned she" cannot be Mr. Bennet. Left unknown, not guessed (a second chance with this
            # person removed has already been tried above).
            if kind == "addressee" and not addresses(quote_text, entry.name):
                fired.append("vocative_ext")  # only the widened pattern or an alias caught it
            note(f"rejected_{kind}", entry.self_id)
            if kind == "addressee":
                report.addressee_rejected += 1
            else:
                report.gender_rejected += 1
            if span.attribution_method is not AttributionMethod.EXPLICIT and span.speaker_self_id:
                store.set_span_speaker(novel_id, span.id, None, AttributionMethod.UNRESOLVED.value, 0.0)
            continue
        note("named", entry.self_id)
        store.set_span_speaker(novel_id, span.id, entry.self_id, AttributionMethod.CONTEXTUAL_LLM.value, MODEL_CONFIDENCE)
        if span.span_type is SpanType.CROWD_REACTION:
            # A named person's line is not a crowd reaction; the classifier mistyped it (LotM ch7 block 39).
            store.set_span_type(novel_id, span.id, SpanType.DIALOGUE.value)
            report.retyped += 1
        report.attributed += 1
    report.roles_merged += _merge_roles(role_spans)
    resolved_roles = _reconcile_roles(store, client, chapter, cast, index, role_spans, report) if role_spans and RECONCILE_ROLES else set()
    for role, role_lines in role_spans.items():
        if role in resolved_roles:
            continue
        holder = _title_entity(store, novel_id, number, role)
        for span in role_lines:
            store.set_span_speaker(novel_id, span.id, holder, AttributionMethod.EPITHET_SLOT.value, ROLE_CONFIDENCE)
    store.conn.commit()
    return report


#: Prompt-context switches, each measurable on its own in the ablation (speaker_diag REPORT 6.3, 6.4).
#: SCENE_CAST: a window shows only people the chapter has introduced by the end of that window, not the whole chapter's cast
#: (ORV ch3 gave six lines to Han Myungoh before the text names him). PREV_SPEAKERS: the window's prompt says who spoke the
#: last lines of the previous window (turn-taking across a cut). CROWD_RULE: untagged crowd/"a man" lines are UNKNOWN and
#: a person called by a noun is the listener.
SCENE_CAST = os.environ.get("ECHOTALES_READER_SCENE_CAST", "1") == "1"
PREV_SPEAKERS = os.environ.get("ECHOTALES_READER_PREV_SPEAKERS", "1") == "1"
CROWD_RULE = os.environ.get("ECHOTALES_READER_CROWD_RULE", "1") == "1"

#: Switch for the re-ask of rejected answers (`_second_chance`), so an ablation can measure it on the reference chapters.
SECOND_CHANCE = os.environ.get("ECHOTALES_READER_SECOND_CHANCE", "1") == "1"

#: Switch for the chapter-wide role -> name pass, so an ablation can turn it off.
RECONCILE_ROLES = os.environ.get("ECHOTALES_READER_RECONCILE", "1") == "1"


class RoleAnswer(BaseModel):
    character: str = "NONE"


def _role_evidence(chapter: Chapter, role: str, cast: list[CastEntry], limit: int = 1800) -> str:
    """Sentences of the whole chapter that mention the role word or a cast name: where a "soldier" gets called Lee."""
    words = [w for w in role.split("_") if len(w) >= 3]
    surfaces = [x for e in cast for x in e.surfaces() if len(_norm(x)) >= 3]
    keep: list[str] = []
    for block in chapter.blocks:
        for sentence in re.split(r"(?<=[.!?\"”])\s+", block.text):
            low = _norm(sentence)
            if any(w in low for w in words) or any(_norm(x) in low for x in surfaces):
                keep.append(sentence.strip())
    text, out = 0, []
    for sentence in keep:
        if text + len(sentence) > limit:
            break
        out.append(sentence)
        text += len(sentence)
    return " ".join(out)


def _reconcile_prompt(people: str, role: str, examples: str, evidence: str) -> str:
    """Which known character a role slot is. Strict on purpose: ORV ch3's "big man in a suit" (an unnamed passenger) was matched
    to Han Myungoh, named in the same carriage, three lines wrong; ORV ch4's "sturdy man" really is Lee Hyunsung because the text
    says so ("That 'Lee Hyunsung' was this man"). Only the second kind should pass."""
    return (
        f"Known characters: {people}\n\nIn this chapter some lines are spoken by a person only called by the role "
        f"'{role.replace('_', ' ')}' (lines such as: {examples}).\nUsing the sentences below, which known "
        "character is that person? Answer a name from the list only if a sentence says outright that this person is that "
        "character (for example 'that man was X'). Someone who merely stands nearby, speaks next to them or is named "
        "elsewhere is not the same person. Otherwise answer NONE.\n\n"
        f"Sentences:\n{evidence}\n\n"
        'Answer as JSON: {"character": "Name or NONE"}'
    )


def _reconcile_roles(
    store: Store, client: ModelClient, chapter: Chapter, cast: list[CastEntry], index: NameIndex,
    role_spans: dict[str, list[Span]], report: SpeakerReport,
) -> set[str]:
    """A role slot ("the soldier", "the host") may be a character the chapter names later (ORV ch4: "Soldier-nim!" is
    Lee Hyunsung; LotM ch14: the "ethereal voice" is Daly). A window sees only ~2,600 characters, so the first pass
    cannot connect them; this one shows the whole chapter's relevant sentences, once per role."""
    people = ", ".join(e.name for e in cast)
    resolved: set[str] = set()
    for role, spans in role_spans.items():
        evidence = _role_evidence(chapter, role, cast)
        examples = " | ".join(s.text[:80] for s in spans[:3])
        prompt = _reconcile_prompt(people, role, examples, evidence)
        try:
            answer = client.complete(Task.READER, prompt, RoleAnswer, novel_id=chapter.novel_id, chapter=chapter.number).value.character
        except Exception:  # noqa: BLE001 - one failed role must not stop the chapter
            continue
        entry = index.resolve(answer)
        if entry is None:
            continue
        for span in spans:
            # A role the chapter names is a named person, so it gets the model-answer confidence. At the role-slot
            # 0.5 the voice stage called every one of these lines "unconfirmed" and gave it a random voice, which
            # undid the whole reconcile pass (audit M1).
            store.set_span_speaker(
                chapter.novel_id, span.id, entry.self_id, AttributionMethod.CONTEXTUAL_LLM.value, MODEL_CONFIDENCE
            )
        report.role_resolved += len(spans)
        resolved.add(role)
    return resolved


_GENERIC_ROLE_WORDS = frozenset({
    "man", "woman", "boy", "girl", "child", "voice", "someone", "people", "crowd", "person", "youth", "stranger",
    "onlooker", "onlookers", "men", "women", "others", "one", "another", "figure", "speaker", "narrator", "who",
    "unknown", "unnamed", "passerby", "bystander", "voices", "enemy", "enemies", "attacker", "attackers",
})


#: Words that make a role an *office or rank* someone holds and can lose or inherit. Only these roles become persistent
#: title entities. Measured on ORV with gemma2:9b: minting every non-generic descriptor ("dokkaebi" the creature,
#: "grandmother", "old man", "first man") put those into later chapters' cast lists, and the model then gave 12 of
#: Kim Dokja's lines in ch5 to "dokkaebi" (speakers 32 -> 18 on that chapter).
_TITLE_WORDS = frozenset({
    "head", "leader", "chief", "elder", "elders", "patriarch", "matriarch", "master", "grandmaster", "lord", "lady",
    "king", "queen", "emperor", "empress", "prince", "princess", "duke", "duchess", "captain", "commander", "general",
    "marshal", "inspector", "officer", "magistrate", "minister", "president", "principal", "abbot", "priest", "bishop",
    "ancestor", "sovereign", "chancellor", "governor", "mayor", "sheriff", "judge", "warden", "headmaster", "dean",
    "professor", "teacher", "doctor", "soldier", "guard", "sergeant", "lieutenant", "colonel", "admiral", "baron",
    "count", "sect", "overseer", "steward", "regent", "heir", "patriarchs",
})


def _title_entity(store: Store, novel_id: str, number: float, role: str) -> str:
    """The persistent entity for a title nobody has been named for yet ("academy elder"), or a chapter slot if generic.

    A title is a transferable alias, not a second character (`resolve/title_holders.py`): it keeps one id across
    chapters, so the same elder keeps one voice; when a later chapter names the holder the name is bound to this entity
    (a facts-pass identity claim), and a handover closes this holder's interval and opens the next one's. A chapter-scoped
    slot could do none of that. Generic roles ("a man", "attackers") stay chapter-scoped: they are not one person."""
    text = role.replace("_", " ")
    words = role.split("_")
    if all(w in _GENERIC_ROLE_WORDS for w in words) or not any(w in _TITLE_WORDS for w in words):
        return f"{novel_id}:anon:{number:g}:{role}"
    entity_id = f"{novel_id}:title:{role}"
    if store.get_self(entity_id) is None:
        pos = DiscoursePosition(chapter=int(number), offset=0)
        store.add_self(
            Self(id=entity_id, novel_id=novel_id, canonical_label=text, first_attested_pos=pos,
                 prominence=Prominence.INCIDENTAL, kind=TargetKind.SELF)
        )
        store.add_alias_binding(
            novel_id,
            AliasBinding(
                alias=text, alias_type=AliasType.TRANSFERABLE_TITLE, target_kind=TargetKind.SELF, target_id=entity_id,
                interval=FuzzyInterval.open_ended(int(number), last_evidence=int(number)), learned_at_pos=pos,
                observer_id="reader", asserted_by=AssertedBy.INFERENCE, truth_status=TruthStatus.TRUE,
                evidence=f"speaks as '{text}' in chapter {number:g}", confidence=ROLE_CONFIDENCE,
            ),
        )
    return entity_id


def _span_at(spans: list[Span], block_index: int, start: int) -> Span | None:
    return next((s for s in spans if s.block_index == block_index and s.start <= start < s.end), None)


_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
#: A quote that opens with a date is a dated written entry (a diary, a log, a letter), never speech. LotM ch21 quotes
#: nine of Emperor Roselle's diary entries ("18th November. ...", "1184, 1st January. ..."); the old pipeline voiced all
#: of them as dialogue (13 false-dialogue spans on that chapter) and the 7B model did not answer NONE for them.
_DATED_ENTRY = re.compile(
    rf"^\W*(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\b|(?:{_MONTHS})\s+\d{{1,2}}\b|\d{{4}}\s*,)", re.IGNORECASE
)


def looks_written(quote_text: str) -> bool:
    """Whether a quoted string is a dated written entry rather than something a person says."""
    return bool(_DATED_ENTRY.match(quote_text))


def _role_slug(answer: str) -> str:
    """`UNKNOWN: the Academy Elder` -> `academy_elder`; empty when no usable role follows."""
    _head, _sep, role = answer.partition(":")
    words = [w for w in re.findall(r"[a-z]+", role.lower()) if w not in {"the", "a", "an"}]
    return "_".join(words[:3])


_GENERIC = frozenset({"the", "a", "an", "he", "she", "they", "someone", "voice", "man", "woman", "boy", "girl"})
#: One-word answers that name nobody and describe nobody: left to the baseline, as before.
_PRONOUNS = frozenset({"he", "she", "they", "it", "i", "you", "we", "him", "her", "them", "someone", "everyone", "anyone", "nobody"})


def describes_a_speaker(answer: str) -> str:
    """"role" or "phrase" when the model's answer is words describing the speaker rather than a name, else "".

    RI ch4 (v16 trace): "The elder", "the academy elder", "third Gu" came back without the UNKNOWN: prefix the prompt asks for;
    they matched no cast entry, the line stayed "unmapped" and kept its baseline guess (a wrong named person for two of seven
    elder lines). Sure only when the answer starts with an article or a lower-case word (a name is capitalised), so
    "Kim Dokja", "Mr. Fool" and a new "Daly" never qualify; a long phrase is no name or role at all ("phrase")."""
    words = answer.split()
    if not words or (len(words) == 1 and words[0].lower().strip(".") in _PRONOUNS):
        return ""
    if len(words) > 4:
        return "phrase"
    return "role" if words[0].lower() in {"the", "a", "an"} or words[0][:1].islower() else ""


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
