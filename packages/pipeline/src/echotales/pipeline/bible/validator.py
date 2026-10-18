"""Story Bible delta validator and bitemporal store applicator.

Validates extracted BibleDelta contracts against the existing narrative knowledge graph
in Store:
1. Alias Resolution & Merging: Matches entity labels and aliases against existing characters.
   - Exact match: automatically resolved to existing self_id.
   - Ambiguous similarity: flags a ReviewItem for the Studio human review queue.
2. Monotonicity & Retraction:
   - Verifies attribute continuity across chapters.
   - If a core physical attribute changes without an explicit PersonaShiftDelta, flags
     a conflicting_attribute ReviewItem.
3. Bitemporal Store Mutation:
   - Appends new entities to self_entity with TargetKind.
   - Appends personas to persona table.
   - Binds personas via self_persona_binding with valid DiscoursePosition and interval.
   - Registers alias_binding and attribute rows.
   - Never rewrites past facts; maintains point-in-time auditability.
"""

from __future__ import annotations

import difflib
import time
from dataclasses import dataclass, field
from typing import Any

from echotales.core.enums import AliasType, AssertedBy, Prominence, TargetKind, TruthStatus
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    DiscoursePosition,
    Persona,
    ReviewItem,
    Self,
    SelfPersonaBinding,
)
from echotales.core.store import Store, normalize_alias
from echotales.pipeline.bible.schema import (
    BibleDelta,
    EntityDelta,
    LocationDelta,
    PersonaShiftDelta,
)


@dataclass(slots=True)
class DeltaValidationResult:
    """Outcome of validating and applying a BibleDelta to Store."""

    delta: BibleDelta
    new_self_ids: list[str] = field(default_factory=list)
    merged_self_ids: dict[str, str] = field(default_factory=dict)  # extracted self_id -> resolved self_id
    flagged_review_items: list[ReviewItem] = field(default_factory=list)
    applied_shifts: list[str] = field(default_factory=list)  # persona_ids
    applied_locations: list[str] = field(default_factory=list)  # location_ids
    conflicts: list[str] = field(default_factory=list)


def _compute_similarity(a: str, b: str) -> float:
    """Normalized string similarity between two names."""
    norm_a = normalize_alias(a)
    norm_b = normalize_alias(b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0
    # Name containment (e.g. "Klein" in "Klein Moretti")
    words_a = set(norm_a.split())
    words_b = set(norm_b.split())
    if words_a and words_b and (words_a.issubset(words_b) or words_b.issubset(words_a)):
        return 0.90
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def apply_bible_delta(store: Store, delta: BibleDelta) -> DeltaValidationResult:
    """Validate a BibleDelta against current Store state and apply bitemporal mutations."""
    novel_id = delta.novel_id
    chapter = delta.chapter
    pos = DiscoursePosition(chapter=int(chapter), offset=0)
    interval = FuzzyInterval.open_ended(chapter)

    result = DeltaValidationResult(delta=delta)

    # Pre-fetch existing entities and aliases
    existing_selves = store.all_selves(novel_id)
    existing_aliases = store.all_aliases(novel_id)

    # 1. Process New Entities & Alias Resolution
    for entity in delta.new_entities:
        target_kind = TargetKind.SELF
        if entity.kind in TargetKind.__members__:
            target_kind = TargetKind(entity.kind)

        # Check for exact or ambiguous matches against existing selves
        best_match_self: Self | None = None
        best_match_score = 0.0
        ambiguous_candidates: list[dict[str, Any]] = []

        for existing in existing_selves:
            # Compare canonical label
            score = _compute_similarity(entity.canonical_label, existing.canonical_label)
            if score > best_match_score:
                best_match_score = score
                best_match_self = existing

            if 0.65 <= score < 0.95 and existing.id != entity.self_id:
                ambiguous_candidates.append({
                    "self_id": existing.id,
                    "canonical_label": existing.canonical_label,
                    "similarity": round(score, 3),
                })

            # Compare against existing aliases
            for ab in existing_aliases:
                if ab.target_id == existing.id:
                    alias_score = _compute_similarity(entity.canonical_label, ab.alias)
                    if alias_score > best_match_score:
                        best_match_score = alias_score
                        best_match_self = existing

        # Resolution decision
        resolved_self_id = entity.self_id
        if best_match_self and (best_match_score >= 0.95 or best_match_self.id == entity.self_id):
            # Definite match: merge into existing self
            resolved_self_id = best_match_self.id
            result.merged_self_ids[entity.self_id] = resolved_self_id
        elif ambiguous_candidates:
            # Ambiguous: flag for Studio human review queue
            rev = ReviewItem(
                id=f"rev:{novel_id}:{chapter}:{entity.self_id}",
                novel_id=novel_id,
                chapter=chapter,
                kind="ambiguous_entity_merge",
                message=(
                    f"Entity '{entity.canonical_label}' ({entity.self_id}) closely matches "
                    f"existing character '{ambiguous_candidates[0]['canonical_label']}' "
                    f"({ambiguous_candidates[0]['self_id']}) with score {ambiguous_candidates[0]['similarity']}."
                ),
                candidates=ambiguous_candidates,
                created_at=time.time(),
            )
            store.add_review_item(rev)
            result.flagged_review_items.append(rev)
            resolved_self_id = entity.self_id
            result.new_self_ids.append(resolved_self_id)
        else:
            # Genuinely new entity
            resolved_self_id = entity.self_id
            result.new_self_ids.append(resolved_self_id)

        # Upsert self_entity if not already present
        if store.get_self(resolved_self_id) is None:
            store.add_self(
                Self(
                    id=resolved_self_id,
                    novel_id=novel_id,
                    canonical_label=entity.canonical_label,
                    first_attested_pos=pos,
                    prominence=Prominence.RECURRING,
                    kind=target_kind,
                )
            )

        # Register aliases
        for alias in entity.aliases:
            store.add_alias_binding(
                novel_id,
                AliasBinding(
                    alias=alias,
                    alias_type=AliasType.EPITHET,
                    target_kind=target_kind,
                    target_id=resolved_self_id,
                    timeline_id="MAIN",
                    interval=interval,
                    learned_at_pos=pos,
                    observer_id="reader",
                    asserted_by=AssertedBy.NARRATOR,
                    truth_status=TruthStatus.TRUE,
                ),
            )

        # Monotonicity check on attributes
        existing_attrs = {
            a.key: a.value
            for a in store.get_attributes(target_kind, resolved_self_id)
            if a.truth_status != TruthStatus.FALSE
        }

        for k, v in entity.initial_attributes.items():
            if k in existing_attrs and existing_attrs[k] != v:
                # Contradiction without persona shift
                conflict_msg = (
                    f"Attribute '{k}' contradiction on {resolved_self_id}: "
                    f"earlier='{existing_attrs[k]}', new='{v}' without persona shift"
                )
                result.conflicts.append(conflict_msg)
                rev = ReviewItem(
                    id=f"rev:{novel_id}:{chapter}:{resolved_self_id}:{k}",
                    novel_id=novel_id,
                    chapter=chapter,
                    kind="conflicting_attribute",
                    message=conflict_msg,
                    candidates=[{"key": k, "prior_value": existing_attrs[k], "new_value": v}],
                    created_at=time.time(),
                )
                store.add_review_item(rev)
                result.flagged_review_items.append(rev)
            else:
                store.add_attribute(
                    novel_id,
                    Attribute(
                        target_kind=target_kind,
                        target_id=resolved_self_id,
                        key=k,
                        value=v,
                        timeline_id="MAIN",
                        interval=interval,
                        learned_at_pos=pos,
                        observer_id="reader",
                        asserted_by=AssertedBy.NARRATOR,
                        truth_status=TruthStatus.TRUE,
                    ),
                )

        if entity.suggested_voice_profile:
            store.add_attribute(
                novel_id,
                Attribute(
                    target_kind=target_kind,
                    target_id=resolved_self_id,
                    key="voice_profile",
                    value=entity.suggested_voice_profile,
                    timeline_id="MAIN",
                    interval=interval,
                    learned_at_pos=pos,
                    observer_id="reader",
                    asserted_by=AssertedBy.NARRATOR,
                    truth_status=TruthStatus.TRUE,
                ),
            )

    # 2. Process Persona Shifts
    for shift in delta.persona_shifts:
        # Resolve target self_id if it was merged
        target_self_id = result.merged_self_ids.get(shift.self_id, shift.self_id)

        # Upsert persona
        store.add_persona(
            Persona(
                id=shift.persona_id,
                novel_id=novel_id,
                body_label=shift.description,
                first_attested_pos=pos,
                notes=f"Reason: {shift.reason}",
            )
        )

        # Add bitemporal binding
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id=target_self_id,
                persona_id=shift.persona_id,
                timeline_id="MAIN",
                interval=interval,
                learned_at_pos=pos,
                observer_id="reader",
                truth_status=TruthStatus.TRUE,
            )
        )
        result.applied_shifts.append(shift.persona_id)

        # Outfit override
        if shift.outfit_id:
            store.add_attribute(
                novel_id,
                Attribute(
                    target_kind=TargetKind.PERSONA,
                    target_id=shift.persona_id,
                    key="outfit",
                    value=shift.outfit_id,
                    timeline_id="MAIN",
                    interval=interval,
                    learned_at_pos=pos,
                    observer_id="reader",
                    asserted_by=AssertedBy.NARRATOR,
                    truth_status=TruthStatus.TRUE,
                ),
            )

        # Appearance overrides on persona
        for k, v in shift.appearance_overrides.items():
            store.add_attribute(
                novel_id,
                Attribute(
                    target_kind=TargetKind.PERSONA,
                    target_id=shift.persona_id,
                    key=k,
                    value=v,
                    timeline_id="MAIN",
                    interval=interval,
                    learned_at_pos=pos,
                    observer_id="reader",
                    asserted_by=AssertedBy.NARRATOR,
                    truth_status=TruthStatus.TRUE,
                ),
            )

    # 3. Process Location Deltas
    for loc in delta.location_deltas:
        if store.get_self(loc.location_id) is None:
            store.add_self(
                Self(
                    id=loc.location_id,
                    novel_id=novel_id,
                    canonical_label=loc.canonical_name,
                    first_attested_pos=pos,
                    prominence=Prominence.INCIDENTAL,
                    notes=loc.description,
                    kind=TargetKind.LOCATION,
                )
            )

        if loc.ambience_sound:
            store.add_attribute(
                novel_id,
                Attribute(
                    target_kind=TargetKind.LOCATION,
                    target_id=loc.location_id,
                    key="ambience_sound",
                    value=loc.ambience_sound,
                    timeline_id="MAIN",
                    interval=interval,
                    learned_at_pos=pos,
                    observer_id="reader",
                    asserted_by=AssertedBy.NARRATOR,
                    truth_status=TruthStatus.TRUE,
                ),
            )

        result.applied_locations.append(loc.location_id)

    return result
