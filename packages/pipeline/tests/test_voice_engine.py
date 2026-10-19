"""Unit tests for Voice Engine: Qwen3-TTS, Dia2, Exclamation Toolkit, and Collision Guard."""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

import numpy as np

from echotales.core.enums import Prominence
from echotales.pipeline.voice.bank import BankVoice, VoiceBank
from echotales.pipeline.voice.casting import (
    VoiceAssignment,
    enforce_episode_zero_collision,
    verify_no_co_occurring_voice_collisions,
)
from echotales.pipeline.voice.dia2 import (
    format_dia2_dialogue_text,
    synthesize_dia2,
)
from echotales.pipeline.voice.exclamations import (
    NARRATOR_MOOD_PROFILES,
    NarratorMood,
    TakeCandidate,
    extract_audio_peaks,
    generate_intensity_takes,
    insert_nonverbal_breath,
    overlap_dialogue_cutoffs,
    select_best_exclamation_take,
)
from echotales.pipeline.voice.qwen_tts import (
    build_emotion_instruction,
    synthesize_qwen_tts,
)


def _generate_test_wav(duration_s: float = 1.0, freq: float = 440.0, sample_rate: int = 24000) -> bytes:
    num_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = []
        for i in range(num_samples):
            val = int(16000.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.append(struct.pack("<h", val))
        wf.writeframes(b"".join(frames))
    return buf.getvalue()


def test_qwen_tts_emotion_instructions() -> None:
    neutral = build_emotion_instruction("neutral", 1)
    assert "balanced cadence" in neutral

    angry_mild = build_emotion_instruction("angry", 1)
    assert "sharp irritation" in angry_mild

    angry_peak = build_emotion_instruction("angry", 3)
    assert "explosive fury" in angry_peak

    shocked_peak = build_emotion_instruction("shocked", 3)
    assert "wide-eyed terror" in shocked_peak


def test_qwen_tts_synthesis(tmp_path: Path) -> None:
    out_file = tmp_path / "holmes_line.wav"
    res = synthesize_qwen_tts(
        text="The game is afoot!",
        voice_id="p225",
        emotion="shocked",
        intensity=2,
        output_path=out_file,
    )
    assert res.path == str(out_file)
    assert out_file.exists()
    assert len(res.audio_bytes) > 0
    assert res.duration_s > 0.5


def test_dia2_dialogue_formatting_and_synthesis(tmp_path: Path) -> None:
    raw = "What on earth is that?"
    formatted = format_dia2_dialogue_text(raw, ["gasp", "chuckle"])
    assert formatted == "[gasp] What on earth is that?"

    res = synthesize_dia2(
        text=raw,
        voice_id="p226",
        nonverbal=["gasp"],
        intensity=2,
        output_path=tmp_path / "dia.wav",
    )
    assert (tmp_path / "dia.wav").exists()
    assert res.intensity == 2


def test_exclamation_take_selection() -> None:
    w1 = _generate_test_wav(1.0, 300.0)
    w2 = _generate_test_wav(1.0, 600.0)

    t1 = TakeCandidate(0, w1, 1.0, dynamic_pitch_range=1.2)
    t2 = TakeCandidate(1, w2, 1.0, dynamic_pitch_range=4.8)

    best = select_best_exclamation_take([t1, t2])
    assert best.take_index == 1
    assert best.dynamic_pitch_range == 4.8

    # Test multi-take generation
    best_gen, all_takes = generate_intensity_takes(
        "Stop right there!", "p225", emotion="angry", intensity=3, num_takes=3
    )
    assert len(all_takes) == 3
    assert best_gen in all_takes


def test_audio_peak_extraction() -> None:
    # Build waveform with two distinct louder spikes
    sample_rate = 24000
    dur = 2.0
    n_samples = int(dur * sample_rate)
    samples = np.zeros(n_samples, dtype=np.float32)

    # Spike at 0.5s and 1.5s
    idx_05 = int(0.5 * sample_rate)
    idx_15 = int(1.5 * sample_rate)
    samples[idx_05 : idx_05 + 1000] = 0.95
    samples[idx_15 : idx_15 + 1000] = 0.95

    # Encode as WAV
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((samples * 32767).astype(np.int16).tobytes())

    peaks = extract_audio_peaks(buf.getvalue(), sample_rate=sample_rate, threshold_factor=1.5)
    assert len(peaks) >= 2
    # Verify peaks correspond approximately to 0.5s and 1.5s
    assert any(abs(p - 0.5) < 0.1 for p in peaks)
    assert any(abs(p - 1.5) < 0.1 for p in peaks)


def test_dialogue_overlap_and_breath() -> None:
    w1 = _generate_test_wav(1.0, 440.0)
    w2 = _generate_test_wav(1.0, 880.0)

    # Test overlap cross-mixing
    merged = overlap_dialogue_cutoffs(w1, w2, overlap_ms=200)
    assert len(merged) > len(w1)  # Overlapped is longer than 1 clip but shorter than 2 separate clips

    # Test nonverbal breath
    with_breath = insert_nonverbal_breath(w1, cue="gasp")
    assert len(with_breath) > len(w1)


def test_narrator_pacing_profiles() -> None:
    assert NarratorMood.SUSPENSE in NARRATOR_MOOD_PROFILES
    profile = NARRATOR_MOOD_PROFILES[NarratorMood.SUSPENSE]
    assert profile.speed_factor < 1.0  # Suspense is slower
    assert profile.pause_after_sentence_s > 0.5


def test_casting_scene_collision_prevention() -> None:
    assignments = {
        "holmes": VoiceAssignment("holmes", "Holmes", "p225", "male:mature", "detective", Prominence.PRINCIPAL),
        "watson": VoiceAssignment("watson", "Watson", "p225", "male:mature", "doctor", Prominence.PRINCIPAL),
        "lestrade": VoiceAssignment("lestrade", "Lestrade", "p226", "male:mature", "inspector", Prominence.RECURRING),
    }

    # Holmes and Watson collide in the same scene
    collisions = verify_no_co_occurring_voice_collisions(["holmes", "watson"], assignments)
    assert len(collisions) == 1
    assert collisions[0] == ("holmes", "watson", "p225")

    # Holmes and Lestrade do not collide
    no_collisions = verify_no_co_occurring_voice_collisions(["holmes", "lestrade"], assignments)
    assert len(no_collisions) == 0

    # Test enforcement of zero collision
    bank = VoiceBank([
        BankVoice("p225", "male", 40, "english", "gentleman"),
        BankVoice("p226", "male", 45, "english", "inspector"),
        BankVoice("p227", "male", 50, "english", "scholar"),
    ])

    resolved = enforce_episode_zero_collision([["holmes", "watson"]], assignments, bank)
    after_collisions = verify_no_co_occurring_voice_collisions(["holmes", "watson"], resolved)
    assert len(after_collisions) == 0
    assert resolved["holmes"].speaker_id != resolved["watson"].speaker_id
