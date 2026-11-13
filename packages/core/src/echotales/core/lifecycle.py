"""Which state changes are legal for a job, a stage run and a pipeline run.

The three lifecycles used to be implicit: any code could write any status, so a user's cancel and a
worker's SUCCEEDED could overwrite each other and a killed process left RUNNING rows that read as
live work forever (EVOLUTION: job lifecycle audit). Here the legal moves are data, one table per
machine, and `check_transition` is the only judge. Nothing else lives in this module; the store
applies the tables atomically (`Store.transition_job`).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class StageStatus(StrEnum):
    """Lifecycle of one `StageRun` (and of a `PipelineRun`, which ends the same ways).

    `RUNNING` with no terminal transition is how a killed process is
    detected on the next invocation: a `stage_run` row stuck at `RUNNING`
    was never finalized, so a resume check must treat it as "needs rerun",
    never as "already done" (a `SUCCEEDED`/`FAILED`/`PARTIAL` input-digest
    match is the only thing allowed to short-circuit re-execution).

    Deliberately has no CANCELLED or INTERRUPTED: a stage is one call that either returns or
    raises, and an interrupted one is recorded FAILED with the reason in `error_summary`. Those
    two outcomes exist only for a `Job`, which can be refused before it starts (`JobStatus`).
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    #: At least one commit-chunk succeeded before failure -- distinct from
    #: FAILED so "12/40 chapters done" is visible instead of indistinguishable
    #: from a run that made zero progress.
    PARTIAL = "PARTIAL"


class JobStatus(StrEnum):
    """Lifecycle of one HTTP-triggered `Job`. A closed vocabulary: the Studio client renders each value.

    A separate enum rather than two new `StageStatus` members, so a stage run can never be
    CANCELLED (a stage cannot be refused before it starts) and the old values keep their meaning
    in existing databases. Old rows load unchanged: their TEXT is a subset of these values.
    """

    #: Queued; the only state a user may cancel from.
    PENDING = "PENDING"
    #: Claimed by the worker. Not cancellable: stopping a thread mid-write could corrupt the database.
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    #: Some commit-chunks landed before the failure (see `StageStatus.PARTIAL`).
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    #: A user withdrew a queued job before the worker claimed it. Distinct from FAILED so a refusal
    #: by the user is not counted as a defect (both used to read FAILED, told apart only by text).
    CANCELLED = "CANCELLED"
    #: The server stopped (restart sweep or process signal) while the job was queued or running. The
    #: work may be partly done; distinct from FAILED because rerunning is the right response, not debugging.
    INTERRUPTED = "INTERRUPTED"


class IllegalTransition(ValueError):
    """A status change the lifecycle table does not allow."""

    def __init__(self, old: StrEnum, new: StrEnum) -> None:
        super().__init__(f"illegal transition {old.value} -> {new.value}")
        self.old = old
        self.new = new


_NONE: frozenset = frozenset()

JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.INTERRUPTED}),
    JobStatus.RUNNING: frozenset(
        {JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.INTERRUPTED}
    ),
    JobStatus.SUCCEEDED: _NONE,
    JobStatus.PARTIAL: _NONE,
    JobStatus.FAILED: _NONE,
    JobStatus.CANCELLED: _NONE,
    JobStatus.INTERRUPTED: _NONE,
}
JOB_TERMINAL: frozenset[JobStatus] = frozenset(s for s, to in JOB_TRANSITIONS.items() if not to)
#: A job a restart or a delete must account for.
JOB_UNFINISHED: frozenset[JobStatus] = frozenset({JobStatus.PENDING, JobStatus.RUNNING})

_STAGE_ENDS = frozenset({StageStatus.SUCCEEDED, StageStatus.FAILED, StageStatus.PARTIAL})

STAGE_TRANSITIONS: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.PENDING: frozenset({StageStatus.RUNNING}),
    StageStatus.RUNNING: _STAGE_ENDS,
    StageStatus.SUCCEEDED: _NONE,
    StageStatus.FAILED: _NONE,
    StageStatus.PARTIAL: _NONE,
}
STAGE_TERMINAL: frozenset[StageStatus] = frozenset(s for s, to in STAGE_TRANSITIONS.items() if not to)

#: A pipeline run ends like a stage, but a finished run may go back to RUNNING: `ensure_pipeline_run`
#: re-enters a run as a rebuild so it cannot read SUCCEEDED while it rewrites the graph.
RUN_TRANSITIONS: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.PENDING: frozenset({StageStatus.RUNNING}),
    StageStatus.RUNNING: _STAGE_ENDS,
    StageStatus.SUCCEEDED: frozenset({StageStatus.RUNNING}),
    StageStatus.FAILED: frozenset({StageStatus.RUNNING}),
    StageStatus.PARTIAL: frozenset({StageStatus.RUNNING}),
}


def check_transition[S: StrEnum](table: Mapping[S, frozenset[S]], old: S, new: S) -> None:
    """Raise `IllegalTransition` unless `table` lists `old -> new`."""
    if new not in table.get(old, frozenset()):
        raise IllegalTransition(old, new)
