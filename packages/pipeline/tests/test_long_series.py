"""Long series: chapter-level invalidation and the pre-run time estimate.

A thousand-chapter book cannot be rebuilt because one chapter was re-edited, and cannot be started without
knowing roughly how long it will take. Both read what the pipeline already records: the chapter text itself and the
`stage_run` timings.
"""

from __future__ import annotations

import json

import pytest
from echotales.core.enums import BlockType
from echotales.core.lifecycle import StageStatus
from echotales.core.models import Block, Chapter, Job, StageRun
from echotales.core.store import Store
from echotales.pipeline import long_series as ls


def _book(texts: dict[int, str]) -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    for n, text in texts.items():
        store.add_chapter(Chapter(novel_id="t", number=float(n), title=f"C{n}", source_href=f"{n}.html",
                                  blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)]))
    store.conn.commit()
    return store


def _edit(store: Store, n: int, text: str) -> None:
    store.conn.execute("DELETE FROM chapter WHERE novel_id='t' AND number=?", (float(n),))
    store.add_chapter(Chapter(novel_id="t", number=float(n), title=f"C{n}", source_href=f"{n}.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)]))
    store.conn.commit()


def _make_products(root, *chapters: int) -> None:
    for n in chapters:
        for kind in ("panels", "audio", "video"):
            (root / "novels" / "t" / kind / f"ch{n}" / "v1").mkdir(parents=True)


def test_nothing_is_stale_before_a_baseline_exists_and_right_after_one() -> None:
    store = _book({1: "one", 2: "two"})
    assert ls.changed_chapters(store, "t") == []
    ls.record_baseline(store, "t")
    assert ls.changed_chapters(store, "t") == []


def test_only_the_edited_chapter_is_changed() -> None:
    store = _book({1: "one", 2: "two", 3: "three"})
    ls.record_baseline(store, "t")
    _edit(store, 2, "two, revised")
    assert ls.changed_chapters(store, "t") == [2.0]


def test_a_new_chapter_counts_as_changed() -> None:
    store = _book({1: "one"})
    ls.record_baseline(store, "t")
    _edit(store, 2, "appended")
    assert ls.changed_chapters(store, "t") == [2.0]


def test_invalidation_marks_only_the_changed_chapters_products(tmp_path) -> None:
    store = _book({1: "one", 2: "two"})
    _make_products(tmp_path, 1, 2)
    ls.record_baseline(store, "t")
    _edit(store, 2, "two, revised")

    report = ls.invalidate_changed(store, "t", data_root=tmp_path)

    assert report.chapters == [2.0]
    assert {p.name for p in report.products[2.0]} == {"panels/ch2", "audio/ch2", "video/ch2"}
    assert 1.0 not in report.products
    # Entity resolution and personas read every chapter, so they are stale as a group, not per chapter.
    assert "6 resolve" in report.volume_stages
    assert [c for c, _ in ls.stale_products(store, "t")] == [2.0]


def test_a_rebaseline_clears_the_stale_marks(tmp_path) -> None:
    store = _book({1: "one", 2: "two"})
    _make_products(tmp_path, 2)
    ls.record_baseline(store, "t")
    _edit(store, 2, "two, revised")
    ls.invalidate_changed(store, "t", data_root=tmp_path)
    ls.record_baseline(store, "t")
    assert ls.stale_products(store, "t") == []
    assert ls.changed_chapters(store, "t") == []


def test_invalidation_also_flags_registered_graph_artifacts() -> None:
    store = _book({1: "one", 2: "two"})
    store.record_artifact("a1", "GRAPH", [ls.chapter_ref("t", 2.0)], "h", "{}")
    store.record_artifact("a2", "GRAPH", [ls.chapter_ref("t", 1.0)], "h", "{}")
    ls.record_baseline(store, "t")
    _edit(store, 2, "two, revised")
    report = ls.invalidate_changed(store, "t")
    assert report.artifacts_invalidated == 1
    rows = {r["id"]: r["invalidated"] for r in store.conn.execute("SELECT id, invalidated FROM derived_artifact WHERE id IN ('a1','a2')")}
    assert rows == {"a1": 1, "a2": 0}


# --- estimate ---------------------------------------------------------------


def _timed_stage(store: Store, name: str, seconds: float, *, job_chapters: str | None = None, n: int = 0) -> None:
    run_id = f"run{n}{name}"
    store.conn.execute(
        "INSERT INTO pipeline_run(run_id, novel_id, source_digest) VALUES (?,?,?)", (run_id, "t", "d")
    )
    store.add_stage_run(StageRun(stage_run_id=f"sr{n}{name}", run_id=run_id, stage_name=name, started_at=100.0,
                                 finished_at=100.0 + seconds, status=StageStatus.SUCCEEDED))
    if job_chapters is not None:
        store.add_job(Job(job_id=f"j{n}{name}", novel_id="t", kind=name, run_id=run_id,
                          params_json=json.dumps({"chapters": job_chapters})))
    store.conn.commit()


def test_parse_chapter_spec_selects_among_existing_chapters() -> None:
    assert ls.select_chapters([1.0, 2.0, 3.0, 4.0], "2-3") == [2.0, 3.0]
    assert ls.select_chapters([1.0, 2.0], None) == [1.0, 2.0]


def test_measured_stage_uses_the_seconds_per_chapter_of_its_earlier_run() -> None:
    store = _book({n: f"c{n}" for n in range(1, 11)})
    _timed_stage(store, "render", 60.0, job_chapters="1-2")  # 30 s per chapter
    est = ls.estimate_run(store, "t", "1-10", stages=("render",))
    row = est["stages"][0]
    assert row["basis"] == "measured" and row["seconds_per_chapter"] == pytest.approx(30.0)
    assert row["chapters"] == 10 and row["seconds"] == pytest.approx(300.0)
    assert est["seconds"] == pytest.approx(300.0)


def test_a_whole_novel_stage_run_divides_by_the_chapter_count() -> None:
    store = _book({n: f"c{n}" for n in range(1, 5)})
    _timed_stage(store, "6 resolve", 8.0)  # no chapter range recorded: the run covered all 4 chapters
    est = ls.estimate_run(store, "t", None, stages=("6 resolve",))
    assert est["stages"][0]["seconds_per_chapter"] == pytest.approx(2.0)


def test_without_a_measurement_the_default_is_labelled_an_estimate() -> None:
    store = _book({1: "a", 2: "b"})
    est = ls.estimate_run(store, "t", "1-2", stages=("render",))
    row = est["stages"][0]
    assert row["basis"] == "estimate"
    assert row["seconds_per_chapter"] == ls.DEFAULT_SECONDS_PER_CHAPTER["render"]
    assert est["measured"] is False


def test_cost_is_zero_locally_and_follows_the_hourly_rate_when_given() -> None:
    store = _book({1: "a"})
    assert ls.estimate_run(store, "t", None, stages=("render",))["cost_usd"] == 0.0
    est = ls.estimate_run(store, "t", None, stages=("render",), gpu_hourly_usd=3600.0)
    assert est["cost_usd"] == pytest.approx(est["seconds"])


# --- estimate before the first ingest (P&P e2e defect 5) ---------------------


def test_a_book_not_yet_ingested_is_unknown_not_zero() -> None:
    """The 202 body of `POST .../pipeline` read `chapters: 0` and 0 s for every stage on a new project."""
    est = ls.estimate_run(Store(":memory:"), "t", None, stages=("render",))
    assert est["known"] is False and est["chapters"] is None and est["seconds"] is None and est["cost_usd"] is None
    assert est["stages"][0]["seconds"] is None and "ingest" in est["note"]
    assert "unknown" in ls.format_estimate(est)


def test_the_chapter_count_comes_from_the_uploaded_source_when_nothing_is_ingested(tmp_path) -> None:
    store = Store(":memory:")
    est = ls.estimate_run(store, "t", "1-2", stages=("render",), source_chapters=[1.0, 2.0, 3.0])
    assert est["known"] is True and est["chapters"] == 2
    assert est["stages"][0]["seconds"] == pytest.approx(2 * ls.DEFAULT_SECONDS_PER_CHAPTER["render"])


def test_source_chapter_numbers_reads_the_epub_without_ingesting(tmp_path) -> None:
    assert ls.source_chapter_numbers(tmp_path / "missing.toml", "t") == []
