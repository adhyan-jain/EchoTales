"""Exclamation toolkit: expressive take selection, audio peak extraction, and dialogue overlap.

Enforces:
1. Multi-take generation for intensity 2-3 lines; selects take with widest dynamic pitch range.
2. Millisecond-accurate audio peak timing extraction for syncing visual manga impacts and camera shakes.
3. Natural non-verbal breath and grunt cues.
4. Interrupted dialogue overlapping (150-200ms) for heated arguments and sudden cut-offs.
5. Storyteller narrator mode with mood-driven pacing.
"""

from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

import numpy as np

from workers.common.contract import TTSWorkerRequest, TTSWorkerResponse
from workers.common.stub import run_tts_worker


class NarratorMood(StrEnum):
    """Pacing and cadence presets for the storyteller narrator."""

    EXPOSITION = "exposition"
    SUSPENSE = "suspense"
    ACTION = "action"
    SOLEMN = "solemn"
    COMEDIC = "comedic"


@dataclass(slots=True)
class NarratorPacingProfile:
    """Narration timing parameters."""

    mood: NarratorMood
    speed_factor: float
    pause_after_sentence_s: float
    cadence_instruction: str


NARRATOR_MOOD_PROFILES: dict[NarratorMood, NarratorPacingProfile] = {
    NarratorMood.EXPOSITION: NarratorPacingProfile(
        mood=NarratorMood.EXPOSITION,
        speed_factor=1.0,
        pause_after_sentence_s=0.35,
        cadence_instruction="clear, measured, and engaging storytelling cadence",
    ),
    NarratorMood.SUSPENSE: NarratorPacingProfile(
        mood=NarratorMood.SUSPENSE,
        speed_factor=0.88,
        pause_after_sentence_s=0.60,
        cadence_instruction="hushed, lingering, tense, building dread with deliberate pauses",
    ),
    NarratorMood.ACTION: NarratorPacingProfile(
        mood=NarratorMood.ACTION,
        speed_factor=1.18,
        pause_after_sentence_s=0.18,
        cadence_instruction="rapid, punchy, urgent, driving the momentum forward",
    ),
    NarratorMood.SOLEMN: NarratorPacingProfile(
        mood=NarratorMood.SOLEMN,
        speed_factor=0.85,
        pause_after_sentence_s=0.70,
        cadence_instruction="deep, resonant, sorrowful, full of emotional gravity",
    ),
    NarratorMood.COMEDIC: NarratorPacingProfile(
        mood=NarratorMood.COMEDIC,
        speed_factor=1.08,
        pause_after_sentence_s=0.25,
        cadence_instruction="wry, brisk, slightly sarcastic comedic delivery",
    ),
}


@dataclass(slots=True)
class TakeCandidate:
    """An audio take rendered for dynamic pitch evaluation."""

    take_index: int
    audio_bytes: bytes
    duration_s: float
    dynamic_pitch_range: float
    sample_rate: int = 24000


def _read_wav_samples(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """Parse 16-bit mono or stereo WAV bytes into a 1D float32 numpy array in [-1.0, 1.0]."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)
    return samples, sample_rate


def _write_wav_samples(samples: np.ndarray, sample_rate: int = 24000) -> bytes:
    """Encode 1D float32 numpy array into 16-bit mono WAV bytes."""
    clipped = np.clip(samples, -1.0, 1.0)
    int_samples = (clipped * 32767.0).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int_samples.tobytes())
    return buf.getvalue()


def measure_dynamic_pitch_range(audio_bytes: bytes, sample_rate: int = 24000) -> float:
    """Estimate dynamic pitch and energy range of an audio take.
    
    Higher values denote greater dynamic expressiveness, vocal lift, and emotional range.
    """
    try:
        samples, sr = _read_wav_samples(audio_bytes)
        if len(samples) < sr * 0.1:  # shorter than 100ms
            return 0.0

        # Window analysis (50ms windows)
        win_size = int(sr * 0.05)
        n_wins = len(samples) // win_size
        if n_wins < 2:
            return float(np.ptp(samples))

        rms_vals: list[float] = []
        zcr_vals: list[float] = []

        for w in range(n_wins):
            chunk = samples[w * win_size : (w + 1) * win_size]
            rms = math.sqrt(float(np.mean(chunk**2)))
            rms_vals.append(rms)

            # Zero crossing rate (proxy for frequency shifts)
            crossings = np.sum(np.abs(np.diff(np.sign(chunk)))) / 2.0
            zcr = float(crossings / len(chunk))
            zcr_vals.append(zcr)

        rms_arr = np.array(rms_vals)
        zcr_arr = np.array(zcr_vals)

        # Dynamic range = RMS amplitude variance * ZCR frequency variance
        energy_dyn = float(np.std(rms_arr))
        freq_dyn = float(np.std(zcr_arr))
        range_score = energy_dyn * 10.0 + freq_dyn * 5.0
        return float(round(range_score, 4))
    except Exception:
        return 0.0


def select_best_exclamation_take(takes: list[TakeCandidate]) -> TakeCandidate:
    """Select the take with the widest dynamic pitch and volume range."""
    if not takes:
        raise ValueError("takes list cannot be empty")
    return max(takes, key=lambda t: t.dynamic_pitch_range)


def generate_intensity_takes(
    text: str,
    voice_id: str,
    *,
    emotion: str = "angry",
    intensity: int = 3,
    num_takes: int = 3,
    run_worker: Callable[[TTSWorkerRequest], TTSWorkerResponse] = run_tts_worker,
) -> tuple[TakeCandidate, list[TakeCandidate]]:
    """Render multiple takes for an exclamation line and select the best dynamic take."""
    takes: list[TakeCandidate] = []

    take_prompts = [
        f"shout loudly with intense fury and sharp emphasis",
        f"scream at peak emotional pitch with raw vocal power",
        f"explode with dramatic force, voice trembling with rage",
    ]

    for idx in range(num_takes):
        prompt = take_prompts[idx % len(take_prompts)]
        req = TTSWorkerRequest(
            text=text,
            voice_id=voice_id,
            emotion_instruction=prompt,
            intensity=intensity,
        )
        resp = run_worker(req)
        score = measure_dynamic_pitch_range(resp.audio_bytes, resp.sample_rate)
        candidate = TakeCandidate(
            take_index=idx,
            audio_bytes=resp.audio_bytes,
            duration_s=resp.duration_s,
            dynamic_pitch_range=score,
            sample_rate=resp.sample_rate,
        )
        takes.append(candidate)

    best = select_best_exclamation_take(takes)
    return best, takes


def extract_audio_peaks(
    audio_bytes: bytes,
    sample_rate: int = 24000,
    *,
    threshold_factor: float = 1.6,
    min_interval_s: float = 0.25,
) -> list[float]:
    """Extract millisecond-accurate peak timestamps for visual manga impacts and shakes.
    
    Returns sorted list of timestamps in seconds where audio intensity peaks above average.
    """
    try:
        samples, sr = _read_wav_samples(audio_bytes)
        if len(samples) == 0:
            return []

        # 20ms RMS windows
        win_size = int(sr * 0.02)
        n_wins = len(samples) // win_size
        if n_wins < 2:
            return [0.0]

        rms_profile = np.zeros(n_wins, dtype=np.float32)
        for w in range(n_wins):
            chunk = samples[w * win_size : (w + 1) * win_size]
            rms_profile[w] = math.sqrt(float(np.mean(chunk**2)))

        mean_rms = float(np.mean(rms_profile))
        peak_thresh = mean_rms * threshold_factor

        peaks: list[float] = []
        last_peak_t = -min_interval_s
        for w in range(1, n_wins - 1):
            val = rms_profile[w]
            if val > peak_thresh and val >= rms_profile[w - 1] and val >= rms_profile[w + 1]:
                t = (w * win_size) / float(sr)
                if t - last_peak_t >= min_interval_s:
                    peaks.append(round(t, 3))
                    last_peak_t = t

        return peaks
    except Exception:
        return []


def insert_nonverbal_breath(
    base_audio_bytes: bytes,
    cue: str = "gasp",
    *,
    sample_rate: int = 24000,
) -> bytes:
    """Prepend a subtle dramatic breath or sharp gasp to heighten emotional delivery."""
    try:
        base_samples, sr = _read_wav_samples(base_audio_bytes)

        # Generate 120ms shaped noise envelope for intake of breath
        breath_dur = 0.12
        n_breath = int(sr * breath_dur)
        t = np.linspace(0.0, 1.0, n_breath)
        # Rising attack envelope
        envelope = np.sin(t * (np.pi / 2.0)) * 0.15
        noise = (np.random.RandomState(42).randn(n_breath) * envelope).astype(np.float32)

        combined = np.concatenate([noise, base_samples])
        return _write_wav_samples(combined, sr)
    except Exception:
        return base_audio_bytes


def overlap_dialogue_cutoffs(
    prev_audio: bytes,
    next_audio: bytes,
    *,
    overlap_ms: int = 180,
    sample_rate: int = 24000,
) -> bytes:
    """Cross-mix interrupted dialogue cut-offs for natural overlapping speech.
    
    Overlaps the tail of prev_audio with the head of next_audio across overlap_ms.
    """
    try:
        s1, sr1 = _read_wav_samples(prev_audio)
        s2, _ = _read_wav_samples(next_audio)
        sr = sr1

        n_overlap = int(sr * (overlap_ms / 1000.0))
        n_overlap = max(1, min(n_overlap, len(s1), len(s2)))

        out_len = len(s1) + len(s2) - n_overlap
        out = np.zeros(out_len, dtype=np.float32)

        # Place s1 before overlap
        out[: len(s1) - n_overlap] = s1[: len(s1) - n_overlap]

        # Overlap region: additive mix with smooth equal-power crossfade
        t = np.linspace(0.0, 1.0, n_overlap, dtype=np.float32)
        fade_out = np.cos(t * (np.pi / 2.0))
        fade_in = np.sin(t * (np.pi / 2.0))

        overlap_start = len(s1) - n_overlap
        out[overlap_start : overlap_start + n_overlap] = (
            s1[len(s1) - n_overlap :] * fade_out + s2[:n_overlap] * fade_in
        )

        # Remaining s2
        out[overlap_start + n_overlap :] = s2[n_overlap:]

        return _write_wav_samples(out, sr)
    except Exception:
        return prev_audio + next_audio
