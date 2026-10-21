"""The version a database build is stamped with, and the check that refuses a stale one.

Why this exists: `pipeline_run.pipeline_version` was empty in every database, so the Studio could render from
a LotM build whose personas predated the speaker-join fix ("0 spoken lines", audit 2026-10-22) and nothing
said so. Bump `PIPELINE_VERSION` whenever extraction output changes meaning (a new reader prompt, a changed
validator); every database built by older code is then refused for real renders until it is rebuilt.
"""

from __future__ import annotations

from echotales.core.store import Store

#: "2" = the reader-pass era (evidence-quoted deltas, text-only canon). "" and "1" are everything built before.
PIPELINE_VERSION = "2"


def staleness_reason(store: Store, novel_id: str) -> str | None:
    """Why this database must not feed a real render, or None when it was built by the current code.

    A database with no recorded run is stale too: it was filled by something that never stamped, which is
    exactly the stale-build case this guards."""
    stamp = store.latest_pipeline_version(novel_id)
    if stamp == PIPELINE_VERSION:
        return None
    seen = "no recorded build" if stamp is None else (f"build stamp {stamp!r}" if stamp else "an unstamped build")
    return (
        f"{novel_id!r} has {seen}; the current pipeline is version {PIPELINE_VERSION!r}. "
        "Rebuild it (echotales run) before a real render."
    )
