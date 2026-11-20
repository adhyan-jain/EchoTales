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
  * `vram_mb`, `ram_mb` and `speed_seconds` are None unless a measurement exists; `speed_source` then names it (an
    EVOLUTION section or the code comment that recorded it). A speed with no source is rejected by the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

KINDS = ("llm", "image", "tts", "video", "inpaint", "depth", "ocr", "vlm")
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
    EngineSpec("gemma2:9b", "llm", "local-low", "Gemma Terms of Use", None, "llm-model", role="model", where="gpu",
               setup_label="gemma2:9b", note="reader and director"),
    EngineSpec("qwen2.5:7b", "llm", "local-low", "Apache-2.0", True, "llm-model", role="model", where="gpu",
               setup_label="qwen2.5:7b", note="name finding"),
    # ---- speech ----
    EngineSpec("stub", "tts", "local-low", _APACHE_REPO, True, "tts", note="silent placeholder audio"),
    EngineSpec("chatterbox", "tts", "local-low", "MIT", True, "tts", where="gpu", setup_label="Chatterbox TTS",
               note="Resemble AI; weights fetched by the package on first use"),
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
