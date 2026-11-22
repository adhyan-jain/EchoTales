"""Fill in the gender of characters whose pronoun count could not call it, and let a reviewer set it.

Why this stage exists (casting audit 2026-11-19): voice casting offers every adult voice of both genders when a
character's gender is `unknown`. On a copy of the RI database 65 of 98 persons were unknown, 20 of 44 speaking
characters among them (Fang Yuan, 902 lines, was cast a female voice); on LotM Dunn Smith got one too. Two causes:

1. `extract_traits` let the model's "unknown" overwrite a pronoun-derived gender (fixed there).
2. Where the pronoun rule really has too little (`traits.gender_from_pronouns` needs six pronouns and a 70% share
   from the paragraphs around the mentions) nothing looked at the text again.

This pass reads only sentences that *name* the character, never the neighbourhood: a pronoun-near-the-name rule was
measured as unreliable (Ruo Nan, Melissa, Daly and Xiong Jiang read as 80-97% male because the narration around them
is about someone else). Precision over recall (non-negotiable 9): a model answer counts only when it is confident and
its evidence quote is verbatim in what it was shown and actually says the claimed gender; everything else stays
`unknown`, which casting reports rather than guesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echotales.core.enums import OBSERVER_READER, AssertedBy, SpanType, TargetKind, TruthStatus
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition, Span
from echotales.core.store import Store
from echotales.pipeline.persona.first_names import name_gender_prior
from echotales.pipeline.persona.split import bodies_of, standing_values
from echotales.pipeline.persona.traits import anchored_window
from pydantic import BaseModel, Field

#: A reviewer's decision is stored with this evidence prefix so no later automatic pass overwrites it.
HUMAN_PREFIX = "human:"

#: Titles that state a gender when written directly before a name. Deliberately small and case-sensitive: translated
#: xianxia uses "Master"/"Elder"/"Senior" for both genders, so those are not here, and a lower-case "miss" is a verb.
#: "Lord" and "Sir" are left out on a measurement: on RI "Lord Yao Ji" is an old woman ("saw Lord Yao Ji casting her
#: bid") with 14 title-cued mentions, and Lord Qing Shu a man; translated xianxia uses the word for both.
_TITLE_GENDER = {
    "Mr": "male", "Mister": "male",
    "Mrs": "female", "Ms": "female", "Miss": "female", "Madam": "female", "Madame": "female", "Lady": "female",
    "Dame": "female",
}
_TITLES = "|".join(sorted(_TITLE_GENDER, key=len, reverse=True))
_TITLE_BEFORE = re.compile(rf"(?<![A-Za-z])({_TITLES})\.?\s+$")
_TITLE_IN_MENTION = re.compile(rf"^({_TITLES})\.?\s+[A-Z]")
#: One title mention proves little (a nickname, a quoted insult); two that agree and none that disagree is a cue.
_MIN_TITLE_MENTIONS = 2

_MALE_WORDS = frozenset(
    "he him his himself man men gentleman boy father son brother husband king prince uncle nephew mr mister sir lord"
    .split()
)
_FEMALE_WORDS = frozenset(
    "she her hers herself woman women lady girl mother daughter sister wife queen princess aunt niece miss mrs ms"
    " madam madame dame".split()
)
_WORD = re.compile(r"[A-Za-z]+")

#: Pronouns that can only refer back to the name they follow when nothing intervenes: subject, possessive, reflexive.
#: "him" and "hers" are left out on purpose: an object pronoun after a name ("Elizabeth remained with no cordial
#: feelings towards him") names the *other* person, which is what put a male vote on a woman in the P&P e2e run.
_OWN_MALE = frozenset({"he", "his", "himself"})
_OWN_FEMALE = frozenset({"she", "her", "herself"})
#: Narration of every kind counts, exposition included: "Mary had heard herself mentioned ... the most accomplished
#: girl" is exposition, and leaving that span type out left Jane, Mary and Lydia with no passage at all (P&P ch3).
_NARRATIVE = (
    SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION, SpanType.NARRATION_EXPOSITION, SpanType.INNER_MONOLOGUE,
)
#: Votes a character needs before the pronoun rule may decide alone (no title, no model), and the share they must agree.
_MIN_VOTES_ALONE = 3
_VOTE_SHARE = 0.85

_SENTENCE = re.compile(r"[^.!?…]+(?:[.!?…]+[\"'”’]*|$)\s*")
_MAX_WINDOW_CHARS = 400
MAX_WINDOWS = 8
MIN_QUOTE_CHARS = 6

SYSTEM = (
    "You decide the gender of one named character in a novel from short passages. In narration a character is "
    "followed by he/his/him or she/her, or called a man, woman, father, sister and so on. Use only words that refer to "
    "THAT character; if the passages are about other people or never show it, answer unknown."
)


class GenderResponse(BaseModel):
    #: `quote` comes first on purpose: ollama decodes the fields in order, and asked for the gender first gemma2:9b
    #: answered "unknown" with an empty quote for Fang Yuan and Gu Yue Bo, whose passages say "his hair", "his eyes".
    #: Having to find the words first makes the verdict follow from them.
    quote: str = Field(default="", description="the exact words from a passage where a pronoun or word shows it, verbatim")
    gender: str = Field(default="unknown", description="male | female | unknown")
    confident: bool = Field(default=False, description="true only if the quote plainly refers to this character")


@dataclass(slots=True)
class GenderReport:
    novel_id: str
    examined: int = 0
    skipped_known: int = 0
    skipped_human: int = 0
    no_persona: int = 0
    by_cue: int = 0
    by_model: int = 0
    by_pronoun: int = 0
    by_pronoun_and_model: int = 0
    no_evidence: int = 0
    rejected_hedged: int = 0
    rejected_quote: int = 0
    model_unknown: int = 0
    errors: int = 0
    #: label -> (gender, method, evidence) for each character this pass decided, so a reviewer can read them.
    decided: dict[str, tuple[str, str, str]] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"gender pass {self.novel_id}: {self.examined} unknown characters examined, {self.by_cue} by title cue,"
            f" {self.by_pronoun} by own pronouns, {self.by_model} by model reading ({self.by_pronoun_and_model} of them"
            f" confirmed by pronouns rather than the quote); left unknown: {self.no_evidence} without gendered text,"
            f" {self.model_unknown} model unknown, {self.rejected_hedged} hedged, {self.rejected_quote} bad quote,"
            f" {self.errors} errors; {self.skipped_known} already known, {self.skipped_human} set by a reviewer, {self.no_persona} without a persona"
        )


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().casefold()


def _side_counts(text: str) -> tuple[int, int]:
    words = [w.casefold() for w in _WORD.findall(text)]
    return sum(w in _MALE_WORDS for w in words), sum(w in _FEMALE_WORDS for w in words)


def own_pronoun_vote(text_after_mention: str) -> str | None:
    """`male`/`female` from the first own-pronoun after a mention, inside the clause the mention opens, else None.

    The window is `traits.anchored_window` (v2): it ends at the sentence end, at the next capitalised word (another
    name) and at a clause boundary, so the pronoun it holds is about the mention's referent and not about whoever
    the sentence turns to next. That rule was preregistered and measured for the trait stage; this reuses it rather
    than a looser near-the-name count, which read Ruo Nan and Melissa as men (docstring above).
    """
    for word in _WORD.findall(anchored_window(text_after_mention, "v2")):
        w = word.casefold()
        if w in _OWN_MALE:
            return "male"
        if w in _OWN_FEMALE:
            return "female"
    return None


def lean_from_votes(votes: list[str]) -> str | None:
    """The side every vote agrees on, when there is at least one and none disagrees (used to steer casting)."""
    sides = set(votes)
    return next(iter(sides)) if len(sides) == 1 else None


def _title_gender(span: Span, offset: int, mention_text: str) -> str | None:
    rel = offset - span.start
    inside = _TITLE_IN_MENTION.match(mention_text)
    if inside:
        return _TITLE_GENDER[inside.group(1)]
    before = _TITLE_BEFORE.search(span.text[max(0, rel - 12) : max(rel, 0)])
    return _TITLE_GENDER[before.group(1)] if before else None


def _window(span: Span, offset: int) -> str:
    """The sentence naming the character plus the one after it, where a continuing pronoun usually sits."""
    rel = offset - span.start
    sentences = list(_SENTENCE.finditer(span.text))
    for i, m in enumerate(sentences):
        if m.start() <= rel < m.end():
            return " ".join(s.group().strip() for s in sentences[i : i + 2])[:_MAX_WINDOW_CHARS]
    return span.text[max(0, rel - 80) : rel + 200]


def _current_gender(store: Store, self_id: str) -> tuple[str, bool]:
    """(standing gender over the character's bodies, whether a reviewer set it)."""
    value, human = "unknown", False
    for persona_id, _interval in bodies_of(store, self_id) or [(f"{self_id}:body1", None)]:
        value = standing_values(store, persona_id).get("gender", value)
        human = human or any(
            a.key == "gender" and a.evidence.startswith(HUMAN_PREFIX)
            for a in store.get_attributes(TargetKind.PERSONA, persona_id)
        )
    return value, human


def write_gender(
    store: Store, novel_id: str, self_id: str, gender: str, evidence: str, *, confidence: float, at: DiscoursePosition,
) -> int:
    """Record `gender` on every body of `self_id` as a new row that supersedes the older gender rows.

    Gender belongs to the consciousness, like the other traits (`build_personas`), so every body gets it. The row copies
    the interval of the row it supersedes and is learned later than it, because `standing_values` picks by story start
    first and learned time second; an older `unknown` row is superseded, not retracted: it never claimed anything
    false (non-negotiable 5).
    """
    written = 0
    entity = next((e for e in store.all_selves(novel_id) if e.id == self_id), None)
    targets = bodies_of(store, self_id) or [(f"{self_id}:body1", None)]
    for persona_id, _interval in targets:
        rows = [a for a in store.get_attributes(TargetKind.PERSONA, persona_id) if a.key == "gender" and a.is_standing]
        best = max(rows, key=lambda a: (a.interval.from_lb, a.learned_at_pos.chapter, a.learned_at_pos.offset), default=None)
        if best is not None:
            interval = best.interval
            learned = at if at > best.learned_at_pos else DiscoursePosition(
                chapter=best.learned_at_pos.chapter, offset=best.learned_at_pos.offset + 1
            )
        else:
            start = int(entity.first_attested_pos.chapter) if entity is not None else at.chapter
            interval = FuzzyInterval.open_ended(start, last_evidence=start)
            learned = at
        store.add_attribute(
            novel_id,
            Attribute(
                target_kind=TargetKind.PERSONA, target_id=persona_id, key="gender", value=gender, interval=interval,
                learned_at_pos=learned, observer_id=OBSERVER_READER, asserted_by=AssertedBy.INFERENCE,
                truth_status=TruthStatus.TRUE, evidence=evidence[:300], confidence=confidence,
            ),
        )
        written += 1
    return written


@dataclass(slots=True)
class _Window:
    chapter: float
    offset: int
    text: str


def _gather(store: Store, novel_id: str, wanted: set[str]):
    """One pass over the book: title cues, name-anchored windows and spoken-line counts for the wanted characters."""
    cues: dict[str, list[str]] = {t: [] for t in wanted}
    votes: dict[str, list[str]] = {t: [] for t in wanted}
    windows: dict[str, list[_Window]] = {t: [] for t in wanted}
    mentions_n: dict[str, int] = {t: 0 for t in wanted}
    labels = {e.id: e.canonical_label for e in store.all_selves(novel_id) if e.id in wanted}
    lines: dict[str, int] = {t: 0 for t in wanted}
    by_label = {label: t for t, label in labels.items()}
    narrative = _NARRATIVE
    for chapter in store.chapter_numbers(novel_id):
        spans = store.get_spans(novel_id, chapter)
        for s in spans:
            who = s.speaker_self_id
            if who in wanted:
                lines[who] += 1
            elif who in by_label:
                lines[by_label[who]] += 1
        mentions = [m for m in store.get_mentions(novel_id, chapter) if m.target_id in wanted]
        if not mentions:
            continue
        by_block: dict[int, list[Span]] = {}
        for s in spans:
            by_block.setdefault(s.block_index, []).append(s)
        seen: set[tuple[str, str]] = set()
        for m in mentions:
            mentions_n[m.target_id] += 1
            span = next((s for s in by_block.get(m.block_index, []) if s.start <= m.offset < s.end), None)
            if span is None:
                continue
            cue = _title_gender(span, m.offset, m.text)
            if cue:
                cues[m.target_id].append(cue)
            if span.span_type in narrative:
                vote = own_pronoun_vote(span.text[m.offset - span.start + len(m.text) :])
                if vote:
                    votes[m.target_id].append(vote)
                text = _window(span, m.offset)
                if (m.target_id, text) not in seen:
                    seen.add((m.target_id, text))
                    windows[m.target_id].append(_Window(chapter, m.offset, text))
    return cues, windows, mentions_n, lines, votes


def _pick(windows: list[_Window], k: int) -> list[_Window]:
    """Up to `k` windows that carry a gendered word, spread over the book rather than taken from its start."""
    gendered = [w for w in windows if sum(_side_counts(w.text)) > 0]
    if len(gendered) <= k:
        return gendered
    step = len(gendered) / k
    return [gendered[int(i * step)] for i in range(k)]


def _prompt(label: str, picked: list[_Window]) -> str:
    body = "\n".join(f"{i}. {w.text}" for i, w in enumerate(picked, 1))
    return (
        f"Character: {label}\n\nPassages that name this character:\n{body}\n\n"
        "Find the clearest passage where a pronoun or word refers to this character, and copy those exact words as the "
        "quote. Then say whether the character is male or female. If no passage shows it, leave the quote empty and "
        "answer unknown."
    )


def infer_missing_genders(
    novel_id: str, store: Store, client: object | None, *, min_mentions: int = 3, max_windows: int = MAX_WINDOWS,
) -> GenderReport:
    """Decide gender for person characters that have none, cue first, then a name-anchored model reading."""
    from echotales.pipeline.llm.tasks import Task

    report = GenderReport(novel_id=novel_id)
    todo = []
    merged = store.merged_into(novel_id)
    for entity in store.all_selves(novel_id):
        if not entity.kind.is_person or entity.id in merged:
            continue
        # A gender row needs a body to sit on; without one the personas stage has not run, and a row on a body that
        # does not exist would be read back by nothing (ORV's database had no personas at all).
        if not bodies_of(store, entity.id):
            report.no_persona += 1
            continue
        gender, human = _current_gender(store, entity.id)
        if human:
            report.skipped_human += 1
        elif gender in ("male", "female"):
            report.skipped_known += 1
        else:
            todo.append(entity)
    if not todo:
        return report

    cues, windows, mentions_n, lines, votes = _gather(store, novel_id, {e.id for e in todo})
    for entity in todo:
        if mentions_n[entity.id] < min_mentions and not lines[entity.id]:
            continue
        report.examined += 1
        found = set(cues[entity.id])
        own = lean_from_votes(votes[entity.id])
        at = windows[entity.id][0] if windows[entity.id] else None
        pos = DiscoursePosition(chapter=int(at.chapter), offset=at.offset) if at else entity.first_attested_pos
        # One title mention proves little (a nickname, a quoted insult); a single one that an own-pronoun in the
        # character's narration agrees with is two independent cues (Jane: "the eldest Miss Bennet" + "her mother").
        if len(found) == 1 and (
            len(cues[entity.id]) >= _MIN_TITLE_MENTIONS or own == next(iter(found))
        ):
            gender = next(iter(found))
            evidence = f"title before the name in {len(cues[entity.id])} mentions"
            write_gender(store, novel_id, entity.id, gender, evidence, confidence=0.9, at=pos)
            report.by_cue += 1
            report.decided[entity.canonical_label] = (gender, "cue", evidence)
            continue
        tally = votes[entity.id]
        for side in ("male", "female"):
            if len(tally) >= _MIN_VOTES_ALONE and tally.count(side) / len(tally) >= _VOTE_SHARE:
                evidence = f"{tally.count(side)} of {len(tally)} own pronouns after the name are {side}"
                write_gender(store, novel_id, entity.id, side, evidence, confidence=0.8, at=pos)
                report.by_pronoun += 1
                report.decided[entity.canonical_label] = (side, "pronoun", evidence)
                break
        else:
            side = ""
        if side:
            continue
        if client is None:
            report.no_evidence += 1
            continue
        picked = _pick(windows[entity.id], max_windows)
        if not picked:
            report.no_evidence += 1
            continue
        shown = _norm(" ".join(w.text for w in picked))
        try:
            result = client.complete(  # type: ignore[attr-defined]
                Task.READER, _prompt(entity.canonical_label, picked), GenderResponse, system=SYSTEM, novel_id=novel_id
            ).value
        except Exception:
            report.errors += 1
            continue
        if result.gender not in ("male", "female"):
            report.model_unknown += 1
            continue
        quote = _norm(result.quote)
        if not result.confident:
            report.rejected_hedged += 1
            continue
        male, female = _side_counts(result.quote)
        claimed, other = (male, female) if result.gender == "male" else (female, male)
        quote_ok = not (len(quote) < MIN_QUOTE_CHARS or quote not in shown or claimed == 0 or other > 0)
        # A small model often answers right and copies the wrong words (gemma2:9b quoted "towards him" for
        # Elizabeth and was rejected). The character's own pronouns in the text are an independent read: when every
        # one of them agrees with the model, the verdict stands without the quote.
        if not quote_ok and own != result.gender:
            report.rejected_quote += 1
            continue
        if not quote_ok:
            report.by_pronoun_and_model += 1
        home = next(w for w in picked if quote in _norm(w.text)) if any(quote in _norm(w.text) for w in picked) else picked[0]
        evidence = (
            f"model reading: {result.quote.strip()}" if quote_ok
            else f"model reading, confirmed by {len(votes[entity.id])} own pronouns after the name"
        )
        write_gender(
            store, novel_id, entity.id, result.gender, evidence, confidence=0.8,
            at=DiscoursePosition(chapter=int(home.chapter), offset=home.offset),
        )
        report.by_model += 1
        report.decided[entity.canonical_label] = (result.gender, "model", evidence)
    store.conn.commit()
    return report


def gender_lean(store: Store, novel_id: str, target_ids: set[str]) -> dict[str, str]:
    """Characters in `target_ids` whose own pronouns all point one way, though no gender is recorded.

    Voice casting uses it to stay on the right side of a character the graph left `unknown`: P&P e2e 2026-11-22 cast
    Lydia a recorded-male voice, gender-blind, while the narration says "she". It is a steer, not a fact: nothing
    is written to the graph, and a single disagreeing pronoun cancels it (precision over recall). A character with
    no pronoun evidence at all falls back to its first name (`gender_lean_basis`).
    """
    return {t: side for t, (side, _) in gender_lean_basis(store, novel_id, target_ids).items()}


def gender_lean_basis(store: Store, novel_id: str, target_ids: set[str]) -> dict[str, tuple[str, str]]:
    """`gender_lean` with the reason: `(side, "pronoun")` or `(side, "name prior")`.

    The name prior (`first_names.py`, US public birth records) is used only for a character in `target_ids` (no
    recorded gender) with no own-pronoun vote at all: P&P ch1-3 Kitty, Lydia and Maria Lucas have no pronoun after
    their names, and Lydia was cast a male voice. Any pronoun vote, even a conflicting pair, keeps the prior out:
    mixed evidence means the text is the better witness than a name.
    """
    if not target_ids:
        return {}
    votes = _gather(store, novel_id, set(target_ids))[4]
    out = {t: (side, "pronoun") for t, v in votes.items() if (side := lean_from_votes(v))}
    labels = {e.id: e.canonical_label for e in store.all_selves(novel_id) if e.id in target_ids}
    for t, label in labels.items():
        if t not in out and not votes.get(t) and (side := name_gender_prior(label)):
            out[t] = (side, "name prior")
    return out
