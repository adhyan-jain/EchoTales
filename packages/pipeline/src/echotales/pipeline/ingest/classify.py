"""Block-level content classification (plans.md Section 6 Phase 0).

Every block of a chapter is sorted into one of the `BlockType` categories
before any identity processing happens. Two of these carry most of the value:

``NON_DIEGETIC`` -- navigation, ads, "read the next chapter at ...", and (for
the LOTM volume) the publisher's Pathways/Characters/Locations appendices. All
of it is archived but excluded from identity processing. The appendices matter
especially: they describe *end-of-volume* state, so letting them into the graph
would hand the reader knowledge they do not have yet and quietly defeat the
knowledge-time model.

``SYSTEM_WINDOW`` -- stat blocks and status screens, parsed into structured
key-value pairs rather than treated as prose. plans.md calls this the
highest-precision attribute source in the novel, which it is: "Level: 7" is
unambiguous in a way that a sentence describing someone's level never is.

Classification is deterministic and conservative. A block that does not clearly
match a special category stays `PROSE`, because a false `NON_DIEGETIC` silently
deletes story content while a missed one costs a little noise downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from echotales.core.enums import BlockType

# --- non-diegetic -----------------------------------------------------------

_NON_DIEGETIC_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*(?:read|continue reading)\b.*\b(?:at|on)\b.*\.(?:com|net|org|me|co)\b",
        r"\b(?:visit|check out|find us at)\b.*\.(?:com|net|org)\b",
        r"^\s*(?:previous|next)\s+chapter\s*$",
        r"^\s*(?:table of )?contents\s*$",
        r"^\s*advertisement\s*$",
        r"^\s*(?:please )?(?:support|donate|patreon|ko-?fi)\b",
        r"^\s*join (?:our|the) discord\b",
        r"^\s*translat(?:or|ed) by\b.*\bedit(?:or|ed) by\b",
        r"^\s*copyright\b|\ball rights reserved\b",
        r"^\s*isbn\b",
    )
]

# Publisher appendices in the official volume release. They are legitimate
# content, just not narration -- and crucially not knowledge the reader holds
# at any point *inside* the story.
_APPENDIX_HEADINGS = frozenset(
    {
        "pathways guide",
        "image gallery",
        "characters",
        "locations",
        "map of the lord of the mysteries world",
        "back cover",
        "front cover",
        "full cover",
        "copyright",
        "synopsis",
        "table of contents",
        "to be continued in...",
        "end of volume 1",
    }
)

# --- notes ------------------------------------------------------------------

_AUTHOR_NOTE = re.compile(
    r"^\s*(?:author'?s?\s+(?:note|words|thoughts)|a/?n\s*[:\-]|afterword|postscript)\b",
    re.IGNORECASE,
)

_TRANSLATOR_NOTE = re.compile(
    r"^\s*(?:translator'?s?\s+note|tl\s*note|t/?n\s*[:\-]|editor'?s?\s+note|"
    r"note\s*[:\-]\s*(?=.*\btranslat))",
    re.IGNORECASE,
)

# --- system windows ---------------------------------------------------------

# A bracketed block whose interior is mostly `Key: Value` lines. Common in
# Korean system/LitRPG fiction; rare-to-absent in the two Chinese sources, but
# the ORV volume will lean on it heavily.
_SYSTEM_DELIMITERS = (("[", "]"), ("【", "】"), ("<", ">"), ("《", "》"))

_KV_LINE = re.compile(r"^\s*[-*+•]?\s*(?P<key>[\w \t'/()-]{1,40}?)\s*[:：]\s*(?P<value>.+?)\s*$")

_SYSTEM_KEYWORDS = re.compile(
    r"\b(?:status|window|system|quest|skill|attribute|stat|notification|"
    r"achievement|level up|ding|alert)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ClassifiedBlock:
    block_type: BlockType
    text: str
    system_fields: dict[str, str]


def _looks_bracketed(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(o) and stripped.endswith(c) for o, c in _SYSTEM_DELIMITERS)


def parse_system_window(text: str) -> dict[str, str]:
    """Extract `Key: Value` pairs from a system-window block.

    Returns empty when the block does not actually carry structured fields, so
    the caller can decline to classify it as a system window. Being strict here
    is the point -- misreading dialogue as a stat block would inject fabricated
    attributes at the highest confidence tier in the pipeline.
    """
    body = text.strip()
    for open_ch, close_ch in _SYSTEM_DELIMITERS:
        if body.startswith(open_ch) and body.endswith(close_ch):
            body = body[len(open_ch) : -len(close_ch)].strip()
            break

    fields: dict[str, str] = {}
    lines = [ln for ln in body.splitlines() if ln.strip()]
    for line in lines:
        match = _KV_LINE.match(line)
        if match:
            key = match.group("key").strip()
            value = match.group("value").strip()
            if key and value:
                fields[key] = value
    return fields


def is_system_window(text: str, *, min_fields: int = 2) -> bool:
    """Whether a block is a status screen rather than prose.

    Requires either an explicit system keyword or a bracketed block, *and*
    enough key-value lines to be structured. A single "Name: Klein" line inside
    ordinary prose is not a status screen.
    """
    if not (_looks_bracketed(text) or _SYSTEM_KEYWORDS.search(text)):
        return False
    fields = parse_system_window(text)
    if len(fields) >= min_fields:
        return True
    # A short bracketed line with one field still counts when it is clearly
    # a notification rather than a sentence.
    return bool(fields) and _looks_bracketed(text) and len(text) < 200


def classify_block(
    text: str,
    *,
    tag: str = "p",
    css_classes: tuple[str, ...] = (),
    is_heading: bool = False,
) -> ClassifiedBlock:
    """Assign a `BlockType` to one block of extracted text.

    `tag` and `css_classes` come from the source markup and let adapters pass
    structural evidence that plain text cannot carry.
    """
    stripped = text.strip()
    if not stripped:
        return ClassifiedBlock(BlockType.NON_DIEGETIC, text, {})

    if is_heading or tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        if stripped.casefold() in _APPENDIX_HEADINGS:
            return ClassifiedBlock(BlockType.NON_DIEGETIC, stripped, {})
        return ClassifiedBlock(BlockType.HEADING, stripped, {})

    for pattern in _NON_DIEGETIC_PATTERNS:
        if pattern.search(stripped):
            return ClassifiedBlock(BlockType.NON_DIEGETIC, stripped, {})

    if _TRANSLATOR_NOTE.match(stripped):
        return ClassifiedBlock(BlockType.TRANSLATOR_NOTE, stripped, {})

    if _AUTHOR_NOTE.match(stripped):
        return ClassifiedBlock(BlockType.AUTHOR_NOTE, stripped, {})

    if is_system_window(stripped):
        return ClassifiedBlock(
            BlockType.SYSTEM_WINDOW, stripped, parse_system_window(stripped)
        )

    # DIALOGUE vs PROSE is decided at span level in Phase 1, not here: a
    # paragraph routinely mixes a spoken line with its narration, and
    # committing to one label for the whole block would lose that.
    return ClassifiedBlock(BlockType.PROSE, stripped, {})


def is_appendix_heading(text: str) -> bool:
    """Whether a heading marks the start of publisher back-matter."""
    return text.strip().casefold() in _APPENDIX_HEADINGS
