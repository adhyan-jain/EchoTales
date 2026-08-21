"""Gold annotation records and their provenance.

A gold record answers one question about one mention: **which individual does
this surface form denote**, written as a canonical identity string chosen by the
annotator rather than as a pipeline entity id. Keeping identity independent of
the pipeline's own inventory is what makes the annotation usable as a
measurement — a label expressed in the system's ids can only ever agree with it.

`kind` carries the second question, and it is the one this corpus actually turns
on: whether the surface denotes an individual *at all*. A capitalised item name
or a role noun that the detector proposed and gold rejects is a false positive,
and it is invisible to any metric that only scores clustering.

**Provenance is not optional metadata.** `HANDOFF Section 6` already forbids feeding
hand-curated alias mappings back in as pipeline input; a *model-drafted* label
is weaker still, and the difference between "a person decided this" and "a model
proposed it" has to survive every export, or a recall number computed from
model-drafted labels will eventually be reported as a result. `PROVENANCE_MODEL`
records are explicitly not gold until confirmed — see `GoldSet.confirmed_only`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Provenance(StrEnum):
    #: Proposed by a model. Not gold. Usable as a draft to be audited, and as a
    #: second annotator for agreement measurement — never as ground truth.
    MODEL = "model"
    #: Confirmed or written by a person. The only records that are gold.
    HUMAN = "human"


class MentionKind(StrEnum):
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    ORGANIZATION = "organization"
    #: The detector proposed this surface and it denotes no individual: a role
    #: noun, a power-scale term, a translation credit, a copied fragment.
    NOT_AN_ENTITY = "not_an_entity"

    @property
    def is_entity(self) -> bool:
        return self is not MentionKind.NOT_AN_ENTITY


#: Kinds that the identity graph is actually about. Locations and items are
#: annotated because dropping them silently is itself a defect worth measuring,
#: but they are scored separately from the character partition.
PERSON_KINDS = frozenset({MentionKind.CHARACTER})


@dataclass(slots=True)
class GoldMention:
    """One annotated mention."""

    novel_id: str
    chapter: float
    offset: int
    surface: str
    #: Canonical identity, the annotator's own string. Empty when `kind` is
    #: `NOT_AN_ENTITY`, since a non-entity denotes nobody.
    identity: str = ""
    kind: MentionKind = MentionKind.CHARACTER
    context: str = ""
    provenance: Provenance = Provenance.MODEL
    #: Which model drafted it, when `provenance` is MODEL. Kept so a drafting
    #: run can be invalidated wholesale if that model is later found unreliable.
    drafted_by: str = ""
    #: Set when a person has reviewed the drafted record, whether they changed
    #: it or not. An unreviewed agreement is not evidence of agreement.
    confirmed: bool = False
    note: str = ""

    @property
    def key(self) -> tuple[str, float, int]:
        """Position identifies a mention, not its surface text.

        Two occurrences of one name in a chapter are two mentions and can, in
        principle, denote two different people.
        """
        return (self.novel_id, self.chapter, self.offset)

    def to_json(self) -> dict[str, object]:
        return {
            "novel_id": self.novel_id,
            "chapter": self.chapter,
            "offset": self.offset,
            "surface": self.surface,
            "identity": self.identity,
            "kind": self.kind.value,
            "context": self.context,
            "provenance": self.provenance.value,
            "drafted_by": self.drafted_by,
            "confirmed": self.confirmed,
            "note": self.note,
        }

    @classmethod
    def from_json(cls, row: dict[str, object]) -> GoldMention:
        return cls(
            novel_id=str(row["novel_id"]),
            chapter=float(row["chapter"]),  # type: ignore[arg-type]
            offset=int(row["offset"]),  # type: ignore[arg-type]
            surface=str(row["surface"]),
            identity=str(row.get("identity", "")),
            kind=MentionKind(str(row.get("kind", MentionKind.CHARACTER.value))),
            context=str(row.get("context", "")),
            provenance=Provenance(str(row.get("provenance", Provenance.MODEL.value))),
            drafted_by=str(row.get("drafted_by", "")),
            confirmed=bool(row.get("confirmed", False)),
            note=str(row.get("note", "")),
        )


@dataclass(slots=True)
class GoldSet:
    """A collection of annotations over one novel."""

    novel_id: str
    mentions: list[GoldMention] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.mentions)

    def __iter__(self) -> Iterator[GoldMention]:
        return iter(self.mentions)

    @property
    def confirmed_only(self) -> GoldSet:
        """The subset that is actually gold.

        Anything reported as a recall or accuracy *result* must come from here.
        Model-drafted records are a draft and a second opinion, nothing more.
        """
        return GoldSet(
            self.novel_id, [m for m in self.mentions if m.confirmed]
        )

    @property
    def entities_only(self) -> GoldSet:
        return GoldSet(self.novel_id, [m for m in self.mentions if m.kind.is_entity])

    @property
    def characters_only(self) -> GoldSet:
        return GoldSet(self.novel_id, [m for m in self.mentions if m.kind in PERSON_KINDS])

    def partition(self) -> dict[tuple[str, float, int], str]:
        """Mention key -> identity. The annotated coreference partition."""
        return {m.key: m.identity for m in self.mentions if m.identity}

    def coverage(self) -> str:
        confirmed = sum(1 for m in self.mentions if m.confirmed)
        kinds: dict[str, int] = {}
        for m in self.mentions:
            kinds[m.kind.value] = kinds.get(m.kind.value, 0) + 1
        identities = len({m.identity for m in self.mentions if m.identity})
        chapters = len({m.chapter for m in self.mentions})
        share = confirmed / len(self.mentions) if self.mentions else 0.0
        return (
            f"{self.novel_id}: {len(self.mentions):,} annotated mentions over "
            f"{chapters} chapters, {identities} distinct identities\n"
            f"  human-confirmed: {confirmed:,} ({share:.0%})"
            f"{'  <- NOT GOLD until this is meaningful' if share < 1.0 else ''}\n"
            "  by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
        )


def write_gold(gold: GoldSet, path: Path | str) -> Path:
    """Write JSONL, one record per line, sorted for a readable diff.

    Sorted by position so a human editing the file by hand reads it in the order
    they read the novel, and so re-drafting produces a reviewable diff rather
    than a reshuffle.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(gold.mentions, key=lambda m: (m.chapter, m.offset))
    out.write_text(
        "\n".join(json.dumps(m.to_json(), ensure_ascii=False) for m in rows) + "\n",
        encoding="utf-8",
    )
    return out


def read_gold(path: Path | str, novel_id: str = "") -> GoldSet:
    """Read JSONL. A missing file is an empty set, not an error.

    Callers are expected to check `len()` and say so — HANDOFF Section 1 is explicit
    that "compare against gold" must fail loudly rather than be improvised, and
    an empty set that silently scores 100% is exactly that failure.
    """
    src = Path(path)
    if not src.exists():
        return GoldSet(novel_id)
    mentions = [
        GoldMention.from_json(json.loads(line))
        for line in src.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return GoldSet(novel_id or (mentions[0].novel_id if mentions else ""), mentions)


def merge_gold(base: GoldSet, incoming: Iterable[GoldMention]) -> GoldSet:
    """Fold new drafts into an existing set without losing human work.

    A human-confirmed record always wins over an incoming draft for the same
    position. Re-drafting after a pipeline change must not silently revert
    decisions a person already made — that would make the annotation effort
    unrepeatable, which is the fastest way to lose it.
    """
    by_key = {m.key: m for m in base.mentions}
    for candidate in incoming:
        existing = by_key.get(candidate.key)
        if existing is not None and existing.confirmed:
            continue
        by_key[candidate.key] = candidate
    return GoldSet(base.novel_id, sorted(by_key.values(), key=lambda m: (m.chapter, m.offset)))
