"""Automatic quality check for voiced chapters: measure what a listener would hear, from the files alone.

Nothing here needs a GPU or the voice engine. It reads `manifest.jsonl` and the per-line WAVs that `echotales voice`
wrote, so it runs in CI on synthetic audio and on a finished render without re-synthesis. Only the intelligibility
round trip needs a speech recogniser (Whisper via `transformers`, on CPU by default); it is injected, so tests and
`--no-asr` runs skip it.

Every check returns a count and the failing span ids. Thresholds are module constants, set from the first real
measurement (Lord of the Mysteries ch7, `docs/EVOLUTION.md` audio-QA section), not from a guess.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from echotales.pipeline.voice.export import gaps_for
from echotales.pipeline.voice.timing import LineTiming, build_timing

#: Frame RMS below this is silence. Chatterbox's noise floor sits far below it; a real breath or tail does not.
SILENCE_DB = -45.0
#: Leading or trailing silence longer than this is audible dead air on top of the inter-line gap.
EDGE_SILENCE_MAX_S = 0.6
#: A line whose whole-clip RMS is below this is effectively not spoken.
NEAR_SILENT_DB = -50.0
CLIP_LEVEL = 0.999
#: More than this fraction of samples at full scale is audible distortion.
CLIP_FRACTION_MAX = 0.001
#: Characters of text per second of speech (silence at the edges excluded). A truncated generation falls below the
#: band, a runaway or garbled one above; lines shorter than `PACE_MIN_CHARS` are mostly pause, so are not judged.
PACE_BAND = (7.0, 22.0)
PACE_MIN_CHARS = 6
#: A line further than this from the chapter's median loudness stands out against its neighbours.
LOUDNESS_OUTLIER_LU = 6.0
#: Words-wrong share above which a line counts as not saying its text.
WER_FLAG = 0.35
#: An effective pause (trailing silence + gap + leading silence) beyond this multiple of the nominal gap, or beyond
#: `PAUSE_MAX_S`, is a hole a listener hears.
PAUSE_MAX_S = 2.0
PAUSE_MIN_S = 0.15
#: Lines this close in the chapter are one conversation for the shared-voice check.
CONVERSATION_WINDOW = 12
#: Median F0 (Hz) below / above which a voice reads as male / female. Overlap region is not judged.
F0_MALE_MAX = 150.0
F0_FEMALE_MIN = 165.0
#: Two voices whose median F0 is within this many semitones, same gender, are hard to tell apart in a scene.
F0_SIMILAR_SEMITONES = 1.0

Transcriber = Callable[[Sequence[Path]], list[str]]


# ---------------------------------------------------------------- audio primitives

def read_mono(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x.mean(axis=1), int(sr)


def frame_db(x: np.ndarray, sr: int, hop_s: float = 0.01) -> np.ndarray:
    """RMS level in dBFS per `hop_s` frame."""
    hop = max(1, int(sr * hop_s))
    n = len(x) // hop
    if n == 0:
        return np.array([-120.0])
    frames = x[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def edge_silence(x: np.ndarray, sr: int, thresh_db: float = SILENCE_DB) -> tuple[float, float]:
    """Seconds of silence before the first and after the last non-silent frame."""
    db = frame_db(x, sr)
    live = np.flatnonzero(db > thresh_db)
    hop_s = len(x) / sr / len(db) if len(db) else 0.01
    if live.size == 0:
        total = len(x) / sr
        return total, total
    return float(live[0] * hop_s), float((len(db) - 1 - live[-1]) * hop_s)


def lufs(x: np.ndarray, sr: int) -> float | None:
    """BS.1770 integrated loudness; short clips are zero-padded to the 0.4 s block the meter needs (silence is gated)."""
    import pyloudnorm as pyln

    if not len(x) or float(np.abs(x).max()) < 1e-5:
        return None
    need = int(sr * 0.4) + 1
    if len(x) < need:
        x = np.pad(x, (0, need - len(x)))
    value = pyln.Meter(sr).integrated_loudness(x.astype(np.float64))
    return None if not np.isfinite(value) else float(value)


def median_f0(x: np.ndarray, sr: int) -> float | None:
    """Median fundamental frequency over voiced frames; None when too little is voiced."""
    import librosa

    y = librosa.resample(x, orig_sr=sr, target_sr=16000) if sr != 16000 else x
    if len(y) < 16000 * 0.5:
        return None
    f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=400, sr=16000, frame_length=1024)
    f0 = f0[voiced & np.isfinite(f0)]
    return float(np.median(f0)) if f0.size >= 10 else None


# ---------------------------------------------------------------- text comparison

_WORD = re.compile(r"[a-z0-9']+")


def normalise_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFKC", text).lower()
    t = t.replace("’", "'").replace("‘", "'").replace("-", " ").replace("—", " ")
    # A quote mark kept as an apostrophe (`‘gathering’`) made every quoted word a mismatch in the first measurement.
    return [w for w in (x.strip("'") for x in _WORD.findall(t)) if w]


def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, wa in enumerate(a, 1):
        cur = [i]
        for j, wb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (wa != wb)))
        prev = cur
    return prev[-1]


def compare_text(ref_text: str, heard: str) -> dict[str, Any]:
    """Word error rate and the three failure shapes a TTS model produces: a dropped ending, a repeated phrase and
    words invented after the text ran out."""
    ref, hyp = normalise_words(ref_text), normalise_words(heard)
    wer = edit_distance(ref, hyp) / max(1, len(ref))
    flags: list[str] = []
    if wer > WER_FLAG:
        flags.append("mismatch")
    if len(ref) >= 4 and wer > 0.15:
        tail = ref[-3:]
        if sum(w in hyp for w in tail) < 2:
            flags.append("dropped_ending")
    if len(hyp) - len(ref) >= 4 and wer > 0.2:
        flags.append("invented_tail")

    def trigram_counts(words: list[str]) -> dict[tuple[str, ...], int]:
        out: dict[tuple[str, ...], int] = defaultdict(int)
        for i in range(len(words) - 2):
            out[tuple(words[i:i + 3])] += 1
        return out

    h, r = trigram_counts(hyp), trigram_counts(ref)
    # Whole-line repeat ("No problem. No problem."): too short for a trigram, measured in ch7.
    doubled = len(ref) >= 1 and len(hyp) == 2 * len(ref) and hyp[: len(ref)] == hyp[len(ref):]
    if doubled or any(n >= 2 and r.get(g, 0) < n for g, n in h.items()):
        flags.append("repeated_phrase")
    return {"wer": round(wer, 3), "ref_words": len(ref), "heard": heard, "flags": flags}


# ---------------------------------------------------------------- the report

@dataclass(slots=True)
class LineMetrics:
    span_id: str
    order: int
    speaker: str
    voice: str
    text: str
    duration: float
    lead_s: float = 0.0
    trail_s: float = 0.0
    peak: float = 0.0
    rms_db: float = -120.0
    clip_fraction: float = 0.0
    cps: float | None = None
    lufs: float | None = None
    f0: float | None = None
    asr: dict[str, Any] | None = None


def speech_rate(text: str, spoken_seconds: float) -> float | None:
    """Characters per second of actual speech, or None when the line is too short or too silent to judge."""
    chars = len(re.sub(r"[\"“”‘’'\s]", "", text))
    return chars / spoken_seconds if chars >= PACE_MIN_CHARS and spoken_seconds > 0.05 else None


def measure_line(t: LineTiming, *, with_f0: bool = True) -> LineMetrics:
    x, sr = read_mono(Path(t.audio_path))
    lead, trail = edge_silence(x, sr)
    rms = float(np.sqrt((x ** 2).mean())) if len(x) else 0.0
    m = LineMetrics(
        span_id=t.span_id, order=t.order, speaker=t.speaker_label or t.speaker_id or "narrator", voice=t.voice,
        text=t.text, duration=t.duration, lead_s=lead, trail_s=trail,
        peak=float(np.abs(x).max()) if len(x) else 0.0,
        rms_db=20 * float(np.log10(max(rms, 1e-6))),
        clip_fraction=float((np.abs(x) >= CLIP_LEVEL).mean()) if len(x) else 0.0,
        lufs=lufs(x, sr),
    )
    spoken = t.duration - lead - trail
    m.cps = speech_rate(t.text, spoken)
    if with_f0 and spoken > 1.0:
        m.f0 = median_f0(x, sr)
    return m


def _ids(items: Sequence[LineMetrics | str]) -> list[str]:
    return [i if isinstance(i, str) else i.span_id for i in items]


def _check(failing: Sequence[LineMetrics | str], total: int, **extra: Any) -> dict[str, Any]:
    ids = _ids(failing)
    return {"count": len(ids), "of": total, "line_ids": ids, **extra}


def coverage_check(
    rows: Sequence[dict[str, Any]], expected_span_ids: Sequence[str] | None, chapter: float, audio_dir: Path
) -> dict[str, Any]:
    mine = [r for r in rows if r.get("chapter") == chapter]
    ids = [r.get("span_id", "") for r in mine]
    seen: set[str] = set()
    dup = [i for i in ids if i in seen or seen.add(i)]  # type: ignore[func-returns-value]
    empty = [r["span_id"] for r in mine if not re.search(r"\w", r.get("text", ""))]
    unvoiced = [r["span_id"] for r in mine if not r.get("audio_path")]
    missing_file: list[str] = []
    for r in mine:
        p = r.get("audio_path")
        if p and not (Path(p) if Path(p).is_absolute() else audio_dir / p).exists() and not (
            audio_dir / f"ch{chapter:g}" / Path(p).name
        ).exists():
            missing_file.append(r["span_id"])
    blocks = [r.get("block_index", 0) for r in mine]
    out_of_order = [mine[i]["span_id"] for i in range(1, len(mine)) if blocks[i] < blocks[i - 1]]
    absent = [s for s in (expected_span_ids or []) if s not in set(ids)]
    extra = [s for s in ids if expected_span_ids is not None and s not in set(expected_span_ids)]
    bad = sorted(set(dup + empty + unvoiced + missing_file + out_of_order + absent + extra))
    return _check(
        bad, len(expected_span_ids) if expected_span_ids is not None else len(mine),
        duplicated=dup, empty=empty, unvoiced=unvoiced, missing_wav=missing_file, out_of_order=out_of_order,
        absent_from_audio=absent, not_in_chapter=extra, compared_with_store=expected_span_ids is not None,
    )


def _spread(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {}
    a = np.asarray(values)
    return {"median": round(float(np.median(a)), 2), "std": round(float(a.std()), 2),
            "p5": round(float(np.percentile(a, 5)), 2), "p95": round(float(np.percentile(a, 95)), 2),
            "min": round(float(a.min()), 2), "max": round(float(a.max()), 2)}


def pause_check(timings: Sequence[LineTiming], metrics: Sequence[LineMetrics]) -> dict[str, Any]:
    """Effective pause a listener hears = previous line's tail silence + inserted gap + next line's head silence."""
    nominal = gaps_for(timings)  # type: ignore[arg-type]
    kinds: dict[str, list[float]] = defaultdict(list)
    wrong_record: list[str] = []
    long_: list[str] = []
    short: list[str] = []
    for i in range(1, len(timings)):
        t, prev = timings[i], timings[i - 1]
        if abs(t.gap_before - nominal[i - 1]) > 0.002:
            wrong_record.append(t.span_id)
        eff = metrics[i - 1].trail_s + t.gap_before + metrics[i].lead_s
        if t.block_index - prev.block_index > 1:
            kind = "scene"
        elif t.voice != prev.voice:
            kind = "speaker_change"
        elif t.block_index != prev.block_index:
            kind = "paragraph"
        else:
            kind = "same_speaker"
        kinds[kind].append(eff)
        if eff > max(PAUSE_MAX_S, nominal[i - 1] + 1.0) and kind != "scene":
            long_.append(t.span_id)
        if eff < PAUSE_MIN_S:
            short.append(t.span_id)
    return _check(
        sorted(set(wrong_record + long_ + short)), max(0, len(timings) - 1),
        record_disagrees_with_rule=wrong_record, too_long=long_, too_short=short,
        effective_seconds_by_kind={k: _spread(v) for k, v in kinds.items()},
    )


def cast_check(
    timings: Sequence[LineTiming],
    metrics: Sequence[LineMetrics],
    bank_meta: dict[str, dict[str, Any]] | None = None,
    graph_gender: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Who got which voice, and whether it can go wrong in a scene.

    `bank_meta`: voice id -> {gender, age}. `graph_gender`: speaker id -> gender the graph holds. Both optional; a
    missing one is reported as not checked, not as passing.
    """
    bank_meta = bank_meta or {}
    speakers: dict[str, dict[str, Any]] = {}
    for t, m in zip(timings, metrics):
        s = speakers.setdefault(t.speaker_id or t.speaker_label or "narrator", {
            "label": t.speaker_label or "narrator", "voices": set(), "lines": 0, "f0": []})
        s["voices"].add(t.voice)
        s["lines"] += 1
        if m.f0:
            s["f0"].append(m.f0)
    # Same voice for two different speakers within one conversation.
    shared: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for i, t in enumerate(timings):
        for u in timings[i + 1: i + 1 + CONVERSATION_WINDOW]:
            a, b = t.speaker_id or t.speaker_label, u.speaker_id or u.speaker_label
            if a != b and t.voice == u.voice:
                key = (*sorted((a, b)), t.voice)
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    shared.append({"speakers": [t.speaker_label or a, u.speaker_label or b], "voice": t.voice,
                                   "line_ids": [t.span_id, u.span_id]})
    # Different bank voices that sound alike: same gender, median F0 within a semitone.
    by_voice: dict[str, list[float]] = defaultdict(list)
    for t, m in zip(timings, metrics):
        if m.f0:
            by_voice[t.voice].append(m.f0)
    med = {v: float(np.median(f)) for v, f in by_voice.items()}
    similar: list[dict[str, Any]] = []
    voices_in_window: set[tuple[str, str]] = set()
    for i, t in enumerate(timings):
        for u in timings[i + 1: i + 1 + CONVERSATION_WINDOW]:
            if t.voice != u.voice:
                voices_in_window.add(tuple(sorted((t.voice, u.voice))))  # type: ignore[arg-type]
    for a, b in sorted(voices_in_window):
        if a in med and b in med:
            ga, gb = bank_meta.get(a, {}).get("gender"), bank_meta.get(b, {}).get("gender")
            semis = abs(12 * np.log2(med[a] / med[b]))
            if semis < F0_SIMILAR_SEMITONES and (ga == gb):
                similar.append({"voices": [a, b], "f0_hz": [round(med[a]), round(med[b])], "semitones": round(float(semis), 2)})
    # Gender: measured pitch against the bank's recorded gender, and the bank's gender against the graph's.
    pitch_gender: list[dict[str, Any]] = []
    graph_mismatch: list[dict[str, Any]] = []
    for v, f in med.items():
        g = bank_meta.get(v, {}).get("gender")
        if (g == "female" and f < F0_MALE_MAX) or (g == "male" and f > F0_FEMALE_MIN):
            pitch_gender.append({"voice": v, "recorded": g, "median_f0_hz": round(f)})
    for sid, s in speakers.items():
        gg = (graph_gender or {}).get(sid)
        for v in s["voices"]:
            vg = bank_meta.get(v, {}).get("gender")
            if gg in ("male", "female") and vg in ("male", "female") and gg != vg:
                graph_mismatch.append({"speaker": s["label"], "graph": gg, "voice": v, "voice_gender": vg})
    problems = len(shared) + len(similar) + len(pitch_gender) + len(graph_mismatch)
    return {
        "count": problems, "of": len(speakers),
        "line_ids": sorted({i for s in shared for i in s["line_ids"]}),
        "shared_voice_in_conversation": shared, "similar_voices_in_conversation": similar,
        "pitch_contradicts_recorded_gender": pitch_gender, "graph_gender_contradicts_voice": graph_mismatch,
        "graph_gender_checked": graph_gender is not None, "bank_metadata_checked": bool(bank_meta),
        "speakers": {k: {"label": v["label"], "voices": sorted(v["voices"]), "lines": v["lines"]} for k, v in speakers.items()},
    }


@dataclass(slots=True)
class QAReport:
    chapter: float
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    lines: list[LineMetrics] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        from dataclasses import asdict

        return {"chapter": self.chapter, "notes": self.notes, "checks": self.checks,
                "lines": [asdict(m) for m in self.lines]}

    def summary(self) -> str:
        rows = [f"audio QA, chapter {self.chapter:g}: {len(self.lines)} lines"]
        for name, c in self.checks.items():
            if c.get("skipped"):
                rows.append(f"  {name:<14} skipped ({c['skipped']})")
                continue
            extra = ""
            if name == "loudness":
                extra = f"  median {c['lufs'].get('median')} LUFS, std {c['lufs'].get('std')} LU"
            elif name == "intelligibility":
                extra = f"  overall WER {c['overall_wer']:.3f}, mean per line {c['mean_line_wer']:.3f}"
            elif name == "pauses":
                extra = "  eff. s: " + ", ".join(f"{k} {v.get('median')}" for k, v in c["effective_seconds_by_kind"].items())
            rows.append(f"  {name:<14} {c['count']:>3} of {c['of']:<4}{extra}")
            if c["count"] and c.get("line_ids"):
                rows.append(f"      e.g. {', '.join(c['line_ids'][:5])}")
        rows += [f"  note: {n}" for n in self.notes]
        return "\n".join(rows)


def audit_chapter(
    audio_dir: str | Path,
    chapter: float,
    *,
    expected_span_ids: Sequence[str] | None = None,
    transcribe: Transcriber | None = None,
    bank_meta: dict[str, dict[str, Any]] | None = None,
    graph_gender: dict[str, str] | None = None,
    with_f0: bool = True,
) -> QAReport:
    audio_dir = Path(audio_dir)
    rows = [json.loads(x) for x in (audio_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    report = QAReport(chapter=chapter)
    report.checks["coverage"] = coverage_check(rows, expected_span_ids, chapter, audio_dir)
    if report.checks["coverage"]["missing_wav"] or report.checks["coverage"]["unvoiced"]:
        report.notes.append("unvoiced or missing WAVs: audio checks below cover only the files that exist")
        rows = [r for r in rows if r.get("audio_path") and Path(r["audio_path"]).exists()]
    timings = build_timing(audio_dir, chapter)
    metrics = [measure_line(t, with_f0=with_f0) for t in timings]
    report.lines = metrics
    n = len(metrics)

    report.checks["silence_clipping"] = _check(
        [m for m in metrics if m.lead_s > EDGE_SILENCE_MAX_S or m.trail_s > EDGE_SILENCE_MAX_S
         or m.clip_fraction > CLIP_FRACTION_MAX or m.rms_db < NEAR_SILENT_DB], n,
        long_edge=_ids([m for m in metrics if m.lead_s > EDGE_SILENCE_MAX_S or m.trail_s > EDGE_SILENCE_MAX_S]),
        clipped=_ids([m for m in metrics if m.clip_fraction > CLIP_FRACTION_MAX]),
        near_silent=_ids([m for m in metrics if m.rms_db < NEAR_SILENT_DB]),
        lead_s=_spread([m.lead_s for m in metrics]), trail_s=_spread([m.trail_s for m in metrics]),
    )
    judged = [m for m in metrics if m.cps is not None]
    report.checks["pace"] = _check(
        [m for m in judged if not PACE_BAND[0] <= m.cps <= PACE_BAND[1]], len(judged),  # type: ignore[operator]
        too_slow=_ids([m for m in judged if m.cps < PACE_BAND[0]]),  # type: ignore[operator]
        too_fast=_ids([m for m in judged if m.cps > PACE_BAND[1]]),  # type: ignore[operator]
        chars_per_second=_spread([m.cps for m in judged if m.cps is not None]), band=list(PACE_BAND),
    )
    loud = [m for m in metrics if m.lufs is not None and m.duration >= 0.8]
    med = float(np.median([m.lufs for m in loud])) if loud else 0.0
    per_speaker: dict[str, list[float]] = defaultdict(list)
    for m in loud:
        per_speaker[m.voice].append(m.lufs)  # type: ignore[arg-type]
    voice_means = {v: round(float(np.mean(x)), 2) for v, x in per_speaker.items()}
    report.checks["loudness"] = _check(
        [m for m in loud if abs(m.lufs - med) > LOUDNESS_OUTLIER_LU], len(loud),  # type: ignore[operator]
        lufs=_spread([m.lufs for m in loud]), by_voice_mean=voice_means,
        voice_mean_range=round(max(voice_means.values()) - min(voice_means.values()), 2) if voice_means else 0.0,
        outlier_lu=LOUDNESS_OUTLIER_LU,
    )
    report.checks["pauses"] = pause_check(timings, metrics)
    report.checks["cast"] = cast_check(timings, metrics, bank_meta, graph_gender)

    if transcribe is None:
        report.checks["intelligibility"] = {"skipped": "no speech recogniser given"}
    else:
        heard = transcribe([Path(t.audio_path) for t in timings])
        wers, ref_total, err_total = [], 0, 0
        bad: list[LineMetrics] = []
        for m, h in zip(metrics, heard):
            m.asr = compare_text(m.text, h)
            wers.append(m.asr["wer"])
            ref_total += m.asr["ref_words"]
            err_total += round(m.asr["wer"] * m.asr["ref_words"])
            if m.asr["flags"]:
                bad.append(m)
        by_flag: dict[str, list[str]] = defaultdict(list)
        for m in bad:
            for f in m.asr["flags"]:  # type: ignore[index]
                by_flag[f].append(m.span_id)
        report.checks["intelligibility"] = _check(
            bad, n, overall_wer=err_total / max(1, ref_total), mean_line_wer=float(np.mean(wers)) if wers else 0.0,
            by_flag=dict(by_flag),
        )
    return report


def whisper_transcriber(model_id: str = "openai/whisper-base.en", device: str = "cpu") -> Transcriber:
    """Whisper through `transformers`, loaded on first use. CPU by default so the check never competes for the GPU."""

    def run(paths: Sequence[Path]) -> list[str]:
        import librosa
        from transformers import pipeline

        asr = pipeline("automatic-speech-recognition", model=model_id, device=device)
        out = []
        for p in paths:
            x, sr = read_mono(p)
            y = librosa.resample(x, orig_sr=sr, target_sr=16000) if sr != 16000 else x
            out.append(asr({"raw": y, "sampling_rate": 16000}, chunk_length_s=30)["text"].strip())
        return out

    return run
