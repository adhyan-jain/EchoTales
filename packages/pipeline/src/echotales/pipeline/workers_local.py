"""Local image worker: NoobAI XL on the GPU with no CPU offload (Phase C, decisions D25).

Enabled with `ECHOTALES_IMAGE_WORKER=noobai`; the stub stays the default so CI and tests never touch a GPU.

Why it is built this way (measured on the RTX 4060 Laptop, 8 GB, 2026-10-22):
- A fully resident SDXL pipeline runs out of memory in the VAE decode. SDXL's VAE is upcast to float32 to decode, which
  doubles its activations, and the old engines worked around that with `enable_model_cpu_offload`, which parks weights in
  system RAM: the exact RAM spike the owner ruled out (2026-10-02).
- So generation is two stages. Stage 1 loads a *text-encoder-only* pipeline (`unet=None, vae=None`) straight onto the GPU
  (`device_map="cuda"`, no CPU copy), encodes every prompt in the batch, and frees it. Stage 2 keeps only the UNet and VAE
  resident (4.95 GiB) and denoises from the cached embeddings. VAE decode tiles are 256 px so the float32 upcast fits.
  Result: peak 5.36 GiB of VRAM, about 22 s per 28-step image at 832x1216 or 1024x1024, nothing offloaded.
- Weights come from the local Hugging Face cache; nothing is downloaded here.

NoobAI XL 1.1 carries a non-commercial licence (decisions D7): this worker is for development and review. The licence-clean
replacement is a different `model_id` behind the same worker contract.
"""

from __future__ import annotations

import base64
import gc
import io
import time
from pathlib import Path

from echotales.pipeline.workers_contract import ImageWorkerRequest, ImageWorkerResponse

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

    def _check_gpu(self) -> None:
        import torch  # type: ignore[import-not-found]

        if not torch.cuda.is_available():
            raise RuntimeError("the local image worker needs a CUDA GPU (ECHOTALES_IMAGE_WORKER=noobai)")
        free_gib = torch.cuda.mem_get_info()[0] / 2**30
        if self._pipe is None and free_gib < MIN_FREE_GIB:
            raise RuntimeError(
                f"only {free_gib:.1f} GiB of GPU memory is free (need {MIN_FREE_GIB}); stop ollama or the other GPU job first"
            )

    def _encode(self, requests: list[ImageWorkerRequest]) -> list[tuple]:  # type: ignore[type-arg]
        """Stage 1: prompt embeddings from a text-encoder-only pipeline that is freed before denoising starts."""
        import torch  # type: ignore[import-not-found]
        from diffusers import StableDiffusionXLPipeline  # type: ignore[import-not-found]

        enc = StableDiffusionXLPipeline.from_pretrained(
            _snapshot(self.model_id), unet=None, vae=None, torch_dtype=torch.float16, use_safetensors=True, device_map="cuda"
        )
        out = []
        for r in requests:
            embeds = enc.encode_prompt(
                fit_prompt(enc.tokenizer, QUALITY_PREFIX, r.prompt),
                negative_prompt=fit_prompt(enc.tokenizer, "", f"{r.negative_prompt}, {DEFAULT_NEGATIVE}".strip(", ")),
                device="cuda",
            )
            out.append(tuple(e.detach() for e in embeds))
        del enc
        gc.collect()
        torch.cuda.empty_cache()
        return out

    def _ensure_pipe(self) -> object:
        """Stage 2 pipeline: UNet and VAE only, tiled decode, resident until `close()`."""
        if self._pipe is None:
            import torch  # type: ignore[import-not-found]
            from diffusers import StableDiffusionXLPipeline  # type: ignore[import-not-found]

            pipe = StableDiffusionXLPipeline.from_pretrained(
                _snapshot(self.model_id), text_encoder=None, text_encoder_2=None, tokenizer=None, tokenizer_2=None,
                torch_dtype=torch.float16, use_safetensors=True, device_map="cuda",
            )
            pipe.vae.enable_tiling()
            pipe.vae.tile_sample_min_size = 256
            pipe.vae.tile_latent_min_size = 32
            self._pipe = pipe
        return self._pipe

    def generate_many(self, requests: list[ImageWorkerRequest]) -> list[ImageWorkerResponse]:
        """Encode every prompt once, then denoise each; batching saves one text-encoder load per image."""
        import torch  # type: ignore[import-not-found]

        self._check_gpu()
        embeds = self._encode(requests)
        pipe = self._ensure_pipe()
        responses = []
        for r, (pe, npe, pp, npp) in zip(requests, embeds, strict=True):
            width, height = fit_size(r.width, r.height)
            started = time.time()
            image = pipe(  # type: ignore[operator]
                prompt_embeds=pe, negative_prompt_embeds=npe, pooled_prompt_embeds=pp, negative_pooled_prompt_embeds=npp,
                width=width, height=height, num_inference_steps=r.steps if r.steps != 25 else STEPS,
                guidance_scale=GUIDANCE if r.guidance_scale == 6.0 else r.guidance_scale,
                generator=torch.Generator("cpu").manual_seed(r.seed),
            ).images[0]
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            responses.append(ImageWorkerResponse(
                image_b64=base64.b64encode(buf.getvalue()).decode("ascii"), seed=r.seed, duration_s=time.time() - started,
            ))
        return responses

    def close(self) -> None:
        """Free the GPU so another model (ollama, a different worker) can use the card."""
        self._pipe = None
        gc.collect()
        try:
            import torch  # type: ignore[import-not-found]

            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - nothing to free without torch
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
