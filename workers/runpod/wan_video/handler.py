"""RunPod serverless handler: image-to-video with Wan 2.2.

Speaks exactly what `echotales.pipeline.video.runpod_video.RunPodVideoEngine` sends and parses:

    input   {"keyframe": "<b64 image>", "last_frame": null, "audio": null, "prompt": str, "num_frames": int,
             "fps": int, "mode": "s2v" | "i2v", "model": "wan2.2-i2v"}
    output  {"video": "<b64 mp4>", "duration_s": float}      failure: {"error": "<message>"}

Why the failure shape: RunPod marks a job FAILED when the handler returns a dict with an "error" key, and the client
copies `error` into its exception text, so the owner sees the real cause instead of "no video in its output".

`mode` defaults to "s2v" in the contract dataclass, but this worker serves the image-to-video checkpoints only: audio
is accepted and ignored (reported as `audio_ignored`), a `last_frame` is refused rather than silently dropped.
torch / diffusers are imported inside `_load_pipeline`, so importing this module (the contract tests do) needs neither.
"""

from __future__ import annotations

import base64
import binascii
import io
import os
import tempfile
from typing import Any

MODEL_NAME = "wan2.2-i2v"
#: Wan needs 4n+1 frames; 5..161 keeps one clip within a few minutes of GPU time.
MIN_FRAMES, MAX_FRAMES = 5, 161
_PIPE: Any = None


def _fail(message: str) -> dict[str, str]:
    return {"error": message}


def _decode_image(value: Any, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"'{field}' must be a non-empty base64 image string")
    try:
        data = base64.b64decode(value.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"'{field}' is not valid base64: {exc}") from exc
    if not data:
        raise ValueError(f"'{field}' decoded to zero bytes")
    return data


def validate(inp: Any) -> dict[str, Any]:
    """Check the request against the client contract; raise ValueError with a message the owner can act on."""
    if not isinstance(inp, dict):
        raise ValueError("job input must be an object")
    model = inp.get("model", MODEL_NAME)
    if model != MODEL_NAME:
        raise ValueError(f"unsupported model {model!r}; this worker serves {MODEL_NAME!r}")
    mode = inp.get("mode", "i2v")
    if mode not in ("s2v", "i2v"):
        raise ValueError(f"unsupported mode {mode!r}; use 'i2v' (or the contract default 's2v', audio is ignored)")
    if inp.get("last_frame"):
        raise ValueError("'last_frame' is not supported by this worker (first-frame image-to-video only)")
    frames, fps = inp.get("num_frames", 81), inp.get("fps", 24)
    if not isinstance(frames, int) or isinstance(frames, bool) or not MIN_FRAMES <= frames <= MAX_FRAMES:
        raise ValueError(f"'num_frames' must be an integer in {MIN_FRAMES}..{MAX_FRAMES}, got {frames!r}")
    if (frames - 1) % 4:
        raise ValueError(f"'num_frames' must be 4n+1 (Wan's temporal stride), got {frames}")
    if not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 60:
        raise ValueError(f"'fps' must be an integer in 1..60, got {fps!r}")
    return {"keyframe": _decode_image(inp.get("keyframe"), "keyframe"), "prompt": str(inp.get("prompt") or ""),
            "num_frames": frames, "fps": fps, "audio_ignored": bool(inp.get("audio"))}


def _load_pipeline() -> Any:
    """Load once per worker. WAN_MODEL_ID defaults to the 5B hybrid (fits 24 GB); set the A14B repo for 80 GB."""
    global _PIPE
    if _PIPE is None:
        import torch
        from diffusers import WanImageToVideoPipeline

        model_id = os.environ.get("WAN_MODEL_ID", "Wan-AI/Wan2.2-TI2V-5B-Diffusers")
        pipe = WanImageToVideoPipeline.from_pretrained(model_id, torch_dtype=torch.bfloat16)
        if os.environ.get("WAN_OFFLOAD", "0") == "1":
            pipe.enable_model_cpu_offload()
        else:
            pipe.to("cuda")
        _PIPE = pipe
    return _PIPE


def _run(params: dict[str, Any]) -> bytes:
    """Heavy part (GPU): keyframe bytes -> mp4 bytes. Tests replace this."""
    from diffusers.utils import export_to_video
    from PIL import Image

    pipe = _load_pipeline()
    width = int(os.environ.get("WAN_WIDTH", "832"))
    height = int(os.environ.get("WAN_HEIGHT", "480"))
    image = Image.open(io.BytesIO(params["keyframe"])).convert("RGB").resize((width, height))
    frames = pipe(image=image, prompt=params["prompt"], height=height, width=width,
                  num_frames=params["num_frames"]).frames[0]
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        export_to_video(frames, tmp.name, fps=params["fps"])
        with open(tmp.name, "rb") as fh:
            return fh.read()


def handler(job: dict[str, Any]) -> dict[str, Any]:
    try:
        params = validate(job.get("input"))
    except ValueError as exc:
        return _fail(str(exc))
    try:
        mp4 = _run(params)
    except Exception as exc:  # a CUDA OOM or a missing weight should reach the owner as text, not a stack-only crash
        return _fail(f"wan generation failed: {type(exc).__name__}: {exc}"[:500])
    out: dict[str, Any] = {"video": base64.b64encode(mp4).decode("ascii"),
                           "duration_s": round(params["num_frames"] / params["fps"], 3)}
    if params["audio_ignored"]:
        out["audio_ignored"] = True
    return out


try:  # the runpod package exists in the image only; tests and local imports must not need it
    import runpod
except ImportError:  # pragma: no cover
    runpod = None

if __name__ == "__main__":
    if runpod is None:
        raise SystemExit("the 'runpod' package is not installed; this file is the serverless entry point")
    runpod.serverless.start({"handler": handler})
