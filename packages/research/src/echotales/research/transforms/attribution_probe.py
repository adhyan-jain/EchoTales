"""Run the product's own speaker-attribution ladder on externally labelled
quotations.

The ladder (`pipeline/speakers/attribution.py::attribute_span`) has only ever
been checked against its own high-confidence output or an LLM spot check
(EVOLUTION 4.88: "a labelled speaker set ... does not exist"). PDNC supplies
human speaker labels, so this adapter rebuilds each PDNC quote as a product
`Span` with the same paragraph-bounded context the product sees, and records
the tier, the confidence constant it emits, and whether it was right.
Tier 4 (the contextual LLM) is deliberately excluded: it is network-bound,
covered 32 lines in the product, and its instability across runs (10/29 lines
changed) would make a calibration number unreproducible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.ingest.normalize import comparison_key
from echotales.pipeline.speakers.attribution import attribute_span
from echotales.research.datasets.pdnc import Novel, Quote

#: Context window either side of a quote, clipped at paragraph breaks. The
#: product attributes within a block (one paragraph of the source), so a wider
#: window would hand the ladder evidence it never gets in production.
CONTEXT_CHARS = 300


@dataclass(frozen=True, slots=True)
class ProbeResult:
    quote_id: str
    quote_type: str
    gold: str
    addressees: tuple[str, ...]
    predicted_raw: str | None
    predicted: str | None  # the unique PDNC main name the surface denotes, else None
    owners: tuple[str, ...]  # every character the predicted surface can denote
    method: str
    confidence: float
    resolved: bool
    correct: bool  # strict: surface denotes exactly the gold speaker
    correct_lenient: bool  # gold speaker is among the surface's owners
    addressee_capture: bool
    #: The predicted surface occurs inside the quote itself -- a vocative
    #: ("Fang Yuan, hand it over!"), the cue the product mistakes for a speaker.
    predicted_in_quote: bool
    gender_gold: str
    gender_pred: str


#: Capitalised words that are not names. PDNC's character lists include
#: descriptive "names" ("The Woman At Whose House She Was Dining"); without
#: this, their tokens turned a predicted pronoun "She" into that character.
_NOT_NAME_TOKENS = frozenset(
    "the a an she he her his him it they them i you we at of in on to and or but "
    "was were is be by for with from that this who whose whom which mr mrs miss "
    "sir lady lord dr st".split()
)

#: PDNC marks quotes whose speaker cannot be determined; they have no gold.
_NO_GOLD = frozenset({"unknowable", "_unknowable", "unknown", "nan", ""})


def alias_index(novel: Novel) -> dict[str, frozenset[str]]:
    """Surface key -> every character it can denote.

    A set, not a single owner: "John" names both John Beaver and John Andrew in
    A Handful of Dust, and the product only ever emits a surface name. Scoring
    reports both a strict reading (the surface must denote exactly the gold
    speaker) and a lenient one (the gold speaker is among its owners).
    """
    owners: dict[str, set[str]] = {}

    def add(key: str, name: str) -> None:
        if key:
            owners.setdefault(key, set()).add(name)

    for c in novel.characters.values():
        for form in (c.name, *c.aliases):
            add(form.lower(), c.name)
            add(comparison_key(form), c.name)
            for tok in form.replace(".", " ").split():
                if tok[:1].isupper() and len(tok) > 2 and tok.lower() not in _NOT_NAME_TOKENS:
                    add(tok.lower(), c.name)
    return {k: frozenset(v) for k, v in owners.items()}


def _clip(text: str, start: int, end: int) -> tuple[str, str]:
    lo = max(0, start - CONTEXT_CHARS)
    hi = min(len(text), end + CONTEXT_CHARS)
    pre = text[lo:start]
    post = text[end:hi]
    if "\n\n" in pre:
        pre = pre.rsplit("\n\n", 1)[1]
    if "\n\n" in post:
        post = post.split("\n\n", 1)[0]
    return pre, post


def probe(novel: Novel, quotes: list[Quote] | None = None) -> list[ProbeResult]:
    idx = alias_index(novel)
    names = {n for owners in idx.values() for n in owners}
    known = frozenset(set(idx) | {k.title() for k in idx} | names)
    out: list[ProbeResult] = []
    for q in quotes if quotes is not None else novel.quotes:
        if q.start < 0 or q.end <= q.start or q.speaker.strip().lower() in _NO_GOLD:
            continue
        pre, post = _clip(novel.text, q.start, q.end)
        span = Span(id=f"{novel.name}:{q.id}", novel_id=novel.name, chapter=1.0,
                    block_index=q.index, start=q.start, end=q.end,
                    span_type=SpanType.DIALOGUE, text=novel.text[q.start:q.end])
        a = attribute_span(span, preceding=pre, following=post, known_names=known)
        raw = a.speaker
        owners: frozenset[str] = frozenset()
        if raw:
            owners = idx.get(raw.lower()) or idx.get(comparison_key(raw)) or frozenset()
        mapped = next(iter(owners)) if len(owners) == 1 else None
        resolved = raw is not None
        correct = mapped == q.speaker
        lenient = q.speaker in owners
        out.append(ProbeResult(
            quote_id=q.id, quote_type=q.quote_type, gold=q.speaker,
            addressees=tuple(q.addressees), predicted_raw=raw, predicted=mapped,
            owners=tuple(sorted(owners)),
            method=a.method.value, confidence=float(a.confidence), resolved=resolved,
            correct=correct, correct_lenient=lenient,
            addressee_capture=bool(resolved and not lenient and owners
                                   and owners & set(q.addressees)),
            predicted_in_quote=bool(raw and re.search(rf"\b{re.escape(raw)}\b", q.text)),
            gender_gold=novel.gender_of(q.speaker),
            gender_pred=novel.gender_of(mapped) if mapped else "U",
        ))
    return out
