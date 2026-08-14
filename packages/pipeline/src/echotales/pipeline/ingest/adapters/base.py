"""Source adapter protocol and shared HTML walking.

Every source formats its EPUB differently, and those differences are exactly
what a general-purpose reader library would flatten away. An adapter's job is
to know one source's quirks -- which element holds the chapter body, whether
the title is repeated as a paragraph, which CSS class marks emphasis -- and to
hand back uniform `Block` objects.

Adding a novel is then a `data/sources.toml` entry naming an adapter, not a
code change.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.pipeline.ingest.classify import (
    ClassifiedBlock,
    classify_block,
    is_appendix_heading,
)
from echotales.pipeline.ingest.epub import Epub, TocEntry, parse_chapter_label
from lxml import etree
from lxml import html as lxml_html

#: Inline elements whose text is emphasised in the source. Preserved as
#: character ranges because emphasis is an independent inner-monologue signal
#: that survives only because ingestion is EPUB-based -- a PDF loses it.
EMPHASIS_TAGS = frozenset({"i", "em"})

#: Elements that separate scenes. Worth keeping: a scene break is free evidence
#: for Phase 2 segmentation, which otherwise has to infer boundaries from prose.
BREAK_TAGS = frozenset({"hr"})

BLOCK_TAGS = frozenset(
    {"p", "div", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"}
)

_WS = re.compile(r"\s+")


@dataclass(slots=True)
class RawBlock:
    """A block of text plus the structural evidence the markup carried."""

    text: str
    tag: str
    css_classes: tuple[str, ...] = ()
    italic_ranges: list[tuple[int, int]] = field(default_factory=list)
    is_break: bool = False


def _normalise_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def extract_block(
    element: etree._Element, *, italic_classes: frozenset[str] = frozenset()
) -> RawBlock:
    """Flatten one block element to text, recording emphasised character ranges.

    Offsets are computed against the *normalised* text so they stay valid
    against what actually gets stored. `italic_classes` catches emphasis some
    sources apply via a whole-block CSS class (e.g. calibre's auto-numbered
    `block_6`) rather than an inline `<i>`/`<em>` tag, which the tag check
    alone would miss entirely.
    """
    parts: list[str] = []
    italics: list[tuple[int, int]] = []

    def walk(node: etree._Element, emphasised: bool) -> None:
        tag = etree.QName(node).localname.lower() if node.tag is not etree.Comment else ""
        node_classes = (node.get("class") or "").split() if isinstance(node.tag, str) else ()
        here = (
            emphasised
            or tag in EMPHASIS_TAGS
            or any(c in italic_classes for c in node_classes)
        )

        if node.text:
            start = sum(len(p) for p in parts)
            parts.append(node.text)
            if here:
                italics.append((start, start + len(node.text)))

        for child in node:
            walk(child, here)
            if child.tail:
                start = sum(len(p) for p in parts)
                parts.append(child.tail)
                # A tail belongs to the parent's emphasis state, not the child's.
                if emphasised:
                    italics.append((start, start + len(child.tail)))

    walk(element, False)
    raw = "".join(parts)
    text = _normalise_ws(raw)

    # Re-map emphasis offsets onto the whitespace-normalised string. Doing this
    # by re-walking is simpler and less error-prone than tracking a shifting
    # delta through the walk above.
    mapped: list[tuple[int, int]] = []
    if italics and text:
        for start, end in italics:
            fragment = _normalise_ws(raw[start:end])
            if not fragment:
                continue
            idx = text.find(fragment)
            if idx >= 0:
                mapped.append((idx, idx + len(fragment)))

    tag_name = etree.QName(element).localname.lower()
    classes = tuple((element.get("class") or "").split())
    return RawBlock(
        text=text,
        tag=tag_name,
        css_classes=classes,
        italic_ranges=_merge_ranges(mapped),
        is_break=tag_name in BREAK_TAGS,
    )


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    ordered = sorted(ranges)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def iter_block_elements(root: etree._Element) -> Iterator[etree._Element]:
    """Yield leaf-ish block elements in document order.

    A container that holds other block elements is skipped in favour of its
    children, so a wrapper `<div>` does not swallow the paragraphs inside it.
    """
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = etree.QName(element).localname.lower()
        if tag in BREAK_TAGS:
            yield element
            continue
        if tag not in BLOCK_TAGS:
            continue
        if any(
            isinstance(child.tag, str)
            and etree.QName(child).localname.lower() in BLOCK_TAGS
            for child in element.iter()
            if child is not element
        ):
            continue
        yield element


class SourceAdapter:
    """Turns one source's EPUB into `Chapter` objects.

    Not an ABC: every hook has a working default, so the base class alone
    ingests a generic EPUB. Subclasses override only the quirks of their
    source, which is what keeps adding a novel a config change.
    """

    #: Name used in data/sources.toml.
    name: str = "generic"

    def __init__(self, epub: Epub, novel_id: str) -> None:
        self.epub = epub
        self.novel_id = novel_id

    # ---- hooks ---------------------------------------------------------

    def content_root(self, tree: etree._Element) -> etree._Element:
        """Element containing the chapter body. Defaults to the whole document."""
        return tree

    def should_skip_block(self, block: RawBlock, index: int) -> bool:
        """Per-source suppression of redundant markup."""
        return False

    # ---- chapter enumeration -----------------------------------------------

    def toc_entries(self) -> list[TocEntry]:
        return self.epub.toc()

    def chapters(self, wanted: ChapterRange | None = None) -> Iterator[Chapter]:
        """Stream chapters, optionally limited to a numeric range.

        Chapter numbers come from the TOC label, never the filename.
        """
        in_appendix = False
        seen_a_chapter = False
        for entry in self.toc_entries():
            parsed = parse_chapter_label(entry.label)

            if parsed.number is None:
                # Back matter latches only *after* the first real chapter.
                # Several of these headings ("Table of Contents", "Copyright",
                # "Front Cover") also appear as front matter, and latching on
                # those would skip the entire novel.
                if seen_a_chapter and is_appendix_heading(entry.label):
                    in_appendix = True
                continue

            # Once in back matter, stop. The publisher volume ends with
            # Pathways/Characters/Locations, which describe end-of-volume
            # state and would leak knowledge the reader does not hold at any
            # point inside the story.
            if in_appendix:
                continue
            seen_a_chapter = True

            if wanted is not None and parsed.number not in wanted:
                continue

            chapter = self.parse_chapter(entry, parsed.number, parsed.title)
            if chapter is not None:
                yield chapter

    def parse_chapter(self, entry: TocEntry, number: float, title: str) -> Chapter | None:
        try:
            raw = self.epub.read(entry.path)
        except KeyError:
            return None

        tree = lxml_html.fromstring(raw)
        root = self.content_root(tree)
        blocks: list[Block] = []

        italic_classes = self.epub.italic_classes()
        # Once a translator's/author's note starts, every remaining block in
        # the chapter is back matter too -- `classify_block` only recognises
        # the *labelled* block ("TL Note:"), and its own continuation
        # paragraphs and footnotes carry no such marker, so without this they
        # were re-entering the story as ordinary PROSE and picking up
        # resolved speakers and mentions from meta-text. In this corpus a
        # translator's note is always chapter-terminal, so latching to the
        # end of the chapter (rather than un-latching at the next `* * *`)
        # is the correct, not merely convenient, boundary -- a footnote can
        # sit on the far side of a second separator from the note label
        # itself and is still back matter.
        in_note = False
        for element in iter_block_elements(root):
            raw_block = extract_block(element, italic_classes=italic_classes)
            if raw_block.is_break:
                # Scene break: zero-width marker that Phase 2 can key on.
                blocks.append(
                    Block(index=len(blocks), block_type=BlockType.NON_DIEGETIC, text="* * *")
                )
                continue
            if not raw_block.text:
                continue
            if self.should_skip_block(raw_block, len(blocks)):
                continue

            if in_note:
                classified = ClassifiedBlock(BlockType.TRANSLATOR_NOTE, raw_block.text.strip(), {})
            else:
                classified = classify_block(
                    raw_block.text,
                    tag=raw_block.tag,
                    css_classes=raw_block.css_classes,
                )
                if classified.block_type in (BlockType.TRANSLATOR_NOTE, BlockType.AUTHOR_NOTE):
                    in_note = True
            blocks.append(
                Block(
                    index=len(blocks),
                    block_type=classified.block_type,
                    text=classified.text,
                    italic_ranges=raw_block.italic_ranges,
                    system_fields=classified.system_fields,
                )
            )

        if not blocks:
            return None
        return Chapter(
            novel_id=self.novel_id,
            number=number,
            title=title,
            source_href=entry.path,
            blocks=blocks,
        )


@dataclass(frozen=True, slots=True)
class ChapterRange:
    """An inclusive chapter range, e.g. ``1-199``.

    Inclusive at both ends because that is how a reader states it, and
    float-valued so split chapters land naturally: 45.1 falls inside ``1-199``
    without needing a special case.
    """

    start: float
    end: float

    def __contains__(self, number: object) -> bool:
        if not isinstance(number, int | float):
            return False
        return self.start <= float(number) <= self.end

    @classmethod
    def parse(cls, spec: str) -> ChapterRange:
        """Parse ``"1-199"``, ``"1"``, or ``"5-"``."""
        text = spec.strip()
        if "-" not in text:
            value = float(text)
            return cls(value, value)
        lo, _, hi = text.partition("-")
        return cls(
            float(lo) if lo.strip() else float("-inf"),
            float(hi) if hi.strip() else float("inf"),
        )

    def __str__(self) -> str:
        return f"{self.start:g}-{self.end:g}"
