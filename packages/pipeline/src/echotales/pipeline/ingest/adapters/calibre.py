"""Adapter for calibre-produced EPUBs (Lord of the Mysteries, official volume).

Structure per chapter document::

    <h1 class="block_">Chapter N: Title</h1>
    <p class="block_7">narration…</p>
    <p class="block_7"><i class="calibre6">inner thought…</i> narration…</p>

The italics are the reason this source is worth more than its page count
suggests. plans.md Section 6 Phase 1 detects `INNER_MONOLOGUE` from attribution verbs
("thought", "said in his heart"), which is a recall-limited heuristic. Here the
translator has already marked those spans structurally, giving a second,
independent signal -- and a labelled slice usable for measuring how well the
verb heuristic actually does on sources that lack the markup.

The base class handles emphasis extraction; this adapter only narrows the
content root and drops the heading, since the chapter title is already carried
by the TOC label.
"""

from __future__ import annotations

from echotales.pipeline.ingest.adapters.base import RawBlock, SourceAdapter
from lxml import etree


class CalibreAdapter(SourceAdapter):
    name = "calibre"

    def content_root(self, tree: etree._Element) -> etree._Element:
        body = tree.xpath("//body")
        return body[0] if body else tree

    def should_skip_block(self, block: RawBlock, index: int) -> bool:
        # The <h1> duplicates the TOC label. Keeping it would put the chapter
        # title into the narration stream, where a title naming a character
        # manufactures a context-free mention at offset 0.
        return block.tag in {"h1", "h2"} and index == 0
