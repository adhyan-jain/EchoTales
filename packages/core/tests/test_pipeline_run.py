"""Core Pipeline Hardening, session 1: `pipeline_run`/`stage_run`/
`stage_artifact` lifecycle, the input-digest skip check that makes
resumability/cache-invalidation real, and `Store.is_canonical`.
"""

from __future__ import annotations

import json

import pytest
from echotales.core.models import StageStatus
from echotales.core.pipeline_run import (
    ensure_pipeline_run,
    record_artifact,
    source_digest_of,
    stage,
)
from echotales.core.store import Store


def test_ensure_pipeline_run_creates_and_is_idempotent(tmp_path):
    store = Store(str(tmp_path / "t.db"))

    run1 = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123")
    run2 = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123", run_id=run1.run_id)

    assert run1.run_id == run2.run_id
    assert store.get_pipeline_run(run1.run_id) is not None


def test_stage_wrapper_records_succeeded_on_clean_exit(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123")

    with stage(store, run_id=run.run_id, stage_name="ingest", input_digest="d1") as handle:
        assert handle is not None
        did_work = True

    assert did_work
    runs = store.list_stage_runs(run.run_id)
    assert len(runs) == 1
    assert runs[0].status is StageStatus.SUCCEEDED
    assert runs[0].finished_at is not None


def test_stage_wrapper_records_failed_and_reraises(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123")

    with pytest.raises(ValueError, match="boom"):
        with stage(store, run_id=run.run_id, stage_name="resolve", input_digest="d1"):
            raise ValueError("boom")

    runs = store.list_stage_runs(run.run_id)
    assert len(runs) == 1
    assert runs[0].status is StageStatus.FAILED
    assert "boom" in runs[0].error_summary


def test_stage_wrapper_skips_when_input_digest_already_succeeded(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123")

    calls = []
    with stage(store, run_id=run.run_id, stage_name="ingest", input_digest="same") as handle:
        assert handle is not None
        calls.append("ran")

    with stage(store, run_id=run.run_id, stage_name="ingest", input_digest="same") as handle:
        assert handle is None  # short-circuited -- no new work
        # A real caller would `if handle is None: return` here; this test
        # just asserts the signal, not caller behaviour.

    assert calls == ["ran"]
    # Only one stage_run row was ever created -- the skip did not write a
    # second one, "hit" or otherwise silently duplicated.
    assert len(store.list_stage_runs(run.run_id)) == 1


def test_stage_wrapper_does_not_skip_on_differing_input_digest(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123")

    with stage(store, run_id=run.run_id, stage_name="ingest", input_digest="v1"):
        pass
    with stage(store, run_id=run.run_id, stage_name="ingest", input_digest="v2") as handle:
        assert handle is not None  # different input -- must actually run

    assert len(store.list_stage_runs(run.run_id)) == 2


def test_stage_wrapper_does_not_skip_after_a_failed_run(tmp_path):
    """A FAILED stage_run must never satisfy the skip check -- only
    SUCCEEDED does, per the plan's explicit resumability semantics."""
    store = Store(str(tmp_path / "t.db"))
    run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123")

    with pytest.raises(ValueError):
        with stage(store, run_id=run.run_id, stage_name="voice", input_digest="d1"):
            raise ValueError("first attempt failed")

    with stage(store, run_id=run.run_id, stage_name="voice", input_digest="d1") as handle:
        assert handle is not None  # retried, not skipped

    assert len(store.list_stage_runs(run.run_id)) == 2


def test_record_artifact_persists_and_lists(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc123")

    with stage(store, run_id=run.run_id, stage_name="render", input_digest="d1") as handle:
        assert handle is not None
        record_artifact(
            store,
            stage_run_id=handle.stage_run.stage_run_id,
            kind="panel",
            path_or_ref="data/N/panels/ch1/v1/p001.png",
            content_digest="fedcba",
        )
        artifacts = store.list_stage_artifacts(handle.stage_run.stage_run_id)

    assert len(artifacts) == 1
    assert artifacts[0].kind == "panel"
    assert artifacts[0].content_digest == "fedcba"


def test_source_digest_of_is_stable_for_identical_bytes(tmp_path):
    f1 = tmp_path / "a.epub"
    f2 = tmp_path / "b.epub"
    f1.write_bytes(b"same content")
    f2.write_bytes(b"same content")

    assert source_digest_of(f1) == source_digest_of(f2)


def test_source_digest_of_differs_for_different_bytes(tmp_path):
    f1 = tmp_path / "a.epub"
    f2 = tmp_path / "b.epub"
    f1.write_bytes(b"content one")
    f2.write_bytes(b"content two")

    assert source_digest_of(f1) != source_digest_of(f2)


class TestIsCanonical:
    def test_unregistered_db_is_not_canonical(self, tmp_path):
        store = Store(str(tmp_path / "scratch.db"))
        assert store.is_canonical is False

    def test_in_memory_db_is_never_canonical(self):
        store = Store(":memory:")
        assert store.is_canonical is False

    def test_registered_path_is_canonical(self, tmp_path, monkeypatch):
        db_path = tmp_path / "webview-working" / "reverend-insanity.db"
        registry_path = tmp_path / "canonical_dbs.json"
        registry_path.write_text(json.dumps({"paths": [str(db_path)]}))

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Store, "_CANONICAL_REGISTRY", registry_path)

        store = Store(str(db_path))
        assert store.is_canonical is True

    def test_missing_registry_file_means_not_canonical(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no canonical_dbs.json created here
        store = Store(str(tmp_path / "anything.db"))
        assert store.is_canonical is False
