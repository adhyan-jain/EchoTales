"""Unit tests for Phase P6 Quality Evaluation Gate (eval/evaluation_gate.py)."""

from __future__ import annotations

import wave
from pathlib import Path

from echotales.pipeline.voice.export import normalise_chapter_track

from eval.evaluation_gate import (
    check_audio_loudness,
    check_cast_gender,
    check_panel_density,
    resolve_name_gender,
    run_evaluation_gates,
)


def _tone_wav(path: Path, seconds: float = 2.0, sr: int = 24000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        # Moderate amplitude sine-like square tone
        fh.writeframes(b"\x20\x00\xe0\xff" * int(sr * seconds / 2))
    return path


def test_density_gate_pass_and_fail_boundaries() -> None:
    # 2400 words, 53 panels -> 2.21 panels / 100 words (near 2.20 reference)
    res_pass = check_panel_density(2400, 53)
    assert res_pass.passed is True
    assert 1.65 <= res_pass.panels_per_100_words <= 2.75

    # Exactly on lower and upper boundaries
    res_low = check_panel_density(10000, 165)
    assert res_low.passed is True

    res_high = check_panel_density(10000, 275)
    assert res_high.passed is True

    # Too dense (> 2.75)
    res_dense = check_panel_density(1000, 35)
    assert res_dense.passed is False

    # Too sparse (< 1.65)
    res_sparse = check_panel_density(1000, 10)
    assert res_sparse.passed is False

    # Invalid word count
    res_zero = check_panel_density(0, 10)
    assert res_zero.passed is False


def test_cast_gender_canonical_zero_errors() -> None:
    # The default checks all main cast members for RI and P&P
    res = check_cast_gender()
    assert res.passed is True
    assert res.error_count == 0
    assert res.checked_count >= 30


def test_cast_gender_catches_intentional_mismatch() -> None:
    # Override with a deliberate gender error
    bad_override = {
        "pride-and-prejudice": {
            "Mr. Bennet": "female",  # wrong
            "Mrs. Bennet": "female",
        }
    }
    res = check_cast_gender(bad_override)
    assert res.passed is False
    assert res.error_count == 1
    assert "resolved as male, expected female" in res.errors[0]


def test_resolve_name_gender_priorities() -> None:
    # Xianxia morphemes
    assert resolve_name_gender("Fang Yuan") == "male"
    assert resolve_name_gender("Gu Yue Bo") == "male"
    assert resolve_name_gender("Shen Cui") == "female"
    assert resolve_name_gender("Fang Zheng") == "male"

    # English titles
    assert resolve_name_gender("Mr. Bennet") == "male"
    assert resolve_name_gender("Mrs. Bennet") == "female"
    assert resolve_name_gender("Lady Catherine") == "female"

    # Western first-names
    assert resolve_name_gender("Elizabeth") == "female"
    assert resolve_name_gender("Charles Bingley") == "male"


def test_audio_loudness_gate_missing_file() -> None:
    res = check_audio_loudness(Path("/tmp/non_existent_audio_file_123.wav"))
    assert res.passed is False
    assert "not found" in res.message


def test_audio_loudness_gate_with_mastered_audio(tmp_path: Path) -> None:
    raw_wav = _tone_wav(tmp_path / "raw.wav", seconds=3.0)
    mastered = tmp_path / "mastered.wav"
    normalise_chapter_track(raw_wav, mastered, target_lufs=-16.0, true_peak=-1.5)

    res = check_audio_loudness(mastered, target_lufs=-16.0, tolerance_lu=1.0)
    assert res.passed is True
    assert res.integrated_lufs is not None
    assert abs(res.integrated_lufs - (-16.0)) <= 1.0
    assert res.true_peak_db is not None
    assert res.true_peak_db <= -1.3  # with margin


def test_run_evaluation_gates_full_report() -> None:
    report = run_evaluation_gates(word_count=2400, panel_count=53, audio_path=None)
    assert report.all_passed is True
    summary = report.summary()
    assert "ALL GATES PASSED" in summary
    assert "1. Panel Density Gate:    PASS" in summary
    assert "2. Cast Gender Gate:      PASS" in summary
    assert "3. Audio Loudness Gate:   PASS" in summary
