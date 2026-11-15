"""Fixtures for the shot composer: real (tiny) panels, real WAVs, and a fake video engine that writes real MP4s.

Nothing here touches a GPU. The fake engine produces clips with ffmpeg from the panel it was given, so the
composer, cache, gate and fallback paths run on actual decoded video instead of mocks.
"""

from __future__ import annotations

import json
import subprocess
import wave
from dataclasses import replace
from pathlib import Path

import numpy as np
from echotales.pipeline.render.direction import PanelDirection
from echotales.pipeline.render.plan import PanelPlan, PlanCastMember, append_panel_plan
from echotales.pipeline.render.shots import LOCAL_LTX, PairDifference, VideoCapability
from echotales.pipeline.video.local import ClipRequest, ClipResult, snap_frames_8k1
from PIL import Image

W, H = 64, 96
OUT_W, OUT_H = 108, 192  # compose size: small, so ffmpeg is quick

#: LOCAL_LTX with the test frame size and a pair limit that lets the planner join same-shot panels.
FAKE_CAP: VideoCapability = replace(
    LOCAL_LTX, engine_id="fake", sizes=((W, H),), max_pair_difference=PairDifference.SAME_SHOT
)


def panel_image(path: Path, seed: int) -> Path:
    """Blocky random texture, so zooming or blending moves real pixels."""
    rng = np.random.default_rng(seed)
    blocks = rng.integers(0, 256, size=(H // 8, W // 8, 3), dtype=np.uint8)
    img = Image.fromarray(blocks).resize((W, H), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def write_wav(path: Path, seconds: float, rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(b"\x00\x00" * round(seconds * rate))


def write_mp4(frames: list[np.ndarray], path: Path, fps: int = 24) -> Path:
    """Encode (h, w, 3) uint8 frames with ffmpeg, near-lossless so SSIM tests measure the content."""
    h, w = frames[0].shape[:2]
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
         "-i", "-", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(path)],
        input=b"".join(f.tobytes() for f in frames), check=True, capture_output=True,
    )
    return path


# (panel seed, scene, cast, slot, lines[(block, type, speaker, seconds)]) -> modes with FAKE_CAP:
#   P0 INTERPOLATE to P1 (same scene, cast, shot size), P1 INTERPOLATE derived (two speakers, next is a scene
#   change), P2 ANIMATE, P3 HOLD (crowd), P4 HOLD (shorter than the minimum clip).
CHAPTER = [
    dict(scene=0, cast=["a"], slot="scene", lines=[(0, "NARRATION_DESCRIPTION", "", 3.02)]),
    dict(scene=0, cast=["a"], slot="scene",
         lines=[(1, "DIALOGUE", "a", 1.43), (2, "DIALOGUE", "b", 1.61)]),
    dict(scene=1, cast=["b"], slot="scene", lines=[(3, "NARRATION_ACTION", "", 2.51)]),
    dict(scene=1, cast=[], slot="crowd", lines=[(4, "NARRATION_ACTION", "", 2.04)]),
    dict(scene=2, cast=["a"], slot="scene", lines=[(5, "NARRATION_ACTION", "", 1.0)]),
]


def build_chapter(root: Path, chapter: float = 1.0, spec: list[dict] | None = None) -> tuple[Path, Path]:
    """Write a panel version directory and an audio directory; return (panels_dir, audio_dir)."""
    spec = spec or CHAPTER
    panels = root / "panels" / f"ch{chapter:g}" / "v1_test"
    audio = root / "audio"
    rows = []
    for i, p in enumerate(spec):
        blocks = [ln[0] for ln in p["lines"]]
        img = panel_image(panels / f"p{i}.png", seed=i + 1)
        append_panel_plan(
            panels / "panel_plan.jsonl",
            PanelPlan(
                novel_id="t", chapter=chapter, panel_seq=i, panel_id=f"t:{chapter:g}:{i}", scene_index=p["scene"],
                scene_state_id=f"state{p['scene']}", slot_kind=p["slot"], lead_block=blocks[0], block_indexes=blocks,
                cast=[PlanCastMember(self_id=c) for c in p["cast"]], location=f"place{p['scene']}",
                direction=PanelDirection(shot="medium", action="turns slowly", expression="calm"),
                prompt="x", engine="stub", width=W, height=H, seed=i, image_path=img.name, cache_key=f"k{i}",
                provenance="generated",
            ),
            truncate=i == 0,
        )
        for blk, kind, speaker, secs in p["lines"]:
            wav = audio / f"ch{chapter:g}" / f"line{blk}.wav"
            write_wav(wav, secs)
            rows.append({
                "chapter": chapter, "block_index": blk, "span_id": f"t:{chapter:g}:{blk}:0", "span_type": kind,
                "speaker_id": speaker, "speaker_label": speaker or "Narrator", "voice": "v1", "text": f"line {blk}.",
                "audio_path": str(wav),
            })
    audio.mkdir(parents=True, exist_ok=True)
    (audio / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return panels, audio


class FakeEngine:
    """Writes a real MP4 per request. `behaviour` picks what is wrong with it, if anything."""

    engine_id = "fake"

    def __init__(self, behaviour: str = "ok", identity: str = "fake-model-1") -> None:
        self.behaviour, self.identity = behaviour, identity
        self.batches: list[list[ClipRequest]] = []

    @property
    def requested(self) -> int:
        return sum(len(b) for b in self.batches)

    def model_identity(self) -> str:
        return self.identity

    def snap_frames(self, frames: int) -> int:
        return snap_frames_8k1(frames)

    def generate_clips(self, requests: list[ClipRequest]) -> list[ClipResult]:
        self.batches.append(list(requests))
        if self.behaviour == "raise":
            raise RuntimeError("worker exploded")
        out = []
        for r in requests:
            if self.behaviour == "fail":
                out.append(ClipResult(r.clip_id, False, "out of memory"))
                continue
            start = np.asarray(Image.open(r.start_image).convert("RGB"))
            end = np.asarray(Image.open(r.end_image).convert("RGB")) if r.end_image else None
            frames = self._frames(start, end, r.frames)
            write_mp4(frames, r.output, r.fps)
            out.append(ClipResult(r.clip_id, True, output=r.output, frames_written=len(frames),
                                  seconds={"denoise": 0.1}, peak_vram_gb=1.0))
        return out

    def _frames(self, start: np.ndarray, end: np.ndarray | None, n: int) -> list[np.ndarray]:
        h, w = start.shape[:2]
        frames = []
        for i in range(n):
            t = i / (n - 1)
            if self.behaviour == "still":
                frames.append(start)
                continue
            # Sub-pixel push-in (affine, bilinear): an integer crop would move in visible steps and trip the gate.
            z = 1 + 0.25 * t
            zoomed = np.asarray(Image.fromarray(start).transform(
                (w, h), Image.AFFINE, (1 / z, 0, w * (1 - 1 / z) / 2, 0, 1 / z, h * (1 - 1 / z) / 2), Image.BILINEAR))
            if end is not None:  # drift toward the end frame, landing exactly on it
                zoomed = zoomed.astype(np.float32) * (1 - t) + end.astype(np.float32) * t
            frames.append(zoomed.astype(np.uint8))
        if self.behaviour == "garbled":
            rng = np.random.default_rng(0)
            frames[n // 2] = rng.integers(0, 256, size=start.shape, dtype=np.uint8)
        if self.behaviour == "wrong_end" and end is not None:
            frames[-1] = np.asarray(Image.fromarray(255 - end))
        return frames


def same_content_embedder(images):
    """Every image embeds to the same direction: no drift anywhere (tests need no CLIP model)."""
    return np.ones((len(images), 4), dtype=np.float32)


def drifting_embedder(images):
    """The first image (the start) points one way, every later one is orthogonal: maximal drift."""
    out = np.zeros((len(images), 4), dtype=np.float32)
    out[0, 0] = 1.0
    out[1:, 1] = 1.0
    return out
