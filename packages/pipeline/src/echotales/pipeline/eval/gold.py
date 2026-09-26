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

**That sentence was already here on 2026-08-12, and it did not prevent the
thing it describes.** 6,952 records drafted by `generate_gold.py` from the
pipeline's own `mention` table were marked `provenance: human, confirmed:
true`, their "NOT independently verified" notes replaced with "Ground-truth
mention", and a B-cubed result (P=100.0%, R=94.6%, F1=97.2%) was reported from
them. Precision of exactly 100.0% is the arithmetic signature of scoring a
partition against itself. See `docs/EVOLUTION.md` 4.74 and
`data/gold/_unusable/README.md`.

So the contract is now enforced at construction rather than described:

- `CIRCULAR_DRAFTERS` names drafters that read the pipeline's output instead of
  the source text. Those records raise `CircularGoldError` if confirmed, at any
  review depth — a human re-reading them checks the system against itself.
- A confirmation must name the person who made it (`confirmed_by`) and must be
  `ReviewDepth.PER_RECORD`. Bulk approval is recorded, and does not count.

Two distinctions this file now keeps separate, because collapsing them is what
went wrong: *independent but unconfirmed* (an LLM reading the novel — a real
draft, one human pass away from gold) versus *circular* (a label read back out
of the system under test — not gold at any amount of review).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from echotales.core.enums import AliasType


class Provenance(StrEnum):
    #: Proposed by a model. Not gold. Usable as a draft to be audited, and as a
    #: second annotator for agreement measurement — never as ground truth.
    MODEL = "model"
    #: Confirmed or written by a person. The only records that are gold.
    HUMAN = "human"


class ReviewDepth(StrEnum):
    """How closely a person actually looked.

    A boolean `confirmed` could not express the thing that went wrong on
    2026-08-12: 6,952 records were approved in one action and the set was then
    reported as human-confirmed gold. The approver's own note said it plainly
    -- "reviewed by glancing over the set, not record by record" -- but that
    caveat lived in a note field no scorer reads, so `confirmed_only` returned
    all of them and a B-cubed number was published from it.
    """

    #: Nobody has looked.
    NONE = "none"
    #: Skimmed in aggregate, approved in bulk. Real information -- an obvious
    #: systematic error would have been caught -- but not an adjudication, so
    #: it never makes a record gold.
    BULK = "bulk"
    #: Adjudicated one record at a time against the source text. The only depth
    #: that can set `confirmed`.
    PER_RECORD = "per_record"


#: Drafters that read the pipeline's own resolution output instead of the
#: source text. A label expressed in the system's own ids can only agree with
#: it, so these records are not a measurement at any review depth -- confirming
#: one means checking whether the system agrees with the system. See
#: `data/gold/_unusable/README.md` for the 6,952-record incident this encodes,
#: and `generate_gold.py:95-102` for the comment that said so before it was code.
CIRCULAR_DRAFTERS = frozenset({"gold-auto-builder"})


class GoldProvenanceError(ValueError):
    """A gold record claims a confirmation it cannot support."""


class CircularGoldError(GoldProvenanceError):
    """A record drafted from the pipeline's own output was marked confirmed."""


class UnattributedConfirmationError(GoldProvenanceError):
    """A record is confirmed but names no reviewer, or no per-record pass."""


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

#: `(novel_id, chapter, offset, normalised_surface)` -- see `GoldMention.key`
#: for why the surface is part of the identity of a mention and not merely
#: payload. Defined here rather than in `coref_score` so the scorer, the
#: calibrator and the gold set cannot drift into three different key shapes;
#: they did drift into three different *coordinate systems* once already
#: (EVOLUTION 4.75), and that cost a 0.4%-instead-of-98.6% reported number.
MentionKey = tuple[str, float, int, str]

#: Stamped on every report and every persisted metric computed from
#: `GoldSet.silver_only`. A tier this project invented for itself needs its
#: caveat travelling *with the number*, not living in a README -- the retracted
#: B-cubed result (EVOLUTION 4.74) was cited for six weeks by people reading a
#: printout, not the provenance doc beside it.
SILVER_BANNER = "SILVER -- LLM-derived reference set (Claude), not human gold; no IAA"


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
    #: docs/design/plans.md Section 4.1 binding type. Needed to split retriever recall@k
    #: by alias_type (eval/retriever_eval.py's TRANSFERABLE_TITLE gate) --
    #: without this field every gold mention silently reported as RIGID_NAME,
    #: which is exactly the easy case and hides a retrieval ceiling on the
    #: hard ones. Defaults to RIGID_NAME for old records drafted before this
    #: field existed; that default is a known undercount, not a measurement.
    alias_type: AliasType = AliasType.RIGID_NAME
    context: str = ""
    provenance: Provenance = Provenance.MODEL
    #: Which model drafted it, when `provenance` is MODEL. Kept so a drafting
    #: run can be invalidated wholesale if that model is later found unreliable.
    drafted_by: str = ""
    #: Set when a person has adjudicated this record individually, whether they
    #: changed it or not. An unreviewed agreement is not evidence of agreement,
    #: and neither is a bulk one -- see `ReviewDepth`. Enforced in
    #: `__post_init__`; this is the field a reported number is computed from,
    #: so it is the one that has to be unfakeable by accident.
    confirmed: bool = False
    #: Who did it. A confirmation that names nobody is how 6,952 machine-drafted
    #: records became "human" provenance with no person attached to the claim.
    confirmed_by: str = ""
    review_depth: ReviewDepth = ReviewDepth.NONE
    note: str = ""

    def __post_init__(self) -> None:
        if not self.confirmed:
            return
        if self.drafted_by in CIRCULAR_DRAFTERS:
            raise CircularGoldError(
                f"{self.novel_id} ch{self.chapter:g}@{self.offset}: drafted by "
                f"{self.drafted_by!r}, which reads the pipeline's own `mention` "
                "table. Confirming it measures the system against itself. Fix the "
                "drafting source, not the flag."
            )
        if not self.confirmed_by:
            raise UnattributedConfirmationError(
                f"{self.novel_id} ch{self.chapter:g}@{self.offset}: confirmed=True "
                "with no `confirmed_by`. Name the person who adjudicated it."
            )
        if self.review_depth is not ReviewDepth.PER_RECORD:
            raise UnattributedConfirmationError(
                f"{self.novel_id} ch{self.chapter:g}@{self.offset}: confirmed=True "
                f"at review_depth={self.review_depth.value!r}. Only "
                f"{ReviewDepth.PER_RECORD.value!r} makes a record gold."
            )

    @property
    def key(self) -> MentionKey:
        """Position *and surface* identify a mention.

        Position alone was the key until 2026-09-24, and it silently lost
        records: a word-boundary **prefix** surface starts at the same offset
        as the longer surface it prefixes, so both annotations landed on one
        key and the later one overwrote the earlier. Measured on the shipped
        drafts: `reverend-insanity-c1-c5.jsonl` has 52 offsets carrying 2-3
        records each (107 records involved), and under the old key it
        collapsed to 288 distinct keys instead of 343 -- **55 annotations
        destroyed at load time**, most of them reassigned to the `Gu Yue`
        clan, which prefixes every clan member's name. In the extended draft a
        bare `"Gu"` negative overwrote a real entity's position the same way.

        Surface is normalised exactly as `coref_score._system_partition`
        normalises `Mention.text` before comparing, so a gold key and the
        system key computed for the same mention agree. That matcher already
        discriminated by surface; only the key it stored under threw the
        distinction away.

        Two occurrences of one name in a chapter remain two mentions at two
        offsets, and can still denote two different people.
        """
        return (self.novel_id, self.chapter, self.offset, self.surface.strip().casefold())

    def to_json(self) -> dict[str, object]:
        return {
            "novel_id": self.novel_id,
            "chapter": self.chapter,
            "offset": self.offset,
            "surface": self.surface,
            "identity": self.identity,
            "kind": self.kind.value,
            "alias_type": self.alias_type.value,
            "context": self.context,
            "provenance": self.provenance.value,
            "drafted_by": self.drafted_by,
            "confirmed": self.confirmed,
            "confirmed_by": self.confirmed_by,
            "review_depth": self.review_depth.value,
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
            alias_type=AliasType(str(row.get("alias_type", AliasType.RIGID_NAME.value))),
            context=str(row.get("context", "")),
            provenance=Provenance(str(row.get("provenance", Provenance.MODEL.value))),
            drafted_by=str(row.get("drafted_by", "")),
            confirmed=bool(row.get("confirmed", False)),
            confirmed_by=str(row.get("confirmed_by", "")),
            review_depth=ReviewDepth(str(row.get("review_depth", ReviewDepth.NONE.value))),
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
    def silver_only(self) -> GoldSet:
        """Model-drafted records that were **not** read back out of the system.

        The honest middle tier between `circular` (worthless -- the pipeline
        scored against its own output, EVOLUTION 4.74) and `confirmed_only`
        (empty, and staying empty until a person adjudicates records one by
        one). These were drafted by a different model family than the one
        under test, reading chapter text rather than the `mention` table, and
        at least one of them *contradicts* the pipeline -- a label that
        disagrees with the system cannot have been derived from it.

        This is a **silver standard, not gold**: no human adjudicated it and
        there is no inter-annotator agreement behind it. Every number computed
        from it must carry `SILVER_BANNER`. It is evidence, and weaker than
        gold, and both halves of that sentence have to survive into the paper.
        """
        return GoldSet(
            self.novel_id,
            [
                m
                for m in self.mentions
                if m.provenance is Provenance.MODEL and m.drafted_by not in CIRCULAR_DRAFTERS
            ],
        )

    @property
    def entities_only(self) -> GoldSet:
        return GoldSet(self.novel_id, [m for m in self.mentions if m.kind.is_entity])

    @property
    def characters_only(self) -> GoldSet:
        return GoldSet(self.novel_id, [m for m in self.mentions if m.kind in PERSON_KINDS])

    def partition(self) -> dict[MentionKey, str]:
        """Mention key -> identity. The annotated coreference partition."""
        return {m.key: m.identity for m in self.mentions if m.identity}

    @property
    def circular(self) -> GoldSet:
        """Records whose labels came from the pipeline's own resolution output.

        Scoring against these measures self-agreement, so they are not a result
        at any confirmation level -- unlike an unconfirmed draft, which only
        needs a person to become one.
        """
        return GoldSet(
            self.novel_id, [m for m in self.mentions if m.drafted_by in CIRCULAR_DRAFTERS]
        )

    def coverage(self) -> str:
        total = len(self.mentions)
        confirmed = sum(1 for m in self.mentions if m.confirmed)
        circular = len(self.circular)
        kinds: dict[str, int] = {}
        depths: dict[str, int] = {}
        for m in self.mentions:
            kinds[m.kind.value] = kinds.get(m.kind.value, 0) + 1
            depths[m.review_depth.value] = depths.get(m.review_depth.value, 0) + 1
        identities = len({m.identity for m in self.mentions if m.identity})
        chapters = len({m.chapter for m in self.mentions})
        share = confirmed / total if total else 0.0
        lines = [
            f"{self.novel_id}: {total:,} annotated mentions over "
            f"{chapters} chapters, {identities} distinct identities",
            f"  human-confirmed: {confirmed:,} ({share:.0%})"
            f"{'  <- NOT GOLD until this is meaningful' if share < 1.0 else ''}",
            "  review depth: " + ", ".join(f"{k}={v:,}" for k, v in sorted(depths.items())),
        ]
        # Printed unconditionally rather than only when non-zero: the draft-tier
        # B-cubed number in `cmd_eval` is computed over every record, and if most
        # of them were drafted from the system's own output then that number is
        # self-agreement, not accuracy. It read 98.1% F1 while being exactly that.
        if circular:
            lines.append(
                f"  drafted from the pipeline's own output: {circular:,} "
                f"({circular / total:.0%})  <- self-agreement, not a measurement"
            )
        lines.append("  by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
        return "\n".join(lines)


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
