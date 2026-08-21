"""TTS backends behind one interface.

Same shape as `llm/` (`base` protocol, `stub`, then real backends), and for
the same reason: the pipeline should name a *capability*, never a vendor, so
swapping engines is a config change rather than a rewrite.

**Engine choice, and why.** Chatterbox (Resemble AI) is the default:

- **MIT licensed.** XTTS-v2 is the better-known cloner and `4b` originally
  proposed it, but it ships under Coqui's CPML -- non-commercial only, from a
  company that has since shut down. Chatterbox closes most of the cloning gap
  without putting a licence ceiling on the project, so a later commercial
  decision is not a re-architecture.
- **It has an explicit emotion dial** (`exaggeration`), which XTTS does not.
  Emotion is a stated requirement here, and a model that exposes it beats one
  where it must be faked through reference-clip selection.
- **~5-second cloning** from a reference clip, which is exactly what the VCTK
  voice bank provides (`voice/bank.py`).

The `turbo` variant is the default model because of the hardware constraint
in HANDOFF Section 3: 8 GB of VRAM, and no stage may share the GPU with another
resident model. Turbo is ~350M parameters against the base model's 0.5B.
**`ollama serve` must not be resident when synthesis runs** -- that is the
same non-negotiable that governs the LLM stages, applied to this one.

`StubEngine` is not a toy: it is what makes the whole voice path testable
without a GPU, and it writes real (silent) WAV files so downstream code that
opens, measures or concatenates them is exercised for real.
"""

from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class SynthesisRequest:
    """One line to render."""

    text: str
    out_path: Path
    reference_clip: Path | None = None
    exaggeration: float = 0.5
    cfg_weight: float = 0.5


class TTSEngine(Protocol):
    """What the pipeline needs from a TTS backend."""

    name: str
    sample_rate: int

    def synthesize(self, request: SynthesisRequest) -> Path:
        """Render one line to `request.out_path` and return it."""
        ...


@dataclass(slots=True)
class StubEngine:
    """Writes real, silent WAV files of a plausible duration.

    Deliberately not a no-op. Downstream code opens these files, reads their
    duration and concatenates them; a stub that wrote nothing would leave all
    of that untested and would let a broken path pass CI. Duration is derived
    from the text so a manifest built against the stub has realistic
    timings.
    """

    name: str = "stub"
    sample_rate: int = 24000
    #: Average speaking rate. 150 wpm is a normal audiobook narration pace.
    words_per_minute: float = 150.0

    def synthesize(self, request: SynthesisRequest) -> Path:
        words = max(1, len(request.text.split()))
        seconds = max(0.3, words / self.words_per_minute * 60.0)
        frames = int(seconds * self.sample_rate)

        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(request.out_path), "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(self.sample_rate)
            fh.writeframes(struct.pack("<h", 0) * frames)
        return request.out_path


@dataclass(slots=True)
class ChatterboxEngine:
    """Resemble AI Chatterbox, loaded lazily.

    Import and model load happen on first use, never at construction, so that
    merely selecting this backend in config does not pull ~2 GB of weights
    onto the GPU during an unrelated pipeline stage.
    """

    name: str = "chatterbox"
    sample_rate: int = 24000
    model_id: str = "turbo"
    device: str = "cuda"
    _model: object | None = None

    def _ensure_model(self) -> object:
        if self._model is None:
            from chatterbox.tts import ChatterboxTTS  # type: ignore[import-not-found]

            self._model = ChatterboxTTS.from_pretrained(device=self.device)
            self.sample_rate = getattr(self._model, "sr", self.sample_rate)
        return self._model

    def synthesize(self, request: SynthesisRequest) -> Path:
        import torchaudio  # type: ignore[import-not-found]

        model = self._ensure_model()
        wav = model.generate(  # type: ignore[attr-defined]
            request.text,
            audio_prompt_path=(
                str(request.reference_clip) if request.reference_clip else None
            ),
            exaggeration=request.exaggeration,
            cfg_weight=request.cfg_weight,
        )
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        # **Explicit PCM16, not torchaudio's default.** `model.generate`
        # returns a float32 tensor, and `torchaudio.save` given one with no
        # further hint writes IEEE-float WAV (format tag 3) -- a real,
        # playable file, but not one the stdlib `wave` module can open.
        # Every duration read and every concatenation in this pipeline
        # (`render/timeline.py::read_wav_duration`,
        # `render/compose.py::concatenate_audio`) goes through `wave`, so a
        # float-format file is not a quality difference, it is a hard
        # failure the first time anything downstream touches the file --
        # measured: `wave.Error: unknown format: 3` composing a real
        # chapter, after all 104 lines had already been paid for. Fixed at
        # the write, where it can never recur, rather than teaching every
        # reader about a second WAV format.
        torchaudio.save(
            str(request.out_path), wav, self.sample_rate,
            encoding="PCM_S", bits_per_sample=16,
        )
        return request.out_path


def get_engine(name: str = "stub", **kwargs: object) -> TTSEngine:
    """Construct a backend by name.

    Unknown names raise rather than silently falling back to the stub: a run
    that quietly produced silent audio because of a typo would look like a
    successful render until someone listened to it.
    """
    if name == "stub":
        return StubEngine(**kwargs)  # type: ignore[arg-type]
    if name == "chatterbox":
        return ChatterboxEngine(**kwargs)  # type: ignore[arg-type]
    raise ValueError(f"unknown TTS engine {name!r}; expected 'stub' or 'chatterbox'")
