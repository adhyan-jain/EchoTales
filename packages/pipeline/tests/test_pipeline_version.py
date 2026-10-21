"""A database must carry the stamp of the code that built it, and a stale one is refused for real renders."""

from echotales.core.pipeline_run import ensure_pipeline_run
from echotales.core.store import Store
from echotales.pipeline.version import PIPELINE_VERSION, staleness_reason


def test_unrecorded_database_is_stale() -> None:
    store = Store(":memory:")
    assert "no recorded build" in staleness_reason(store, "n")


def test_unstamped_run_is_stale_until_restamped() -> None:
    store = Store(":memory:")
    ensure_pipeline_run(store, novel_id="n", source_digest="abcdef012345")
    assert "unstamped" in staleness_reason(store, "n")
    # Re-entering the same run with current code re-stamps it.
    ensure_pipeline_run(store, novel_id="n", source_digest="abcdef012345", pipeline_version=PIPELINE_VERSION)
    assert staleness_reason(store, "n") is None


def test_older_stamp_is_named_in_the_reason() -> None:
    store = Store(":memory:")
    ensure_pipeline_run(store, novel_id="n", source_digest="abcdef012345", pipeline_version="1")
    assert "'1'" in staleness_reason(store, "n")
