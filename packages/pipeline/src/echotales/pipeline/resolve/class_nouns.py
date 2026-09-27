"""Type capitalized class nouns as categories, not characters.

**The defect.** LOTM writes its Beyonder Sequence names like proper names:
"Seer", "Mystery Pryer", "Sleepless", "Corpse Collector". NER tags them as
characters, so the resolver minted a person for each, and they were offered to
voice and panel casting (LOTM product database, 2026-09-27). Non-negotiable 4
says a generic descriptor never enters the graph as an individual.

**The signal is how the text uses the name, not the name itself.** A proper
name is not pluralized and does not take an indefinite article; a class noun
does ("What abilities do Seers have?", "a Sleepless", "the Seer potion",
"Sequence 9 Beyonder"). An entity whose capitalized label is used that way in
at least `MIN_GENERIC` places, and in at least `MIN_GENERIC_SHARE` of all its
uses, is a category. Members of a coordinated list with a category ("choosing
Apprentice, Marauder, or Seer") share its type when they are rare themselves
(at most `MAX_LISTED_MENTIONS` mentions), since a list coordinates like with
like. On RI no entity qualifies; Bai Ning Bing, the nearest, has 2 generic-
looking uses out of 669.

**Declared item heads.** RI's Gu worms ("Flash Blink Gu", "Heaven Earth
Magnificent Sound Gu") are never pluralized or given an article, so usage
cannot show it; eight were people in the database of record. The novel's
`item_heads` in sources.toml name the category word, and a multi-word label
ending in one is an ITEM. Single-word labels are left alone, so a person
called only "Gu" is never retyped.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from echotales.core.enums import TargetKind
from echotales.core.store import Store

log = logging.getLogger(__name__)

MIN_GENERIC = 2
MIN_GENERIC_SHARE = 0.25
MAX_LISTED_MENTIONS = 5

_QUANTIFIER = r"(?:a|an|every|each|any|no|other|another|some|many|those|these)"
_CLASS_CONTEXT = r"(?:potion|formula|pathway|ingredients?)"


def _counts(label: str, text: str) -> tuple[int, int]:
    """(generic uses, all uses) of a capitalized label in the volume text."""
    lab = re.escape(label)
    bare = len(re.findall(rf"\b{lab}\b", text))
    plural = len(re.findall(rf"\b{lab}(?:s|es)\b", text))
    quantified = len(re.findall(rf"\b{_QUANTIFIER}\s+{lab}\b", text, re.IGNORECASE))
    context = len(re.findall(
        rf"\b{lab}(?:[’']s)?\s+{_CLASS_CONTEXT}\b|\b(?:formula|potion|pathway|Sequence\s+\d+)\s+"
        rf"(?:(?:of|for|the)\s+)*{lab}\b", text))
    return plural + quantified + context, bare + plural


def _item_heads(novel_id: str) -> tuple[str, ...]:
    from echotales.pipeline.ingest.sources import load_sources

    try:
        source = load_sources().get(novel_id)
    except (FileNotFoundError, OSError, ValueError):
        return ()
    return source.item_heads if source is not None else ()


def type_class_nouns(store: Store, novel_id: str, *, dry_run: bool = False,
                     item_heads: tuple[str, ...] | None = None) -> list[str]:
    """Re-type person entities used as class nouns (CATEGORY) or named with a
    declared item head (ITEM); returns their labels."""
    people = [e for e in store.all_selves(novel_id) if e.kind.is_person]
    if not people:
        return []
    heads = set(_item_heads(novel_id) if item_heads is None else item_heads)
    items = {e.id: e.canonical_label for e in people
             if len(words := e.canonical_label.split()) > 1 and words[-1] in heads}
    people = [e for e in people if e.id not in items]
    text = "\n".join(b.text for c in store.chapter_numbers(novel_id)
                     if (ch := store.get_chapter(novel_id, c)) for b in ch.blocks)
    mentions = Counter(m.target_id for m in store.get_mentions(novel_id) if m.target_id)
    found: dict[str, str] = {}
    for e in people:
        generic, total = _counts(e.canonical_label, text)
        if generic >= MIN_GENERIC and generic >= MIN_GENERIC_SHARE * total:
            found[e.id] = e.canonical_label
    if found:
        by_label = {e.canonical_label: e for e in people if e.id not in found}
        item = r"(?:the\s+)?[A-Z][\w’'-]*(?:\s+[A-Z][\w’'-]*)*"
        for m in re.finditer(rf"{item}(?:,\s+{item})+,?\s+(?:and|or)\s+{item}", text):
            members = [re.sub(r"^the\s+", "", x.strip()) for x in re.split(r",|\s+(?:and|or)\s+", m.group(0))]
            if not any(x in found.values() for x in members):
                continue
            for x in members:
                e = by_label.get(x)
                if e is not None and mentions[e.id] <= MAX_LISTED_MENTIONS:
                    found[e.id] = e.canonical_label
    if not dry_run:
        for sid in found:
            store.set_kind(sid, TargetKind.CATEGORY)
        for sid in items:
            store.set_kind(sid, TargetKind.ITEM)
    if found or items:
        log.info("typed as categories: %s; as items: %s",
                 ", ".join(sorted(found.values())) or "none", ", ".join(sorted(items.values())) or "none")
    return sorted([*found.values(), *items.values()])
