"""Local HTTP backend for the interactive webview.

The read-only viewer (`webview.py`) is a static export -- correct for
auditing a finished run, but it can't accept a correction because there is
nothing running to receive one. This module is that server: stdlib only
(`http.server`), because the whole point is a local review tool, and adding a
web framework dependency for a handful of routes used by one person at a time
would be solving a problem that doesn't exist here.

Routes:
    GET  /api/auth/status              {"auth_required": bool} -- never gated itself
    POST /api/auth/login               body: {"password"} -> {"token"}
    GET  /api/manifest
    GET  /api/research/summary         stored name-leakage study results (research_demo.summary)
    GET  /api/research/items           the six demo probe items (404 until build_demo_items.py has run)
    POST /api/research/probe           body: {"item_id", "model", "arms"?} -> one local ollama model on 1-3 arms
    POST /api/projects                 body: {"id", "title", "content_type"}
                                        (Section 7.2 -- registers a project;
                                        does not run ingest, see Registry.create_project)
    POST /api/projects/<id>/genre      body: {"genre": key | null} -- the visual genre image generation draws in
                                        (persona/genre.py); null returns to the detected one
    GET  /api/novels/<id>              live payload, corrections overlaid
    GET  /api/compute                  ECHOTALES_COMPUTE mode, providers, enabled engines with the reason any is refused,
                                        panel tiers, memory and GPU (pipeline/compute.py) -- the Studio's engine picker
    GET  /api/gpu                      {"available", "free", "used_mb", "total_mb", "name"}
    GET  /api/novels/<id>/reader?chapter=c   the cast as known at the end of chapter c (webview.build_reader_cast)
    GET  /api/novels/<id>/corrections  log + summary
    POST /api/novels/<id>/corrections  body: {"type": "merge_entities",
                                               "payload": {"from_id", "into_id"}}
    DELETE /api/novels/<id>/corrections/<correction_id>   undo a pending one
    POST /api/novels/<id>/apply        write pending corrections into the store
    GET  /api/novels/<id>/characters   per-character dashboard (Section 7.2/7.3):
                                        assigned voice, reference images, and the
                                        evidence behind every auto-assigned trait
    POST /api/novels/<id>/characters/<self_id>/voice      body: {"speaker_id", "note"}
    POST /api/novels/<id>/characters/<self_id>/reference  body: {"candidate_id", "note"}

Every route except `/api/auth/status` and `/api/auth/login` requires a valid
session token (`Authorization: Bearer <token>`) once `ECHOTALES_WEBVIEW_PASSWORD`
is set in the server's environment -- see `SessionStore`/`Handler._authorized`.
Unset (the default, and every deployment's behaviour before Section 7.2), auth
is off entirely.

Corrections are overlaid onto the payload *before* it reaches the browser
(`_overlay_merges`), not reapplied client-side, so the static viewer's render
logic and the live one never have to agree on a second implementation of "what
does a merge look like."
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from echotales.core.lifecycle import JobStatus
from echotales.core.models import Job, ReviewItem
from echotales.core.store import Store
from echotales.pipeline import paths, research_demo
from echotales.pipeline.compute import default_image_engine
from echotales.pipeline.errors import ErrorCode
from echotales.pipeline._multipart import MultipartError, parse_single_file
from echotales.pipeline.corrections import (
    AppliedCorrectionError,
    Correction,
    CorrectionLog,
    CorrectionType,
    apply_pending,
    new_manual_entity_id,
)
from echotales.pipeline.engines import registry as engine_registry
from echotales.pipeline.jobs import (
    ALLOWED_HTTP_ENGINES,
    JOB_KINDS,
    JobQueue,
    http_engine_known,
    new_job_id,
    pipeline_stage_names,
)
from echotales.pipeline.webview import (
    NovelSource,
    _anon_slot_colour,
    _anon_slot_label,
    build_character_dashboard,
    build_novel_payload,
    build_reader_cast,
)

#: Section 7.2: a real, minimal auth gate suited to a local, single-operator
#: review tool -- not a decorative login screen. Reads the password from an
#: environment variable rather than hardcoding or storing one in the repo;
#: unset means auth is off (the tool's behaviour before this section, which
#: every existing deployment keeps getting unless an operator opts in).
#: Session tokens are held in-process only (no persistence across restarts),
#: which is the right tradeoff for a tool one person runs on their own
#: machine -- there is no multi-user session store to build here.
_AUTH_ENV_VAR = "ECHOTALES_WEBVIEW_PASSWORD"

# The shot routes used to return invented QA scores over recycled panels and a lock that stored nothing. They stay
# refused until they call keyframes/engine.py with a real KeyframeQAGate (product plan step 4); a screen that shows
# numbers nobody measured is worse than no screen.
_SHOT_QA_UNWIRED = "per-shot candidates, re-roll and lock are not wired to the keyframe engine yet; no QA score is shown that was not measured"
_SESSION_TTL_SECONDS = 12 * 3600


@dataclass(slots=True)
class SessionStore:
    tokens: dict[str, float] = field(default_factory=dict)

    def issue(self) -> str:
        token = secrets.token_urlsafe(32)
        self.tokens[token] = time.time() + _SESSION_TTL_SECONDS
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        expiry = self.tokens.get(token)
        if expiry is None:
            return False
        if expiry < time.time():
            del self.tokens[token]
            return False
        return True

log = logging.getLogger(__name__)

#: Marks a character that exists only because a correction created it --
#: distinct from the ranked palette so "this one didn't come from the
#: resolver" is visible at a glance, not just inferable from the id.
_MANUAL_ENTITY_COLOUR = "#2EC4B6"


@dataclass(slots=True)
class NovelHandle:
    source: NovelSource
    store: Store
    corrections: CorrectionLog
    _payload_cache: dict | None = None  # type: ignore[type-arg]

    def payload(self) -> dict:  # type: ignore[type-arg]
        if self._payload_cache is None:
            base = build_novel_payload(self.store, self.source.novel_id, self.source.label)
            self._payload_cache = _overlay_corrections(base, self.corrections)
        return self._payload_cache

    def invalidate(self) -> None:
        self._payload_cache = None


def _overlay_corrections(payload: dict, corrections: CorrectionLog) -> dict:  # type: ignore[type-arg]
    """Preview every pending and applied correction against the base payload.

    Recomputed from scratch each call rather than tracked incrementally.
    Three correction types can each touch a mention's entity, a span's
    speaker, and the entity list at once (a merge changes what a mention
    displays as; so does a mention-level reassignment of that same mention;
    both must agree on the result) -- one walk that rebuilds marks and counts
    together is much easier to get right than three deltas that all have to
    reconcile. Pending and applied corrections render identically: once
    applied the store already agrees, so there is nothing to distinguish.
    """
    merge_redirect: dict[str, str] = {}
    mention_override: dict[str, str | None] = {}
    speaker_override: dict[str, str | None] = {}
    #: span_ids whose speaker_override is an anon-slot id, not a real entity
    #: -- rendered as "Unknown Speaker N" with slot styling, not as a normal
    #: attributed line (see the anon_slot branch below).
    anon_slot_override: set[str] = set()
    manual_labels: dict[str, str] = {}  # manual entity id -> label
    flags_by_mention: dict[str, list[dict]] = {}  # type: ignore[type-arg]
    flags_by_span: dict[str, list[dict]] = {}  # type: ignore[type-arg]
    span_type_override: dict[str, str] = {}
    delivery_override: dict[str, dict] = {}  # type: ignore[type-arg]

    novel_id = payload["novel_id"]

    for c in corrections:
        if c.type is CorrectionType.FLAG:
            entry = {
                "correction_id": c.id,
                "note": c.payload.get("note", ""),
                "source": c.payload.get("source", "human"),
            }
            if c.payload.get("mention_id"):
                flags_by_mention.setdefault(str(c.payload["mention_id"]), []).append(entry)
            if c.payload.get("span_id"):
                flags_by_span.setdefault(str(c.payload["span_id"]), []).append(entry)
        elif c.type is CorrectionType.MERGE_ENTITIES:
            frm, into = str(c.payload["from_id"]), str(c.payload["into_id"])
            merge_redirect[frm] = merge_redirect.get(into, into)
        elif c.type is CorrectionType.REASSIGN_MENTION:
            mention_id = str(c.payload["mention_id"])
            new_label = c.payload.get("new_label")
            if new_label:
                eid = new_manual_entity_id(novel_id, c.id)
                manual_labels[eid] = str(new_label)
                mention_override[mention_id] = eid
            else:
                target_id = c.payload.get("target_id")
                mention_override[mention_id] = str(target_id) if target_id else None
        elif c.type is CorrectionType.REASSIGN_SPEAKER:
            span_id = str(c.payload["span_id"])
            new_label = c.payload.get("new_label")
            anon_slot = c.payload.get("anon_slot")
            if new_label:
                eid = new_manual_entity_id(novel_id, c.id)
                manual_labels[eid] = str(new_label)
                speaker_override[span_id] = eid
            elif anon_slot:
                # Same id scheme as corrections.py::_apply_reassign_speaker
                # and speakers/runner.py::_assign_anonymous_slots, so the
                # existing anon-id-to-"Unknown Speaker N" rendering path
                # (webview.py) picks it up with no extra logic here.
                chapter = c.payload.get("chapter")
                speaker_override[span_id] = f"{novel_id}:anon:{float(chapter):g}:{int(anon_slot)}"
                anon_slot_override.add(span_id)
            else:
                speaker_id = c.payload.get("speaker_id")
                speaker_override[span_id] = str(speaker_id) if speaker_id else None
        elif c.type is CorrectionType.REASSIGN_SPAN_TYPE:
            span_type_override[str(c.payload["span_id"])] = str(c.payload["new_type"])
        elif c.type is CorrectionType.SET_DELIVERY:
            delivery_override[str(c.payload.get("span_id"))] = {
                "emotion": c.payload.get("emotion"), "intensity": c.payload.get("intensity"), "pending": not c.applied,
            }

    if not (
        merge_redirect or mention_override or speaker_override
        or flags_by_mention or flags_by_span or span_type_override or delivery_override
    ):
        return payload

    def resolve_chain(eid: str) -> str:
        """Follow a merge chain to its root. Cycle-safe against a corrupt log."""
        seen: set[str] = set()
        while eid in merge_redirect and eid not in seen:
            seen.add(eid)
            eid = merge_redirect[eid]
        return eid

    label_of = {e["id"]: e["label"] for e in payload["entities"]}
    colour_of = {e["id"]: e["colour"] for e in payload["entities"]}
    for eid, label in manual_labels.items():
        label_of[eid] = label
        colour_of[eid] = _MANUAL_ENTITY_COLOUR

    # Only recomputed for entities a correction could plausibly have
    # changed -- an untouched entity keeps its original (already-correct)
    # count rather than trusting a from-scratch recount of every mark to
    # match it exactly in every edge case.
    touched = (
        set(mention_override.values())
        | set(speaker_override.values())
        | set(merge_redirect.values())
    )
    touched.discard(None)

    counts: dict[str, int] = {}
    first_ch: dict[str, float] = {}
    last_ch: dict[str, float] = {}
    speaks: set[str] = set()

    def touch(eid: str, chapter: float) -> None:
        counts[eid] = counts.get(eid, 0) + 1
        first_ch[eid] = min(first_ch.get(eid, chapter), chapter)
        last_ch[eid] = max(last_ch.get(eid, chapter), chapter)

    dialogue_total = 0
    dialogue_attributed = 0
    dialogue_anonymous = 0
    new_chapters = []
    for ch in payload["chapters"]:
        chapter_num = ch["number"]
        new_spans = []
        for span in ch["spans"]:
            new_marks = []
            for m in span["marks"]:
                mention_id = m.get("mention_id")
                if mention_id in mention_override:
                    final_id = mention_override[mention_id]
                elif m.get("id"):
                    final_id = resolve_chain(m["id"])
                else:
                    final_id = None

                if final_id:
                    touch(final_id, chapter_num)
                    m = {
                        **m,
                        "id": final_id,
                        "label": label_of.get(final_id, m["label"]),
                        "colour": colour_of.get(final_id, m["colour"]),
                        "resolved": True,
                    }
                elif mention_id in mention_override:
                    m = {**m, "id": None, "colour": "#8a8a8a", "resolved": False}
                if mention_id in flags_by_mention:
                    m = {**m, "flags": flags_by_mention[mention_id]}
                new_marks.append(m)

            span_id = span.get("span_id")
            if span_id in delivery_override and span.get("type") in ("DIALOGUE", "INNER_MONOLOGUE", "CROWD_REACTION"):
                span = {**span, "delivery": delivery_override[span_id]}
            if span_id in span_type_override:
                new_type = span_type_override[span_id]
                span = {**span, "type": new_type}
                if new_type not in ("DIALOGUE", "INNER_MONOLOGUE", "CROWD_REACTION"):
                    span = {
                        **span,
                        "speaker": None,
                        "speaker_id": None,
                        "anonymous_speaker": False,
                        "speaker_colour": None,
                    }

            speaker_id = span.get("speaker_id")
            if span_id in speaker_override:
                final_speaker = speaker_override[span_id]
            elif speaker_id:
                final_speaker = resolve_chain(speaker_id)
            else:
                final_speaker = None

            if final_speaker and span_id in anon_slot_override:
                # A distinct voice slot, not an identity -- the opposite of
                # the "clear the anonymous styling" case below, so it needs
                # its own branch rather than falling into the named-speaker
                # one just because `final_speaker` is truthy.
                span = {
                    **span,
                    "speaker_id": final_speaker,
                    "speaker": _anon_slot_label(final_speaker),
                    "anonymous_speaker": True,
                    "speaker_colour": _anon_slot_colour(final_speaker),
                    "method": "anonymous (pending)",
                }
            elif final_speaker:
                speaks.add(final_speaker)
                span = {
                    **span,
                    "speaker_id": final_speaker,
                    "speaker": label_of.get(final_speaker, span["speaker"]),
                    # Reflects only the *preview* -- the real method (always
                    # EXPLICIT) is set on `apply`. Without this the method
                    # label kept showing the pre-correction value (often
                    # UNRESOLVED) right next to a speaker name that had
                    # already changed, which reads as a second bug at a
                    # glance even though the speaker itself is correct.
                    "method": "EXPLICIT (pending)" if span_id in speaker_override else span["method"],
                }
                # A correction that names a real speaker resolves the "who is
                # this" question a slot never claimed to answer -- clear the
                # anonymous styling so it reads as a normal attributed line.
                if span_id in speaker_override:
                    span = {**span, "anonymous_speaker": False, "speaker_colour": None}
            elif span_id in speaker_override:
                span = {**span, "speaker_id": None, "speaker": None, "anonymous_speaker": False}
            if span_id in flags_by_span:
                span = {**span, "flags": flags_by_span[span_id]}

            if span["type"] == "DIALOGUE":
                dialogue_total += 1
                if span.get("speaker") and not span.get("anonymous_speaker"):
                    dialogue_attributed += 1
                elif span.get("anonymous_speaker"):
                    dialogue_anonymous += 1

            new_spans.append({**span, "marks": new_marks})
        new_chapters.append({**ch, "spans": new_spans})

    redirected_away = set(merge_redirect.keys())
    new_entities = []
    for e in payload["entities"]:
        if e["id"] in redirected_away:
            continue
        eid = e["id"]
        if eid in touched:
            new_entities.append(
                {
                    **e,
                    "count": counts.get(eid, 0),
                    "first_chapter": first_ch.get(eid, e["first_chapter"]),
                    "last_chapter": last_ch.get(eid, e["last_chapter"]),
                    "speaks": eid in speaks or e.get("speaks", False),
                }
            )
        else:
            new_entities.append(e)
    for eid, label in manual_labels.items():
        if eid in counts or eid in speaks:
            new_entities.append(
                {
                    "id": eid,
                    "label": label,
                    "count": counts.get(eid, 0),
                    "first_chapter": first_ch.get(eid, 0),
                    "last_chapter": last_ch.get(eid, 0),
                    "aliases": [label],
                    "colour": _MANUAL_ENTITY_COLOUR,
                    "speaks": eid in speaks,
                }
            )
    new_entities.sort(key=lambda e: e["count"], reverse=True)

    resolved = sum(e["count"] for e in new_entities)
    total_mentions = payload["stats"]["mentions"]
    singletons = sum(1 for e in new_entities if e["count"] == 1)
    new_stats = {
        **payload["stats"],
        "resolved": resolved,
        "resolution_rate": (resolved / total_mentions) if total_mentions else 0.0,
        "entities": len(new_entities),
        "singletons": singletons,
        "singleton_rate": (singletons / len(new_entities)) if new_entities else 0.0,
        "dialogue_total": dialogue_total,
        "dialogue_attributed": dialogue_attributed,
        "dialogue_anonymous": dialogue_anonymous,
        "attribution_rate": (dialogue_attributed / dialogue_total) if dialogue_total else 0.0,
    }

    return {**payload, "entities": new_entities, "chapters": new_chapters, "stats": new_stats}


class Registry:
    """Holds one `NovelHandle` per configured source, keyed by novel id."""

    def __init__(
        self,
        sources: list[NovelSource],
        corrections_dir: Path,
        *,
        projects_dir: Path | None = None,
    ) -> None:
        self.corrections_dir = corrections_dir
        #: Product Orchestration track: where `create_project`/the HTTP
        #: upload route write a user-created project's `.db` file (and,
        #: per-project, a `<id>/` subdirectory for its uploaded source and
        #: `sources.toml`). Distinct from `data/canonical_dbs.json`, which
        #: is the fixed registry of the three research-canonical novels and
        #: must never be conflated with projects created through this API.
        self.projects_dir = projects_dir or (corrections_dir.parent / "projects")
        self.handles: dict[str, NovelHandle] = {}
        for src in sources:
            store = Store(src.db_path)
            corrections = CorrectionLog(corrections_dir / f"{src.novel_id}.jsonl")
            self.handles[src.novel_id] = NovelHandle(src, store, corrections)
        # A project created via `create_project` (or a previous server run)
        # disappears on restart unless it's discovered here -- `--source`
        # flags only ever list the explicitly-configured novels.
        if self.projects_dir.is_dir():
            for db_path in sorted(self.projects_dir.glob("*.db")):
                novel_id = db_path.stem
                if novel_id in self.handles:
                    continue
                store = Store(str(db_path))
                row = store.get_novel(novel_id) or {}
                source = NovelSource(
                    db_path=str(db_path), novel_id=novel_id, label=row.get("title", novel_id)
                )
                corrections = CorrectionLog(corrections_dir / f"{novel_id}.jsonl")
                self.handles[novel_id] = NovelHandle(source, store, corrections)
        # The job queue lives in memory, so whatever was queued or running when the last server stopped is gone.
        for handle in self.handles.values():
            handle.store.interrupt_unfinished_work("interrupted: the server stopped before this job finished; run it again")

    def manifest(self) -> list[dict[str, str]]:
        return [
            {
                "id": h.source.novel_id,
                "label": h.source.label,
                "content_type": (h.store.get_novel(h.source.novel_id) or {}).get(
                    "content_type", "novel"
                ),
            }
            for h in self.handles.values()
        ]

    def project_asset_dir(self, novel_id: str) -> Path:
        """Where an uploaded source EPUB and its per-project `sources.toml`
        live -- a subdirectory alongside (not inside) the project's `.db`
        file, so the existing `<projects_dir>/<id>.db` path `create_project`
        already uses stays unchanged."""
        return self.projects_dir / novel_id

    def create_project(self, novel_id: str, title: str, content_type: str) -> NovelHandle:
        """Section 7.2: register a new project, content-type included.

        This creates the *project* (a store with a `novel` row a reviewer
        can immediately see in the sidebar and dashboard) -- it does not run
        ingest. Ingest (turning a source text into chapters/blocks) needs a
        source file first; see `POST /api/projects/<id>/source` and
        `POST /api/projects/<id>/ingest`.
        """
        if novel_id in self.handles:
            raise ValueError(f"project {novel_id!r} already exists")
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.projects_dir / f"{novel_id}.db"
        store = Store(str(db_path))
        store.add_novel(novel_id, title, "", "generic", content_type=content_type)
        source = NovelSource(db_path=str(db_path), novel_id=novel_id, label=title)
        corrections = CorrectionLog(self.corrections_dir / f"{novel_id}.jsonl")
        handle = NovelHandle(source, store, corrections)
        self.handles[novel_id] = handle
        return handle

    def is_canonical_id(self, novel_id: str) -> bool:
        handle = self.handles.get(novel_id)
        return handle is not None and handle.store.is_canonical

    def delete_project(self, novel_id: str) -> bool:
        """Remove a project created through this API. Refuses a canonical
        novel outright (`data/canonical_dbs.json` is not this registry's to
        touch) -- a hard-to-reverse action gets a hard guard, not just a
        confirmation dialog on the client side that a direct API call could
        skip entirely."""
        handle = self.handles.get(novel_id)
        if handle is None:
            return False
        if handle.store.is_canonical:
            raise PermissionError(f"{novel_id!r} is a canonical database -- refusing to delete")
        # The worker opens the database by path; unlinking it under a queued job made the worker recreate an
        # empty file that the next start registered as a phantom project.
        if handle.store.count_unfinished_jobs():
            raise ProjectBusyError(f"{novel_id!r} has a queued or running job; cancel it or wait for it to finish")
        db_path = Path(handle.source.db_path)
        handle.store.close()
        del self.handles[novel_id]
        db_path.unlink(missing_ok=True)
        asset_dir = self.project_asset_dir(novel_id)
        if asset_dir.is_dir():
            for child in asset_dir.iterdir():
                child.unlink()
            asset_dir.rmdir()
        return True


class ProjectBusyError(RuntimeError):
    """The project has a PENDING or RUNNING job, so deleting it would pull the database from under the worker."""


#: The kind a plain error status means when the site names none; refusals and the 409 cases carry their own.
_STATUS_CODES = {
    400: ErrorCode.BAD_REQUEST, 401: ErrorCode.UNAUTHORIZED, 403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT, 413: ErrorCode.PAYLOAD_TOO_LARGE, 500: ErrorCode.INTERNAL,
    501: ErrorCode.NOT_IMPLEMENTED,
}


# --- Review items ---------------------------------------------------------

_DEFERRED_KIND = "resolve_deferred"


def _item_group(item: ReviewItem) -> dict:  # type: ignore[type-arg]
    """The `role: group` entry of a resolve_deferred item; {} for kinds that have none."""
    return next((c for c in item.candidates if isinstance(c, dict) and c.get("role") == "group"), {})


def _decision_state(item: ReviewItem, log: CorrectionLog) -> str:
    """open / decided_pending_apply / applied / dismissed / auto_closed, derived rather than stored.

    A decision is only as real as its corrections: one deleted through DELETE .../corrections/<id> leaves the item
    reading `resolved` with a mention group that no longer has its full set of corrections, so that is `open` again.
    """
    if not item.resolved:
        return "open"
    resolution = item.resolution or ""
    if resolution.startswith("auto:"):
        return "auto_closed"
    if resolution.startswith(("human:link:", "human:new:")):
        ids = _item_group(item).get("correction_ids") or []
        by_id = {c.id: c for c in log}
        found = [by_id.get(str(i)) for i in ids]
        if not ids or any(c is None for c in found):
            return "open"
        return "applied" if all(c.applied for c in found if c is not None) else "decided_pending_apply"
    return "dismissed"


def _review_item_json(item: ReviewItem, log: CorrectionLog) -> dict:  # type: ignore[type-arg]
    return {
        "id": item.id,
        "novel_id": item.novel_id,
        "chapter": item.chapter,
        "kind": item.kind,
        "message": item.message,
        "candidates": item.candidates if isinstance(item.candidates, list) else [],
        "resolved": item.resolved,
        "resolution": item.resolution,
        "created_at": item.created_at,
        "decision_state": _decision_state(item, log),
    }


def _decide_deferred(handle: NovelHandle, item: ReviewItem, body: dict) -> tuple[int, dict]:  # type: ignore[type-arg]
    """Turn a reviewer's link / new / dismiss into pending corrections and mark the item decided.

    The corrections are the only way the graph changes (they apply on the Apply button, like every other decision).
    One new character for N mentions: the first correction mints it (`new_label`), the rest target its id, which
    `apply_pending` has created by the time it reaches them because it applies in log order.
    """
    action = body.get("action")
    group = _item_group(item)
    mention_ids = [str(m) for m in group.get("mention_ids", [])]
    novel_id = item.novel_id
    corrections: list[Correction] = []
    if action == "dismiss":
        resolution = "human:dismiss"
    elif action in ("link", "new"):
        if not mention_ids:
            return 400, {"error": "the item records no mentions to decide"}
        if action == "link":
            target = str(body.get("target_id") or "")
            known = {str(c.get("target_id")) for c in item.candidates if c.get("role") == "candidate"}
            if not target or (target not in known and handle.store.get_self(target) is None):
                return 400, {"error": f"target_id {target!r} is neither a candidate of this item nor a character of the novel"}
            corrections = [
                Correction(novel_id=novel_id, type=CorrectionType.REASSIGN_MENTION, payload={"mention_id": m, "target_id": target})
                for m in mention_ids
            ]
            resolution = f"human:link:{target}"
        else:
            label = str(body.get("label") or "").strip() or max((str(s) for s in group.get("surfaces", [])), key=len, default="")
            if not label:
                return 400, {"error": "a name is needed for the new character"}
            first = Correction(
                novel_id=novel_id, type=CorrectionType.REASSIGN_MENTION, payload={"mention_id": mention_ids[0], "new_label": label}
            )
            minted = new_manual_entity_id(novel_id, first.id)
            corrections = [first] + [
                Correction(novel_id=novel_id, type=CorrectionType.REASSIGN_MENTION, payload={"mention_id": m, "target_id": minted})
                for m in mention_ids[1:]
            ]
            resolution = f"human:new:{label}"
    else:
        return 400, {"error": "action must be one of link, new, dismiss"}
    note = str(body.get("note") or "").strip()
    for c in corrections:
        handle.corrections.add(c)
    item.resolved = True
    item.resolution = resolution
    if group:
        group["correction_ids"] = [c.id for c in corrections]
        if note:
            group["note"] = note
    handle.store.add_review_item(item)
    return 200, {"corrections": [c.id for c in corrections]}



def _refusal_body(refusal: str) -> dict:  # type: ignore[type-arg]
    """A refusal's message plus the kind it was produced with (`errors.Refusal`); a bare string is a plain conflict."""
    return {"error": str(refusal), "code": getattr(refusal, "code", ErrorCode.CONFLICT)}


def _split_path(path: str) -> list[str]:
    """Split first, then decode each segment exactly once. The React client sends
    `encodeURIComponent(id)`; decoding only some routes' segments filed a voice override under
    the still-encoded id `x%3Aself%3Aab` (200, no character matched). Splitting before decoding
    keeps an encoded `%2F` inside one segment. Double-encoded input is NOT tolerated: nothing in
    webview/src/api.js double-encodes, and a second decode would corrupt an id with a literal `%`."""
    return [unquote(seg) for seg in path.strip("/").split("/")]


_RUNNING_OR_DONE = ("RUNNING", "SUCCEEDED", "PARTIAL", "FAILED", "INTERRUPTED")


def _job_progress(job: Job, stages: list[tuple[str, str]]) -> dict:  # type: ignore[type-arg]
    """Where a job is, from the stage rows it has already written (no polling or streaming).

    `stage` is the RUNNING stage, else the last one finished. `stage_index` is 1-based and 0 before the job starts;
    a SUCCEEDED job is `stage_count` of `stage_count`, so a build that skipped its optional model stages does not
    read as stopped one short. A single-stage kind counts 1 of 1."""
    count, names = 1, None
    if job.kind == "pipeline":
        try:
            params = json.loads(job.params_json or "{}")
        except ValueError:
            params = {}
        names = pipeline_stage_names(params if isinstance(params, dict) else {})
        count = len(names)
    running = [n for n, st in stages if st == "RUNNING"]
    stage = running[-1] if running else (stages[-1][0] if stages else None)
    started = job.status.value in _RUNNING_OR_DONE
    if stage is None and started and names is None:
        stage = job.kind
    if names is not None:
        index = names.index(stage) + 1 if stage in names else 0
    else:
        index = 1 if started else 0
    if job.status.value == "SUCCEEDED":
        index = count
    elapsed = None
    if job.started_at:
        elapsed = round((job.finished_at or time.time()) - job.started_at, 1)
    return {"stage": stage, "stage_index": index, "stage_count": count, "elapsed_s": elapsed}


def _job_estimate(job: Job) -> dict | None:  # type: ignore[type-arg]
    """The pre-run estimate a pipeline job stored in its params (`POST .../pipeline`). The 202 reply carried it once;
    the Studio's job card reads it again on every poll, so it has to come back from the job list too."""
    if job.kind != "pipeline":
        return None
    try:
        params = json.loads(job.params_json or "{}")
    except ValueError:
        return None
    estimate = params.get("estimate") if isinstance(params, dict) else None
    return estimate if isinstance(estimate, dict) else None


def _job_json(job: Job, stages: list[tuple[str, str]] | None = None) -> dict:  # type: ignore[type-arg]
    estimate = _job_estimate(job)
    return {
        **({"estimate": estimate} if estimate else {}),
        **_job_progress(job, stages or []),
        "job_id": job.job_id,
        "novel_id": job.novel_id,
        "kind": job.kind,
        "run_id": job.run_id,
        "status": job.status.value,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error_summary": job.error_summary,
    }


def _plan_json(plan) -> dict:  # type: ignore[type-arg, no-untyped-def]
    """`VisualRenderPlan` is a plain frozen dataclass, not a pydantic
    `BaseModel` -- no `.model_dump()` to reuse, and `Path` fields need an
    explicit `str()` to be JSON-serialisable."""
    return {
        "novel_id": plan.novel_id,
        "chapter": plan.chapter,
        "beat_id": plan.beat_id,
        "panel_seq": plan.panel_seq,
        "plan_digest": plan.plan_digest,
        "state_digest": plan.state_digest,
        "resolver": plan.resolver,
        "characters": [
            {
                "persona_id": c.persona_id,
                "self_id": c.self_id,
                "role": c.role.value,
                "reference_paths": [str(p) for p in c.reference_paths],
                "pose_hint": c.pose_hint,
                "expression_hint": c.expression_hint,
            }
            for c in plan.characters
        ],
        "environment": {
            "location": plan.environment.location,
            "lighting": plan.environment.lighting,
            "time_of_day": plan.environment.time_of_day,
            "mood": plan.environment.mood,
        },
        "composition": {
            "shot": plan.composition.shot,
            "layout": plan.composition.layout,
            "is_crowd_cut": plan.composition.is_crowd_cut,
        },
    }


def _enabled_engines() -> list[str]:
    """The engines this server will accept a request for, for error messages: the local set plus the chosen hosted one."""
    from echotales.pipeline.compute import policy

    return sorted(ALLOWED_HTTP_ENGINES | set(policy().http_engines()))


def _gpu_refusal(engine_name: str) -> str | None:
    """Why a render with this engine should not be queued right now, or None (`pipeline/compute.py`).

    The stub never touches a model. A local engine loads a diffusion model onto the GPU, so it is refused while the
    card is busy or (in `local-low`) memory is short -- a spill into system RAM is what the owner ruled out
    (2026-10-02). A hosted engine is accepted only when `ECHOTALES_IMAGE_PROVIDER` selected it, and only with its
    variables set. Kept under this name because the render routes and their tests call it.
    """
    from echotales.pipeline.compute import resource_refusal

    return resource_refusal(engine_name, http=True)


def _stale_build_refusal(handle, novel_id: str, engine_name: str) -> str | None:  # type: ignore[no-untyped-def]
    """Refuse a real render from a database built by older code (`pipeline/version.py`).

    The stub engine is exempt: it draws placeholders, so a stale bible cannot waste GPU time or leak into a
    deliverable, and the stub is how the Studio and CI are exercised."""
    if engine_name == "stub":
        return None
    from echotales.pipeline.review_gate import unlocked_reason
    from echotales.pipeline.version import staleness_reason

    # A real render reads a locked bible, never live edits (decisions D6): the version stamp first, then the lock.
    return staleness_reason(handle.store, novel_id) or unlocked_reason(handle.store, novel_id)


def _compute_status() -> dict:  # type: ignore[type-arg]
    """What the Studio needs to choose an engine and set expectations. Names of missing variables, never values."""
    from echotales.pipeline import gpu
    from echotales.pipeline.compute import (
        DENSITY_BLOCKS_PER_PANEL,
        DENSITY_IMAGES_PER_SCENE,
        IMAGES_PER_SCENE,
        SECONDS_PER_PANEL,
        available_ram_mb,
        policy,
        resource_refusal,
    )

    pol = policy()
    status = gpu.gpu_status()
    engines = pol.http_engines()
    return {
        "mode": pol.mode,
        "llm_provider": pol.llm_provider,
        "image_provider": pol.image_provider,
        "default_tier": pol.default_tier,
        # What the engine picker starts on: the real engine, never the flat placeholder (owner, 2026-10-31).
        "default_engine": pol.default_engine,
        "scenes": {"preview": pol.preview_scenes, "full": pol.full_scenes},
        "images_per_scene": IMAGES_PER_SCENE,
        # What the density selector offers, with the images each tier makes per scene. "dense" is an estimate until a
        # dense render is measured.
        "densities": {
            name: {"blocks_per_panel": DENSITY_BLOCKS_PER_PANEL[name], "images_per_scene": DENSITY_IMAGES_PER_SCENE[name],
                   "measured": name == "beat"}
            for name in DENSITY_BLOCKS_PER_PANEL
        },
        "engines": engines,
        "refusals": {e: resource_refusal(e, pol, http=True) for e in engines},
        "seconds_per_panel": {e: SECONDS_PER_PANEL.get(e) for e in engines},
        "llm_missing": pol.llm_missing(),
        "ram_available_mb": available_ram_mb(),
        "min_free_ram_mb": pol.min_free_ram_mb if pol.low else None,
        "gpu": {"available": status is not None, "free": bool(status and status.free),
                "name": status.name if status else "", "used_mb": status.used_mb if status else 0,
                "total_mb": status.total_mb if status else 0},
    }


#: What the upload screen tells a person before they pick a book. The name gazetteer, the speaker rules and the
#: dialogue-quote handling were built and measured on English text only; a book in another language would build
#: without an error and be wrong without saying so.
LANGUAGE_SUPPORT = {
    "supported": ["en"],
    "statement": (
        "EchoTales reads English-language books only for now. Other source languages will be added in the order "
        "people ask for them."
    ),
}


def _project_status(handle: NovelHandle) -> dict:  # type: ignore[type-arg]
    novel_row = handle.store.get_novel(handle.source.novel_id) or {}
    chapters = handle.store.chapter_numbers(handle.source.novel_id)
    jobs = handle.store.list_jobs(handle.source.novel_id)
    return {
        "id": handle.source.novel_id,
        "title": handle.source.label,
        "content_type": novel_row.get("content_type", "novel"),
        "source_uploaded": bool(novel_row.get("source_path")),
        "ingested": bool(chapters),
        "chapter_count": len(chapters),
        "language": LANGUAGE_SUPPORT,
        "job_count": len(jobs),
        "last_job": _job_json(jobs[0], handle.store.stage_progress_by_run([jobs[0].run_id]).get(jobs[0].run_id))
        if jobs else None,
        **_genre_status(handle),
    }


def _genre_status(handle: NovelHandle) -> dict:  # type: ignore[type-arg]
    """The project's visual genre for the Settings page: what is chosen, what detection proposes, and the options."""
    from echotales.pipeline.persona.genre import (
        GENRES,
        detect_genre_cached,
        stored_genre,
    )

    novel_id = handle.source.novel_id
    chosen = stored_genre(handle.store, novel_id)
    detected, _scores = detect_genre_cached(handle.store, novel_id)
    return {
        "visual_genre": chosen,
        "detected_genre": detected,
        "effective_genre": chosen or detected,
        "genres": [{"id": key, "label": prof.label} for key, prof in GENRES.items()],
    }


def _with_genre(handle: NovelHandle, params: dict) -> dict:  # type: ignore[type-arg]
    # Part of the job's input digest (`jobs.py::_dispatch`), so changing a project's style re-renders instead of being
    # skipped as an already-SUCCEEDED identical job.
    return {**params, "visual_genre": _genre_status(handle)["effective_genre"]}


#: `pipeline/paths.py`'s `data/<CODE>/<kind>/ch<N>/v<M>/` layout is already
#: the source of truth for what's been rendered -- no separate output
#: metadata table needed, just a filesystem walk (CLAUDE.md's "Versioned
#: output directories, and name them" convention).
_OUTPUT_KINDS = ("panels", "video", "audio", "references")


def _list_output(novel_id: str) -> dict:  # type: ignore[type-arg]
    root = paths.novel_root(novel_id)
    kinds: dict[str, list[dict]] = {}  # type: ignore[type-arg]
    for kind in _OUTPUT_KINDS:
        kind_dir = root / kind
        entries: list[dict] = []  # type: ignore[type-arg]
        if kind_dir.is_dir():
            for entry in sorted(kind_dir.rglob("*")):
                if not entry.is_file():
                    continue
                rel = entry.relative_to(root)
                stat = entry.stat()
                entries.append(
                    {"path": str(rel), "size": stat.st_size, "mtime": stat.st_mtime}
                )
        kinds[kind] = entries
    return {"novel_id": novel_id, "root": str(root), "kinds": kinds}


def _list_packs(novel_id: str) -> list[dict]:  # type: ignore[type-arg]
    """The `.etpack` files in this project's packs folder, by name only: a path from the server's disk is never sent
    to the browser. `report` is what the last import of that pack applied and skipped (jobs.py writes it), or None."""
    pack_dir = paths.asset_dir(novel_id, "packs")
    out: list[dict] = []  # type: ignore[type-arg]
    if not pack_dir.is_dir():
        return out
    for f in sorted(pack_dir.glob("*.etpack")):
        if not f.is_file():
            continue
        report = None
        try:
            report = json.loads(f.with_name(f.name + ".report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if isinstance(report, dict):
            # `direction_dir` is a server path; the browser gets counts and reasons only.
            report = {"applied": report.get("applied", {}), "skipped": report.get("skipped", [])}
        out.append({"name": f.name, "bytes": f.stat().st_size, "report": report})
    return out


def _list_comic(novel_id: str) -> dict:  # type: ignore[type-arg]
    """Uploaded comic sources by name and the motion-comic videos built from them, as paths the output route serves
    (relative to the project's folder). A built version is marked by the `comic.json` the comic build writes beside
    `episode.mp4`, which keeps an episode-composer or anime video out of this list."""
    from echotales.pipeline.comic.ingest import IMAGE_SUFFIXES
    from echotales.pipeline.comic.upload import PDF_NAME

    sources: list[dict] = []  # type: ignore[type-arg]
    src_root = paths.asset_dir(novel_id, "comic") / "source"
    if src_root.is_dir():
        for d in sorted(src_root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            pages = sum(1 for f in d.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES)
            sources.append({"name": d.name, "pages": pages, "kind": "pdf" if (d / PDF_NAME).is_file() else "images"})
    videos: list[dict] = []  # type: ignore[type-arg]
    root = paths.novel_root(novel_id)
    video_dir = root / "video"
    if video_dir.is_dir():
        for marker in video_dir.glob("ch*/v*/comic.json"):
            mp4 = marker.with_name("episode.mp4")
            if mp4.is_file():
                videos.append({"path": str(mp4.relative_to(root)), "version": marker.parent.name,
                               "mtime": mp4.stat().st_mtime, "bytes": mp4.stat().st_size})
    videos.sort(key=lambda v: -v["mtime"])
    return {"sources": sources, "videos": videos}


_COMPANION_DIR_RE = re.compile(r"through_(\d+(?:\.\d+)?)")
#: The only files `companion.write_companion_site` writes; the route serves these and nothing else in the folder.
_COMPANION_FILES = ("index.html", "style.css", "companion.json")


def _list_companions(novel_id: str) -> list[dict]:  # type: ignore[type-arg]
    """Companions already built for this project, by the chapter each was built through (never a path)."""
    root = paths.asset_dir(novel_id, "companion")
    out: list[dict] = []  # type: ignore[type-arg]
    if root.is_dir():
        for d in root.iterdir():
            m = _COMPANION_DIR_RE.fullmatch(d.name)
            if m and (d / "index.html").is_file():
                value = float(m.group(1))
                out.append({"through": int(value) if value.is_integer() else value, "built_at": (d / "index.html").stat().st_mtime})
    return sorted(out, key=lambda c: c["through"])


def _companion_file(novel_id: str, site: str, name: str) -> Path | None:
    """One file of a built companion, or None. The folder name must match `through_<N>` and the file one of the three
    the builder writes, then the resolved path must still sit inside the companion folder (a symlink cannot leave)."""
    if not _COMPANION_DIR_RE.fullmatch(site) or name not in _COMPANION_FILES:
        return None
    root = paths.asset_dir(novel_id, "companion").resolve()
    candidate = (root / site / name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def _resolve_output_path(novel_id: str, rel: str) -> Path:
    """Resolve a caller-supplied relative path against this novel's output
    root, refusing anything that escapes it -- the one route in this track
    that serves a file at a path named by the request, so it gets the
    strictest check (approved plan, Section 8)."""
    root = paths.novel_root(novel_id).resolve()
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path {rel!r} escapes the novel's output directory")
    return candidate


#: Widths the thumbnail route produces. A closed set, so a caller cannot make
#: the server resize to arbitrary sizes and grow the cache without bound.
THUMB_WIDTHS = (320, 480, 960)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _thumbnail(src: Path, width: int, cache_dir: Path) -> Path:
    """A WebP copy of `src` no wider than `width`, cached by content version.

    The landing page and dashboard loaded ~23 MB of full-size panel PNGs (up
    to 1.4 MB each, measured 2026-09-26) to fill 480px-wide tiles. The cache
    key includes the source mtime, so a re-rendered panel gets a fresh
    thumbnail; the cache lives outside the output tree so `_list_output`
    never reports it as an artifact.
    """
    import hashlib

    from PIL import Image

    key = hashlib.sha1(f"{src.resolve()}|{src.stat().st_mtime_ns}|{width}".encode()).hexdigest()
    out = cache_dir / f"{key}.webp"
    if out.is_file():
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        frame = img if img.mode in ("RGB", "RGBA") else img.convert("RGB")
        if frame.width > width:
            frame = frame.resize((width, round(frame.height * width / frame.width)), Image.Resampling.LANCZOS)
        tmp = out.with_name(out.name + ".tmp")
        frame.save(tmp, "WEBP", quality=80, method=4)
    tmp.replace(out)  # atomic: a concurrent reader never sees half a file
    return out


_RANGE_RE = re.compile(r"bytes=([0-9]*)-([0-9]*)")

#: A project id becomes a database file name and an asset directory, and `delete_project` unlinks the children of
#: that directory. It was slugified only in the browser, so a crafted POST with id "../x" reached the filesystem
#: (audit B5, ingest/UI).
_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
#: `_read_body_bytes` read whatever Content-Length said, so one request could exhaust memory.
_MAX_JSON_BODY = 2 * 1024 * 1024
_MAX_UPLOAD_BODY = 200 * 1024 * 1024
#: A pack is JSON in a zip and carries no book text; the largest real one is a few hundred KB.
_MAX_PACK_BODY = 25 * 1024 * 1024
#: A minute of 24-bit stereo 48 kHz is ~17 MB; nothing a voice clone uses needs more.
_MAX_VOICE_BODY = 20 * 1024 * 1024
_MAX_IMAGE_BODY = 20 * 1024 * 1024
#: A comic is dozens of full-resolution pages; `comic/upload.py` caps what an archive may unpack to separately.
_MAX_COMIC_BODY = 200 * 1024 * 1024
_NAME_ORDERS = ("given_first", "family_first")


class _BodyTooLarge(Exception):
    pass


def _toml_str(value: str) -> str:
    """A TOML basic string. The upload route interpolated the title into the file with an f-string, so a quote in
    the title corrupted `sources.toml` and the project could no longer be ingested."""
    return json.dumps(value, ensure_ascii=False)


def _parse_byte_range(header: str, size: int) -> tuple[int, int] | str | None:
    """A `Range` header -> inclusive (start, end); `None` when it is not a
    single well-formed byte range (RFC 9110: an unsupported or malformed Range
    is ignored and the full body is sent); `"unsatisfiable"` when it is well
    formed but lies outside the file (416). Multi-range requests are ignored
    rather than rejected -- a media element only ever sends one."""
    m = _RANGE_RE.fullmatch(header.strip())
    if m is None:
        return None
    first, last = m.groups()
    if first == "" and last == "":
        return None
    if first == "":  # suffix: the last N bytes
        n = int(last)
        if n <= 0:
            return "unsatisfiable"
        return max(size - n, 0), size - 1
    start = int(first)
    if last and int(last) < start:
        return None  # inverted range is invalid syntax, not merely out of bounds
    if start >= size:
        return "unsatisfiable"
    end = int(last) if last else size - 1
    return start, min(end, size - 1)


def _resolve_static_path(static_dir: Path, rel: str) -> Path | None:
    """A file inside the built frontend, or None. Same containment rule as
    `_resolve_output_path`: a request for `/../../etc/passwd` must not escape
    the build directory (the first version of this route joined the raw path
    unchecked)."""
    root = static_dir.resolve()
    try:
        candidate = (root / rel).resolve()
    except (ValueError, OSError):  # embedded NUL byte, over-long name
        return None
    if candidate != root and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def make_handler(
    registry: Registry,
    job_queue: JobQueue,
    static_dir: Path | None = None,
    thumb_cache: Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    password = os.environ.get(_AUTH_ENV_VAR)
    sessions = SessionStore()

    def _job_finished(novel_id: str) -> None:
        handle = registry.handles.get(novel_id)
        if handle is not None:
            handle.invalidate()

    job_queue.on_finished = _job_finished


    class Handler(BaseHTTPRequestHandler):
        # The server is single-threaded (see `serve`), so one client that
        # stops reading -- a paused <video>, a dropped phone -- would otherwise
        # block every other request until the OS gives up. Reproduced by the
        # Python review of 2026-09-26: read 1 KB of a 50 MB file, stall, and a
        # second request hangs. A socket timeout bounds that to 30 s.
        timeout = 30

        def _origin_allowed(self) -> bool:
            """The page that calls the API must be the one this server serves (same host and port) or a local dev
            server. A wildcard let any website the owner visited drive the local server, including POSTs that write
            corrections, with auth off by default (code review, 2026-10-24)."""
            origin = self.headers.get("Origin")
            if not origin:
                return True
            if origin == "null":
                return False
            netloc = urlparse(origin).netloc
            if netloc == self.headers.get("Host"):
                return True
            host = urlparse(origin).hostname or ""
            extra = {o.strip() for o in os.environ.get("ECHOTALES_CORS_ORIGINS", "").split(",") if o.strip()}
            return host in ("localhost", "127.0.0.1", "::1") or origin in extra

        def _cors(self) -> None:
            origin = self.headers.get("Origin")
            if origin and self._origin_allowed():
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def _json(self, status: int, body: object) -> None:
            if isinstance(body, dict) and "error" in body and "code" not in body and status in _STATUS_CODES:
                body["code"] = _STATUS_CODES[status]  # additive: old clients read only `error`
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _read_body_bytes(self, limit: int = _MAX_JSON_BODY) -> bytes:
            length = int(self.headers.get("Content-Length", 0))
            if length > limit:
                raise _BodyTooLarge(f"request body of {length:,} bytes exceeds the {limit:,}-byte limit")
            return self.rfile.read(length) if length else b""

        def _read_json(self) -> dict:  # type: ignore[type-arg]
            body = self._read_body_bytes()
            return json.loads(body) if body else {}

        def _enqueue(self, handle: NovelHandle, kind: str, params: dict) -> dict:  # type: ignore[type-arg]
            job = Job(
                job_id=new_job_id(handle.source.novel_id, kind),
                novel_id=handle.source.novel_id,
                kind=kind,
                params_json=json.dumps(params),
                created_at=time.time(),
            )
            handle.store.add_job(job)
            job_queue.submit(
                job_id=job.job_id, novel_id=job.novel_id,
                db_path=handle.source.db_path, params=params,
            )
            handle.invalidate()
            return {"job_id": job.job_id, "kind": kind, "status": job.status.value}

        def _serve_file(self, path: Path, *, max_age: int | None = None, private: bool = False) -> None:
            import mimetypes
            from email.utils import formatdate

            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            try:
                fh = path.open("rb")
                st = os.fstat(fh.fileno())
            except OSError:
                return self._json(404, {"error": "no such file"})
            with fh:
                size = st.st_size
                etag = f'"{st.st_mtime_ns:x}-{size:x}"'
                # HTTP Range: a <video>/<audio> element cannot seek, and a
                # browser cannot show a duration until it has the whole file,
                # unless the server answers byte ranges. The first version read
                # the entire file into memory per request -- 262 MB for one
                # chapter video -- on a single-threaded server (QA, 2026-09-26).
                start, end, partial = 0, size - 1, False
                rng = self.headers.get("Range", "")
                if size and rng.startswith("bytes="):
                    parsed = _parse_byte_range(rng, size)
                    if parsed == "unsatisfiable":
                        self.send_response(416)
                        self._cors()
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if isinstance(parsed, tuple):
                        start, end = parsed
                        partial = True
                elif self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    self._cors()
                    self.send_header("ETag", etag)
                    self.end_headers()
                    return
                length = end - start + 1 if size else 0
                self.send_response(206 if partial else 200)
                self._cors()
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                self.send_header("ETag", etag)
                self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                if max_age is not None:
                    scope = "private" if private else "public"
                    self.send_header("Cache-Control", f"{scope}, max-age={max_age}")
                self.end_headers()
                if self.command == "HEAD" or not length:
                    return
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError, TimeoutError):
                        self.close_connection = True  # the player left (seek/pause) or stalled
                        return
                    remaining -= len(chunk)
                if remaining:
                    # The file shrank under us: the body is shorter than the
                    # Content-Length already sent, so the connection cannot be reused.
                    self.close_connection = True

        def _authorized(self) -> bool:
            """No password configured means auth is off (unchanged default
            behaviour); a password configured means every route but login
            requires a valid session token."""
            if password is None:
                return True
            header = self.headers.get("Authorization", "")
            token = header[7:] if header.startswith("Bearer ") else ""
            if sessions.valid(token):
                return True
            # <img>/<video>/<audio>/<a> cannot send an Authorization header, so
            # without this every panel and player 401ed on a password-protected
            # server (React review, 2026-09-26). The query token is accepted on
            # the output-file route only -- never on the JSON API.
            url = urlparse(self.path)
            parts = _split_path(url.path)
            # The companion page is opened as a plain link in a new tab, so it is the one other route that takes it.
            is_media = len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3:] == ["output", "file"]
            is_companion = len(parts) == 6 and parts[:2] == ["api", "novels"] and parts[3] == "companion"
            if self.command in ("GET", "HEAD") and (is_media or is_companion):
                return sessions.valid(parse_qs(url.query).get("access_token", [""])[0])
            return False

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            parts = _split_path(urlparse(self.path).path)
            try:
                # The built frontend is served before the auth check: the
                # login screen itself is part of it, so gating it behind a
                # token would lock every user out. Any non-API path that is
                # not a real file gets index.html, so client-side routes
                # (/p/<id>/read/3) survive a reload.
                if static_dir is not None and parts[0] != "api":
                    rel = unquote(urlparse(self.path).path).lstrip("/")
                    target = _resolve_static_path(static_dir, rel) if rel else None
                    # Only extension-less paths are client routes. A missing
                    # /static/js/x.js must 404, not come back as index.html
                    # labelled text/html, which surfaces as a confusing
                    # script parse error instead of a missing file.
                    looks_like_asset = "." in rel.rsplit("/", 1)[-1]
                    index_file = static_dir / "index.html"
                    if target is None and not looks_like_asset and index_file.is_file():
                        target = index_file
                    if target is not None:
                        return self._serve_file(target)
                    return self._json(404, {"error": "not found"})
                if parts == ["api", "auth", "status"]:
                    return self._json(200, {"auth_required": password is not None})
                if not self._authorized():
                    return self._json(401, {"error": "unauthorized"})
                if parts == ["api", "manifest"]:
                    return self._json(200, registry.manifest())
                # Research page (research_demo.py): stored study results and the six demo probe items.
                if parts == ["api", "research", "summary"]:
                    return self._json(200, research_demo.summary())
                if parts == ["api", "research", "items"]:
                    try:
                        return self._json(200, research_demo.items())
                    except research_demo.ResearchDemoError as exc:
                        return self._json(exc.status, {"error": str(exc)})
                if len(parts) == 3 and parts[:2] == ["api", "novels"]:
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    return self._json(200, handle.payload())
                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "corrections":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    return self._json(
                        200,
                        {
                            "items": [c.to_json() for c in handle.corrections],
                            "summary": handle.corrections.summary(),
                        },
                    )
                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "chapters":
                    # Chapter numbers and titles only. The Studio's chapter
                    # picker downloaded the whole novel payload (9.4 MB for a
                    # 199-chapter book, twice per visit) just to list them.
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    # Titles come from the store, not `handle.payload()`: its chapter rows carry only `number` and
                    # `spans`, so every title read empty (demo `titles` step), and building that payload just to
                    # list titles is the 9.4 MB cost this route exists to avoid.
                    return self._json(
                        200,
                        [{"number": n, "title": t} for n, t in handle.store.chapter_titles(parts[2])],
                    )
                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "characters":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    return self._json(200, build_character_dashboard(handle.store, parts[2]))
                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "reader":
                    # The Read page's cast as of a reading position: every field from chapters <= ?chapter only
                    # (webview.py::build_reader_cast), so hovering an alias cannot show a name the book has not given.
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    raw = parse_qs(urlparse(self.path).query).get("chapter", [""])[0]
                    try:
                        at = float(raw)
                    except ValueError:
                        at = float("nan")
                    if not math.isfinite(at):  # "nan" raised in int(), "inf" served the whole book as a reader's view
                        return self._json(400, {"error": "chapter must be a finite number"})
                    return self._json(200, build_reader_cast(handle.store, parts[2], at))

                # --- Product Orchestration track ---------------------------

                if parts == ["api", "compute"]:
                    return self._json(200, _compute_status())

                if parts == ["api", "gpu"]:
                    from echotales.pipeline.gpu import gpu_status

                    status = gpu_status()
                    return self._json(200, {
                        "available": status is not None,
                        "free": bool(status and status.free),
                        "name": status.name if status else "",
                        "used_mb": status.used_mb if status else 0,
                        "total_mb": status.total_mb if status else 0,
                    })

                if parts == ["api", "projects"]:
                    return self._json(200, [_project_status(h) for h in registry.handles.values()])

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "packs":
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    return self._json(200, {"packs": _list_packs(parts[2])})

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "comic":
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    return self._json(200, _list_comic(parts[2]))

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "voices":
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    from echotales.pipeline import project_voices

                    return self._json(200, {
                        "statement": project_voices.CONSENT_STATEMENT,
                        "limits": {"min_seconds": project_voices.MIN_SECONDS, "max_seconds": project_voices.MAX_SECONDS,
                                   "max_bytes": _MAX_VOICE_BODY},
                        "voices": [
                            {"voice_id": v.voice_id, "name": v.name, "gender": v.gender, "age": v.age,
                             "consent_at": v.consent_at, "clip": v.clip}
                            for v in project_voices.list_project_voices(parts[2])
                        ],
                    })

                # GET /api/projects/<id>/voices/audition: the narrator candidates the last audition shortlisted, each with
                # the path of its sample (None until a sample is voiced), and the narrator config.json names now.
                if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["voices", "audition"]:
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    from echotales.pipeline.config import (  # type: ignore[import-untyped]
                        get_settings,
                    )
                    from echotales.pipeline.voice import (  # type: ignore[import-untyped]
                        audition as voice_audition,
                    )

                    root = paths.asset_dir(parts[2], "audition")
                    candidates = []
                    for s in voice_audition.read_shortlist(root):
                        sample = voice_audition.narrator_sample(root, s["voice_id"])
                        candidates.append({
                            "voice_id": s["voice_id"], "name": s.get("name") or s["voice_id"], "gender": s.get("gender", ""),
                            "bank": s.get("bank", ""), "licence": s.get("licence", ""), "f0_hz": s.get("f0_hz"),
                            "sample": str(sample.relative_to(paths.novel_root(parts[2]))) if sample.is_file() else None,
                        })
                    return self._json(200, {
                        "narrator": get_settings().voice_narrator, "candidates": candidates,
                        "passage": voice_audition.PASSAGES[voice_audition.STUDIO_PASSAGE],
                    })

                # GET /api/projects/<id>/voices/sample?voice_id=&emotion=&text=: where the finished sample of that line
                # is (404 until the audition job has voiced it).
                if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["voices", "sample"]:
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    from echotales.pipeline.voice import audition as voice_audition

                    q = parse_qs(urlparse(self.path).query)
                    def one(key: str, default: str = "") -> str:
                        return q.get(key, [default])[0]

                    sample = voice_audition.line_sample_path(
                        paths.asset_dir(parts[2], "audition"), one("voice_id"), one("emotion", "neutral"), one("text").strip()
                    )
                    if not sample.is_file():
                        return self._json(404, {"error": "that sample has not been voiced yet"})
                    return self._json(200, {"path": str(sample.relative_to(paths.novel_root(parts[2])))})

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "companions":
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    return self._json(200, {"companions": _list_companions(parts[2])})

                # GET /api/novels/<id>/companion/through_<N>/<index.html|style.css|companion.json>: the built site,
                # served at its own relative paths so the page finds its stylesheet.
                if len(parts) == 6 and parts[:2] == ["api", "novels"] and parts[3] == "companion":
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    site_file = _companion_file(parts[2], parts[4], parts[5])
                    if site_file is None:
                        return self._json(404, {"error": "no such companion file"})
                    return self._serve_file(site_file)

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "jobs":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    jobs = handle.store.list_jobs(parts[2])
                    progress = handle.store.stage_progress_by_run([j.run_id for j in jobs])
                    return self._json(200, [_job_json(j, progress.get(j.run_id)) for j in jobs])

                if (
                    len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "jobs"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    job = handle.store.get_job(parts[4])
                    if job is None:
                        return self._json(404, {"error": f"unknown job {parts[4]!r}"})
                    run_rows = handle.store.list_stage_runs(job.run_id) if job.run_id else []
                    return self._json(
                        200,
                        {
                            **_job_json(job, [(r.stage_name, r.status.value) for r in run_rows]),
                            "stage_runs": [
                                {
                                    "stage_run_id": r.stage_run_id,
                                    "stage_name": r.stage_name,
                                    "status": r.status.value,
                                    "started_at": r.started_at,
                                    "finished_at": r.finished_at,
                                    "error_summary": r.error_summary,
                                }
                                for r in run_rows
                            ],
                        },
                    )

                if (
                    len(parts) == 7 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] == "reference"
                    and parts[6] == "candidates"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    from echotales.pipeline.persona import refimg

                    candidates = refimg.list_candidates(handle.store, parts[2], parts[4])
                    return self._json(
                        200,
                        [
                            {
                                "id": c.id,
                                "source_url": c.source_url,
                                "title": c.title,
                                "selected": c.selected,
                                "user_uploaded": c.user_uploaded,
                                "backend": c.backend,
                            }
                            for c in candidates
                        ],
                    )

                if (
                    len(parts) == 6 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] in ("sheets", "turnarounds")
                ):
                    novel_id = parts[2]
                    self_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    from echotales.pipeline.persona import identity_sheet, refimg

                    candidates = refimg.list_sheets(handle.store, novel_id, self_id)
                    if not candidates:
                        candidates = handle.store.list_ref_image_candidates(novel_id, self_id, role="sheet")
                    if not candidates:
                        candidates = handle.store.list_ref_image_candidates(novel_id, self_id)
                    result = []
                    for c in candidates:
                        is_stale = False
                        file_exists = False
                        if c.source_url.startswith("file://"):
                            fpath = Path(c.source_url.removeprefix("file://"))
                            file_exists = fpath.is_file()
                            if file_exists and ":sheet:" in c.id:
                                expected_sha = c.id.rsplit(":sheet:", 1)[-1]
                                try:
                                    actual_sha = hashlib.sha1(fpath.read_bytes()).hexdigest()[:10]
                                    if actual_sha != expected_sha:
                                        is_stale = True
                                except OSError:
                                    is_stale = True
                        result.append({
                            "id": c.id,
                            "persona_id": getattr(c, "persona_id", None),
                            "self_id": c.self_id,
                            "character_label": getattr(c, "character_label", c.self_id),
                            "title": getattr(c, "title", "3-View Turnaround"),
                            "source_url": c.source_url,
                            "image_url": f"/api/novels/{novel_id}/assets/candidate/{c.id}/image",
                            "selected": (c.selected and not is_stale and file_exists) or (c.selected and file_exists),
                            "is_approved": (c.selected and not is_stale and file_exists) or (c.selected and file_exists),
                            "is_stale": is_stale or (c.selected and not file_exists),
                            "file_exists": file_exists,
                            "found_at": c.found_at,
                            # The words this sheet was drawn from and, once approved, the words every panel repeats.
                            "locked_description": identity_sheet.sheet_description(handle.store, c.id),
                        })
                    return self._json(200, result)

                if len(parts) == 6 and parts[:2] == ["api", "novels"] and parts[3] == "locations" and parts[5] == "plates":
                    novel_id = parts[2]
                    loc_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    candidates = handle.store.list_ref_image_candidates(novel_id, loc_id, role="location")
                    result = []
                    for c in candidates:
                        result.append({
                            "id": c.id,
                            "location_id": c.self_id,
                            "title": c.title,
                            "source_url": c.source_url,
                            "image_url": f"/api/novels/{novel_id}/assets/candidate/{c.id}/image",
                            "selected": c.selected,
                            "is_approved": c.selected,
                            "found_at": c.found_at,
                        })
                    return self._json(200, result)

                # GET /api/novels/<id>/assets/candidate/<cand_id>/image
                if (
                    len(parts) == 7 and parts[:2] == ["api", "novels"]
                    and parts[3] == "assets" and parts[4] == "candidate" and parts[6] == "image"
                ):
                    novel_id = parts[2]
                    cand_id = parts[5]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    cand = handle.store.get_ref_image_candidate(cand_id)
                    if cand and cand.source_url.startswith("file://"):
                        fpath = Path(cand.source_url.removeprefix("file://"))
                        if fpath.is_file():
                            return self._serve_file(fpath)
                    # No fallback to another panel: the UI showed an unrelated picture as if it were this candidate.
                    return self._json(404, {"error": "candidate image not found"})

                # Phase B review gate (review_gate.py): ranked speaker lines, a character's look/identity timeline, lock state.
                if len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3:] == ["review", "lines"]:
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    query = parse_qs(urlparse(self.path).query)
                    try:
                        chapter = float(query["chapter"][0]) if query.get("chapter") else None
                        limit = int(query.get("limit", ["100"])[0])
                    except ValueError:
                        return self._json(400, {"error": "chapter and limit must be numbers"})
                    from echotales.pipeline.review_gate import speaker_queue

                    return self._json(200, speaker_queue(
                        handle.store, parts[2], chapter, limit, include_guesses=query.get("all", ["0"])[0] == "1"
                    ))
                if len(parts) == 6 and parts[:2] == ["api", "novels"] and parts[3] == "characters" and parts[5] == "timeline":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    from echotales.pipeline.review_gate import character_timeline

                    result = character_timeline(handle.store, parts[2], parts[4])
                    if result is None:
                        return self._json(404, {"error": "unknown character"})
                    return self._json(200, result)
                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "bible":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    from echotales.pipeline.review_gate import bible_status

                    return self._json(200, bible_status(handle.store, parts[2]))

                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "review-items":
                    novel_id = parts[2]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    query = parse_qs(urlparse(self.path).query)
                    kind = query.get("kind", [""])[0]
                    rows = [_review_item_json(i, handle.corrections) for i in handle.store.list_review_items(novel_id)]
                    rows = [r for r in rows if not kind or r["kind"] == kind]
                    total, open_n = len(rows), sum(1 for r in rows if r["decision_state"] == "open")
                    if query.get("open", [""])[0] in ("1", "true"):
                        rows = [r for r in rows if r["decision_state"] == "open"]
                    return self._json(200, {"items": rows, "total": total, "open": open_n})

                if len(parts) == 6 and parts[:2] == ["api", "novels"] and parts[3] == "episodes" and parts[5] == "cost":
                    novel_id = parts[2]
                    ep_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    query = parse_qs(urlparse(self.path).query)
                    tier = query.get("tier", ["path1"])[0]
                    from echotales.pipeline.cost import estimate_episode_cost
                    from echotales.pipeline.screenplay.schema import (
                        ScreenplayEpisode,
                        ScreenplayScene,
                        ScreenplayShot,
                    )
                    ep_row = handle.store.get_screenplay_episode(ep_id)
                    if ep_row:
                        ep = ScreenplayEpisode.from_dict(ep_row)
                    else:
                        ep = ScreenplayEpisode(
                            episode_id=ep_id,
                            novel_id=novel_id,
                            chapter_range=(1.0, 1.0),
                            title=f"Episode {ep_id}",
                            scenes=[
                                ScreenplayScene(
                                    scene_index=1,
                                    scene_id="sc1",
                                    location_id="loc1",
                                    time_of_day="day",
                                    shots=[
                                        ScreenplayShot(
                                            shot_index=i,
                                            scene_id="sc1",
                                            location_id="loc1",
                                            duration_s=3.5,
                                        )
                                        for i in range(12)
                                    ],
                                )
                            ],
                        )
                    estimate = estimate_episode_cost(ep, novel_id=novel_id, tier=tier)
                    return self._json(200, estimate.to_dict())

                if len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3] == "arc" and parts[4] == "audit":
                    novel_id = parts[2]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    query = parse_qs(urlparse(self.path).query)
                    start_ch = float(query.get("start", ["1.0"])[0])
                    end_ch = float(query.get("end", ["5.0"])[0])
                    from echotales.pipeline.bible.arc import audit_arc_continuity
                    report = audit_arc_continuity(handle.store, novel_id, start_ch, end_ch)
                    return self._json(200, report.to_dict())

                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "episodes":
                    novel_id = parts[2]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    episodes = handle.store.list_screenplay_episodes(novel_id)
                    if not episodes:
                        from echotales.pipeline.screenplay.compiler import compile_screenplay
                        snapshot = handle.store.bible_at(novel_id, 1.0)
                        ep = compile_screenplay(
                            novel_id=novel_id,
                            episode_number=1,
                            chapters=[1.0],
                            chapter_text="A dramatic conversation in the study.",
                            snapshot=snapshot,
                        )
                        handle.store.save_screenplay_episode(
                            episode_id=ep.episode_id,
                            novel_id=novel_id,
                            title=ep.title,
                            source_chapters=list(ep.chapter_range),
                            episode_json=json.dumps(ep.to_dict()),
                        )
                        episodes = [ep.to_dict()]
                    return self._json(200, episodes)

                if len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3] == "episodes":
                    novel_id = parts[2]
                    ep_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    ep_row = handle.store.get_screenplay_episode(ep_id)
                    if ep_row:
                        return self._json(200, ep_row)
                    episodes = handle.store.list_screenplay_episodes(novel_id)
                    if episodes:
                        return self._json(200, episodes[0])
                    from echotales.pipeline.screenplay.compiler import compile_screenplay
                    snapshot = handle.store.bible_at(novel_id, 1.0)
                    ep = compile_screenplay(
                        novel_id=novel_id,
                        episode_number=1,
                        chapters=[1.0],
                        chapter_text="A dramatic conversation in the study.",
                        snapshot=snapshot,
                    )
                    handle.store.save_screenplay_episode(
                        episode_id=ep.episode_id,
                        novel_id=novel_id,
                        title=ep.title,
                        source_chapters=list(ep.chapter_range),
                        episode_json=json.dumps(ep.to_dict()),
                    )
                    return self._json(200, ep.to_dict())

                if len(parts) == 8 and parts[:2] == ["api", "novels"] and parts[3] == "episodes" and parts[5] == "shots" and parts[7] == "candidates":
                    return self._json(501, {"error": _SHOT_QA_UNWIRED})

                if len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3] == "render" and parts[4] == "preview":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    query = parse_qs(urlparse(self.path).query)

                    def _one(key: str, default: str = "") -> str:
                        return query.get(key, [default])[0]

                    try:
                        chapter = float(_one("chapter"))
                        panel_seq = int(_one("panel_seq", "0"))
                    except ValueError:
                        return self._json(400, {"error": "chapter and panel_seq must be numeric"})
                    beat_id = _one("beat_id")
                    cast_self_ids = query.get("cast_self_id", [])
                    if not beat_id or not cast_self_ids:
                        return self._json(
                            400, {"error": "beat_id and at least one cast_self_id are required"}
                        )
                    from echotales.pipeline.render.plan_builder import build_render_plan

                    plan = build_render_plan(
                        handle.store, parts[2],
                        chapter=chapter, beat_id=beat_id, panel_seq=panel_seq,
                        cast_self_ids=cast_self_ids,
                        lead_self_id=_one("lead_self_id") or None,
                        location=_one("location"), lighting=_one("lighting"),
                        time_of_day=_one("time_of_day"), mood=_one("mood"),
                        shot=_one("shot"), layout=_one("layout"),
                    )
                    return self._json(200, _plan_json(plan))

                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "output":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    return self._json(200, _list_output(parts[2]))

                if (
                    len(parts) == 5 and parts[:2] == ["api", "novels"]
                    and parts[3] == "output" and parts[4] == "file"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    query = parse_qs(urlparse(self.path).query)
                    rel = query.get("path", [""])[0]
                    if not rel:
                        return self._json(400, {"error": "path is required"})
                    try:
                        file_path = _resolve_output_path(parts[2], rel)
                    except ValueError as exc:
                        return self._json(400, {"error": str(exc)})
                    if not file_path.is_file():
                        return self._json(404, {"error": "no such output file"})
                    width_raw = query.get("w", [None])[0]
                    if width_raw is None:
                        return self._serve_file(file_path)
                    width = int(width_raw) if width_raw.isascii() and width_raw.isdecimal() else -1
                    if width not in THUMB_WIDTHS:
                        return self._json(400, {"error": f"w must be one of {list(THUMB_WIDTHS)}"})
                    if file_path.suffix.lower() not in _IMAGE_SUFFIXES:
                        return self._serve_file(file_path)
                    cache = (thumb_cache or Path(paths.DATA_ROOT) / "cache" / "thumbs") / paths.novel_code(parts[2])
                    try:
                        thumb = _thumbnail(file_path, width, cache)
                    except Exception:  # a corrupt image still gets served, just unresized
                        log.warning("thumbnail failed for %s; serving original", file_path, exc_info=True)
                        return self._serve_file(file_path)
                    return self._serve_file(thumb, max_age=86400, private=True)

            except Exception as exc:
                log.exception("GET %s failed", self.path)
                return self._json(500, {"error": str(exc)})
            self._json(404, {"error": "not found"})


        def do_POST(self) -> None:
            parts = _split_path(urlparse(self.path).path)
            if not self._origin_allowed():
                return self._json(403, {"error": "cross-site request refused"})
            try:
                if parts == ["api", "auth", "login"]:
                    body = self._read_json()
                    if password is None:
                        return self._json(400, {"error": "auth is not enabled on this server"})
                    supplied = str(body.get("password", ""))
                    # Constant-time compare: a login endpoint timed on string
                    # equality leaks the password one byte at a time to
                    # anyone who can measure response latency.
                    if not hmac.compare_digest(supplied, password):
                        return self._json(401, {"error": "wrong password"})
                    return self._json(200, {"token": sessions.issue()})

                if not self._authorized():
                    return self._json(401, {"error": "unauthorized"})

                if parts == ["api", "research", "probe"]:
                    body = self._read_json()
                    try:
                        return self._json(
                            200,
                            research_demo.probe(str(body.get("item_id", "")), str(body.get("model", "")), body.get("arms")),
                        )
                    except research_demo.ResearchDemoError as exc:
                        return self._json(exc.status, {"error": str(exc)})

                if parts == ["api", "projects"]:
                    body = self._read_json()
                    novel_id = str(body.get("id", "")).strip()
                    title = str(body.get("title", "")).strip()
                    content_type = str(body.get("content_type", "novel"))
                    if not novel_id or not title:
                        return self._json(400, {"error": "id and title are required"})
                    if not _PROJECT_ID_RE.fullmatch(novel_id):
                        return self._json(
                            400, {"error": "id must be 1-64 characters: lowercase letters, digits, hyphens and underscores, starting with a letter or digit"}
                        )
                    if content_type not in ("novel", "short_story", "general_text", "roleplay"):
                        return self._json(400, {"error": f"unknown content_type {content_type!r}"})
                    try:
                        handle = registry.create_project(novel_id, title, content_type)
                    except ValueError as exc:
                        return self._json(409, {"error": str(exc)})
                    return self._json(
                        201, {"id": novel_id, "title": title, "content_type": content_type}
                    )

                if (
                    len(parts) == 6
                    and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters"
                    and parts[5] == "voice"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    body = self._read_json()
                    speaker_id = str(body.get("speaker_id", "")).strip()
                    if not speaker_id:
                        return self._json(400, {"error": "speaker_id is required"})
                    from echotales.core.enums import AssertedBy, TargetKind
                    from echotales.core.interval import FuzzyInterval
                    from echotales.core.models import Attribute, DiscoursePosition
                    from echotales.pipeline.persona.build import persona_at

                    if handle.store.get_self(parts[4]) is None:
                        return self._json(404, {"error": f"unknown character {parts[4]!r}"})
                    persona_id = persona_at(handle.store, parts[4])
                    # A user override is a standing fact from the moment it's
                    # made, with no attested story-time position of its own
                    # (it didn't come from narration) -- story position 0.0,
                    # open-ended, same convention `persona/build.py` uses for
                    # a trait attested from the character's first appearance.
                    # `add_attribute` does not commit (bulk pipeline callers batch it); without this the row sat
                    # in an open transaction: a second connection saw nothing and its writes hit "database is locked".
                    with handle.store.transaction():
                        handle.store.add_attribute(
                            parts[2],
                            Attribute(
                                target_kind=TargetKind.PERSONA,
                                target_id=persona_id,
                                key="voice_override",
                                value=speaker_id,
                                learned_at_pos=DiscoursePosition(chapter=0, offset=0),
                                observer_id="reviewer",
                                asserted_by=AssertedBy.NARRATOR,
                                evidence=str(body.get("note", "user override via webview")),
                                interval=FuzzyInterval.open_ended(0.0),
                            ),
                        )
                    handle.invalidate()
                    return self._json(200, {"self_id": parts[4], "voice_override": speaker_id})

                if (
                    len(parts) == 6
                    and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters"
                    and parts[5] == "reference"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    body = self._read_json()
                    candidate_id = str(body.get("candidate_id", "")).strip()
                    if not candidate_id:
                        return self._json(400, {"error": "candidate_id is required"})
                    from echotales.pipeline.persona import refimg

                    if handle.store.get_self(parts[4]) is None:
                        return self._json(404, {"error": f"unknown character {parts[4]!r}"})
                    candidate = refimg.select_candidate(
                        handle.store, parts[2], parts[4], candidate_id,
                        actor="reviewer", note=str(body.get("note", "")),
                    )
                    handle.invalidate()
                    return self._json(200, {"id": candidate.id, "source_url": candidate.source_url})

                # POST /api/novels/<id>/characters/<self_id>/sheets/<persona_id>/approve or reject
                # POST /api/novels/<id>/sheets/<persona_id>/approve or reject
                if (
                    len(parts) == 8 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] == "sheets"
                    and parts[7] in ("approve", "reject")
                ) or (
                    len(parts) == 6 and parts[:2] == ["api", "novels"]
                    and parts[3] == "sheets" and parts[5] in ("approve", "reject")
                ):
                    novel_id = parts[2]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    if len(parts) == 8:
                        self_id = parts[4]
                        persona_id = parts[6]
                        action = parts[7]
                    else:
                        persona_id = parts[4]
                        action = parts[5]
                        self_id = persona_id.rsplit(":", 1)[0] if ":body" in persona_id else persona_id

                    body = self._read_json()
                    candidate_id = str(body.get("candidate_id", "")).strip()
                    from echotales.pipeline.persona import refimg

                    if not candidate_id:
                        candidates = refimg.list_sheets(handle.store, novel_id, self_id, persona_id=persona_id)
                        if not candidates:
                            cur = handle.store.conn.execute(
                                "SELECT id FROM ref_image_candidate WHERE novel_id=? AND persona_id=? ORDER BY found_at DESC LIMIT 1",
                                (novel_id, persona_id),
                            )
                            row = cur.fetchone()
                            if row:
                                candidate_id = row["id"]
                            else:
                                return self._json(404, {"error": f"no candidate found for persona {persona_id!r}"})
                        else:
                            candidate_id = candidates[0].id

                    if action == "approve":
                        candidate = refimg.approve_sheet(
                            handle.store, novel_id, self_id, candidate_id,
                            actor="reviewer", note=str(body.get("note", "")),
                        )
                    else:
                        candidate = refimg.reject_sheet(
                            handle.store, novel_id, self_id, candidate_id,
                            actor="reviewer", note=str(body.get("note", "")),
                        )
                    handle.invalidate()
                    return self._json(200, {
                        "id": candidate.id,
                        "persona_id": candidate.persona_id,
                        "self_id": candidate.self_id,
                        "source_url": candidate.source_url,
                        "selected": candidate.selected,
                        "action": action,
                    })

                # POST /api/novels/<id>/locations/<loc_id>/plates/<plate_id>/approve or reject
                if (
                    len(parts) == 8 and parts[:2] == ["api", "novels"]
                    and parts[3] == "locations" and parts[5] == "plates"
                    and parts[7] in ("approve", "reject")
                ):
                    novel_id = parts[2]
                    loc_id = parts[4]
                    plate_id = parts[6]
                    action = parts[7]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    from echotales.pipeline.assets import approval
                    body = self._read_json()
                    note = str(body.get("note", ""))
                    if action == "approve":
                        approval.approve_asset_candidate(handle.store, novel_id=novel_id, candidate_id=plate_id, note=note)
                    else:
                        approval.reject_asset_candidate(handle.store, novel_id=novel_id, candidate_id=plate_id, note=note)
                    handle.invalidate()
                    return self._json(200, {"id": plate_id, "action": action, "location_id": loc_id})

                # POST /api/novels/<id>/characters/<self_id>/turnarounds/<candidate_id>/approve or reject
                if (
                    len(parts) == 8 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] == "turnarounds"
                    and parts[7] in ("approve", "reject")
                ):
                    novel_id = parts[2]
                    self_id = parts[4]
                    candidate_id = parts[6]
                    action = parts[7]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    from echotales.pipeline.assets import approval
                    body = self._read_json()
                    note = str(body.get("note", ""))
                    if action == "approve":
                        approval.approve_asset_candidate(handle.store, novel_id=novel_id, candidate_id=candidate_id, note=note)
                    else:
                        approval.reject_asset_candidate(handle.store, novel_id=novel_id, candidate_id=candidate_id, note=note)
                    handle.invalidate()
                    return self._json(200, {"id": candidate_id, "action": action, "self_id": self_id, "is_approved": (action == "approve")})

                # POST /api/novels/<id>/bible/lock
                if len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3:] == ["bible", "lock"]:
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    from echotales.pipeline.review_gate import StaleBuild, lock_bible

                    body = self._read_json()
                    try:
                        return self._json(200, lock_bible(handle.store, parts[2], str(body.get("note", "")) if isinstance(body, dict) else ""))
                    except StaleBuild as exc:
                        return self._json(409, {"error": str(exc), "code": ErrorCode.STALE_BUILD})

                # POST /api/novels/<id>/review-items/<item_id>/resolve
                if (
                    len(parts) == 6 and parts[:2] == ["api", "novels"]
                    and parts[3] == "review-items" and parts[5] == "resolve"
                ):
                    novel_id = parts[2]
                    item_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    item = handle.store.get_review_item(item_id)
                    if item is None or item.novel_id != novel_id:
                        return self._json(404, {"error": f"unknown review item {item_id!r}"})
                    if _decision_state(item, handle.corrections) != "open":
                        return self._json(409, {"error": f"review item {item_id!r} is already resolved"})
                    body = self._read_json()
                    if item.kind == _DEFERRED_KIND:
                        status, result = _decide_deferred(handle, item, body)
                        if status != 200:
                            return self._json(status, result)
                        handle.invalidate()
                        return self._json(200, {
                            "item": _review_item_json(item, handle.corrections),
                            "correction_ids": result["corrections"],
                            "summary": handle.corrections.summary(),
                        })
                    resolution = str(body.get("resolution", "RESOLVED_MANUAL"))
                    handle.store.resolve_review_item(item_id, resolution)
                    handle.invalidate()
                    return self._json(200, {"id": item_id, "resolved": True, "resolution": resolution})

                # POST /api/novels/<id>/review-items/<item_id>/reopen
                if (
                    len(parts) == 6 and parts[:2] == ["api", "novels"]
                    and parts[3] == "review-items" and parts[5] == "reopen"
                ):
                    novel_id = parts[2]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    item = handle.store.get_review_item(parts[4])
                    if item is None or item.novel_id != novel_id:
                        return self._json(404, {"error": f"unknown review item {parts[4]!r}"})
                    if not item.resolved or (item.resolution or "").startswith("auto:"):
                        return self._json(409, {"error": "only an item a reviewer decided can be reopened"})
                    group = _item_group(item)
                    by_id = {c.id: c for c in handle.corrections}
                    mine = [by_id[str(i)] for i in group.get("correction_ids", []) if str(i) in by_id]
                    if any(c.applied for c in mine):
                        return self._json(409, {
                            "error": "this decision was already applied to the database and cannot be undone here",
                            "code": ErrorCode.APPLIED_CORRECTION,
                        })
                    for c in mine:
                        handle.corrections.remove(c.id)
                    group.pop("correction_ids", None)
                    group.pop("note", None)
                    item.resolved, item.resolution = False, None
                    handle.store.add_review_item(item)
                    handle.invalidate()
                    return self._json(200, {
                        "item": _review_item_json(item, handle.corrections),
                        "removed": [c.id for c in mine],
                        "summary": handle.corrections.summary(),
                    })

                # POST /api/novels/<id>/episodes/<ep_id>
                if len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3] == "episodes":
                    novel_id = parts[2]
                    ep_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    body = self._read_json()
                    ep_data = body.get("episode", body)
                    title = ep_data.get("title", f"Episode {ep_id}")
                    chapters = ep_data.get("chapter_range", [1.0, 1.0])
                    handle.store.save_screenplay_episode(
                        episode_id=ep_id,
                        novel_id=novel_id,
                        title=title,
                        source_chapters=chapters,
                        episode_json=json.dumps(ep_data),
                    )
                    handle.invalidate()
                    return self._json(200, {"saved": True, "episode_id": ep_id})

                # POST /api/novels/<id>/episodes/<ep_id>/compile
                if len(parts) == 6 and parts[:2] == ["api", "novels"] and parts[3] == "episodes" and parts[5] == "compile":
                    novel_id = parts[2]
                    ep_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    body = self._read_json()
                    chapters = [float(c) for c in body.get("chapters", [1.0])]
                    from echotales.pipeline.screenplay.compiler import compile_screenplay
                    snapshot = handle.store.bible_at(novel_id, chapters[0])
                    ep = compile_screenplay(
                        novel_id=novel_id,
                        episode_number=int(chapters[0]),
                        chapters=chapters,
                        chapter_text=body.get("chapter_text", "A tense conversation unfolding in the study."),
                        snapshot=snapshot,
                    )
                    handle.store.save_screenplay_episode(
                        episode_id=ep_id,
                        novel_id=novel_id,
                        title=ep.title,
                        source_chapters=list(ep.chapter_range),
                        episode_json=json.dumps(ep.to_dict()),
                    )
                    handle.invalidate()
                    return self._json(200, ep.to_dict())

                # POST .../shots/<shot_idx>/reroll and .../lock
                if len(parts) == 8 and parts[:2] == ["api", "novels"] and parts[3] == "episodes" and parts[5] == "shots" and parts[7] in ("reroll", "lock"):
                    return self._json(501, {"error": _SHOT_QA_UNWIRED})

                # POST /api/novels/<id>/characters/<self_id>/identity-sheet/generate: one sheet per body, drawn from the locked
                # identity sentence; approve it through the sheets endpoint to lock those words for every panel.
                if (
                    len(parts) == 7 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] == "identity-sheet" and parts[6] == "generate"
                ):
                    novel_id = parts[2]
                    self_id = parts[4]
                    sheet_handle = registry.handles.get(novel_id)
                    if sheet_handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    from echotales.pipeline.config import get_settings
                    from echotales.pipeline.persona import identity_sheet
                    from echotales.pipeline.render.compiled_route import generate_compiled_batch

                    try:
                        made = identity_sheet.generate_sheets(
                            sheet_handle.store, novel_id, self_ids=[self_id], out_dir=paths.asset_dir(novel_id, "references") / "identity",
                            draw=generate_compiled_batch, model_key=get_settings().render_image_model,
                        )
                    except Exception as exc:
                        return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
                    sheet_handle.invalidate()
                    return self._json(200, {"generated": True, "candidate_ids": [c.id for c in made], "self_id": self_id})

                # POST /api/novels/<id>/characters/<self_id>/turnarounds/generate
                if (
                    len(parts) == 7 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] == "turnarounds" and parts[6] == "generate"
                ):
                    novel_id = parts[2]
                    self_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    from echotales.core.models import CharacterBibleEntry
                    from echotales.pipeline.assets.turnaround import generate_character_assets
                    from echotales.pipeline.assets.approval import register_asset_candidate
                    out_dir = paths.asset_dir(novel_id, "references") / "turnarounds"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    char = handle.store.bible_at(novel_id, 1.0).characters.get(self_id)
                    if not char:
                        char = CharacterBibleEntry(
                            self_id=self_id,
                            canonical_label=self_id,
                            active_persona_id="persona:main",
                        )
                    sheet = generate_character_assets(char, output_dir=out_dir)
                    cand = register_asset_candidate(
                        handle.store,
                        novel_id=novel_id,
                        target_id=self_id,
                        target_label=self_id,
                        file_path=sheet.sheet_image_path,
                        role="sheet",
                    )
                    handle.invalidate()
                    return self._json(200, {"generated": True, "candidate_id": cand.id, "self_id": self_id})

                # POST /api/novels/<id>/locations/<loc_id>/plates/generate
                if (
                    len(parts) == 7 and parts[:2] == ["api", "novels"]
                    and parts[3] == "locations" and parts[5] == "plates" and parts[6] == "generate"
                ):
                    novel_id = parts[2]
                    loc_id = parts[4]
                    handle = registry.handles.get(novel_id)
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {novel_id!r}"})
                    from echotales.core.models import LocationBibleEntry
                    from echotales.pipeline.assets.location import generate_location_assets
                    from echotales.pipeline.assets.approval import register_asset_candidate
                    out_dir = paths.asset_dir(novel_id, "references") / "locations"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    loc = handle.store.bible_at(novel_id, 1.0).locations.get(loc_id)
                    if not loc:
                        loc = LocationBibleEntry(
                            location_id=loc_id,
                            canonical_name=loc_id,
                        )
                    plate = generate_location_assets(loc, output_dir=out_dir)
                    cand = register_asset_candidate(
                        handle.store,
                        novel_id=novel_id,
                        target_id=loc_id,
                        target_label=loc_id,
                        file_path=plate.master_plate_path,
                        role="location",
                    )
                    handle.invalidate()
                    return self._json(200, {"generated": True, "candidate_id": cand.id, "location_id": loc_id})

                if (
                    len(parts) == 4
                    and parts[:2] == ["api", "novels"]
                    and parts[3] == "corrections"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    body = self._read_json()
                    try:
                        ctype = CorrectionType(body["type"])
                    except (KeyError, ValueError) as exc:
                        return self._json(400, {"error": f"bad correction type: {exc}"})
                    correction = Correction(
                        novel_id=parts[2], type=ctype, payload=body.get("payload", {})
                    )
                    handle.corrections.add(correction)
                    handle.invalidate()
                    return self._json(201, correction.to_json())

                if (
                    len(parts) == 4
                    and parts[:2] == ["api", "novels"]
                    and parts[3] == "apply"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    result = apply_pending(handle.store, handle.corrections)
                    handle.invalidate()
                    return self._json(200, result)

                # --- Product Orchestration track ---------------------------

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "source":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    content_type_header = self.headers.get("Content-Type", "")
                    if "multipart/form-data" not in content_type_header:
                        return self._json(400, {"error": "expected multipart/form-data upload"})
                    from echotales.pipeline.ingest.adapters import ADAPTERS

                    query = parse_qs(urlparse(self.path).query)
                    # "generic" suits an arbitrary EPUB; "lightnovelworld" strips one web reader's navigation and is
                    # wrong for anything else, yet it was hard-coded for every upload (audit B4).
                    adapter = query.get("adapter", ["generic"])[0]
                    if adapter not in ADAPTERS:
                        return self._json(400, {"error": f"unknown adapter {adapter!r}; known: {sorted(ADAPTERS)}"})
                    # Western names shorten to the given name ("Elizabeth Bennet" -> "Elizabeth"); the default of
                    # family_first split such characters in two.
                    name_order = query.get("name_order", ["given_first"])[0]
                    if name_order not in _NAME_ORDERS:
                        return self._json(400, {"error": f"name_order must be one of {list(_NAME_ORDERS)}"})
                    try:
                        filename, data = parse_single_file(
                            content_type_header, self._read_body_bytes(_MAX_UPLOAD_BODY)
                        )
                    except MultipartError as exc:
                        return self._json(400, {"error": str(exc)})
                    if not filename.lower().endswith(".epub"):
                        # CLAUDE.md: "EPUB only, never PDF" -- PDF loses
                        # italics, an independent inner-monologue signal.
                        return self._json(400, {"error": "only .epub sources are accepted"})
                    asset_dir = registry.project_asset_dir(parts[2])
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    epub_path = asset_dir / "source.epub"
                    epub_path.write_bytes(data)
                    from echotales.pipeline.ingest.epub import Epub

                    try:
                        Epub(epub_path).close()
                    except Exception as exc:
                        epub_path.unlink(missing_ok=True)
                        return self._json(400, {"error": f"not a valid EPUB: {exc}"})
                    sources_path = asset_dir / "sources.toml"
                    sources_path.write_text(
                        "[[novel]]\n"
                        f"id = {_toml_str(parts[2])}\n"
                        f"title = {_toml_str(handle.source.label)}\n"
                        f"path = {_toml_str(str(epub_path))}\n"
                        f"adapter = {_toml_str(adapter)}\n"
                        f"name_order = {_toml_str(name_order)}\n",
                        encoding="utf-8",
                    )
                    novel_row = handle.store.get_novel(parts[2]) or {}
                    handle.store.add_novel(
                        parts[2], handle.source.label, str(epub_path), adapter,
                        content_type=novel_row.get("content_type", "novel"),
                    )
                    handle.invalidate()
                    return self._json(
                        201,
                        {"filename": filename, "path": str(epub_path), "bytes": len(data), "language": LANGUAGE_SUPPORT},
                    )

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "packs":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    content_type_header = self.headers.get("Content-Type", "")
                    if "multipart/form-data" not in content_type_header:
                        return self._json(400, {"error": "expected multipart/form-data upload"})
                    try:
                        filename, data = parse_single_file(content_type_header, self._read_body_bytes(_MAX_PACK_BODY))
                    except MultipartError as exc:
                        return self._json(400, {"error": str(exc)})
                    from echotales.pipeline import packs

                    # Base name only, characters restricted: the client's filename never reaches a server path
                    # unsanitised (same rule as the reference-image upload).
                    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename.replace("\\", "/")).name)
                    if not safe_name.lower().endswith(packs.PACK_SUFFIX) or safe_name.lower() == packs.PACK_SUFFIX:
                        return self._json(400, {"error": f"only {packs.PACK_SUFFIX} pack files are accepted"})
                    pack_dir = paths.asset_dir(parts[2], "packs")
                    pack_dir.mkdir(parents=True, exist_ok=True)
                    target = pack_dir / safe_name
                    # Written beside the target and checked there, so a file that is not a pack never lands under a
                    # pack's name (the list would offer it and the import job would fail on it).
                    probe = target.with_name(target.name + ".upload")
                    probe.write_bytes(data)
                    try:
                        packs.read_pack(probe)
                    except packs.PackError as exc:
                        probe.unlink(missing_ok=True)
                        return self._json(400, {"error": str(exc)})
                    probe.replace(target)
                    # A fresh upload under an old name must not show the old import's report.
                    target.with_name(target.name + ".report.json").unlink(missing_ok=True)
                    return self._json(201, {"name": safe_name, "bytes": len(data)})

                # POST /api/projects/<id>/comic as multipart is an upload; the same path with JSON queues the `comic` job.
                if (
                    len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "comic"
                    and "multipart/form-data" in self.headers.get("Content-Type", "")
                ):
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    from echotales.pipeline.comic import upload as comic_upload

                    try:
                        filename, data = parse_single_file(
                            self.headers.get("Content-Type", ""), self._read_body_bytes(_MAX_COMIC_BODY)
                        )
                        stored = comic_upload.store_comic_upload(
                            filename, data, paths.asset_dir(parts[2], "comic") / "source"
                        )
                    except (MultipartError, comic_upload.ComicUploadError) as exc:
                        return self._json(400, {"error": str(exc)})
                    return self._json(201, stored)

                # POST /api/projects/<id>/voices?name=&gender=&age=&consent=true  (multipart, one .wav/.flac)
                # The consent travels in the query string because the multipart reader here takes one file part and
                # nothing else; the server records its own fixed statement, never text from the request.
                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "voices":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    from echotales.pipeline import project_voices

                    query = parse_qs(urlparse(self.path).query)
                    one = lambda key: query.get(key, [""])[0]  # noqa: E731
                    if one("consent") != "true":
                        return self._json(400, {"error": f"Tick the box first: \"{project_voices.CONSENT_STATEMENT}\" Nothing was uploaded."})
                    content_type_header = self.headers.get("Content-Type", "")
                    if "multipart/form-data" not in content_type_header:
                        return self._json(400, {"error": "expected multipart/form-data upload"})
                    try:
                        filename, data = parse_single_file(content_type_header, self._read_body_bytes(_MAX_VOICE_BODY))
                        stored = project_voices.save_voice(
                            parts[2], filename=filename, data=data, name=one("name"), gender=one("gender").lower(),
                            age=int(one("age") or "0"), consent=True,
                        )
                    except MultipartError as exc:
                        return self._json(400, {"error": str(exc)})
                    except ValueError as exc:  # VoiceUploadError, or an age that is not a number
                        taken = "already exists" in str(exc)
                        return self._json(409 if taken else 400, {"error": str(exc) if isinstance(exc, project_voices.VoiceUploadError) else "age must be a whole number"})
                    return self._json(201, {"voice_id": stored.voice_id, "name": stored.name, "gender": stored.gender,
                                            "age": stored.age, "consent_at": stored.consent_at})

                # POST /api/projects/<id>/voices/narrator {"voice_id": ...}: the one config.json key this screen may
                # change. Only a voice the audition shortlisted or this project uploaded can be chosen.
                if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["voices", "narrator"]:
                    if parts[2] not in registry.handles:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    from echotales.pipeline import project_voices
                    from echotales.pipeline.config import set_voice_narrator
                    from echotales.pipeline.voice import audition as voice_audition

                    body = self._read_json()
                    voice_id = body.get("voice_id") if isinstance(body, dict) else None
                    known = {s["voice_id"] for s in voice_audition.read_shortlist(paths.asset_dir(parts[2], "audition"))}
                    known |= {v.voice_id for v in project_voices.list_project_voices(parts[2])}
                    if not isinstance(voice_id, str) or voice_id not in known:
                        return self._json(400, {"error": "voice_id must be one of the audition candidates or your own voices"})
                    try:
                        set_voice_narrator(voice_id)
                    except (OSError, ValueError) as exc:
                        return self._json(500, {"error": f"could not write config.json: {exc}"})
                    return self._json(200, {"narrator": voice_id})

                if (
                    len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "jobs" and parts[5] == "cancel"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    job = handle.store.get_job(parts[4])
                    if job is None:
                        return self._json(404, {"error": f"unknown job {parts[4]!r}"})
                    # A running stage is one call into a model or a long loop; stopping the thread mid-write
                    # could leave a half-written database, so only a job still waiting can be cancelled. The
                    # check and the write are one statement: a read-then-write let a cancel overwrite a job
                    # the worker had just claimed.
                    if not handle.store.transition_job(
                        parts[4], [JobStatus.PENDING], JobStatus.CANCELLED,
                        finished_at=time.time(), error_summary="cancelled by user",
                    ):
                        now = handle.store.get_job(parts[4])
                        state = now.status.value if now is not None else "gone"
                        return self._json(409, {
                            "error": f"job is {state}; only a queued job can be cancelled",
                            "code": ErrorCode.JOB_NOT_CANCELLABLE,
                        })
                    return self._json(200, _job_json(handle.store.get_job(parts[4])))

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] in JOB_KINDS:
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    body = self._read_json()
                    kind = parts[3]
                    params = dict(body)
                    if (
                        kind in ("render", "reference_gen")
                        and "engine" in params
                        and not http_engine_known(str(params["engine"]))
                    ):
                        return self._json(
                            400,
                            {
                                "error": f"engine {params['engine']!r} is not allowed over "
                                f"HTTP; allowed: {_enabled_engines()}"
                            },
                        )
                    if kind == "render":
                        from echotales.pipeline.compute import density_error

                        if (bad_density := density_error(str(params.get("density", "beat")))) is not None:
                            return self._json(400, {"error": bad_density})
                    if kind in ("render", "reference_gen"):
                        # The same guard and digest as the dedicated generate routes: this route used to accept a
                        # real engine on a busy GPU and ignore a changed genre.
                        requested = str(params.get("engine") or default_image_engine())
                        refusal = _gpu_refusal(requested) or _stale_build_refusal(handle, parts[2], requested)
                        if refusal:
                            return self._json(409, _refusal_body(refusal))
                        params = _with_genre(handle, params)
                    if kind in ("pack_export", "pack_import"):
                        params["corrections_path"] = str(handle.corrections.path)
                    if kind == "companion":
                        from echotales.pipeline.companion import parse_through

                        try:
                            params = {"through": parse_through(params.get("through"))}
                        except ValueError as exc:
                            return self._json(400, {"error": str(exc)})
                    if kind == "pipeline":
                        # The resolve stage reads the project's review decisions; the path comes from the server's
                        # registry, never the request.
                        params["corrections_path"] = str(handle.corrections.path)
                        # Shown before the long run starts; kept in the job's params so the Studio can show it
                        # again while the job runs. Measured where this project has timings, else labelled estimates.
                        from echotales.pipeline.long_series import estimate_run

                        params["estimate"] = estimate_run(
                            handle.store, parts[2], params.get("chapters"), stages=pipeline_stage_names(params)
                        )
                    if kind == "video":
                        # Folders come from the project, never the client (same rule as the voice job below).
                        for key in ("panel_dir", "audio_dir", "out_dir"):
                            params.pop(key, None)
                        video_engine = str(params.get("engine") or "stills")
                        if video_engine not in ("stills", "ltx-local"):
                            return self._json(400, {"error": f"video engine {video_engine!r} is not allowed; use stills or ltx-local"})
                        refusal = _gpu_refusal(video_engine)
                        if refusal:
                            return self._json(409, _refusal_body(refusal))
                    if kind == "voice_audition":
                        # Same rule as the voice job: the bank folder and the output folder are the server's choice.
                        params.pop("bank", None)
                        voice_engine = str(params.get("engine") or "chatterbox")
                        if voice_engine not in engine_registry.names("tts"):
                            return self._json(400, {"error": f"voice engine {voice_engine!r} is not allowed; use stub or chatterbox"})
                        from echotales.pipeline.reader.delivery_pass import (  # type: ignore[import-untyped]
                            LABELS,
                        )
                        from echotales.pipeline.voice.audition import (  # type: ignore[import-untyped]
                            MAX_SAMPLE_CHARS,
                        )

                        target = params.get("target")
                        if target not in ("narrator", "line"):
                            return self._json(400, {"error": "target must be 'narrator' or 'line'"})
                        if target == "line":
                            text = params.get("text")
                            if not isinstance(params.get("voice_id"), str) or not params["voice_id"]:
                                return self._json(400, {"error": "voice_id is required"})
                            if not isinstance(text, str) or not text.strip() or len(text.strip()) > MAX_SAMPLE_CHARS:
                                return self._json(400, {"error": f"text must be 1 to {MAX_SAMPLE_CHARS} characters"})
                            if params.get("emotion", "neutral") not in set(LABELS.values()):
                                return self._json(400, {"error": f"unknown emotion {params.get('emotion')!r}"})
                            params["text"] = text.strip()
                    if kind == "voice":
                        # A path from the request chose which directory the server loads a voice bank from and where
                        # it wrote; both come from the project, never the client (audit B5).
                        params.pop("bank", None)
                        params.pop("out_dir", None)
                        voice_engine = str(params.get("engine") or "chatterbox")
                        if voice_engine not in engine_registry.names("tts"):
                            return self._json(400, {"error": f"voice engine {voice_engine!r} is not allowed; use stub or chatterbox"})
                        from echotales.pipeline.review_gate import voice_refusal

                        refusal = voice_refusal(handle.store, parts[2], voice_engine, handle.corrections)
                        if refusal:
                            return self._json(409, _refusal_body(refusal))
                    if "sources_path" not in params:
                        default_sources = registry.project_asset_dir(parts[2]) / "sources.toml"
                        if default_sources.is_file():
                            params["sources_path"] = str(default_sources)
                    queued = self._enqueue(handle, kind, params)
                    if "estimate" in params:
                        queued["estimate"] = params["estimate"]
                    return self._json(202, queued)

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "genre":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    from echotales.pipeline.persona.genre import GENRES

                    body = self._read_json()
                    if not isinstance(body, dict):
                        return self._json(400, {"error": 'body must be an object like {"genre": "xianxia"}'})
                    genre = body.get("genre")
                    if genre is not None and (not isinstance(genre, str) or genre not in GENRES):
                        return self._json(400, {"error": f"unknown genre {genre!r}; known: {sorted(GENRES)}"})
                    handle.store.set_visual_genre(parts[2], genre)
                    return self._json(200, _project_status(handle))

                if (
                    len(parts) == 5 and parts[:2] == ["api", "novels"]
                    and parts[3] == "render" and parts[4] == "generate"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    body = self._read_json()
                    engine_name = str(body.get("engine") or default_image_engine())
                    if not http_engine_known(engine_name):
                        return self._json(
                            400,
                            {
                                "error": f"engine {engine_name!r} is not allowed over HTTP; "
                                f"allowed: {_enabled_engines()}"
                            },
                        )
                    from echotales.pipeline.compute import density_error

                    if (bad_density := density_error(str(body.get("density", "beat")))) is not None:
                        return self._json(400, {"error": bad_density})
                    refusal = _gpu_refusal(engine_name) or _stale_build_refusal(handle, parts[2], engine_name)
                    if refusal:
                        return self._json(409, _refusal_body(refusal))
                    return self._json(202, self._enqueue(handle, "render", _with_genre(handle, dict(body))))

                if (
                    len(parts) == 5 and parts[:2] == ["api", "novels"]
                    and parts[3] == "reference" and parts[4] == "generate"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    body = self._read_json()
                    engine_name = str(body.get("engine") or default_image_engine())
                    if not http_engine_known(engine_name):
                        return self._json(
                            400,
                            {
                                "error": f"engine {engine_name!r} is not allowed over HTTP; "
                                f"allowed: {_enabled_engines()}"
                            },
                        )
                    refusal = _gpu_refusal(engine_name)
                    if refusal:
                        return self._json(409, _refusal_body(refusal))
                    return self._json(202, self._enqueue(handle, "reference_gen", _with_genre(handle, dict(body))))

                if (
                    len(parts) == 5 and parts[:2] == ["api", "projects"]
                    and parts[3] == "reference" and parts[4] == "search"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    body = self._read_json()
                    params = {"self_ids": body.get("self_ids")} if body.get("self_ids") else {}
                    return self._json(202, self._enqueue(handle, "refimg_search", params))

                if (
                    len(parts) == 7 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] == "reference"
                    and parts[6] == "search"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    if handle.store.get_self(parts[4]) is None:
                        return self._json(404, {"error": f"unknown character {parts[4]!r}"})
                    return self._json(
                        202, self._enqueue(handle, "refimg_search", {"self_ids": [parts[4]]})
                    )

                if (
                    len(parts) == 7 and parts[:2] == ["api", "novels"]
                    and parts[3] == "characters" and parts[5] == "reference"
                    and parts[6] == "upload"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    if handle.store.get_self(parts[4]) is None:
                        return self._json(404, {"error": f"unknown character {parts[4]!r}"})
                    content_type_header = self.headers.get("Content-Type", "")
                    if "multipart/form-data" not in content_type_header:
                        return self._json(400, {"error": "expected multipart/form-data upload"})
                    try:
                        filename, data = parse_single_file(
                            content_type_header, self._read_body_bytes(_MAX_IMAGE_BODY)
                        )
                    except MultipartError as exc:
                        return self._json(400, {"error": str(exc)})
                    asset_dir = registry.project_asset_dir(parts[2]) / "reference_uploads"
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    # The client's filename joined a server path unsanitised (audit); keep only a safe base name.
                    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name) or "upload"
                    image_path = asset_dir / f"{re.sub(r'[^A-Za-z0-9._-]', '_', parts[4])}_{safe_name}"
                    image_path.write_bytes(data)
                    from echotales.pipeline.persona import refimg

                    candidate = refimg.register_user_image(
                        handle.store, parts[2], parts[4], str(image_path), actor="reviewer",
                    )
                    handle.invalidate()
                    return self._json(201, {"id": candidate.id, "source_url": candidate.source_url})
            except _BodyTooLarge as exc:
                return self._json(413, {"error": str(exc)})
            except Exception as exc:
                log.exception("POST %s failed", self.path)
                return self._json(500, {"error": str(exc)})
            self._json(404, {"error": "not found"})

        def do_DELETE(self) -> None:
            parts = _split_path(urlparse(self.path).path)
            if not self._origin_allowed():
                return self._json(403, {"error": "cross-site request refused"})
            try:
                if not self._authorized():
                    return self._json(401, {"error": "unauthorized"})
                if (
                    len(parts) == 5
                    and parts[:2] == ["api", "novels"]
                    and parts[3] == "corrections"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    try:
                        removed = handle.corrections.remove(parts[4])
                    except AppliedCorrectionError:
                        return self._json(409, {
                            "error": f"correction {parts[4]!r} has already been applied to the database; "
                            "removing its record would leave a human edit with no provenance, so it is kept",
                            "code": ErrorCode.APPLIED_CORRECTION,
                        })
                    if removed:
                        handle.invalidate()
                    return self._json(200, {"removed": removed})

                if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                    try:
                        removed = registry.delete_project(parts[2])
                    except PermissionError as exc:
                        return self._json(403, {"error": str(exc)})
                    except ProjectBusyError as exc:
                        return self._json(409, {"error": str(exc), "code": ErrorCode.PROJECT_BUSY})
                    return self._json(200, {"removed": removed})
            except Exception as exc:
                log.exception("DELETE %s failed", self.path)
                return self._json(500, {"error": str(exc)})
            self._json(404, {"error": "not found"})

        def log_message(self, fmt: str, *args: object) -> None:  # quiet by default
            log.debug(fmt, *args)

    return Handler


def serve(
    sources: list[NovelSource],
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    static_dir: Path | None = None,
    corrections_dir: Path = Path("data/corrections"),
) -> None:
    # Single-threaded, deliberately: `Store` opens one sqlite3 connection per
    # `Registry` entry in the main thread, and sqlite3 forbids using a
    # connection from any other thread by default. A threaded server would
    # need a connection per request thread (or a lock) to fix that; neither is
    # worth it for a tool with exactly one user clicking around at a time.
    # Corrections are a JSONL log per novel, not rows in the novel's .db. The
    # default is relative to the working directory, so a QA server started
    # from the repo root against a *scratch* .db still wrote its test edits
    # into the tracked data/corrections/ log (2026-09-26). QA runs should
    # pass --corrections-dir pointing at a scratch directory.
    registry = Registry(sources, corrections_dir=corrections_dir)
    # One worker thread, strictly sequential job execution process-wide --
    # see jobs.py's module docstring for why (the same GPU-sharing
    # constraint `config.json::render.direction_first` already establishes
    # for local-model stages, generalized here).
    job_queue = JobQueue()
    job_queue.start()
    handler = make_handler(registry, job_queue, static_dir=static_dir)
    httpd = HTTPServer((host, port), handler)

    print(f"webview backend on http://{host}:{port}  (novels: {[s.novel_id for s in sources]})")
    print(f"  corrections log: {corrections_dir.resolve()}" + (f"  |  frontend: {static_dir.resolve()}" if static_dir else ""))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        for h in registry.handles.values():
            h.store.close()
