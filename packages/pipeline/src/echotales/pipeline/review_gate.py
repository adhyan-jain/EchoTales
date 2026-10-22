"""The review gate: what to show a person, and the locked bible a render is allowed to read (decisions D6, Phase B).

Analyse automatically -> a person reviews only what is flagged -> **lock a versioned bible** -> generate. This module
holds the three read models the Studio screens need (a ranked queue of speaker lines to check, a per-character look and
identity timeline, a lock status) and the lock itself. It reads and writes only the store; the HTTP routes in
`webview_server.py` are thin wrappers, so everything here is testable without a server.

A lock stores a digest of the facts a render reads, per chapter. A later edit makes the live digest differ, which marks
the bible "dirty" and says which chapters changed, so only the episodes built from those chapters need to render again.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from echotales.core.enums import SpanType, TargetKind
from echotales.core.store import Store
from echotales.pipeline.version import PIPELINE_VERSION, staleness_reason

#: Span types that carry a quoted line a person can have said.
_QUOTE_TYPES = (SpanType.DIALOGUE.value, SpanType.INNER_MONOLOGUE.value, SpanType.CROWD_REACTION.value)
#: A model-attributed line below this confidence is queued even though it has a name.
LOW_CONFIDENCE = 0.8


def _slot_label(speaker_id: str) -> str:
    """`n:title:academy_elder` / `n:anon:4:academy_elder` -> "academy elder"."""
    tail = speaker_id.split(":title:")[-1] if ":title:" in speaker_id else speaker_id.split(":")[-1]
    return tail.replace("_", " ")


def _reason(speaker_id: str | None, method: str, confidence: float) -> str | None:
    """Why a line is worth a person's time, or None when it is settled (an explicit "X said")."""
    if not speaker_id:
        return "unnamed"
    if ":title:" in speaker_id or ":anon:" in speaker_id:
        return "role_slot"
    if method == "EXPLICIT":
        return "low_confidence" if confidence < LOW_CONFIDENCE else None
    return "low_confidence" if confidence < LOW_CONFIDENCE else "model_guess"


def speaker_queue(
    store: Store, novel_id: str, chapter: float | None = None, limit: int = 100, include_guesses: bool = False
) -> dict:  # type: ignore[type-arg]
    """Quoted lines whose speaker a person should confirm, most-affecting first.

    Unnamed lines, role slots and low-confidence guesses are queued by default; a named model guess is listed only with
    `include_guesses` (a full audit), because showing every guess would defeat the point of a bounded queue
    (non-negotiable 7). `affected` counts the lines in the chapter that share the same speaker slot, so one decision
    on a slot is worth as many lines as it covers."""
    marks = ",".join("?" for _ in _QUOTE_TYPES)
    sql = (
        f"SELECT id, chapter, block_index, start, text, speaker_self_id, attribution_method, confidence FROM span "
        f"WHERE novel_id=? AND span_type IN ({marks})"
    )
    params: list = [novel_id, *_QUOTE_TYPES]
    if chapter is not None:
        sql += " AND chapter=?"
        params.append(chapter)
    rows = store.conn.execute(sql + " ORDER BY chapter, block_index, start", params).fetchall()
    share: dict[tuple[float, str], int] = {}
    for r in rows:
        key = (r["chapter"], r["speaker_self_id"] or "")
        share[key] = share.get(key, 0) + 1
    labels: dict[str, str] = {}
    items = []
    for r in rows:
        reason = _reason(r["speaker_self_id"], r["attribution_method"], r["confidence"])
        if reason is None or (reason == "model_guess" and not include_guesses):
            continue
        sid = r["speaker_self_id"]
        if sid and sid not in labels:
            entity = store.get_self(sid)
            labels[sid] = entity.canonical_label if entity else _slot_label(sid)
        items.append({
            "span_id": r["id"], "chapter": r["chapter"], "block_index": r["block_index"], "text": r["text"],
            "speaker_id": sid, "speaker_label": labels.get(sid) if sid else None,
            "method": r["attribution_method"], "confidence": r["confidence"], "reason": reason,
            "affected": share[(r["chapter"], sid or "")],
        })
    items.sort(key=lambda i: (-i["affected"], i["confidence"], i["chapter"], i["block_index"]))
    return {"total": len(items), "items": items[: max(0, limit)]}


def character_timeline(store: Store, novel_id: str, self_id: str) -> dict | None:  # type: ignore[type-arg]
    """Every look version and every name/title of one character, each with its evidence quote and two clocks.

    `story_from` can be earlier than `learned_chapter`: a title held since chapter 1 but tied to its holder's name in
    chapter 6 shows both, which is what lets a reviewer see why chapter 1's "clan head" is the same person as chapter
    6's named man (decisions D20)."""
    entity = store.get_self(self_id)
    if entity is None:
        return None
    inf = float("inf")
    persona_ids = {f"{self_id}:body1"}
    personas = []
    for b in store.get_self_persona_bindings(self_id=self_id):
        persona_ids.add(b.persona_id)
        personas.append({
            "persona_id": b.persona_id, "from_chapter": b.interval.from_lb,
            "to_chapter": None if b.interval.to_ub == inf else b.interval.to_ub,
        })
    if not personas:
        personas.append({"persona_id": f"{self_id}:body1", "from_chapter": entity.first_attested_pos.chapter, "to_chapter": None})
    looks = []
    for pid in sorted(persona_ids):
        for a in store.get_attributes(TargetKind.PERSONA, pid):
            if a.key in ("reference_image_path", "reference_appearance_digest"):
                continue  # bookkeeping rows, not looks
            looks.append({
                "persona_id": pid, "key": a.key, "value": a.value, "from_chapter": a.interval.from_lb,
                "evidence": a.evidence, "confidence": a.confidence, "asserted_by": a.asserted_by.value,
            })
    looks.sort(key=lambda x: (x["key"], x["from_chapter"]))
    # The database can hold the same binding several times (LotM's "Klein Moretti" appeared three times in the first
    # browser check), so identical bindings are shown once, keeping the longest evidence.
    unique: dict[tuple, dict] = {}  # type: ignore[type-arg]
    for a in store.get_aliases_for(TargetKind.SELF, self_id):
        if a.retracted_at is not None:
            continue
        row = {
            "alias": a.alias, "alias_type": a.alias_type.value, "story_from": a.interval.from_lb,
            "story_to": None if a.interval.to_ub == inf else a.interval.to_ub,
            "learned_chapter": a.learned_at_pos.chapter, "evidence": a.evidence,
        }
        key = (row["alias"].lower(), row["alias_type"], row["story_from"], row["story_to"], row["learned_chapter"])
        if key not in unique or len(row["evidence"]) > len(unique[key]["evidence"]):
            unique[key] = row
    identities = sorted(unique.values(), key=lambda x: (x["story_from"], x["alias"]))
    return {"self_id": self_id, "label": entity.canonical_label, "personas": personas, "looks": looks, "identities": identities}


def fact_digests(store: Store, novel_id: str) -> tuple[str, dict[str, str], dict[str, int]]:
    """A digest of what a render reads, in total and per chapter, plus counts.

    Covers who speaks each quoted line, every attribute and alias by the chapter it was learned, and the entities by
    first chapter. Any edit that changes one of those changes the digest of exactly the chapter it belongs to."""
    per: dict[str, list[str]] = {}

    def add(chapter: float, *parts: object) -> None:
        per.setdefault(str(int(chapter)), []).append("|".join(str(p) for p in parts))

    marks = ",".join("?" for _ in _QUOTE_TYPES)
    lines = store.conn.execute(
        f"SELECT chapter, id, span_type, speaker_self_id FROM span WHERE novel_id=? AND span_type IN ({marks})",
        (novel_id, *_QUOTE_TYPES),
    ).fetchall()
    for r in lines:
        add(r["chapter"], "span", r["id"], r["span_type"], r["speaker_self_id"])
    attrs = store.conn.execute(
        "SELECT learned_chapter, target_id, key, value, truth_status FROM attribute WHERE novel_id=?", (novel_id,)
    ).fetchall()
    for r in attrs:
        add(r["learned_chapter"], "attr", r["target_id"], r["key"], r["value"], r["truth_status"])
    aliases = store.conn.execute(
        "SELECT learned_chapter, target_id, alias, alias_type, story_from_lb, story_to_ub, truth_status FROM alias_binding"
        " WHERE novel_id=?", (novel_id,),
    ).fetchall()
    for r in aliases:
        add(r["learned_chapter"], "alias", r["target_id"], r["alias"], r["alias_type"], r["story_from_lb"], r["story_to_ub"], r["truth_status"])
    entities = store.conn.execute(
        "SELECT first_chapter, id, canonical_label, kind FROM self_entity WHERE novel_id=?", (novel_id,)
    ).fetchall()
    for r in entities:
        add(r["first_chapter"], "entity", r["id"], r["canonical_label"], r["kind"])
    chapter_digests = {
        ch: hashlib.sha256("\n".join(sorted(parts)).encode()).hexdigest()[:16] for ch, parts in sorted(per.items(), key=lambda kv: int(kv[0]))
    }
    total = hashlib.sha256(json.dumps(chapter_digests, sort_keys=True).encode()).hexdigest()[:16]
    counts = {"lines": len(lines), "attributes": len(attrs), "aliases": len(aliases), "entities": len(entities)}
    return total, chapter_digests, counts


def _changed_chapters(old: dict[str, str], new: dict[str, str]) -> list[int]:
    return sorted(int(ch) for ch in set(old) | set(new) if old.get(ch) != new.get(ch))


def bible_status(store: Store, novel_id: str) -> dict:  # type: ignore[type-arg]
    """The current digest against the latest lock: is anything unlocked, and which chapters differ?"""
    locks = store.list_bible_locks(novel_id)
    digest, chapters, _counts = fact_digests(store, novel_id)
    latest = locks[-1] if locks else None
    changed = _changed_chapters(latest["chapter_digests"], chapters) if latest else sorted(int(c) for c in chapters)
    return {
        "current": {
            "digest": digest,
            "pipeline_version": PIPELINE_VERSION,
            "stale_reason": staleness_reason(store, novel_id),
            "dirty": latest is None or latest["digest"] != digest,
            "changed_chapters": changed,
            "locked_version": latest["version"] if latest else None,
        },
        "locks": [{k: v for k, v in lock.items() if k not in ("digest", "chapter_digests")} for lock in locks],
    }


class StaleBuild(Exception):
    """Raised when a stale build is asked to be locked: locking would bless facts an older pipeline produced."""


def lock_bible(store: Store, novel_id: str, note: str = "") -> dict:  # type: ignore[type-arg]
    """Freeze the current facts as the next bible version. Refuses a stale build (version-stamp check, D8)."""
    reason = staleness_reason(store, novel_id)
    if reason:
        raise StaleBuild(reason)
    previous = store.list_bible_locks(novel_id)
    digest, chapters, counts = fact_digests(store, novel_id)
    lock = store.add_bible_lock(novel_id, {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": note,
        "pipeline_version": PIPELINE_VERSION, "digest": digest, "chapter_digests": chapters, "counts": counts,
    })
    return {
        "version": lock["version"], "created_at": lock["created_at"], "note": note, "pipeline_version": PIPELINE_VERSION,
        "counts": counts, "changed_chapters": _changed_chapters(previous[-1]["chapter_digests"], chapters) if previous else [],
    }


def unlocked_reason(store: Store, novel_id: str) -> str | None:
    """Why a real render must not read this bible, or None: no lock yet, or edits since the last lock."""
    status = bible_status(store, novel_id)["current"]
    if status["locked_version"] is None:
        return f"{novel_id!r} has no locked bible; review it and lock a version before a real render."
    if status["dirty"]:
        chapters = ", ".join(str(c) for c in status["changed_chapters"][:10])
        return f"{novel_id!r} has edits since bible v{status['locked_version']} (chapters {chapters}); lock a new version first."
    return None
