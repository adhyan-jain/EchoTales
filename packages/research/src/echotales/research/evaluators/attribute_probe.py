"""Automatic attribute probes and holistic judges for rendered panels.

Two independent probes, so "the generator rendered attribute X" is never
decided by only the model that is later graded as a judge:

- **CLIP zero-shot** (openai/clip-vit-large-patch14 -- the encoder SDXL
  conditions on, i.e. the generator's own space, the circular case
  CLIPScore already is in `scripts/eval/clip_score.py`);
- **llava:7b through ollama** (a local VLM with independent weights),
  asked constrained questions.

Holistic judges (what evaluation pipelines actually use): CLIPScore against
the intended description, and llava's 1-10 "does this match" rating.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.request
from pathlib import Path

OLLAMA = "http://localhost:11434/api/generate"

_CLIP = None


def _clip():
    global _CLIP
    if _CLIP is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        dev = "cuda" if torch.cuda.is_available() else "cpu"
        m = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(dev).eval()
        p = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
        _CLIP = (m, p, dev)
    return _CLIP


def clip_release() -> None:
    """Free CLIP before ollama loads llava onto the same card."""
    global _CLIP
    _CLIP = None
    import gc

    gc.collect()
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass


def clip_probs(image: Path, texts: list[str]) -> list[float]:
    import torch
    from PIL import Image

    m, p, dev = _clip()
    inp = p(text=texts, images=Image.open(image).convert("RGB"), return_tensors="pt", padding=True)
    with torch.inference_mode():
        out = m(**{k: v.to(dev) for k, v in inp.items()})
    return [float(x) for x in out.logits_per_image.softmax(dim=-1)[0].cpu()]


def clip_score(image: Path, text: str) -> float:
    import torch
    from PIL import Image

    m, p, dev = _clip()
    inp = p(text=[text], images=Image.open(image).convert("RGB"), return_tensors="pt",
            padding=True, truncation=True)
    # Full forward, not get_image_features: in transformers 5 that returns a
    # BaseModelOutputWithPooling, not a tensor (crashed H-JUDGE-V, 2026-10-03).
    with torch.inference_mode():
        out = m(**{k: v.to(dev) for k, v in inp.items()})
    ie = out.image_embeds / out.image_embeds.norm(dim=-1, keepdim=True)
    te = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
    return float((ie @ te.T)[0, 0])


CLIP_PROMPTS = {
    "gender": {"F": "an anime illustration of a woman", "M": "an anime illustration of a man"},
    "hair": {"black": "an anime illustration of a person with black hair",
             "blonde": "an anime illustration of a person with blonde hair"},
}


def clip_attributes(image: Path, settings: tuple[str, ...]) -> dict[str, dict[str, float]]:
    out = {}
    for attr, opts in CLIP_PROMPTS.items():
        keys = sorted(opts)
        out[attr] = dict(zip(keys, clip_probs(image, [opts[k] for k in keys])))
    out["setting"] = dict(zip(settings, clip_probs(image, [f"an anime illustration {s}" for s in settings])))
    return out


def _llava(image: Path, prompt: str, model: str = "llava:7b") -> str:
    # keep_alive 30s, not ollama's 5-minute default: a probe left resident
    # made the next experiment's free-GPU guard refuse to render (2026-10-03).
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "keep_alive": "30s",
                       "images": [base64.b64encode(image.read_bytes()).decode()],
                       "options": {"temperature": 0, "seed": 0, "num_predict": 12}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["response"].strip()


def llava_attributes(image: Path, settings: tuple[str, ...]) -> dict:
    # Forced choice. The first version offered "unknown" and llava took it on
    # 85% of *committed* panels (H-VRUNG run 1, 2026-10-03) -- an instrument
    # failure, not a property of the images. Abstention is now read from
    # the separate person-visible question instead.
    g = _llava(image, "Look at the main figure in this image. Is it a man or a woman? "
                      "Answer with exactly one word: man or woman.").lower()
    # Open question for hair: the forced "black or blonde" choice answered
    # "black" for 7/8 blonde figures (option-order bias); the open colour
    # word scored 15/16 on committed panels with a visible person.
    h = _llava(image, "What colour is the main figure's hair? Answer with one colour word.").lower()
    p = _llava(image, "Is there a person visible in this image? Answer yes or no.").lower()
    opts = "; ".join(f"{i + 1}) {s}" for i, s in enumerate(settings))
    s = _llava(image, f"Where does this scene take place? Options: {opts}. Answer with the number only.")
    m = re.search(r"\d+", s)
    si = int(m.group()) - 1 if m else -1
    gender = "F" if ("woman" in g or "female" in g) else ("M" if re.search(r"\bman\b|\bmale\b", g) else None)
    return {
        "gender": gender,
        "hair": ("blonde" if re.search(r"blond|yellow|gold|light|white|silver|fair", h)
                 else "black" if re.search(r"black|dark|brown", h) else None),
        "person": "yes" in p,
        "setting": settings[si] if 0 <= si < len(settings) else None,
    }


def llava_match(image: Path, description: str) -> float:
    r = _llava(image, f"Description: \"{description}\"\nHow well does the image match the "
                      "description in every detail, including the person's gender, hair colour "
                      "and the place? Answer with a single integer from 1 (not at all) to 10 "
                      "(perfectly).")
    m = re.search(r"\d+", r)
    return float(m.group()) if m else float("nan")


def llava_unload(model: str = "llava:7b") -> None:
    """Release llava's VRAM now (keep_alive 0) so a following GPU job's
    free-GPU guard sees an empty card."""
    body = json.dumps({"model": model, "keep_alive": 0}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:
        pass
