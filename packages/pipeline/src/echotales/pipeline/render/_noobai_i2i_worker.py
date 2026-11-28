"""Standalone subprocess: NoobAI XL img2img over a list of Z-Image panels (art-drama arm D, comparison only).

Why a subprocess, one model: the card is 8 GB and Z-Image and NoobAI must never be resident together (owner GPU rules). The
pattern is `persona/_img2img_worker.py` (a fresh CUDA context, one engine, exit) but for a batch, because loading NoobAI costs
more than the 10-15 denoise steps an img2img pass runs. Same two-stage shape as `workers_local.LocalNoobAIWorker`: a text-encoder-only
pipeline encodes every tag prompt with compel (whole prompt, chunked, nothing cut at 77 tokens) and is freed, then only the UNet and
VAE stay resident for `StableDiffusionXLImg2ImgPipeline` (tiled VAE, nothing offloaded to the CPU).

Usage: `_noobai_i2i_worker.py <jobs.json>`; jobs.json = {"jobs": [{init, out, prompt, negative, strength, seed}], "stats": path}.
Writes each `out` PNG and a stats list (seconds, peak VRAM GiB, tokens, chunks) to `stats`."""

from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: _noobai_i2i_worker.py <jobs.json>", file=sys.stderr)
        return 2
    spec = json.loads(Path(argv[1]).read_text())
    jobs = spec["jobs"]

    import torch
    from compel import CompelForSDXL
    from diffusers import StableDiffusionXLImg2ImgPipeline, StableDiffusionXLPipeline
    from echotales.pipeline.workers_local import (
        MIN_FREE_GIB,
        MODEL_ID,
        _compel_safe,
        _snapshot,
        fit_size,
        plan_chunks,
    )
    from PIL import Image

    free = torch.cuda.mem_get_info()[0] / 2**30
    if free < MIN_FREE_GIB:
        raise RuntimeError(f"only {free:.1f} GiB of GPU memory is free (need {MIN_FREE_GIB}); another GPU job is running")
    torch.cuda.reset_peak_memory_stats()
    snap = _snapshot(MODEL_ID)
    t0 = time.time()
    enc = StableDiffusionXLPipeline.from_pretrained(snap, unet=None, vae=None, torch_dtype=torch.float16, use_safetensors=True,
                                                    device_map="cuda")
    compel = CompelForSDXL(enc)
    embeds, plans = [], []
    for j in jobs:
        cond = compel(main_prompt=_compel_safe(j["prompt"]), negative_prompt=_compel_safe(j["negative"]))
        embeds.append(tuple(e.detach() for e in (cond.embeds, cond.negative_embeds, cond.pooled_embeds, cond.negative_pooled_embeds)))
        plans.append(plan_chunks(enc.tokenizer, [("prompt", j["prompt"])]))
    encode_peak = torch.cuda.max_memory_allocated() / 2**30
    del enc, compel
    gc.collect()
    torch.cuda.empty_cache()
    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        snap, text_encoder=None, text_encoder_2=None, tokenizer=None, tokenizer_2=None, torch_dtype=torch.float16,
        use_safetensors=True, device_map="cuda")
    pipe.vae.enable_tiling()
    pipe.vae.tile_sample_min_size = 256
    pipe.vae.tile_latent_min_size = 32
    load_s = time.time() - t0
    stats = []
    for j, (pe, npe, pp, npp), plan in zip(jobs, embeds, plans, strict=True):
        init = Image.open(j["init"]).convert("RGB")
        w, h = fit_size(*init.size)
        init = init.resize((w, h), Image.Resampling.LANCZOS)
        torch.cuda.reset_peak_memory_stats()
        s0 = time.time()
        img = pipe(prompt_embeds=pe, negative_prompt_embeds=npe, pooled_prompt_embeds=pp, negative_pooled_prompt_embeds=npp,
                   image=init, strength=j["strength"], num_inference_steps=28, guidance_scale=5.5,
                   generator=torch.Generator("cpu").manual_seed(j["seed"])).images[0]
        Path(j["out"]).parent.mkdir(parents=True, exist_ok=True)
        img.save(j["out"])
        stats.append({"out": j["out"], "strength": j["strength"], "seconds": round(time.time() - s0, 2),
                      "denoise_peak_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3), "tokens": plan["tokens"],
                      "chunks": plan["chunks"]})
    Path(spec["stats"]).write_text(json.dumps({"load_s": round(load_s, 1), "encode_peak_gib": round(encode_peak, 3), "images": stats}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
