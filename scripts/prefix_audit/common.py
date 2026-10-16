"""Shared helpers for the prefix-faithfulness audit (docs/research/PREFIX_FAITHFULNESS/PREREG.md).

LABEL PROVENANCE: SYSTEM-INTERNAL (no labels). CPU only; no LLM, no network, no GPU. The canonical databases are
copied with the SQLite backup API (they carry live -wal files, so a plain open or file copy could miss or corrupt
pages) and every build runs on a throwaway copy under data/scratch/prefix_audit/. Only ids, chapter numbers and
counts are ever written to results: no novel text.
"""

from __future__ import annotations

import math
import os
import shutil
import sqlite3
from pathlib import Path

# Must be set before echotales is imported: stub mode is what makes every build deterministic and offline.
os.environ["ECHOTALES_LLM_MODE"] = "stub"

WORKTREE = Path(__file__).resolve().parents[2]
SCRATCH = WORKTREE / "data" / "scratch" / "prefix_audit"
RESULTS = WORKTREE / "data" / "eval" / "prefix_audit"
# The worktree has no data/db (gitignored). The main checkout's databases are read through the SQLite backup API only.
SOURCE_DB_DIR = Path(os.environ.get("PREFIX_AUDIT_SOURCE_DB_DIR", "/home/adhyan/Desktop/EchoTales/data/db"))

#: The cuts E6 used, so a replication is comparable cut for cut.
CUTS = {
    "lord-of-the-mysteries": [5, 10, 20, 30],
    "omniscient-readers-viewpoint": [5, 10, 20, 30],
    "reverend-insanity": [10, 20, 40, 80, 120],
    # PREREG_PD.md: public-domain English originals, stores built by scripts/prefix_audit/pd_volume.py
    "oliver-twist": [5, 10, 15, 20, 30, 40],
    "three-musketeers": [10, 20, 30, 40, 50],
}
PD_DB_DIR = WORKTREE / "data" / "scratch" / "pd_db"

from echotales.core.store import Store  # noqa: E402,F401


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 5), round(min(1.0, c + h), 5)]


def snapshot_source(nid: str) -> Path:
    """One consistent single-file snapshot of a canonical database, taken once and reused by every build."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    dst = SCRATCH / f"{nid}.src.db"
    if dst.exists():
        return dst
    origin = SOURCE_DB_DIR / (nid + ".db")
    if not origin.exists():
        origin = PD_DB_DIR / (nid + ".db")
    src = sqlite3.connect(f"file:{origin}?mode=ro", uri=True)
    out = sqlite3.connect(dst)
    with out:
        src.backup(out)
    out.close()
    src.close()
    return dst


def fresh_copy(src: Path, name: str) -> str:
    dst = SCRATCH / f"{name}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(dst) + suffix).unlink(missing_ok=True)
    shutil.copy(src, dst)
    return str(dst)


