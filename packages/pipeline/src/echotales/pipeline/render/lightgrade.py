"""Light and mood graded from the text, so a night room lit by a lamp is not drawn bright and evenly lit.

Why (round 3, LotM ch1, 2026-11-20): the staging sheet said "a study lit by a wall lamp" and the prompt said nothing of how
dark the scene is, so all 16 panels came out warm, even and bright while the reference anime grades the same scene low-key with
deep shadows. The model has no CFG (Z-Image Turbo), so strength comes only from saying the light plainly and early.

The words are a small vocabulary of light sources and times of day, not a parser: the first field that states any light wins
(the staging sheet's own "Light:" line before the director's lighting before the passage before the free-text paragraph, whose
invented "dimly lit room" contradicted a staged "bright lights" hall)."""

from __future__ import annotations

import re

_LOW = ("night", "midnight", "moonlit", "moonlight", "moonless", "darkness", "pitch black", "dimly", "dim light", "candle",
        "lamp", "lantern", "torch", "firelight", "gaslight")
_DUSK = ("dusk", "sunset", "sundown", "twilight", "dawn", "sunrise", "late afternoon", "golden hour", "evening")
_SOFT = ("rain", "drizzle", "overcast", "fog", "mist", "storm", "snow", "gloomy")
_DAY = ("daylight", "sunlight", "noon", "morning", "midday", "sunny", "afternoon", "hard sun", "sun ")
_BRIGHT = ("bright", "radiant", "radiat", "brilliant", "glory")

_SENTENCE = {
    "low": ("Low-key lighting: deep shadows swallow most of the frame, the subject lit only by the stated light source with a "
            "soft rim light, a dark moody cinematic grade, dim and never bright or evenly lit."),
    "dusk": "Golden-hour light: a low sun, long soft shadows, warm rim light on the subject and cooler shadows.",
    "soft": "Soft overcast light: diffuse, desaturated and cool, with atmospheric depth in the distance.",
    "day": "Natural daylight with clear soft shadows.",
    "bright": "Bright luminous light with a soft glow.",
}
_MOOD = (
    (("horror", "ominous", "eerie", "sinister", "dread", "uncanny", "menac"), "an ominous colour grade with deep red and sickly green accents"),
    (("grim", "somber", "sombre", "sad", "grief", "tragic", "hopeless"), "a muted cold blue-grey grade"),
)


def _hits(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(r"\b" + re.escape(w.strip()), text) for w in words)


def light_kind(text: str) -> str:
    """The light category a text states ("low", "dusk", "soft", "day", "bright") or "" when it states none."""
    return _kind(text)


def _kind(text: str) -> str:
    low = text.lower() + " "
    # A time of day outranks a source ("a lamp at dusk" is dusk); a low-key source outranks plain weather.
    for kind, words in (("low", _LOW), ("dusk", _DUSK), ("soft", _SOFT), ("day", _DAY), ("bright", _BRIGHT)):
        if _hits(low, words):
            return kind
    return ""


def light_grade(*fields: str, mood: str = "") -> str:
    """The grading sentence for the first field that states a light, plus a mood accent; "" when the text states none."""
    kind = ""
    for f in fields:
        # A staging sheet's own "Light:" clause is the statement; the rest of the sheet (Set:, Blocking:) comes later in priority.
        m = re.search(r"\bLight:\s*(.*?)(?=\s+(?:Set|Blocking):|\Z)", f, re.S)
        kind = _kind(m.group(1)) if m else ""
        if kind:
            break
    if not kind:
        for f in fields:
            kind = _kind(f)
            if kind:
                break
    out = _SENTENCE.get(kind, "")
    mood_l = (mood or "").lower()
    accent = next((a for words, a in _MOOD if any(w in mood_l for w in words)), "")
    if accent and out:
        out = out.rstrip(".") + f", {accent}."
    elif accent:
        out = f"Colour grade: {accent}."
    return out
