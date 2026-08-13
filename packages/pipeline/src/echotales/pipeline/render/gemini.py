"""Image generation through Google AI Studio's Gemini API.

**Why this exists alongside `openrouter.py`.** OpenRouter has no free image
model at all -- every image-output model there is priced per image, and a
free-tier key returns `HTTP 402` the moment its grace runs out (measured:
two images, then payment required). Google AI Studio bills the *same* model
family against a genuinely free daily quota, so the quality that made the
hosted path worth having is reachable without a card.

Same `PanelImageEngine` contract as every other backend, so it is one more
`--image-engine` value and changes nothing else.

**The safety filter is the binding constraint here, not the quota.** This
corpus is violent, and Gemini refuses gore: a blood-soaked Reverend Insanity
chapter-1 prompt comes back with no image and a `PROHIBITED_CONTENT` /
`IMAGE_SAFETY` finish reason. `openrouter.soften` is reused verbatim for the
retry rather than reimplemented -- it is the same problem with the same
answer, and one copy means one place to improve the wording.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from echotales.pipeline.render.openrouter import soften

log = logging.getLogger(__name__)

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

#: Finish reasons that mean "refused", as opposed to "failed". Only these
#: are worth a softened retry; anything else is a real error and is raised.
_REFUSALS = {"PROHIBITED_CONTENT", "IMAGE_SAFETY", "SAFETY", "BLOCKLIST"}


def api_key() -> str:
    """The Gemini key, from the environment or a gitignored `.env`.

    Accepts either `GEMINI_API_KEY` or `GOOGLE_API_KEY`, since AI Studio
    hands out the same credential under both names depending on where it is
    copied from, and having a key rejected for its variable name is a
    pointless way to lose ten minutes.
    """
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    for candidate in (Path(".env"), Path.home() / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                return value.strip()
    return ""


@dataclass(slots=True)
class GeminiImageEngine:
    """Gemini image generation, free-tier friendly.

    Reference images are accepted and ignored, exactly as in
    `OpenRouterImageEngine`: there is no IP-Adapter equivalent here, so
    character consistency rests entirely on the canonical appearance text
    (`persona/canon.py`) being restated in every prompt the director writes.
    That is the real cost of choosing a hosted engine over the local one.
    """

    name: str = "gemini"
    model_id: str = "gemini-2.5-flash-image"
    timeout: float = 120.0
    soften_on_refusal: bool = True

    def _request(self, prompt: str) -> tuple[bytes | None, str]:
        key = api_key()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set; put it in .env (gitignored) or "
                "export it, or use --image-engine manga to stay local"
            )

        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
        request = urllib.request.Request(
            _ENDPOINT.format(model=self.model_id),
            data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        candidates = payload.get("candidates") or []
        if not candidates:
            blocked = (payload.get("promptFeedback") or {}).get("blockReason")
            return None, str(blocked or "no_candidates")

        candidate = candidates[0]
        for part in (candidate.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"]), "ok"

        return None, str(candidate.get("finishReason", "no_image"))

    def generate(self, request: object) -> Path:
        prompt = request.prompt  # type: ignore[attr-defined]
        out_path: Path = request.out_path  # type: ignore[attr-defined]

        data, reason = self._request(prompt)
        if data is None and self.soften_on_refusal and reason.upper() in _REFUSALS:
            log.warning(
                "%s refused (%s); retrying with violence abstracted",
                out_path.name,
                reason,
            )
            data, reason = self._request(soften(prompt))

        if data is None:
            raise RuntimeError(f"no image returned for {out_path.name} ({reason})")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path
