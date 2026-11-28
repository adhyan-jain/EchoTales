"""Train one character LoRA for an SDXL-family anime checkpoint (NoobAI-XL, Illustrious-XL) from an assembled identity set.

Trainer chosen: diffusers' `train_text_to_image_lora_sdxl.py` (v0.35.0, pinned by sha256, fetched on first use into
~/.cache/echotales/tools). Why not kohya sd-scripts: it pins its own torch/diffusers/transformers and would need a second venv
(~8 GB of wheels over a link that measured 0.1 MB/s on 2026-11-28); the diffusers script runs in the project venv with only
`datasets` added (`datasets<5`: datasets 5 wants huggingface-hub 2, which breaks transformers 5).

What the script gives for an 8 GB card: fp16 UNet, LoRA params in fp32, gradient checkpointing, bitsandbytes 8-bit Adam, VAE and
text embeddings precomputed once (cached latents) and freed before training, rank 16-32. What it does NOT give: aspect-ratio
bucketing. `build_lora_set.py` therefore letterboxes every image to one square (identity sheets are plain grey, so padding costs
nothing), and the resolution here is that one size. Expected VRAM (not measured; no GPU was allowed in the session that wrote
this): about 7-8 GB at 768 px, 9-11 GB at 1024 px, so the default is 768 and 1024 is likely to OOM on the 4060 Laptop.

The text encoders are not trained, so the worker can encode prompts once and attach the LoRA per job (`_sdxl_art_worker.py`).
Runs as its own subprocess under `/tmp/echotales-gpu.lock`; `--dry-run` builds and validates the command with no GPU and no lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

LOCK = "/tmp/echotales-gpu.lock"
TRAINER_URL = "https://raw.githubusercontent.com/huggingface/diffusers/v0.35.0/examples/text_to_image/train_text_to_image_lora_sdxl.py"
TRAINER_SHA256 = "e733e9cce32fbe1802dc61426d75f3ab12ff6e824e3f2ee8fa258a60650bdfeb"
TRAINER_PATH = Path.home() / ".cache/echotales/tools/train_text_to_image_lora_sdxl.py"
#: The stock SDXL VAE overflows in fp16 (NaN latents); this fine-tune is the standard fix (MIT).
VAE_FP16_FIX = "madebyollin/sdxl-vae-fp16-fix"
DEFAULT_CHECKPOINT = {"noobai": "Laxhar/noobai-XL-1.1", "illustrious": "OnomaAIResearch/Illustrious-xl-early-release-v0"}
MIN_FREE_GIB = 7.0


def ensure_trainer(path: Path = TRAINER_PATH) -> Path:
    """The pinned trainer file; downloaded once, refused if its hash is not the pinned one."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(TRAINER_URL, path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != TRAINER_SHA256:
        raise RuntimeError(f"{path} does not match the pinned diffusers v0.35.0 trainer (sha256); delete it and retry")
    return path


def default_steps(n_images: int) -> int:
    """About 40 optimiser steps per image, clamped: a 12-image set is 480 steps, a 60-image set is capped at 1500."""
    return max(400, min(1500, 40 * n_images))


def read_set(data: Path) -> list[dict]:
    meta = data / "metadata.jsonl"
    if not meta.exists():
        raise FileNotFoundError(f"{meta} is missing; build the set with scripts/art/build_lora_set.py")
    rows = [json.loads(line) for line in meta.read_text().splitlines() if line.strip()]
    missing = [r["file_name"] for r in rows if not (data / r["file_name"]).exists() or not r.get("text")]
    if missing:
        raise ValueError(f"{len(missing)} metadata rows have no image or no caption: {missing[:3]}")
    if not rows:
        raise ValueError(f"{meta} has no rows")
    return rows


def build_command(a: argparse.Namespace, n_images: int, *, python: str = sys.executable, trainer: Path = TRAINER_PATH) -> list[str]:

    checkpoint = a.checkpoint or DEFAULT_CHECKPOINT[a.base]
    steps = a.steps or default_steps(n_images)
    cmd = [
        python, str(trainer),
        "--pretrained_model_name_or_path", checkpoint,
        "--pretrained_vae_model_name_or_path", a.vae,
        "--train_data_dir", str(a.data), "--caption_column", "text",
        "--resolution", str(a.resolution), "--train_batch_size", "1", "--gradient_accumulation_steps", str(a.grad_accum),
        "--gradient_checkpointing", "--use_8bit_adam", "--mixed_precision", "fp16",
        "--rank", str(a.rank), "--learning_rate", str(a.lr), "--lr_scheduler", "cosine", "--lr_warmup_steps", "50",
        "--max_train_steps", str(steps), "--checkpointing_steps", str(max(100, steps // 3)), "--seed", str(a.seed),
        "--dataloader_num_workers", "0", "--output_dir", str(a.out), "--report_to", "none",
    ]
    if not a.no_flip:
        cmd.append("--random_flip")
    return cmd


def locked(cmd: list[str], lock: str = LOCK) -> list[str]:
    """`flock` blocks until the other GPU job (ollama, a render) releases the card: no two models are ever resident together."""
    return ["flock", lock, *cmd]


def free_gib() -> float:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    return float(out.stdout.split()[0]) / 1024


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True, help="folder from build_lora_set.py (images + metadata.jsonl)")
    ap.add_argument("--out", type=Path, required=True, help="output folder; the LoRA is <out>/pytorch_lora_weights.safetensors")
    ap.add_argument("--base", choices=sorted(DEFAULT_CHECKPOINT), default="noobai")
    ap.add_argument("--checkpoint", default="", help="HF id or local diffusers folder; default from --base")
    ap.add_argument("--vae", default=VAE_FP16_FIX)
    ap.add_argument("--rank", type=int, default=16, choices=range(4, 65), metavar="4-64")
    ap.add_argument("--resolution", type=int, default=768)
    ap.add_argument("--steps", type=int, default=0, help="0 = default_steps(n_images)")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--no-flip", action="store_true", help="never mirror (asymmetric hair, scars, a left-hand sword)")
    ap.add_argument("--dry-run", action="store_true", help="validate the set and print the command; no GPU, no lock, no download")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    rows = read_set(a.data)
    if len(rows) < 8:
        print(f"warning: only {len(rows)} images; a character LoRA under ~8 images memorises poses", file=sys.stderr)
    cmd = build_command(a, len(rows), trainer=TRAINER_PATH)
    full = locked(cmd)
    if a.dry_run:
        print(json.dumps({"images": len(rows), "steps": a.steps or default_steps(len(rows)), "command": full}, indent=1))
        return 0
    if shutil.which("flock") is None:
        raise RuntimeError("flock is required (the GPU lock)")
    ensure_trainer()
    free = free_gib()
    if free < MIN_FREE_GIB:
        raise RuntimeError(f"only {free:.1f} GiB of GPU memory is free (need {MIN_FREE_GIB}); another GPU job is running")
    a.out.mkdir(parents=True, exist_ok=True)
    print("running:", shlex.join(full), flush=True)
    return subprocess.run(full, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
