"""M4B export plumbing: which tracks, what titles, which engine, and the Studio job (audit B3, B7, M10).

The ffmpeg encode itself is covered where ffmpeg exists (`test_reader_delivery.py`); these run everywhere.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

from echotales.core.lifecycle import JobStatus
from echotales.core.models import Job
from echotales.core.store import Store
from echotales.pipeline import jobs
from echotales.pipeline.voice.export import (
    LOUDNESS_LUFS,
    TRUE_PEAK_DB,
    _concat_escape,
    book_tracks,
    engine_of,
    loudnorm_filter,
)
from echotales.pipeline.voice.runner import chapter_track


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
                  status=JobStatus.PENDING, created_at=1.0, params_json=json.dumps(params))
        store.add_job(job)
        jobs.run_job(store, job, params)
        return store.get_job(job.job_id)

    empty = run({})
    assert empty.status is JobStatus.FAILED and "no chapter audio" in empty.error_summary

    _wav(audio / "ch1" / "chapter.wav")
    (audio / "run.json").write_text(json.dumps({"engine": "stub"}), encoding="utf-8")
    silent = run({"x": 1})
    assert silent.status is JobStatus.FAILED and "stub" in silent.error_summary


def test_loudnorm_filter_single_and_two_pass() -> None:
    single = loudnorm_filter()
    assert single == f"loudnorm=I={LOUDNESS_LUFS}:TP={TRUE_PEAK_DB}:LRA=11"
    assert LOUDNESS_LUFS == -16.0
    assert TRUE_PEAK_DB == -1.5

    measured = {
        "input_i": "-22.5",
        "input_tp": "-3.1",
        "input_lra": "7.5",
        "input_thresh": "-32.5",
        "target_offset": "0.1",
    }
    two_pass = loudnorm_filter(measured)
    assert "measured_I=-22.5" in two_pass
    assert "measured_TP=-3.1" in two_pass
    assert "linear=true" in two_pass


def test_chapter_track_with_loudness_mastering(tmp_path: Path) -> None:
    c1 = _wav(tmp_path / "c1.wav")
    c2 = _wav(tmp_path / "c2.wav")
    out = tmp_path / "ch_mastered.wav"
    res = chapter_track([c1, c2], out, master_loudness=True)
    assert res.exists()
    assert res == out
    with wave.open(str(res), "rb") as fh:
        assert fh.getnframes() > 0

