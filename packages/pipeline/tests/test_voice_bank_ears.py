"""EARS voice bank: loading, emotion mapping, and the whisper fallback chain.

The fallback chain is the load-bearing part. `delivery.py` now asks for
`whisper` on HUSHED lines, which only EARS records; VCTK and CREMA-D must keep
producing exactly what they produced before (`fear`), or swapping the default
emotion request silently changes every existing bank's audio.
"""

from __future__ import annotations

import json
from pathlib import Path

from echotales.pipeline.spans.delivery import DeliveryPolarity
from echotales.pipeline.voice.bank import BankVoice, load_ears
from echotales.pipeline.voice.delivery import EMOTION_FOR_POLARITY


def _make_ears(root: Path) -> None:
    (root / "speaker_statistics.json").write_text(json.dumps({
        "p001": {"gender": "female", "age": "26-35", "native language": "american english"},
        "p002": {"gender": "male", "age": "prefer not to answer", "native language": "english"},
        "p003": {"gender": "prefer not to answer", "age": "18-25", "native language": "english"},
    }))
    for sid in ("p001", "p002", "p003"):
        d = root / sid
        d.mkdir()
        for name in ("emo_neutral_sentences", "emo_anger_sentences", "emo_fear_sentences",
                     "emo_contentment_sentences", "emo_pride_sentences",
                     "rainbow_01_whisper", "rainbow_01_loud", "rainbow_01_regular"):
            (d / f"{name}.wav").write_bytes(b"RIFF")


def test_loads_only_speakers_with_disclosed_gender_and_age(tmp_path: Path) -> None:
    _make_ears(tmp_path)
    bank = load_ears(tmp_path)
    assert [v.speaker_id for v in bank.voices] == ["earsp001"]
    voice = bank.voices[0]
    assert voice.gender == "female" and voice.age == 30


def test_maps_ears_emotions_onto_the_delivery_vocabulary(tmp_path: Path) -> None:
    _make_ears(tmp_path)
    voice = load_ears(tmp_path).voices[0]
    assert voice.clip_for("angry").name == "emo_anger_sentences.wav"
    assert voice.clip_for("happy").name == "emo_contentment_sentences.wav"
    assert voice.clip_for("whisper").name == "rainbow_01_whisper.wav"
    # Every EARS emotion stays reachable under its own name too.
    assert voice.clip_for("pride").name == "emo_pride_sentences.wav"
    assert voice.reference_clip.name == "emo_neutral_sentences.wav"


def test_every_polarity_the_delivery_layer_can_request_resolves(tmp_path: Path) -> None:
    _make_ears(tmp_path)
    voice = load_ears(tmp_path).voices[0]
    for polarity, emotion in EMOTION_FOR_POLARITY.items():
        assert voice.clip_for(emotion) is not None, polarity


def test_hushed_now_requests_whisper() -> None:
    assert EMOTION_FOR_POLARITY[DeliveryPolarity.HUSHED] == "whisper"


def test_a_bank_without_whisper_still_gets_fear(tmp_path: Path) -> None:
    """The regression guard: CREMA-D-shaped voices have no whisper, and must
    receive the `fear` clip HUSHED lines received before this change."""
    fear = tmp_path / "fear.wav"
    neutral = tmp_path / "neutral.wav"
    voice = BankVoice("x", "male", 40, reference_clip=neutral,
                      emotion_clips={"fear": fear, "neutral": neutral})
    assert voice.clip_for("whisper") == fear


def test_a_read_speech_bank_falls_back_to_its_reference(tmp_path: Path) -> None:
    ref = tmp_path / "ref.wav"
    voice = BankVoice("x", "male", 40, reference_clip=ref)
    assert voice.clip_for("whisper") == ref
    assert voice.clip_for("angry") == ref
