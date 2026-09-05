"""Legacy `self_entity.kind` backfill (HANDOFF/EVOLUTION 4.54).

`GlobalResolver._entity_kind` (this package's `runner.py`) types every
*newly created* entity from its founding mentions' `Mention.entity_label`,
wired since commit a17ea32 ("type non-person entities so they stop
behaving like characters"). That logic is real and already runs on every
`resolve_novel` call for entities minted from here on.

The gap it does not close: `entity_label` is written only by the Layer-1
per-mention NER pass in `mentions/runner.py`, and it is `NULL` for every
mention in any database whose mentions stage last ran before that pass
existed (verified directly: `data/webview-working/reverend-insanity.db`
has 9568/9568 mentions with `entity_label IS NULL`, despite 9469 of them
being `method=SCORED` -- i.e. exactly the rows that pass is supposed to
label). `Store.get_self()` reads a `NULL` `kind` back as `TargetKind.SELF`
for backward compatibility, which is precisely how "Qing Mao Mountain" (a
LOCATION) and "South Border" (a LOCATION) ended up in the voice/panel cast
as if they were people.

Reprocessing those novels from raw text just to regenerate `entity_label`
would mean a full NER re-run over the whole corpus -- out of scope for a
backfill, and exactly the "full production re-run" this change is not
supposed to trigger. Instead this reuses the **on-disk chapter-level NER
cache** that every real (non-stub) mentions run already writes to
`data/lexicons/<novel_id>-ner-cache.json` (`mentions/chapter_ner.py`'s
`NameCache`) -- the same Qwen model's real surface -> label judgements for
that exact chapter text, computed once and never wired into `self_entity`.
This is real model evidence already on disk, not name-keyword guessing
(CLAUDE.md non-negotiable #9 explicitly rejects "ends in Mountain =
LOCATION").

Voting rule: aggregated across a whole novel's chapters, a bare reused
surface (e.g. "Gu Yue", both a clan and a component of several members'
names) can carry a genuine mix of labels the way a single founding-mention
group in `_entity_kind` never would, so this cannot demand the same
zero-tolerance unanimity. Instead the plurality label must outright beat
"character" in vote count -- a tie or a narrow "character" lead both keep
the SELF default (a wrong SELF is a cheap, visible, correctable mistake; a
wrong LOCATION silently drops a real character from casting), while a
clear non-character plurality (2 "location" votes to 1 "character" for
"Gu Yue", say) is enough real evidence to reclassify.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

from echotales.core.enums import TargetKind
from echotales.core.store import Store

log = logging.getLogger(__name__)

#: Same mapping `_entity_kind` uses -- kept in sync deliberately rather than
#: imported, since importing from `runner.py` here would invert the natural
#: dependency (`runner.py` calls into this module, not the reverse).
_KIND_BY_LABEL = {
    "location": TargetKind.LOCATION,
    "organization": TargetKind.ORGANIZATION,
    "item": TargetKind.ITEM,
}


def _load_cache_votes(cache_path: Path) -> dict[str, Counter]:
    """surface -> Counter({label: number of chapters it was seen with that label})."""
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        log.warning("kind backfill: unreadable NER cache at %s, skipping", cache_path)
        return {}
    votes: dict[str, Counter] = {}
    for chapter_entry in data.values():
        if not isinstance(chapter_entry, dict):
            continue
        for surface, label in chapter_entry.items():
            votes.setdefault(surface, Counter())[label] += 1
    return votes


def _classify(surfaces: list[str], votes: dict[str, Counter]) -> TargetKind | None:
    """Aggregate cache votes across every alias surface this entity is known by.

    Returns `None` (leave unset, i.e. still defaults to SELF on read) rather
    than guess when the evidence is absent, mixed, or only a plurality --
    see module docstring for the precision-first reasoning.
    """
    combined: Counter = Counter()
    seen_any = False
    for surface in surfaces:
        counts = votes.get(surface)
        if counts:
            seen_any = True
            combined.update(counts)
    if not seen_any:
        return None
    best_label, best_count = combined.most_common(1)[0]
    char_count = combined.get("character", 0)
    # A bare surface like "Gu Yue" can be a genuine mixed bag across a whole
    # novel's chapters (the clan name most chapters, a person's own name in
    # one or two) -- unlike `_entity_kind`'s single founding-mention group,
    # this is aggregated over the entire corpus, so demanding zero
    # "character" votes anywhere would leave every reused name unclassified.
    # The plurality label still has to outright beat "character", not just
    # tie or edge it out, before this overrides the SELF default.
    if best_label == "character" or best_count <= char_count:
        return None
    kind = _KIND_BY_LABEL.get(best_label)
    if kind is None:
        return None
    return kind


def backfill_kinds(store: Store, novel_id: str, cache_path: Path) -> dict[str, int]:
    """Fill `self_entity.kind` for every entity of `novel_id` still unset.

    Idempotent, cheap (no model calls -- pure aggregation over an on-disk
    cache), and safe to call unconditionally on every `resolve_novel` run:
    it only ever touches rows where the raw column is still NULL/empty, so
    it can never clobber a kind `_entity_kind` already assigned at creation
    time from real `entity_label` evidence. This is what makes the fix
    durable rather than a one-off -- see EVOLUTION 4.54.
    """
    stats = {"checked": 0, "classified": 0, "left_default": 0}
    unset_ids = store.unset_kind_self_ids(novel_id)
    if not unset_ids:
        return stats
    votes = _load_cache_votes(cache_path)
    if not votes:
        stats["left_default"] = len(unset_ids)
        stats["checked"] = len(unset_ids)
        return stats
    for self_id in unset_ids:
        stats["checked"] += 1
        entity = store.get_self(self_id)
        if entity is None:
            continue
        surfaces = {entity.canonical_label}
        for alias in store.get_aliases_for(TargetKind.SELF, self_id):
            surfaces.add(alias.alias)
        kind = _classify(sorted(surfaces), votes)
        if kind is not None:
            store.set_kind(self_id, kind)
            stats["classified"] += 1
        else:
            stats["left_default"] += 1
    return stats
