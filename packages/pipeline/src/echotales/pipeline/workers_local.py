"""Local image worker: NoobAI XL on the GPU with no CPU offload (Phase C, decisions D25).

This is the default worker for a real run. `workers_contract._image_worker_choice` picks the stub only when
`ECHOTALES_IMAGE_WORKER=stub` or the language-model mode is stub (so CI and tests never touch a GPU), and rejects any
other value. This line used to say the stub was the default, which stopped being true with decisions D31(c): a flat
colour image must never come out of a real run.

Why it is built this way (measured on the RTX 4060 Laptop, 8 GB, 2026-10-22):
- A fully resident SDXL pipeline runs out of memory in the VAE decode. SDXL's VAE is upcast to float32 to decode, which
  doubles its activations, and the old engines worked around that with `enable_model_cpu_offload`, which parks weights in
  system RAM: the exact RAM spike the owner ruled out (2026-10-02).
- So generation is two stages. Stage 1 loads a *text-encoder-only* pipeline (`unet=None, vae=None`) straight onto the GPU
  (`device_map="cuda"`, no CPU copy), encodes every prompt in the batch, and frees it. Stage 2 keeps only the UNet and VAE
  resident (4.95 GiB) and denoises from the cached embeddings. VAE decode tiles are 256 px so the float32 upcast fits.
  Result: peak 5.36 GiB of VRAM, about 22 s per 28-step image at 832x1216 or 1024x1024, nothing offloaded.
- Weights come from the local Hugging Face cache; nothing is downloaded here.

Long prompts (stage A, 2026-11-15): the 77-token fit above silently dropped whole clauses (a recorded panel lost its layout,
setting, lighting and location, 102 tokens cut to 73), so the encode step now chunks the whole prompt through `compel`
(`CompelForSDXL`, both text encoders, 75-token chunks concatenated on the sequence axis, negative padded to the same length,
pooled embedding from the first chunk) and logs per prompt the token count, the chunks, and which labelled compiler section
falls in which chunk (`plan_chunks`). `fit_prompt` stays for callers that want a hard cap.

NoobAI XL 1.1 carries a non-commercial licence (decisions D7): this worker is for development and review. The licence-clean
replacement is a different `model_id` behind the same worker contract.
"""

from __future__ import annotations

import base64
import gc
import io
import logging
import time
from pathlib import Path

from echotales.pipeline.workers_contract import ImageWorkerRequest, ImageWorkerResponse

logger = logging.getLogger(__name__)

MODEL_ID = "Laxhar/noobai-XL-1.1"
#: NoobAI is trained on score tags; "masterpiece, best quality" is the wrong family of quality words for it
#: (memory: echotales-image-model-stack).
QUALITY_PREFIX = "score_9, score_8_up, score_7_up, very aesthetic, absurdres"
DEFAULT_NEGATIVE = (
    "worst quality, low quality, bad anatomy, bad hands, extra fingers, text, handwriting, annotations, japanese text, "
    "speech bubble, watermark, signature, blurry"
)
STEPS = 28
GUIDANCE = 5.5
#: Pixel budget per image on the 8 GB card: 832x1216 and 1024x1024 are both under it and measured fine.
MAX_PIXELS = 1_100_000
#: Free VRAM needed before loading. UNet+VAE take 4.95 GiB and a 1 MP denoise peaks at 5.36 GiB; below this the card is
#: shared with another job (ollama, a render) and a load would fail halfway.
MIN_FREE_GIB = 6.5


def fit_size(width: int, height: int, max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    """Scale a request down to the pixel budget, keeping the aspect ratio, in multiples of 64 (SDXL's grid)."""
    scale = min(1.0, (max_pixels / (width * height)) ** 0.5)
    return max(256, int(width * scale) // 64 * 64), max(256, int(height * scale) // 64 * 64)


#: CLIP reads 77 tokens including the start and end markers; everything past it is ignored without a word.
CLIP_TOKENS = 75


def fit_prompt(tokenizer: object, prefix: str, prompt: str, limit: int = CLIP_TOKENS) -> str:
    """`prefix, prompt` that fits the model's token window, dropping whole trailing clauses from the prompt.

    The quality prefix is spent first and the caller orders its clauses by importance, so what is lost is the least
    important clause, not the middle of one. Without this the tail was cut silently: a Victorian sheet lost its
    full-body framing, and a longer one would have lost the era."""
    count = lambda text: len(tokenizer(text, add_special_tokens=False).input_ids)  # type: ignore[operator]  # noqa: E731
    clauses = [c.strip() for c in prompt.split(",") if c.strip()]
    head = f"{prefix}, " if prefix else ""
    while clauses and count(head + ", ".join(clauses)) > limit:
        clauses.pop()
    return head + ", ".join(clauses)


def plan_chunks(
    tokenizer: object, sections: list[tuple[str, str]], size: int = CLIP_TOKENS, sep: str = ", "
) -> dict[str, object]:
    """Token count, chunk count and the chunks each labelled section falls in, for a prompt joined as `sep.join(texts)`.

    Tokens are counted on the cumulative text, so a section's span is where the running count says it is; a section that
    straddles a boundary reports both chunks. This is the arithmetic the log needs ("the setting is in chunk 2 of 3"),
    separate from the embedding so it runs with a tokenizer alone."""
    count = lambda text: len(tokenizer(text, add_special_tokens=False).input_ids)  # type: ignore[operator]  # noqa: E731
    spans: dict[str, list[int]] = {}
    done, text = 0, ""
    for label, part in sections:
        text = f"{text}{sep}{part}" if text else part
        end = count(text)
        spans[label] = list(range(done // size, max(done, end - 1) // size + 1)) if end > done else []
        done = end
    return {"tokens": done, "chunks": max(1, -(-done // size)), "sections": spans}


def _compel_safe(text: str) -> str:
    """Compel reads parentheses and `+`/`-` as weights; prompt text must reach the encoder unchanged."""
    return text.replace("(", "\\(").replace(")", "\\)")


def _snapshot(model_id: str) -> str:
    org, _, name = model_id.partition("/")
    root = Path.home() / ".cache/huggingface/hub" / f"models--{org}--{name}" / "snapshots"
    for snap in sorted(root.iterdir(), reverse=True) if root.is_dir() else []:
        if (snap / "model_index.json").exists():
            return str(snap)
    raise FileNotFoundError(f"{model_id} is not in the local Hugging Face cache ({root}); download it first")


class LocalNoobAIWorker:
    """Generates images for `ImageWorkerRequest`s on the local GPU. One instance keeps the UNet and VAE resident."""

    def __init__(self, model_id: str = MODEL_ID) -> None:
        self.model_id = model_id
        self._pipe: object | None = None
        #: One record per generated image: seconds, peak VRAM (GiB), tokens, chunks, section-to-chunk map.
        self.stats: list[dict[str, object]] = []

    def _check_gpu(self) -> None:
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("the local image worker needs a CUDA GPU (ECHOTALES_IMAGE_WORKER=noobai)")
        free_gib = torch.cuda.mem_get_info()[0] / 2**30
        if self._pipe is None and free_gib < MIN_FREE_GIB:
            raise RuntimeError(
                f"only {free_gib:.1f} GiB of GPU memory is free (need {MIN_FREE_GIB}); stop ollama or the other GPU job first"
            )

    def _encode(
        self, requests: list[ImageWorkerRequest], sections: list[list[tuple[str, str]]] | None = None
    ) -> tuple[list[tuple], list[dict[str, object]]]:  # type: ignore[type-arg]
        """Stage 1: whole-prompt chunked embeddings from a text-encoder-only pipeline freed before denoising starts.

        With `sections` the prompt is the compiler's finished text (its own quality tags), otherwise the legacy prompt gets
        `QUALITY_PREFIX`. Nothing is dropped either way; length costs chunks, not clauses."""
        import torch
        from compel import CompelForSDXL
        from diffusers import StableDiffusionXLPipeline

        enc = StableDiffusionXLPipeline.from_pretrained(
            _snapshot(self.model_id), unet=None, vae=None, torch_dtype=torch.float16, use_safetensors=True, device_map="cuda"
        )
        compel = CompelForSDXL(enc)
        out, plans = [], []
        for i, r in enumerate(requests):
            if sections is not None:
                pos, neg = r.prompt, r.negative_prompt
                labelled = sections[i]
            else:
                pos = f"{QUALITY_PREFIX}, {r.prompt}"
                neg = f"{r.negative_prompt}, {DEFAULT_NEGATIVE}".strip(", ")
                labelled = [("quality", QUALITY_PREFIX), ("prompt", r.prompt)]
            plan = plan_chunks(enc.tokenizer, labelled)
            plan["negative_tokens"] = plan_chunks(enc.tokenizer, [("negative", neg)])["tokens"]
            cond = compel(main_prompt=_compel_safe(pos), negative_prompt=_compel_safe(neg))
            out.append(tuple(e.detach() for e in (
                cond.embeds, cond.negative_embeds, cond.pooled_embeds, cond.negative_pooled_embeds)))
            plans.append(plan)
            logger.info("prompt tokens=%s chunks=%s sections=%s", plan["tokens"], plan["chunks"], plan["sections"])
        del enc, compel
        gc.collect()
        torch.cuda.empty_cache()
        return out, plans

    def _ensure_pipe(self) -> object:
        """Stage 2 pipeline: UNet and VAE only, tiled decode, resident until `close()`."""
        if self._pipe is None:
            import torch
            from diffusers import StableDiffusionXLPipeline

            pipe = StableDiffusionXLPipeline.from_pretrained(
                _snapshot(self.model_id), text_encoder=None, text_encoder_2=None, tokenizer=None, tokenizer_2=None,
                torch_dtype=torch.float16, use_safetensors=True, device_map="cuda",
            )
            pipe.vae.enable_tiling()
            pipe.vae.tile_sample_min_size = 256
            pipe.vae.tile_latent_min_size = 32
            self._pipe = pipe
        return self._pipe

    def generate_many(
        self,
        requests: list[ImageWorkerRequest],
        sections: list[list[tuple[str, str]]] | None = None,
        *,
        greyscale: bool = False,
    ) -> list[ImageWorkerResponse]:
        """Encode every prompt once, then denoise each; batching saves one text-encoder load per image.

        `greyscale` is manga mode's last step: the prompt asks for monochrome, but a checkpoint leaks colour (tinted paper,
        a coloured robe), so every image is converted through `palette.apply_palette(INK)` and none can come out coloured."""
        import torch

        self._check_gpu()
        torch.cuda.reset_peak_memory_stats()
        embeds, plans = self._encode(requests, sections)
        encode_peak = torch.cuda.max_memory_allocated() / 2**30
        pipe = self._ensure_pipe()
        responses = []
        for r, plan, (pe, npe, pp, npp) in zip(requests, plans, embeds, strict=True):
            width, height = fit_size(r.width, r.height)
            torch.cuda.reset_peak_memory_stats()
            started = time.time()
            image = pipe(  # type: ignore[operator]
                prompt_embeds=pe, negative_prompt_embeds=npe, pooled_prompt_embeds=pp, negative_pooled_prompt_embeds=npp,
                width=width, height=height, num_inference_steps=r.steps if r.steps != 25 else STEPS,
                guidance_scale=GUIDANCE if r.guidance_scale == 6.0 else r.guidance_scale,
                generator=torch.Generator("cpu").manual_seed(r.seed),
            ).images[0]
            if greyscale:
                from echotales.pipeline.render.palette import Palette, PaletteSpec, apply_palette

                image = apply_palette(image, PaletteSpec(palette=Palette.INK))
            duration = time.time() - started
            self.stats.append({
                **plan, "seed": r.seed, "seconds": round(duration, 2), "denoise_peak_gib": round(
                    torch.cuda.max_memory_allocated() / 2**30, 3),
                "encode_peak_gib": round(encode_peak, 3), "width": width, "height": height,
            })
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            responses.append(ImageWorkerResponse(
                image_b64=base64.b64encode(buf.getvalue()).decode("ascii"), seed=r.seed, duration_s=duration,
            ))
        return responses

    def close(self) -> None:
        """Free the GPU so another model (ollama, a different worker) can use the card."""
        self._pipe = None
        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass


_WORKER: LocalNoobAIWorker | None = None


def run_local_image_worker(req: ImageWorkerRequest) -> ImageWorkerResponse:
    """`run_image_worker`'s local backend: one request through the shared, resident worker."""
    global _WORKER
    if _WORKER is None:
        _WORKER = LocalNoobAIWorker()
    return _WORKER.generate_many([req])[0]


def close_local_worker() -> None:
    global _WORKER
    if _WORKER is not None:
        _WORKER.close()
        _WORKER = None
