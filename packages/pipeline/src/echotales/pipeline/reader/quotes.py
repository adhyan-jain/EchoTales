"""Quoted-utterance addressing shared by the reader pass and the reader-gold scorer.

A quoted line is addressed as `block.q`: the block index and the ordinal of the quote inside that block. The reader
tags each one in the passage it shows the model, and `eval/reader_gold.py` looks the same keys up, so the pattern has to
be a single definition -- two copies would disagree on a multi-paragraph quote and silently shift every `q` after it.
"""

from __future__ import annotations

import re

# A quote runs to its closing mark or, when the paragraph ends first, to the end of the block: multi-paragraph
# speech opens a quote in every paragraph and closes only in the last (LotM ch7 blocks 10, 26, 27).
# ORV is set in straight quotes, LotM and RI in curly ones (ORV ch2 had zero curly matches).
QUOTE = re.compile(r"“[^”]*(?:”|$)|\"[^\"]*(?:\"|$)")


def quote_starts(text: str) -> list[int]:
    """Character offset of each quote's opening mark, in order."""
    return [m.start() for m in QUOTE.finditer(text)]


def tag_block(index: int, text: str) -> str:
    """The block's text with `[index.q]` inserted before every quote's opening mark."""
    counter = iter(range(10_000))
    return QUOTE.sub(lambda m: f"[{index}.{next(counter)}]{m.group(0)}", text)
