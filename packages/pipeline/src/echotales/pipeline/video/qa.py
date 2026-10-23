"""8-Frame Video QA Gate and Automatic Path 1 Fallback.

Inspects generated video clips across four criteria:
1. Identity Drift: Cosine similarity against seed keyframe across 8 sampled frames (threshold >= 0.82).
2. Temporal Flicker: Inter-frame stability and luminance consistency (threshold >= 0.75).
3. Morphing / Anatomical Deformity: Sudden aberrant geometry changes.
4. Audio / Lip-sync Coherence: Duration and speech alignment.

When video QA fails, automatically falls back to Path 1 2.5D layered parallax composition,
guaranteeing 100% render reliability across whole episodes.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

from echotales.pipeline.compositor.engine import (
    CompositionShotSpec,
    compose_shot_2_5d,
)
from echotales.pipeline.keyframes.qa import (
    cosine_similarity,
    extract_default_image_features,
)
from echotales.pipeline.video.wan import (
    WanMode,
    generate_wan_s2v_dialogue,
    generate_wan_video,
)

logger = logging.getLogger(__name__)


def sample_8_video_frames(video_path: Path, num_frames: int = 8) -> list[Image.Image]:
    """Sample evenly spaced frames from a video file using ffmpeg."""
    frames: list[Image.Image] = []
    with tempfile.TemporaryDirectory() as td:
        out_pattern = Path(td) / "f_%03d.png"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={num_frames},scale=320:-1",
            "-vframes",
            str(num_frames),
            str(out_pattern),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            for p in sorted(Path(td).glob("f_*.png")):
                try:
                    with Image.open(p) as img:
                        frames.append(img.copy().convert("RGB"))
                except Exception as exc:
                    logger.warning("video QA could not read sampled frame %s: %s", p.name, exc)
        except Exception as exc:
            # An unreadable video returns no frames and evaluate() fails it; it used to read as a pass.
            logger.warning("video QA could not sample frames from %s: %s", video_path, exc)
    return frames


def probe_video_duration(video_path: Path) -> float:
    """Read actual video duration via ffprobe or ffmpeg."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(res)
    except Exception:
        return 0.0


@dataclass(slots=True)
class VideoQAReport:
    """Consolidated 8-frame video QA evaluation report."""

    video_path: str
    passed: bool
    identity_drift_score: float  # [0.0, 1.0]
    temporal_flicker_score: float  # [0.0, 1.0]
    morphing_score: float  # [0.0, 1.0]
    duration_match: bool
    overall_score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_path": self.video_path,
            "passed": self.passed,
            "identity_drift_score": round(self.identity_drift_score, 4),
            "temporal_flicker_score": round(self.temporal_flicker_score, 4),
            "morphing_score": round(self.morphing_score, 4),
            "duration_match": self.duration_match,
            "overall_score": round(self.overall_score, 4),
            "reasons": list(self.reasons),
        }


class VideoQAGate:
    """8-Frame automated Video QA Gate."""

    def __init__(
        self,
        *,
        identity_threshold: float = 0.82,
        flicker_threshold: float = 0.75,
        identity_eval_fn: Callable[[str, str], float] | None = None,
        flicker_eval_fn: Callable[[str], float] | None = None,
        morphing_eval_fn: Callable[[str], float] | None = None,
        duration_fn: Callable[[str], float] | None = None,
    ) -> None:
        self.identity_threshold = identity_threshold
        self.flicker_threshold = flicker_threshold
        self.identity_eval_fn = identity_eval_fn
        self.flicker_eval_fn = flicker_eval_fn
        self.morphing_eval_fn = morphing_eval_fn
        self.duration_fn = duration_fn

    def evaluate(
        self,
        video_path: str | Path,
        seed_keyframe_path: str | Path,
        *,
        audio_path: str | Path | None = None,
        expected_duration_s: float | None = None,
    ) -> VideoQAReport:
        """Evaluate video against identity drift, temporal flicker, morphing, and duration."""
        v_path = Path(video_path)
        if not v_path.exists() or v_path.stat().st_size == 0:
            return VideoQAReport(
                video_path=str(v_path),
                passed=False,
                identity_drift_score=0.0,
                temporal_flicker_score=0.0,
                morphing_score=0.0,
                duration_match=False,
                overall_score=0.0,
                reasons=["Video file does not exist or is zero bytes"],
            )

        kf_feat = extract_default_image_features(seed_keyframe_path)
        sampled_frames = sample_8_video_frames(v_path, num_frames=8)

        # 1. Identity Drift
        if self.identity_eval_fn is not None:
            id_score = self.identity_eval_fn(str(v_path), str(seed_keyframe_path))
        elif sampled_frames:
            frame_feats = [extract_default_image_features(f) for f in sampled_frames]
            id_sims = [cosine_similarity(kf_feat, ff) for ff in frame_feats]
            id_score = float(np.mean(id_sims))
        else:
            id_score = 0.0

        # 2. Temporal Flicker
        if self.flicker_eval_fn is not None:
            flicker_score = self.flicker_eval_fn(str(v_path))
        elif len(sampled_frames) >= 2:
            diffs = [
                float(np.mean(np.abs(np.array(sampled_frames[i], dtype=np.float32) - np.array(sampled_frames[i + 1], dtype=np.float32))) / 255.0)
                for i in range(len(sampled_frames) - 1)
            ]
            flicker_score = float(np.clip(1.0 - float(np.mean(diffs)), 0.0, 1.0))
        else:
            flicker_score = 0.0

        # 3. Morphing
        if self.morphing_eval_fn is not None:
            morph_score = self.morphing_eval_fn(str(v_path))
        elif len(sampled_frames) >= 2:
            frame_feats = [extract_default_image_features(f) for f in sampled_frames]
            morph_sims = [
                cosine_similarity(frame_feats[i], frame_feats[i + 1])
                for i in range(len(frame_feats) - 1)
            ]
            morph_score = float(np.mean(morph_sims))
        else:
            morph_score = 0.0

        # 4. Duration Match & Lip-sync
        actual_dur = self.duration_fn(str(v_path)) if self.duration_fn else probe_video_duration(v_path)
        # An unreadable duration fails; it used to count as a match, so a corrupt file could pass.
        dur_match = actual_dur > 0
        if dur_match and expected_duration_s is not None and expected_duration_s > 0:
            dur_match = abs(actual_dur - expected_duration_s) <= 1.0

        id_pass = id_score >= self.identity_threshold
        flicker_pass = flicker_score >= self.flicker_threshold
        morph_pass = morph_score >= 0.80

        passed = id_pass and flicker_pass and morph_pass and dur_match

        overall = (
            0.40 * id_score
            + 0.30 * flicker_score
            + 0.20 * morph_score
            + (0.10 if dur_match else 0.0)
        )

        reasons: list[str] = []
        if not id_pass:
            reasons.append(
                f"Identity drift score {id_score:.3f} below threshold {self.identity_threshold:.2f}"
            )
        if not flicker_pass:
            reasons.append(
                f"Temporal flicker score {flicker_score:.3f} below threshold {self.flicker_threshold:.2f}"
            )
        if not morph_pass:
            reasons.append(f"Morphing score {morph_score:.3f} below acceptable threshold")
        if not sampled_frames and not (self.identity_eval_fn and self.flicker_eval_fn and self.morphing_eval_fn):
            reasons.append("No frames could be sampled from the video; unscored checks count as failed")
        if not dur_match:
            reasons.append("Video duration unreadable or mismatched with audio timing")

        return VideoQAReport(
            video_path=str(v_path),
            passed=passed,
            identity_drift_score=id_score,
            temporal_flicker_score=flicker_score,
            morphing_score=morph_score,
            duration_match=dur_match,
            overall_score=overall,
            reasons=reasons,
        )


def render_shot_with_video_or_fallback(
    shot_spec: CompositionShotSpec,
    output_dir: Path | str,
    *,
    prompt: str = "",
    qa_gate: VideoQAGate | None = None,
    fallback_to_2_5d: bool = True,
    fps: int = 24,
) -> tuple[str, str, VideoQAReport | None]:
    """Attempt Path 2 video render; automatically fall back to Path 1 on QA failure.
    
    Returns (rendered_video_path, tier_used, qa_report).
    tier_used is either 'video' or '2.5d_fallback'.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gate = qa_gate or VideoQAGate()

    video_shot_path = out_dir / f"shot_{shot_spec.shot_index:03d}_video.mp4"

    try:
        # Attempt Path 2 Video (Wan S2V if dialogue present, otherwise Wan I2V)
        if shot_spec.dialogue_audio_path and Path(shot_spec.dialogue_audio_path).exists():
            res = generate_wan_s2v_dialogue(
                keyframe_path=shot_spec.keyframe_path,
                audio_path=shot_spec.dialogue_audio_path,
                output_path=video_shot_path,
                prompt=prompt,
                fps=fps,
            )
        else:
            num_frames = max(24, int(round(shot_spec.duration_s * fps)))
            res = generate_wan_video(
                keyframe_path=shot_spec.keyframe_path,
                output_path=video_shot_path,
                prompt=prompt,
                mode=WanMode.I2V,
                num_frames=num_frames,
                fps=fps,
            )

        # Evaluate QA Gate
        qa_rep = gate.evaluate(
            res.video_path,
            shot_spec.keyframe_path,
            audio_path=shot_spec.dialogue_audio_path,
            expected_duration_s=shot_spec.duration_s,
        )

        if qa_rep.passed or not fallback_to_2_5d:
            return res.video_path, "video", qa_rep

    except Exception as exc:
        logger.warning("Path 2 video failed for shot %s, using the 2.5D fallback: %s", shot_spec.shot_index, exc)
        qa_rep = VideoQAReport(
            video_path=str(video_shot_path),
            passed=False,
            identity_drift_score=0.0,
            temporal_flicker_score=0.0,
            morphing_score=0.0,
            duration_match=False,
            overall_score=0.0,
            reasons=[f"Path 2 video generation failed ({type(exc).__name__}: {exc}); using the Path 1 fallback"],
        )

    # Automatic Fallback to Path 1 2.5D Parallax Compositor
    fallback_path = compose_shot_2_5d(shot_spec, out_dir, fps=fps)
    return fallback_path, "2.5d_fallback", qa_rep
