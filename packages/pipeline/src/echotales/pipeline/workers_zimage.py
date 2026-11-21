"""Local Z-Image Turbo worker: same contract and call shape as `workers_local.LocalNoobAIWorker`.

Why this model (measured 2026-11-16, RTX 4060 Laptop 8 GB, probe in `data/scratch/image_probe/REPORT.md`): on the RI chapter 1
cliff scene NoobAI drew the cliff or the crowd but rarely both with the hero in focus (a hero missing in one image, a
close-up split into a manga strip), while Z-Image Turbo put hero, cliff and a crowd of 12-20 in all 4 of 4 probe images from
one natural-language prompt. Cost: 32-34 s per 832x1216 image (NoobAI 22 s), peak 5.77 GiB (NoobAI 5.36).

Model: Tongyi-MAI/Z-Image-Turbo (https://huggingface.co/Tongyi-MAI/Z-Image-Turbo), 6.15B, Apache-2.0, 8 DiT evaluations
(9 scheduler steps), no classifier-free guidance, so there is no negative prompt and `guidance_scale` is always 0.
Text encoder: Qwen3-4B. Both are quantised so the pair fits an 8 GB card with no CPU offload:
- transformer: GGUF Q4_K_M, 3.85 GB (https://huggingface.co/unsloth/Z-Image-Turbo-GGUF), loaded with diffusers
  `from_single_file` + `GGUFQuantizationConfig`, dequantised on the fly;
- text encoder: Qwen3-4B GGUF Q4_K_M, 2.5 GB (https://huggingface.co/unsloth/Qwen3-4B-GGUF). Each tensor is dequantised
  and, for linear layers, re-quantised to bitsandbytes nf4 straight onto the GPU (no CPU copy of the model). Probe
  substitution: vanilla Qwen3-4B, not the Z-Image repo's own encoder copy (8 GB of bf16 shards); the images showed the
  prompts were understood, but no A/B against the original encoder was run.

Sequential residency, as in the NoobAI worker: stage 1 loads the encoder, embeds every prompt of the batch, frees it;
stage 2 loads transformer and VAE. Measured: encoder load + encode 50 s (peak 2.6 GiB, lowest available RAM 2.5 GB, the
tightest point of the whole run), transformer + VAE load 24 s. If a pipeline is still resident from an earlier batch it
is freed before the encoder loads again, so the two never share the card (costs the 24 s reload per batch).

Prompts are never truncated: Qwen3 reads far more than the 77 CLIP tokens that cut the NoobAI prompts; the token count and
the section-to-token map are logged per prompt (`plan_chunks` with a window of `MAX_TOKENS`).

Weights come from a local directory only (`ECHOTALES_ZIMAGE_DIR`, default `~/.cache/echotales/zimage`) with the layout
`base/` (diffusers repo skeleton: tokenizer, text_encoder config, transformer config, vae, scheduler), `gguf/` and `te/`.
Nothing is downloaded here. Extra packages beyond the base environment: `gguf` and `bitsandbytes`, both in the
`render` extra.

Licence: Apache-2.0 for the model; the GGUF files inherit it. Unlike NoobAI this is usable commercially.
"""

from __future__ import annotations

import base64
import gc
import io
import logging
import os
import time
from collections.abc import Mapping
from pathlib import Path

from echotales.pipeline.workers_contract import ImageWorkerRequest, ImageWorkerResponse
from echotales.pipeline.workers_local import fit_size, plan_chunks

logger = logging.getLogger(__name__)

MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"
TRANSFORMER_FILE = "gguf/z-image-turbo-Q4_K_M.gguf"
ENCODER_FILE = "te/Qwen3-4B-Q4_K_M.gguf"
#: Scheduler steps the probe used (9 steps = 8 transformer evaluations, the Turbo recipe).
STEPS = 9
#: Turbo is distilled without CFG; a non-zero scale would double the cost for a worse image.
GUIDANCE = 0.0
#: Free VRAM needed before loading: peak was 5.77 GiB; below this another job (ollama, a render) has the card.
MIN_FREE_GIB = 6.5
#: The probe's lowest available RAM was 2.5 GB, while the encoder loaded; under this floor the load is aborted instead of
#: pushing the machine into swap (owner flagged a RAM spike 2026-10-02).
MIN_AVAILABLE_RAM_GB = 2.0
#: Qwen3's window; the Z-Image pipeline defaults to 512 prompt tokens.
MAX_TOKENS = 512

_GGUF_TO_HF = {
    "attn_q": "self_attn.q_proj", "attn_k": "self_attn.k_proj", "attn_v": "self_attn.v_proj",
    "attn_output": "self_attn.o_proj", "attn_q_norm": "self_attn.q_norm", "attn_k_norm": "self_attn.k_norm",
    "attn_norm": "input_layernorm", "ffn_norm": "post_attention_layernorm",
    "ffn_gate": "mlp.gate_proj", "ffn_up": "mlp.up_proj", "ffn_down": "mlp.down_proj",
}


def lora_args(env: Mapping[str, str]) -> tuple[str, str, float] | None:
    """(folder, file name, scale) for the optional LoRA, or None when `ECHOTALES_ZIMAGE_LORA` is unset.

    Strength is `ECHOTALES_ZIMAGE_LORA_SCALE`, default 0.6. A bare file path is read by diffusers as a hub repo id,
    which offline mode refuses, so folder and file name are given apart. A character LoRA trained by `cloud_lora.py`
    is loaded the same way. Unset means the pipeline is built exactly as before.
    """
    lora = env.get("ECHOTALES_ZIMAGE_LORA")
    if not lora:
        return None
    return str(Path(lora).parent), Path(lora).name, float(env.get("ECHOTALES_ZIMAGE_LORA_SCALE", "0.6"))


def model_dir() -> Path:
    root = Path(os.environ.get("ECHOTALES_ZIMAGE_DIR") or Path.home() / ".cache/echotales/zimage")
    for rel in ("base/model_index.json", TRANSFORMER_FILE, ENCODER_FILE):
        if not (root / rel).exists():
            raise FileNotFoundError(
                f"Z-Image weights are not in {root} (missing {rel}); set ECHOTALES_ZIMAGE_DIR to a directory with "
                f"base/, gguf/ and te/ (nothing is downloaded automatically)"
            )
    return root


def available_ram_gb() -> float:
    """MemAvailable in GB, or infinity where /proc is absent (the guard then does nothing rather than fail)."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) / 2**20
    except OSError:
        pass
    return float("inf")


def hf_name(gguf_name: str) -> str | None:
    """GGUF tensor name -> Qwen3Model parameter name; `None` for the LM head, which an embedding model does not use."""
    if gguf_name == "token_embd.weight":
        return "embed_tokens.weight"
    if gguf_name == "output_norm.weight":
        return "norm.weight"
    if gguf_name == "output.weight":
        return None
    _, i, rest = gguf_name.split(".", 2)
    key, suffix = rest.rsplit(".", 1)
    return f"layers.{i}.{_GGUF_TO_HF[key]}.{suffix}"


class LocalZImageWorker:
    """Generates images for `ImageWorkerRequest`s on the local GPU. Keeps transformer and VAE resident between calls."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root else None
        self._pipe: object | None = None
        #: One record per image: seconds, peak VRAM (GiB), tokens, section-to-token map, plus `load_encode_s`/`load_pipe_s`.
        self.stats: list[dict[str, object]] = []

    @property
    def root(self) -> Path:
        if self._root is None:
            self._root = model_dir()
        return self._root

    def _check_gpu(self) -> None:
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("the Z-Image worker needs a CUDA GPU")
        free_gib = torch.cuda.mem_get_info()[0] / 2**30
        if free_gib < MIN_FREE_GIB:
            raise RuntimeError(
                f"only {free_gib:.1f} GiB of GPU memory is free (need {MIN_FREE_GIB}); stop ollama or the other GPU job first"
            )

    def _load_encoder(self) -> object:
        """Qwen3-4B from GGUF, tensor by tensor onto the GPU as nf4, so no full-precision copy ever sits in RAM."""
        import gguf
        import numpy as np
        import torch
        from bitsandbytes.nn import Linear4bit, Params4bit
        from gguf.quants import dequantize
        from transformers import AutoConfig, Qwen3Model
        from transformers.models.qwen3.modeling_qwen3 import Qwen3RotaryEmbedding

        cfg = AutoConfig.from_pretrained(str(self.root / "base/text_encoder"))
        with torch.device("meta"):
            model = Qwen3Model(cfg)

        def get(path: str) -> object:
            obj: object = model
            for part in path.split("."):
                obj = getattr(obj, part)
            return obj

        plain = (gguf.GGMLQuantizationType.F32, gguf.GGMLQuantizationType.F16)
        for n, t in enumerate(gguf.GGUFReader(str(self.root / ENCODER_FILE)).tensors):
            if n % 16 == 0 and available_ram_gb() < MIN_AVAILABLE_RAM_GB:
                raise RuntimeError(f"available RAM fell under {MIN_AVAILABLE_RAM_GB} GB while loading the text encoder")
            name = hf_name(t.name)
            if name is None:
                continue
            arr = t.data if t.tensor_type in plain else dequantize(t.data, t.tensor_type)
            w = torch.from_numpy(np.ascontiguousarray(arr).astype(np.float32, copy=False))
            w = w.reshape(tuple(reversed(t.shape))).to(torch.bfloat16)
            mod_path, pname = name.rsplit(".", 1)
            mod = get(mod_path)
            if isinstance(mod, torch.nn.Linear):
                lin = Linear4bit(mod.in_features, mod.out_features, bias=False, compute_dtype=torch.bfloat16,
                                 quant_type="nf4", device="meta")
                lin.weight = Params4bit(w, requires_grad=False, quant_type="nf4").to("cuda")
                parent, _, child = mod_path.rpartition(".")
                setattr(get(parent), child, lin)
            else:
                setattr(mod, pname, torch.nn.Parameter(w.to("cuda"), requires_grad=False))
            del w, arr
        model.rotary_emb = Qwen3RotaryEmbedding(cfg).to("cuda")
        return model.eval()

    def _encode(
        self, requests: list[ImageWorkerRequest], sections: list[list[tuple[str, str]]] | None = None
    ) -> tuple[list[object], list[dict[str, object]]]:
        """Stage 1: one embedding per prompt (second-to-last hidden state of the chat-templated prompt, as the pipeline
        does), computed with only the encoder on the card and freed before the transformer loads."""
        import torch
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(str(self.root / "base/tokenizer"))
        started = time.time()
        te = self._load_encoder()
        out, plans = [], []
        with torch.no_grad():
            for i, r in enumerate(requests):
                text = tok.apply_chat_template([{"role": "user", "content": r.prompt}], tokenize=False,
                                               add_generation_prompt=True, enable_thinking=True)
                ids = tok(text, return_tensors="pt").input_ids.cuda()
                hidden = te(input_ids=ids, output_hidden_states=True).hidden_states[-2]  # type: ignore[operator]
                out.append(hidden[0].to(torch.bfloat16).cpu())
                plan = plan_chunks(tok, sections[i] if sections else [("prompt", r.prompt)], size=MAX_TOKENS, sep=" ")
                plan["template_tokens"] = int(ids.shape[1])
                plans.append(plan)
                logger.info("z-image prompt tokens=%s (+template %s) sections=%s", plan["tokens"], ids.shape[1], plan["sections"])
        del te
        gc.collect()
        torch.cuda.empty_cache()
        self._encode_seconds = round(time.time() - started, 1)
        return out, plans

    def _ensure_pipe(self) -> object:
        if self._pipe is None:
            import torch
            from diffusers import (
                AutoencoderKL,
                FlowMatchEulerDiscreteScheduler,
                GGUFQuantizationConfig,
                ZImagePipeline,
                ZImageTransformer2DModel,
            )

            started = time.time()
            base = str(self.root / "base")
            transformer = ZImageTransformer2DModel.from_single_file(
                str(self.root / TRANSFORMER_FILE), config=base, subfolder="transformer",
                quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16), torch_dtype=torch.bfloat16,
            ).to("cuda")
            vae = AutoencoderKL.from_pretrained(base, subfolder="vae", torch_dtype=torch.bfloat16).to("cuda")
            vae.enable_tiling()
            scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(base, subfolder="scheduler")
            self._pipe = ZImagePipeline(scheduler=scheduler, vae=vae, text_encoder=None, tokenizer=None, transformer=transformer)
            # Optional style LoRA (`ECHOTALES_ZIMAGE_LORA=<file>`, strength `ECHOTALES_ZIMAGE_LORA_SCALE`, default 0.6). Off by
            # default: it exists to hold one cel-shaded look if prompt wording alone cannot (owner, 2026-11-19).
            import os

            if args := lora_args(os.environ):
                folder, weight_name, scale = args
                self._pipe.load_lora_weights(folder, weight_name=weight_name, adapter_name="style")
                self._pipe.set_adapters(["style"], adapter_weights=[scale])
            self._pipe_seconds = round(time.time() - started, 1)
        return self._pipe

    def generate_many(
        self,
        requests: list[ImageWorkerRequest],
        sections: list[list[tuple[str, str]]] | None = None,
        *,
        greyscale: bool = False,
    ) -> list[ImageWorkerResponse]:
        """Encode every prompt once, then denoise each. `negative_prompt` is ignored (no CFG on Turbo); `greyscale` runs
        the same INK palette pass as the NoobAI worker so manga mode is monochrome whatever the model leaked."""
        import torch

        if self._pipe is not None:
            self.close()  # sequential residency: the encoder must not share the card with the transformer
        self._check_gpu()
        torch.cuda.reset_peak_memory_stats()
        embeds, plans = self._encode(requests, sections)
        encode_peak = torch.cuda.max_memory_allocated() / 2**30
        pipe = self._ensure_pipe()
        responses = []
        for r, plan, emb in zip(requests, plans, embeds, strict=True):
            width, height = fit_size(r.width, r.height)
            torch.cuda.reset_peak_memory_stats()
            started = time.time()
            image = pipe(  # type: ignore[operator]
                prompt_embeds=[emb.cuda()], height=height, width=width,
                num_inference_steps=r.steps if r.steps != 25 else STEPS, guidance_scale=GUIDANCE,
                generator=torch.Generator("cuda").manual_seed(r.seed),
            ).images[0]
            if greyscale:
                from echotales.pipeline.render.palette import Palette, PaletteSpec, apply_palette

                image = apply_palette(image, PaletteSpec(palette=Palette.INK))
            duration = time.time() - started
            self.stats.append({
                **plan, "seed": r.seed, "seconds": round(duration, 2),
                "denoise_peak_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
                "encode_peak_gib": round(encode_peak, 3), "width": width, "height": height,
                "load_encode_s": getattr(self, "_encode_seconds", 0.0), "load_pipe_s": getattr(self, "_pipe_seconds", 0.0),
            })
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            responses.append(ImageWorkerResponse(
                image_b64=base64.b64encode(buf.getvalue()).decode("ascii"), seed=r.seed, duration_s=duration,
            ))
        return responses

    def close(self) -> None:
        """Free the GPU so another model can use the card."""
        self._pipe = None
        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass
