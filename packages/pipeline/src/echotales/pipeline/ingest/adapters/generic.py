"""Fallback adapter for sources with no dedicated handler.

Applies only the base behaviour: walk the document body, extract blocks,
preserve emphasis, classify. Good enough to ingest an unfamiliar EPUB and see
what comes out, which is the intended first step when adding a novel -- run
this, inspect the blocks, then write a dedicated adapter for whatever it got
wrong.
"""

from __future__ import annotations

from echotales.pipeline.ingest.adapters.base import RawBlock, SourceAdapter
from lxml import etree


class GenericAdapter(SourceAdapter):
    name = "generic"

    def content_root(self, tree: etree._Element) -> etree._Element:
        body = tree.xpath("//body")
        return body[0] if body else tree

    def should_skip_block(self, block: RawBlock, index: int) -> bool:
        # A leading heading is nearly always the chapter title, which the TOC
        # label already supplies.
        return index == 0 and block.tag in {"h1", "h2", "h3"}
