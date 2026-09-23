"""Record *who witnessed* each reveal, populating the observer axis.

`architecture.md`'s headline acceptance test is that `state_of(observer=X)`
returns something different from `state_of(observer=READER)` -- the Wu clan
does not know Wu Yi Hai is Fang Yuan, even though the reader has known since
chapter one. That test could not pass, and not because the query was wrong:
verified against `data/webview-working/reverend-insanity.db`, every row in
`self_persona_binding` (83), `alias_binding` (9,469) and `attribute` (536) is
stamped `READER`, the `observation` table is **empty**, and nothing in the
codebase ever wrote to it. The schema, the model and the query logic all
existed. The writer did not (EVOLUTION 4.80).

This module is the writer. It reuses what is already there rather than adding
a detector: `detect_reveals.py::find_reveals` already computes where a
narrator reveal happens and which entity it names (and stamps it
`OBSERVER_READER` unconditionally, at `detect_reveals.py:254`), and
`anaphora/local.py::present_cast_ids` already decides who is physically in a
block. A reveal plus a co-present cast is an observation.

**What an observation here does and does not claim.** It claims: this entity
was physically present in the scene where the narrator revealed a name, so
they plausibly learned it. It does not claim they believed it, understood it,
or told anyone. Presence is the only witnessing signal this text reliably
provides -- the alternative, inferring knowledge from dialogue, is the
unbounded "replay who witnessed what" approach `architecture.md` Section 8b
already rejected for `audience_scope_compatibility` on the grounds that it
silently becomes a constant.

**Scene granularity, not block, and this was measured rather than assumed.**
The first implementation used the reveal's own block, matching
`detect_reveals.py::reveal_target_for_block`. Run against RI it produced
**zero** observations from all three reveals, and the reason was not a bug:
each reveal block contained exactly one person mention, the revealed
character themselves, who is excluded by definition. Block granularity is
right for *panel casting* (who is in this frame) and wrong for *witnessing*
(who is in the room) -- someone standing there is a witness whether or not
their name recurs in the same paragraph. The enclosing `NarrativeSegment` is
the scene unit this codebase already has, so witnesses are drawn from it,
falling back to the block when a reveal falls outside every segment.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from echotales.core.models import DiscoursePosition, Observation
from echotales.core.readset import fact_ref, normalize
from echotales.core.store import Store

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ObservationReport:
    novel_id: str
    reveals: int = 0
    reveals_with_witnesses: int = 0
    observations_written: int = 0
    observers: int = 0

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.reveals:,} reveals, "
            f"{self.reveals_with_witnesses:,} with a co-present witness -> "
            f"{self.observations_written:,} observations across "
            f"{self.observers:,} observers"
        )


def reveal_fact_ref(target_id: str, revealed_name: str) -> str:
    """The alias binding a reveal creates, as `readset.observable_ref` spells it.

    Must agree with `observable_ref(AliasBinding)` exactly or an observation
    names a fact `state_of` will never look up -- and the failure is silent,
    because a missing observation is indistinguishable from "this character
    did not witness it".
    """
    return fact_ref("alias", target_id, normalize(revealed_name))


def _scene_blocks(
    segments: list, chapter: float, block_index: int
) -> list[int]:
    """Block indices of the narrative segment containing this reveal.

    Falls back to the reveal's own block when no segment covers it, so a
    novel without segmentation still produces (fewer) observations rather
    than silently none.
    """
    for segment in segments:
        if segment.chapter_from <= chapter <= segment.chapter_to:
            low = segment.offset_from if segment.chapter_from == chapter else 0
            high = segment.offset_to if segment.chapter_to == chapter else 10**6
            if low <= block_index <= high:
                return list(range(low, min(high, low + 10_000) + 1))
    return [block_index]


def detect_observations(
    store: Store, novel_id: str, *, include_revealed_self: bool = False
) -> ObservationReport:
    """Write one observation per (witness, revealed alias) pair.

    `include_revealed_self` is off by default: the person whose identity is
    revealed already knows it, and recording them as having *learned* it at
    the reveal would date their self-knowledge to the moment someone else
    found out -- which is precisely the Self-vs-Persona confusion
    non-negotiable #3 exists to prevent.
    """
    from echotales.pipeline.anaphora.local import present_cast_ids
    from echotales.pipeline.resolve.detect_reveals import find_reveals

    report = ObservationReport(novel_id=novel_id)
    reveals = find_reveals(store, novel_id)
    if not reveals:
        return report

    segments = store.get_segments(novel_id)

    person_ids = frozenset(
        s.id for s in store.all_selves(novel_id) if s.kind.is_person
    )

    # Mentions are fetched per chapter, not per reveal: several reveals often
    # land in one chapter and a per-reveal query would re-read it each time.
    by_chapter: dict[float, list] = defaultdict(list)
    for reveal in reveals:
        by_chapter[float(reveal.chapter)].append(reveal)

    pending: list[Observation] = []
    observers: set[str] = set()
    for chapter, chapter_reveals in sorted(by_chapter.items()):
        mentions = store.get_mentions(novel_id, chapter)
        in_block: dict[int, list] = defaultdict(list)
        for mention in mentions:
            in_block[int(mention.block_index or 0)].append(mention)

        for reveal in chapter_reveals:
            report.reveals += 1
            scene_blocks = _scene_blocks(segments, chapter, reveal.block_index)
            in_scene = [m for b in scene_blocks for m in in_block.get(b, [])]
            witnesses = present_cast_ids(in_scene, person_ids)
            if not include_revealed_self:
                witnesses.discard(reveal.target_id)
            if not witnesses:
                continue
            report.reveals_with_witnesses += 1
            ref = reveal_fact_ref(reveal.target_id, reveal.revealed_name)
            pos = DiscoursePosition(chapter=int(chapter), offset=int(reveal.offset))
            for witness in sorted(witnesses):
                observers.add(witness)
                pending.append(
                    Observation(observer_id=witness, fact_ref=ref, learned_at_pos=pos)
                )

    report.observations_written = store.add_observations(pending)
    report.observers = len(observers)
    store.conn.commit()
    return report
