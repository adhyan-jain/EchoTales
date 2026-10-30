"""M4B export plumbing: which tracks, what titles, which engine, and the Studio job (audit B3, B7, M10).

The ffmpeg encode itself is covered where ffmpeg exists (`test_reader_delivery.py`); these run everywhere.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

from echotales.core.models import Job, StageStatus
from echotales.core.store import Store
from echotales.pipeline import jobs
from echotales.pipeline.voice.export import _concat_escape, book_tracks, engine_of


def _wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(16000)
        fh.writeframes(b"\x00\x00" * 1600)
    return path


def test_tracks_are_in_chapter_order_with_the_books_own_titles(tmp_path: Path) -> None:
    for n in (10, 2, 1):
        _wav(tmp_path / f"ch{n}" / "chapter.wav")
    tracks, titles, numbers = book_tracks(tmp_path, {1.0: "The Beginning", 2.0: "Chapter II", 10.0: ""})

    assert numbers == [1.0, 2.0, 10.0]  # numeric, not "ch10" before "ch2"
    assert [t.parent.name for t in tracks] == ["ch1", "ch2", "ch10"]
    assert titles == ["Chapter 1: The Beginning", "Chapter II", "Chapter 10"]


def test_engine_of_reads_the_run_record(tmp_path: Path) -> None:
    assert engine_of(tmp_path) == ""  # audio from before the record existed
    (tmp_path / "run.json").write_text(json.dumps({"engine": "stub"}), encoding="utf-8")
    assert engine_of(tmp_path) == "stub"


def test_an_apostrophe_in_a_path_cannot_break_the_concat_list() -> None:
    assert _concat_escape(Path("/books/Alice's Adventures/ch1/chapter.wav")) == "/books/Alice'\\''s Adventures/ch1/chapter.wav"


def test_the_export_job_refuses_silent_stub_audio_and_an_empty_directory(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "audio"
    monkeypatch.setattr("echotales.pipeline.paths.asset_dir", lambda novel_id, kind: audio)
    store = Store(":memory:")
    store.add_novel("n", "N", "x.epub", "generic")

    def run(params: dict) -> Job:
        job = Job(job_id=f"n:export_m4b:{len(params)}{sorted(params)}", novel_id="n", kind="export_m4b",
                  status=StageStatus.PENDING, created_at=1.0, params_json=json.dumps(params))
        store.add_job(job)
        jobs.run_job(store, job, params)
        return store.get_job(job.job_id)

    empty = run({})
    assert empty.status is StageStatus.FAILED and "no chapter audio" in empty.error_summary

    _wav(audio / "ch1" / "chapter.wav")
    (audio / "run.json").write_text(json.dumps({"engine": "stub"}), encoding="utf-8")
    silent = run({"x": 1})
    assert silent.status is StageStatus.FAILED and "stub" in silent.error_summary
