"""LTX-Video 2B video worker. Runs in its OWN Python interpreter, one process per batch of clips.

Run it by file path with the video environment's interpreter (`ECHOTALES_VIDEO_PYTHON`, built by
`scripts/setup_video.sh`); it imports nothing from echotales and nothing heavy at import time, so the
main environment can import it to validate a job without torch:

    python ltx_worker.py --job job.json --result result.json
    python ltx_worker.py --job job.json --validate-only

Why a separate process and a separate interpreter:
- The video stack needs library versions the main environment does not have (torch 2.15 cu132, diffusers
  main, transformers 5.22, bitsandbytes), and changing the main environment is not allowed.
- The model cannot stay loaded between clips in one long-lived process on 8 GB. Measured (EVOLUTION
  4.146 probe): the transformer (3.85 GB) and a 97-frame VAE decode do not fit together, and a second
  clip in the same process ran out of memory while the transformer reloaded beside the resident VAE.
  A process that exits returns every byte, which is a guarantee a `del` plus `empty_cache` is not.

Memory plan, all of it measured on an RTX 4060 Laptop (8 GB) with about 5 GB of free RAM:
1. Prompts are encoded once by the NF4 T5 encoder (4.3 GB of VRAM), which is then freed. Embeddings are
   cached on disk keyed by prompt and model, so a rerun never loads the encoder.
2. The transformer is loaded tensor by tensor straight onto the GPU (never a CPU copy of the model;
   `from_single_file(device_map=...)` fails for this class). No CPU offload anywhere.
3. `batched` (default): the transformer and the VAE stay resident while every clip is denoised to a
   latent (the VAE is needed to encode the start/end frames), latents are kept in RAM (1.3 MB each),
   then the transformer is freed and every latent is decoded with only the VAE resident. The transformer
   loads once per batch instead of once per clip. `per_clip` loads, denoises, frees and decodes strictly
   one clip at a time and is kept as the slower fallback and the measurement baseline.

A watcher thread aborts the process, after writing a result file that says why, when system RAM
available falls under `min_free_ram_gb` (never rely on swap).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

JOB_VERSION = 1
MODES = ("batched", "per_clip")
#: Names the cached embeddings and the parent's cache key; bump when the encoder or its settings change.
MODEL_TAG = "ltx-2b-0.9.8-distilled|t5xxl-bf16-nf4|tok128"
PROMPT_TOKENS = 128
TRANSFORMER_REPO = "Lightricks/LTX-Video"
TRANSFORMER_FILE = "ltxv-2b-0.9.8-distilled.safetensors"
CONFIG_REPO = "Lightricks/LTX-Video-0.9.5"
T5_REPO = "city96/t5-v1_1-xxl-encoder-bf16"
#: The distilled model's own 8-entry schedule. 0-1 float timesteps produced pure noise (probe).
TIMESTEPS = [1000, 993, 987, 981, 975, 909, 725, 0.03]
DECODE_TIMESTEP = 0.05
DECODE_NOISE_SCALE = 0.025
RAM_ABORT_EXIT = 42


class JobError(ValueError):
    """The job file cannot be run as written."""


# --------------------------------------------------------------------------- job and result (no torch)


def embed_key(prompt: str) -> str:
    return hashlib.sha256(f"{MODEL_TAG}|{prompt}".encode()).hexdigest()[:32]


def validate_job(job: dict) -> dict:
    """Return the job unchanged if it can run, else raise `JobError` naming the first problem."""
    if not isinstance(job, dict):
        raise JobError("job must be a JSON object")
    if job.get("version") != JOB_VERSION:
        raise JobError(f"job version {job.get('version')!r}, this worker reads {JOB_VERSION}")
    if job.get("mode", "batched") not in MODES:
        raise JobError(f"mode {job.get('mode')!r} is not one of {MODES}")
    if not job.get("embed_cache_dir"):
        raise JobError("embed_cache_dir is required")
    clips = job.get("clips")
    if not isinstance(clips, list) or not clips:
        raise JobError("clips must be a non-empty list")
    ids: set[str] = set()
    outputs: set[str] = set()
    for i, c in enumerate(clips):
        where = f"clips[{i}]"
        for key in ("id", "start_image", "frames", "fps", "width", "height", "seed", "output"):
            if key not in c:
                raise JobError(f"{where}: missing {key!r}")
        if c["id"] in ids:
            raise JobError(f"{where}: duplicate id {c['id']!r}")
        if c["output"] in outputs:
            raise JobError(f"{where}: two clips write {c['output']!r}")
        ids.add(c["id"])
        outputs.add(c["output"])
        # LTX packs 8 frames per latent step plus the first: any other count is silently rounded down,
        # which would break the length the composer promised the audio.
        if not (isinstance(c["frames"], int) and c["frames"] >= 9 and (c["frames"] - 1) % 8 == 0):
            raise JobError(f"{where}: frames must be 8k+1 and at least 9, got {c['frames']!r}")
        for key in ("width", "height"):
            if not (isinstance(c[key], int) and c[key] >= 64 and c[key] % 32 == 0):
                raise JobError(f"{where}: {key} must be a multiple of 32 and at least 64, got {c[key]!r}")
        if not (isinstance(c["fps"], int) and c["fps"] > 0):
            raise JobError(f"{where}: fps must be a positive integer")
        if not isinstance(c.get("prompt", ""), str):
            raise JobError(f"{where}: prompt must be a string")
        for key in ("start_image", "end_image"):
            if c.get(key) and not Path(c[key]).is_file():
                raise JobError(f"{where}: {key} {c[key]!r} does not exist")
    return job


def load_job(path: str | Path) -> dict:
    try:
        return validate_job(json.loads(Path(path).read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise JobError(f"{path}: not valid JSON: {exc}") from exc


def write_result(path: str | Path, result: dict) -> None:
    """Atomic, so a reader never sees half a file (the RAM watcher writes from another thread)."""
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def new_result(job: dict) -> dict:
    return {
        "version": JOB_VERSION, "ok": False, "error": None, "mode": job.get("mode", "batched"),
        "min_avail_ram_gb": None, "stages": [],
        "clips": [{"id": c["id"], "ok": False, "error": "not run", "output": c["output"],
                   "frames_written": 0, "seconds": {}, "peak_vram_gb": None} for c in job["clips"]],
    }


def available_ram_gb() -> float | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 2**20
    except (OSError, ValueError, IndexError):
        pass
    return None


def emit(event: str, **kw: object) -> None:
    """One line the parent streams to its log and uses as a heartbeat for the per-clip timeout."""
    print("PROGRESS " + json.dumps({"event": event, **kw}), flush=True)


class RamWatch:
    """Aborts the whole process when available RAM falls under the floor, after saying why."""

    def __init__(self, floor_gb: float, result: dict, result_path: str | Path) -> None:
        self.floor, self.result, self.result_path = floor_gb, result, result_path
        self.min_avail = float("inf")
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> float | None:
        self._stop.set()
        return None if self.min_avail == float("inf") else round(self.min_avail, 2)

    def _run(self) -> None:
        while not self._stop.wait(0.2):
            avail = available_ram_gb()
            if avail is None:
                continue
            self.min_avail = min(self.min_avail, avail)
            if avail < self.floor:
                self.result["ok"] = False
                self.result["error"] = (
                    f"aborted: available RAM {avail:.2f} GB fell under the {self.floor:.1f} GB floor"
                )
                self.result["min_avail_ram_gb"] = round(self.min_avail, 2)
                write_result(self.result_path, self.result)
                print("!! " + self.result["error"], flush=True)
                os._exit(RAM_ABORT_EXIT)


# --------------------------------------------------------------------------- model (heavy imports inside)


def _free() -> None:
    import gc

    import torch

    gc.collect()
    torch.cuda.empty_cache()


def _vram_gb() -> float:
    import torch

    return round(torch.cuda.max_memory_allocated() / 1e9, 2)


def encode_prompts(prompts: list[str], cache_dir: Path) -> dict[str, float]:
    """Embed every prompt not already cached, then free the encoder. Returns seconds by step."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    missing = [p for p in dict.fromkeys(prompts) if not (cache_dir / f"{embed_key(p)}.pt").exists()]
    if not missing:
        return {"encode": 0.0, "encoder_load": 0.0}
    import torch
    from huggingface_hub import snapshot_download
    from transformers import BitsAndBytesConfig, T5EncoderModel, T5TokenizerFast

    t0 = time.time()
    d = snapshot_download(T5_REPO)
    tok = T5TokenizerFast.from_pretrained(d)
    enc = T5EncoderModel.from_pretrained(
        d,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_type="nf4"
        ),
        device_map={"": 0}, torch_dtype=torch.bfloat16,
    )
    loaded = time.time()
    for p in missing:
        t = tok([p], padding="max_length", max_length=PROMPT_TOKENS, truncation=True, return_tensors="pt").to("cuda")
        with torch.no_grad():
            e = enc(t.input_ids, attention_mask=t.attention_mask)[0]
        torch.save({"embeds": e.to(torch.bfloat16).cpu(), "mask": t.attention_mask.cpu()},
                   cache_dir / f"{embed_key(p)}.pt")
    del enc
    _free()
    return {"encoder_load": round(loaded - t0, 1), "encode": round(time.time() - loaded, 1)}


class Stack:
    """The transformer, VAE and scheduler, loaded and freed independently."""

    def __init__(self) -> None:
        from huggingface_hub import hf_hub_download, snapshot_download

        self.ckpt = hf_hub_download(TRANSFORMER_REPO, TRANSFORMER_FILE)
        self.cfg = snapshot_download(
            CONFIG_REPO, allow_patterns=["transformer/config.json", "vae/*", "scheduler/*", "model_index.json"]
        )
        self.transformer = None
        self.vae = None
        self.pipe = None

    def load_transformer(self) -> None:
        import torch
        from diffusers import LTXVideoTransformer3DModel
        from diffusers.loaders.single_file_utils import (
            convert_ltx_transformer_checkpoint_to_diffusers,
        )
        from safetensors import safe_open

        # Tensors go straight to the GPU, never a CPU copy of the whole model (the owner's RAM rule).
        with safe_open(self.ckpt, "pt", device="cuda") as f:
            sd = {k: f.get_tensor(k).to(torch.bfloat16) for k in f.keys()}  # noqa: SIM118 - safe_open has no iter
        sd = convert_ltx_transformer_checkpoint_to_diffusers(sd)
        cfg = LTXVideoTransformer3DModel.load_config(self.cfg, subfolder="transformer")
        with torch.device("meta"):
            tr = LTXVideoTransformer3DModel.from_config(cfg)
        tr.load_state_dict(sd, strict=False, assign=True)
        del sd
        self.transformer = tr.to("cuda", torch.bfloat16)

    def load_vae(self) -> None:
        import torch
        from diffusers import AutoencoderKLLTXVideo

        vae = AutoencoderKLLTXVideo.from_pretrained(self.cfg, subfolder="vae", torch_dtype=torch.bfloat16)
        vae = vae.to("cuda")
        vae.enable_tiling()
        self.vae = vae

    def build_pipe(self) -> None:
        from diffusers import FlowMatchEulerDiscreteScheduler, LTXConditionPipeline

        sch = FlowMatchEulerDiscreteScheduler.from_pretrained(self.cfg, subfolder="scheduler")
        self.pipe = LTXConditionPipeline(
            scheduler=sch, vae=self.vae, text_encoder=None, tokenizer=None, transformer=self.transformer
        )

    def free_transformer(self) -> None:
        if self.pipe is not None:
            self.pipe.transformer = None
        self.transformer = None
        _free()

    def free_all(self) -> None:
        self.pipe = None
        self.transformer = None
        self.vae = None
        _free()


def denoise(stack: Stack, clip: dict, cache_dir: Path):
    """One clip to a latent on the CPU (1.3 MB at 512x768x97)."""
    import torch
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
    from PIL import Image

    w, h, n = clip["width"], clip["height"], clip["frames"]
    start = Image.open(clip["start_image"]).convert("RGB").resize((w, h), Image.LANCZOS)
    conds = [LTXVideoCondition(image=start, frame_index=0)]
    if clip.get("end_image"):
        end = Image.open(clip["end_image"]).convert("RGB").resize((w, h), Image.LANCZOS)
        conds.append(LTXVideoCondition(image=end, frame_index=n - 1))
    cached = torch.load(cache_dir / f"{embed_key(clip.get('prompt', ''))}.pt")
    out = stack.pipe(
        conditions=conds, prompt_embeds=cached["embeds"].to("cuda"),
        prompt_attention_mask=cached["mask"].to("cuda"), height=h, width=w, num_frames=n,
        frame_rate=clip["fps"], timesteps=TIMESTEPS, num_inference_steps=len(TIMESTEPS),
        guidance_scale=1.0, decode_timestep=DECODE_TIMESTEP, decode_noise_scale=DECODE_NOISE_SCALE,
        image_cond_noise_scale=0.0, generator=torch.Generator("cuda").manual_seed(clip["seed"]),
        output_type="latent",
    )
    return out.frames.detach().to("cpu")


def decode_to_mp4(stack: Stack, latent, clip: dict) -> int:
    """Decode one latent with the transformer already freed, write the MP4, return frames written."""
    import imageio
    import numpy as np
    import torch
    from diffusers.utils.torch_utils import randn_tensor

    pipe, vae = stack.pipe, stack.vae
    lat = pipe._denormalize_latents(
        latent.to("cuda"), vae.latents_mean, vae.latents_std, vae.config.scaling_factor
    ).to(torch.bfloat16)
    noise = randn_tensor(
        lat.shape, generator=torch.Generator("cuda").manual_seed(clip["seed"]), device=lat.device, dtype=lat.dtype
    )
    lat = (1 - DECODE_NOISE_SCALE) * lat + DECODE_NOISE_SCALE * noise
    with torch.no_grad():
        video = vae.decode(lat, torch.tensor([DECODE_TIMESTEP], device="cuda", dtype=lat.dtype), return_dict=False)[0]
    frames = pipe.video_processor.postprocess_video(video, output_type="pil")[0]
    out = Path(clip["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimwrite(str(out), [np.asarray(f.convert("RGB")) for f in frames], fps=clip["fps"],
                     codec="libx264", quality=8, macro_block_size=1)
    return len(frames)


# --------------------------------------------------------------------------- orchestration


def _record(result: dict, idx: int, **fields: object) -> None:
    result["clips"][idx].update(fields)


def run_job(job: dict, result: dict, result_path: str | Path) -> None:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("no CUDA device")
    cache_dir = Path(job["embed_cache_dir"])
    clips = job["clips"]
    stages: list[dict] = result["stages"]

    t = time.time()
    enc = encode_prompts([c.get("prompt", "") for c in clips], cache_dir)
    stages.append({"name": "encode_prompts", "seconds": round(time.time() - t, 1), **enc})
    emit("encoded", **enc)

    stack = Stack()
    mode = job.get("mode", "batched")

    def one_clip_denoise(i: int) -> object | None:
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        try:
            lat = denoise(stack, clips[i], cache_dir)
        except Exception as exc:
            _record(result, i, ok=False, error=f"denoise: {type(exc).__name__}: {exc}"[:400])
            emit("clip_failed", id=clips[i]["id"], stage="denoise")
            _free()
            return None
        _record(result, i, seconds={**result["clips"][i]["seconds"], "denoise": round(time.time() - t0, 1)},
                peak_vram_gb=_vram_gb())
        emit("denoised", id=clips[i]["id"], seconds=round(time.time() - t0, 1))
        return lat

    def one_clip_decode(i: int, lat: object) -> None:
        t0 = time.time()
        try:
            n = decode_to_mp4(stack, lat, clips[i])
        except Exception as exc:
            _record(result, i, ok=False, error=f"decode: {type(exc).__name__}: {exc}"[:400])
            emit("clip_failed", id=clips[i]["id"], stage="decode")
            _free()
            return
        prev = result["clips"][i]
        peak = max(prev.get("peak_vram_gb") or 0.0, _vram_gb())
        _record(result, i, ok=True, error=None, frames_written=n, peak_vram_gb=peak,
                seconds={**prev["seconds"], "decode": round(time.time() - t0, 1)})
        emit("clip_done", id=clips[i]["id"], frames=n)

    if mode == "batched":
        t0 = time.time()
        stack.load_transformer()
        stack.load_vae()
        stack.build_pipe()
        stages.append({"name": "load_transformer_and_vae", "seconds": round(time.time() - t0, 1)})
        emit("loaded", seconds=round(time.time() - t0, 1))
        latents = [one_clip_denoise(i) for i in range(len(clips))]
        stack.free_transformer()
        t0 = time.time()
        for i, lat in enumerate(latents):
            if lat is not None:
                torch.cuda.reset_peak_memory_stats()
                one_clip_decode(i, lat)
        stages.append({"name": "decode_all", "seconds": round(time.time() - t0, 1)})
        stack.free_all()
    else:
        for i in range(len(clips)):
            t0 = time.time()
            stack.load_transformer()
            stack.load_vae()
            stack.build_pipe()
            _record(result, i, seconds={"load": round(time.time() - t0, 1)})
            lat = one_clip_denoise(i)
            stack.free_transformer()
            if lat is not None:
                torch.cuda.reset_peak_memory_stats()
                one_clip_decode(i, lat)
            stack.free_all()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--job", required=True)
    ap.add_argument("--result", help="where to write the result JSON (required unless --validate-only)")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args(argv)
    if not args.validate_only and not args.result:
        ap.error("--result is required unless --validate-only")
    try:
        job = load_job(args.job)
    except (JobError, OSError) as exc:
        print(f"invalid job: {exc}", file=sys.stderr)
        if args.result:
            write_result(args.result, {"version": JOB_VERSION, "ok": False, "error": f"invalid job: {exc}",
                                       "clips": [], "stages": []})
        return 2
    if args.validate_only:
        print(f"job ok: {len(job['clips'])} clips, mode {job.get('mode', 'batched')}")
        return 0

    result = new_result(job)
    watch = RamWatch(float(job.get("min_free_ram_gb", 2.0)), result, args.result)
    watch.start()
    code = 0
    try:
        run_job(job, result, args.result)
        result["ok"] = all(c["ok"] for c in result["clips"])
        if not result["ok"]:
            result["error"] = "some clips failed; see clips[].error"
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"[:600]
        code = 1
    result["min_avail_ram_gb"] = watch.stop()
    write_result(args.result, result)
    return code


if __name__ == "__main__":
    sys.exit(main())
