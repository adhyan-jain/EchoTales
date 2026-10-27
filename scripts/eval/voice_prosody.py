"""How much an audiobook render varies in pitch and loudness, line to line and within a line.

A proxy for "does it sound performed or read flat", for comparing two renders of the same chapter (a bank change, the
emotion pass). It is not a quality score: a render that shouts every line varies a lot and is still bad, so a result
here is checked by ear before it is called better. Measured per span type, because narration is meant to stay calmer
than dialogue and pooling them hides whether dialogue actually moved.

    python scripts/eval/voice_prosody.py <manifest.jsonl> [<manifest.jsonl> ...] [--chapter 1] [--out result.json]

Per group (dialogue, narration): across-line spread of median pitch (semitones), mean within-line pitch range
(p90 - p10, semitones), across-line spread of loudness (dB), and the most common exaggeration value's share.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

import librosa
import numpy as np

_DIALOGUE = {"DIALOGUE", "INNER_MONOLOGUE", "CROWD_REACTION"}


def _clip(manifest: Path, recorded: str) -> Path | None:
    """The line's WAV: the recorded path, or the same file name beside the manifest (renders were moved since)."""
    path = Path(recorded)
    if path.exists():
        return path
    beside = manifest.parent / path.parent.name / path.name
    return beside if beside.exists() else None


def line_features(path: Path) -> tuple[float, float, float] | None:
    """(median pitch in semitones re 100 Hz, p90-p10 pitch range in semitones, mean RMS in dB) for one clip."""
    y, sr = librosa.load(str(path), sr=16000, mono=True)
    if y.size < sr * 0.3:
        return None
    f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=500, sr=sr, frame_length=1024)
    f0 = f0[voiced & ~np.isnan(f0)]
    if f0.size < 5:
        return None
    semis = 12 * np.log2(f0 / 100.0)
    rms = librosa.feature.rms(y=y)[0]
    loud = 20 * np.log10(np.maximum(rms[rms > rms.max() * 0.05], 1e-6))
    return float(np.median(semis)), float(np.percentile(semis, 90) - np.percentile(semis, 10)), float(loud.mean())


def summarise(manifest: Path, chapter: float | None) -> dict[str, object]:
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if chapter is not None:
        rows = [r for r in rows if float(r["chapter"]) == chapter]
    out: dict[str, object] = {"manifest": str(manifest), "lines": len(rows)}
    for group in ("dialogue", "narration"):
        picked = [r for r in rows if (r["span_type"] in _DIALOGUE) == (group == "dialogue")]
        feats = []
        for r in picked:
            clip = _clip(manifest, r.get("audio_path", ""))
            if clip is not None and (f := line_features(clip)) is not None:
                feats.append(f)
        dials = Counter(r["exaggeration"] for r in picked)
        out[group] = {
            "lines": len(picked),
            "measured": len(feats),
            "pitch_spread_st": round(statistics.pstdev(f[0] for f in feats), 2) if len(feats) > 1 else None,
            "within_line_range_st": round(statistics.mean(f[1] for f in feats), 2) if feats else None,
            "loudness_spread_db": round(statistics.pstdev(f[2] for f in feats), 2) if len(feats) > 1 else None,
            "top_dial_share": round(dials.most_common(1)[0][1] / len(picked), 2) if picked else None,
            "emotional_lines": sum(1 for r in picked if r.get("emotion", "neutral") != "neutral"),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--chapter", type=float, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    results = [summarise(m, args.chapter) for m in args.manifests]
    text = json.dumps(results, indent=2)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
