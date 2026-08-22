"""Narrator reveal patterns: "It was Fang Yuan of course."

Web novels use a small set of stock constructions to hand the *reader* an
identity that the characters on the page do not have -- "the immortal
zombie" walks around unnamed for a scene, and the narrator drops "This was
none other than Fang Yuan" at the end of it. The resolver links mentions
from surface forms already in the text; it does not read this rhetorical
move at all, so a reveal paragraph's *earlier* ambiguous references stay
whatever placeholder they were before the reveal, for every purpose
downstream -- including a panel drawing "the immortal zombie" as a
featureless placeholder in a scene the reader already knows is Fang Yuan.

**Additive only, by design.** This module never rewrites a `Mention`, never
touches candidate scoring, and defines no new schema: a reveal is logged as
a `ResolutionEvent` (`type=LINK`, `method=DECLARATION`) whose payload is a
plain dict, the same append-only log every other resolution decision goes
through. `cause_pos`/`payload["observer_id"]` scope it to `OBSERVER_READER`
explicitly -- **in-scene characters do not learn the identity this way**;
nothing here asserts they do, and a separate signal (a character saying "I
know who you are") would be needed for that and is out of scope here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from echotales.core.enums import OBSERVER_READER, EventType, ResolutionMethod, SpanType
from echotales.core.models import DiscoursePosition, ResolutionEvent
from echotales.core.store import Store

log = logging.getLogger(__name__)

#: Stock narrator constructions that hand the reader an identity the
#: characters on the page don't have. Each must capture the revealed name in
#: a group called `name`. Ordered by how much of the sentence they anchor on
#: (more specific first), though `_find_reveals_in_text` doesn't rely on
#: ordering -- every pattern is tried against every span.
REVEAL_PATTERNS = [
    re.compile(
        r"[Ii]t was (?P<name>[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3})"
        r"(?:'s|’s|,)?\s+(?:of course|indeed)"
    ),
    re.compile(
        r"[Tt]his was none other than (?P<name>[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3})"
    ),
    re.compile(
        r"[Nn]one other than (?P<name>[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3})"
    ),
    re.compile(
        r"[Ww]ho else could it be but (?P<name>[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3})"
    ),
    re.compile(
        r"[Aa]s it turned out,?\s+it was (?P<name>[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3})"
    ),
    re.compile(
        r"[Tt]he person was in fact (?P<name>[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3})"
    ),
]

#: Reveal payloads are logged with this key so a later reader of the event
#: log (or a re-run) can tell a reveal event apart from every other `LINK`
#: without a schema change.
REVEAL_EVENT_KIND = "narrator_reveal"


@dataclass(slots=True)
class Reveal:
    chapter: float
    block_index: int
    offset: int
    matched_text: str
    revealed_name: str
    target_id: str  # Self id the revealed name resolved to.


@dataclass(slots=True)
class RevealReport:
    novel_id: str
    candidates_found: int = 0
    resolved: int = 0
    unresolved_name: int = 0
    already_logged: int = 0

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.candidates_found} reveal-pattern matches, "
            f"{self.resolved} resolved to a known character "
            f"({self.unresolved_name} named someone not in the graph), "
            f"{self.already_logged} already logged"
        )


def _name_index(store: Store, novel_id: str) -> dict[str, str]:
    """casefolded surface -> self id, across every person entity.

    Deliberately read-only against mentions already in the store -- this is
    the same surface vocabulary the resolver itself produced, just indexed
    the other way round (name -> entity, not entity -> name), so a reveal's
    named text can be looked up without re-deriving anything the resolver
    already decided.
    """
    from echotales.pipeline.resolve.appearance_extract import _surface_forms

    index: dict[str, str] = {}
    for entity in store.all_selves(novel_id):
        if not entity.kind.is_person:
            continue
        for surface in _surface_forms(store, novel_id, entity.id):
            # Longer, more specific surfaces should not be shadowed by a
            # shorter one seen for a different entity; keep the first
            # (arbitrary but stable) owner rather than flip-flopping.
            index.setdefault(surface, entity.id)
    return index


def _resolve_name(revealed: str, index: dict[str, str]) -> str | None:
    """Match a revealed name against the index, tail-first.

    Same reasoning as `appearance_extract.find_reveal_blocks`: this corpus
    gives a full clan-prefixed name once and a bare surname or given name
    everywhere after, so an exact-string match alone misses most reveals.
    Tail-matching risks a false positive when two characters share a given
    name; that risk is accepted here the same way it already is there, since
    rejecting every ambiguous reveal outright would silently keep the
    placeholder for the majority of real cases.
    """
    folded = revealed.casefold()
    if folded in index:
        return index[folded]
    for surface, target_id in index.items():
        if len(surface) > 3 and (folded == surface or folded.endswith(" " + surface)):
            return target_id
    return None


def find_reveals(store: Store, novel_id: str) -> list[Reveal]:
    """Every reveal-pattern match in the novel's narration, resolved to a
    known character where possible.

    Narration only, same as `appearance_extract` -- a character's own
    dialogue guessing someone's identity is a claim, not the narrator
    handing the reader a fact.
    """
    index = _name_index(store, novel_id)
    out: list[Reveal] = []

    # A block can satisfy more than one pattern for the same reveal --
    # "This was none other than X" also matches the bare "none other than
    # X" pattern as a substring -- so this is deduplicated per (block,
    # target), not per regex match. One reveal, however many patterns
    # noticed it.
    seen: set[tuple[float, int, str]] = set()
    for row in store.conn.execute(
        "SELECT chapter, block_index, start, text FROM span"
        " WHERE novel_id = ? AND span_type IN (?, ?)",
        (novel_id, SpanType.NARRATION_DESCRIPTION.value, SpanType.NARRATION_ACTION.value),
    ):
        text = str(row["text"])
        chapter = float(row["chapter"])
        block_index = int(row["block_index"])
        for pattern in REVEAL_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group("name")
                target_id = _resolve_name(name, index)
                if target_id is None:
                    continue
                key = (chapter, block_index, target_id)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    Reveal(
                        chapter=chapter,
                        block_index=block_index,
                        offset=int(row["start"]) + match.start(),
                        matched_text=match.group(0),
                        revealed_name=name,
                        target_id=target_id,
                    )
                )
    return out


def detect_reveals(store: Store, novel_id: str) -> RevealReport:
    """Find reveal patterns and log each as a `ResolutionEvent` for
    `OBSERVER_READER`.

    Idempotent: a reveal already logged for the same `(chapter, block_index,
    target_id)` is not written again, so re-running this stage after more
    chapters are ingested only appends what is new.
    """
    report = RevealReport(novel_id=novel_id)
    index = _name_index(store, novel_id)

    logged = {
        (
            event.payload.get("chapter"),
            event.payload.get("block_index"),
            event.payload.get("target_id"),
        )
        for event in store.iter_events()
        if event.type is EventType.LINK
        and event.payload.get("kind") == REVEAL_EVENT_KIND
        and event.payload.get("novel_id") == novel_id
    }
    # A block can satisfy more than one pattern for the same reveal -- see
    # `find_reveals` -- so this run's own hits are deduplicated the same way
    # before being checked against `logged`, or a single reveal spanning two
    # pattern matches would count as both "resolved" and "already_logged".
    seen_this_run: set[tuple[float, int, str]] = set()

    for row in store.conn.execute(
        "SELECT chapter, block_index, start, text FROM span"
        " WHERE novel_id = ? AND span_type IN (?, ?)",
        (novel_id, SpanType.NARRATION_DESCRIPTION.value, SpanType.NARRATION_ACTION.value),
    ):
        text = str(row["text"])
        chapter = float(row["chapter"])
        block_index = int(row["block_index"])
        for pattern in REVEAL_PATTERNS:
            for match in pattern.finditer(text):
                report.candidates_found += 1
                name = match.group("name")
                target_id = _resolve_name(name, index)
                if target_id is None:
                    report.unresolved_name += 1
                    continue

                key = (chapter, block_index, target_id)
                if key in seen_this_run:
                    continue
                seen_this_run.add(key)
                if key in logged:
                    report.already_logged += 1
                    continue
                logged.add(key)

                offset = int(row["start"]) + match.start()
                store.append_event(
                    ResolutionEvent(
                        id=f"reveal:{novel_id}:{chapter:g}:{block_index}:{offset}:{target_id}",
                        seq=store.next_seq(),
                        type=EventType.LINK,
                        payload={
                            "kind": REVEAL_EVENT_KIND,
                            "novel_id": novel_id,
                            "chapter": chapter,
                            "block_index": block_index,
                            "offset": offset,
                            "target_id": target_id,
                            "matched_text": match.group(0),
                            "observer_id": OBSERVER_READER,
                        },
                        cause_pos=DiscoursePosition(chapter=chapter, offset=offset),
                        method=ResolutionMethod.DECLARATION,
                    )
                )
                report.resolved += 1

    store.conn.commit()
    return report


def reveal_target_for_block(
    store: Store, novel_id: str, chapter: float, block_index: int
) -> str | None:
    """The self id a reveal event names for this exact block, if any.

    Scoped to the block, not the chapter or the enclosing scene -- the same
    granularity `get_panel_cast` uses for presence, and for the same reason:
    a reveal that happened three blocks ago describes what the reader knows
    generally, not who is standing in *this* frame. Panel casting can use
    this to draw the revealed character's position-appropriate persona
    instead of whatever placeholder entity carried the ambiguous mentions,
    without this module ever touching `get_panel_cast` or `present_cast`
    itself.
    """
    for event in store.iter_events():
        if event.type is not EventType.LINK:
            continue
        payload = event.payload
        if (
            payload.get("kind") == REVEAL_EVENT_KIND
            and payload.get("novel_id") == novel_id
            and payload.get("chapter") == chapter
            and payload.get("block_index") == block_index
        ):
            return str(payload.get("target_id")) if payload.get("target_id") else None
    return None
