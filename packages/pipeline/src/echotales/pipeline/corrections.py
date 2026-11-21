"""Human corrections made from the webview: log, then apply.

Two separate things happen to a correction, and neither is "feed it back into
the resolver as input" -- HANDOFF Section 6 rules that out explicitly, since a
resolver fed its own answer key stops being measurable. Instead:

1. **Logged** as a `GoldMention`-adjacent record with `Provenance.HUMAN` and
   `confirmed=True` -- real evidence for calibrating `ConformalGate` (Section 4.1)
   later, which is the principled path to the pipeline actually improving.
2. **Applied** to the live SQLite store on request: mentions get rebound,
   the entity list changes, an event is appended to the existing append-only
   log. This does not change how the resolver decides anything -- it patches
   *this run's* output, the same way a human copy-editor patches a draft.

Nine correction types:

- `merge_entities` -- two entities are the same person; fold one into the other.
- `reassign_mention` -- one specific occurrence of a name was linked to the
  wrong entity (or left unresolved). Addressed by `Mention.id`, not by
  surface text, so correcting "this one 'Mo Bei'" never touches any other
  occurrence that happens to share the spelling.
- `reassign_speaker` -- a dialogue or inner-monologue span has the wrong
  speaker, or none. Addressed by `Span.id`.
- `merge_lines` -- two adjacent spans in one block are really one sentence
  the classifier split (a quote plus its narration tag is the common case,
  but any adjacent pair works). The absorbed span is deleted outright, not
  hidden -- see `Store.delete_span`.
- `flag` -- not a fix, a note: "look at this again." Never applied to the
  store (`apply_pending` treats it as a no-op there) -- it exists purely so a
  suspicious line survives past the moment you noticed it, whether you or an
  automated review pass wrote it. `source` on the payload distinguishes a
  human flag from `agent:<model>` so an unattended nightly sweep's guesses are
  never visually confused with your own.
- `reassign_span_type` -- the classifier's `SpanType` was wrong: prose read as
  narration that's actually a translator's note (retype `NON_DIEGETIC`, which
  drops it from both audio and panels), or the reverse. Addressed by `Span.id`.
- `create_mention` -- a reference to a character exists in the text but was
  never detected as a mention at all ("old bastard Fang" referring to Fang
  Yuan): the reviewer selects the text themselves, so there is no existing
  `Mention.id` to correct, unlike `reassign_mention`. Addressed by span id
  plus a span-local character range; the alias type is inferred the same way
  the pipeline infers it for a detected surface (`classify_alias_type`),
  since a human picking the text supplies the surface, not its category.

- `set_gender` -- a character's gender is wrong or unknown (`male`, `female` or `unknown`). Addressed by `self_id`.
  Stored as a new gender row marked as a reviewer's, which the automatic gender pass never overwrites; voice casting
  reads it on the next run.

- `set_delivery` -- how one line is performed: an emotion (EARS's names, as the reader's delivery pass writes them) and
  an intensity 1-3. Addressed by `span_id`. Stored in its own table that the delivery pass never rewrites, and read
  back through `Store.span_emotions` -- the call `voice/runner.py` already makes -- so the next voice run uses it with
  no change to the runner. An explicit delivery marker in the line ("said expressionlessly") still outranks it at
  synthesis time (non-negotiable 10).

`reassign_mention` and `reassign_speaker` can target an existing entity *or*
mint a new one (`new_label` set instead of `target_id`/`speaker_id`) -- the
character isn't in the list yet, so create it. The new entity's id is decided
once, when the correction is logged (`new_manual_entity_id`), so the live
preview and the eventual store write always agree on what "the new character"
refers to.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from echotales.core.enums import (
    AttributionMethod,
    EventType,
    Provenance,
    ReferenceMode,
    ResolutionMethod,
    SpanType,
    TargetKind,
)
from echotales.core.models import DiscoursePosition, Mention, ResolutionEvent, Self
from echotales.core.store import Store

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows: threads stay safe, other processes do not
    fcntl = None  # type: ignore[assignment]

# One re-entrant lock per log file in this process. flock alone would also
# serialise threads (separate open files), but re-entrancy is what lets
# `apply_pending` hold the lock across its own `mark_applied` calls.
_PATH_LOCKS: dict[str, threading.RLock] = {}
_HELD_DEPTH: dict[str, int] = {}  # guarded by the path's RLock
_PATH_LOCKS_GUARD = threading.Lock()


class AppliedCorrectionError(Exception):
    """Removing a correction whose edit already landed in the store.

    The store edit survives a removal, so deleting the record would leave a
    human change with no human-provenance record behind it.
    """


class CorrectionType(StrEnum):
    MERGE_ENTITIES = "merge_entities"
    REASSIGN_MENTION = "reassign_mention"
    REASSIGN_SPEAKER = "reassign_speaker"
    MERGE_LINES = "merge_lines"
    FLAG = "flag"
    REASSIGN_SPAN_TYPE = "reassign_span_type"
    CREATE_MENTION = "create_mention"
    SET_GENDER = "set_gender"
    SET_DELIVERY = "set_delivery"


def new_manual_entity_id(novel_id: str, correction_id: str) -> str:
    """Id for an entity created from the webview, not by the resolver.

    Distinct from `GlobalResolver`'s own `f"{novel_id}:self{n}"` scheme so a
    manually-created entity can never collide with one the resolver already
    minted or will mint on a future run over the same novel.
    """
    return f"{novel_id}:manual:{correction_id}"


@dataclass(slots=True)
class Correction:
    novel_id: str
    type: CorrectionType
    payload: dict[str, object]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    applied: bool = False
    #: Why the last apply failed; it stays pending, and the Studio can say why (EVOLUTION 4.183).
    error: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "novel_id": self.novel_id,
            "type": self.type.value,
            "payload": self.payload,
            "created_at": self.created_at,
            "applied": self.applied,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, row: dict[str, object]) -> Correction:
        return cls(
            id=str(row["id"]),
            novel_id=str(row["novel_id"]),
            type=CorrectionType(str(row["type"])),
            payload=dict(row["payload"]),  # type: ignore[arg-type]
            created_at=float(row["created_at"]),  # type: ignore[arg-type]
            applied=bool(row.get("applied", False)),
            error=str(row.get("error", "") or ""),
        )


class CorrectionLog:
    """JSONL, one file per novel, always re-read under a lock before a write.

    Several instances exist for one file at once (the server's long-lived
    one, a pipeline job's, the CLI's). Each used to rewrite the file from its
    own stale in-memory list, erasing the others' records and resetting
    `applied` (so a correction was applied twice). Every mutation now takes an
    advisory lock, reloads the file, changes it, and replaces it atomically.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._items: list[Correction] = []
        self._reload()

    def _reload(self) -> None:
        # Safe without the lock: writers `os.replace`, so a reader sees a whole file.
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._items = []
            return
        self._items = [
            Correction.from_json(json.loads(line)) for line in text.splitlines() if line.strip()
        ]

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        """Exclusive across threads and processes; re-entrant within a thread."""
        key = str(self.path.resolve())
        with _PATH_LOCKS_GUARD:
            thread_lock = _PATH_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            # A nested acquire must not flock again: a second open file on the
            # same path blocks on our own lock and deadlocks `apply_pending`.
            if fcntl is None or _HELD_DEPTH.get(key, 0) > 0:
                _HELD_DEPTH[key] = _HELD_DEPTH.get(key, 0) + 1
                try:
                    yield
                finally:
                    _HELD_DEPTH[key] -= 1
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path.with_name(self.path.name + ".lock"), "a") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                _HELD_DEPTH[key] = 1
                try:
                    yield
                finally:
                    _HELD_DEPTH[key] = 0
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

    def __iter__(self):  # type: ignore[no-untyped-def]
        self._reload()
        return iter(list(self._items))

    def __len__(self) -> int:
        self._reload()
        return len(self._items)

    def add(self, correction: Correction) -> None:
        with self.locked():
            self._reload()
            self._items.append(correction)
            self._flush()

    def remove(self, correction_id: str) -> bool:
        with self.locked():
            self._reload()
            target = next((c for c in self._items if c.id == correction_id), None)
            if target is None:
                return False
            if target.applied:
                raise AppliedCorrectionError(correction_id)
            self._items = [c for c in self._items if c.id != correction_id]
            self._flush()
            return True

    def mark_applied(self, correction_id: str) -> None:
        with self.locked():
            self._reload()
            for c in self._items:
                if c.id == correction_id:
                    c.applied = True
            self._flush()

    def mark_failed(self, correction_id: str, error: str) -> None:
        with self.locked():
            self._reload()
            for c in self._items:
                if c.id == correction_id:
                    c.error = error
            self._flush()

    def _flush(self) -> None:
        # Temp file + replace: a crash mid-write must not leave a truncated log.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(
                    "\n".join(json.dumps(c.to_json(), ensure_ascii=False) for c in self._items)
                    + ("\n" if self._items else "")
                )
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

    def summary(self) -> dict[str, object]:
        self._reload()
        by_type: dict[str, int] = {}
        for c in self._items:
            by_type[c.type.value] = by_type.get(c.type.value, 0) + 1
        return {
            "total": len(self._items),
            "applied": sum(1 for c in self._items if c.applied),
            "pending": sum(1 for c in self._items if not c.applied),
            # What "Apply" actually acts on -- excludes flags, which have no
            # store-side effect and are dismissed by removal, not applying.
            "pending_actionable": sum(
                1 for c in self._items if not c.applied and c.type is not CorrectionType.FLAG
            ),
            "flags_open": sum(1 for c in self._items if c.type is CorrectionType.FLAG),
            "by_type": by_type,
        }


def apply_pending(store: Store, log: CorrectionLog) -> dict[str, object]:
    """Apply every unapplied correction to the live store. Idempotent.

    Returns a summary of what changed, since "nothing printed" is not
    distinguishable from "nothing happened" otherwise.
    """
    # Held throughout so two concurrent applies cannot both pick the same
    # pending correction and collide on its event id.
    with log.locked():
        return _apply_pending_locked(store, log)


def _apply_pending_locked(store: Store, log: CorrectionLog) -> dict[str, object]:
    applied: list[dict[str, object]] = []

    # `flag` is deliberately excluded: it changes nothing in the store, so
    # "apply pending corrections" sweeping it up would silently mark a note
    # as dealt with the moment you fix something unrelated. A flag's
    # lifecycle is separate -- it stays pending until you explicitly remove
    # it (`CorrectionLog.remove`, exposed as DELETE .../corrections/<id>),
    # which is "I've looked at this" without needing a second endpoint.
    pending = [c for c in log if not c.applied and c.type is not CorrectionType.FLAG]

    for correction in pending:
        # `seq` is UNIQUE: the millisecond clock collided for two applies in one ms.
        seq = store.next_seq()
        try:
            if correction.type is CorrectionType.MERGE_ENTITIES:
                result = _apply_merge(store, correction, seq=seq)
            elif correction.type is CorrectionType.REASSIGN_MENTION:
                result = _apply_reassign_mention(store, correction, seq=seq)
            elif correction.type is CorrectionType.REASSIGN_SPEAKER:
                result = _apply_reassign_speaker(store, correction, seq=seq)
            elif correction.type is CorrectionType.MERGE_LINES:
                result = _apply_merge_lines(store, correction, seq=seq)
            elif correction.type is CorrectionType.REASSIGN_SPAN_TYPE:
                result = _apply_reassign_span_type(store, correction, seq=seq)
            elif correction.type is CorrectionType.CREATE_MENTION:
                result = _apply_create_mention(store, correction, seq=seq)
            elif correction.type is CorrectionType.SET_GENDER:
                result = _apply_set_gender(store, correction, seq=seq)
            elif correction.type is CorrectionType.SET_DELIVERY:
                result = _apply_set_delivery(store, correction, seq=seq)
            else:  # pragma: no cover - CorrectionType is closed, kept for safety
                result = {"type": correction.type.value, "error": "unknown correction type"}
        except Exception as exc:
            result = {"type": correction.type.value, "error": str(exc)}
        else:
            # Only a *successful* apply is marked done. A correction whose
            # apply raised or returned an "error" result stays pending, so
            # it surfaces again next time rather than silently vanishing.
            if "error" not in result:
                log.mark_applied(correction.id)
        failed = "error" in result
        if failed:
            # A half-done apply (a row written, then the event append raised) was committed below and the correction
            # stayed pending, so the next apply wrote it again (EVOLUTION 4.183). Undo it, keep it pending, say why.
            store.conn.rollback()
            log.mark_failed(correction.id, str(result["error"]))
        applied.append(result)
        # Committed after every item, not once at the end: a later
        # correction failing must not roll back -- or leave merely
        # uncommitted -- the ones that already succeeded. `mark_applied`
        # writes its own file immediately (`CorrectionLog._flush`), so this
        # keeps the store and the log's "applied" bit from ever disagreeing
        # about whether a given correction actually landed.
        if not failed:
            store.conn.commit()

    return {"applied": applied, "count": sum(1 for r in applied if "error" not in r)}


def replay_applied_merges(store: Store, log: CorrectionLog, novel_id: str) -> int:
    """Re-apply the merges a person already made, after a resolve rebuilt every target.

    The log marks a merge applied once and `apply_pending` never replays it, so a re-resolve (a new chapter, a fixed
    stage) silently split "Fang Yuan" and "Wang Ju Chi" again while the log still read as merged. Entity ids are
    content-derived, so an id from the log names the same entity on a rerun over the same text; a merge whose
    entities are gone is skipped, not guessed at.
    """
    known = {e.id for e in store.all_selves(novel_id)}
    n = 0
    for c in log:
        if c.novel_id != novel_id or not c.applied or c.type is not CorrectionType.MERGE_ENTITIES:
            continue
        if str(c.payload["from_id"]) in known and str(c.payload["into_id"]) in known:
            _apply_merge(store, c, seq=store.next_seq())
            n += 1
    return n


def _apply_merge(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    from_id = str(correction.payload["from_id"])
    into_id = str(correction.payload["into_id"])
    novel_id = correction.novel_id

    mentions = [
        m for m in store.get_mentions(novel_id) if m.target_id == from_id
    ]
    for m in mentions:
        m.target_id = into_id
    if mentions:
        store.add_mentions(mentions)

    store.append_event(
        ResolutionEvent(
            id=f"{novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.MERGE,
            payload={
                "from_id": from_id,
                "into_id": into_id,
                "mentions_rebound": len(mentions),
                "source": "human_correction",
                "correction_id": correction.id,
            },
            cause_pos=DiscoursePosition(chapter=0, offset=0),
        )
    )
    return {
        "type": "merge_entities",
        "from_id": from_id,
        "into_id": into_id,
        "mentions_rebound": len(mentions),
    }


def _ensure_manual_entity(
    store: Store, correction: Correction, *, label: str, first_pos: DiscoursePosition
) -> str:
    """Create the entity a correction wants, if it doesn't exist yet.

    Idempotent on `new_entity_id` -- `apply_pending` may run this correction
    exactly once, but a corrupted/replayed log must not create the same
    character twice under two different ids.
    """
    entity_id = new_manual_entity_id(correction.novel_id, correction.id)
    if store.get_self(entity_id) is None:
        store.add_self(
            Self(
                id=entity_id,
                novel_id=correction.novel_id,
                canonical_label=label,
                first_attested_pos=first_pos,
            )
        )
    return entity_id


def _apply_reassign_mention(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    mention_id = str(correction.payload["mention_id"])
    novel_id = correction.novel_id

    mention = next((m for m in store.get_mentions(novel_id) if m.id == mention_id), None)
    if mention is None:
        return {"type": "reassign_mention", "mention_id": mention_id, "error": "mention not found"}

    new_label = correction.payload.get("new_label")
    if new_label:
        final_target = _ensure_manual_entity(
            store, correction, label=str(new_label), first_pos=mention.position
        )
    else:
        target_id = correction.payload.get("target_id")
        final_target = str(target_id) if target_id else None

    old_target = mention.target_id
    mention.target_id = final_target
    mention.method = ResolutionMethod.MANUAL
    mention.provenance = Provenance.HUMAN_AUTHORED
    store.add_mentions([mention])

    store.append_event(
        ResolutionEvent(
            id=f"{novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.REBIND if final_target else EventType.RETRACT,
            payload={
                "mention_id": mention_id,
                "old_target_id": old_target,
                "new_target_id": final_target,
                "source": "human_correction",
                "correction_id": correction.id,
            },
            cause_pos=mention.position,
        )
    )
    return {
        "type": "reassign_mention",
        "mention_id": mention_id,
        "old_target_id": old_target,
        "new_target_id": final_target,
    }


def _apply_create_mention(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    """A reviewer marks text the detector never proposed as a mention at all.

    `local_start`/`local_end` are span-local -- the same coordinate space the
    webview already renders marks in (`webview.py`'s `marks[].s`/`.e`) -- so
    the browser can send exactly what the user selected without knowing
    anything about block-local offsets. `Mention.offset` is block-local (see
    its docstring), so `span.start` translates it, the same translation
    `webview.py` already does in the other direction to build `marks`.
    """
    from echotales.pipeline.mentions.alias_type import classify_alias_type

    span_id = str(correction.payload["span_id"])
    chapter = float(correction.payload["chapter"])
    novel_id = correction.novel_id

    span = next((s for s in store.get_spans(novel_id, chapter) if s.id == span_id), None)
    if span is None:
        return {"type": "create_mention", "span_id": span_id, "error": "span not found"}

    local_start = int(correction.payload["local_start"])
    local_end = int(correction.payload["local_end"])
    if not (0 <= local_start < local_end <= len(span.text)):
        return {"type": "create_mention", "span_id": span_id, "error": "offset out of range"}
    surface = str(correction.payload.get("text") or span.text[local_start:local_end])

    new_label = correction.payload.get("new_label")
    if new_label:
        target_id = _ensure_manual_entity(
            store, correction, label=str(new_label), first_pos=span.position
        )
    else:
        target_id = correction.payload.get("target_id")
        target_id = str(target_id) if target_id else None
        if target_id is None:
            return {"type": "create_mention", "span_id": span_id, "error": "no target given"}

    alias_type, _ = classify_alias_type(surface)
    reference_mode = (
        ReferenceMode.DIALOGUE_REFERENCE
        if span.span_type is SpanType.DIALOGUE
        else ReferenceMode.NARRATOR_REFERENCE
    )
    mention = Mention(
        id=f"{novel_id}:correction:{correction.id}:mention",
        novel_id=novel_id,
        segment_id="",
        chapter=chapter,
        offset=span.start + local_start,
        text=surface,
        alias_type=alias_type,
        span_type=span.span_type,
        reference_mode=reference_mode,
        target_kind=TargetKind.SELF,
        target_id=target_id,
        confidence=1.0,
        method=ResolutionMethod.MANUAL,
        provenance=Provenance.HUMAN_AUTHORED,
        block_index=span.block_index,
    )
    store.add_mentions([mention])

    store.append_event(
        ResolutionEvent(
            id=f"{novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.REBIND,
            payload={
                "mention_id": mention.id,
                "span_id": span_id,
                "surface": surface,
                "new_target_id": target_id,
                "source": "human_correction",
                "correction_id": correction.id,
            },
            cause_pos=span.position,
        )
    )
    return {
        "type": "create_mention",
        "span_id": span_id,
        "mention_id": mention.id,
        "target_id": target_id,
    }


def _apply_reassign_speaker(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    span_id = str(correction.payload["span_id"])
    chapter = float(correction.payload["chapter"])
    novel_id = correction.novel_id

    span = next((s for s in store.get_spans(novel_id, chapter) if s.id == span_id), None)
    if span is None:
        return {"type": "reassign_speaker", "span_id": span_id, "error": "span not found"}

    new_label = correction.payload.get("new_label")
    anon_slot = correction.payload.get("anon_slot")
    if new_label:
        final_speaker = _ensure_manual_entity(
            store, correction, label=str(new_label), first_pos=span.position
        )
    elif anon_slot:
        # A distinct voice slot, not an identity -- same id scheme as the
        # pipeline's own `speakers/runner.py::_assign_anonymous_slots`, so it
        # renders as "Unknown Speaker N" and gets a slot colour for free
        # (`webview.py::_anon_slot_label`/`_anon_slot_colour`) instead of
        # needing a parallel display path for a human-picked slot.
        final_speaker = f"{novel_id}:anon:{chapter:g}:{int(anon_slot)}"
    else:
        speaker_id = correction.payload.get("speaker_id")
        final_speaker = str(speaker_id) if speaker_id else None

    old_speaker = span.speaker_self_id
    span.speaker_self_id = final_speaker
    # HUMAN, not EXPLICIT/ANONYMOUS_SLOT, and confidence 1.0: the old EXPLICIT write left the reader's 0.0 in place,
    # so `voice/runner.py` voiced a reviewed line as "unconfirmed" and `review_gate._reason` queued it again.
    span.attribution_method = AttributionMethod.HUMAN if final_speaker else AttributionMethod.UNRESOLVED
    span.confidence = 1.0 if final_speaker else 0.0
    store.add_spans([span])

    store.append_event(
        ResolutionEvent(
            id=f"{novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.REBIND if final_speaker else EventType.RETRACT,
            payload={
                "span_id": span_id,
                "old_speaker_id": old_speaker,
                "new_speaker_id": final_speaker,
                "source": "human_correction",
                "correction_id": correction.id,
            },
            cause_pos=span.position,
        )
    )
    return {
        "type": "reassign_speaker",
        "span_id": span_id,
        "old_speaker_id": old_speaker,
        "new_speaker_id": final_speaker,
    }


def _apply_merge_lines(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    """Fold `absorbed_span_id` into `primary_span_id`.

    Both must share a block. The merged span's text is re-sliced from the
    source block rather than concatenated from the two spans' own `.text`,
    so punctuation and whitespace between them survive exactly as written --
    string-joining `a.text + b.text` would silently lose or duplicate
    whatever character sat at the boundary.
    """
    novel_id = correction.novel_id
    chapter = float(correction.payload["chapter"])
    primary_id = str(correction.payload["primary_span_id"])
    absorbed_id = str(correction.payload["absorbed_span_id"])

    spans = {s.id: s for s in store.get_spans(novel_id, chapter)}
    primary = spans.get(primary_id)
    absorbed = spans.get(absorbed_id)
    if primary is None or absorbed is None:
        return {
            "type": "merge_lines",
            "error": f"span not found (primary={primary_id!r} absorbed={absorbed_id!r})",
        }
    if primary.block_index != absorbed.block_index:
        return {"type": "merge_lines", "error": "spans are not in the same block"}

    chapter_obj = store.get_chapter(novel_id, chapter)
    block = next((b for b in chapter_obj.blocks if b.index == primary.block_index), None)
    if block is None:
        return {"type": "merge_lines", "error": "containing block not found"}

    new_start = min(primary.start, absorbed.start)
    new_end = max(primary.end, absorbed.end)
    primary.start = new_start
    primary.end = new_end
    primary.text = block.text[new_start:new_end].strip()
    store.add_spans([primary])
    store.delete_span(novel_id, absorbed_id)

    store.append_event(
        ResolutionEvent(
            id=f"{novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.VOID_SPAN,
            payload={
                "merged_into": primary_id,
                "absorbed": absorbed_id,
                "source": "human_correction",
                "correction_id": correction.id,
            },
            cause_pos=primary.position,
        )
    )
    return {"type": "merge_lines", "primary_span_id": primary_id, "absorbed_span_id": absorbed_id}


def _apply_reassign_span_type(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    novel_id = correction.novel_id
    span_id = str(correction.payload["span_id"])
    chapter = float(correction.payload["chapter"])
    new_type = SpanType(str(correction.payload["new_type"]))

    span = next((s for s in store.get_spans(novel_id, chapter) if s.id == span_id), None)
    if span is None:
        return {"type": "reassign_span_type", "span_id": span_id, "error": "span not found"}

    old_type = span.span_type
    span.span_type = new_type
    # A line retyped away from DIALOGUE/INNER_MONOLOGUE is no longer spoken by
    # anyone in particular; carrying over a stale speaker (real or anonymous)
    # would misrepresent both the graph and, downstream, who gets voiced.
    if new_type not in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE, SpanType.CROWD_REACTION):
        span.speaker_self_id = None
        span.attribution_method = AttributionMethod.UNRESOLVED
    store.add_spans([span])

    store.append_event(
        ResolutionEvent(
            id=f"{novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.VOID_SPAN if new_type is SpanType.NON_DIEGETIC else EventType.REBIND,
            payload={
                "span_id": span_id,
                "old_type": old_type.value,
                "new_type": new_type.value,
                "source": "human_correction",
                "correction_id": correction.id,
            },
            cause_pos=span.position,
        )
    )
    return {
        "type": "reassign_span_type",
        "span_id": span_id,
        "old_type": old_type.value,
        "new_type": new_type.value,
    }


def _apply_set_gender(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    from echotales.pipeline.persona.gender import HUMAN_PREFIX, write_gender

    self_id = str(correction.payload["self_id"])
    gender = str(correction.payload.get("gender", "")).strip().lower()
    if gender not in ("male", "female", "unknown"):
        return {"type": "set_gender", "self_id": self_id, "error": f"gender must be male, female or unknown, got {gender!r}"}
    entity = next((e for e in store.all_selves(correction.novel_id) if e.id == self_id), None)
    if entity is None or not entity.kind.is_person:
        return {"type": "set_gender", "self_id": self_id, "error": "character not found"}
    written = write_gender(
        store, correction.novel_id, self_id, gender, f"{HUMAN_PREFIX} reviewer set gender", confidence=1.0,
        at=entity.first_attested_pos,
    )
    store.append_event(
        ResolutionEvent(
            id=f"{correction.novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.ATTRIBUTE_UPDATE,
            payload={"self_id": self_id, "key": "gender", "value": gender, "source": "human_correction",
                     "correction_id": correction.id},
            cause_pos=entity.first_attested_pos,
        )
    )
    return {"type": "set_gender", "self_id": self_id, "gender": gender, "bodies": written}


def _apply_set_delivery(store: Store, correction: Correction, *, seq: int) -> dict[str, object]:
    from echotales.pipeline.reader.delivery_pass import LABELS

    span_id = str(correction.payload.get("span_id", ""))
    emotion = str(correction.payload.get("emotion", "")).strip()
    intensity = correction.payload.get("intensity")

    def refuse(why: str) -> dict[str, object]:
        return {"type": "set_delivery", "span_id": span_id, "error": why}

    # The stored emotion is the corpus name the delivery pass writes ("anger", not "angry"), so a clip can be picked by it.
    if emotion not in set(LABELS.values()):
        return refuse(f"emotion must be one of {sorted(set(LABELS.values()))}, got {emotion!r}")
    if isinstance(intensity, bool) or not isinstance(intensity, int) or not 1 <= intensity <= 3:
        return refuse(f"intensity must be 1, 2 or 3, got {intensity!r}")
    found = store.span_chapter_and_type(correction.novel_id, span_id)
    if found is None:
        return refuse("span not found")
    chapter, span_type = found
    # Narration has a mood per passage rather than a per-line emotion; giving it one here would be read by nothing.
    if span_type not in (SpanType.DIALOGUE.value, SpanType.INNER_MONOLOGUE.value, SpanType.CROWD_REACTION.value):
        return refuse("only a quoted line (dialogue, inner monologue or a crowd reaction) has a delivery")
    store.set_span_emotion_override(correction.novel_id, span_id, chapter, emotion, intensity)
    store.append_event(
        ResolutionEvent(
            id=f"{correction.novel_id}:correction:{correction.id}",
            seq=seq,
            type=EventType.ATTRIBUTE_UPDATE,
            payload={"span_id": span_id, "key": "delivery", "value": f"{emotion}:{intensity}",
                     "source": "human_correction", "correction_id": correction.id},
            cause_pos=DiscoursePosition(chapter=int(chapter), offset=0),
        )
    )
    return {"type": "set_delivery", "span_id": span_id, "emotion": emotion, "intensity": intensity}
