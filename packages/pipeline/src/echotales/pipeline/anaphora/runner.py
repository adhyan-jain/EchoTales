"""Phase 5 orchestration: group and validate mentions chapter by chapter.

Also feeds pronoun resolutions back into Phase 4. A large share of the speech
spans that attribution leaves unresolved are pronoun subjects ("he said"), and
those become attributable once the pronoun has an antecedent -- so the two
phases are run in sequence rather than independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.enums import AliasType, AttributionMethod, ReferenceMode, SpanType
from echotales.core.models import Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.anaphora.local import (
    find_kinship_terms,
    group_mentions,
    resolve_kinship_group,
)
from echotales.pipeline.anaphora.validate import ValidationResult, validate_groups
from echotales.pipeline.spans import classify_chapter


@dataclass(slots=True)
class AnaphoraReport:
    novel_id: str
    chapters: int = 0
    groups: int = 0
    pronoun_links: int = 0
    kinship_links: int = 0
    splits: int = 0
    escalated_chapters: int = 0
    violations_by_kind: dict[str, int] = field(default_factory=dict)
    recovered_attributions: int = 0

    def summary(self) -> str:
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(self.violations_by_kind.items())) or "none"
        return (
            f"{self.novel_id}: {self.groups:,} local groups over {self.chapters} chapters\n"
            f"  pronoun links: {self.pronoun_links:,}  kinship links: {self.kinship_links:,}"
            f"  splits: {self.splits}\n"
            f"  violations: {kinds}\n"
            f"  chapters flagged for escalation: {self.escalated_chapters}\n"
            f"  speech spans recovered for attribution: {self.recovered_attributions:,}"
        )


def resolve_chapter(
    novel_id: str,
    chapter_number: float,
    store: Store,
    *,
    concurrent_personas: frozenset[str] = frozenset(),
) -> tuple[ValidationResult, int]:
    """Group and validate one chapter. Returns the result and pronoun-link count."""
    chapter = store.get_chapter(novel_id, chapter_number)
    if chapter is None:
        return ValidationResult(groups=[]), 0

    spans = classify_chapter(chapter)
    mentions = store.get_mentions(novel_id, chapter_number)
    segments = store.get_segments(novel_id, chapter_number)

    groups, links = group_mentions(mentions, spans, timeline_id="")
    result = validate_groups(
        groups, mentions, segments, concurrent_personas=concurrent_personas
    )
    return result, len(links)


def resolve_novel(
    novel_id: str,
    store: Store,
    *,
    concurrent_personas: frozenset[str] = frozenset(),
    commit_every: int = 25,
) -> AnaphoraReport:
    """Run local anaphora over a whole novel and write group ids onto mentions."""
    report = AnaphoraReport(novel_id=novel_id)

    for i, chapter in enumerate(store.iter_chapters(novel_id), start=1):
        spans = classify_chapter(chapter)
        mentions = store.get_mentions(novel_id, chapter.number)
        segments = store.get_segments(novel_id, chapter.number)
        if not mentions:
            report.chapters += 1
            continue

        groups, links = group_mentions(mentions, spans)
        result = validate_groups(
            groups, mentions, segments, concurrent_personas=concurrent_personas
        )

        # Write group membership back so Phase 6 can retrieve by group.
        group_of: dict[str, str] = {}
        for group in result.groups:
            for mention_id in group.mention_ids:
                group_of[mention_id] = group.id
        for mention in mentions:
            mention.local_group_id = group_of.get(mention.id)
        store.add_mentions(mentions)

        kinship_mentions = _resolve_kinship_mentions(novel_id, chapter, spans, mentions, group_of)
        if kinship_mentions:
            store.add_mentions(kinship_mentions)
        report.kinship_links += len(kinship_mentions)

        recovered = _recover_attributions(store, novel_id, chapter.number, spans, links)

        report.chapters += 1
        report.groups += len(result.groups)
        report.pronoun_links += len(links)
        report.splits += result.split_count
        report.recovered_attributions += recovered
        if result.needs_escalation:
            report.escalated_chapters += 1
        for violation in result.violations:
            report.violations_by_kind[violation.kind] = (
                report.violations_by_kind.get(violation.kind, 0) + 1
            )

        if i % commit_every == 0:
            store.conn.commit()

    store.conn.commit()
    return report


def _resolve_kinship_mentions(
    novel_id: str,
    chapter: Chapter,
    spans: list,  # type: ignore[type-arg]
    mentions: list[Mention],
    group_of: dict[str, str],
) -> list[Mention]:
    """Mint a `Mention` for each resolved bare kinship word ("Uncle", "Aunt", ...).

    These never exist as mentions before this point -- nothing upstream
    proposes a bare role word as a mention candidate (see
    `local.py::find_kinship_terms`). Minted straight into the antecedent's
    local group rather than left to resolve independently, so Phase 6 treats
    "Uncle Gu Yue Dong Tu" and a later bare "Uncle" as what they are: the same
    referent, already established within this chapter.

    The sticky binding (`local.py::resolve_kinship_group`'s rule 2) resets at
    every scene break, same as `speakers/runner.py`'s turn-taking state --
    carrying a family binding across a scene change risks attaching "Uncle" to
    whoever happened to be the last one bound, in a scene they are not even in.
    """
    scene_break_blocks = {b.index for b in chapter.blocks if b.text.strip() == "* * *"}
    block_text_by_index = {b.index: b.text for b in chapter.blocks}
    last_break = -1

    established: dict[str, Mention] = {}
    out: list[Mention] = []
    index = 0
    for span in spans:
        if span.block_index in scene_break_blocks and span.block_index > last_break:
            last_break = span.block_index
            established.clear()
        if span.span_type in (SpanType.NON_DIEGETIC, SpanType.SYSTEM_WINDOW):
            continue
        for term, offset in find_kinship_terms(span.text, span.start):
            key = term.casefold()
            resolved = resolve_kinship_group(
                offset,
                offset + len(term),
                span.block_index,
                mentions,
                established=established.get(key),
                block_text=block_text_by_index.get(span.block_index),
            )
            if resolved is None:
                continue
            antecedent, confidence, rule = resolved
            established[key] = antecedent
            if rule == "kinship_fused":
                # This occurrence is already `antecedent` itself ("Uncle Gu
                # Yue Dong Tu" detected as one mention) -- only the sticky
                # binding needed updating, not a second mention for the same
                # text.
                continue
            group_id = group_of.get(antecedent.id)
            if group_id is None:
                continue
            index += 1
            out.append(
                Mention(
                    id=f"{novel_id}:{chapter.number:g}:kin{index}",
                    novel_id=novel_id,
                    segment_id="",
                    chapter=chapter.number,
                    offset=offset,
                    text=term,
                    alias_type=AliasType.RELATIONAL_DEICTIC,
                    span_type=span.span_type,
                    # Conservative default: a kinship word describes someone's
                    # relation, not necessarily that they are physically in
                    # the scene right now, so this does not assert presence
                    # the way a `PRESENT` mention would for co-presence checks.
                    reference_mode=ReferenceMode.NARRATOR_REFERENCE,
                    confidence=confidence,
                    block_index=span.block_index,
                    local_group_id=group_id,
                )
            )
    return out


def _recover_attributions(
    store: Store,
    novel_id: str,
    chapter_number: float,
    spans: list,  # type: ignore[type-arg]
    links: int,
) -> int:
    """Attribute speech spans whose subject was a pronoun.

    Phase 4 deliberately leaves "he said" unresolved rather than guessing.
    Once the pronoun has an antecedent, the line is attributable at the
    antecedent's confidence -- which is why the two phases run in sequence.
    """
    from echotales.pipeline.anaphora.local import find_pronouns, resolve_pronoun

    stored = {s.id: s for s in store.get_spans(novel_id, chapter_number)}
    mentions = store.get_mentions(novel_id, chapter_number)
    if not mentions:
        return 0

    recovered = 0
    updated = []
    for span in spans:
        existing = stored.get(span.id)
        if existing is None or existing.speaker_self_id:
            continue
        if existing.span_type not in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE):
            continue

        # Look just after the line, where "he said" sits.
        window_start = span.end
        candidates = [
            p
            for p in find_pronouns(span.text, span.start)
            if p[1] >= window_start - len(span.text)
        ]
        if not candidates:
            continue

        _, offset, gender, number = candidates[0]
        resolved = resolve_pronoun(offset, gender, number, mentions)
        if resolved is None:
            continue
        antecedent, confidence, _ = resolved
        existing.speaker_self_id = antecedent.text
        existing.attribution_method = AttributionMethod.CONTEXTUAL_LLM
        # Discount: this is a two-step inference (pronoun -> antecedent ->
        # speaker), so it must not carry the confidence of a direct link.
        existing.confidence = confidence * 0.8
        updated.append(existing)
        recovered += 1

    if updated:
        store.add_spans(updated)
    return recovered
