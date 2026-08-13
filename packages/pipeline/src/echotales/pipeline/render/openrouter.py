"""OpenRouter-hosted image generation.

**Why a hosted model at all, in a project that has been deliberately
local-only.** The local checkpoints (MeinaMix, then GuoFeng3) produce output
that is recognisably the right *genre* and unmistakably the wrong *quality*:
soft faces, muddy composition, and -- because a 512px SD1.5 panel has little
room for both -- either a character or a setting, rarely both in one legible
frame. Measured against the same prompt, a hosted model returns a figure on
a cliff edge with mist, distant peaks, correct robes and a glowing cicada in
frame together. That gap is not closeable by prompt engineering, and the
brief is a watchable video, not a purity test.

The cost argument that made local the default also inverts once panels are
per *beat* rather than per block: ~14 images a chapter at fractions of a
cent, instead of ~89. `render/beats.py` is what makes this affordable.

The local engines stay exactly where they are. This is one more
`PanelImageEngine`, selected by name, and `--image-engine manga` still works
offline with no key.

**Safety filtering is a first-class case here, not an edge case.** This
corpus is violent -- Reverend Insanity's first chapter is a massacre -- and
the hosted model refuses gore outright (`finish_reason: content_filter`,
verified on a blood-soaked prompt from RI ch1). A refused panel is retried
once with the violence abstracted rather than dropped, because a chapter
missing its climactic image is worse than one whose climax is implied.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

#: Explicit gore -> the same beat, implied. Applied only after a refusal:
#: the unsoftened prompt is always tried first, because "blood pooling
#: beneath him" is the actual image the chapter calls for and the model
#: does sometimes allow it in context.
_SOFTEN = (
    (r"\bblood[- ]?soaked\b", "battle-worn"),
    (r"\bblood pooling\b", "dark stains spreading"),
    (r"\bpool of blood\b", "dark stain"),
    (r"\bblood\b", "dark stains"),
    (r"\bgore\b", ""),
    (r"\bcorpses?\b", "fallen figures"),
    (r"\bdead bodies\b", "fallen figures"),
    (r"\bmutilated\b", "wounded"),
    (r"\bdisembowel\w*\b", "struck down"),
    (r"\bsevered\b", "broken"),
    (r"\bkilling\b", "defeating"),
    (r"\bkills?\b", "defeats"),
    (r"\bslaughter\w*\b", "battle"),
    (r"\bmassacre\b", "battle"),
)


def soften(prompt: str) -> str:
    """Abstract explicit violence while keeping the moment intact."""
    out = prompt
    for pattern, replacement in _SOFTEN:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()


def api_key() -> str:
    """The OpenRouter key, from the environment or a gitignored `.env`.

    Read at call time rather than import time so that merely importing this
    module never requires a key, and never captures a stale one.
    """
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    for candidate in (Path(".env"), Path.home() / ".env"):
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "OPENROUTER_API_KEY":
                    return value.strip()
    return ""


@dataclass(slots=True)
class OpenRouterImageEngine:
    """Hosted image generation through OpenRouter.

    Implements `PanelImageEngine`, so it drops into `render_panels`
    unchanged. Reference images are accepted and **ignored**: this model
    takes no IP-Adapter conditioning, and character consistency instead
    rests on the canonical appearance text
    (`persona/canon.py`) being repeated verbatim in every prompt the
    director writes. That is genuinely weaker than image conditioning and
    is the main thing given up by choosing this engine.
    """

    name: str = "openrouter"
    model_id: str = "google/gemini-2.5-flash-image"
    timeout: float = 120.0
    #: Retry the same panel with violence abstracted after a refusal.
    soften_on_refusal: bool = True

    def _request(self, prompt: str) -> tuple[bytes | None, str]:
        """`(png bytes, finish_reason)` for one prompt."""
        key = api_key()
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set; export it or put it in .env "
                "(which is gitignored), or use --image-engine manga to stay local"
            )

        body = json.dumps(
            {
                "model": self.model_id,
                "modalities": ["image", "text"],
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            _ENDPOINT,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if "error" in payload:
            raise RuntimeError(str(payload["error"])[:300])

        choice = payload["choices"][0]
        images = choice["message"].get("images") or []
        if not images:
            return None, str(choice.get("finish_reason", "no_image"))

        url = images[0]["image_url"]["url"]
        return base64.b64decode(url.split(",", 1)[1]), "stop"

    def generate(self, request: object) -> Path:
        prompt = request.prompt  # type: ignore[attr-defined]
        out_path: Path = request.out_path  # type: ignore[attr-defined]

        data, reason = self._request(prompt)
        if data is None and reason == "content_filter" and self.soften_on_refusal:
            log.warning(
                "%s refused (content filter); retrying with violence abstracted",
                out_path.name,
            )
            data, reason = self._request(soften(prompt))

        if data is None:
            raise RuntimeError(f"no image returned for {out_path.name} ({reason})")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path
