"""One table of every engine the pipeline can use, so adding a model is one entry here and not five list edits.

Why this exists: the engine names used to live in `compute.py` (LOCAL_ENGINES, HOSTED_ENGINES, VIDEO_ENGINES,
SECONDS_PER_PANEL, LLM_PROVIDERS, IMAGE_PROVIDERS), `jobs.py` (ALLOWED_HTTP_ENGINES, VIDEO_ENGINES), `cli.py` (five
copies of the `--image-engine` choices, which had already drifted: `render` offered `runpod`, `persona reference` did
not), `voice/engine.py`, `render/motion.py`, `webview_server.py` and `comic/ocr.py`. A licence or a memory need lived in
none of them, so nobody could ask "which of these can I ship commercially".

This module imports nothing from the pipeline (it is imported by `compute.py` and `cli.py`), and only declares data.
The implementations (the classes behind each name) stay where they are; the registry is the list of what exists and
what each costs.

Honesty rules for the fields:
  * `commercial_safe` is True only where the licence was checked and permits commercial use, False where it forbids it
    (THIRD_PARTY_LICENSES.md), and None where it has not been checked. The `--commercial-safe` filter keeps only True.
  * `version`, `params_b`, `quantization`, `eval_ref` are filled only from something checked (`ollama show`,
    `ollama list`, a model card, a file under `data/eval/`); None means not looked up, never "probably".
  * `approval` is the owner's open-weight size policy (decision D70): "policy" up to 8B parameters, "owner_exception"
    for the named allowlist, "not_authorized" above that. Hosted APIs (Anthropic and friends) are outside it because
    their parameter counts are unpublished; `check_model_policy` enforces it.
  * `vram_mb`, `ram_mb` and `speed_seconds` are None unless a measurement exists; `speed_source` then names it (an
    EVOLUTION section or the code comment that recorded it). A speed with no source is rejected by the tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

KINDS = ("llm", "image", "tts", "video", "inpaint", "depth", "ocr", "vlm", "ner")
TIERS = ("local-low", "local-high", "cloud")
#: `engine` is something a user picks by name; `provider` is a hosting choice for a kind; `model` is a weight set the
#: code loads under a provider or a compiler (listed so its licence is not lost).
ROLES = ("engine", "provider", "model")
#: Where the work runs: no card, the local GPU, or someone else's hardware.
WHERE = ("cpu", "gpu", "hosted")

_APACHE_REPO = "Apache-2.0 (this repository)"


@dataclass(frozen=True, slots=True)
class EngineSpec:
    name: str
    kind: str
    tier: str
    licence: str
    #: True checked and allowed; False checked and forbidden; None not checked.
    commercial_safe: bool | None
    #: Which code path selects this entry; lists are filtered by (kind, surface).
    surface: str
    role: str = "engine"
    where: str = "cpu"
    vram_mb: int | None = None
    ram_mb: int | None = None
    speed_seconds: float | None = None
    speed_unit: str | None = None
    speed_source: str | None = None
    #: The HTTP API (Studio) accepts this image engine by name in any configuration.
    http: bool = False
    #: Position in the Studio's list when the image provider is `local` (None: not offered there).
    studio_rank: int | None = None
    #: The text `scripts/setup.sh` prints for this model; a test checks its licence against this entry.
    setup_label: str | None = None
    note: str = ""
    #: Exact tag, digest or HF revision the figures below were taken on.
    version: str | None = None
    #: Parameter count in billions, for the open-weight size policy (D70).
    params_b: float | None = None
    #: Advertised size class in billions (qwen3:8b is 8.2B exact, class 8). The D70 ceiling applies to this (owner
    #: addendum 2026-11-27); `params_b` is still recorded exactly.
    size_class_b: float | None = None
    quantization: str | None = None
    approval: Literal["policy", "owner_exception", "not_authorized"] | None = None
    #: Repo-relative path of the measurement file for this model.
    eval_ref: str | None = None


def _img(name: str, *, licence: str, safe: bool | None, where: str, tier: str = "local-low", http: bool = False,
         rank: int | None = None, speed: float | None = None, source: str | None = None, note: str = "") -> EngineSpec:
    return EngineSpec(name, "image", tier, licence, safe, "render-image", where=where, http=http, studio_rank=rank,
                      speed_seconds=speed, speed_unit="image" if speed is not None else None, speed_source=source,
                      note=note)


_SPEED_GUIDE = ("compute.py SECONDS_PER_PANEL: NoobAI XL, 35 steps, ~1.1 s/step, RTX 4060 Laptop 8 GB, 2026-10-18; "
                "applied to the same-family engines, not timed separately")
_UNCHECKED = "unchecked; see THIRD_PARTY_LICENSES.md"

# Declaration order is user-visible: it is the order of the CLI `--image-engine` choices and of error messages.
ENGINES: tuple[EngineSpec, ...] = (
    # ---- image engines (render-image: `render --image-engine`, `persona reference --engine`, HTTP jobs) ----
    _img("stub", licence=_APACHE_REPO, safe=True, where="cpu", tier="local-low", http=True, rank=0, speed=0.3,
         source="compute.py SECONDS_PER_PANEL: flat placeholder fill, no model",
         note="writes flat placeholders; for tests and CI"),
    _img("sdxl", licence=_UNCHECKED, safe=None, where="gpu", http=True, rank=3, speed=45.0, source=_SPEED_GUIDE),
    _img("manga", licence=_UNCHECKED, safe=None, where="gpu", http=True, speed=60.0,
         source="compute.py SECONDS_PER_PANEL guide figure; not separately measured"),
    _img("illustrious", licence="Illustrious model licence (non-commercial)", safe=False, where="gpu", http=True,
         rank=2, speed=45.0, source=_SPEED_GUIDE, note="THIRD_PARTY_LICENSES.md, decision D7"),
    _img("noobai", licence="NoobAI licence (non-commercial, covers generated images)", safe=False, where="gpu",
         http=True, rank=1, speed=45.0, source=_SPEED_GUIDE, note="THIRD_PARTY_LICENSES.md, decision D7"),
    _img("refined", licence=_UNCHECKED, safe=None, where="gpu", http=True, speed=60.0,
         source="compute.py SECONDS_PER_PANEL guide figure; not separately measured"),
    # Hosted image engines. Order matters: `ECHOTALES_IMAGE_PROVIDER` errors list them in this order.
    _img("runpod", licence="hosted service terms", safe=None, where="hosted", tier="cloud"),
    _img("gemini", licence="hosted service terms", safe=None, where="hosted", tier="cloud"),
    _img("openrouter", licence="hosted service terms", safe=None, where="hosted", tier="cloud"),
    EngineSpec("z-image-turbo", "image", "local-low", "Apache-2.0", True, "compiler", role="model", where="gpu",
               setup_label="Z-Image Turbo",
               note="Tongyi-MAI/Z-Image-Turbo, loaded by the compiled-route image worker; weights placed by hand"),
    EngineSpec("noobai-xl-1.1", "image", "local-low", "fair-ai-public-license-1.0-sd (non-commercial, card metadata)", False,
               "compiler", role="model", where="gpu", note="Laxhar/noobai-XL-1.1, the compiler's SDXL-tag profile; comparison only (D58)"),
    EngineSpec("illustrious-xl-0.1", "image", "local-low", "fair-ai-public-license-1.0-sd (HF card metadata)", False,
               "compiler", role="model", where="gpu",
               note="OnomaAIResearch/Illustrious-xl-early-release-v0, art bake-off v3 arm C2; never measured"),
    EngineSpec("anima", "image", "local-low",
               "CircleStone Labs Non-Commercial License (derivative of Cosmos-Predict2-2B, NVIDIA Open Model License)", False,
               "compiler", role="model", where="gpu", note="circlestone-labs/Anima-Base-v1.0-Diffusers; weights not downloaded, never measured"),
    # ---- language models ----
    EngineSpec("ollama", "llm", "local-low", "MIT (ollama server)", True, "llm-provider", role="provider", where="gpu"),
    EngineSpec("runpod", "llm", "cloud", "hosted service terms", None, "llm-provider", role="provider", where="hosted"),
    EngineSpec("openai", "llm", "cloud", "hosted service terms", None, "llm-provider", role="provider", where="hosted"),
    EngineSpec("gemini", "llm", "cloud", "hosted service terms", None, "llm-provider", role="provider", where="hosted"),
    EngineSpec("anthropic", "llm", "cloud", "hosted service terms", None, "llm-provider", role="provider",
               where="hosted"),
    EngineSpec("gateway", "llm", "cloud", "hosted service terms", None, "llm-provider", role="provider",
               where="hosted"),
    EngineSpec("stub", "llm", "local-low", _APACHE_REPO, True, "llm-provider", role="provider",
               note="deterministic canned replies; ECHOTALES_LLM_MODE=stub"),
    # Digest and quantization are from `ollama list` / `ollama show` on the dev machine, 2026-11-26.
    EngineSpec("gemma2:9b", "llm", "local-low", "Gemma Terms of Use", None, "llm-model", role="model", where="gpu",
               setup_label="gemma2:9b", note="reader and director; 9.2B is an owner-approved exception (D70)",
               version="ff02c3702f32", params_b=9.2, size_class_b=9.0, quantization="Q4_0", approval="owner_exception",
               eval_ref="data/eval/reader/bakeoff-gemma2-9b.json"),
    EngineSpec("qwen2.5:7b", "llm", "local-low", "Apache-2.0", True, "llm-model", role="model", where="gpu",
               setup_label="qwen2.5:7b", note="name finding",
               version="845dbda0ea48", params_b=7.6, size_class_b=7.0, quantization="Q4_K_M", approval="policy",
               eval_ref="data/eval/reader/bakeoff-qwen2.5-7b.json"),
    # Owner addendum 2026-11-27 to D70: the ceiling is the advertised class, so 8.2B exact is allowed as an "8B" model.
    # Digest and quantization from `ollama list` / `ollama show qwen3:8b`, 2026-11-27.
    EngineSpec("qwen3:8b", "llm", "local-low", "Apache-2.0", True, "llm-model", role="model", where="gpu",
               setup_label="qwen3:8b", note="NER context classifier (mentions.detector=hybrid)",
               version="500a1f067a9f", params_b=8.2, size_class_b=8.0, quantization="Q4_K_M", approval="policy",
               eval_ref="data/eval/ner/final/bakeoff-hybrid-qwen3-8b-0.7-0.3-test-rescored-filtered.json"),
    # Served by vLLM on a RunPod pod (`RUNPOD_SERVED_MODELS` in .env.example). Above the owner's ceiling, so refused
    # by `check_model_policy`; the entries exist so the refusal names a reason. Parameter counts are the model cards'.
    EngineSpec("llama70b", "llm", "cloud", "verify (Llama community licence)", None, "llm-model", role="model",
               where="hosted", params_b=70.6, approval="not_authorized",
               note="RunPod served-model alias; not authorised (D70); used only in the CHIMERA study"),
    EngineSpec("qwen72b", "llm", "cloud", "verify (Qwen licence)", None, "llm-model", role="model",
               where="hosted", params_b=72.7, approval="not_authorized",
               note="RunPod served-model alias; not authorised (D70)"),
    EngineSpec("olmo32b", "llm", "cloud", "verify (OLMo 2 32B)", None, "llm-model", role="model",
               where="hosted", params_b=32.2, approval="not_authorized",
               note="RunPod served-model alias; not authorised (D70)"),
    # ---- named-entity recognition (candidates for the romanized-name NER work; none is wired into a stage here) ----
    EngineSpec("urchade/gliner_medium-v2.1", "ner", "local-low", "Apache-2.0", True, "ner-model", role="model",
               params_b=0.2, size_class_b=1.0, approval="policy", note="GLiNER zero-shot span NER; parameter count approximate"),
    EngineSpec("urchade/gliner_large-v2.1", "ner", "local-low", "Apache-2.0", True, "ner-model", role="model",
               params_b=0.5, size_class_b=1.0, approval="policy", note="GLiNER zero-shot span NER; parameter count approximate"),
    EngineSpec("urchade/gliner_multi-v2.1", "ner", "local-low", "Apache-2.0", True, "ner-model", role="model",
               params_b=0.5, size_class_b=1.0, approval="policy", note="GLiNER multilingual; parameter count approximate"),
    EngineSpec("numind/NuNER_Zero", "ner", "local-low", "verify (MIT per the model card, not re-read here)", None,
               "ner-model", role="model", params_b=0.4, size_class_b=1.0, approval="policy",
               note="NuNER Zero span NER; parameter count approximate"),
    EngineSpec("en_core_web_sm", "ner", "local-low", "MIT", True, "ner-model", role="model",
               params_b=0.00001, size_class_b=1.0, approval="policy", note="spaCy English small pipeline, CPU"),
    EngineSpec("en_core_web_trf", "ner", "local-low", "MIT", True, "ner-model", role="model",
               params_b=0.125, size_class_b=1.0, approval="policy", note="spaCy English transformer pipeline (RoBERTa-base)"),
    EngineSpec("nametag3-english", "ner", "local-low", "CC BY-NC-SA 4.0", False, "ner-model", role="model",
               params_b=0.6, size_class_b=1.0, approval="policy", note="UFAL NameTag 3 English; eval-only, non-commercial"),
    # ---- speech ----
    EngineSpec("stub", "tts", "local-low", _APACHE_REPO, True, "tts", note="silent placeholder audio"),
    EngineSpec("chatterbox", "tts", "local-low", "MIT", True, "tts", where="gpu", setup_label="Chatterbox TTS",
               note="Resemble AI; weights fetched by the package on first use"),
    EngineSpec("elevenlabs", "tts", "cloud", "hosted service terms (ElevenLabs, the user's own account and key)", None, "tts",
               where="hosted",
               note="optional, never the default; library or the user's own uploaded voices only, no cloning of real "
                    "people; text leaves the machine; mock-tested only (EVOLUTION 4.174)"),
    # ---- optional hosted engines behind the cloud ledger (own surfaces: not in any local choice list) ----
    EngineSpec("qwen-image-edit-runpod", "image", "cloud", "hosted service terms; model weights Apache-2.0 (Qwen-Image-Edit)",
               None, "cloud-keyframe", where="hosted",
               note="multi-reference keyframes from approved character sheets; RunPod worker; mock-tested only (4.174)"),
    EngineSpec("wan-runpod", "video", "cloud", "hosted service terms; worker weights Apache-2.0 (Wan 2.2), unchecked here",
               None, "cloud-video", where="hosted",
               note="image to video on a RunPod worker (Wan 2.2 / AniSora class); mock-tested only (4.174)"),
    EngineSpec("character-lora-runpod", "image", "cloud", "hosted service terms; the LoRA is yours (trained from your "
               "approved references)", None, "cloud-lora", role="provider", where="hosted",
               note="trains one character LoRA from approved references; loaded locally via ECHOTALES_ZIMAGE_LORA; "
                    "mock-tested only (4.174)"),
    # ---- video: the chapter video (`echotales anime`, the `video` job) ----
    EngineSpec("stills", "video", "local-low", _APACHE_REPO, True, "anime-video", note="ffmpeg pans over the stills"),
    EngineSpec("ltx-local", "video", "local-low", _UNCHECKED, None, "anime-video", where="gpu", vram_mb=7400,
               ram_mb=3500, speed_seconds=18.0, speed_unit="4 s clip (denoise 12 s + decode 6 s, model warm)",
               speed_source="EVOLUTION 4.146 (RTX 4060 Laptop 8 GB; 27 to 70 s per clip with reload); vram is the "
                            "nvidia-smi peak, ram the free RAM compute.py requires to start",
               note="LTX-Video 2B 0.9.8 distilled, image to video"),
    # ---- video: motion-clip library (`render --motion-engine`) ----
    EngineSpec("stub", "video", "local-low", _APACHE_REPO, True, "motion-clip"),
    EngineSpec("svd", "video", "local-low", _UNCHECKED, None, "motion-clip", where="gpu",
               note="Stable Video Diffusion, image to video"),
    # ---- motion comic: clean plates, depth, text reading ----
    EngineSpec("cv", "inpaint", "local-low", "Apache-2.0 (OpenCV)", True, "comic-inpaint",
               note="Telea; the fallback when no GPU or weights"),
    EngineSpec("lama", "inpaint", "local-low", "Apache-2.0", True, "comic-inpaint", where="gpu",
               note="big-lama TorchScript under data/models/lama/"),
    EngineSpec("depth-anything-v2-small", "depth", "local-low", "Apache-2.0", True, "comic-depth", where="gpu",
               note="25M parameters; the Base and Large releases are under a non-commercial licence"),
    EngineSpec("rapidocr", "ocr", "local-low", "Apache-2.0", True, "comic-ocr"),
    EngineSpec("easyocr", "ocr", "local-low", "Apache-2.0", True, "comic-ocr"),
)


def _check(kind: str | None) -> None:
    if kind is not None and kind not in KINDS:
        raise ValueError(f"unknown engine kind {kind!r}; use one of {', '.join(KINDS)}")


def select(*, kind: str | None = None, surface: str | None = None, role: str | None = None,
           where: str | None = None, commercial_safe: bool = False) -> tuple[EngineSpec, ...]:
    """Entries matching every given filter; `commercial_safe=True` keeps only those checked as commercial-use safe."""
    _check(kind)
    return tuple(
        e for e in ENGINES
        if (kind is None or e.kind == kind) and (surface is None or e.surface == surface)
        and (role is None or e.role == role) and (where is None or e.where == where)
        and (not commercial_safe or e.commercial_safe is True)
    )


def names(kind: str, *, surface: str | None = None, role: str = "engine", where: str | None = None) -> tuple[str, ...]:
    """Names in declaration order. `role` defaults to engine, so providers and loaded models never leak into a choice list."""
    return tuple(e.name for e in select(kind=kind, surface=surface, role=role, where=where))


def get(kind: str, name: str, *, surface: str | None = None) -> EngineSpec:
    for e in select(kind=kind, surface=surface, role=None):
        if e.name == name:
            return e
    raise KeyError(f"no {kind} engine named {name!r}")


def expected(options: tuple[str, ...]) -> str:
    """`'a' or 'b'` for two, `'a', 'b' or 'c'` for more: the phrase the old error messages used."""
    quoted = [repr(n) for n in options]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " or " + quoted[-1]


# ---- the lists this replaces, each derived in one place ----

def http_image_engines() -> frozenset[str]:
    """Image engines the HTTP API accepts in any configuration (was `jobs.ALLOWED_HTTP_ENGINES`)."""
    return frozenset(e.name for e in select(kind="image", surface="render-image") if e.http)


def local_image_engines() -> frozenset[str]:
    """Image engines that load a diffusion model on the local GPU (was `compute.LOCAL_ENGINES`)."""
    return frozenset(names("image", surface="render-image", where="gpu"))


def hosted_image_engines() -> frozenset[str]:
    """Image engines that run on someone else's hardware (was `compute.HOSTED_ENGINES`)."""
    return frozenset(names("image", surface="render-image", where="hosted"))


def studio_local_engines() -> list[str]:
    """The engines the Studio offers when the image provider is `local`, in its display order."""
    ranked = [e for e in select(kind="image", surface="render-image") if e.studio_rank is not None]
    return [e.name for e in sorted(ranked, key=lambda e: e.studio_rank or 0)]


def seconds_per_image() -> dict[str, float | None]:
    """Seconds per image where a figure exists (was `compute.SECONDS_PER_PANEL`)."""
    return {e.name: e.speed_seconds for e in select(kind="image", surface="render-image") if e.speed_seconds is not None}


def compiler_profiles() -> tuple[str, ...]:
    """The image models the prompt compiler has a profile for, in declaration order (what `render.image_model` may name)."""
    return names("image", surface="compiler", role="model")


def llm_providers() -> tuple[str, ...]:
    return names("llm", role="provider")


def image_providers() -> tuple[str, ...]:
    """`local` plus every hosted image engine plus the stub: what `ECHOTALES_IMAGE_PROVIDER` may say."""
    return ("local", *sorted(hosted_image_engines(), key=names("image", surface="render-image").index), "stub")


# ---- the open-weight size policy (decision D70) ----

#: Owner policy 2026-11-26: open-weight models up to 8B parameters; these names are the only larger ones allowed.
OWNER_APPROVED_EXCEPTIONS = frozenset({"gemma2:9b"})
MAX_OPEN_WEIGHT_PARAMS_B = 8.0


_SIZE_IN_NAME = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)b(?![a-z])", re.IGNORECASE)


class ModelPolicyError(ValueError):
    """An open-weight model above the owner's size ceiling (or marked not authorised) was selected."""


def effective_size_b(spec: EngineSpec) -> float | None:
    """The size the ceiling applies to: advertised class, else the size in the tag, else the exact count.

    Why (owner addendum 2026-11-27): qwen3:8b is advertised as 8B and ollama reports 8.2B; comparing the exact count
    would refuse a model the owner called allowed. The exact count stays in `params_b` for the record.
    """
    if spec.size_class_b is not None:
        return spec.size_class_b
    sizes = [float(m) for m in _SIZE_IN_NAME.findall(spec.name)]
    return max(sizes) if sizes else spec.params_b


def check_model_policy(spec: EngineSpec) -> None:
    """Refuse an open-weight llm/ner spec above 8B unless it is the owner's named exception.

    Why: the owner's ceiling used to live only in prose, and the RunPod served-model list (llama70b, qwen72b,
    olmo32b) sat in `.env.example` with nothing stopping a run from selecting it. Hosted APIs are exempt: their
    parameter counts are unpublished, so the policy cannot apply to them (assumption recorded in D70).
    """
    if spec.kind not in ("llm", "ner") or spec.role != "model":
        return
    if spec.approval == "not_authorized":
        raise ModelPolicyError(f"model {spec.name!r} is not authorised by the owner's open-weight policy (D70)")
    excepted = spec.approval == "owner_exception" and spec.name in OWNER_APPROVED_EXCEPTIONS
    size = effective_size_b(spec)
    if size is not None and size > MAX_OPEN_WEIGHT_PARAMS_B and not excepted:
        raise ModelPolicyError(
            f"model {spec.name!r} is in the {size:g}B size class, above the owner's {MAX_OPEN_WEIGHT_PARAMS_B:g}B "
            f"ceiling, and is not an approved exception ({', '.join(sorted(OWNER_APPROVED_EXCEPTIONS))}); see D70")


def check_llm_model(name: str, *, provider: str) -> None:
    """Fail-closed policy check for the model a local (`ollama`) or RunPod provider is about to load.

    A registered name uses its advertised size class (see `effective_size_b`). An unregistered name falls back to the size written in the tag
    (`llama3:70b`, `qwen72b`); a name with no size in it passes, because refusing every unknown tag would also refuse
    the small models people legitimately pull, and the registry is where such a model gets its size recorded.
    Stub and hosted-API providers are exempt (D70).
    """
    if provider not in ("ollama", "runpod") or not name:
        return
    for e in ENGINES:
        if e.kind == "llm" and e.role == "model" and e.name == name:
            check_model_policy(e)
            return
    sizes = [float(m) for m in _SIZE_IN_NAME.findall(name)]
    if sizes and max(sizes) > MAX_OPEN_WEIGHT_PARAMS_B and name not in OWNER_APPROVED_EXCEPTIONS:
        raise ModelPolicyError(
            f"model {name!r} looks like {max(sizes):g}B parameters, above the owner's {MAX_OPEN_WEIGHT_PARAMS_B:g}B "
            f"ceiling; register it with its size or choose a smaller model (D70)")
