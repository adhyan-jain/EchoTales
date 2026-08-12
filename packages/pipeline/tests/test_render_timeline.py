"""Shot decisions + real audio durations -> timed shots (xyz.md Step 4, video revision)."""

from __future__ import annotations

import struct
import wave
from dataclasses import dataclass

from echotales.pipeline.render.director import ShotPlan
from echotales.pipeline.render.timeline import build_timeline, read_wav_duration


def _write_wav(path, seconds: float, sample_rate: int = 24000) -> None:
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(struct.pack("<h", 0) * frames)


@dataclass(slots=True)
class _Line:
    block_index: int
    audio_path: str


class TestReadWavDuration:
    def test_reads_the_real_duration(self, tmp_path) -> None:
        path = tmp_path / "a.wav"
        _write_wav(path, 2.0)
        assert abs(read_wav_duration(path) - 2.0) < 0.01


class TestBuildTimeline:
    def _panel_shot(self, block_index: int) -> ShotPlan:
        return ShotPlan(
            chapter=1.0, block_index=block_index, kind="pan",
            asset_path=f"block{block_index}.png", pan_direction="zoom_in",
        )

    def test_sums_lines_within_a_block_and_stamps_cumulative_time(self, tmp_path) -> None:
        a, b, c = tmp_path / "a.wav", tmp_path / "b.wav", tmp_path / "c.wav"
        _write_wav(a, 1.0)
        _write_wav(b, 1.5)
        _write_wav(c, 2.0)
        lines = [
            _Line(block_index=0, audio_path=str(a)),
            _Line(block_index=0, audio_path=str(b)),
            _Line(block_index=1, audio_path=str(c)),
        ]
        shots = [self._panel_shot(0), self._panel_shot(1)]

        timeline = build_timeline(1.0, lines, shots)
        assert len(timeline) == 2
        assert timeline[0].start == 0.0
        assert abs(timeline[0].end - 2.5) < 0.01
        assert abs(timeline[1].start - 2.5) < 0.01
        assert abs(timeline[1].end - 4.5) < 0.01

    def test_block_with_no_shot_carries_the_previous_one_forward(self, tmp_path) -> None:
        a, b = tmp_path / "a.wav", tmp_path / "b.wav"
        _write_wav(a, 1.0)
        _write_wav(b, 1.0)
        lines = [
            _Line(block_index=0, audio_path=str(a)),
            _Line(block_index=1, audio_path=str(b)),  # no ShotPlan for block 1
        ]
        shots = [self._panel_shot(0)]

        timeline = build_timeline(1.0, lines, shots)
        assert len(timeline) == 2
        assert timeline[1].asset_path == "block0.png"
        assert timeline[1].carried_over is True
        assert timeline[0].carried_over is False

    def test_leading_gap_with_no_prior_shot_is_dropped_not_invented(self, tmp_path) -> None:
        a = tmp_path / "a.wav"
        _write_wav(a, 1.0)
        lines = [_Line(block_index=0, audio_path=str(a))]

        timeline = build_timeline(1.0, lines, shots=[])
        assert timeline == []
