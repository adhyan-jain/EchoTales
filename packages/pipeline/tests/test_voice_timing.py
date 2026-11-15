"""Audio timing record: durations, both clocks, and loud failure on a bad WAV."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from echotales.pipeline.voice.export import gaps_for
from echotales.pipeline.voice.runner import chapter_track
from echotales.pipeline.voice.timing import (
    TimingError,
    build_timing,
    duration_of_blocks,
    load_timing,
)

RATE = 8000


def _wav(path: Path, seconds: float, rate: int = RATE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(b"\x01\x00" * int(rate * seconds))
    return path


#: (span id, block, voice, span type, seconds)
LINES = [
    ("s0", 1, "narr", "NARRATION_DESCRIPTION", 1.0),
    ("s1", 1, "narr", "NARRATION_DESCRIPTION", 0.5),  # same block, same voice: 0.25
    ("s2", 2, "ann", "DIALOGUE", 0.75),  # new block, new voice: 0.45
    ("s3", 3, "ann", "DIALOGUE", 0.4),  # new block, same voice: 0.6
    ("s4", 7, "narr", "NARRATION_ACTION", 1.2),  # jump over blocks: 1.4
]


def _audio(tmp_path: Path, lines=LINES) -> Path:
    rows = []
    for span, block, voice, st, sec in lines:
        p = _wav(tmp_path / "ch1" / f"{span}.wav", sec)
        rows.append({
            "chapter": 1.0, "block_index": block, "span_id": span, "span_type": st,
            "speaker_id": voice, "speaker_label": voice.upper(), "voice": voice,
            "text": f"text {span}", "audio_path": str(p), "emotion": "calm",
        })
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return tmp_path


def test_durations_and_both_clocks(tmp_path):
    t = build_timing(_audio(tmp_path), 1.0)
    assert [x.span_id for x in t] == ["s0", "s1", "s2", "s3", "s4"]
    assert [x.duration for x in t] == pytest.approx([1.0, 0.5, 0.75, 0.4, 1.2])
    assert t[0].start_gapless == 0.0 and t[-1].end_gapless == pytest.approx(3.85)
    assert t[1].start_gapless == pytest.approx(t[0].end_gapless)
    assert [x.gap_before for x in t] == pytest.approx([0.0, 0.25, 0.45, 0.6, 1.4])
    assert t[1].start_gapped == pytest.approx(1.25)
    assert t[-1].end_gapped == pytest.approx(3.85 + 0.25 + 0.45 + 0.6 + 1.4)
    assert t[2].emotion == "calm" and t[2].speaker_label == "ANN"


def test_gapped_clock_matches_real_chapter_wav(tmp_path):
    t = build_timing(_audio(tmp_path), 1.0)
    lines = [SimpleNamespace(block_index=b, voice=v, span_type=st) for _, b, v, st, _ in LINES]
    out = chapter_track([Path(x.audio_path) for x in t], tmp_path / "real.wav", gaps=gaps_for(lines))
    with wave.open(str(out), "rb") as fh:
        real = fh.getnframes() / fh.getframerate()
    assert abs(t[-1].end_gapped - real) <= 1.0 / RATE


def test_non_sample_aligned_gap_still_matches(tmp_path):
    # 0.45 s at 22050 Hz is 9922.5 frames: the real file truncates, so the clock must too.
    rate = 22050
    rows = []
    for i, voice in enumerate(["a", "b"] * 20):
        p = _wav(tmp_path / "ch1" / f"s{i}.wav", 0.0453, rate)
        rows.append({"chapter": 1.0, "block_index": 1, "span_id": f"s{i}", "span_type": "DIALOGUE",
                     "voice": voice, "audio_path": str(p)})
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    t = build_timing(tmp_path, 1.0)
    out = chapter_track(
        [Path(x.audio_path) for x in t], tmp_path / "r.wav",
        gaps=gaps_for([SimpleNamespace(**r) for r in rows]),
    )
    with wave.open(str(out), "rb") as fh:
        real = fh.getnframes() / fh.getframerate()
    assert abs(t[-1].end_gapped - real) <= 1.0 / rate


def test_missing_wav_names_the_span(tmp_path):
    audio = _audio(tmp_path)
    (tmp_path / "ch1" / "s2.wav").unlink()
    with pytest.raises(TimingError, match="s2"):
        build_timing(audio, 1.0)


def test_zero_length_wav_names_the_span(tmp_path):
    audio = _audio(tmp_path)
    _wav(tmp_path / "ch1" / "s3.wav", 0.0)
    with pytest.raises(TimingError, match="s3"):
        build_timing(audio, 1.0)


def test_write_and_load_round_trip(tmp_path):
    audio = _audio(tmp_path)
    t = build_timing(audio, 1.0, write=True)
    assert (tmp_path / "ch1" / "timing.jsonl").exists()
    assert load_timing(audio, 1.0) == t


def test_unknown_schema_rejected(tmp_path):
    audio = _audio(tmp_path)
    build_timing(audio, 1.0, write=True)
    f = tmp_path / "ch1" / "timing.jsonl"
    f.write_text(f.read_text().replace('"schema_version":1', '"schema_version":9'))
    with pytest.raises(TimingError, match="schema_version"):
        load_timing(audio, 1.0)


def test_block_and_list_durations(tmp_path):
    t = build_timing(_audio(tmp_path), 1.0)
    assert duration_of_blocks(t, [1]) == pytest.approx(1.5)
    assert duration_of_blocks(t, [1], "gapped") == pytest.approx(1.75)
    assert duration_of_blocks(t, [1, 2]) == pytest.approx(2.25)
    assert duration_of_blocks(t, [1, 2], "gapped") == pytest.approx(1.75 + 0.45 + 0.75)
    assert duration_of_blocks(t, [1, 3], "gapped") == pytest.approx(1.75 + 0.4)  # no pause inside the set
    assert duration_of_blocks(t, [99]) == 0.0


def test_other_chapter_and_unvoiced_rows_ignored(tmp_path):
    audio = _audio(tmp_path)
    m = tmp_path / "manifest.jsonl"
    extra = [{"chapter": 2.0, "block_index": 1, "span_id": "x", "audio_path": "nope.wav"},
             {"chapter": 1.0, "block_index": 4, "span_id": "y", "audio_path": ""}]
    m.write_text(m.read_text() + "\n".join(json.dumps(r) for r in extra) + "\n")
    assert len(build_timing(audio, 1.0)) == 5
