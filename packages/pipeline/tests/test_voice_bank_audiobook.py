"""LibriTTS-R and Hi-Fi TTS loaders, the licence stamp, and `load_bank` dispatch.

Layouts are the ones the corpora document (README_libritts_r.txt; the Hi-Fi TTS manifests), reproduced with tiny
files: `speakers.tsv` keeps its real header quirk (the last two header words are space-joined, not tab-joined).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from echotales.pipeline.errors import ErrorCode
from echotales.pipeline.voice.bank import (
    BANK_KINDS,
    HIFITTS_SPEAKERS,
    load_bank,
    load_hifitts,
    load_libritts_r,
    noncommercial_refusal,
)


def _tone(path: Path, seconds: float, sr: int = 24000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), (0.1 * np.sin(np.arange(int(sr * seconds)) * 0.05)).astype("float32"), sr)
    return path


def _libritts(root: Path) -> None:
    (root / "speakers.tsv").write_text(
        "READER\tGENDER\tSUBSET NAME\n"
        "14\tF\tdev-clean\tKristin LeMoine\n"
        "17\tM\tdev-clean\tGord Mackenzie\n"
        "20\tF\ttrain-other-500\tGesine\n",  # no audio extracted for this one
        encoding="utf-8",
    )
    _tone(root / "dev-clean" / "14" / "100" / "14_100_000001_000000.wav", 3.0)
    _tone(root / "dev-clean" / "14" / "100" / "14_100_000002_000000.wav", 12.0)
    _tone(root / "dev-clean" / "17" / "200" / "17_200_000001_000000.wav", 9.0)


def test_libritts_r_reads_speakers_tsv_and_skips_readers_without_audio(tmp_path: Path) -> None:
    _libritts(tmp_path)
    bank = load_libritts_r(tmp_path)
    assert [(v.speaker_id, v.gender, v.name) for v in bank.voices] == [
        ("libritts_r14", "female", "Kristin LeMoine"),
        ("libritts_r17", "male", "Gord Mackenzie"),
    ]
    assert (bank.bank_id, bank.licence) == ("libritts_r", "CC BY 4.0")


def test_libritts_r_reference_is_a_cloning_length_clip_not_the_first_fragment(tmp_path: Path) -> None:
    _libritts(tmp_path)
    voice = load_libritts_r(tmp_path).voices[0]
    assert voice.reference_clip.name == "14_100_000002_000000.wav"  # 12 s, not the 3 s sorted first


def test_libritts_r_requires_speakers_tsv(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_libritts_r(tmp_path)


def _hifitts(root: Path) -> None:
    _tone(root / "audio" / "92_clean" / "10349" / "a_0001.flac", 10.0, 44100)
    _tone(root / "audio" / "6670_other" / "9000" / "b_0001.flac", 10.0, 44100)
    _tone(root / "audio" / "999_clean" / "1" / "c.flac", 10.0, 44100)  # not a Hi-Fi TTS speaker


def test_hifitts_gender_comes_from_the_published_table_and_unknown_speakers_are_skipped(tmp_path: Path) -> None:
    _hifitts(tmp_path)
    bank = load_hifitts(tmp_path)
    assert [(v.speaker_id, v.gender, v.region) for v in bank.voices] == [
        ("hifitts6670", "male", "other"),
        ("hifitts92", "female", "clean"),
    ]
    assert (bank.bank_id, bank.licence) == ("hifitts", "CC BY 4.0")


def test_hifitts_table_is_six_female_four_male() -> None:
    genders = [g for g, _ in HIFITTS_SPEAKERS.values()]
    assert (genders.count("female"), genders.count("male")) == (6, 4)


def test_load_bank_finds_the_corpus_folder_under_the_bank_root(tmp_path: Path) -> None:
    (tmp_path / "libritts_r").mkdir()
    _libritts(tmp_path / "libritts_r")
    _hifitts(tmp_path / "hifitts")
    assert len(load_bank("libritts_r", tmp_path).voices) == 2
    assert len(load_bank("hifitts", tmp_path).voices) == 2
    with pytest.raises(ValueError):
        load_bank("nope", tmp_path)


def test_audiobook_banks_are_commercial_and_ears_is_not() -> None:
    assert "libritts_r" in BANK_KINDS and "hifitts" in BANK_KINDS
    for kind in ("libritts_r", "hifitts", "vctk"):
        assert noncommercial_refusal(kind, m4b=True, allowed=False) is None
    assert noncommercial_refusal("ears", m4b=True, allowed=False).code is ErrorCode.LICENCE_REFUSED


def test_audiobook_kind_merges_both_audiobook_corpora_and_is_the_default(monkeypatch, tmp_path):
    # VCTK was rejected for audiobooks (2026-11-19) and the chosen narrator is a LibriTTS-R reader, so the default
    # bank must hold Hi-Fi TTS and LibriTTS-R voices together under one CC BY 4.0 stamp.
    from echotales.pipeline.voice import bank as bank_mod

    def fake(part):
        return lambda root: bank_mod.VoiceBank([bank_mod.BankVoice(speaker_id=f"{part}1", gender="male", age=35)])

    monkeypatch.setattr(bank_mod, "load_hifitts", fake("hifitts"))
    monkeypatch.setattr(bank_mod, "load_libritts_r", fake("libritts_r"))
    merged = bank_mod.load_bank("audiobook", tmp_path)
    assert {v.speaker_id for v in merged.voices} == {"hifitts1", "libritts_r1"}
    assert (merged.bank_id, merged.licence) == ("audiobook", "CC BY 4.0")
    assert bank_mod.DEFAULT_BANK_KIND == "audiobook"
