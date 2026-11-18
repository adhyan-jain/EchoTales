"""Narrator audition: shortlist candidate narrators from the loaded banks, then let a person listen.

Why this exists: the narrator is heard on every line of an audiobook, so picking one from a bank by a default id
(`p227`, a placeholder) or by gender alone is the wrong decision procedure. The bank holds thousands of readers
(LibriTTS-R) or ten studio-grade ones (Hi-Fi TTS); an acoustic filter cuts that to a dozen a person can audition in
ten minutes. The filter is deliberately crude and only removes the clearly unsuitable (noisy, rushed, drawling,
unpitched); the choice among what survives is a listening decision, which is what `--synthesize` prepares.

Measures are computed from the reference clip alone, with numpy and librosa already used by `voice/qa.py`:

- median F0 (`qa.median_f0`): spreads the shortlist across the pitch range so twelve candidates are not twelve
  similar baritones.
- SNR: 90th minus 10th percentile of 10 ms frame levels. A clip with no pause in it understates its own noise
  floor, so this is an upper bound on SNR, good enough to reject a room-tone-heavy recording.
- rate: loudness-envelope peaks per second of active speech, a syllable-rate proxy. It needs no transcript (the
  banks have none), and ranks pace correctly even though it is not syllables per second.
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from echotales.pipeline.voice import qa
from echotales.pipeline.voice.bank import BankVoice, VoiceBank
from echotales.pipeline.voice.engine import SynthesisRequest, TTSEngine

#: Clips noisier than this are rejected. Calibrated on the Hi-Fi TTS dev sample and LibriTTS-R dev-clean
#: (see the sample stats JSON), where restored LibriTTS-R readers and Hi-Fi "clean" speakers sit well
#: above it.
MIN_SNR_DB = 30.0
#: Envelope-peak rate band; measured on the same samples, normal audiobook reading sits mid-band.
RATE_BAND = (2.5, 6.5)

#: Three passages every candidate reads: the register the book is actually written in, a public-domain
#: control any listener can judge against a known text, and a shouted line, because a narrator who cannot raise
#: their voice without breaking is no use for the dialogue-heavy chapters. All own writing except p2.
PASSAGES: dict[str, str] = {
    "p1_dark": (
        "The corridor swallowed the lantern light long before the stairs, and the cold that rose from below "
        "carried no smell at all. He counted the steps the way a man counts debts, and did not look back."
    ),
    "p2_pride": (
        "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in "
        "want of a wife. However little known the feelings or views of such a man may be on his first entering a "
        "neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is "
        "considered the rightful property of some one or other of their daughters."
    ),
    "p3_shout": "Get back! Get away from the gate, now, or I will bring this whole wall down on your heads!",
}
#: (exaggeration, cfg_weight) per passage: the shout is asked for the way `delivery.py` asks for a heightened line.
_DELIVERY = {"p3_shout": (0.75, 0.40)}
_NEUTRAL_DELIVERY = (0.5, 0.5)


@dataclass(slots=True)
class ClipStats:
    voice_id: str = ""
    bank: str = ""
    licence: str = ""
    gender: str = ""
    name: str = ""
    clip: str = ""
    f0_hz: float | None = None
    snr_db: float = 0.0
    rate_hz: float = 0.0
    seconds: float = 0.0


def measure_array(x: np.ndarray, sr: int) -> ClipStats:
    db = qa.frame_db(x, sr)
    snr = float(np.percentile(db, 90) - np.percentile(db, 10))
    # Speaking span: first to last frame within 25 dB of the speech level, so pauses inside it count as time (a
    # slow reader pauses more) while the leading and trailing room tone does not. A peak is a smoothed-envelope
    # maximum standing 10 dB above the noise floor, with 80 ms either side to itself, so a syllable counts once.
    smooth = np.convolve(db, np.ones(5) / 5, mode="same")
    floor = np.percentile(db, 10)
    live = np.flatnonzero(db > np.percentile(db, 90) - 25)
    active = float(live[-1] - live[0] + 1) * 0.01 if live.size else 0.0
    peaks = 0
    for i in range(4, len(smooth) - 4):
        if smooth[i] >= smooth[i - 4 : i + 5].max() and smooth[i] > floor + 10:
            peaks += 1
    return ClipStats(
        f0_hz=qa.median_f0(x, sr),
        snr_db=round(snr, 1),
        rate_hz=round(peaks / active, 2) if active > 0 else 0.0,
        seconds=round(len(x) / sr, 2),
    )


def measure_voice(voice: BankVoice, bank: VoiceBank) -> ClipStats | None:
    if voice.reference_clip is None:
        return None
    try:
        x, sr = qa.read_mono(Path(voice.reference_clip))
    except Exception:  # noqa: BLE001 - one unreadable clip must not abort the whole audition
        return None
    s = measure_array(x, sr)
    s.voice_id, s.bank, s.licence = voice.speaker_id, bank.bank_id, bank.licence
    s.gender, s.name, s.clip = voice.gender, voice.name, str(voice.reference_clip)
    return s


def _eligible(s: ClipStats, min_snr_db: float, rate_band: tuple[float, float]) -> bool:
    return s.f0_hz is not None and s.snr_db >= min_snr_db and rate_band[0] <= s.rate_hz <= rate_band[1]


def _spread(pool: list[ClipStats], k: int) -> list[ClipStats]:
    """`k` clips spread over F0: start from the cleanest, then repeatedly take the one furthest in pitch from
    everything chosen (ties to the cleaner clip)."""
    if k <= 0 or not pool:
        return []
    chosen = [max(pool, key=lambda s: s.snr_db)]
    rest = [s for s in pool if s is not chosen[0]]
    while rest and len(chosen) < k:
        best = max(rest, key=lambda s: (min(abs(s.f0_hz - c.f0_hz) for c in chosen), s.snr_db))  # type: ignore[operator]
        chosen.append(best)
        rest.remove(best)
    return chosen


def shortlist(
    stats: list[ClipStats],
    n: int = 12,
    *,
    min_snr_db: float = MIN_SNR_DB,
    rate_band: tuple[float, float] = RATE_BAND,
) -> list[ClipStats]:
    """Up to `n` eligible candidates, half per gender, spread across pitch within each gender.

    A gender with too few eligible clips hands its unused places to the other, so the list is as long as the
    eligible pool allows rather than as balanced as possible.
    """
    pool = [s for s in stats if _eligible(s, min_snr_db, rate_band)]
    by_gender = {g: [s for s in pool if s.gender == g] for g in ("female", "male")}
    quota = {"female": n // 2 + n % 2, "male": n // 2}
    for g, other in (("female", "male"), ("male", "female")):
        spare = quota[g] - len(by_gender[g])
        if spare > 0:
            quota[g] -= spare
            quota[other] += spare
    picked = _spread(by_gender["female"], quota["female"]) + _spread(by_gender["male"], quota["male"])
    return picked[:n]


def audition(banks: list[VoiceBank], n: int = 12) -> tuple[list[ClipStats], list[ClipStats]]:
    """Measure every bank voice; return (shortlist, everything measured)."""
    measured = [s for bank in banks for v in bank.voices if (s := measure_voice(v, bank)) is not None]
    return shortlist(measured, n), measured


def write_stats(path: Path, picked: list[ClipStats], measured: list[ClipStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "filter": {"min_snr_db": MIN_SNR_DB, "rate_band": RATE_BAND},
                "measured": len(measured),
                "shortlist": [asdict(s) for s in picked],
                "rejected": [asdict(s) for s in measured if s not in picked],
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def synthesize_audition(picked: list[ClipStats], banks: list[VoiceBank], engine: TTSEngine, out_dir: Path) -> Path:
    """Voice every passage for every candidate through `engine`, cloning from the candidate's own reference clip,
    and write `index.html` listing name, bank, licence, stats and one player per passage."""
    out_dir.mkdir(parents=True, exist_ok=True)
    voices = {v.speaker_id: v for bank in banks for v in bank.voices}
    rows: list[str] = []
    for s in picked:
        voice = voices[s.voice_id]
        players = []
        for key, text in PASSAGES.items():
            exaggeration, cfg = _DELIVERY.get(key, _NEUTRAL_DELIVERY)
            target = out_dir / s.voice_id / f"{key}.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            engine.synthesize(SynthesisRequest(
                text=text, out_path=target, reference_clip=voice.reference_clip,
                exaggeration=exaggeration, cfg_weight=cfg,
            ))
            players.append(f'<figure><figcaption>{html.escape(key)}</figcaption>'
                           f'<audio controls preload="none" src="{html.escape(s.voice_id)}/{key}.wav"></audio></figure>')
        f0 = "n/a" if s.f0_hz is None else f"{s.f0_hz:.0f} Hz"
        rows.append(
            f"<section><h2>{html.escape(s.name or s.voice_id)}</h2>"
            f"<p>{html.escape(s.voice_id)} &middot; bank {html.escape(s.bank)} &middot; licence {html.escape(s.licence)} "
            f"&middot; {html.escape(s.gender)} &middot; F0 {f0} &middot; SNR {s.snr_db:.0f} dB "
            f"&middot; rate {s.rate_hz:.1f}/s</p>{''.join(players)}</section>"
        )
    page = out_dir / "index.html"
    page.write_text(
        "<!doctype html><meta charset=utf-8><title>Narrator audition</title>"
        "<style>body{font:16px system-ui;max-width:48rem;margin:2rem auto;padding:0 1rem}"
        "section{border-top:1px solid #8884;padding:.5rem 0}figure{margin:.4rem 0}audio{width:100%}</style>"
        "<h1>Narrator audition</h1>" + "".join(rows),
        encoding="utf-8",
    )
    return page
