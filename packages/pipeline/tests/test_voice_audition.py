"""Narrator audition: crude acoustic measures on synthetic signals, the shortlist rule, and the index page.

Nothing here synthesises speech; the `--synthesize` path takes any engine, and a stub engine is enough to check the
files and the page it produces.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from echotales.pipeline.voice.audition import (
    PASSAGES,
    ClipStats,
    measure_array,
    shortlist,
    synthesize_audition,
)
from echotales.pipeline.voice.bank import BankVoice, VoiceBank
from echotales.pipeline.voice.engine import get_engine

SR = 16000


def _voiced(f0: float, seconds: float = 6.0, syll_hz: float = 4.0, noise: float = 0.0, seed: int = 0) -> np.ndarray:
    """Harmonic 'speech': a pulse-train-like tone at `f0`, amplitude-modulated into syllables, plus white noise."""
    t = np.arange(int(SR * seconds)) / SR
    carrier = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    env = 0.5 * (1 + np.sin(2 * np.pi * syll_hz * t - np.pi / 2)) ** 2
    rng = np.random.default_rng(seed)
    return (0.2 * carrier * env + noise * rng.standard_normal(len(t))).astype("float32")


def test_f0_snr_and_rate_are_measured_from_the_signal() -> None:
    s = measure_array(_voiced(120.0, noise=0.0005), SR)
    assert s.f0_hz == pytest.approx(120.0, rel=0.06)
    assert s.snr_db > 40
    assert s.rate_hz == pytest.approx(4.0, abs=0.8)


def test_noise_lowers_snr_and_faster_syllables_raise_rate() -> None:
    clean = measure_array(_voiced(120.0, noise=0.0005), SR)
    noisy = measure_array(_voiced(120.0, noise=0.02), SR)
    fast = measure_array(_voiced(120.0, syll_hz=6.0, noise=0.0005), SR)
    assert noisy.snr_db < clean.snr_db - 15
    assert fast.rate_hz > clean.rate_hz + 1.0


def _stat(vid: str, gender: str, f0: float, snr: float = 45.0, rate: float = 4.0) -> ClipStats:
    return ClipStats(voice_id=vid, bank="b", licence="CC BY 4.0", gender=gender, name=vid, clip="x.wav",
                     f0_hz=f0, snr_db=snr, rate_hz=rate, seconds=10.0)


def test_shortlist_drops_noisy_unreadable_and_off_pace_clips() -> None:
    pool = [
        _stat("ok", "male", 110),
        _stat("noisy", "male", 120, snr=12),
        _stat("fast", "male", 130, rate=9.0),
        _stat("slow", "male", 140, rate=0.8),
        _stat("nof0", "male", 0.0),
    ]
    pool[-1].f0_hz = None
    assert [c.voice_id for c in shortlist(pool, 12)] == ["ok"]


def test_shortlist_balances_gender_and_spreads_pitch() -> None:
    men = [_stat(f"m{i}", "male", 85 + 5 * i) for i in range(12)]  # 85..140 Hz, evenly
    women = [_stat(f"f{i}", "female", 170 + 8 * i) for i in range(12)]
    picked = shortlist(men + women, 6)
    assert sorted(c.gender for c in picked) == ["female"] * 3 + ["male"] * 3
    male_f0 = sorted(c.f0_hz for c in picked if c.gender == "male")
    assert male_f0[-1] - male_f0[0] >= 40  # spread across the range, not the three nearest the best clip


def test_shortlist_fills_from_the_other_gender_when_one_runs_short() -> None:
    pool = [_stat("m0", "male", 100)] + [_stat(f"f{i}", "female", 170 + 10 * i) for i in range(8)]
    picked = shortlist(pool, 6)
    assert len(picked) == 6 and sum(c.gender == "male" for c in picked) == 1


def test_shortlist_never_exceeds_n_or_the_pool() -> None:
    assert len(shortlist([_stat("a", "male", 100)], 12)) == 1
    assert shortlist([], 12) == []


def test_synthesize_writes_three_passages_per_candidate_and_an_index(tmp_path: Path) -> None:
    clip = tmp_path / "ref.wav"
    sf.write(str(clip), _voiced(110.0), SR)
    voice = BankVoice(speaker_id="hifitts92", gender="female", age=35, reference_clip=clip, name="Cori <Samuel>")
    bank = VoiceBank([voice], bank_id="hifitts", licence="CC BY 4.0")
    stats = [_stat("hifitts92", "female", 200.0)]
    stats[0].bank, stats[0].name = "hifitts", "Cori <Samuel>"

    out = tmp_path / "aud"
    synthesize_audition(stats, [bank], get_engine("stub"), out)

    assert len(PASSAGES) == 3
    for key in PASSAGES:
        assert (out / "hifitts92" / f"{key}.wav").is_file()
    html = (out / "index.html").read_text(encoding="utf-8")
    assert html.count("<audio") == 3
    assert "CC BY 4.0" in html and "hifitts" in html
    assert "Cori &lt;Samuel&gt;" in html and "Cori <Samuel>" not in html  # escaped
    assert 'src="hifitts92/p1_dark.wav"' in html


def test_passages_include_the_public_domain_opening_and_no_empty_text() -> None:
    assert PASSAGES["p2_pride"].startswith("It is a truth universally acknowledged")
    assert all(p.strip() for p in PASSAGES.values())
    json.dumps(PASSAGES)


def test_voice_audition_command_writes_the_shortlist_json(tmp_path: Path) -> None:
    from echotales.pipeline.cli import main

    root = tmp_path / "bank" / "hifitts" / "audio" / "92_clean" / "1"
    root.mkdir(parents=True)
    sf.write(str(root / "a.flac"), _voiced(200.0, seconds=10.0, noise=0.0005), SR)
    out = tmp_path / "aud"
    code = main(["voice-audition", "--bank", str(tmp_path / "bank"), "--bank-kind", "hifitts", "--out", str(out)])
    assert code == 0
    data = json.loads((out / "shortlist.json").read_text(encoding="utf-8"))
    assert [s["voice_id"] for s in data["shortlist"]] == ["hifitts92"]
    assert data["shortlist"][0]["licence"] == "CC BY 4.0"
    assert not (out / "index.html").exists()  # no --synthesize, no GPU engine touched
