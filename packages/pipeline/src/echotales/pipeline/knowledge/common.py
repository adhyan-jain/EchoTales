"""Shared helpers: text normalisation, the model id a client will use, and resumable-run markers."""

from __future__ import annotations

import json
import re
from typing import Any

from echotales.core.store import Store

KB_TIER = "kb"


def norm(text: str) -> str:
    """Lower-case, curly quotes straightened, whitespace collapsed: the comparison form for quote checks."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in(quote: str, text: str) -> bool:
    """Whether `quote` occurs in `text` after normalisation. Under 8 characters never counts (a stray word proves nothing)."""
    q = norm(quote).strip(" .,;:\"'…")
    return len(q) >= 8 and q in norm(text)


def model_id_of(client: Any) -> str:
    """The model a client will use for READER calls, for the resume key and for the evidence stamp."""
    explicit = getattr(client, "model_id", None)
    if explicit:
        return str(explicit)
    try:
        from echotales.pipeline.llm.tasks import Task, profile_for

        return str(client._provider_for(profile_for(Task.READER), Task.READER).model)
    except Exception:
        return "unknown"


def artifact_id(kind: str, novel_id: str, *parts: object) -> str:
    return ":".join(["kb", kind, novel_id, *[str(p) for p in parts]])


def has_artifact(store: Store, art_id: str) -> bool:
    return store.conn.execute("SELECT 1 FROM derived_artifact WHERE id=?", (art_id,)).fetchone() is not None


def put_artifact(store: Store, art_id: str, payload: dict[str, Any]) -> None:
    store.record_artifact(art_id, KB_TIER, [], "", json.dumps(payload, ensure_ascii=False))
    store.conn.commit()


def get_artifact(store: Store, art_id: str) -> dict[str, Any] | None:
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (art_id,)).fetchone()
    return json.loads(row["payload_json"]) if row else None


def artifacts_like(store: Store, prefix: str) -> list[dict[str, Any]]:
    rows = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id LIKE ?", (prefix + "%",)).fetchall()
    return [json.loads(r["payload_json"]) for r in rows]


def parse_range(spec: str | None, available: list[float]) -> list[float]:
    """`3-9` or `1,4,7-9` over the chapters a novel has."""
    if not spec:
        return sorted(available)
    wanted: set[float] = set()
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        lo, hi = float(a), float(b or a)
        wanted |= {n for n in available if lo <= n <= hi}
    return sorted(wanted)
