"""Unit tests for Path 2 Video Engine (Wan 2.2, LTX-2.5), Video QA Gate, and Fallback."""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

import pytest
from PIL import Image

from echotales.pipeline.compositor.engine import CompositionShotSpec
from echotales.pipeline.screenplay.schema import CameraMove
from echotales.pipeline.video.ltx import generate_ltx_video
from echotales.pipeline.video.qa import (
    VideoQAGate,
    VideoQAReport,
    render_shot_with_video_or_fallback,
)
from echotales.pipeline.video.wan import (
    WanMode,
    generate_wan_s2v_dialogue,
    generate_wan_video,
)


@pytest.fixture
def sample_keyframe(tmp_path: Path) -> Path:
    img_path = tmp_path / "keyframe.png"
    img = Image.new("RGB", (360, 640), (70, 90, 110))
    img.save(img_path, "PNG")
    return img_path


@pytest.fixture
def sample_audio(tmp_path: Path) -> Path:
    audio_path = tmp_path / "voice.wav"
    sample_rate = 24000
    duration_s = 0.5
    num_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = []
        for i in range(num_samples):
            val = int(12000.0 * math.sin(2.0 * math.pi * 440.0 * (i / sample_rate)))
            frames.append(struct.pack("<h", val))
        wf.writeframes(b"".join(frames))
    audio_path.write_bytes(buf.getvalue())
    return audio_path


def test_wan_video_generation(sample_keyframe: Path, sample_audio: Path, tmp_path: Path) -> None:
    # 1. Image-to-Video
    i2v_out = tmp_path / "i2v.mp4"
    res_i2v = generate_wan_video(
        keyframe_path=sample_keyframe,
        output_path=i2v_out,
        mode=WanMode.I2V,
        num_frames=24,
        fps=24,
    )
    assert i2v_out.exists()
    assert res_i2v.duration_s == pytest.approx(1.0)

    # 2. Sound-to-Video Lip Sync
    s2v_out = tmp_path / "s2v.mp4"
    res_s2v = generate_wan_s2v_dialogue(
        keyframe_path=sample_keyframe,
        audio_path=sample_audio,
        output_path=s2v_out,
        fps=24,
    )
    assert s2v_out.exists()
    assert res_s2v.mode == WanMode.S2V


def test_ltx_video_generation(sample_keyframe: Path, tmp_path: Path) -> None:
    ltx_out = tmp_path / "ltx.mp4"
    res = generate_ltx_video(
        prompt="Misty moorland at twilight with moving ground fog",
        output_path=ltx_out,
        keyframe_path=sample_keyframe,
        num_frames=48,
        fps=24,
    )
    assert ltx_out.exists()
    assert res.num_frames == 48


def test_video_qa_gate(sample_keyframe: Path, tmp_path: Path) -> None:
    gate = VideoQAGate(identity_threshold=0.82, flicker_threshold=0.75)

    dummy_video = tmp_path / "dummy.mp4"
    dummy_video.write_bytes(b"ftypisom" + b"\x00" * 200)

    # Clean passing evaluation
    rep = gate.evaluate(dummy_video, sample_keyframe)
    assert rep.passed is True
    assert rep.identity_drift_score >= 0.82

    # Failing evaluation with strict custom identity check
    failing_gate = VideoQAGate(
        identity_eval_fn=lambda v, kf: 0.65,  # Identity drift below 0.82
    )
    rep_fail = failing_gate.evaluate(dummy_video, sample_keyframe)
    assert rep_fail.passed is False
    assert any("Identity drift score" in r for r in rep_fail.reasons)


def test_video_fallback_to_path_1(
    sample_keyframe: Path,
    sample_audio: Path,
    tmp_path: Path,
) -> None:
    spec = CompositionShotSpec(
        shot_index=1,
        duration_s=0.2,
        keyframe_path=str(sample_keyframe),
        dialogue_audio_path=str(sample_audio),
        camera_move=CameraMove.SLOW_PUSH_IN,
    )

    # 1. When Video QA passes: returns video tier
    passing_gate = VideoQAGate()
    vid_path, tier, rep = render_shot_with_video_or_fallback(
        spec,
        tmp_path / "pass_dir",
        qa_gate=passing_gate,
        fallback_to_2_5d=True,
    )
    assert tier == "video"
    assert Path(vid_path).exists()
    assert rep is not None and rep.passed is True

    # 2. When Video QA fails: automatically falls back to Path 1 2.5D compositor!
    failing_gate = VideoQAGate(
        identity_eval_fn=lambda v, kf: 0.50,  # Below threshold
    )
    fb_path, fb_tier, fb_rep = render_shot_with_video_or_fallback(
        spec,
        tmp_path / "fail_dir",
        qa_gate=failing_gate,
        fallback_to_2_5d=True,
    )
    assert fb_tier == "2.5d_fallback"
    assert Path(fb_path).exists()
    assert Path(fb_path).suffix == ".mp4"
    assert fb_rep is not None and fb_rep.passed is False
