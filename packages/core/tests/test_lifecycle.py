"""The job, stage-run and pipeline-run lifecycles are declared data, and the store enforces them atomically."""

from __future__ import annotations

import pytest
from echotales.core.lifecycle import (
    JOB_TERMINAL,
    JOB_TRANSITIONS,
    RUN_TRANSITIONS,
    STAGE_TERMINAL,
    STAGE_TRANSITIONS,
    IllegalTransition,
    JobStatus,
    StageStatus,
    check_transition,
)
from echotales.core.models import Job
from echotales.core.pipeline_run import ensure_pipeline_run, stage
from echotales.core.store import Store
from hypothesis import given
from hypothesis import strategies as st


def _store_with_job(status: JobStatus = JobStatus.PENDING) -> Store:
    store = Store(":memory:")
    store.add_job(Job(job_id="j", novel_id="n", kind="ingest", status=status, created_at=1.0))
    return store


class TestTables:
    def test_every_state_has_a_row_and_targets_are_states(self) -> None:
        for table, enum in ((JOB_TRANSITIONS, JobStatus), (STAGE_TRANSITIONS, StageStatus), (RUN_TRANSITIONS, StageStatus)):
            assert set(table) == set(enum)
            assert all(to <= set(enum) for to in table.values())

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            (JobStatus.RUNNING, JobStatus.CANCELLED),  # a running stage cannot be stopped safely
            (JobStatus.PENDING, JobStatus.SUCCEEDED),  # never ran
            (JobStatus.SUCCEEDED, JobStatus.FAILED),
            (JobStatus.CANCELLED, JobStatus.RUNNING),
            (JobStatus.INTERRUPTED, JobStatus.PENDING),
            (JobStatus.PENDING, JobStatus.PENDING),
        ],
    )
    def test_illegal_job_moves_are_rejected_naming_both_states(self, old: JobStatus, new: JobStatus) -> None:
        with pytest.raises(IllegalTransition, match=f"{old.value} -> {new.value}"):
            check_transition(JOB_TRANSITIONS, old, new)

    def test_legal_moves_pass(self) -> None:
        check_transition(JOB_TRANSITIONS, JobStatus.PENDING, JobStatus.CANCELLED)
        check_transition(STAGE_TRANSITIONS, StageStatus.RUNNING, StageStatus.PARTIAL)

    def test_a_stage_run_has_no_cancelled_or_interrupted_state(self) -> None:
        assert "CANCELLED" not in StageStatus.__members__ and "INTERRUPTED" not in StageStatus.__members__
        assert JobStatus.CANCELLED in JOB_TERMINAL and StageStatus.RUNNING not in STAGE_TERMINAL

    def test_a_finished_run_may_be_reentered_as_a_rebuild_but_a_finished_stage_may_not(self) -> None:
        check_transition(RUN_TRANSITIONS, StageStatus.SUCCEEDED, StageStatus.RUNNING)
        with pytest.raises(IllegalTransition):
            check_transition(STAGE_TRANSITIONS, StageStatus.SUCCEEDED, StageStatus.RUNNING)

    def test_old_rows_with_the_legacy_vocabulary_still_load(self) -> None:
        store = Store(":memory:")
        for i, legacy in enumerate(("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL")):
            store.conn.execute(
                "INSERT INTO job(job_id, novel_id, kind, run_id, status, params_json, created_at, error_summary)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (f"old{i}", "n", "ingest", "", legacy, "{}", float(i), ""),
            )
        assert {j.status.value for j in store.list_jobs("n")} == {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL"}


class TestCompareAndSet:
    def test_moves_only_from_an_expected_state(self) -> None:
        store = _store_with_job()
        assert store.transition_job("j", [JobStatus.PENDING], JobStatus.RUNNING, started_at=5.0)
        assert not store.transition_job("j", [JobStatus.PENDING], JobStatus.CANCELLED)
        job = store.get_job("j")
        assert job.status is JobStatus.RUNNING and job.started_at == 5.0 and job.finished_at is None

    def test_a_pair_the_table_forbids_raises_and_writes_nothing(self) -> None:
        store = _store_with_job()
        with pytest.raises(IllegalTransition):
            store.transition_job("j", [JobStatus.PENDING], JobStatus.SUCCEEDED)
        assert store.get_job("j").status is JobStatus.PENDING

    def test_update_job_cannot_set_status(self) -> None:
        with pytest.raises(TypeError):
            _store_with_job().update_job("j", status=JobStatus.FAILED)  # type: ignore[call-arg]

    @given(st.lists(st.tuples(st.sampled_from(list(JobStatus)), st.sampled_from(list(JobStatus))), max_size=40))
    def test_random_attempts_never_reach_an_undeclared_state_nor_leave_a_terminal_one(
        self, attempts: list[tuple[JobStatus, JobStatus]]
    ) -> None:
        store = _store_with_job()
        for expected, new in attempts:
            before = store.get_job("j").status
            try:
                moved = store.transition_job("j", [expected], new)
            except IllegalTransition:
                moved = False
            after = store.get_job("j").status
            assert after in JobStatus
            if before in JOB_TERMINAL:
                assert after is before
            if moved:
                assert before is expected and new in JOB_TRANSITIONS[before]
            else:
                assert after is before


class TestInterruptBookkeeping:
    def test_keyboard_interrupt_inside_a_stage_closes_it(self) -> None:
        store = Store(":memory:")
        run = ensure_pipeline_run(store, novel_id="n", source_digest="abc")
        with pytest.raises(KeyboardInterrupt), stage(store, run_id=run.run_id, stage_name="s", input_digest="d"):
            raise KeyboardInterrupt
        (row,) = store.list_stage_runs(run.run_id)
        assert row.status is StageStatus.FAILED and "KeyboardInterrupt" in row.error_summary
        assert row.finished_at is not None
