"""Runtime configuration, read from the environment and `.env`.

The LLM mode is the switch that matters. Testing runs fully local against
ollama; production escalates hard cases to the API. Nothing structural changes
between them -- the router picks providers, and every stage sees the same
`LLMProvider` interface.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    #: Below this confidence a local answer is escalated in hybrid mode.
    escalation_confidence_threshold: float = 0.75

    #: Hard ceiling on escalated calls per run. Guards against a
    #: misconfiguration turning a 600-chapter job into an unbounded API bill.
    max_escalations_per_run: int = 5000

    db_path: Path = Path("data/echotales.db")
    sources_path: Path = Path("data/sources.toml")
    gold_path: Path = Path("data/gold")
    lexicon_path: Path = Path("data/lexicons")

    #: Chapters per LLM processing window (plans.md §6).
    window_size: int = 40

    #: Conformal target error rate for the LINK decision.
    conformal_alpha: float = 0.05

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

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
        _settings = Settings()
    return _settings
