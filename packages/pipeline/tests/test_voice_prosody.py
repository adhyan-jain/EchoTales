"""Delivery tempo/pitch and the ffmpeg prosody step (delivery.py, pitch.py, runner fingerprint)."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from echotales.core.enums import SpanType
from echotales.pipeline.persona.traits import TraitProfile
from echotales.pipeline.spans.delivery import DeliveryPolarity
from echotales.pipeline.voice import pitch
from echotales.pipeline.voice.delivery import DeliverySettings, settings_for
from echotales.pipeline.voice.pitch import ffmpeg_available, modulate_prosody
from echotales.pipeline.voice.runner import _line_fingerprint


def _sine(path: Path, seconds: float = 1.0, sr: int = 16000) -> None:
    t = np.arange(int(sr * seconds)) / sr
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def _seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def test_exclamation_is_faster_and_higher() -> None:
    s = settings_for(span_type=SpanType.DIALOGUE, polarity=DeliveryPolarity.HEIGHTENED, profile=None, text="Stop!")
    assert s.tempo_ratio > 1.0 and s.pitch_semitones > 0.0


def test_formal_elder_is_slower_and_lower() -> None:
    profile = TraitProfile(
        target_id="p", gender="male", age_band="elder", register="formal",
        extraversion=0.5, openness=0.5, conscientiousness=0.8, agreeableness=0.5, neuroticism=0.2,
    )
    s = settings_for(span_type=SpanType.DIALOGUE, polarity=DeliveryPolarity.FLAT, profile=profile, text="It is decided.")
    assert s.tempo_ratio < 1.0 and s.pitch_semitones < 0.0


def test_fingerprint_changes_with_tempo() -> None:
    # A tempo change must not reuse a WAV rendered at the old tempo (the stamp skips re-synthesis).
    class E:
        name = "chatterbox"

    a = DeliverySettings(0.5, 0.5, 0.0, "", "neutral", 1.0)
    b = DeliverySettings(0.5, 0.5, 0.0, "", "neutral", 1.12)
    assert _line_fingerprint(E(), "x", None, a) != _line_fingerprint(E(), "x", None, b)


def test_noop_leaves_file_untouched(tmp_path: Path) -> None:
    p = tmp_path / "a.wav"
    p.write_bytes(b"dummy")
    modulate_prosody(p, 0.0, 1.0)
    assert p.read_bytes() == b"dummy"


needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg missing")


@needs_ffmpeg
def test_tempo_changes_real_duration(tmp_path: Path) -> None:
    p = tmp_path / "a.wav"
    _sine(p)
    modulate_prosody(p, 0.0, 1.25)
    assert _seconds(p) == pytest.approx(0.8, abs=0.08)


@needs_ffmpeg
def test_missing_rubberband_falls_back_to_atempo_for_tempo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pitch, "rubberband_available", lambda: False)
    p = tmp_path / "a.wav"
    _sine(p)
    modulate_prosody(p, 2.0, 1.25)  # pitch cannot be honoured, tempo still is
    assert _seconds(p) == pytest.approx(0.8, abs=0.08)


@needs_ffmpeg
def test_missing_rubberband_pitch_only_is_left_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pitch, "rubberband_available", lambda: False)
    p = tmp_path / "a.wav"
    _sine(p)
    before = p.read_bytes()
    modulate_prosody(p, 2.0, 1.0)
    assert p.read_bytes() == before
