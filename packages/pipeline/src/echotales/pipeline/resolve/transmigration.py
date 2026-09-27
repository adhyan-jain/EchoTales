"""Merge a transmigrated consciousness with the name of the body it took.

**The defect.** LOTM's protagonist is Zhou Mingrui, who wakes in the body of a
dead student, Klein Moretti; from then on the narration and every other
character call him "Klein". The resolver kept Zhou Mingrui, "Klein Moretti"
and "Klein" as three separate people (LOTM ch1-20: 177 + 4 + 420 mentions),
contrary to the project's own model -- one Self, a new Persona (docs/design/
architecture.md, Self != persona) -- and contrary to the LOTM reference set,
which labels all of them as one identity. Once "Klein Moretti" had split off,
the token "klein" belonged to two entities, so the name-containment rule
correctly refused to attach a bare "Klein" to either, and a third character
appeared.

**The rule, evidence-driven and precision-first.** A Self S absorbs another
person entity N only when the text gives both:
1. **a transmigration cue** in S's own narration ("could I have
   transmigrated?", "before his transmigration", "this body's original
   owner"), in at least `MIN_CUE_BLOCKS` blocks; and
2. **N as what S now has**: "Klein's memories", "Klein's muscle memory",
   "how Klein had died" -- N's possessions or death narrated from S's point
   of view, in at least `MIN_BODY_BLOCKS` blocks.
Two independent kinds of evidence are required so that a character who
merely remembers or mourns another is never merged with them. N's
first-name / full-name variants ("Klein" / "Klein Moretti") go with it,
matched by `normalize.name_containment` under either name order.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from echotales.core.enums import OBSERVER_READER, AliasType, EventType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import AliasBinding, DiscoursePosition, ResolutionEvent
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key, name_containment

log = logging.getLogger(__name__)

_CUE = re.compile(
    r"\btransmigrat\w*|\bthis body\b|\b(?:original|previous|former) owner\b|"
    r"\bbody[’']s (?:original|previous|former)\b|\breborn (?:as|into)\b|\bpossessed (?:this|the) body\b",
    re.IGNORECASE,
)
_NAME = r"[A-Z][\w-]+(?:\s+[A-Z][\w-]+){0,2}"
_BODY = re.compile(
    rf"(?P<poss>{_NAME})[’']s\s+(?:(?:shattered|fragmented|remaining|original)\s+)?"
    rf"(?:memor(?:y|ies)|memory fragments|muscle memory|body|experience|past|identity|life)\b"
    rf"|how (?P<died>{_NAME}) had died|(?P<death>{_NAME})[’']s death\b",
)
MIN_CUE_BLOCKS = 2
MIN_BODY_BLOCKS = 2


@dataclass(slots=True)
class TransmigrationReport:
    merges: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        if not self.merges:
            return "transmigration: none detected"
        return "transmigration: " + "; ".join(
            f"{m['into']} <- {', '.join(m['absorbed'])} ({m['mentions']} mentions; "
            f"cues {m['cue_blocks']}, body evidence {m['body_blocks']})" for m in self.merges
        )


def _names(store: Store, novel_id: str) -> tuple[dict[str, str], dict[str, str]]:
    """(comparison_key -> Self id for unambiguous person names, id -> label)."""
    owners: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for e in store.all_selves(novel_id):
        if e.kind.is_person:
            labels[e.id] = e.canonical_label
            owners[comparison_key(e.canonical_label)].add(e.id)
    return {k: next(iter(v)) for k, v in owners.items() if len(v) == 1 and k}, labels


def _longest_name(raw: str, names: dict[str, str]) -> str | None:
    words = raw.split()
    for n in range(len(words), 0, -1):
        if sid := names.get(comparison_key(" ".join(words[-n:]))):
            return sid
    return None


def _variants(labels: dict[str, str], anchor: str, exclude: str) -> list[str]:
    out = []
    for oid, lab in labels.items():
        if oid == exclude:
            continue
        if oid == anchor or max(
            name_containment(lab, labels[anchor], ambiguous_tokens=frozenset()),
            name_containment(lab, labels[anchor], ambiguous_tokens=frozenset(), given_name_first=True),
        ) > 0:
            out.append(oid)
    return out


def merge_transmigrations(store: Store, novel_id: str, *, dry_run: bool = False) -> TransmigrationReport:
    report = TransmigrationReport()
    names, labels = _names(store, novel_id)
    if not names:
        return report
    cue_blocks: Counter[str] = Counter()
    body: dict[str, Counter[str]] = defaultdict(Counter)
    first_cue: dict[str, float] = {}
    patterns = {sid: re.compile(rf"\b{re.escape(lab)}\b") for sid, lab in labels.items() if len(lab) > 2}

    for chapter in store.chapter_numbers(novel_id):
        ch = store.get_chapter(novel_id, chapter)
        if ch is None:
            continue
        for block in ch.blocks:
            text = block.text
            present = [sid for sid, pat in patterns.items() if pat.search(text)]
            if not present:
                continue
            if _CUE.search(text):
                for sid in present:
                    cue_blocks[sid] += 1
                    first_cue.setdefault(sid, chapter)
            for m in _BODY.finditer(text):
                other = _longest_name(m.group("poss") or m.group("died") or m.group("death"), names)
                if other is None:
                    continue
                for sid in present:
                    if sid != other:
                        body[sid][other] += 1

    for sid, cues in cue_blocks.items():
        if cues < MIN_CUE_BLOCKS:
            continue
        for other, n in body[sid].items():
            if n < MIN_BODY_BLOCKS or other not in labels:
                continue
            absorbed = _variants(labels, other, exclude=sid)
            start = first_cue.get(sid, 1.0)
            moved = 0
            for oid in absorbed:
                mentions = [m for m in store.get_mentions(novel_id) if m.target_id == oid]
                moved += len(mentions)
                if dry_run:
                    continue
                for m in mentions:
                    m.target_id = sid
                store.add_mentions(mentions)
                store.add_alias_binding(novel_id, AliasBinding(
                    alias=labels[oid], alias_type=AliasType.RIGID_NAME, target_kind=TargetKind.SELF,
                    target_id=sid, interval=FuzzyInterval.open_ended(start),
                    learned_at_pos=DiscoursePosition(chapter=int(start)), observer_id=OBSERVER_READER,
                    evidence=f"transmigration: {labels[sid]} took {labels[other]}'s body", confidence=0.85,
                ))
                seq = store.conn.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM resolution_event").fetchone()[0]
                store.append_event(ResolutionEvent(
                    id=uuid.uuid4().hex, seq=seq, type=EventType.MERGE,
                    payload={"from_id": oid, "into_id": sid, "mentions_rebound": len(mentions),
                             "source": "transmigration", "cue_blocks": cues, "body_blocks": n},
                    cause_pos=DiscoursePosition(chapter=int(start)), confidence=0.85,
                ))
            report.merges.append({"into": labels[sid], "absorbed": [labels[o] for o in absorbed],
                                  "mentions": moved, "cue_blocks": cues, "body_blocks": n})
    if report.merges:
        log.info(report.summary())
    return report
