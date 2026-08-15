"""ModelClient: the single entry point for every model call.

No pipeline stage names a model. A stage names a `Task`, and the client picks
the model from the configured backend. Switching development (ollama) to
production (Anthropic) is therefore one config value and zero code changes,
which is the whole point of routing by task rather than by tier.

This sits above `LLMRouter`. The router still owns escalation accounting; the
client owns *which model* a task gets and *what sampling* it uses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from echotales.core.store import Store
from echotales.pipeline.config import ModelBackend, Settings, get_settings
from echotales.pipeline.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailable,
    SchemaT,
)
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.llm.tasks import (
    VRAM_BUDGET_FRACTION,
    Task,
    TaskProfile,
    models_required,
    profile_for,
)

log = logging.getLogger(__name__)


def detect_vram_bytes() -> int | None:
    """Total VRAM in bytes, or None when it cannot be determined.

    Uses `nvidia-smi` rather than a Python CUDA binding so the check works
    without torch installed — preflight must run on a bare checkout.
    """
    import shutil
    import subprocess

    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    first = out.stdout.strip().splitlines()
    if not first:
        return None
    try:
        return int(float(first[0].strip())) * 1024 * 1024
    except ValueError:
        return None


@dataclass(slots=True)
class OversizedModel:
    """A model whose weights will not fit in VRAM."""

    name: str
    size_bytes: int
    budget_bytes: int

    @property
    def size_gb(self) -> float:
        return self.size_bytes / 1024**3

    @property
    def budget_gb(self) -> float:
        return self.budget_bytes / 1024**3


@dataclass(slots=True)
class PreflightResult:
    backend: str
    available: bool
    missing: list[str]
    detail: str = ""
    #: Present but too large to stay resident on the GPU.
    oversized: list[OversizedModel] = field(default_factory=list)

    def instructions(self) -> str:
        """A copy-pasteable fix for whatever is wrong."""
        if self.available:
            return ""
        lines: list[str] = []
        if self.backend == ModelBackend.OLLAMA.value:
            if self.missing:
                pulls = "\n".join(f"  ollama pull {m}" for m in sorted(self.missing))
                lines.append(f"Missing ollama models:\n{pulls}")
            for over in self.oversized:
                lines.append(
                    f"{over.name} needs {over.size_gb:.1f} GB but the VRAM budget is "
                    f"{over.budget_gb:.1f} GB. It would partially offload to CPU, which "
                    f"competes with the pipeline for system RAM. Pick a smaller model "
                    f"in llm/tasks.py, or run this task on the API backend."
                )
            return "\n".join(lines)
        if self.backend == ModelBackend.GATEWAY.value:
            return self.detail or "gateway unreachable; check it is running on the configured host"
        return "Set ANTHROPIC_API_KEY and install the api extra: uv sync --extra api"


class ModelClient:
    """Dispatches model calls by task against the configured backend."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        store: Store | None = None,
        provider_override: LLMProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store
        #: Set in tests, or when running fully offline.
        self._override = provider_override
        self._providers: dict[str, LLMProvider] = {}
        self.calls = 0

    # ---- provider construction -----------------------------------------

    @property
    def backend(self) -> ModelBackend:
        return self.settings.model_backend

    def _provider_for(self, profile: TaskProfile) -> LLMProvider:
        if self._override is not None:
            return self._override

        if self.backend is ModelBackend.STUB:
            return self._providers.setdefault("stub", StubProvider())

        if self.backend is ModelBackend.OLLAMA:
            model = profile.ollama_model
            existing = self._providers.get(model)
            if existing is None:
                from echotales.pipeline.llm.ollama import OllamaProvider

                existing = OllamaProvider(
                    model=model,
                    host=self.settings.llm_local_host,
                    timeout=self.settings.llm_local_timeout,
                    num_ctx=self.settings.llm_local_num_ctx,
                )
                self._providers[model] = existing
            return existing

        if self.backend is ModelBackend.GATEWAY:
            model = self.settings.llm_gateway_model
            existing = self._providers.get(model)
            if existing is None:
                from echotales.pipeline.llm.gateway import GatewayProvider

                existing = GatewayProvider(model=model, host=self.settings.llm_gateway_host)
                self._providers[model] = existing
            return existing

        model = profile.anthropic_model
        existing = self._providers.get(model)
        if existing is None:
            from echotales.pipeline.llm.anthropic import AnthropicProvider

            existing = AnthropicProvider(
                model=model,
                api_key=self.settings.anthropic_api_key or None,
                timeout=self.settings.llm_api_timeout,
            )
            self._providers[model] = existing
        return existing

    def model_for(self, task: Task) -> str:
        """Which model this task resolves to under the current backend."""
        profile = profile_for(task)
        if self.backend is ModelBackend.STUB:
            return "stub"
        if self.backend is ModelBackend.OLLAMA:
            return profile.ollama_model
        if self.backend is ModelBackend.GATEWAY:
            return self.settings.llm_gateway_model
        return profile.anthropic_model

    # ---- the call --------------------------------------------------------

    def complete(
        self,
        task: Task,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str = "",
        novel_id: str = "",
        chapter: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult[SchemaT]:
        """Run one task-scoped model call."""
        profile = profile_for(task)
        provider = self._provider_for(profile)
        request = LLMRequest(
            stage=task.value,
            prompt=prompt,
            system=system,
            temperature=profile.temperature,
            max_tokens=max_tokens or profile.max_tokens,
        )
        result = provider.complete(request, schema)
        self.calls += 1

        if self.store is not None:
            self.store.log_llm_call(
                stage=task.value,
                tier=provider.tier,
                model=provider.model,
                escalated=False,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
                ok=True,
                novel_id=novel_id,
                chapter=chapter,
            )
        return result

    # ---- preflight --------------------------------------------------------

    def preflight(self) -> PreflightResult:
        """Check every model this backend needs is reachable.

        Run before a long job: discovering a missing model on chapter 140 of a
        600-chapter run wastes hours, and the failure mode is a silent quality
        drop rather than a crash if a stage falls back.
        """
        backend = self.backend.value
        if self.backend is ModelBackend.STUB or self._override is not None:
            return PreflightResult(backend=backend, available=True, missing=[])

        if self.backend is ModelBackend.GATEWAY:
            from echotales.pipeline.llm.gateway import GatewayProvider

            provider = GatewayProvider(
                model=self.settings.llm_gateway_model, host=self.settings.llm_gateway_host
            )
            if provider.available():
                return PreflightResult(backend=backend, available=True, missing=[])
            return PreflightResult(
                backend=backend,
                available=False,
                missing=[self.settings.llm_gateway_model],
                detail=(
                    f"gateway at {self.settings.llm_gateway_host} unreachable, or "
                    f"model {self.settings.llm_gateway_model!r} not in its /models list"
                ),
            )

        required = models_required(backend)

        if self.backend is ModelBackend.ANTHROPIC:
            if not self.settings.anthropic_api_key:
                return PreflightResult(
                    backend=backend,
                    available=False,
                    missing=sorted(required),
                    detail="ANTHROPIC_API_KEY is not set",
                )
            return PreflightResult(backend=backend, available=True, missing=[])

        import httpx

        try:
            response = httpx.get(f"{self.settings.llm_local_host}/api/tags", timeout=5.0)
            response.raise_for_status()
            entries = response.json().get("models", [])
        except Exception as exc:
            return PreflightResult(
                backend=backend,
                available=False,
                missing=sorted(required),
                detail=f"ollama unreachable at {self.settings.llm_local_host}: {exc}",
            )

        sizes = {m.get("name", ""): int(m.get("size", 0)) for m in entries}
        installed = set(sizes)

        # ollama reports exact tags; accept a bare family name as a match for
        # its default tag so "llama3" satisfies "llama3:latest".
        def resolve(model: str) -> str | None:
            if model in installed:
                return model
            family = model.split(":")[0]
            for tag in installed:
                if tag == f"{family}:latest":
                    return tag
            return None

        missing: list[str] = []
        oversized: list[OversizedModel] = []

        vram = detect_vram_bytes()
        budget = int(vram * VRAM_BUDGET_FRACTION) if vram else None

        for model in sorted(required):
            tag = resolve(model)
            if tag is None:
                missing.append(model)
                continue
            # Enforce full GPU residency by measured size. Partial CPU offload
            # would contend with the pipeline for the ~4.5 GB of free system
            # RAM it already streams chapters to stay inside.
            if budget is not None and sizes.get(tag, 0) > budget:
                oversized.append(
                    OversizedModel(name=tag, size_bytes=sizes[tag], budget_bytes=budget)
                )

        problems: list[str] = []
        if missing:
            problems.append(f"{len(missing)} model(s) not pulled")
        if oversized:
            problems.append(f"{len(oversized)} model(s) exceed the VRAM budget")

        return PreflightResult(
            backend=backend,
            available=not missing and not oversized,
            missing=missing,
            oversized=oversized,
            detail="; ".join(problems),
        )

    def require_ready(self) -> None:
        """Raise unless every needed model is available."""
        result = self.preflight()
        if not result.available:
            raise LLMUnavailable(f"{result.detail}\n{result.instructions()}")
