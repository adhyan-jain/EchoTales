"""Body changes: when one continuity of consciousness occupies a second body.

`architecture.md §4`'s whole reason for splitting `Self` from `Persona` is
that a consciousness can outlive a body -- and until this module existed the
pipeline never detected one, so `persona/build.py` minted exactly one persona
per self and said so as a known limitation. Every downstream consumer
hardcoded `f"{self_id}:body1"`, which is a correct answer only for characters
who never change.

**The two worked examples are both in chapter 1 of a real novel in this
corpus, and both were read out of the actual text rather than imagined:**

    RI ch1:   "With the use of the Spring Autumn Cicada I have been reborn,
               going back to the time of 500 years ago!"
    LOTM ch1: "memories began flooding him as they slowly appeared in his
               mind! Klein Moretti, a citizen of the Northern Continent..."

Fang Yuan is a 500-year-old demonic cultivator before that sentence and a
fifteen-year-old clan boy after it. Drawing him the same way on both sides of
it is wrong in a way no amount of prompt tuning fixes, because the error is in
the graph, not the prompt.

**Detection is lexical first, model-confirmed second.** The cue vocabulary
below was grepped out of the two novels rather than guessed -- §4.24's combat
verbs scored literally zero on real chapters because they were written from
imagination, and that lesson applies exactly here. A model call then *vetoes*
candidates: the lexicon is deliberately generous (it fires on any chapter that
mentions a rebirth, including the dozens that merely refer back to one) and
the model decides whether this passage is the moment a body changed. With
`--no-llm` the lexicon stands alone, and `BodyChange.source` records which.

**Echoes are not events.** A reborn character keeps mentioning the rebirth for
the rest of the book -- RI says "reborn" again in ch2 and ch3. Cues within
`_ECHO_CHAPTERS` of an accepted change are folded into it rather than minting
a third body. This is the single most important guard here: without it a
protagonist accumulates a new body every few chapters.

**Boundaries are sub-chapter.** The RI transition happens partway through
chapter 1, so a chapter-granular boundary would put the 500-year-old and the
teenager in the same epoch. Story positions are floats precisely so a position
can fall between two chapters (`interval.StoryPos`), so a change at block *i*
of *n* is placed at ``chapter + i/n``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from echotales.core.enums import ReferenceMode, SpanType, TargetKind
from echotales.core.interval import Certainty, FuzzyInterval
from echotales.core.models import Persona, SelfPersonaBinding
from echotales.core.store import Store
from pydantic import BaseModel

log = logging.getLogger(__name__)

#: Cue strength. A change needs one STRONG cue, or two SUPPORTING ones in the
#: same chapter -- "previous life" alone is something a character can simply
#: reminisce about, while "transmigrated" is an assertion that a body changed.
_STRONG = (
    (r"\breborn\b", "rebirth"),
    (r"\brebirths?\b", "rebirth"),
    (r"\breincarnat\w*", "rebirth"),
    (r"\btransmigrat\w*", "transmigration"),
    # LOTM ch1, verbatim shape: "memories began flooding him".
    (
        r"\bmemories\b[^.!?]{0,40}\b(?:flood\w*|surg\w*|pour\w*|rush\w*)\b",
        "transmigration",
    ),
    (r"\bpossess(?:ed|ing)\b[^.!?]{0,20}\bbody\b", "possession"),
    # The destination has to be a *body*. Without that clause this matched
    # LOTM ch126's "his mind, body, and soul suddenly entered a magical
    # state", which is a trance, not a transfer -- and the model agreed with
    # the regex, so the veto did not save it. A cue that is wrong in a
    # plausible-sounding way is worse than one that never fires.
    (
        r"\bsoul\b[^.!?]{0,30}\b(?:entered|crossed into|transferred|possessed)\b"
        r"[^.!?]{0,30}\b(?:body|corpse|flesh|vessel|shell)\b",
        "possession",
    ),
    (r"\bwoke up in (?:a|an|another|someone)\b[^.!?]{0,20}\bbody\b", "transmigration"),
)

_SUPPORTING = (
    (r"\b(?:previous|past|former) life\b", "rebirth"),
    (r"\bgoing back to the time of\b", "rebirth"),
    (r"\breturned to (?:the )?(?:time|day|year|age|body)\b", "rebirth"),
    (r"\b(?:new|another|unfamiliar|different|younger) body\b", "transmigration"),
    (r"\bin the body of\b", "transmigration"),
    (r"\bsecond life\b", "rebirth"),
)

_STRONG_RE = tuple((re.compile(p, re.I), kind) for p, kind in _STRONG)

#: The strong cues, exported. `render/director.py` scores a transformation as
#: a drawable moment from this same table -- one definition of "a body
#: changed here", so the graph and the camera cannot disagree about where it
#: happened.
BODY_CHANGE_CUES = _STRONG_RE
_SUPPORTING_RE = tuple((re.compile(p, re.I), kind) for p, kind in _SUPPORTING)

#: A cue this close to an accepted change is that change being referred to
#: again, not a new one. Five chapters is generous on purpose: the cost of
#: merging two genuinely distinct bodies a few chapters apart is a missing
#: epoch, while the cost of splitting on every echo is a character who has a
#: dozen bodies and no usable reference sheet.
_ECHO_CHAPTERS = 5.0

#: A body nobody is shown living in is not worth minting. The entity must be
#: attested in at least this many chapters after the change.
_MIN_CHAPTERS_AFTER = 2

#: Closed vocabulary. A model answer outside it becomes "other" rather than
#: being trusted -- same hallucination discipline as `world/schema.py`.
CHANGE_KINDS = ("rebirth", "transmigration", "possession", "body_swap", "other")

_MAX_PASSAGE_CHARS = 600

#: How many alternative cues in one chapter are worth putting to the model
#: before giving up on that chapter. See `find_change_candidates`.
_MAX_PER_CHAPTER = 3

_NARRATION = (
    SpanType.NARRATION_ACTION,
    SpanType.NARRATION_DESCRIPTION,
    SpanType.NARRATION_EXPOSITION,
)

#: A character's own first-person claim about their own body, which in both
#: worked examples is the *clearest* statement in the chapter -- Fang Yuan
#: says "I have been reborn", Zhou Mingrui thinks "Could I have
#: transmigrated?". Accepted only when the speaker is this entity and the
#: line is about themselves (`_speaks_of_self`).
_SELF_REPORT = (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE)

_FIRST_PERSON = re.compile(r"\b(?:I|I'?ve|I'?m|me|my|myself)\b")

#: How far from a resolved PRESENT mention a cue may sit. See `_near`.
_PRESENCE_WINDOW = 3

SYSTEM = (
    "You decide whether a passage from a translated web novel is the moment a "
    "character's physical body changes -- rebirth into a younger self, "
    "transmigration into another person's body, possession, or a body swap. "
    "Referring back to a change that already happened is NOT such a moment. "
    "Return only JSON."
)


@dataclass(frozen=True, slots=True)
class BodyChange:
    """One attested transition from one body to the next."""

    chapter: float
    block_index: int
    #: Story position of the boundary: ``chapter + block/blocks_in_chapter``.
    story_pos: float
    kind: str
    cue: str
    passage: str
    new_body_label: str = ""
    source: str = "lexicon"

    @property
    def evidence(self) -> str:
        return f"{self.kind} at ch{self.chapter:g} block {self.block_index}: {self.cue}"


@dataclass(frozen=True, slots=True)
class BodyEpoch:
    """One body, and the stretch of story it is the character's body for."""

    index: int
    persona_id: str
    body_label: str
    from_pos: float
    #: None while the body is still the current one.
    to_pos: float | None
    cause: str
    evidence: str
    #: Latest position at which the character was still observed in this body.
    #: Grows the CERTAIN zone of an open epoch -- without it every position
    #: after the change is only PLAUSIBLE, which is honest but needlessly weak
    #: when the text shows them in that body for another 190 chapters.
    last_evidence: float | None = None

    @property
    def interval(self) -> FuzzyInterval:
        if self.to_pos is None:
            return FuzzyInterval.open_ended(
                self.from_pos,
                last_evidence=self.last_evidence or self.from_pos,
            )
        # A *closed* interval, and that is the whole point: an epoch that ends
        # must stop containing later positions, or position-filtered retrieval
        # would still hand the old body to a later chapter.
        return FuzzyInterval.point_known(self.from_pos, self.to_pos)


@dataclass(slots=True)
class SplitReport:
    novel_id: str
    entities_scanned: int = 0
    candidates: int = 0
    confirmed: int = 0
    vetoed_by_model: int = 0
    echoes_folded: int = 0
    rejected_other_character: int = 0
    rejected_no_life_after: int = 0
    failures: int = 0
    by_entity: dict[str, list[str]] = field(default_factory=dict)

    def summary(self) -> str:
        split = ", ".join(
            f"{label} ({len(kinds)}+1 bodies)" for label, kinds in self.by_entity.items()
        ) or "none"
        return (
            f"{self.novel_id}: {self.confirmed} body change(s) across "
            f"{self.entities_scanned} entities\n"
            f"  candidates: {self.candidates}; echoes folded: {self.echoes_folded}; "
            f"about another character: {self.rejected_other_character}; "
            f"model-vetoed: {self.vetoed_by_model}; "
            f"no life after: {self.rejected_no_life_after}; failed: {self.failures}\n"
            f"  split: {split}"
        )


class BodyChangeVerdict(BaseModel):
    """The model's read on one candidate passage."""

    changed: bool = False
    kind: str = ""
    new_body_label: str = ""
    reason: str = ""


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------


def _cues(text: str) -> list[tuple[str, str, bool]]:
    """`(kind, matched text, is_strong)` for every cue in this passage."""
    found: list[tuple[str, str, bool]] = []
    for pattern, kind in _STRONG_RE:
        m = pattern.search(text)
        if m:
            found.append((kind, m.group(0), True))
    for pattern, kind in _SUPPORTING_RE:
        m = pattern.search(text)
        if m:
            found.append((kind, m.group(0), False))
    return found


def _blocks_present(store: Store, novel_id: str, target_id: str) -> dict[float, set[int]]:
    """Chapters -> blocks where this entity is physically present.

    `PRESENT` only, the same filter `appearance_extract` applies and for the
    same reason: a rebirth recounted in someone else's dialogue, or witnessed
    in a third party's flashback, is not this character's body changing here.
    """
    out: dict[float, set[int]] = {}
    for row in store.conn.execute(
        "SELECT DISTINCT chapter, block_index, reference_mode FROM mention "
        "WHERE novel_id=? AND target_id=? ORDER BY chapter, block_index",
        (novel_id, target_id),
    ):
        if ReferenceMode(row["reference_mode"]) is ReferenceMode.PRESENT:
            out.setdefault(float(row["chapter"]), set()).add(int(row["block_index"]))
    return out


def _near(blocks: set[int], index: int, window: int = _PRESENCE_WINDOW) -> bool:
    """Is the character present within `window` blocks of this one?

    **Both worked examples in the corpus need this**, which is why it is not
    a strict block match. RI ch1's "memories of his previous life on Earth
    emerged before his eyes" and LOTM ch1's "memories began flooding him"
    each sit in a block whose only reference to the character is the pronoun
    "his" -- and an unresolved pronoun is not a mention, so a same-block rule
    finds neither. That is §10 item 11d (mention resolution is the ceiling on
    everything above it) showing up here rather than a reason to widen the
    rule indefinitely: three blocks is a paragraph or two, close enough that
    the narration is still about whoever the scene was just about.
    """
    return any(abs(b - index) <= window for b in blocks)


def _speaker_keys(store: Store, novel_id: str, target_id: str) -> set[str]:
    """Every surface form of this entity, normalised for speaker matching.

    `Span.speaker_self_id` does not hold a `Self` id despite its name -- the
    attribution ladder writes a *surface form* there and resolution never
    revisits it (§4.21, found the same way in voice casting). Joining on
    `comparison_key` is the same fix `voice/runner.py::speaker_index` makes,
    applied to one entity rather than the whole cast.
    """
    from echotales.pipeline.ingest.normalize import comparison_key

    keys = set()
    for row in store.conn.execute(
        "SELECT DISTINCT text FROM mention WHERE novel_id=? AND target_id=?",
        (novel_id, target_id),
    ):
        if key := comparison_key(row["text"]):
            keys.add(key)
    entity = store.get_self(target_id)
    if entity is not None and (key := comparison_key(entity.canonical_label)):
        keys.add(key)
    return keys


def _is_speaker(span: object, keys: set[str]) -> bool:
    from echotales.pipeline.ingest.normalize import comparison_key

    raw = getattr(span, "speaker_self_id", None)
    if not raw:
        return False
    return comparison_key(str(raw)) in keys


def cast_labels(store: Store, novel_id: str) -> dict[str, str]:
    """`self_id -> canonical label` for every person in the novel.

    Computed once per novel by `detect_body_changes` and threaded down, since
    the alternative is one `all_selves` scan per entity.
    """
    return {
        e.id: e.canonical_label for e in store.all_selves(novel_id) if e.kind.is_person
    }


def _about_someone_else(
    text: str, target_id: str, cast: dict[str, str]
) -> str | None:
    """The other character this passage is about, if it is about one.

    **The corpus forced this guard, and it is free.** A rebirth is narrated
    once and stood next to by everyone in the scene, so a presence-based rule
    hands a new body to every bystander: RI chapter 109's "Fang Yuan's
    rebirth changed his current situation" produced a candidate for *Jia Fu*,
    who is merely mentioned nearby. If the passage names a different
    character and never names this one, it is that character's change being
    described, not this one's.

    Deliberately conservative in the other direction: a passage naming
    nobody ("In short, it is the ability to be reborn" -- RI ch1, the real
    transition) is *not* rejected here. Deciding those is what the model
    veto is for.
    """
    low = text.casefold()
    mine = cast.get(target_id, "")
    if mine and mine.casefold() in low:
        return None
    for other_id, label in cast.items():
        if other_id == target_id or len(label) < 4:
            continue
        if label.casefold() in low:
            return label
    return None


def _distinct_blocks(changes: list[BodyChange]) -> list[BodyChange]:
    """One cue per block: several regexes matching one sentence is one cue."""
    seen: set[int] = set()
    out: list[BodyChange] = []
    for change in changes:
        if change.block_index in seen:
            continue
        seen.add(change.block_index)
        out.append(change)
    return out


def _context_passage(spans: list, block_index: int, window: int = 1) -> str:
    """The cue block plus its immediate neighbours.

    A single span is too thin to judge. RI's real transition matched on
    "In short, it is the ability to be reborn" -- true of the *item*, and on
    its own not obviously a body change at all. The next block is
    "With the use of the Spring Autumn Cicada I have been reborn, going back
    to the time of 500 years ago!", which settles it. Giving the model the
    sentence that matched and nothing else was asking it to adjudicate a
    passage the regex had already stripped of its context.
    """
    parts = [
        s.text.strip()
        for s in spans
        if abs(s.block_index - block_index) <= window and s.text.strip()
    ]
    return " ".join(parts)[:_MAX_PASSAGE_CHARS]


def _speaks_of_self(text: str) -> bool:
    """Does this line claim the change for the *speaker*?

    A character saying "I have been reborn" is first-hand evidence about
    their own body; one saying "you were reborn" or "he was reincarnated" is
    evidence about someone else's, and treating the two alike would give a
    body to every bystander in the scene.
    """
    return bool(_FIRST_PERSON.search(text))


def find_change_candidates(
    store: Store,
    novel_id: str,
    target_id: str,
    *,
    report: SplitReport | None = None,
    cast: dict[str, str] | None = None,
) -> list[BodyChange]:
    """Lexical candidates, echo-folded, in discourse order.

    Generous by design -- the model veto in `detect_body_changes` is what
    makes the final answer precise. Returning nothing here is the common and
    correct case: most characters have one body.
    """
    present = _blocks_present(store, novel_id, target_id)
    if not present:
        return []
    chapters = sorted(present)
    last_chapter = chapters[-1]
    speaker_keys = _speaker_keys(store, novel_id, target_id)
    cast = cast_labels(store, novel_id) if cast is None else cast

    candidates: list[BodyChange] = []
    for chapter in chapters:
        spans = store.get_spans(novel_id, chapter)
        if not spans:
            continue
        n_blocks = max(s.block_index for s in spans) + 1
        blocks = present[chapter]

        strong: list[BodyChange] = []
        supporting: list[BodyChange] = []
        for span in spans:
            text = span.text.strip()
            if not text:
                continue
            if span.span_type in _SELF_REPORT:
                # First-hand: this character saying it about themselves.
                if not _is_speaker(span, speaker_keys) or not _speaks_of_self(text):
                    continue
            elif span.span_type in _NARRATION:
                if not _near(blocks, span.block_index):
                    continue
            else:
                continue
            other = _about_someone_else(text, target_id, cast)
            if other is not None:
                if report is not None:
                    report.rejected_other_character += 1
                continue
            for kind, cue, is_strong in _cues(text):
                change = BodyChange(
                    chapter=chapter,
                    block_index=span.block_index,
                    story_pos=chapter + span.block_index / max(n_blocks, 1),
                    kind=kind,
                    cue=cue,
                    passage=_context_passage(spans, span.block_index),
                )
                if is_strong:
                    strong.append(change)
                else:
                    supporting.append(change)

        # **Alternatives, not one shot.** LOTM chapter 1 contains both
        # "C-could I have transmigrated?" (a character speculating) and
        # "memories began flooding him" (the narrator stating it), and the
        # first is much the weaker evidence. Keeping only the earliest cue in
        # the chapter meant a model veto on the weak one threw away the
        # chapter, taking the strong one with it. `detect_body_changes` now
        # tries them in order and stops at the first the model confirms.
        alternatives = strong or (supporting if len(supporting) >= 2 else [])
        alternatives = _distinct_blocks(alternatives)[:_MAX_PER_CHAPTER]
        if not alternatives:
            continue
        chosen = alternatives[0]

        # A change with no story left after it explains nothing and mints a
        # body nobody is ever shown in.
        after = [c for c in chapters if c > chosen.chapter]
        if len(after) < _MIN_CHAPTERS_AFTER and last_chapter - chosen.chapter < 1:
            if report is not None:
                report.rejected_no_life_after += 1
            continue

        # **Echo folding, and the corpus made this rule much stricter than
        # the first draft.** Fang Yuan's rebirth is referred back to in
        # chapters 2, 19, 71, 105, 135, 145, 187 and 198 -- a distance window
        # alone gave him eight bodies. A character who has already been
        # reborn *once* talking about being reborn again is, overwhelmingly,
        # the same event being recalled, so a second cue of a kind already
        # accepted is folded no matter how far away it is. A cue of a
        # genuinely different kind (reborn, then later possessed) is still a
        # new candidate, subject to the distance window.
        seen_kinds = {c.kind for c in candidates}
        too_close = candidates and chosen.chapter - candidates[-1].chapter <= _ECHO_CHAPTERS
        if chosen.kind in seen_kinds or too_close:
            if report is not None:
                report.echoes_folded += 1
            continue
        candidates.extend(alternatives)

    return candidates


def _build_prompt(label: str, change: BodyChange) -> str:
    return "\n".join(
        [
            f"Character: {label}",
            f"Chapter {change.chapter:g}, passage:",
            f'  "{change.passage}"',
            "",
            "Does this passage narrate this character's body CHANGING -- being "
            "reborn into a younger body, transmigrating into someone else's, "
            "being possessed, or swapping bodies?",
            "Answer false if it merely refers back to a change that happened "
            "earlier, or describes someone else's change.",
            "",
            'Return only JSON: {"changed": true|false, '
            f'"kind": one of {list(CHANGE_KINDS)}, '
            '"new_body_label": "short name for the character in the NEW body, '
            'or empty", "reason": "one short sentence"}',
        ]
    )


def _clean_label(raw: str, fallback: str) -> str:
    """A body label the model may have invented, or a safe fallback."""
    label = " ".join(str(raw or "").split())[:60]
    if not label or not any(ch.isalpha() for ch in label):
        return fallback
    # A sentence is a reason, not a label.
    if len(label.split()) > 6 or label.rstrip().endswith("."):
        return fallback
    return label


def detect_body_changes(
    store: Store,
    novel_id: str,
    entity: object,
    *,
    client: object | None = None,
    report: SplitReport | None = None,
    cast: dict[str, str] | None = None,
) -> list[BodyChange]:
    """Confirmed body changes for one entity, earliest first.

    Without `client` the lexical candidates stand as-is (the `--no-llm` path,
    marked `source="lexicon"`, one per chapter); with one, the alternatives
    within a chapter are tried in order and the first the model confirms wins
    -- at most one body change per chapter either way, because a chapter that
    changes a character's body twice is not something this corpus contains.
    """
    target_id = str(entity.id)  # type: ignore[attr-defined]
    label = str(entity.canonical_label)  # type: ignore[attr-defined]
    candidates = find_change_candidates(
        store, novel_id, target_id, report=report, cast=cast
    )
    by_chapter: dict[float, list[BodyChange]] = {}
    for change in candidates:
        by_chapter.setdefault(change.chapter, []).append(change)

    if report is not None:
        report.candidates += len(by_chapter)
    if not candidates or client is None:
        return [group[0] for _ch, group in sorted(by_chapter.items())]


    confirmed: list[BodyChange] = []
    for _chapter, group in sorted(by_chapter.items()):
        for change in group:
            if _adjudicate(
                store,
                novel_id,
                target_id,
                label,
                change,
                client=client,
                report=report,
                confirmed=confirmed,
            ):
                break
    return confirmed


def _adjudicate(
    store: Store,
    novel_id: str,
    target_id: str,
    label: str,
    change: BodyChange,
    *,
    client: object,
    report: SplitReport | None,
    confirmed: list[BodyChange],
) -> bool:
    """Put one candidate to the model; append and return True if it holds."""
    from echotales.pipeline.llm.tasks import Task

    try:
        result = client.complete(  # type: ignore[attr-defined]
            Task.PERSONA_SPLIT,
            _build_prompt(label, change),
            BodyChangeVerdict,
            system=SYSTEM,
            novel_id=novel_id,
        )
    except Exception as exc:
        log.warning("body-change check failed for %s: %s", target_id, exc)
        if report is not None:
            report.failures += 1
        # Keep the lexical candidate rather than silently dropping a real
        # split because a model call timed out.
        confirmed.append(change)
        return True

    verdict = result.value
    if not verdict.changed:
        if report is not None:
            report.vetoed_by_model += 1
        return False
    kind = verdict.kind if verdict.kind in CHANGE_KINDS else change.kind
    confirmed.append(
        BodyChange(
            chapter=change.chapter,
            block_index=change.block_index,
            story_pos=change.story_pos,
            kind=kind,
            cue=change.cue,
            passage=change.passage,
            new_body_label=_clean_label(verdict.new_body_label, ""),
            source="llm",
        )
    )
    return True


# ---------------------------------------------------------------------------
# epochs
# ---------------------------------------------------------------------------


def epochs_for(
    self_id: str,
    label: str,
    first_pos: float,
    changes: list[BodyChange],
    *,
    last_pos: float | None = None,
) -> list[BodyEpoch]:
    """Contiguous body epochs covering this character's whole appearance.

    Always returns at least one epoch, so a character with no detected change
    is described by exactly the same structure as one with three -- callers
    never need a special case for "unsplit".
    """
    epochs: list[BodyEpoch] = []
    start = first_pos
    cause = "first attested"
    evidence = ""
    for index, change in enumerate(
        [c for c in changes if c.story_pos > first_pos], start=1
    ):
        epochs.append(
            BodyEpoch(
                index=index,
                persona_id=f"{self_id}:body{index}",
                body_label=label if index == 1 else f"{label} (body {index})",
                from_pos=start,
                to_pos=change.story_pos,
                cause=cause,
                evidence=evidence,
            )
        )
        start = change.story_pos
        cause = change.kind
        evidence = change.evidence
        label = change.new_body_label or label

    index = len(epochs) + 1
    epochs.append(
        BodyEpoch(
            index=index,
            persona_id=f"{self_id}:body{index}",
            body_label=label if index == 1 else f"{label} (body {index})",
            from_pos=start,
            to_pos=None,
            cause=cause,
            evidence=evidence,
            last_evidence=last_pos,
        )
    )
    return epochs


def write_epochs(
    store: Store,
    novel_id: str,
    entity: object,
    epochs: list[BodyEpoch],
    *,
    observer_id: str,
    notes: str = "",
) -> None:
    """Persist a persona and binding per epoch."""
    from echotales.core.models import DiscoursePosition

    for epoch in epochs:
        pos = DiscoursePosition(chapter=float(int(epoch.from_pos)), offset=0)
        store.add_persona(
            Persona(
                id=epoch.persona_id,
                novel_id=novel_id,
                body_label=epoch.body_label,
                first_attested_pos=pos,
                notes="; ".join(p for p in (notes, epoch.cause, epoch.evidence) if p),
            )
        )
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id=str(entity.id),  # type: ignore[attr-defined]
                persona_id=epoch.persona_id,
                interval=epoch.interval,
                learned_at_pos=pos,
                observer_id=observer_id,
            )
        )


# ---------------------------------------------------------------------------
# lookup -- the render-time half
# ---------------------------------------------------------------------------


def persona_at(
    store: Store,
    self_id: str,
    position: float | None = None,
) -> str:
    """Which body this consciousness is in at `position`.

    This is the accessor every consumer of persona attributes should use
    instead of `f"{self_id}:body1"`. It is deliberately total: a store with no
    bindings at all (every database built before this module existed) still
    gets `:body1` back, so nothing breaks on an old graph -- it simply does
    not benefit.

    `position=None` means "the latest body", which is the right default for a
    question that is not about a moment (a cast list, a CLI dump).
    """
    bindings = [
        b
        for b in store.get_self_persona_bindings(self_id=self_id)
        if store.get_persona(b.persona_id) is not None
    ]
    if not bindings:
        return f"{self_id}:body1"
    bindings.sort(key=lambda b: b.interval.from_lb)
    if position is None:
        return bindings[-1].persona_id

    certain = [
        b for b in bindings if b.interval.contains(position) is Certainty.CERTAIN
    ]
    if certain:
        return certain[-1].persona_id
    plausible = [b for b in bindings if b.interval.contains(position).is_possible]
    if plausible:
        return plausible[-1].persona_id
    # Before the character's first appearance: their first body is the only
    # honest answer, and returning nothing would make a caller invent one.
    return bindings[0].persona_id


def bodies_of(store: Store, self_id: str) -> list[tuple[str, FuzzyInterval]]:
    """Every body this self has had, earliest first."""
    bindings = sorted(
        store.get_self_persona_bindings(self_id=self_id),
        key=lambda b: b.interval.from_lb,
    )
    return [(b.persona_id, b.interval) for b in bindings]


def is_split(store: Store, self_id: str) -> bool:
    """True when this character occupies more than one body over the story."""
    return len(store.get_self_persona_bindings(self_id=self_id)) > 1


def split_selves(store: Store, novel_id: str) -> dict[str, list[str]]:
    """`self_id -> [persona_id, ...]` for every character with a body change.

    The ablation figure (§10 item 11b) needs exactly this list: the characters
    a flat pipeline gets wrong.
    """
    out: dict[str, list[str]] = {}
    for entity in store.all_selves(novel_id):
        if entity.kind is not TargetKind.SELF:
            continue
        personas = [p for p, _i in bodies_of(store, entity.id)]
        if len(personas) > 1:
            out[entity.id] = personas
    return out
