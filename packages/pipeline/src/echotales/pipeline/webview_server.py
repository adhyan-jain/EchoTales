"""Local HTTP backend for the interactive webview.

The read-only viewer (`webview.py`) is a static export -- correct for
auditing a finished run, but it can't accept a correction because there is
nothing running to receive one. This module is that server: stdlib only
(`http.server`), because the whole point is a local review tool, and adding a
web framework dependency for a handful of routes used by one person at a time
would be solving a problem that doesn't exist here.

Routes:
    GET  /api/manifest
    GET  /api/novels/<id>              live payload, corrections overlaid
    GET  /api/novels/<id>/corrections  log + summary
    POST /api/novels/<id>/corrections  body: {"type": "merge_entities",
                                               "payload": {"from_id", "into_id"}}
    DELETE /api/novels/<id>/corrections/<correction_id>   undo a pending one
    POST /api/novels/<id>/apply        write pending corrections into the store

Corrections are overlaid onto the payload *before* it reaches the browser
(`_overlay_merges`), not reapplied client-side, so the static viewer's render
logic and the live one never have to agree on a second implementation of "what
does a merge look like."
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from echotales.core.store import Store
from echotales.pipeline.corrections import (
    Correction,
    CorrectionLog,
    CorrectionType,
    apply_pending,
    new_manual_entity_id,
)
from echotales.pipeline.webview import NovelSource, build_novel_payload

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
            if new_label:
                eid = new_manual_entity_id(novel_id, c.id)
                manual_labels[eid] = str(new_label)
                speaker_override[span_id] = eid
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

            if final_speaker:
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

    def __init__(self, sources: list[NovelSource], corrections_dir: Path) -> None:
        self.handles: dict[str, NovelHandle] = {}
        for src in sources:
            store = Store(src.db_path)
            corrections = CorrectionLog(corrections_dir / f"{src.novel_id}.jsonl")
            self.handles[src.novel_id] = NovelHandle(src, store, corrections)

    def manifest(self) -> list[dict[str, str]]:
        return [
            {"id": h.source.novel_id, "label": h.source.label} for h in self.handles.values()
        ]


def make_handler(registry: Registry) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, status: int, body: object) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict:  # type: ignore[type-arg]
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length))

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            parts = urlparse(self.path).path.strip("/").split("/")
            try:
                if parts == ["api", "manifest"]:
                    return self._json(200, registry.manifest())
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
            except Exception as exc:
                log.exception("GET %s failed", self.path)
                return self._json(500, {"error": str(exc)})
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            parts = urlparse(self.path).path.strip("/").split("/")
            try:
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
            except Exception as exc:
                log.exception("POST %s failed", self.path)
                return self._json(500, {"error": str(exc)})
            self._json(404, {"error": "not found"})

        def do_DELETE(self) -> None:
            parts = urlparse(self.path).path.strip("/").split("/")
            try:
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
            except Exception as exc:
                log.exception("DELETE %s failed", self.path)
                return self._json(500, {"error": str(exc)})
            self._json(404, {"error": "not found"})

        def log_message(self, fmt: str, *args: object) -> None:  # quiet by default
            log.debug(fmt, *args)

    return Handler


def serve(sources: list[NovelSource], *, host: str = "127.0.0.1", port: int = 8787) -> None:
    # Single-threaded, deliberately: `Store` opens one sqlite3 connection per
    # `Registry` entry in the main thread, and sqlite3 forbids using a
    # connection from any other thread by default. A threaded server would
    # need a connection per request thread (or a lock) to fix that; neither is
    # worth it for a tool with exactly one user clicking around at a time.
    registry = Registry(sources, corrections_dir=Path("data/corrections"))
    handler = make_handler(registry)
    httpd = HTTPServer((host, port), handler)
    print(f"webview backend on http://{host}:{port}  (novels: {[s.novel_id for s in sources]})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        for h in registry.handles.values():
            h.store.close()
