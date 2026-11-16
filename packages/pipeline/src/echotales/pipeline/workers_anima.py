"""Local Anima worker: the same two-stage residency as `workers_local`, for circlestone-labs/Anima.

Anima (https://huggingface.co/circlestone-labs/Anima) is a 2B text-to-image model from CircleStone Labs and Comfy Org: a
Cosmos-Predict2 DiT, a Qwen3-0.6B text encoder feeding a T5-token "LLM adapter" (`AnimaTextConditioner`), and the Qwen-Image
VAE. The official diffusers repo `circlestone-labs/Anima-Base-v1.0-Diffusers` is 5.65 GB in all (transformer 3.91, text
encoder 1.19, conditioner 0.27, VAE 0.25 GB); `diffusers` 0.39 in the main environment ships `AnimaModularPipeline`, so no
second environment is needed. Licence: CircleStone Labs Non-Commercial (generated images may be used commercially).

Residency, to stay under 6 GB without CPU offload: stage 1 loads only the Qwen text encoder and tokenizers (1.2 GB), encodes
every prompt (Qwen's window is 512 tokens, so a compiled prompt is never chunked or cut) and frees it; stage 2 loads the
conditioner, transformer and VAE (4.4 GB in bf16) and denoises from the cached embeddings.

STATUS: written against the diffusers 0.39 source and NOT yet run: the weights are not downloaded (the stage-A rules allowed
no download over 1 GB while the GPU was reserved). The first GPU run must confirm that the denoise blocks accept the cached
embeddings as inputs and measure peak VRAM; until then the `anima` profile is untested, not unavailable.
"""

from __future__ import annotations

import base64
import gc
import io
import logging
import time

from echotales.pipeline.render.compiler import model_profile
from echotales.pipeline.workers_contract import ImageWorkerRequest, ImageWorkerResponse

logger = logging.getLogger(__name__)

#: Free VRAM needed before loading: 4.4 GB resident weights plus activations at 832x1216, with the owner's headroom.
MIN_FREE_GIB = 6.5
MAX_SEQ = 512


class LocalAnimaWorker:
    def __init__(self, repo: str | None = None) -> None:
        self.repo = repo or model_profile("anima").model_id
        self._pipe: object | None = None
        self.stats: list[dict[str, object]] = []

    def _check_gpu(self) -> None:
        import torch  # type: ignore[import-not-found]

        if not torch.cuda.is_available():
            raise RuntimeError("the Anima worker needs a CUDA GPU")
        free_gib = torch.cuda.mem_get_info()[0] / 2**30
        if free_gib < MIN_FREE_GIB:
            raise RuntimeError(f"only {free_gib:.1f} GiB of GPU memory is free (need {MIN_FREE_GIB}); another job has the card")

    def _encode(self, requests: list[ImageWorkerRequest]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        import torch  # type: ignore[import-not-found]
        from diffusers import ModularPipeline  # type: ignore[import-not-found]
        from diffusers.modular_pipelines.anima.encoders import (
            AnimaTextEncoderStep,  # type: ignore[import-not-found]
        )

        pipe = ModularPipeline.from_pretrained(self.repo)
        pipe.load_components(names=["text_encoder", "tokenizer", "t5_tokenizer"], torch_dtype=torch.bfloat16)
        pipe.text_encoder.to("cuda")
        out, plans = [], []
        for r in requests:
            out.append(AnimaTextEncoderStep.encode_prompt(
                pipe, r.prompt, r.negative_prompt, prepare_unconditional_embeds=True, max_sequence_length=MAX_SEQ,
                device=torch.device("cuda"), dtype=torch.bfloat16,
            ))
            tokens = len(pipe.tokenizer(r.prompt).input_ids)
            plans.append({"tokens": tokens, "chunks": 1, "sections": {}})
            logger.info("anima prompt tokens=%s (window %s, never chunked)", tokens, MAX_SEQ)
        del pipe
        gc.collect()
        torch.cuda.empty_cache()
        return out, plans

    def _ensure_pipe(self) -> object:
        if self._pipe is None:
            import torch  # type: ignore[import-not-found]
            from diffusers import ModularPipeline  # type: ignore[import-not-found]

            pipe = ModularPipeline.from_pretrained(self.repo)
            pipe.load_components(names=["text_conditioner", "transformer", "vae", "scheduler"], torch_dtype=torch.bfloat16)
            for name in ("text_conditioner", "transformer", "vae"):
                getattr(pipe, name).to("cuda")
            self._pipe = pipe
        return self._pipe

    def generate_many(
        self, requests: list[ImageWorkerRequest], sections: list[list[tuple[str, str]]] | None = None, *,
        greyscale: bool = False,
    ) -> list[ImageWorkerResponse]:
        import torch  # type: ignore[import-not-found]

        self._check_gpu()
        profile = model_profile("anima")
        torch.cuda.reset_peak_memory_stats()
        embeds, plans = self._encode(requests)
        encode_peak = torch.cuda.max_memory_allocated() / 2**30
        pipe = self._ensure_pipe()
        responses = []
        for r, plan, e in zip(requests, plans, embeds, strict=True):
            torch.cuda.reset_peak_memory_stats()
            started = time.time()
            image = pipe(  # type: ignore[operator]
                **e, width=r.width, height=r.height,
                num_inference_steps=r.steps if r.steps != 25 else profile.steps,
                generator=torch.Generator("cpu").manual_seed(r.seed),
            ).images[0]
            if greyscale:
                from echotales.pipeline.render.palette import Palette, PaletteSpec, apply_palette

                image = apply_palette(image, PaletteSpec(palette=Palette.INK))
            duration = time.time() - started
            self.stats.append({
                **plan, "seed": r.seed, "seconds": round(duration, 2),
                "denoise_peak_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
                "encode_peak_gib": round(encode_peak, 3), "width": r.width, "height": r.height,
            })
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            responses.append(ImageWorkerResponse(
                image_b64=base64.b64encode(buf.getvalue()).decode("ascii"), seed=r.seed, duration_s=duration,
            ))
        return responses

    def close(self) -> None:
        self._pipe = None
        gc.collect()
        try:
            import torch  # type: ignore[import-not-found]

            torch.cuda.empty_cache()
        except Exception:
            pass
