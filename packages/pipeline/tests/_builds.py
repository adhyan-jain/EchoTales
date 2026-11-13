"""Test setup for 'this database was built': only a full build counts toward `staleness_reason`."""

from __future__ import annotations

import uuid

from echotales.core.models import StageStatus
from echotales.core.pipeline_run import ensure_pipeline_run
from echotales.core.store import Store
from echotales.pipeline.version import PIPELINE_VERSION


def record_build(
    store: Store,
    novel_id: str = "n",
    *,
    version: str = PIPELINE_VERSION,
    status: StageStatus = StageStatus.SUCCEEDED,
) -> str:
    """A full build as `echotales run` / the `pipeline` job records it. Unique run id: two in one second must not merge."""
    run = ensure_pipeline_run(
        store, novel_id=novel_id, source_digest="abcdef012345", run_id=f"{novel_id}-b-{uuid.uuid4().hex[:8]}",
        pipeline_version=version, is_build=True,
    )
    store.update_pipeline_run_status(run.run_id, status)
    return run.run_id


def record_job_run(
    store: Store,
    novel_id: str = "n",
    *,
    version: str = PIPELINE_VERSION,
    status: StageStatus = StageStatus.SUCCEEDED,
) -> str:
    """The row `jobs._dispatch` makes for any non-build job (render, voice, export_m4b, ...)."""
    run = ensure_pipeline_run(
        store, novel_id=novel_id, source_digest="abcdef012345", run_id=f"{novel_id}-j-{uuid.uuid4().hex[:8]}",
        pipeline_version=version,
    )
    store.update_pipeline_run_status(run.run_id, status)
    return run.run_id
