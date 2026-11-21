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


def speaker_ids(
    spans: list[Span], blocks: list[int], *, lead: int, label_of: Callable[[Span], str],
) -> list[str]:
    """Self ids of the people who say a quoted line in these blocks: the lead block's speaker first, then in reading order.

    Why (P&P e2e 2026-11-22): the cast came from PRESENT mentions only, and the speaker of a line is not a mention, so "My dear
    Mr. Bennet" (said by his wife) was drawn as the husband, and the wife appeared in 6 of 32 panels. The same attribution
    guard as `spoken_lines` applies: a quote that opens by calling the speaker by name belongs to someone else, and a speaker
    `label_of` does not name (anonymous, unresolved, not a person) is not cast."""
    wanted = set(blocks)
    ordered = sorted(
        (s for s in spans if s.block_index in wanted and s.span_type is SpanType.DIALOGUE and s.text.strip() and s.speaker_self_id),
        key=lambda s: (s.block_index != lead, s.block_index, s.start),
    )
    out: list[str] = []
    for sp in ordered:
        who = label_of(sp).strip()
        if not who or _is_vocative_of(who, " ".join(sp.text.split())):
            continue
        if sp.speaker_self_id not in out:
            out.append(str(sp.speaker_self_id))
    return out
