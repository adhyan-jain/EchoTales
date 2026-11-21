"""RunPod serverless handler: multi-reference keyframes with Qwen-Image-Edit.

Speaks exactly what `echotales.pipeline.render.runpod_edit.RunPodEditEngine` sends and parses:

    input   {"prompt", "negative_prompt", "width", "height", "seed", "references": ["<b64 png>", ...]}   (1..3 refs)
    output  {"image": "<b64 png>"}          failure: {"error": "<message>"}

`{"image": ...}` is one of the shapes `runpod._first_b64` accepts. The pipeline is Qwen-Image-Edit-2509 (the release
that takes several input images); torch / diffusers load lazily so importing this module needs neither.
"""

from __future__ import annotations

import base64
import binascii
import io
import os
from typing import Any

MAX_REFERENCES = 3  # the same cap as the engine's MAX_REFERENCES
MIN_SIDE, MAX_SIDE = 256, 2048
_PIPE: Any = None


def _fail(message: str) -> dict[str, str]:
    return {"error": message}


def validate(inp: Any) -> dict[str, Any]:
    if not isinstance(inp, dict):
        raise ValueError("job input must be an object")
    prompt = inp.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("'prompt' must be a non-empty string")
    refs = inp.get("references")
    if not isinstance(refs, list) or not 1 <= len(refs) <= MAX_REFERENCES:
        raise ValueError(f"'references' must be a list of 1..{MAX_REFERENCES} base64 images")
    decoded: list[bytes] = []
    for i, ref in enumerate(refs):
        try:
            data = base64.b64decode(str(ref).split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"'references[{i}]' is not valid base64: {exc}") from exc
        if not data:
            raise ValueError(f"'references[{i}]' decoded to zero bytes")
        decoded.append(data)
    width, height = inp.get("width", 1024), inp.get("height", 1024)
    for name, v in (("width", width), ("height", height)):
        if not isinstance(v, int) or isinstance(v, bool) or not MIN_SIDE <= v <= MAX_SIDE:
            raise ValueError(f"'{name}' must be an integer in {MIN_SIDE}..{MAX_SIDE}, got {v!r}")
    seed = inp.get("seed", 0)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError(f"'seed' must be an integer, got {seed!r}")
    return {"prompt": prompt, "negative_prompt": str(inp.get("negative_prompt") or " "), "width": width,
            "height": height, "seed": seed, "references": decoded}


def _load_pipeline() -> Any:
    """Load once per worker. About 40 GB of bf16 weights: an 80 GB GPU, or 48 GB with QWEN_OFFLOAD=1."""
    global _PIPE
    if _PIPE is None:
        import torch
        from diffusers import QwenImageEditPlusPipeline

        pipe = QwenImageEditPlusPipeline.from_pretrained(
            os.environ.get("QWEN_MODEL_ID", "Qwen/Qwen-Image-Edit-2509"), torch_dtype=torch.bfloat16)
        if os.environ.get("QWEN_OFFLOAD", "0") == "1":
            pipe.enable_model_cpu_offload()
        else:
            pipe.to("cuda")
        _PIPE = pipe
    return _PIPE


def _run(params: dict[str, Any]) -> bytes:
    """Heavy part (GPU): references + prompt -> PNG bytes. Tests replace this."""
    import torch
    from PIL import Image

    pipe = _load_pipeline()
    images = [Image.open(io.BytesIO(b)).convert("RGB") for b in params["references"]]
    result = pipe(image=images, prompt=params["prompt"], negative_prompt=params["negative_prompt"],
                  width=params["width"], height=params["height"], num_inference_steps=40, true_cfg_scale=4.0,
                  generator=torch.Generator("cuda").manual_seed(params["seed"])).images[0]
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


def handler(job: dict[str, Any]) -> dict[str, Any]:
    try:
        params = validate(job.get("input"))
    except ValueError as exc:
        return _fail(str(exc))
    try:
        png = _run(params)
    except Exception as exc:
        return _fail(f"qwen-image-edit failed: {type(exc).__name__}: {exc}"[:500])
    return {"image": base64.b64encode(png).decode("ascii")}


try:
    import runpod
except ImportError:  # pragma: no cover
    runpod = None

if __name__ == "__main__":
    if runpod is None:
        raise SystemExit("the 'runpod' package is not installed; this file is the serverless entry point")
    runpod.serverless.start({"handler": handler})
