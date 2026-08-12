"""Phase 8: voice casting and speech synthesis (`4b`, `architecture.md §8b`).

Four pieces, in dependency order:

- `bank.py` -- the reference-voice bank, built from CSTR VCTK's stated
  speaker metadata (age, gender, accent) rather than from a classifier's
  guess about a voice.
- `casting.py` -- assigns a bank voice per character, colouring **within**
  archetype buckets because §8b already established that global
  collision-free assignment is not achievable on this content.
- `delivery.py` -- turns a line's context into synthesis parameters, and is
  where non-negotiable #10 is enforced: an explicit delivery marker
  overrides scene sentiment and speaker baseline alike.
- `engine.py` / `runner.py` -- the pluggable TTS backend and the stage that
  renders a novel's script through it.
"""

from __future__ import annotations

from echotales.pipeline.voice.bank import (
    BankVoice,
    VoiceBank,
    load_vctk,
    parse_speaker_info,
    pick_mob_voice,
)
from echotales.pipeline.voice.casting import CastingReport, cast_voices
from echotales.pipeline.voice.delivery import DeliverySettings, pace_text, settings_for
from echotales.pipeline.voice.engine import (
    ChatterboxEngine,
    StubEngine,
    SynthesisRequest,
    get_engine,
)
from echotales.pipeline.voice.runner import AudioLine, VoiceReport, render_novel

__all__ = [
    "AudioLine",
    "BankVoice",
    "CastingReport",
    "ChatterboxEngine",
    "DeliverySettings",
    "StubEngine",
    "SynthesisRequest",
    "VoiceBank",
    "VoiceReport",
    "cast_voices",
    "get_engine",
    "load_vctk",
    "pace_text",
    "parse_speaker_info",
    "pick_mob_voice",
    "render_novel",
]
