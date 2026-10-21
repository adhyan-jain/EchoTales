"""Minimal, synchronous pipeline-run/stage-run orchestration.

Every EchoTales stage today runs as a separate CLI subcommand / separate OS
process, opening its own `Store(db_path)` with no shared in-process state
between stages (`commands.py`). That isolation is good; the gap is that
nothing records what actually happened -- a crash mid-stage leaves no trace
of how far it got, a rerun always redoes full work even when nothing
upstream changed, and there is no way to ask "did this stage's output
actually come from a specific completed run" without recomputing everything.

This module is deliberately a thin wrapper, not a rewrite: it does not touch
any existing stage function's signature or internal logic. It wraps a stage
invocation with start/finish bookkeeping against the `pipeline_run`/
`stage_run`/`stage_artifact` tables (`store.py`) so that resumability, cache
invalidation and provenance become real without a queue, a scheduler, or any
new infrastructure -- local, SQLite-backed, synchronous.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from echotales.core.models import PipelineRun, StageArtifact, StageRun, StageStatus
from echotales.core.store import Store


def digest_bytes(data: bytes) -> str:
    """Short, stable content digest. Truncated to 16 hex chars (64 bits) --
    collision risk is irrelevant here (it only gates a skip-or-rerun
    decision, never identity), and a short digest keeps run_id/stage_run_id
    strings human-legible in logs and `stage_run` listings."""
    return hashlib.sha256(data).hexdigest()[:16]


def digest_text(text: str) -> str:
    return digest_bytes(text.encode("utf-8"))


def source_digest_of(path: Path | str) -> str:
    """sha256 of a source file's bytes (e.g. the EPUB) -- already-available
    `hashlib`, no new dependency, matches the approved plan's exact choice."""
    return digest_bytes(Path(path).read_bytes())


def new_run_id(novel_id: str, source_digest: str, *, at: float | None = None) -> str:
    """`f"{novel_id}-{utc_timestamp}-{short_source_digest}"` -- human-legible
    and stable, never a DB auto-increment id or a process-randomized UUID."""
    ts = int(at if at is not None else time.time())
    return f"{novel_id}-{ts}-{source_digest[:8]}"


def new_stage_run_id(run_id: str, stage_name: str) -> str:
    """Unique per invocation (a stage can legitimately run more than once
    within one `run_id`, e.g. a retry) -- the uniqueness comes from a short
    random suffix, not from any DB-assigned counter."""
    return f"{run_id}:{stage_name}:{uuid.uuid4().hex[:8]}"


def new_artifact_id(stage_run_id: str, kind: str, seq: int) -> str:
    return f"{stage_run_id}:{kind}:{seq}"


class PartialStageFailure(Exception):
    """Raise this (or a subclass) from inside a stage's own per-chunk loop
    to tell the `stage()` wrapper below that real, committed progress
    happened before the failure -- e.g. `resolve_novel`'s per-chapter
    commit boundary. The `stage()` wrapper checks for this type and records
    `PARTIAL` instead of `FAILED`, so "12/40 chapters done" survives in
    `stage_run.error_summary` instead of looking identical to zero
    progress. Any other exception still means `FAILED`, since most stages
    (persona/world/appearance today) have no chunk boundary of their own
    yet and an unqualified exception should not be guessed at as partial.
    """

    def __init__(self, message: str, *, progress: str = "") -> None:
        super().__init__(message)
        self.progress = progress


@dataclass(slots=True)
class StageHandle:
    """Returned by `start_stage`; pass to `finish_stage` (directly, or via
    the `stage` context manager below)."""

    stage_run: StageRun


def start_stage(
    store: Store,
    *,
    run_id: str,
    stage_name: str,
    input_digest: str,
    config_json: str = "{}",
    parent_stage_run_ids: list[str] | None = None,
) -> StageHandle:
    stage_run = StageRun(
        stage_run_id=new_stage_run_id(run_id, stage_name),
        run_id=run_id,
        stage_name=stage_name,
        input_digest=input_digest,
        config_json=config_json,
        started_at=time.time(),
        status=StageStatus.RUNNING,
        parent_stage_run_ids=parent_stage_run_ids or [],
    )
    store.add_stage_run(stage_run)
    return StageHandle(stage_run=stage_run)


def finish_stage(
    store: Store,
    handle: StageHandle,
    *,
    status: StageStatus,
    output_digest: str = "",
    error_summary: str = "",
) -> None:
    store.update_stage_run(
        handle.stage_run.stage_run_id,
        status=status,
        finished_at=time.time(),
        output_digest=output_digest,
        error_summary=error_summary,
    )


@contextmanager
def stage(
    store: Store,
    *,
    run_id: str,
    stage_name: str,
    input_digest: str,
    config_json: str = "{}",
    parent_stage_run_ids: list[str] | None = None,
    skip_if_succeeded: bool = True,
) -> Iterator[StageHandle | None]:
    """Wrap one stage invocation.

    Yields `None` (and does no work) when a `SUCCEEDED` `stage_run` already
    exists for this exact `(stage_name, input_digest)` pair and
    `skip_if_succeeded` is true -- the generalized form of the render
    pipeline's own `cache_index.json` skip check, applied to every stage.
    Otherwise yields a `StageHandle`; the caller does its real work, and on
    a clean exit this records `SUCCEEDED`, while an exception records
    `FAILED` with the exception's message as `error_summary` and re-raises
    (never swallows a failure -- the whole point is an accurate record, not
    a quieter one).

    Does not attempt partial-chunk `PARTIAL` status here -- a stage that
    wants that granularity (per-chapter commit loops such as
    `resolve_novel`) records it directly via `finish_stage`, since only the
    stage itself knows where its own chunk boundaries are.
    """
    if skip_if_succeeded:
        existing = store.find_succeeded_stage_run(stage_name, input_digest)
        if existing is not None:
            yield None
            return
    handle = start_stage(
        store,
        run_id=run_id,
        stage_name=stage_name,
        input_digest=input_digest,
        config_json=config_json,
        parent_stage_run_ids=parent_stage_run_ids,
    )
    try:
        yield handle
    except PartialStageFailure as exc:
        summary = str(exc) + (f" (progress: {exc.progress})" if exc.progress else "")
        finish_stage(store, handle, status=StageStatus.PARTIAL, error_summary=summary)
        raise
    except Exception as exc:
        finish_stage(store, handle, status=StageStatus.FAILED, error_summary=str(exc))
        raise
    else:
        finish_stage(store, handle, status=StageStatus.SUCCEEDED)


def ensure_pipeline_run(
    store: Store,
    *,
    novel_id: str,
    source_digest: str,
    run_id: str | None = None,
    pipeline_version: str = "",
) -> PipelineRun:
    """Fetch an existing `pipeline_run` row or create one. Idempotent by
    `run_id` so re-entering the same run (e.g. resuming a chained stage
    sequence) never duplicates the row.

    `pipeline_version` was never set before 2026-10-22, so every database in
    `data/db/` carried an empty stamp and a build made before the speaker-join
    fix was indistinguishable from a current one (audit: LotM personas built
    from "0 spoken lines"). A re-entered run is re-stamped to the version now
    executing, so the stamp always names the newest code that touched it."""
    rid = run_id or new_run_id(novel_id, source_digest)
    existing = store.get_pipeline_run(rid)
    if existing is not None:
        if pipeline_version and existing.pipeline_version != pipeline_version:
            store.set_pipeline_run_version(rid, pipeline_version)
            existing.pipeline_version = pipeline_version
        return existing
    run = PipelineRun(
        run_id=rid,
        novel_id=novel_id,
        source_digest=source_digest,
        created_at=time.time(),
        status=StageStatus.RUNNING,
        pipeline_version=pipeline_version,
    )
    store.add_pipeline_run(run)
    return run


def record_artifact(
    store: Store, *, stage_run_id: str, kind: str, path_or_ref: str, content_digest: str = ""
) -> StageArtifact:
    existing = store.list_stage_artifacts(stage_run_id)
    artifact = StageArtifact(
        artifact_id=new_artifact_id(stage_run_id, kind, len(existing)),
        stage_run_id=stage_run_id,
        kind=kind,
        path_or_ref=path_or_ref,
        content_digest=content_digest,
        created_at=time.time(),
    )
    store.add_stage_artifact(artifact)
    return artifact
