"""Tests for Voice Actor Banks and dynamic prosody modulation (actor_bank.py, delivery.py, pitch.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from echotales.core.enums import SpanType
from echotales.pipeline.persona.traits import TraitProfile
from echotales.pipeline.spans.delivery import DeliveryPolarity
from echotales.pipeline.voice.actor_bank import (
    VoiceActorArchetype,
    VoiceActorProfile,
    load_esd,
    load_libritts_r,
    load_voice_actor_manifest,
)
from echotales.pipeline.voice.delivery import DeliverySettings, settings_for
from echotales.pipeline.voice.pitch import ffmpeg_available, modulate_prosody


def test_voice_actor_profile_conversion(tmp_path: Path) -> None:
    clip_neutral = tmp_path / "neutral.wav"
    clip_angry = tmp_path / "angry.wav"
    clip_neutral.write_bytes(b"RIFFdummy")
    clip_angry.write_bytes(b"RIFFdummy")

    profile = VoiceActorProfile(
        speaker_id="va_fang_yuan",
        name="Fang Yuan Voice",
        gender="male",
        age=28,
        archetype=VoiceActorArchetype.COLD_DOMINANT,
        accent="english",
        reference_clip=clip_neutral,
        emotion_clips={"neutral": clip_neutral, "angry": clip_angry},
    )

    bank_voice = profile.to_bank_voice()
    assert bank_voice.speaker_id == "va_fang_yuan"
    assert bank_voice.gender == "male"
    assert bank_voice.age == 28
    assert bank_voice.clip_for("angry") == clip_angry
    assert bank_voice.clip_for("neutral") == clip_neutral
    assert bank_voice.clip_for("whisper") == clip_neutral  # fallback


def test_load_voice_actor_manifest(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    (clips_dir / "lead_neutral.wav").write_bytes(b"RIFF")
    (clips_dir / "lead_angry.wav").write_bytes(b"RIFF")
    (clips_dir / "elder_neutral.wav").write_bytes(b"RIFF")

    manifest = [
        {
            "speaker_id": "va_lead",
            "name": "Cold Protagonist",
            "gender": "male",
            "age": 25,
            "archetype": "cold_dominant",
            "clips": {
                "neutral": "clips/lead_neutral.wav",
                "angry": "clips/lead_angry.wav",
            },
        },
        {
            "speaker_id": "va_elder",
            "name": "Ancient Patriarch",
            "gender": "male",
            "age": 70,
            "archetype": "venerable_master",
            "clips": {
                "neutral": "clips/elder_neutral.wav",
            },
        },
    ]

    manifest_file = tmp_path / "voice_actors.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    bank = load_voice_actor_manifest(manifest_file, clips_dir=tmp_path)
    assert len(bank.voices) == 2
    lead = next(v for v in bank.voices if v.speaker_id == "va_lead")
    assert lead.age == 25
    assert lead.clip_for("angry") == clips_dir / "lead_angry.wav"

    elder = next(v for v in bank.voices if v.speaker_id == "va_elder")
    assert elder.age_band == "elder"


def test_load_esd_bank(tmp_path: Path) -> None:
    esd_root = tmp_path / "ESD"
    spk_0011 = esd_root / "0011"
    (spk_0011 / "Neutral").mkdir(parents=True)
    (spk_0011 / "Angry").mkdir(parents=True)
    (spk_0011 / "Neutral" / "0011_000001.wav").write_bytes(b"RIFF")
    (spk_0011 / "Angry" / "0011_000002.wav").write_bytes(b"RIFF")

    bank = load_esd(esd_root, english_only=True)
    assert len(bank.voices) == 1
    v = bank.voices[0]
    assert v.speaker_id == "esd_0011"
    assert v.gender == "male"
    assert "angry" in v.emotion_clips


def test_dynamic_prosody_tuning_exclamation() -> None:
    settings = settings_for(
        span_type=SpanType.DIALOGUE,
        polarity=DeliveryPolarity.HEIGHTENED,
        profile=None,
        text="Stop right there!",
    )
    assert settings.exaggeration >= 0.75
    assert settings.tempo_ratio > 1.0  # Sped up for exclamation
    assert settings.pitch_semitones > 0.0  # Pitched up for exclamation


def test_dynamic_prosody_tuning_elder_formal() -> None:
    elder_profile = TraitProfile(
        target_id="p_elder",
        gender="male",
        age_band="elder",
        register="formal",
        extraversion=0.5,
        openness=0.5,
        conscientiousness=0.8,
        agreeableness=0.5,
        neuroticism=0.2,
    )
    settings = settings_for(
        span_type=SpanType.DIALOGUE,
        polarity=DeliveryPolarity.FLAT,
        profile=elder_profile,
        text="The clan will decide your fate tomorrow.",
    )
    assert settings.tempo_ratio < 1.0  # Slower, measured pace
    assert settings.pitch_semitones < 0.0  # Lower, authoritative pitch


def test_modulate_prosody_noop_on_default(tmp_path: Path) -> None:
    p = tmp_path / "test.wav"
    p.write_bytes(b"dummy")
    # No-op when semitones ~ 0 and tempo ~ 1.0
    modulate_prosody(p, semitones=0.0, tempo=1.0)
    assert p.read_bytes() == b"dummy"
