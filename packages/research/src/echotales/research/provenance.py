"""Where a result came from: commit, dirty tree, inputs, environment.

EVOLUTION 4.81 found most of the repo's numbers had been produced from an
uncommitted tree. A dirty flag is therefore recorded, not refused -- research
iteration happens on dirty trees -- but it is surfaced in every comparison so
a dirty-tree number is never mistaken for a reproducible one.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except Exception:
        return ""


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def collect(config_hash: str, inputs: dict[str, Path] | None = None) -> dict[str, Any]:
    digests = {}
    for name, p in (inputs or {}).items():
        p = Path(p)
        digests[name] = file_digest(p) if p.is_file() else ("missing" if not p.exists() else "dir")
    return {
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "config_hash": config_hash,
        "inputs": digests,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "created_at": time.time(),
    }
