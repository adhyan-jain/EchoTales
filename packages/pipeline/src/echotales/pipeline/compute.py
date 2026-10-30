"""How heavy a run may be and where it runs: `ECHOTALES_COMPUTE`, and two provider switches under it.

    ECHOTALES_COMPUTE = local-low | local-high | cloud
        local-low   (default) a laptop. One model resident at a time, a memory check before a render, previews before
                    full chapters, a smaller director context.
        local-high  a workstation. The pipeline as it was built: full chapters, the director's own context, no extra
                    guards.
        cloud       a preset that points both providers below at RunPod. No local GPU or RAM is used or checked.

    ECHOTALES_LLM_PROVIDER   = ollama | runpod | openai | gemini | anthropic | gateway | stub
    ECHOTALES_IMAGE_PROVIDER = local | runpod | gemini | openrouter | stub
        Each, when set, overrides what the compute preset would pick, so "RunPod images with a local director" or
        "Gemini for the director, local diffusion" is two lines in `.env`. Unset: `cloud` means runpod for both, and
        `local-*` means ollama (or the existing ECHOTALES_MODEL_BACKEND) and the local diffusion engine.

Why compute is one value: the pieces only make sense together. A preview tier without the memory guard is just a smaller
crash. Why the providers are separate: the hosted ones differ per job (a cheap hosted director with local images is a
real configuration), and the codebase already had Anthropic, an OpenAI-compatible gateway, and Gemini and OpenRouter
image engines. The OpenAI, Gemini and RunPod language models all speak the OpenAI chat protocol, so they share one
client (`llm/gateway.py`) and differ only in base URL, key and model.

Why `local-low` is the default: the development machine has an 8 GB GPU and ran out of memory mid-render (2026-10-02,
and again on 2026-10-18 with 20 GB of swap in use before the first panel). A safe default that can be loosened beats a
fast one that freezes the desktop. `ECHOTALES_COMPUTE=local-high` restores the original behaviour.

What `local-low` changes, and what it does not (measured 2026-10-18 unless stated):
  * **Sequential models.** The director (ollama) runs to completion and is unloaded before the image model loads,
    whatever `render.direction_first` says. Never both at once.
  * **Memory guard.** A local render is refused when available RAM is below `low_compute_min_free_ram_mb` or the GPU is
    busy, with the numbers, instead of starting and taking the desktop down.
  * **Tiers.** A render defaults to a preview (`preview_scenes`, 3 scenes, about ten images) unless the caller asks
    for the full chapter. Scenes, not images: `--max-panels` caps scenes and each gets one to three.
  * **Director context.** `low_compute_num_ctx` (4096): at the configured 8192 `gemma2:9b` was 9.5 GB and 2 GB spilled
    into system RAM; at 4096 it is 8.1 GB with 0.7 GB spilled. The longest director prompt measured for LotM chapter 1
    is about 3,400 tokens at a pessimistic 3 characters per token, so nothing is truncated.
  * **Not changed: the director's model.** The repo measured `qwen2.5:7b` ignoring the director's negative rules where
    `gemma2:9b` held them (EVOLUTION, RI ch1), so a smaller model is only used if `low_compute_director_model` is set.
  * **Not implemented: a faster few-step image model.** None is installed here and none was compared.

Nothing here reads or sends a key by itself: the variables are namespaced `ECHOTALES_*` and empty by default, and a
provider with a missing variable is refused with the variable's name instead of failing mid-run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from echotales.pipeline import gpu

LOCAL_LOW = "local-low"
LOCAL_HIGH = "local-high"
CLOUD = "cloud"
MODES = (LOCAL_LOW, LOCAL_HIGH, CLOUD)

LLM_PROVIDERS = ("ollama", "runpod", "openai", "gemini", "anthropic", "gateway", "stub")
IMAGE_PROVIDERS = ("local", "runpod", "gemini", "openrouter", "stub")

#: Engines that load a diffusion model onto the local GPU.
LOCAL_ENGINES = frozenset({"sdxl", "illustrious", "noobai", "refined", "manga"})
#: Engines that run on someone else's hardware, by the image provider that selects them.
HOSTED_ENGINES = frozenset({"runpod", "gemini", "openrouter"})

#: Base URLs of the OpenAI-compatible language-model providers that have a fixed one (`runpod` takes its own).
OPENAI_COMPATIBLE_BASE = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}

#: Images per scene as measured: 10 scenes of LotM chapter 1 produced 33 images (2026-10-18). A scene's budget is 1 to 3
#: (`render/scenes.py`), plus crowd cuts.
IMAGES_PER_SCENE = 3.3

#: Seconds per image on the development laptop (RTX 4060 Laptop 8 GB, NoobAI XL at 35 steps, ~1.1 s/step, 2026-10-18),
#: image generation only (the director adds a few minutes). A guide for the Studio's "about N minutes", not a promise; None where nothing was measured.
SECONDS_PER_PANEL: dict[str, float | None] = {
    "stub": 0.3, "sdxl": 45.0, "illustrious": 45.0, "noobai": 45.0, "refined": 60.0, "manga": 60.0,
}


def _norm(value: str | None) -> str:
    return re.sub(r"[\s_]+", "-", (value or "").strip().lower())


def parse_mode(value: str | None) -> str:
    """Normalise whatever was typed into one of `MODES`; an unknown value is an error, not a quiet default."""
    raw = _norm(value)
    aliases = {"": LOCAL_LOW, "local": LOCAL_LOW, "low": LOCAL_LOW, "laptop": LOCAL_LOW, "high": LOCAL_HIGH,
               "workstation": LOCAL_HIGH, "runpod": CLOUD}
    mode = aliases.get(raw, raw)
    if mode not in MODES:
        raise ValueError(f"ECHOTALES_COMPUTE={value!r} is not one of {', '.join(MODES)}")
    return mode


def _provider(value: str | None, allowed: tuple[str, ...], name: str) -> str:
    raw = _norm(value)
    if raw and raw not in allowed:
        raise ValueError(f"{name}={value!r} is not one of {', '.join(allowed)}")
    return raw


@dataclass(frozen=True, slots=True)
class ComputePolicy:
    mode: str
    llm_provider: str
    image_provider: str
    local_image_engine: str
    preview_scenes: int
    full_scenes: int
    low_num_ctx: int
    low_director_model: str
    min_free_ram_mb: int
    runpod_api_key: str
    runpod_llm_base_url: str
    runpod_llm_model: str
    runpod_image_endpoint: str
    openai_api_key: str
    openai_model: str
    gemini_api_key: str
    gemini_model: str

    @property
    def cloud(self) -> bool:
        return self.mode == CLOUD

    @property
    def low(self) -> bool:
        return self.mode == LOCAL_LOW

    @property
    def default_tier(self) -> str:
        return "preview" if self.low else "full"

    @property
    def force_sequential(self) -> bool:
        """Run the director to completion and unload it before the image model loads."""
        return self.low

    @property
    def default_engine(self) -> str:
        """The image engine this configuration uses unless a caller names one."""
        return self.local_image_engine if self.image_provider == "local" else self.image_provider

    def scenes_for(self, tier: str | None) -> int:
        """How many scenes a render of this tier covers (`render_panels(max_panels=...)` caps scenes, not images)."""
        return self.preview_scenes if (tier or self.default_tier) == "preview" else self.full_scenes

    def director_num_ctx(self, configured: int) -> int:
        """The context window for the director: capped in `local-low`, as configured otherwise."""
        return min(configured, self.low_num_ctx) if self.low else configured

    def director_model(self, profile_model: str) -> str:
        """The director's ollama model: the profile's, unless `local-low` was given a smaller one."""
        return (self.low_director_model or profile_model) if self.low else profile_model

    def llm_missing(self) -> list[str]:
        """Environment variables the chosen language-model provider still needs, by name."""
        need: dict[str, str] = {}
        if self.llm_provider == "runpod":
            need = {"ECHOTALES_RUNPOD_API_KEY": self.runpod_api_key,
                    "ECHOTALES_RUNPOD_LLM_BASE_URL": self.runpod_llm_base_url,
                    "ECHOTALES_RUNPOD_LLM_MODEL": self.runpod_llm_model}
        elif self.llm_provider == "openai":
            need = {"ECHOTALES_OPENAI_API_KEY": self.openai_api_key, "ECHOTALES_OPENAI_MODEL": self.openai_model}
        elif self.llm_provider == "gemini":
            need = {"ECHOTALES_GEMINI_API_KEY": self.gemini_api_key, "ECHOTALES_GEMINI_MODEL": self.gemini_model}
        return [name for name, value in need.items() if not value]

    def image_missing(self, engine: str) -> list[str]:
        """Environment variables a hosted image engine still needs. Gemini and OpenRouter read their own keys."""
        if engine != "runpod":
            return []
        need = {"ECHOTALES_RUNPOD_API_KEY": self.runpod_api_key,
                "ECHOTALES_RUNPOD_IMAGE_ENDPOINT": self.runpod_image_endpoint}
        return [name for name, value in need.items() if not value]

    def http_engines(self) -> list[str]:
        """Image engines the Studio offers and the server accepts: the stub plus what this configuration selects.

        A hosted engine is accepted over HTTP only when it is the configured provider: choosing it in `.env` is the
        operator's opt-in to spend, and a request must not be able to pick a paid engine the operator never chose.
        """
        if self.image_provider == "local":
            return ["stub", "noobai", "illustrious", "sdxl"]
        if self.image_provider == "stub":
            return ["stub"]
        return ["stub", self.image_provider]

    def estimate_seconds(self, engine: str, scenes: int, density: str = "beat") -> float | None:
        per = SECONDS_PER_PANEL.get(engine)
        images = DENSITY_IMAGES_PER_SCENE.get(density, IMAGES_PER_SCENE)
        return None if per is None else round(per * images * scenes)


def policy(settings: object | None = None) -> ComputePolicy:
    from echotales.pipeline.config import get_settings

    s = settings or get_settings()
    mode = parse_mode(getattr(s, "compute", LOCAL_LOW))
    llm = _provider(getattr(s, "llm_provider", ""), LLM_PROVIDERS, "ECHOTALES_LLM_PROVIDER")
    image = _provider(getattr(s, "image_provider", ""), IMAGE_PROVIDERS, "ECHOTALES_IMAGE_PROVIDER")
    if not llm:
        # An explicit choice wins; then the cloud preset; then the long-standing ECHOTALES_MODEL_BACKEND.
        llm = "runpod" if mode == CLOUD else str(getattr(s.model_backend, "value", s.model_backend))
    if not image:
        image = "runpod" if mode == CLOUD else "local"
    return ComputePolicy(
        mode=mode, llm_provider=llm, image_provider=image,
        local_image_engine=_norm(getattr(s, "local_image_engine", "noobai")) or "noobai",
        preview_scenes=int(s.preview_scenes), full_scenes=int(s.full_scenes),
        low_num_ctx=int(s.low_compute_num_ctx), low_director_model=str(s.low_compute_director_model or ""),
        min_free_ram_mb=int(s.low_compute_min_free_ram_mb),
        runpod_api_key=str(s.runpod_api_key or ""), runpod_llm_base_url=str(s.runpod_llm_base_url or ""),
        runpod_llm_model=str(s.runpod_llm_model or ""), runpod_image_endpoint=str(s.runpod_image_endpoint or ""),
        openai_api_key=str(s.openai_api_key or ""), openai_model=str(s.openai_model or ""),
        gemini_api_key=str(s.gemini_api_key or ""), gemini_model=str(s.gemini_model or ""),
    )


def available_ram_mb() -> int | None:
    """MemAvailable from /proc/meminfo in MiB, or None where it cannot be read (not Linux)."""
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def resource_refusal(engine: str, pol: ComputePolicy | None = None, *, http: bool = False) -> str | None:
    """Why a render with `engine` should not start now, or None. Used by the CLI and the server alike.

    `http=True` (the server) also refuses an engine this configuration did not select; the CLI keeps allowing any
    engine by name, as it always has, because the person at the keyboard is the opt-in.
    """
    pol = pol or policy()
    if engine == "stub":
        return None
    if http and engine not in pol.http_engines():
        return (f"engine {engine!r} is not enabled on this server (ECHOTALES_IMAGE_PROVIDER={pol.image_provider}); "
                f"enabled: {', '.join(pol.http_engines())}")
    if engine in HOSTED_ENGINES:
        missing = pol.image_missing(engine)
        return f"the {engine} engine needs {', '.join(missing)}" if missing else None
    if engine not in LOCAL_ENGINES:
        return None
    if pol.image_provider != "local":
        return (f"ECHOTALES_IMAGE_PROVIDER is {pol.image_provider}, so the local engine {engine!r} is off; "
                "set it to local (or ECHOTALES_COMPUTE=local-low) to use the GPU")

    status = gpu.gpu_status()
    if status is None:
        return f"engine {engine!r} needs an NVIDIA GPU, and none was found on the server"
    if not status.free:
        return f"the GPU is busy ({status.describe()}); stop what is using it, or queue the stub engine"
    if pol.low:
        free = available_ram_mb()
        if free is not None and free < pol.min_free_ram_mb:
            return (f"only {free} MiB of RAM is available (local-low needs {pol.min_free_ram_mb}); close other "
                    "applications, or set ECHOTALES_COMPUTE=local-high to skip this check")
    return None


#: Panel density: how many story blocks (roughly paragraphs) share one picture. "beat" is what every render so far
#: used, a moment per image; "dense" draws every block. The audiobook is the whole text either way, so this only
#: decides how much of it is illustrated (decision of 2026-10-31: offer both in the frontend).
DENSITY_BLOCKS_PER_PANEL = {"beat": 4, "dense": 1}
DEFAULT_DENSITY = "beat"
#: Images per scene by density. Only "beat" was measured (3.3, LotM ch1); "dense" is the chunk-size ratio applied to
#: it and must be re-measured on a real dense render before the estimate is trusted.
DENSITY_IMAGES_PER_SCENE = {"beat": 3.3, "dense": 3.3 * 4}


def density_error(density: str) -> str | None:
    """A message when `density` is not one of the known values, else None."""
    if density in DENSITY_BLOCKS_PER_PANEL:
        return None
    return f"unknown density {density!r}; use one of {sorted(DENSITY_BLOCKS_PER_PANEL)}"
