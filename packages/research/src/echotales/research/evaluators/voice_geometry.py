"""Speaker-embedding geometry of a voice bank.

The perceptual-cost hypothesis says a misattributed line costs more the more
the wrong voice differs from the right one. Listener judgments are the real
measure; this module provides the *objective* axis those judgments are
plotted against -- cosine distance between Chatterbox's own speaker
embeddings (the encoder that conditions synthesis, so "distance" is in the
space the generator actually uses). It is a stimulus-design variable and a
covariate, never a stand-in for perception (Latinus & Belin 2012: voice
identity is perceived categorically, so embedding distance and perceived
difference are not linear).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from echotales.pipeline.paths import RESEARCH_CACHE_DIR, VOICE_BANK_DIR

CACHE = RESEARCH_CACHE_DIR / "voice_embeddings_ears.json"


@dataclass(frozen=True, slots=True)
class BankGeometry:
    ids: list[str]
    genders: list[str]  # "M" / "F"
    emb: np.ndarray  # (n, d), L2-normalised

    def distance(self, a: str, b: str) -> float:
        i, j = self.ids.index(a), self.ids.index(b)
        return float(1.0 - self.emb[i] @ self.emb[j])

    def gender(self, a: str) -> str:
        return self.genders[self.ids.index(a)]


def _ve_weights() -> Path:
    hub = Path.home() / ".cache/huggingface/hub/models--ResembleAI--chatterbox/snapshots"
    for p in sorted(hub.glob("*/ve.safetensors")):
        return p
    raise FileNotFoundError("Chatterbox ve.safetensors not in the HF cache")


def ears_geometry(*, refresh: bool = False) -> BankGeometry:
    """Embed each native-English EARS speaker's neutral clip (cached)."""
    if CACHE.exists() and not refresh:
        d = json.loads(CACHE.read_text())
        return BankGeometry(d["ids"], d["genders"], np.asarray(d["emb"], dtype=float))

    import librosa
    import torch
    from chatterbox.models.voice_encoder import VoiceEncoder
    from safetensors.torch import load_file

    from echotales.pipeline.voice.bank import load_ears

    bank = load_ears(VOICE_BANK_DIR / "ears")
    ve = VoiceEncoder()
    ve.load_state_dict(load_file(str(_ve_weights())))
    ve.eval()
    ids, genders, embs = [], [], []
    with torch.inference_mode():
        for v in bank.voices:
            if not v.reference_clip:
                continue
            # Load at the encoder rate (librosa default resampler) so the
            # encoder never takes its resampy path, which is not installed.
            sr = ve.hp.sample_rate
            wav, _ = librosa.load(str(v.reference_clip), sr=sr)
            e = ve.embeds_from_wavs([wav], sample_rate=sr, as_spk=True)
            ids.append(v.speaker_id)
            genders.append("M" if v.gender == "male" else "F")
            embs.append(np.asarray(e, dtype=float))
    emb = np.vstack(embs)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"ids": ids, "genders": genders, "emb": emb.round(6).tolist()}))
    return BankGeometry(ids, genders, emb)


def synthetic_geometry(seed: int = 0, n_per_gender: int = 6, dim: int = 16) -> BankGeometry:
    """Deterministic stand-in for `--stub`: two gender clusters on the sphere."""
    rng = np.random.default_rng(seed)
    centres = {"M": rng.normal(size=dim), "F": rng.normal(size=dim)}
    ids, genders, rows = [], [], []
    for g, c in centres.items():
        for k in range(n_per_gender):
            ids.append(f"{g.lower()}{k}")
            genders.append(g)
            rows.append(c + 0.6 * rng.normal(size=dim))
    emb = np.vstack(rows)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    return BankGeometry(ids, genders, emb)


def load_encoder():
    """Chatterbox's own voice encoder (CPU), from the cached weights."""
    from chatterbox.models.voice_encoder import VoiceEncoder
    from safetensors.torch import load_file

    ve = VoiceEncoder()
    ve.load_state_dict(load_file(str(_ve_weights())))
    ve.eval()
    return ve


def identify(wav_path: Path, geom: BankGeometry, ve=None) -> tuple[str, dict[str, float]]:
    """Nearest bank voice to a rendered clip, plus its cosine to every voice.

    The manipulation check for perceptual stimuli: a listening study is only
    interpretable if the line meant to be in voice X demonstrably is.
    """
    import librosa

    ve = ve or load_encoder()
    wav, _ = librosa.load(str(wav_path), sr=ve.hp.sample_rate)
    e = np.asarray(ve.embeds_from_wavs([wav], sample_rate=ve.hp.sample_rate, as_spk=True), dtype=float)
    e /= np.linalg.norm(e)
    sims = geom.emb @ e
    return geom.ids[int(sims.argmax())], {v: float(x) for v, x in zip(geom.ids, sims)}
