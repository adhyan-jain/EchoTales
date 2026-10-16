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
    GET  /api/novels/<id>              live payload, corrections overlaid
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

import hmac
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from echotales.core.models import Job
from echotales.core.store import Store
from echotales.pipeline import paths, research_demo
from echotales.pipeline._multipart import MultipartError, parse_single_file
from echotales.pipeline.corrections import (
    Correction,
    CorrectionLog,
    CorrectionType,
    apply_pending,
    new_manual_entity_id,
)
from echotales.pipeline.jobs import ALLOWED_HTTP_ENGINES, JOB_KINDS, JobQueue, new_job_id
from echotales.pipeline.webview import (
    NovelSource,
    _anon_slot_colour,
    _anon_slot_label,
    build_character_dashboard,
    build_novel_payload,
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

    if not (
        merge_redirect or mention_override or speaker_override
        or flags_by_mention or flags_by_span or span_type_override
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


def _job_json(job: Job) -> dict:  # type: ignore[type-arg]
    return {
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
        "job_count": len(jobs),
        "last_job": _job_json(jobs[0]) if jobs else None,
    }


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


    class Handler(BaseHTTPRequestHandler):
        # The server is single-threaded (see `serve`), so one client that
        # stops reading -- a paused <video>, a dropped phone -- would otherwise
        # block every other request until the OS gives up. Reproduced by the
        # Python review of 2026-09-26: read 1 KB of a 50 MB file, stall, and a
        # second request hangs. A socket timeout bounds that to 30 s.
        timeout = 30

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def _json(self, status: int, body: object) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _read_body_bytes(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0))
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
            parts = url.path.strip("/").split("/")
            if self.command in ("GET", "HEAD") and len(parts) == 5 and parts[:2] == ["api", "novels"] and parts[3:] == ["output", "file"]:
                return sessions.valid(parse_qs(url.query).get("access_token", [""])[0])
            return False

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            parts = urlparse(self.path).path.strip("/").split("/")
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
                    return self._json(
                        200,
                        [
                            {"number": c["number"], "title": c.get("title", "")}
                            for c in handle.payload().get("chapters", [])
                        ],
                    )
                if len(parts) == 4 and parts[:2] == ["api", "novels"] and parts[3] == "characters":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    return self._json(200, build_character_dashboard(handle.store, parts[2]))

                # --- Product Orchestration track ---------------------------

                if parts == ["api", "projects"]:
                    return self._json(200, [_project_status(h) for h in registry.handles.values()])

                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "jobs":
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown project {parts[2]!r}"})
                    return self._json(
                        200, [_job_json(j) for j in handle.store.list_jobs(parts[2])]
                    )

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
                            **_job_json(job),
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
            parts = urlparse(self.path).path.strip("/").split("/")
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

                    persona_id = persona_at(handle.store, parts[4])
                    # A user override is a standing fact from the moment it's
                    # made, with no attested story-time position of its own
                    # (it didn't come from narration) -- story position 0.0,
                    # open-ended, same convention `persona/build.py` uses for
                    # a trait attested from the character's first appearance.
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

                    candidate = refimg.select_candidate(
                        handle.store, parts[2], parts[4], candidate_id,
                        actor="reviewer", note=str(body.get("note", "")),
                    )
                    handle.invalidate()
                    return self._json(200, {"id": candidate.id, "source_url": candidate.source_url})

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
                    try:
                        filename, data = parse_single_file(
                            content_type_header, self._read_body_bytes()
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
                        f'id = "{parts[2]}"\n'
                        f'title = "{handle.source.label}"\n'
                        f'path = "{epub_path}"\n'
                        'adapter = "lightnovelworld"\n'
                    )
                    novel_row = handle.store.get_novel(parts[2]) or {}
                    handle.store.add_novel(
                        parts[2], handle.source.label, str(epub_path), "lightnovelworld",
                        content_type=novel_row.get("content_type", "novel"),
                    )
                    handle.invalidate()
                    return self._json(
                        201, {"filename": filename, "path": str(epub_path), "bytes": len(data)}
                    )

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
                        and params["engine"] not in ALLOWED_HTTP_ENGINES
                    ):
                        return self._json(
                            400,
                            {
                                "error": f"engine {params['engine']!r} is not allowed over "
                                f"HTTP; allowed: {sorted(ALLOWED_HTTP_ENGINES)}"
                            },
                        )
                    if "sources_path" not in params:
                        default_sources = registry.project_asset_dir(parts[2]) / "sources.toml"
                        if default_sources.is_file():
                            params["sources_path"] = str(default_sources)
                    return self._json(202, self._enqueue(handle, kind, params))

                if (
                    len(parts) == 5 and parts[:2] == ["api", "novels"]
                    and parts[3] == "render" and parts[4] == "generate"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    body = self._read_json()
                    engine_name = str(body.get("engine", "stub"))
                    if engine_name not in ALLOWED_HTTP_ENGINES:
                        return self._json(
                            400,
                            {
                                "error": f"engine {engine_name!r} is not allowed over HTTP; "
                                f"allowed: {sorted(ALLOWED_HTTP_ENGINES)}"
                            },
                        )
                    return self._json(202, self._enqueue(handle, "render", dict(body)))

                if (
                    len(parts) == 5 and parts[:2] == ["api", "novels"]
                    and parts[3] == "reference" and parts[4] == "generate"
                ):
                    handle = registry.handles.get(parts[2])
                    if handle is None:
                        return self._json(404, {"error": f"unknown novel {parts[2]!r}"})
                    body = self._read_json()
                    engine_name = str(body.get("engine", "stub"))
                    if engine_name not in ALLOWED_HTTP_ENGINES:
                        return self._json(
                            400,
                            {
                                "error": f"engine {engine_name!r} is not allowed over HTTP; "
                                f"allowed: {sorted(ALLOWED_HTTP_ENGINES)}"
                            },
                        )
                    return self._json(202, self._enqueue(handle, "reference_gen", dict(body)))

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
                    content_type_header = self.headers.get("Content-Type", "")
                    if "multipart/form-data" not in content_type_header:
                        return self._json(400, {"error": "expected multipart/form-data upload"})
                    try:
                        filename, data = parse_single_file(
                            content_type_header, self._read_body_bytes()
                        )
                    except MultipartError as exc:
                        return self._json(400, {"error": str(exc)})
                    asset_dir = registry.project_asset_dir(parts[2]) / "reference_uploads"
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    image_path = asset_dir / f"{parts[4]}_{filename}"
                    image_path.write_bytes(data)
                    from echotales.pipeline.persona import refimg

                    candidate = refimg.register_user_image(
                        handle.store, parts[2], parts[4], str(image_path), actor="reviewer",
                    )
                    handle.invalidate()
                    return self._json(201, {"id": candidate.id, "source_url": candidate.source_url})
            except Exception as exc:
                log.exception("POST %s failed", self.path)
                return self._json(500, {"error": str(exc)})
            self._json(404, {"error": "not found"})

        def do_DELETE(self) -> None:
            parts = urlparse(self.path).path.strip("/").split("/")
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
                    removed = handle.corrections.remove(parts[4])
                    if removed:
                        handle.invalidate()
                    return self._json(200, {"removed": removed})

                if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                    try:
                        removed = registry.delete_project(parts[2])
                    except PermissionError as exc:
                        return self._json(403, {"error": str(exc)})
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
