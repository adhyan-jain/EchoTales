"""Expressive voice actor bank and dataset loader.

VCTK is read speech (110 university students/staff reading monotone newspaper
prompts), so casting from it leaves main characters sounding like students
reading a timetable.

This module introduces **Voice Actor Banks**:
1. **Acted performances with authentic vocal projection and emotion**:
   Voice actors tune their voice, modulate pitch, speed up or slow down, and
   deliver genuine emotion on exclamations and dramatic moments.
2. **Character Archetype Mapping**:
   Instead of casting by age/gender alone, characters map to vocal archetypes:
   - `COLD_DOMINANT`: deep, calm, calculating (e.g. ruthless schemers, dark leads)
   - `HOTHEADED_RIVAL`: high-energy, rapid, explosive exclamations
   - `VENERABLE_MASTER`: deep resonance (-2 to -4 semitones), slow measured pace
   - `LIVELY_COMPANION`: bright, rapid, expressive pitch contours
   - `CALCULATING_SCHEMER`: intimate, hushed, deliberate cadence
   - `DRAMATIC_NARRATOR`: engaging audiobook narrator with dynamic pace
3. **Multi-emotion takes per actor**:
   Authentic takes for `neutral`, `angry`, `whisper`, `sad`, `happy`, and `exclamation`.
   Chatterbox clones from the reference clip's acoustic prosody, so an angry reference
   delivers real diaphragm energy on shouted lines that no `exaggeration` dial can fake.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from echotales.pipeline.voice.bank import BankVoice, VoiceBank, age_band_for

log = logging.getLogger(__name__)


class VoiceActorArchetype(StrEnum):
    """Vocal archetypes for web-novel and anime adaptations."""

    COLD_DOMINANT = "cold_dominant"
    HOTHEADED_RIVAL = "hotheaded_rival"
    VENERABLE_MASTER = "venerable_master"
    LIVELY_COMPANION = "lively_companion"
    CALCULATING_SCHEMER = "calculating_schemer"
    DRAMATIC_NARRATOR = "dramatic_narrator"
    STOIC_WARRIOR = "stoic_warrior"
    GENTLE_MATRIARCH = "gentle_matriarch"
    GENERIC = "generic"


@dataclass(slots=True)
class VoiceActorProfile:
    """Rich profile for a professional voice actor."""

    speaker_id: str
    name: str
    gender: str
    age: int
    archetype: VoiceActorArchetype = VoiceActorArchetype.GENERIC
    accent: str = "english"
    region: str = ""
    description: str = ""
    reference_clip: Path | None = None
    emotion_clips: dict[str, Path] = field(default_factory=dict)
    base_tempo_ratio: float = 1.0
    pitch_offset_semitones: float = 0.0

    def to_bank_voice(self) -> BankVoice:
        """Convert into standard BankVoice for pipeline compatibility."""
        return BankVoice(
            speaker_id=self.speaker_id,
            gender=self.gender,
            age=self.age,
            accent=self.accent,
            region=self.region,
            reference_clip=self.reference_clip,
            emotion_clips=self.emotion_clips,
        )


def load_voice_actor_manifest(
    manifest_path: str | Path,
    *,
    clips_dir: str | Path | None = None,
) -> VoiceBank:
    """Load a curated Voice Actor Bank from a JSON or JSONL manifest.

    The manifest format allows specifying rich character archetypes,
    descriptions, base pitch offsets, and multi-emotion reference takes.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Voice actor manifest not found: {manifest_path}")

    base_dir = Path(clips_dir) if clips_dir else manifest_path.parent

    raw_data: list[dict[str, Any]]
    if manifest_path.suffix.lower() == ".jsonl":
        raw_data = [
            json.loads(line)
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        content = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_data = content if isinstance(content, list) else content.get("voices", [])

    voices: list[BankVoice] = []
    for item in raw_data:
        speaker_id = str(item.get("speaker_id") or item.get("id", "")).strip()
        if not speaker_id:
            continue

        gender = str(item.get("gender", "unknown")).casefold().strip()
        age = int(item.get("age", 30))
        accent = str(item.get("accent", "english")).strip()
        region = str(item.get("region", "")).strip()

        clips_map: dict[str, Path] = {}
        raw_clips = item.get("clips") or item.get("emotion_clips") or {}
        for emotion, rel_path in raw_clips.items():
            clip_path = base_dir / rel_path
            if clip_path.exists():
                clips_map[emotion.casefold()] = clip_path

        ref_clip: Path | None = None
        if "reference_clip" in item and item["reference_clip"]:
            p = base_dir / item["reference_clip"]
            if p.exists():
                ref_clip = p

        if not ref_clip:
            ref_clip = clips_map.get("neutral") or (next(iter(clips_map.values())) if clips_map else None)

        voice = BankVoice(
            speaker_id=speaker_id,
            gender=gender,
            age=age,
            accent=accent,
            region=region,
            reference_clip=ref_clip,
            emotion_clips=clips_map,
        )
        voices.append(voice)

    return VoiceBank(voices=voices)


def load_esd(
    root: str | Path,
    *,
    english_only: bool = True,
) -> VoiceBank:
    """Load the Emotional Speech Dataset (ESD, Zhou et al.).

    ESD contains 350 parallel utterances per speaker across 5 acted emotions:
    `neutral`, `angry`, `happy`, `sad`, `surprise`.
    Speakers 0011-0020 are native English speakers; 0001-0010 are Mandarin.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"ESD root directory not found: {root}")

    esd_genders: dict[str, str] = {
        "0011": "male", "0012": "male", "0013": "male", "0014": "male", "0015": "male",
        "0016": "female", "0017": "female", "0018": "female", "0019": "female", "0020": "female",
        "0001": "female", "0002": "female", "0003": "female", "0004": "female", "0005": "female",
        "0006": "male", "0007": "male", "0008": "male", "0009": "male", "0010": "male",
    }

    voices: list[BankVoice] = []
    for spk_dir in sorted(root.iterdir()):
        if not spk_dir.is_dir():
            continue
        spk_id = spk_dir.name
        if english_only and spk_id not in esd_genders:
            continue
        if english_only and int(spk_id) < 11:
            continue

        gender = esd_genders.get(spk_id, "unknown")
        emotion_folders = {
            "neutral": spk_dir / "Neutral",
            "angry": spk_dir / "Angry",
            "happy": spk_dir / "Happy",
            "sad": spk_dir / "Sad",
            "surprise": spk_dir / "Surprise",
        }

        emotion_clips: dict[str, Path] = {}
        for emo, folder in emotion_folders.items():
            if folder.is_dir():
                wavs = sorted(folder.glob("*.wav"))
                if wavs:
                    idx = min(15, len(wavs) - 1)
                    emotion_clips[emo] = wavs[idx]

        if not emotion_clips:
            continue

        ref_clip = emotion_clips.get("neutral") or next(iter(emotion_clips.values()))
        voices.append(
            BankVoice(
                speaker_id=f"esd_{spk_id}",
                gender=gender,
                age=28,
                accent="english",
                reference_clip=ref_clip,
                emotion_clips=emotion_clips,
            )
        )

    return VoiceBank(voices=voices)


def load_libritts_r(
    root: str | Path,
    *,
    subset: str = "clean",
) -> VoiceBank:
    """Load LibriTTS-R restored audiobook voice actors."""
    root = Path(root)
    speakers_file = root / "speakers.tsv"
    if not speakers_file.exists():
        speakers_file = root.parent / "speakers.tsv"

    metadata: dict[str, tuple[str, str]] = {}
    if speakers_file.exists():
        with speakers_file.open(encoding="utf-8") as f:
            for line in f:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3 and parts[0].isdigit():
                    reader_id = parts[0]
                    gender = "female" if parts[1].upper() == "F" else "male"
                    name = parts[2]
                    metadata[reader_id] = (gender, name)

    voices: list[BankVoice] = []
    for spk_dir in sorted(root.glob("*")):
        if not spk_dir.is_dir() or not spk_dir.name.isdigit():
            continue
        spk_id = spk_dir.name
        gender, name = metadata.get(spk_id, ("unknown", f"Narrator {spk_id}"))

        wavs = sorted(spk_dir.glob("*/*.wav"))
        if not wavs:
            continue

        chosen = wavs[min(3, len(wavs) - 1)]
        voices.append(
            BankVoice(
                speaker_id=f"libri_{spk_id}",
                gender=gender,
                age=35,
                accent="american",
                region="",
                reference_clip=chosen,
                emotion_clips={"neutral": chosen},
            )
        )

    return VoiceBank(voices=voices)
