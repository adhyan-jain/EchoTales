"""Content digest of a pipeline database: what it resolved, not its bytes.

A file sha256 is not a stable identity for these databases: they run in WAL
mode, and merely opening one through `Store` rewrites the header. On
2026-09-27 the RI database of record changed file hash (a2695660 -> d6accb2d)
from a read-only dry run, while its content was identical to v1.1 rebuilt
from v1. This digest hashes the parts every result depends on: mention
targets, span types and speakers, entity kinds, alias bindings.

    python3 scripts/maintenance/db_content_digest.py data/db/reverend-insanity.db
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys

QUERIES = {
    "mentions": "SELECT id || '|' || coalesce(target_id, '') FROM mention ORDER BY id",
    "spans": "SELECT id || '|' || span_type || '|' || coalesce(speaker_self_id, '') FROM span ORDER BY id",
    "entities": "SELECT id || '|' || coalesce(kind, '') FROM self_entity ORDER BY id",
    "aliases": "SELECT alias || '|' || target_id FROM alias_binding ORDER BY alias, target_id",
}


def digest(path: str) -> dict[str, str]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = {}
    for name, sql in QUERIES.items():
        h = hashlib.sha256()
        for (row,) in conn.execute(sql):
            h.update(row.encode() + b"\n")
        out[name] = h.hexdigest()[:16]
    conn.close()
    out["all"] = hashlib.sha256("".join(out.values()).encode()).hexdigest()[:16]
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, digest(p))
