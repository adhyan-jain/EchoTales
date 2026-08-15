"""Local multi-provider gateway, OpenAI-compatible.

Points at the author's own local key-rotation proxy (not part of this
project): an OpenAI-compatible server on `127.0.0.1` that fans a single
logical model name ("coding-best") out across several providers' free
tiers (Gemini, Groq, OpenRouter, ...) and falls back automatically when one
is rate-limited. From this codebase's side it is just another
`LLMProvider` -- the rotation/fallback logic is entirely the gateway's
problem, not this client's.

Exists specifically to get panel direction (`render/direction.py`) off
ollama: the local diffusion engine and a resident ollama model cannot both
fit in 8 GB VRAM (`EVOLUTION.md` section 9), and routing direction calls
through this gateway instead removes ollama from the GPU picture entirely
for that stage, at zero API cost (free-tier keys only).
"""

from __future__ import annotations

import os
import time

import httpx
from echotales.pipeline.llm.base import (
    LLMParseError,
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailable,
    SchemaT,
    parse_into,
    schema_instructions,
)

DEFAULT_HOST = "http://127.0.0.1:11435/v1"
DEFAULT_MODEL = "coding-best"
#: The gateway does its own key management; this is a placeholder so the
#: HTTP client always sends a (non-empty, per OpenAI client convention)
#: Authorization header, never a real secret.
PLACEHOLDER_KEY = "not-needed"


class GatewayProvider(LLMProvider):
    tier = "gateway"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = 180.0,
    ) -> None:
        self._model = model
        self.host = (host or os.environ.get("ECHOTALES_GATEWAY_HOST") or DEFAULT_HOST).rstrip(
            "/"
        )
        self._api_key = api_key or os.environ.get("ECHOTALES_GATEWAY_API_KEY") or PLACEHOLDER_KEY
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    @property
    def model(self) -> str:
        return self._model

    def available(self) -> bool:
        try:
            resp = self._client.get(f"{self.host}/models", timeout=3.0)
            resp.raise_for_status()
            models = {m.get("id", "") for m in resp.json().get("data", [])}
        except Exception:
            return False
        return self._model in models

    def complete(self, request: LLMRequest, schema: type[SchemaT]) -> LLMResult[SchemaT]:
        prompt = f"{request.prompt}\n\n{schema_instructions(schema)}"
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            # Honoured by providers that support it, ignored by those that
            # don't -- schema_instructions in the prompt is what actually
            # carries the requirement across every provider the gateway
            # might route to.
            "response_format": {"type": "json_object"},
        }
        started = time.perf_counter()

        # The gateway's whole reason to exist is rotating across providers
        # under free-tier rate limits, and not every provider it can land
        # on honours "return only JSON" as reliably as another -- confirmed
        # directly: an identical request against this same gateway returned
        # clean JSON on one call and a markdown bullet list ("*   `shot`:
        # ...") with no JSON object in it at all on another, under load, no
        # code change in between. A retry is not a generic robustness
        # nicety here, it is *the* fix -- it gives the gateway's own
        # rotation a second chance to land on a provider that behaves,
        # which fixing the parser to tolerate one bad output shape would
        # not: the next bad shape would just be a different one.
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                resp = self._client.post(
                    f"{self.host}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                value = parse_into(schema, content)
                break
            except httpx.HTTPError as exc:
                last_exc = exc
                continue
            except (KeyError, IndexError) as exc:
                last_exc = exc
                continue
            except LLMParseError as exc:
                last_exc = exc
                continue
        else:
            raise LLMUnavailable(
                f"gateway request failed after 2 attempts: {last_exc}"
            ) from last_exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        usage = data.get("usage") or {}
        return LLMResult(
            value=value,
            model=data.get("model", self._model),
            tier=self.tier,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=elapsed_ms,
        )

    def close(self) -> None:
        self._client.close()
