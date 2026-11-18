"""Audio QA on synthetic audio (sine and silence): no model, no GPU."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from echotales.pipeline.voice import qa

SR = 16000


def _sine(seconds: float, amp: float = 0.3, hz: float = 220.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float32)


def _build(tmp: Path, lines: list[dict], chapter: float = 1) -> Path:
    """`lines`: span_id, text, voice, speaker_id, block_index, audio (np array)."""
    rows = []
    for ln in lines:
        p = tmp / "ch1" / f"{ln['span_id']}.wav"
        p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(p), ln["audio"], SR, subtype="PCM_16")
        rows.append({
            "chapter": chapter, "block_index": ln["block_index"], "span_id": ln["span_id"],
            "span_type": "dialogue", "speaker_id": ln.get("speaker_id", ""), "speaker_label": ln.get("speaker_id", ""),
            "voice": ln["voice"], "text": ln["text"], "audio_path": str(p), "emotion": "neutral",
        })
    (tmp / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return tmp


def test_edge_silence_and_clipping_are_measured() -> None:
    x = np.concatenate([_silence(0.8), _sine(1.0), _silence(0.2)])
    lead, trail = qa.edge_silence(x, SR)
    assert lead == pytest.approx(0.8, abs=0.03)
    assert trail == pytest.approx(0.2, abs=0.03)
    assert qa.edge_silence(_silence(1.0), SR) == (1.0, 1.0)


def test_chapter_flags_silence_clipping_pace_and_missing_span(tmp_path: Path) -> None:
    text = "This is a perfectly ordinary sentence of speech."  # 40 letters
    good = np.concatenate([_silence(0.1), _sine(4.0), _silence(0.1)])
    _build(tmp_path, [
        {"span_id": "a", "text": text, "voice": "v1", "block_index": 1, "audio": good},
        {"span_id": "b", "text": text, "voice": "v1", "block_index": 2, "audio": np.concatenate([_silence(1.2), _sine(4.0)])},
        {"span_id": "c", "text": text, "voice": "v1", "block_index": 3, "audio": np.clip(_sine(4.0, amp=3.0), -1, 1)},
        {"span_id": "d", "text": text, "voice": "v1", "block_index": 4, "audio": _sine(0.5)},  # truncated: far too fast
        {"span_id": "e", "text": text, "voice": "v1", "block_index": 5, "audio": _silence(3.0)},
    ])
    r = qa.audit_chapter(tmp_path, 1, expected_span_ids=["a", "b", "c", "d", "e", "f"], with_f0=False)
    assert r.checks["coverage"]["absent_from_audio"] == ["f"]
    sc = r.checks["silence_clipping"]
    assert "b" in sc["long_edge"] and "c" in sc["clipped"] and "e" in sc["near_silent"]
    assert r.checks["pace"]["too_fast"] == ["d"]
    assert r.checks["intelligibility"]["skipped"]
    assert "silence_clipping" in r.summary()


def test_loudness_outlier_and_pause_rule(tmp_path: Path) -> None:
    lines = [
        {"span_id": f"s{i}", "text": "word " * 12, "voice": "v1" if i % 2 else "v2", "speaker_id": f"p{i % 2}",
         "block_index": i, "audio": _sine(2.0, amp=0.02 if i == 3 else 0.2)}
        for i in range(1, 7)
    ]
    _build(tmp_path, lines)
    r = qa.audit_chapter(tmp_path, 1, with_f0=False)
    assert r.checks["loudness"]["line_ids"] == ["s3"]
    p = r.checks["pauses"]
    assert p["record_disagrees_with_rule"] == []
    assert p["effective_seconds_by_kind"]["speaker_change"]["median"] == pytest.approx(0.45, abs=0.05)


def test_asr_round_trip_flags_dropped_ending_and_invented_tail(tmp_path: Path) -> None:
    ref = "I will meet you at the old station before the rain starts"
    _build(tmp_path, [
        {"span_id": "a", "text": ref, "voice": "v", "block_index": 1, "audio": _sine(3.0)},
        {"span_id": "b", "text": ref, "voice": "v", "block_index": 2, "audio": _sine(3.0)},
        {"span_id": "c", "text": ref, "voice": "v", "block_index": 3, "audio": _sine(3.0)},
        {"span_id": "d", "text": ref, "voice": "v", "block_index": 4, "audio": _sine(3.0)},
    ])
    heard = [
        "I will meet you at the old station before the rain starts.",
        "I will meet you at the old station",
        ref + " and then they all went home together tonight",
        "I will meet you at the old station before the rain starts rain starts rain starts",
    ]
    r = qa.audit_chapter(tmp_path, 1, transcribe=lambda paths: heard, with_f0=False)
    by = r.checks["intelligibility"]["by_flag"]
    assert by["dropped_ending"] == ["b"]
    assert "c" in by["invented_tail"]
    assert "d" in by["repeated_phrase"]
    assert "a" not in sum(by.values(), [])
    assert r.lines[0].asr["wer"] == 0.0


def test_cast_flags_shared_voice_between_speakers_in_one_conversation(tmp_path: Path) -> None:
    lines = [
        {"span_id": f"s{i}", "text": "word " * 12, "voice": "v1", "speaker_id": "alice" if i % 2 else "bob",
         "block_index": i, "audio": _sine(2.0)}
        for i in range(1, 5)
    ]
    _build(tmp_path, lines)
    r = qa.audit_chapter(
        tmp_path, 1, with_f0=False, bank_meta={"v1": {"gender": "female", "age": 30}},
        graph_gender={"alice": "female", "bob": "male"},
    )
    cast = r.checks["cast"]
    assert cast["shared_voice_in_conversation"][0]["voice"] == "v1"
    assert cast["graph_gender_contradicts_voice"][0]["speaker"] == "bob"


def test_word_error_rate_normalises_case_and_punctuation() -> None:
    assert qa.compare_text("“Hello, there!” he said.", "hello there he said")["wer"] == 0.0
    assert qa.compare_text("one two three four", "one two four")["wer"] == pytest.approx(0.25)


# --- fixes the first real measurement (LotM ch7) asked for -------------------------------------------------

from echotales.pipeline.voice import levels  # noqa: E402


def test_loudness_normalisation_brings_quiet_and_loud_lines_to_one_target(tmp_path: Path) -> None:
    quiet, loud = tmp_path / "q.wav", tmp_path / "l.wav"
    sf.write(str(quiet), _sine(2.0, amp=0.03), SR, subtype="PCM_16")
    sf.write(str(loud), _sine(2.0, amp=0.6), SR, subtype="PCM_16")
    for p in (quiet, loud):
        levels.normalise_file(p, target_lufs=-20.0)
        x, sr = qa.read_mono(p)
        assert qa.lufs(x, sr) == pytest.approx(-20.0, abs=1.0)
        assert float(np.abs(x).max()) <= 0.96  # never pushed into clipping


def test_normalisation_leaves_a_silent_file_alone(tmp_path: Path) -> None:
    p = tmp_path / "s.wav"
    sf.write(str(p), _silence(1.0), SR, subtype="PCM_16")
    assert levels.normalise_file(p) is None


class _ScriptedEngine:
    """Each call writes the next scripted duration of sine, the way a retry draws a fresh sample."""

    name = "scripted"

    def __init__(self, seconds: list[float]) -> None:
        self.seconds, self.calls = list(seconds), 0

    def synthesize(self, request):  # type: ignore[no-untyped-def]
        sf.write(str(request.out_path), _sine(self.seconds[min(self.calls, len(self.seconds) - 1)]), SR, subtype="PCM_16")
        self.calls += 1
        return request.out_path


def _req(tmp_path: Path, text: str):  # type: ignore[no-untyped-def]
    from echotales.pipeline.voice.engine import SynthesisRequest

    return SynthesisRequest(text=text, out_path=tmp_path / "line.wav")


def test_a_runaway_generation_is_resynthesised_and_the_better_take_kept(tmp_path: Path) -> None:
    text = "No problem at all, really."  # ~22 characters: about 1.4 s of speech
    eng = _ScriptedEngine([6.0, 5.0, 1.5])
    result = levels.synthesize_checked(eng, _req(tmp_path, text), max_retries=2)
    assert eng.calls == 3 and result.retries == 2 and not result.gave_up
    assert qa.read_mono(tmp_path / "line.wav")[0].shape[0] / SR == pytest.approx(1.5, abs=0.05)


def test_retries_are_bounded_and_the_least_bad_take_is_kept(tmp_path: Path) -> None:
    text = "No problem at all, really."
    eng = _ScriptedEngine([6.0, 9.0, 4.0])
    result = levels.synthesize_checked(eng, _req(tmp_path, text), max_retries=2)
    assert eng.calls == 3 and result.gave_up
    assert qa.read_mono(tmp_path / "line.wav")[0].shape[0] / SR == pytest.approx(4.0, abs=0.05)


def test_a_retry_that_raises_still_leaves_the_best_earlier_take_in_place(tmp_path: Path) -> None:
    """A crash mid-retry left the half-written failed take at the output path while the better first take was deleted."""

    class _Crashes(_ScriptedEngine):
        def synthesize(self, request):  # type: ignore[no-untyped-def]
            if self.calls >= 1:
                sf.write(str(request.out_path), _sine(9.0), SR, subtype="PCM_16")  # the take that was being written
                self.calls += 1
                raise RuntimeError("out of memory")
            return super().synthesize(request)

    eng = _Crashes([6.0])
    with pytest.raises(RuntimeError):
        levels.synthesize_checked(eng, _req(tmp_path, "No problem at all, really."), max_retries=2)
    assert qa.read_mono(tmp_path / "line.wav")[0].shape[0] / SR == pytest.approx(6.0, abs=0.05)
    assert not (tmp_path / "line.best.wav").exists()


def test_a_good_first_take_is_not_retried(tmp_path: Path) -> None:
    eng = _ScriptedEngine([1.5])
    result = levels.synthesize_checked(eng, _req(tmp_path, "No problem at all, really."), max_retries=2)
    assert eng.calls == 1 and result.retries == 0
