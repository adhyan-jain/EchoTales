"""Standalone subprocess for the art bake-off v3: SDXL-family checkpoints (NoobAI, Illustrious) with optional character LoRA,
img2img init and ControlNet, over a batch of jobs. Nothing else is resident: the owner's GPU rule is one model per process.

Same two-stage shape as `workers_local.LocalNoobAIWorker` and `_noobai_i2i_worker.py`: a text-encoder-only pipeline encodes every
prompt with compel (whole prompt chunked, nothing cut at 77 tokens) and is freed, then only UNet and VAE stay resident, tiled
VAE decode, nothing offloaded. A LoRA is loaded per job and unloaded after it; it trains only the UNet (`train_character_lora.py`),
so the precomputed prompt embeddings stay valid.

Usage: `_sdxl_art_worker.py <jobs.json>`; jobs.json = {"checkpoint": HF id, "stats": path, "allow_big_control": false,
"jobs": [{out, prompt, negative, seed, width, height, steps?, guidance?, init?, strength?, lora?: {path, scale, trigger?},
control?: {kind, image, scale?, start?, end?, preprocess?}}]}."""

from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: _sdxl_art_worker.py <jobs.json>", file=sys.stderr)
        return 2
    spec = json.loads(Path(argv[1]).read_text())
    jobs = spec["jobs"]
    allow_big = bool(spec.get("allow_big_control", False))

    from echotales.pipeline.render.sdxl_control import (
        CONTROLNETS,
        ControlSpec,
        control_map,
        validate,
    )

    controls = [ControlSpec.from_dict(j["control"]) if j.get("control") else None for j in jobs]
    for c in controls:
        if c is not None:
            validate(c, allow_big=allow_big)  # refuse before a 6 GiB model is loaded, not after
            if CONTROLNETS[c.kind][3] is not None:
                raise NotImplementedError(f"{c.kind}: the union ControlNet needs StableDiffusionXLControlNetUnionPipeline, not wired "
                                          f"(it is 2.5 GiB and does not fit 8 GB); use a depth or canny map, or a pre-drawn pose on a larger card")

    import torch
    from compel import CompelForSDXL
    from diffusers import (
        ControlNetModel,
        StableDiffusionXLControlNetImg2ImgPipeline,
        StableDiffusionXLControlNetPipeline,
        StableDiffusionXLImg2ImgPipeline,
        StableDiffusionXLPipeline,
    )
    from echotales.pipeline.workers_local import (
        MIN_FREE_GIB,
        _compel_safe,
        _snapshot,
        fit_size,
        plan_chunks,
    )
    from huggingface_hub import hf_hub_download
    from PIL import Image

    free = torch.cuda.mem_get_info()[0] / 2**30
    if free < MIN_FREE_GIB:
        raise RuntimeError(f"only {free:.1f} GiB of GPU memory is free (need {MIN_FREE_GIB}); another GPU job is running")
    torch.cuda.reset_peak_memory_stats()
    snap = _snapshot(spec["checkpoint"])
    t0 = time.time()
    enc = StableDiffusionXLPipeline.from_pretrained(snap, unet=None, vae=None, torch_dtype=torch.float16, use_safetensors=True,
                                                    device_map="cuda")
    compel = CompelForSDXL(enc)
    embeds, plans = [], []
    for j in jobs:
        cond = compel(main_prompt=_compel_safe(j["prompt"]), negative_prompt=_compel_safe(j.get("negative", "")))
        embeds.append(tuple(e.detach() for e in (cond.embeds, cond.negative_embeds, cond.pooled_embeds, cond.negative_pooled_embeds)))
        plans.append(plan_chunks(enc.tokenizer, [("prompt", j["prompt"])]))
    encode_peak = torch.cuda.max_memory_allocated() / 2**30
    del enc, compel
    gc.collect()
    torch.cuda.empty_cache()
    base = StableDiffusionXLPipeline.from_pretrained(
        snap, text_encoder=None, text_encoder_2=None, tokenizer=None, tokenizer_2=None, torch_dtype=torch.float16,
        use_safetensors=True, device_map="cuda")
    base.vae.enable_tiling()
    base.vae.tile_sample_min_size = 256
    base.vae.tile_latent_min_size = 32
    i2i = StableDiffusionXLImg2ImgPipeline(**base.components)
    cn_models: dict[str, object] = {}
    load_s = time.time() - t0
    stats = []
    for j, ctl, (pe, npe, pp, npp), plan in zip(jobs, controls, embeds, plans, strict=True):
        w, h = fit_size(j.get("width", 832), j.get("height", 1216))
        kw = dict(prompt_embeds=pe, negative_prompt_embeds=npe, pooled_prompt_embeds=pp, negative_pooled_prompt_embeds=npp,
                  num_inference_steps=j.get("steps", 28), guidance_scale=j.get("guidance", 5.5),
                  generator=torch.Generator("cpu").manual_seed(j["seed"]))
        init = Image.open(j["init"]).convert("RGB").resize((w, h), Image.Resampling.LANCZOS) if j.get("init") else None
        if ctl is not None:
            repo, fname, _, _mode = CONTROLNETS[ctl.kind]
            if repo not in cn_models:
                cn_models[repo] = ControlNetModel.from_pretrained(
                    str(Path(hf_hub_download(repo, fname)).parent), variant="fp16", torch_dtype=torch.float16, use_safetensors=True).to("cuda")
            cn = cn_models[repo]
            kw.update(controlnet_conditioning_scale=ctl.scale, control_guidance_start=ctl.start, control_guidance_end=ctl.end)
            if init is not None:
                pipe, kw = StableDiffusionXLControlNetImg2ImgPipeline(**base.components, controlnet=cn), {
                    **kw, "image": init, "control_image": control_map(ctl, (w, h)), "strength": j.get("strength", 0.45)}
            else:
                pipe, kw = StableDiffusionXLControlNetPipeline(**base.components, controlnet=cn), {
                    **kw, "image": control_map(ctl, (w, h)), "width": w, "height": h}
        elif init is not None:
            pipe, kw = i2i, {**kw, "image": init, "strength": j.get("strength", 0.45)}
        else:
            pipe, kw = base, {**kw, "width": w, "height": h}
        lora = j.get("lora")
        if lora:
            base.load_lora_weights(str(Path(lora["path"]).parent), weight_name=Path(lora["path"]).name, adapter_name="char")
            base.set_adapters(["char"], adapter_weights=[float(lora.get("scale", 0.8))])
        torch.cuda.reset_peak_memory_stats()
        s0 = time.time()
        img = pipe(**kw).images[0]
        if lora:
            base.unload_lora_weights()
        Path(j["out"]).parent.mkdir(parents=True, exist_ok=True)
        img.save(j["out"])
        stats.append({"out": j["out"], "seconds": round(time.time() - s0, 2), "denoise_peak_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
                      "tokens": plan["tokens"], "chunks": plan["chunks"], "lora": bool(lora), "control": ctl.kind if ctl else None})
    Path(spec["stats"]).write_text(json.dumps({"load_s": round(load_s, 1), "encode_peak_gib": round(encode_peak, 3), "images": stats}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
