"""Voice bank, casting and delivery (Phase 8, `4b`, `architecture.md §8b`)."""

from __future__ import annotations

import random

from echotales.core.enums import Prominence, SpanType
from echotales.pipeline.persona.traits import TraitProfile
from echotales.pipeline.spans.delivery import DeliveryPolarity
from echotales.pipeline.voice.bank import (
    VoiceBank,
    age_band_for,
    parse_speaker_info,
    pick_mob_voice,
)
from echotales.pipeline.voice.casting import cast_voices
from echotales.pipeline.voice.delivery import pace_text, settings_for
from echotales.pipeline.voice.engine import SynthesisRequest, get_engine

SPEAKER_INFO = """ID  AGE  GENDER  ACCENTS  REGION
p225  23  F    English    Southern  England
p226  22  M    English    Surrey
p227  38  M    English    Cumbria
p228  64  F    English    Southern  England
p229  11  M    Scottish   Fife
"""


def _bank() -> VoiceBank:
    return VoiceBank(voices=parse_speaker_info(SPEAKER_INFO))


class TestBank:
    def test_parses_real_vctk_metadata_shape(self) -> None:
        voices = parse_speaker_info(SPEAKER_INFO)
        assert len(voices) == 5
        assert voices[0].speaker_id == "p225"
        assert voices[0].gender == "female"
        assert voices[0].age == 23

    def test_header_and_blank_lines_are_skipped(self) -> None:
        assert parse_speaker_info("ID AGE GENDER ACCENTS REGION\n\n") == []

    def test_age_bands_match_the_trait_vocabulary(self) -> None:
        assert age_band_for(8) == "child"
        assert age_band_for(22) == "youth"
        assert age_band_for(38) == "adult"
        assert age_band_for(64) == "elder"

    def test_exact_bucket_is_preferred(self) -> None:
        hits = _bank().nearest_bucket("male", "adult")
        assert [v.speaker_id for v in hits] == ["p227"]

    def test_age_is_relaxed_before_gender(self) -> None:
        """A listener forgives a character sounding a decade off far more
        readily than sounding like the wrong person entirely."""
        # No female:child in the bank; the nearest female is the youth p225.
        hits = _bank().nearest_bucket("female", "child")
        assert all(v.gender == "female" for v in hits)

    def test_unknown_gender_falls_back_on_age(self) -> None:
        hits = _bank().nearest_bucket("unknown", "adult")
        assert hits and all(v.age_band == "adult" for v in hits)

    def test_mob_voice_respects_gender(self) -> None:
        """The whole mob requirement: a crowd member has no identity worth
        modelling, but a female guard must not be voiced as a man."""
        rng = random.Random(0)
        for _ in range(10):
            picked = pick_mob_voice(_bank(), "female", "adult", rng=rng)
            assert picked is not None and picked.gender == "female"

    def test_mob_voice_is_reproducible_for_a_seed(self) -> None:
        """Re-synthesising one chapter must not silently recast the extras."""
        a = pick_mob_voice(_bank(), "male", "adult", rng=random.Random(7))
        b = pick_mob_voice(_bank(), "male", "adult", rng=random.Random(7))
        assert a is not None and b is not None and a.speaker_id == b.speaker_id


class TestCasting:
    def _profiles(self, n: int, gender: str = "male") -> dict[str, TraitProfile]:
        return {
            f"e{i}": TraitProfile(
                target_id=f"e{i}",
                label=f"Char{i}",
                gender=gender,
                age_band="adult",
                prominence=Prominence.RECURRING,
            )
            for i in range(n)
        }

    def test_assigns_a_voice_per_character(self) -> None:
        assignments, report = cast_voices("t", self._profiles(3), _bank())
        assert len(assignments) == 3
        assert report.assigned == 3

    def test_is_deterministic_for_a_seed(self) -> None:
        a, _ = cast_voices("t", self._profiles(3), _bank(), seed=5)
        b, _ = cast_voices("t", self._profiles(3), _bank(), seed=5)
        assert {k: v.speaker_id for k, v in a.items()} == {
            k: v.speaker_id for k, v in b.items()
        }

    def test_principals_are_cast_before_incidentals(self) -> None:
        """When a bucket runs short, reuse must land on the characters a
        listener is least likely to be tracking by voice."""
        profiles = self._profiles(2)
        profiles["e0"].prominence = Prominence.INCIDENTAL
        profiles["e1"].prominence = Prominence.PRINCIPAL
        assignments, _ = cast_voices("t", profiles, _bank())
        # Only one male:adult voice exists, so the principal takes it first
        # and the collision (if any) is recorded against the incidental.
        assert assignments["e1"].speaker_id == "p227"

    def test_collisions_are_recorded_not_hidden(self) -> None:
        """§8b accepts residual collisions and requires them to be visible;
        the system does not claim global collision-free assignment."""
        _, report = cast_voices("t", self._profiles(4), _bank())
        assert "does not" not in report.summary()  # sanity: summary renders
        assert "accepted by design" in report.summary()


class TestDelivery:
    def test_flat_marker_overrides_everything(self) -> None:
        """Non-negotiable #10: a protagonist described as 'expressionless'
        during the novel's most violent scenes must not be voiced
        dramatically -- the contrast *is* the characterisation."""
        loud = TraitProfile(target_id="e", label="X", extraversion=1.0)
        out = settings_for(
            span_type=SpanType.DIALOGUE,
            polarity=DeliveryPolarity.FLAT,
            profile=loud,
            text="I will kill you all!",
        )
        assert out.exaggeration <= 0.3
        assert "FLAT" in out.rationale

    def test_exclamation_raises_intensity_and_slows_guidance(self) -> None:
        out = settings_for(span_type=SpanType.DIALOGUE, text="Stop him!")
        assert out.exaggeration > 0.5
        assert out.cfg_weight < 0.5

    def test_narration_stays_near_neutral(self) -> None:
        out = settings_for(span_type=SpanType.NARRATION_ACTION, text="He walked north.")
        assert out.exaggeration <= 0.45

    def test_extraversion_offset_is_bounded(self) -> None:
        """A large offset would make a character's *neutral* lines sound
        permanently agitated."""
        shy = TraitProfile(target_id="e", label="X", extraversion=0.0)
        loud = TraitProfile(target_id="e", label="X", extraversion=1.0)
        a = settings_for(span_type=SpanType.DIALOGUE, profile=shy, text="Hello.")
        b = settings_for(span_type=SpanType.DIALOGUE, profile=loud, text="Hello.")
        assert abs(b.exaggeration - a.exaggeration) <= 0.21

    def test_short_text_is_not_repaced(self) -> None:
        assert pace_text("Run!") == "Run!"

    def test_em_dash_interruption_gets_room(self) -> None:
        text = "He raised his hand and said—" + "the words came fast and hard, " * 3
        assert " — " in pace_text(text)


class TestEngine:
    def test_stub_writes_a_real_wav(self, tmp_path) -> None:
        """The stub is not a no-op: downstream code opens these files and
        reads their duration, and a stub that wrote nothing would let a
        broken path pass CI."""
        import wave

        out = tmp_path / "a.wav"
        get_engine("stub").synthesize(SynthesisRequest(text="one two three", out_path=out))
        assert out.exists()
        with wave.open(str(out)) as fh:
            assert fh.getnframes() > 0

    def test_chatterbox_writes_pcm16_not_torchaudios_float_default(self, tmp_path) -> None:
        """Measured on a real chapter: `model.generate` returns a float32
        tensor, and `torchaudio.save` given one with no encoding hint writes
        IEEE-float WAV (format tag 3) -- playable, but not something the
        stdlib `wave` module (used by every duration read and every
        concatenation in `render/`) can open. The failure didn't surface
        until compose, after all 104 lines of a chapter had already been
        synthesised. `wave` accepting the file is the actual contract this
        engine has to satisfy."""
        import wave

        import torch
        from echotales.pipeline.voice.engine import ChatterboxEngine

        class _FakeModel:
            sr = 24000

            def generate(self, *args, **kwargs):
                # float32 in [-1, 1], exactly what chatterbox itself returns.
                return torch.zeros(1, 4800, dtype=torch.float32)

        engine = ChatterboxEngine()
        engine._model = _FakeModel()  # skip the real ~2GB download/load

        out = tmp_path / "line.wav"
        engine.synthesize(SynthesisRequest(text="hand it over", out_path=out))

        with wave.open(str(out)) as fh:
            assert fh.getsampwidth() == 2  # PCM16, not the 4-byte float default
            assert fh.getnframes() > 0

    def test_unknown_engine_raises_rather_than_silently_stubbing(self) -> None:
        """A run that quietly produced silent audio because of a typo would
        look successful until someone listened to it."""
        import pytest

        with pytest.raises(ValueError, match="unknown TTS engine"):
            get_engine("nope")
