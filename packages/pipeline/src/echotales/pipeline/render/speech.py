"""Who says each line of a beat, and to whom, in words the art director can use.

Why (owner review of the 2026-11-19 RI ch1 sheet): the enemies' ultimatum panels all gave the lone hero a "cold mocking smile".
The director saw only narration, or a bare quote, so every line's emotion landed on the one character in CAST. The graph already
holds a speaker for every line (`Span.speaker_self_id`, what the voice stage reads); this carries it into direction so the
speaker's face carries the line and the others react.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from echotales.core.models import Span, SpanType

_HEAD = re.compile(r"^\W*([^,!?.:;]{1,40}?)\s*[,!]")


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", text.lower()) if len(t) > 2}


def _is_vocative_of(speaker: str, quote: str) -> bool:
    """The quote opens by calling the speaker by name ("Fang Yuan, hand it over!"). People do not address themselves, so the
    attribution is wrong; measured on RI ch1 block 0, which the graph gave to the very man being threatened."""
    m = _HEAD.match(quote)
    return bool(m and _tokens(speaker) & _tokens(m.group(1)))


def spoken_lines(
    spans: list[Span], blocks: list[int], *, label_of: Callable[[Span], str], cast: list[str],
    max_lines: int = 3, max_words: int = 14,
) -> str:
    """One bullet per quoted line of the beat: who says it, to whom, the opening words. "" when the beat has none.

    `label_of` returns the speaker's name or "" when unknown. A speaker outside `cast` is not named (the director may only name
    CAST): "someone else". The addressee is a cast member named inside the quote, else the one cast member who is not the
    speaker when only one is left."""
    wanted = set(blocks)
    out: list[str] = []
    for sp in sorted(spans, key=lambda s: (s.block_index, s.start)):
        if sp.block_index not in wanted or sp.span_type not in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE) or not sp.text.strip():
            continue
        quote = " ".join(sp.text.split())
        who = label_of(sp).strip()
        if who and sp.span_type is SpanType.DIALOGUE and _is_vocative_of(who, quote):
            who = ""
        in_cast = next((c for c in cast if c.lower() == who.lower()), "") if who else ""
        low = quote.lower()
        named = [c for c in cast if c != in_cast and c.lower() in low]
        others = [c for c in cast if c != in_cast]
        to = named[0] if named else (others[0] if len(others) == 1 and sp.span_type is SpanType.DIALOGUE else "")
        words = quote.split()
        short = " ".join(words[:max_words]) + (" ..." if len(words) > max_words else "")
        if sp.span_type is SpanType.INNER_MONOLOGUE:
            out.append(f'- {in_cast or "someone"} thinks, silently: {short}')
            continue
        speaker = in_cast or "someone who is not in CAST (draw them among the others, never as a CAST member)"
        out.append(f'- {speaker} says{f" to {to}" if to else ""}: {short}')
        if len(out) >= max_lines:
            break
    return "\n".join(out)
