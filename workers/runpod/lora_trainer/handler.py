"""RunPod serverless handler: train a Z-Image character LoRA from approved reference images.

Speaks exactly what `echotales.pipeline.cloud_lora.submit` sends:

    input   {"task": "train-lora", "base_model": "z-image-turbo", "trigger": str, "steps": int, "rank": int,
             "images": [{"name": str, "b64": "<b64 image>", "caption": str}, ...]}
    output  {"lora": "<b64 safetensors>"}          failure: {"error": "<message>"}

Trainer: ostris/ai-toolkit, run as a subprocess (`python run.py <config>`) from AI_TOOLKIT_DIR. UNCERTAIN: that
ai-toolkit trains Z-Image Turbo, and the config keys below, were not checked against a real run. Z-Image Turbo is a
step-distilled model, so ai-toolkit trains it through a "training adapter" that has to be loaded for the run; if the
installed ai-toolkit does not know the `zimage` architecture, training exits non-zero and this handler returns the
trainer's last output as the error. Any base other than `z-image-turbo` is refused up front, not attempted.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SUPPORTED_BASES = ("z-image-turbo",)
MAX_IMAGES, MAX_STEPS, MAX_RANK = 40, 4000, 64
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _fail(message: str) -> dict[str, str]:
    return {"error": message}


def validate(inp: Any) -> dict[str, Any]:
    if not isinstance(inp, dict):
        raise ValueError("job input must be an object")
    if inp.get("task") != "train-lora":
        raise ValueError(f"unsupported task {inp.get('task')!r}; this worker only runs 'train-lora'")
    base = inp.get("base_model")
    if base not in SUPPORTED_BASES:
        raise ValueError(f"unsupported base_model {base!r}; this worker trains only {', '.join(SUPPORTED_BASES)}")
    trigger = inp.get("trigger")
    if not isinstance(trigger, str) or not trigger.strip():
        raise ValueError("'trigger' must be a non-empty string")
    steps, rank = inp.get("steps", 1000), inp.get("rank", 16)
    if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= MAX_STEPS:
        raise ValueError(f"'steps' must be an integer in 1..{MAX_STEPS}, got {steps!r}")
    if not isinstance(rank, int) or isinstance(rank, bool) or not 1 <= rank <= MAX_RANK:
        raise ValueError(f"'rank' must be an integer in 1..{MAX_RANK}, got {rank!r}")
    images = inp.get("images")
    if not isinstance(images, list) or not 1 <= len(images) <= MAX_IMAGES:
        raise ValueError(f"'images' must be a list of 1..{MAX_IMAGES} entries")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(images):
        if not isinstance(item, dict) or not item.get("name") or not item.get("b64"):
            raise ValueError(f"'images[{i}]' needs 'name' and 'b64'")
        try:
            data = base64.b64decode(str(item["b64"]).split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"'images[{i}].b64' is not valid base64: {exc}") from exc
        if not data:
            raise ValueError(f"'images[{i}].b64' decoded to zero bytes")
        out.append({"name": _SAFE_NAME.sub("_", Path(str(item["name"])).name), "data": data,
                    "caption": str(item.get("caption") or trigger)})
    return {"trigger": trigger, "steps": steps, "rank": rank, "images": out, "base_model": base}


def _config(params: dict[str, Any], dataset: Path, out_dir: Path) -> dict[str, Any]:
    """ai-toolkit job config for a Z-Image Turbo LoRA. Keys follow its example configs; unverified, see module doc."""
    return {"job": "extension", "config": {
        "name": "echotales_lora", "process": [{
            "type": "sd_trainer", "training_folder": str(out_dir), "device": "cuda:0",
            "trigger_word": params["trigger"],
            "network": {"type": "lora", "linear": params["rank"], "linear_alpha": params["rank"]},
            "save": {"dtype": "float16", "save_every": params["steps"], "max_step_saves_to_keep": 1},
            "datasets": [{"folder_path": str(dataset), "caption_ext": "txt", "resolution": [768, 1024],
                          "cache_latents_to_disk": True}],
            "train": {"batch_size": 1, "steps": params["steps"], "gradient_checkpointing": True,
                      "noise_scheduler": "flowmatch", "optimizer": "adamw8bit", "lr": 1e-4, "dtype": "bf16"},
            "model": {"name_or_path": os.environ.get("ZIMAGE_MODEL_ID", "Tongyi-MAI/Z-Image-Turbo"),
                      "arch": "zimage", "quantize": True},
        }]}, "meta": {"name": "echotales_lora", "version": "1.0"}}


def _run(params: dict[str, Any]) -> bytes:
    """Heavy part (GPU): write the dataset, run the trainer, return the .safetensors bytes. Tests replace this."""
    toolkit = Path(os.environ.get("AI_TOOLKIT_DIR", "/opt/ai-toolkit"))
    if not (toolkit / "run.py").is_file():
        raise RuntimeError(f"ai-toolkit not found at {toolkit} (set AI_TOOLKIT_DIR)")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dataset, out_dir = root / "dataset", root / "out"
        dataset.mkdir()
        for img in params["images"]:
            (dataset / img["name"]).write_bytes(img["data"])
            (dataset / (Path(img["name"]).stem + ".txt")).write_text(img["caption"], encoding="utf-8")
        cfg = root / "config.json"  # ai-toolkit reads JSON as well as YAML (verify)
        cfg.write_text(json.dumps(_config(params, dataset, out_dir)), encoding="utf-8")
        proc = subprocess.run(["python", "run.py", str(cfg)], cwd=toolkit, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout)[-400:]
            raise RuntimeError(f"ai-toolkit exited {proc.returncode} (does this build support Z-Image Turbo?): {tail}")
        found = sorted(out_dir.rglob("*.safetensors"), key=lambda p: p.stat().st_mtime)
        if not found:
            raise RuntimeError("training finished but wrote no .safetensors file")
        return found[-1].read_bytes()


def handler(job: dict[str, Any]) -> dict[str, Any]:
    try:
        params = validate(job.get("input"))
    except ValueError as exc:
        return _fail(str(exc))
    try:
        lora = _run(params)
    except Exception as exc:
        return _fail(f"lora training failed: {type(exc).__name__}: {exc}"[:600])
    return {"lora": base64.b64encode(lora).decode("ascii")}


try:
    import runpod
except ImportError:  # pragma: no cover
    runpod = None

if __name__ == "__main__":
    if runpod is None:
        raise SystemExit("the 'runpod' package is not installed; this file is the serverless entry point")
    runpod.serverless.start({"handler": handler})
