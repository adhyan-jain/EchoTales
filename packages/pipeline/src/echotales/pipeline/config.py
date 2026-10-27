"""Runtime configuration, read from the environment and `.env`.

The LLM mode is the switch that matters. Testing runs fully local against
ollama; production escalates hard cases to the API. Nothing structural changes
between them -- the router picks providers, and every stage sees the same
`LLMProvider` interface.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Repo-root `config.json` -- plain JSON on purpose, for values a human
#: edits directly rather than through `.env`: the local gateway's
#: host/model, and the render direction-first toggle. Everything else
#: stays in `.env`/environment variables as before; this is not a wholesale
#: migration, only for what actually benefits from being a checked-in,
#: directly-editable file instead of an environment variable.
_CONFIG_JSON = Path(__file__).resolve().parents[5] / "config.json"


def _load_config_json() -> dict[str, object]:
    if not _CONFIG_JSON.exists():
        return {}
    try:
        raw = json.loads(_CONFIG_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, object] = {}
    gateway = raw.get("gateway", {})
    if "host" in gateway:
        out["llm_gateway_host"] = gateway["host"]
    if "model" in gateway:
        out["llm_gateway_model"] = gateway["model"]
    render = raw.get("render", {})
    if "direction_first" in render:
        out["render_direction_first"] = render["direction_first"]
    persona = raw.get("persona", {})
    if "prefix_causal" in persona:
        out["persona_prefix_causal"] = persona["prefix_causal"]
    voice = raw.get("voice", {})
    if "narrator" in voice:
        out["voice_narrator"] = voice["narrator"]
    return out


class LLMMode(StrEnum):
    #: Deterministic canned responses. No GPU, no network. The CI default.
    STUB = "stub"
    #: ollama only.
    LOCAL = "local"
    #: Anthropic only.
    API = "api"
    #: Local for bulk, API for the cases local defers on.
    HYBRID = "hybrid"


class ModelBackend(StrEnum):
    """Which backend `ModelClient` dispatches to.

    Separate from `LLMMode`, which governs *escalation*. This governs *which
    provider hosts the models*: ollama for development, Anthropic for
    production. Switching is one value, and no call site names a model.
    """

    STUB = "stub"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    #: The author's local multi-provider key-rotation proxy
    #: (`llm/gateway.py`), OpenAI-compatible. Free-tier only, no GPU
    #: contention with a local image/TTS engine -- see that module's
    #: docstring for why this exists as a distinct backend from `ollama`.
    GATEWAY = "gateway"
    #: OpenAI-chat-compatible hosted providers, all served by `llm/gateway.py`'s client with their own base URL, key and
    #: model (`pipeline/compute.py`). Selected by `ECHOTALES_LLM_PROVIDER` or the `cloud` compute preset, not
    #: by `ECHOTALES_MODEL_BACKEND`, which keeps meaning the local choice (stub, ollama, anthropic, gateway).
    RUNPOD = "runpod"
    OPENAI = "openai"
    GEMINI = "gemini"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ECHOTALES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_mode: LLMMode = LLMMode.STUB

    #: Which provider hosts the models. `ollama` for development, `anthropic`
    #: for production. Per-task model choice lives in `llm/tasks.py`, so this
    #: is the only value that changes between the two.
    model_backend: ModelBackend = ModelBackend.STUB

    # ollama's `qwen2.5:7b` tag is already the instruct variant. Pinned to the
    # bare tag because that is what is installed locally; the `-instruct`
    # suffix is a separate tag that must be pulled explicitly.
    llm_local_model: str = "qwen2.5:7b"
    llm_local_host: str = "http://localhost:11434"
    llm_local_timeout: float = 180.0
    llm_local_num_ctx: int = 8192

    llm_api_model: str = "claude-sonnet-4-5"
    llm_api_timeout: float = 120.0

    #: The local gateway (`llm/gateway.py`), sourced from `config.json`, not
    #: `.env` -- see that file's own comment for why this pair specifically
    #: lives there.
    llm_gateway_host: str = "http://127.0.0.1:11435/v1"
    llm_gateway_model: str = "coding-best"

    #: True: direct every panel first (one pass, gateway/API only, no local
    #: GPU needed), cache the results, then generate images in a second
    #: pass. False: direct and generate interleaved, one panel at a time
    #: (the original behaviour) -- only safe when direction doesn't need
    #: the local GPU (gateway/API backends), never with `ollama` alongside
    #: a local image engine (`docs/EVOLUTION.md` section 9's measured OOM).
    render_direction_first: bool = True

    #: True: persona traits are written as revisions stamped by the chapter their evidence reaches
    #: (`build_personas(prefix_causal=True)`), so a reader-position query serves only what the reader could know.
    #: The default build stamped each trait at first sighting but computed it from up to twelve later chapters: 23
    #: of 289 gender values served at a cut came from chapters not yet read, and 47 depended on them
    #: (docs/research/PAPER/READER_FAITHFULNESS.md 5.2, 5.4). Whole-novel readers (voice casting, reference sheets,
    #: the dashboard) read the final revision and were byte-for-byte unchanged on three serials
    #: (scripts/prefix_audit/product_parity.py). Costs about 9% more attribute rows and ~50% more persona-stage time.
    persona_prefix_causal: bool = True
    #: Bank speaker id that reads the narration, chosen by ear (`config.json` voice.narrator). The narrator reads
    #: most of every chapter (184 of 245 lines on RI), so it is a taste decision, not something to pick by id order.
    #: Empty: `voice/runner.py::_narrator_voice`'s deterministic choice.
    voice_narrator: str = ""

    #: Below this confidence a local answer is escalated in hybrid mode.
    escalation_confidence_threshold: float = 0.75

    #: Hard ceiling on escalated calls per run. Guards against a
    #: misconfiguration turning a 600-chapter job into an unbounded API bill.
    max_escalations_per_run: int = 5000

    db_path: Path = Path("data/db/reverend-insanity.db")
    sources_path: Path = Path("data/sources.toml")
    gold_path: Path = Path("data/gold")
    lexicon_path: Path = Path("data/lexicons")

    #: Chapters per LLM processing window (docs/design/plans.md Section 6).
    window_size: int = 40

    #: Conformal target error rate for the LINK decision.
    conformal_alpha: float = 0.05

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # --- compute and providers (pipeline/compute.py) -------------------------------------------------------------
    #: local-low | local-high | cloud. The default is the laptop-safe one; see compute.py for what each changes.
    compute: str = "local-low"
    #: Optional overrides of what the preset picks. Empty means "follow the preset".
    llm_provider: str = ""
    image_provider: str = ""
    #: The local diffusion engine when the image provider is `local`.
    local_image_engine: str = "noobai"
    #: Scenes rendered in a preview and in a full chapter. `--max-panels` is a cap on SCENES, and a scene gets one to
    #: three images: 10 scenes produced 33 images on LotM chapter 1 (2026-10-18), so a preview is 3 scenes, about
    #: ten images. `echotales render --max-panels` still wins.
    preview_scenes: int = 3
    full_scenes: int = 70
    #: `local-low` only: the director's context window, and an optional smaller ollama model for it.
    low_compute_num_ctx: int = 4096
    low_compute_director_model: str = ""
    #: `local-low` only: a local render is refused below this much available RAM.
    low_compute_min_free_ram_mb: int = 3000
    #: Hosted providers. Namespaced ECHOTALES_* and empty by default; nothing is read from anywhere else.
    runpod_api_key: str = ""
    runpod_llm_base_url: str = ""
    runpod_llm_model: str = ""
    runpod_image_endpoint: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    gemini_api_key: str = ""
    gemini_model: str = ""

    #: Stage toggles, for iterating on one half of the render pipeline
    #: without paying for the other. Both real backends are expensive and
    #: independent -- panel generation is 40-70s/image on this hardware,
    #: real TTS is ~5-10s/line -- so tuning prompts for one while the other
    #: keeps generating for real wastes exactly the GPU time being iterated
    #: to save. `False` forces that stage to its stub engine regardless of
    #: what `--image-engine`/`--engine` asked for, rather than requiring the
    #: caller to remember to pass `stub` by hand every time; the CLI prints
    #: a note when a toggle overrides an explicit real-engine request, so
    #: the override is never silent.
    enable_image_gen: bool = True
    enable_tts: bool = True


_settings: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    global _settings
    if _settings is None or reload:
        settings = Settings()
        # config.json fills in only fields an env var/`.env` didn't already
        # set -- pydantic-settings gives init kwargs the *highest*
        # precedence, so passing these as constructor args would make
        # config.json always win over an explicit env var, backwards from
        # what a human editing a checked-in file next to `.env` expects.
        # Applied after construction instead, and only where the field
        # still holds its hardcoded default.
        for key, value in _load_config_json().items():
            if getattr(settings, key) == Settings.model_fields[key].default:
                setattr(settings, key, value)
        _settings = settings
    return _settings
