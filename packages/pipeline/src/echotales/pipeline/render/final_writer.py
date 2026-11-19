"""Stage two of the two-stage director: a prompt-writing model polishes the grounded facts into the final paragraph.

Stage one (a general model) states facts and the scene staging, grounded in the text. Stage two (Z-Image-Engineer, a Qwen3-4B
fine-tuned to write Z-Image Turbo prompts) may only rephrase and add camera, lens and light. It was built for creative
expansion, so it invents: the validators below reject any person, name or object that the facts do not contain, and the
caller falls back to the facts themselves.
"""

from __future__ import annotations

import re
from collections.abc import Callable

#: Common people and props a prompt writer adds for atmosphere. Closed on purpose: it names what an invention looks like in
#: this genre of scene; anything it does not list is not judged, so a miss is silent and a false reject is impossible.
_INVENTABLE = (
    "girl boy child children woman women man men elder monk soldier guard servant maiden beggar dog cat horse crane bird "
    "dragon sword spear banner flag lantern lamp torch pavilion temple pagoda gate bridge boat tower palace throne altar "
    "fountain statue candle scroll book bow arrow shield armor fire flame lightning petal blossom cherry"
).split()
_NAME = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


def validate_final(paragraph: str, facts: str, *, cast: list[str]) -> list[str]:
    facts_l = facts.lower()
    facts_words = {_stem(w) for w in re.findall(r"[a-z]+", facts_l)}
    rejects: list[str] = []
    allowed = {n.lower() for n in cast}
    for m in _NAME.finditer(paragraph):
        if m.group(0).lower() not in allowed and m.group(0).lower() not in facts_l:
            rejects.append(f"name not in facts: {m.group(0)}")
    for w in re.findall(r"[a-z]+", paragraph.lower()):
        if _stem(w) in {_stem(x) for x in _INVENTABLE} and _stem(w) not in facts_words:
            rejects.append(f"object or person not in facts: {w}")
    return sorted(set(rejects))


def ollama_chat(model: str, seed: str, *, host: str = "http://localhost:11434", timeout: float = 120.0) -> str:
    import httpx

    r = httpx.post(f"{host}/api/chat", timeout=timeout, json={
        "model": model, "stream": False, "keep_alive": 0,
        "messages": [{"role": "user", "content": seed}], "options": {"temperature": 0.5, "num_ctx": 2048},
    })
    r.raise_for_status()
    return str(r.json()["message"]["content"]).strip()


def write_final(
    facts: str, *, cast: list[str], model: str = "z-engineer", chat: Callable[[str, str], str] | None = None,
    words: int = 120,
) -> tuple[str, list[str]]:
    """The polished paragraph, or `facts` itself when two attempts both fail validation. Returns (text, rejects of the last try)."""
    chat = chat or ollama_chat
    seed = (f"{facts}\n\nKeep every person, object, count, side of the frame and expression exactly as written and add nothing "
            f"new. Write about {words} words.")
    rejects: list[str] = []
    for _ in range(2):
        try:
            out = chat(model, seed)
        except Exception as exc:  # the model being unreachable is not a failed panel
            return facts, [f"writer unavailable: {exc}"]
        rejects = validate_final(out, facts, cast=cast)
        if not rejects:
            return out, []
        seed += "\nYour previous version added: " + "; ".join(rejects) + ". Remove them."
    return facts, rejects
