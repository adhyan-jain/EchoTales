"""Product Orchestration track: `jobs.py`'s worker/dispatch layer.

Runs entirely against synthetic fixtures (a tiny in-memory EPUB, a temp
`sources.toml`) so CI needs no GPU, no network, and none of the real novels
under `data/raw/` -- same convention `test_ingest.py` already uses.
"""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest
from echotales.core.models import Job, StageStatus
from echotales.core.store import Store
from echotales.pipeline.jobs import ALLOWED_HTTP_ENGINES, JobQueue, new_job_id, run_job, run_stage


def _build_epub(path: Path) -> Path:
    """Minimal valid single-chapter EPUB -- same shape as
    `test_ingest.py::build_epub`, inlined here to avoid a cross-test-module
    import dependency."""
    docs = {
        "page-0.html": (
            '<div class="chapter type-1"><div class="chapter-title-wrap">'
            '<h2 class="chapter-title">Chapter 1: First</h2></div>'
            '<div class="ugc chapter-ugc"><p><strong>Chapter 1 - First</strong></p>'
            "<p>Opening narration.</p></div></div>"
        )
    }
    toc = [("Chapter 1: First", "page-0.html")]
    nav = "".join(
        f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{label}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, (label, href) in enumerate(toc)
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f"<docTitle><text>Test</text></docTitle><navMap>{nav}</navMap></ncx>"
    )
    manifest = "".join(
        f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, href in enumerate(docs)
    )
    spine = "".join(f'<itemref idref="d{i}"/>' for i in range(len(docs)))
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Novel</dc:title><dc:language>en</dc:language>"
        '<dc:identifier id="id">test</dc:identifier></metadata>'
        f'<manifest>{manifest}<item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{spine}</spine></package>'
    )
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="book.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("book.opf", opf)
        z.writestr("toc.ncx", ncx)
        for href, body in docs.items():
            z.writestr(href, f"<html><body>{body}</body></html>")
    return path


def _write_sources_toml(path: Path, *, novel_id: str, epub_path: Path) -> Path:
    path.write_text(
        f'[[novel]]\nid = "{novel_id}"\ntitle = "Test Novel"\n'
        f'path = "{epub_path}"\nadapter = "lightnovelworld"\n'
    )
    return path


class TestEngineAllowlist:
    def test_paid_engines_excluded(self) -> None:
        assert "gemini" not in ALLOWED_HTTP_ENGINES
        assert "openrouter" not in ALLOWED_HTTP_ENGINES

    def test_local_engines_allowed(self) -> None:
        assert {"stub", "sdxl", "illustrious", "noobai", "refined", "manga"} == ALLOWED_HTTP_ENGINES


class TestRunStageResumability:
    """`run_stage` is the one code path `cmd_run` and `run_job` share --
    confirm it has the same skip/fail semantics `pipeline_run.py::stage()`
    already proves, since it wraps that same bookkeeping."""

    def test_records_succeeded_and_runs_fn(self, tmp_path: Path) -> None:
        from echotales.core.pipeline_run import ensure_pipeline_run

        store = Store(str(tmp_path / "t.db"))
        run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc")
        calls = []
        result = run_stage(
            store, run_id=run.run_id, stage_name="ingest", input_digest="d1",
            fn=lambda: calls.append(1) or "done",
        )
        assert result == "done"
        assert calls == [1]
        runs = store.list_stage_runs(run.run_id)
        assert runs[0].status == StageStatus.SUCCEEDED

    def test_skips_when_succeeded_run_already_matches_digest(self, tmp_path: Path) -> None:
        from echotales.core.pipeline_run import ensure_pipeline_run

        store = Store(str(tmp_path / "t.db"))
        run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc")
        calls = []
        run_stage(
            store, run_id=run.run_id, stage_name="ingest", input_digest="same",
            fn=lambda: calls.append(1),
        )
        result = run_stage(
            store, run_id=run.run_id, stage_name="ingest", input_digest="same",
            fn=lambda: calls.append(2),
        )
        assert calls == [1]  # second call skipped entirely -- fn never ran
        assert result is None

    def test_records_failed_and_reraises(self, tmp_path: Path) -> None:
        from echotales.core.pipeline_run import ensure_pipeline_run

        store = Store(str(tmp_path / "t.db"))
        run = ensure_pipeline_run(store, novel_id="n1", source_digest="abc")

        def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError):
            run_stage(store, run_id=run.run_id, stage_name="resolve", input_digest="d2", fn=boom)
        runs = store.list_stage_runs(run.run_id)
        assert runs[0].status == StageStatus.FAILED
        assert "kaboom" in runs[0].error_summary


class TestRunJobIngest:
    """End-to-end: a real `ingest` job against a synthetic EPUB + a
    per-project `sources.toml`, exactly the shape the upload route writes
    (see the plan's Section 3/jobs.py's `sources_path` handling)."""

    def test_ingest_job_runs_and_records_success(self, tmp_path: Path) -> None:
        epub = _build_epub(tmp_path / "novel.epub")
        sources_path = _write_sources_toml(
            tmp_path / "sources.toml", novel_id="testnovel", epub_path=epub
        )
        store = Store(str(tmp_path / "t.db"))
        job = Job(
            job_id=new_job_id("testnovel", "ingest"),
            novel_id="testnovel",
            kind="ingest",
            params_json="{}",
            created_at=time.time(),
        )
        store.add_job(job)

        run_job(store, job, {"sources_path": str(sources_path)})

        updated = store.get_job(job.job_id)
        assert updated.status == StageStatus.SUCCEEDED
        assert updated.run_id
        assert store.chapter_numbers("testnovel") == [1.0]

    def test_unknown_kind_records_failed_not_raise(self, tmp_path: Path) -> None:
        store = Store(str(tmp_path / "t.db"))
        job = Job(
            job_id=new_job_id("n1", "bogus"), novel_id="n1", kind="bogus", created_at=time.time()
        )
        store.add_job(job)

        run_job(store, job, {})  # must not raise -- failure is recorded, not propagated

        updated = store.get_job(job.job_id)
        assert updated.status == StageStatus.FAILED
        assert "bogus" in updated.error_summary


class TestJobQueue:
    def test_submits_and_runs_sequentially(self, tmp_path: Path) -> None:
        epub = _build_epub(tmp_path / "novel.epub")
        sources_path = _write_sources_toml(
            tmp_path / "sources.toml", novel_id="testnovel", epub_path=epub
        )
        db_path = str(tmp_path / "t.db")
        store = Store(db_path)
        job = Job(
            job_id=new_job_id("testnovel", "ingest"),
            novel_id="testnovel",
            kind="ingest",
            created_at=time.time(),
        )
        store.add_job(job)
        store.close()

        q = JobQueue()
        q.start()
        q.submit(
            job_id=job.job_id, novel_id="testnovel", db_path=db_path,
            params={"sources_path": str(sources_path)},
        )
        q._q.join()  # test-only: block until the worker drains the queue

        check = Store(db_path)
        updated = check.get_job(job.job_id)
        assert updated.status == StageStatus.SUCCEEDED
