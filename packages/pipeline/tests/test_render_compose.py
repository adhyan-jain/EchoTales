"""The compositor: audio concatenation, the stub, and (when `ffmpeg` is on
PATH) a real end-to-end encode (xyz.md Step 4, video revision)."""

from __future__ import annotations

import json
import shutil
import struct
import wave
from pathlib import Path

import pytest

from echotales.pipeline.render._png import write_solid_png
from echotales.pipeline.render.compose import (
    FfmpegComposeEngine,
    StubComposeEngine,
    concatenate_audio,
    get_engine,
)
from echotales.pipeline.render.timeline import TimedShot


def _write_wav(path, seconds: float, sample_rate: int = 24000) -> None:
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(struct.pack("<h", 0) * frames)


class TestConcatenateAudio:
    def test_concatenated_duration_is_the_sum(self, tmp_path) -> None:
        a, b = tmp_path / "a.wav", tmp_path / "b.wav"
        _write_wav(a, 1.0)
        _write_wav(b, 2.0)
        out = concatenate_audio([a, b], tmp_path / "out.wav")
        with wave.open(str(out)) as fh:
            assert abs(fh.getnframes() / fh.getframerate() - 3.0) < 0.01

    def test_mismatched_format_raises_rather_than_resampling(self, tmp_path) -> None:
        a, b = tmp_path / "a.wav", tmp_path / "b.wav"
        _write_wav(a, 1.0, sample_rate=24000)
        _write_wav(b, 1.0, sample_rate=16000)
        with pytest.raises(ValueError, match="different WAV format"):
            concatenate_audio([a, b], tmp_path / "out.wav")

    def test_no_real_files_writes_an_empty_wav(self, tmp_path) -> None:
        out = concatenate_audio([tmp_path / "missing.wav"], tmp_path / "out.wav")
        with wave.open(str(out)) as fh:
            assert fh.getnframes() == 0


class TestStubComposeEngine:
    def test_writes_real_concatenated_audio_and_a_shot_manifest(self, tmp_path) -> None:
        a = tmp_path / "a.wav"
        _write_wav(a, 1.5)
        shot = TimedShot(chapter=1.0, block_index=0, kind="pan", asset_path="x.png", start=0.0, end=1.5)

        out = StubComposeEngine().render([shot], [a], tmp_path / "ch1.mp4")
        assert out.with_suffix(".wav").exists()
        with wave.open(str(out.with_suffix(".wav"))) as fh:
            assert abs(fh.getnframes() / fh.getframerate() - 1.5) < 0.01

        shots = json.loads(out.with_suffix(".shots.json").read_text())
        assert shots[0]["block_index"] == 0


class TestGetEngine:
    def test_unknown_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown compose engine"):
            get_engine("nope")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
class TestFfmpegComposeEngineIntegration:
    def test_composites_a_real_playable_mp4(self, tmp_path) -> None:
        """One pan shot over a still panel, one cutaway to a 4-frame motion
        clip, muxed against real (silent) audio -- the whole chain, for
        real, end to end."""
        panel = tmp_path / "panel.png"
        write_solid_png(panel, 64, 64, (200, 40, 40))

        clip_dir = tmp_path / "clip"
        for i in range(4):
            write_solid_png(clip_dir / f"frame{i:04d}.png", 64, 64, (40, 200 - i * 20, 40))

        a, b = tmp_path / "a.wav", tmp_path / "b.wav"
        _write_wav(a, 1.0)
        _write_wav(b, 0.5)

        timeline = [
            TimedShot(chapter=1.0, block_index=0, kind="pan", asset_path=str(panel),
                      pan_direction="zoom_in", start=0.0, end=1.0),
            TimedShot(chapter=1.0, block_index=1, kind="clip", asset_path=str(clip_dir),
                      tag="clash", start=1.0, end=1.5),
        ]

        out = tmp_path / "ch1.mp4"
        FfmpegComposeEngine().render(timeline, [a, b], out)

        assert out.exists() and out.stat().st_size > 0
        import subprocess

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(out)],
            capture_output=True, text=True,
        )
        duration = float(probe.stdout.strip())
        assert 1.2 < duration < 1.8
