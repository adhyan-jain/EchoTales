"""The version a database build is stamped with, and the check that refuses a stale one.

Why this exists: `pipeline_run.pipeline_version` was empty in every database, so the Studio could render from
a LotM build whose personas predated the speaker-join fix ("0 spoken lines", audit 2026-10-22) and nothing
said so. Bump `PIPELINE_VERSION` whenever extraction output changes meaning (a new reader prompt, a changed
validator); every database built by older code is then refused for real renders until it is rebuilt.
"""

from __future__ import annotations

from echotales.core.models import StageStatus
from echotales.core.store import Store
from echotales.pipeline.errors import ErrorCode, Refusal

#: "2" = the reader-pass era (evidence-quoted deltas, text-only canon). "" and "1" are everything built before.
PIPELINE_VERSION = "2"


def staleness_reason(store: Store, novel_id: str) -> str | None:
    """Why this database must not feed a real render, or None when its newest full build succeeded under the
    current code.

    Only a full build counts (`pipeline_run.is_build`): every job writes a pipeline_run row too, and a failed
    `export_m4b` job once re-stamped a stale database current. The newest build decides even when an older one
    succeeded, because a failed or running rebuild has already rewritten part of the graph. A database with no
    recorded build is stale: it was filled by something that never stamped."""
    build = store.latest_build(novel_id)
    if build is None:
        return Refusal(
            f"{novel_id!r} has no recorded build; the current pipeline is version {PIPELINE_VERSION!r}. "
            "Rebuild it (echotales run) before a real render.",
            ErrorCode.STALE_BUILD,
        )
    if build.status == StageStatus.RUNNING:
        return Refusal(
            f"A build of {novel_id!r} is still running; wait for it to finish before a real render.",
            ErrorCode.STALE_BUILD,
        )
    if build.status != StageStatus.SUCCEEDED:
        return Refusal(
            f"The last build of {novel_id!r} did not finish, so its contents are partly rewritten. "
            "Rebuild it (echotales run) before a real render.",
            ErrorCode.STALE_BUILD,
        )
    stamp = build.pipeline_version
    if stamp == PIPELINE_VERSION:
        return None
    seen = f"build stamp {stamp!r}" if stamp else "an unstamped build"
    return Refusal(
        f"{novel_id!r} has {seen}; the current pipeline is version {PIPELINE_VERSION!r}. "
        "Rebuild it (echotales run) before a real render.",
        ErrorCode.STALE_BUILD,
    )
