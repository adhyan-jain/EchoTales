"""A database must carry the stamp of the code that built it, and a stale one is refused for real renders.

Only a SUCCEEDED full build can make a database current; a job's bookkeeping row never does (2026-11: a failing
`export_m4b` job re-stamped a stale database current)."""

import sqlite3
from pathlib import Path

from _builds import record_build, record_job_run
from echotales.core.models import StageStatus
from echotales.core.store import Store
from echotales.pipeline.version import PIPELINE_VERSION, staleness_reason


def test_unrecorded_database_is_stale() -> None:
    store = Store(":memory:")
    assert "no recorded build" in staleness_reason(store, "n")


def test_unstamped_build_is_stale() -> None:
    store = Store(":memory:")
    record_build(store, version="")
    assert "unstamped" in staleness_reason(store, "n")


def test_older_stamp_is_named_in_the_reason() -> None:
    store = Store(":memory:")
    record_build(store, version="1")
    assert "'1'" in staleness_reason(store, "n")


def test_succeeded_current_build_is_current() -> None:  # (d)
    store = Store(":memory:")
    record_build(store)
    assert staleness_reason(store, "n") is None


def test_non_build_job_stamped_current_does_not_cure_a_stale_database() -> None:  # (a)
    store = Store(":memory:")
    record_build(store, version="1")
    record_job_run(store)
    assert "'1'" in staleness_reason(store, "n")


def test_only_job_rows_means_no_recorded_build() -> None:  # (a)
    store = Store(":memory:")
    record_job_run(store)
    assert "no recorded build" in staleness_reason(store, "n")


def test_failed_job_of_any_kind_does_not_cure_a_stale_database() -> None:  # (b)
    store = Store(":memory:")
    record_build(store, version="1")
    record_job_run(store, status=StageStatus.FAILED)
    assert "'1'" in staleness_reason(store, "n")


def test_failed_build_is_not_current() -> None:  # (c)
    store = Store(":memory:")
    record_build(store, status=StageStatus.FAILED)
    assert "did not finish" in staleness_reason(store, "n")


def test_failed_rebuild_over_a_good_build_is_not_current() -> None:  # (c)
    # The failed build had already rewritten part of the graph, so the earlier good stamp no longer describes it.
    store = Store(":memory:")
    record_build(store)
    record_build(store, status=StageStatus.FAILED)
    assert "did not finish" in staleness_reason(store, "n")
    record_build(store)
    assert staleness_reason(store, "n") is None


def test_running_build_is_not_current() -> None:
    store = Store(":memory:")
    record_build(store)
    record_build(store, status=StageStatus.RUNNING)
    assert "still running" in staleness_reason(store, "n")


def test_current_build_followed_by_any_non_build_runs_stays_current() -> None:  # (e)
    store = Store(":memory:")
    record_build(store)
    for status in (StageStatus.SUCCEEDED, StageStatus.FAILED, StageStatus.RUNNING):
        record_job_run(store, status=status)
        record_job_run(store, version="", status=status)
    assert staleness_reason(store, "n") is None


def test_old_stamp_build_then_current_non_build_run_is_still_stale() -> None:  # (f)
    store = Store(":memory:")
    record_build(store, version="1")
    record_job_run(store)
    assert staleness_reason(store, "n") is not None


def test_builds_of_another_novel_do_not_count() -> None:
    store = Store(":memory:")
    record_build(store, "other")
    assert "no recorded build" in staleness_reason(store, "n")


def _legacy_db(path: Path, runs: list[tuple[str, str, str, float, list[str]]]) -> None:
    """A database file in the old shape: `pipeline_run` without `is_build`. runs: (id, version, status, at, stages)."""
    Store(path).close()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE pipeline_run DROP COLUMN is_build")
    for run_id, version, status, at, stages in runs:
        conn.execute(
            "INSERT INTO pipeline_run(run_id, novel_id, source_digest, pipeline_version, created_at, status)"
            " VALUES (?,?,?,?,?,?)", (run_id, "n", "abcdef012345", version, at, status),
        )
        for i, name in enumerate(stages):
            conn.execute(
                "INSERT INTO stage_run(stage_run_id, run_id, stage_name, status) VALUES (?,?,?,?)",
                (f"{run_id}:{name}:{i}", run_id, name, "SUCCEEDED"),
            )
    conn.commit()
    conn.close()


def test_legacy_database_with_a_finished_current_build_is_migrated_current(tmp_path: Path) -> None:  # (g)
    db = tmp_path / "old.db"
    _legacy_db(db, [("n-1", PIPELINE_VERSION, "SUCCEEDED", 1.0, ["0 ingest", "7 personas"])])
    assert staleness_reason(Store(db), "n") is None
    assert staleness_reason(Store(db), "n") is None  # reopening after the migration is idempotent


def test_legacy_database_is_stale_when_only_a_job_row_carries_the_current_stamp(tmp_path: Path) -> None:  # (g)
    db = tmp_path / "old.db"
    _legacy_db(db, [
        ("n-1", "1", "SUCCEEDED", 1.0, ["0 ingest", "7 personas"]),
        ("n-2", PIPELINE_VERSION, "FAILED", 2.0, ["export_m4b"]),
    ])
    assert "'1'" in staleness_reason(Store(db), "n")


def test_legacy_run_without_a_persona_stage_is_not_a_build(tmp_path: Path) -> None:  # (g)
    db = tmp_path / "old.db"
    _legacy_db(db, [("n-1", PIPELINE_VERSION, "SUCCEEDED", 1.0, ["ingest", "resolve"])])
    assert "no recorded build" in staleness_reason(Store(db), "n")
