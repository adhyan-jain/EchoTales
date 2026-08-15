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

import json
import os
import re
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

_MD_LINE = re.compile(
    r"^\s*(?:[-*]|\d+[.)])\s*\*{0,2}`?(?P<key>[A-Za-z_][\w ]*)`?\*{0,2}\s*:\s*(?P<value>.+?)\s*$"
)


def _markdown_to_json(text: str) -> str:
    """Best-effort recovery when a provider answers in a markdown list
    instead of JSON despite being told not to (e.g. "*   `shot`: \"wide\"").

    Not a general markdown parser -- just enough structure to catch the one
    failure mode actually observed against this gateway under load. A line
    that doesn't match is silently skipped; a response that yields no
    fields at all still fails downstream in `parse_into`, exactly as if
    this function didn't exist, so this can only help, never make a
    parseable response worse.
    """
    fields: dict[str, object] = {}
    for line in text.splitlines():
        match = _MD_LINE.match(line)
        if not match:
            continue
        key = match.group("key").strip().lower().replace(" ", "_")
        raw = match.group("value").strip().rstrip(",")
        quoted = re.findall(r'"([^"]*)"', raw)
        if raw.startswith("[") or len(quoted) > 1:
            fields[key] = quoted
        elif quoted:
            fields[key] = quoted[0]
        else:
            fields[key] = raw.strip('"')
    return json.dumps(fields)


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
            # `json_schema` constrains decoding directly on providers that
            # honour it -- strictly better than `json_object`, which only
            # promises *some* JSON object, not one matching this shape.
            # `strict: False`: the gateway fans this out across providers
            # with uneven support for OpenAI's strict-mode schema rules
            # (no defaults, additionalProperties: false, every property
            # required) -- asking for strict on a provider that can't do it
            # risks an outright rejection instead of a degraded-but-usable
            # answer. `schema_instructions` in the prompt plus the retry/
            # salvage path in this method are what carry the requirement
            # the rest of the way on a provider that ignores this field
            # entirely, which is the behaviour actually observed.
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": False,
                },
            },
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
        attempts = 4
        for attempt in range(attempts):
            try:
                resp = self._client.post(
                    f"{self.host}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                try:
                    value = parse_into(schema, content)
                except LLMParseError:
                    # Last resort before giving up on this attempt: some
                    # providers the gateway can land on answer in a
                    # markdown bullet/numbered list instead of JSON despite
                    # being told not to ("*   `shot`: \"wide\""). Salvage
                    # what a real JSON parse would have gotten anyway
                    # rather than discard a perfectly good answer just
                    # because of its punctuation.
                    value = parse_into(schema, _markdown_to_json(content))
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
                f"gateway request failed after {attempts} attempts: {last_exc}"
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
