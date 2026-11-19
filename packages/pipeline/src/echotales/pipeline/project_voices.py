"""A person's own voice (or one they have permission to use) as a casting voice for one project.

A reference clip of a real person lets a voice-cloning engine speak as them, so nothing is stored without an explicit
consent, and the consent is stored with the clip: a JSON record beside it holding the exact statement shown, the time,
and the clip's hash. The clip lives in the project's own folder (`data/novels/<CODE>/voices/`), never in the shared
voice bank, so it can only ever be cast in the book it was uploaded to.

The upload validates what it can without a decoder: WAV through the standard library, FLAC from its STREAMINFO block.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from echotales.pipeline import paths
from echotales.pipeline.voice.bank import BankVoice, VoiceBank

#: What the checkbox says, and what is recorded. The server writes this text, not whatever the client sends, so a record
#: always states the same promise.
CONSENT_STATEMENT = "This is my voice or I have the speaker's permission."
VOICE_ID_PREFIX = "project:"
SUFFIXES = (".wav", ".flac")
#: A clone needs a few seconds of clean speech; a minute is more than any engine here uses, and caps the stored size.
MIN_SECONDS, MAX_SECONDS = 3.0, 60.0
MIN_AGE, MAX_AGE = 5, 100
_NAME = re.compile(r"[^a-z0-9]+")


class VoiceUploadError(ValueError):
    """The upload cannot be stored; the message is written for the person who uploaded it."""


@dataclass(slots=True)
class StoredVoice:
    voice_id: str
    name: str
    gender: str
    age: int
    consent_at: str


def voices_dir(novel_id: str) -> Path:
    return paths.asset_dir(novel_id, "voices")


def slug(name: str) -> str:
    """`My Voice` -> `my-voice`. Letters and digits only, so a name can never carry a path."""
    return _NAME.sub("-", name.casefold()).strip("-")[:40]


def audio_seconds(data: bytes, suffix: str) -> float:
    """Duration of a WAV or FLAC held in memory, or `VoiceUploadError` if it is not one."""
    if suffix == ".wav":
        try:
            with wave.open(io.BytesIO(data)) as w:
                return w.getnframes() / float(w.getframerate())
        except (wave.Error, EOFError, ZeroDivisionError):
            raise VoiceUploadError("that is not a readable WAV file (16-bit PCM is the safe choice)") from None
    # FLAC: "fLaC", then the first metadata block, which must be STREAMINFO (type 0, 34 bytes). Sample rate is 20 bits
    # and total samples 36 bits, packed with channels and bit depth into the 8 bytes at offset 18.
    if len(data) < 42 or data[:4] != b"fLaC" or data[4] & 0x7F != 0:
        raise VoiceUploadError("that is not a readable FLAC file")
    packed = int.from_bytes(data[18:26], "big")
    rate, total = packed >> 44, packed & ((1 << 36) - 1)
    if rate == 0 or total == 0:
        raise VoiceUploadError("that FLAC file does not say how long it is; export it again")
    return total / rate


def save_voice(novel_id: str, *, filename: str, data: bytes, name: str, gender: str, age: int, consent: bool) -> StoredVoice:
    if not consent:
        raise VoiceUploadError(f"Tick the box first: \"{CONSENT_STATEMENT}\" Nothing was uploaded.")
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    if suffix not in SUFFIXES:
        raise VoiceUploadError("only .wav and .flac recordings are accepted")
    key = slug(name)
    if not key:
        raise VoiceUploadError("give the voice a name made of letters or digits")
    if gender not in ("male", "female"):
        raise VoiceUploadError("gender must be male or female: it decides which characters the voice can be cast as")
    if not MIN_AGE <= age <= MAX_AGE:
        raise VoiceUploadError(f"age must be between {MIN_AGE} and {MAX_AGE}")
    seconds = audio_seconds(data, suffix)
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise VoiceUploadError(f"the recording is {seconds:.1f} s; it must be between {MIN_SECONDS:g} and {MAX_SECONDS:g} s")
    folder = voices_dir(novel_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{key}{suffix}"
    if any((folder / f"{key}{s}").exists() for s in SUFFIXES):
        raise VoiceUploadError(f"a voice named {key!r} already exists in this project; choose another name")
    record = {
        "voice_id": f"{VOICE_ID_PREFIX}{key}", "name": name.strip()[:80], "gender": gender, "age": age,
        "statement": CONSENT_STATEMENT, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "file": target.name, "sha256": hashlib.sha256(data).hexdigest(), "seconds": round(seconds, 2),
    }
    # The clip first, then the record that makes it usable: a crash between them leaves a clip nothing lists, never a
    # listed voice with no consent on file.
    target.write_bytes(data)
    (folder / f"{key}.consent.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return StoredVoice(record["voice_id"], record["name"], gender, age, record["timestamp"])


def _records(novel_id: str) -> list[tuple[dict, Path]]:
    """Every voice with a readable consent record and its clip still in place, in name order."""
    out: list[tuple[dict, Path]] = []
    folder = voices_dir(novel_id)
    if not folder.is_dir():
        return out
    for rec_path in sorted(folder.glob("*.consent.json")):
        try:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            clip = folder / Path(str(rec["file"])).name
        except (OSError, ValueError, KeyError):
            continue
        if clip.is_file() and rec.get("statement") and rec.get("voice_id", "").startswith(VOICE_ID_PREFIX):
            out.append((rec, clip))
    return out


def list_project_voices(novel_id: str) -> list[StoredVoice]:
    return [StoredVoice(r["voice_id"], r.get("name", r["voice_id"]), r["gender"], int(r["age"]), r["timestamp"]) for r, _ in _records(novel_id)]


def load_project_voices(novel_id: str) -> list[BankVoice]:
    """The project's voices as casting candidates. No emotion clips: `clip_for` falls back to the one reference."""
    return [
        BankVoice(speaker_id=r["voice_id"], gender=r["gender"], age=int(r["age"]), reference_clip=clip, name=r.get("name", ""))
        for r, clip in _records(novel_id)
    ]


def with_project_voices(bank: VoiceBank, novel_id: str) -> VoiceBank:
    """`bank` plus this project's own voices, keeping its licence stamp (a project voice is the uploader's to license)."""
    mine = load_project_voices(novel_id)
    if not mine:
        return bank
    return VoiceBank([*bank.voices, *mine], bank_id=bank.bank_id, licence=bank.licence)
