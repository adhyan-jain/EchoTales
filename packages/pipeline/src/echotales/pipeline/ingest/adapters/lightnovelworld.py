"""Adapter for lightnovelworld web-reader exports (Reverend Insanity).

Structure per chapter document::

    <div class="chapter type-1">
      <div class="chapter-title-wrap"><h2 class="chapter-title">Chapter N: …</h2></div>
      <div class="ugc chapter-ugc">
        <p><strong>Chapter N – …</strong></p>   <- the title, repeated
        <p>…</p>
      </div>
    </div>

Two quirks this adapter exists to absorb:

**Filenames are off by one.** Chapter 1 is ``page-0.html``. Chapter numbers
therefore come from the TOC label and never from the href.

**The title is repeated as a bold first paragraph.** Left in, it would be
detected as narration, tokenised, and fed to the mention detector -- so every
chapter whose title names a character (very common here) would manufacture a
spurious mention at offset 0 with no narrative context to resolve it against.
"""

from __future__ import annotations

import re

from echotales.pipeline.ingest.adapters.base import RawBlock, SourceAdapter
from lxml import etree

_TITLE_ECHO = re.compile(r"^\s*chapter\s*\d+(?:\.\d+)?\s*[:\-–—]", re.IGNORECASE)


class LightNovelWorldAdapter(SourceAdapter):
    name = "lightnovelworld"

    def content_root(self, tree: etree._Element) -> etree._Element:
        """Narrow to the body container so the title heading is excluded."""
        for xpath in (
            '//div[contains(@class, "chapter-ugc")]',
            '//div[contains(@class, "chapter")]',
        ):
            found = tree.xpath(xpath)
            if found:
                return found[0]
        return tree

    def should_skip_block(self, block: RawBlock, index: int) -> bool:
        """Drop the repeated title paragraph.

        Restricted to the first few blocks: a mid-chapter line that merely
        mentions another chapter should not be silently deleted.
        """
        return index < 2 and bool(_TITLE_ECHO.match(block.text))
