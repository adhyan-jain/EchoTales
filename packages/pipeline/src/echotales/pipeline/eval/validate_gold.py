"""Structural validation of an annotation file, independent of any model.

Why this exists as code rather than as a habit: `test_all_novels_gold_sets.py`
checked provenance and the *absence* of confirmed gold, but nothing ever
checked that two records could not occupy one key. They could, and they did --
52 offsets in `reverend-insanity-c1-c5.jsonl` carried 2-3 records each, and
under the pre-2026-09-24 key 55 of its 343 annotations were destroyed at load
time with no error anywhere. A silent 16% data loss passed CI for six weeks.

Every check here answers "is this file internally coherent", never "is this
annotation correct". Correctness needs a person, and this project has
deliberately not claimed one (see `GoldSet.silver_only`).

The store argument is optional: the checks that need chapter text are skipped
with an explicit `skipped` severity when no store is given, rather than
silently passing. A check that could not run must not look like a check that
passed -- that conflation is the same class of error as EVOLUTION 4.74.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.store import Store

from .gold import CIRCULAR_DRAFTERS, GoldSet, MentionKind


@dataclass(slots=True)
class Finding:
    """One structural problem, or one clean bill of health for a check."""

    check: str
    severity: str  # "error" | "warning" | "info" | "skipped"
    count: int
    detail: str
    examples: list[str] = field(default_factory=list)

    def summary(self) -> str:
        mark = {"error": "FAIL", "warning": "WARN", "info": "ok  ", "skipped": "SKIP"}[
            self.severity
        ]
        line = f"  [{mark}] {self.check}: {self.detail}"
        for ex in self.examples[:5]:
            line += f"\n           {ex}"
        if len(self.examples) > 5:
            line += f"\n           ... and {len(self.examples) - 5} more"
        return line


@dataclass(slots=True)
class ValidationReport:
    path: str
    novel_id: str
    records: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        head = (
            f"gold validation: {self.path}\n"
            f"  novel={self.novel_id}  records={self.records:,}  "
            f"verdict={'PASS' if self.ok else 'FAIL'} "
            f"({len(self.errors)} error(s))"
        )
        return head + "\n" + "\n".join(f.summary() for f in self.findings)

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "novel_id": self.novel_id,
            "records": self.records,
            "ok": self.ok,
            "findings": [
                {
                    "check": f.check,
                    "severity": f.severity,
                    "count": f.count,
                    "detail": f.detail,
                    "examples": f.examples[:20],
                }
                for f in self.findings
            ],
        }


def _colliding_keys(gold: GoldSet) -> Finding:
    """Two records under one key.

    After the 2026-09-24 key change this should be impossible by construction,
    which is exactly why it is asserted: the check is cheap and the failure it
    guards was invisible for six weeks.
    """
    counts = Counter(m.key for m in gold.mentions)
    dupes = {k: v for k, v in counts.items() if v > 1}
    if not dupes:
        return Finding("colliding-keys", "info", 0, "every record has a distinct key")
    lost = sum(v - 1 for v in dupes.values())
    return Finding(
        "colliding-keys",
        "error",
        lost,
        f"{len(dupes)} key(s) carry more than one record; {lost} record(s) "
        f"would be destroyed by any partition built on this key",
        [f"ch{k[1]:g}@{k[3]!r} x{v}" for k, v in sorted(dupes.items(), key=str)[:20]],
    )


def _positional_overlaps(gold: GoldSet) -> Finding:
    """Distinct surfaces annotated at one (chapter, offset).

    Legitimate and common after the key fix -- "Gu Yue" the clan and
    "Gu Yue Fang Yuan" the person genuinely both begin there. Reported as
    information so the count stays visible in the record, not as a problem.
    """
    by_pos: dict[tuple[float, int], set[str]] = defaultdict(set)
    for m in gold.mentions:
        by_pos[(m.chapter, m.offset)].add(m.surface)
    shared = {p: s for p, s in by_pos.items() if len(s) > 1}
    if not shared:
        return Finding("positional-overlap", "info", 0, "no offset carries two surfaces")
    return Finding(
        "positional-overlap",
        "info",
        len(shared),
        f"{len(shared)} offset(s) carry 2+ distinct surfaces -- expected where a "
        f"name prefixes another (clan vs member); both records are preserved",
        [f"ch{c:g}@{o}: {sorted(s)}" for (c, o), s in sorted(shared.items())[:20]],
    )


def _malformed_spans(gold: GoldSet, store: Store | None) -> Finding:
    """Does the annotated surface actually sit at the annotated offset?

    Needs the ingested chapter text, so it is skipped -- loudly -- without a
    store. Gold offsets are chapter-absolute over `Chapter.story_text`, the
    `"\\n\\n"`-join of story blocks; this reproduces that join rather than
    trusting a second copy of the rule to stay in sync.
    """
    if store is None:
        return Finding(
            "malformed-spans", "skipped", 0, "no --db given; span validity unchecked"
        )
    bad: list[str] = []
    checked = 0
    cache: dict[float, str | None] = {}
    for m in gold.mentions:
        if m.chapter not in cache:
            chapter = store.get_chapter(gold.novel_id, m.chapter)
            cache[m.chapter] = (
                "\n\n".join(b.text for b in chapter.blocks if b.block_type.is_story_content)
                if chapter is not None
                else None
            )
        text = cache[m.chapter]
        if text is None:
            continue
        checked += 1
        if m.offset < 0 or m.offset + len(m.surface) > len(text):
            bad.append(f"ch{m.chapter:g}@{m.offset} {m.surface!r}: offset outside chapter")
        elif text[m.offset : m.offset + len(m.surface)] != m.surface:
            found = text[m.offset : m.offset + len(m.surface)]
            bad.append(f"ch{m.chapter:g}@{m.offset} expected {m.surface!r}, text has {found!r}")
    if not checked:
        return Finding(
            "malformed-spans", "skipped", 0, "no annotated chapter is ingested in this db"
        )
    if not bad:
        return Finding(
            "malformed-spans", "info", 0, f"all {checked:,} checked spans sit at their offset"
        )
    return Finding(
        "malformed-spans",
        "error",
        len(bad),
        f"{len(bad):,} of {checked:,} spans do not match the chapter text at their offset",
        bad[:20],
    )


def _self_referential(gold: GoldSet) -> Finding:
    """One surface claimed by two identities inside one chapter.

    Across a volume this is legitimate and is the project's whole subject -- a
    transferable title changes holder. Within a single chapter it is far more
    often a drafting slip, so it is scoped that way, and reported as a warning
    rather than an error because a real mid-chapter handover does exist in
    this corpus.
    """
    by: dict[tuple[float, str], set[str]] = defaultdict(set)
    for m in gold.mentions:
        if m.identity and m.kind is not MentionKind.NOT_AN_ENTITY:
            by[(m.chapter, m.surface.casefold())].add(m.identity)
    conflicts = {k: v for k, v in by.items() if len(v) > 1}
    if not conflicts:
        return Finding(
            "self-referential", "info", 0, "no surface denotes two identities within a chapter"
        )
    return Finding(
        "self-referential",
        "warning",
        len(conflicts),
        f"{len(conflicts)} surface(s) denote 2+ identities within one chapter",
        [f"ch{c:g} {s!r} -> {sorted(i)}" for (c, s), i in sorted(conflicts.items())[:20]],
    )


def _contradictory_negatives(gold: GoldSet) -> Finding:
    """A surface annotated both as an entity and as `not_an_entity`.

    The extended RI draft's exact defect: bare "Gu" is a negative and also
    prefixes real entities. Both records now survive the key, so the
    contradiction is visible instead of one silently winning -- which is the
    point of surfacing it here rather than letting a partition pick a winner.
    """
    entity: set[str] = set()
    negative: set[str] = set()
    for m in gold.mentions:
        (negative if m.kind is MentionKind.NOT_AN_ENTITY else entity).add(m.surface.casefold())
    both = entity & negative
    if not both:
        return Finding(
            "contradictory-negatives", "info", 0, "no surface is both entity and negative"
        )
    return Finding(
        "contradictory-negatives",
        "warning",
        len(both),
        f"{len(both)} surface(s) annotated as an entity somewhere and as "
        f"not_an_entity elsewhere",
        sorted(both)[:20],
    )


def _impossible_targets(gold: GoldSet) -> Finding:
    """Entity records with no identity, and negatives that carry one.

    Both are contract violations of `GoldMention`: an entity mention must
    denote somebody, and a non-entity must denote nobody.
    """
    bad: list[str] = []
    for m in gold.mentions:
        if m.kind is MentionKind.NOT_AN_ENTITY and m.identity:
            bad.append(f"ch{m.chapter:g}@{m.offset} {m.surface!r}: not_an_entity with identity")
        elif m.kind is not MentionKind.NOT_AN_ENTITY and not m.identity:
            bad.append(
                f"ch{m.chapter:g}@{m.offset} {m.surface!r}: {m.kind.value} with no identity"
            )
    if not bad:
        return Finding("impossible-targets", "info", 0, "kind and identity agree on every record")
    return Finding(
        "impossible-targets",
        "error",
        len(bad),
        f"{len(bad):,} record(s) violate kind/identity",
        bad[:20],
    )


def _missing_entities(gold: GoldSet, store: Store | None) -> Finding:
    """Annotated chapters where the system detected no mention at all.

    A whole chapter of gold with zero system mentions is the signature of the
    NER truncation defect (EVOLUTION 4.76), not of a resolution error, and the
    two want different fixes -- worth separating before anyone reads a recall
    number and starts tuning the resolver.
    """
    if store is None:
        return Finding("missing-entities", "skipped", 0, "no --db given; coverage unchecked")
    annotated = {m.chapter for m in gold.mentions}
    empty = sorted(ch for ch in annotated if not store.get_mentions(gold.novel_id, chapter=ch))
    if not empty:
        return Finding(
            "missing-entities", "info", 0, f"all {len(annotated)} annotated chapters have mentions"
        )
    return Finding(
        "missing-entities",
        "warning",
        len(empty),
        f"{len(empty)} of {len(annotated)} annotated chapters have zero system mentions",
        [f"ch{c:g}" for c in empty[:20]],
    )


def _provenance(gold: GoldSet) -> Finding:
    """Tier census.

    Not pass/fail -- the number a reader needs before trusting any metric
    computed from this file.
    """
    circular = len(gold.circular.mentions)
    silver = len(gold.silver_only.mentions)
    confirmed = len(gold.confirmed_only.mentions)
    drafters = Counter(m.drafted_by or "(unattributed)" for m in gold.mentions)
    return Finding(
        "provenance",
        "warning" if circular else "info",
        circular,
        f"confirmed={confirmed:,} silver={silver:,} circular={circular:,} "
        f"({'; '.join(f'{k}={v:,}' for k, v in drafters.most_common())})"
        + (
            f"  <- circular records were drafted by {sorted(CIRCULAR_DRAFTERS)} "
            "from the pipeline's own output and cannot score it"
            if circular
            else ""
        ),
    )


def _alias_type_coverage(gold: GoldSet) -> Finding:
    """How much of a recall@k breakdown this file can actually support.

    A file that is 100% RIGID_NAME produces an alias-type table with one
    populated row, which reads like a measurement and is not one.
    """
    counts = Counter(m.alias_type.value for m in gold.mentions if m.kind.is_entity)
    if not counts:
        return Finding("alias-type-coverage", "warning", 0, "no entity records")
    total = sum(counts.values())
    top_share = counts.most_common(1)[0][1] / total
    severity = "warning" if top_share > 0.95 else "info"
    detail = ", ".join(f"{k}={v:,}" for k, v in counts.most_common())
    if severity == "warning":
        detail += (
            f"  <- {top_share:.0%} is a single type; a per-alias-type breakdown "
            "from this file does not measure the hard types"
        )
    return Finding("alias-type-coverage", severity, len(counts), detail)


def validate_gold(gold: GoldSet, path: str, store: Store | None = None) -> ValidationReport:
    """Run every structural check.

    Ordered cheapest-first so a catastrophic file fails before the span checks
    read every chapter off disk.
    """
    findings = [
        _provenance(gold),
        _colliding_keys(gold),
        _positional_overlaps(gold),
        _impossible_targets(gold),
        _self_referential(gold),
        _contradictory_negatives(gold),
        _alias_type_coverage(gold),
        _malformed_spans(gold, store),
        _missing_entities(gold, store),
    ]
    return ValidationReport(path, gold.novel_id, len(gold.mentions), findings)


def write_report(report: ValidationReport, out_path: Path | str) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_json(), indent=2) + "\n", encoding="utf-8")
    return out
