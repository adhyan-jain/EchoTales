"""Bank gender labels checked against measured pitch, and age carried by the delivery layer.

Measured on the audiobook bank (2026-11-19 casting audit): Hi-Fi TTS 6671 and LibriTTS-R 7976 are labelled male but
their reference clips sit at 208 and 232 Hz, so a male character cast with either reads as a woman. Neither corpus
publishes age (every voice is `ASSUMED_READER_AGE`), so an elder or a youth was always voiced by an adult reader.
"""

from __future__ import annotations

from pathlib import Path

from echotales.core.enums import SpanType
from echotales.pipeline.persona.traits import TraitProfile
from echotales.pipeline.voice.bank import BankVoice, VoiceBank
from echotales.pipeline.voice.delivery import settings_for
from echotales.pipeline.voice.qa import pitch_gender_conflicts, without_voices


def _bank() -> VoiceBank:
    voices = [
        BankVoice("m_ok", "male", 35, reference_clip=Path("a.wav")),
        BankVoice("m_high", "male", 35, reference_clip=Path("b.wav")),
        BankVoice("m_overlap", "male", 35, reference_clip=Path("c.wav")),
        BankVoice("f_ok", "female", 35, reference_clip=Path("d.wav")),
        BankVoice("f_low", "female", 35, reference_clip=Path("e.wav")),
        BankVoice("f_unmeasured", "female", 35, reference_clip=Path("f.wav")),
    ]
    return VoiceBank(voices, bank_id="audiobook", licence="CC BY 4.0")


F0 = {"m_ok": 110.0, "m_high": 208.0, "m_overlap": 160.0, "f_ok": 190.0, "f_low": 120.0, "f_unmeasured": None}


def test_pitch_that_contradicts_the_recorded_gender_is_flagged() -> None:
    assert set(pitch_gender_conflicts(_bank(), F0)) == {"m_high", "f_low"}


def test_the_overlap_band_and_unmeasured_voices_are_not_judged() -> None:
    conflicts = pitch_gender_conflicts(_bank(), F0)
    assert "m_overlap" not in conflicts and "f_unmeasured" not in conflicts


def test_without_voices_drops_them_but_never_empties_a_gender() -> None:
    bank = without_voices(_bank(), {"m_high", "f_low"})
    ids = {v.speaker_id for v in bank.voices}
    assert "m_high" not in ids and "f_low" not in ids and "m_ok" in ids
    assert bank.licence == "CC BY 4.0"
    # Dropping every male would leave nobody to cast a man with: the males stay rather than empty the gender.
    emptied = without_voices(_bank(), {"m_ok", "m_high", "m_overlap"})
    assert any(v.gender == "male" for v in emptied.voices)


def _profile(age_band: str, register: str = "neutral") -> TraitProfile:
    return TraitProfile(target_id="p", label="P", gender="male", age_band=age_band, register=register)


def test_an_elder_is_pitched_down_from_the_adult_reader() -> None:
    adult = settings_for(span_type=SpanType.DIALOGUE, profile=_profile("adult"), text="It is decided.")
    elder = settings_for(span_type=SpanType.DIALOGUE, profile=_profile("elder"), text="It is decided.")
    assert elder.pitch_semitones < adult.pitch_semitones
    assert elder.tempo_ratio < adult.tempo_ratio


def test_a_youth_is_pitched_up_and_a_matching_voice_is_left_alone() -> None:
    youth = settings_for(span_type=SpanType.DIALOGUE, profile=_profile("youth"), text="Come on.")
    assert youth.pitch_semitones > 0
    # The bank voice already is an elder (a bank with real ages): no second shift on top of a real old voice.
    same = settings_for(span_type=SpanType.DIALOGUE, profile=_profile("elder"), text="It is decided.", voice_age_band="elder")
    plain = settings_for(span_type=SpanType.DIALOGUE, profile=_profile("adult"), text="It is decided.")
    assert same.pitch_semitones == plain.pitch_semitones


def test_age_and_formal_register_together_stay_below_a_cartoon_shift() -> None:
    s = settings_for(span_type=SpanType.DIALOGUE, profile=_profile("elder", "formal"), text="It is decided.")
    assert s.pitch_semitones >= -3.0
