"""Cutoff-scoped character reference asset emission.

Part of Reveal-Aware Visual Memory for Long-Form Narrative Adaptation (Phase 2).
Enforces strict decoupling of story position p from discourse cutoff k.
Assembles reference prompts strictly from facts admissible under (p, k, o, Pi),
and emits a verifiable JSON provenance manifest alongside the asset.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from echotales.core.enums import (
    OBSERVER_READER,
    OBSERVER_SYSTEM,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import Certainty, FuzzyInterval
from echotales.core.models import MAIN_TIMELINE, DiscoursePosition
from echotales.core.readset import observable_ref
from echotales.core.state import StateResolver, current_bindings, observer_scope
from echotales.core.visual_memory import (
    DisclosurePolicy,
    FactProvenance,
    RejectionReason,
    VisualAssetKind,
    VisualAssetRecord,
    VisualAssetRegistry,
)
from echotales.pipeline.persona.canon import apply_canon
from echotales.pipeline.persona.reference_gen import (
    build_reference_prompt,
    reference_negative,
)
from echotales.pipeline.resolve.appearance_extract import APPEARANCE_KEYS

if TYPE_CHECKING:
    from echotales.core.store import Store
    from echotales.pipeline.render.panels import PanelImageEngine

log = logging.getLogger(__name__)


class EmissionStatus(StrEnum):
    """Status outcome of cutoff-scoped asset emission."""

    #: Asset successfully compiled and emitted with full provenance.
    SUCCESS = "success"
    #: Request was rejected due to policy, cutoff, embodiment, or lineage violation.
    REJECTED = "rejected"
    #: No grounded appearance attributes were admissible; fallback prompt only.
    FALLBACK_PROMPT_ONLY = "fallback_prompt_only"


@dataclass(frozen=True, slots=True)
class ScopedEmissionResult:
    """Outcome of emit_scoped_reference."""

    status: EmissionStatus
    asset_record: VisualAssetRecord | None = None
    prompt: str = ""
    manifest_path: str = ""
    image_path: str = ""
    rejection_reasons: tuple[RejectionReason, ...] = ()
    diagnostics: tuple[str, ...] = ()


def emit_scoped_reference(
    store: Store,
    novel_id: str,
    self_id: str,
    *,
    story_pos: float,
    discourse_cutoff: DiscoursePosition,
    observer_id: str = OBSERVER_READER,
    policy: DisclosurePolicy = DisclosurePolicy.IN_SEQUENCE,
    persona_id: str | None = None,
    timeline_id: str = MAIN_TIMELINE,
    task: str = "character_reference",
    asset_kind: VisualAssetKind = VisualAssetKind.CHARACTER_PORTRAIT,
    body_epoch_index: int | None = 1,
    engine: PanelImageEngine | None = None,
    engine_id: str = "stub",
    out_dir: str | Path | None = None,
    allow_plausible: bool = False,
    parent_asset_ids: Sequence[str] = (),
    parent_assets: Mapping[str, VisualAssetRecord] | None = None,
    registry: VisualAssetRegistry | None = None,
    include_canon: bool = False,
    dry_run: bool = False,
    seed: int = 0,
    width: int = 768,
    height: int = 1024,
    checkpoint_id: str = "",
    rendering_params: Sequence[tuple[str, str]] = (),
    gender: str | None = None,
    age_band: str | None = None,
    detailed: bool = True,
) -> ScopedEmissionResult:
    """Generate a reusable visual reference asset scoped strictly to narrative coordinates.

    Coordinates:
    - story_pos (p): story-world time being depicted.
    - discourse_cutoff (k): narrative reveal boundary.
    - observer_id (o): intended audience/character viewpoint.
    - policy (Pi): disclosure policy (IN_SEQUENCE, RETROSPECTIVE, OMNISCIENT).

    Decoupling guarantee:
    p and k are independent coordinates. In retrospective rendering (e.g. flashback to
    p=5 with cutoff k=100), facts revealed up to k=100 that held at p=5 are admitted.
    In sequential rendering (p=5, k=5), facts revealed at k > 5 are strictly excluded,
    preventing spoiler contamination in early reference sheets.
    """
    # 1. Determine effective knowledge cutoff
    if policy is DisclosurePolicy.OMNISCIENT or observer_id == OBSERVER_SYSTEM:
        effective_cutoff = DiscoursePosition(chapter=10**6, offset=0)
    else:
        effective_cutoff = discourse_cutoff

    resolver = StateResolver(store, novel_id, default_observer=observer_id)

    # 2. Embodiment validation: Self -> Persona
    self_state = resolver.state_of(
        self_id,
        target_kind=TargetKind.SELF,
        timeline_id=timeline_id,
        position=story_pos,
        observer_id=observer_id,
        knowledge_pos=effective_cutoff,
        include_plausible=allow_plausible,
    )

    active_personas = self_state.persona_ids
    if persona_id is not None:
        if persona_id not in active_personas:
            # Check why it is not active
            bindings = current_bindings(store.get_self_persona_bindings(self_id=self_id))
            target_binding = next((b for b in bindings if b.persona_id == persona_id), None)
            if target_binding is not None:
                if target_binding.interval.contains(story_pos) == Certainty.EXCLUDED:
                    return ScopedEmissionResult(
                        status=EmissionStatus.REJECTED,
                        rejection_reasons=(RejectionReason.EMBODIMENT_MISMATCH,),
                        diagnostics=(
                            f"Persona {persona_id} interval {target_binding.interval} does not contain story_pos {story_pos}",
                        ),
                    )
                if target_binding.learned_at_pos > effective_cutoff and observer_id != OBSERVER_SYSTEM:
                    return ScopedEmissionResult(
                        status=EmissionStatus.REJECTED,
                        rejection_reasons=(RejectionReason.CUTOFF_EXCEEDED,),
                        diagnostics=(
                            f"Persona binding {persona_id} learned at {target_binding.learned_at_pos} exceeds cutoff {effective_cutoff}",
                        ),
                    )
                if (
                    target_binding.interval.contains(story_pos) == Certainty.PLAUSIBLE
                    and not allow_plausible
                ):
                    return ScopedEmissionResult(
                        status=EmissionStatus.REJECTED,
                        rejection_reasons=(RejectionReason.EMBODIMENT_UNCERTAIN,),
                        diagnostics=(
                            f"Persona binding {persona_id} certainty is PLAUSIBLE at story_pos {story_pos} and allow_plausible=False",
                        ),
                    )
                return ScopedEmissionResult(
                    status=EmissionStatus.REJECTED,
                    rejection_reasons=(RejectionReason.NO_ADMISSIBLE_EMBODIMENT,),
                    diagnostics=(
                        f"Persona {persona_id} not visible to observer {observer_id} at cutoff {effective_cutoff}",
                    ),
                )
            else:
                return ScopedEmissionResult(
                    status=EmissionStatus.REJECTED,
                    rejection_reasons=(RejectionReason.EMBODIMENT_MISMATCH,),
                    diagnostics=(f"Persona {persona_id} is not bound to self {self_id}",),
                )
        active_persona_id = persona_id
    else:
        if not active_personas:
            return ScopedEmissionResult(
                status=EmissionStatus.REJECTED,
                rejection_reasons=(RejectionReason.NO_ADMISSIBLE_EMBODIMENT,),
                diagnostics=(
                    f"No admissible embodiment for {self_id} at story_pos {story_pos}, cutoff {effective_cutoff}, observer {observer_id}",
                ),
            )
        active_persona_id = active_personas[0]

    # 3. Transitive Parent Lineage Verification
    lookup: dict[str, VisualAssetRecord] = {}
    if parent_assets:
        lookup.update(parent_assets)
    if registry:
        lookup.update(registry.as_mapping())

    for pid in parent_asset_ids:
        parent = lookup.get(pid)
        if parent is None:
            return ScopedEmissionResult(
                status=EmissionStatus.REJECTED,
                rejection_reasons=(RejectionReason.TRANSITIVE_LINEAGE_VIOLATION,),
                diagnostics=(f"Parent asset {pid} not found in parent_assets or registry",),
            )
        # Check parent cutoff
        if parent.effective_cutoff > effective_cutoff and policy is not DisclosurePolicy.OMNISCIENT:
            return ScopedEmissionResult(
                status=EmissionStatus.REJECTED,
                rejection_reasons=(RejectionReason.CUTOFF_EXCEEDED, RejectionReason.TRANSITIVE_LINEAGE_VIOLATION),
                diagnostics=(
                    f"Parent asset {pid} effective cutoff {parent.effective_cutoff} exceeds request cutoff {effective_cutoff}",
                ),
            )
        # Check parent embodiment
        if parent.self_id != self_id or parent.persona_id != active_persona_id:
            return ScopedEmissionResult(
                status=EmissionStatus.REJECTED,
                rejection_reasons=(RejectionReason.EMBODIMENT_MISMATCH, RejectionReason.TRANSITIVE_LINEAGE_VIOLATION),
                diagnostics=(
                    f"Parent asset {pid} embodiment ({parent.self_id}, {parent.persona_id}) incompatible with ({self_id}, {active_persona_id})",
                ),
            )
        # Check observer visibility
        allowed_scopes = observer_scope(observer_id)
        if allowed_scopes is not None and observer_id not in parent.observer_scope:
            return ScopedEmissionResult(
                status=EmissionStatus.REJECTED,
                rejection_reasons=(RejectionReason.OBSERVER_UNAUTHORIZED, RejectionReason.TRANSITIVE_LINEAGE_VIOLATION),
                diagnostics=(
                    f"Parent asset {pid} observer scope {parent.observer_scope} excludes observer {observer_id}",
                ),
            )
        # Check parent transitive facts for retractions
        parent_facts = parent.transitive_facts(lookup)
        for pf in parent_facts:
            if pf.retracted_at is not None and effective_cutoff >= pf.retracted_at:
                return ScopedEmissionResult(
                    status=EmissionStatus.REJECTED,
                    rejection_reasons=(RejectionReason.FACT_RETRACTED, RejectionReason.TRANSITIVE_LINEAGE_VIOLATION),
                    diagnostics=(
                        f"Parent asset {pid} depends on retracted fact {pf.fact_ref} (retracted at {pf.retracted_at})",
                    ),
                )
            if pf.learned_at_pos > effective_cutoff and policy is not DisclosurePolicy.OMNISCIENT:
                return ScopedEmissionResult(
                    status=EmissionStatus.REJECTED,
                    rejection_reasons=(RejectionReason.CUTOFF_EXCEEDED, RejectionReason.TRANSITIVE_LINEAGE_VIOLATION),
                    diagnostics=(
                        f"Parent asset {pid} depends on fact {pf.fact_ref} learned at {pf.learned_at_pos} > cutoff {effective_cutoff}",
                    ),
                )

    # 4. Resolve admissible attributes with full provenance
    admissible_attrs = resolver.resolve_admissible_attributes(
        active_persona_id,
        target_kind=TargetKind.PERSONA,
        timeline_id=timeline_id,
        position=story_pos,
        observer_id=observer_id,
        knowledge_pos=effective_cutoff,
        include_plausible=allow_plausible,
    )

    appearance: dict[str, str] = {}
    source_facts_list: list[FactProvenance] = []
    for attr in admissible_attrs:
        cert = attr.interval.contains(story_pos)
        prov = FactProvenance(
            fact_ref=observable_ref(attr),
            learned_at_pos=attr.learned_at_pos,
            valid_interval=attr.interval,
            retracted_at=attr.retracted_at,
            observer_id=attr.observer_id,
            truth_status=attr.truth_status,
            certainty=cert,
            source_row_id=attr.source_row_id,
        )
        source_facts_list.append(prov)
        if attr.key in APPEARANCE_KEYS and attr.value:
            appearance[attr.key] = attr.value

    if include_canon:
        appearance = apply_canon(novel_id, self_id, appearance, active_persona_id)

    # Demographics
    attr_map = {a.key: a.value for a in admissible_attrs}
    resolved_gender = gender if gender is not None else attr_map.get("gender", appearance.get("gender", "unknown"))
    resolved_age_band = age_band if age_band is not None else attr_map.get("age_band", appearance.get("age_band", "adult"))

    # 5. Build prompt strictly from admissible attributes
    self_entity = store.get_self(self_id)
    label = str(getattr(self_entity, "canonical_label", self_id)) if self_entity is not None else self_id
    prompt = build_reference_prompt(
        label,
        appearance,
        gender=resolved_gender,
        age_band=resolved_age_band,
        detailed=detailed,
        solo=True,
        novel_id=novel_id,
    )
    prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    # 6. Compute bounds & effective cutoff
    bindings = current_bindings(store.get_self_persona_bindings(self_id=self_id))
    binding = next((b for b in bindings if b.persona_id == active_persona_id), None)
    story_interval = binding.interval if binding is not None else FuzzyInterval.point_known(story_pos, story_pos)

    fact_cutoffs = [f.learned_at_pos for f in source_facts_list]
    parent_cutoffs = [lookup[p].effective_cutoff for p in parent_asset_ids if p in lookup]
    all_cutoffs = fact_cutoffs + parent_cutoffs
    record_effective_cutoff = max(all_cutoffs, default=discourse_cutoff)

    asset_id = f"ref_{novel_id}_{self_id}_{active_persona_id}_p{int(story_pos)}_k{discourse_cutoff.chapter}_{prompt_digest[:8]}"

    if observer_id in (OBSERVER_READER, OBSERVER_SYSTEM):
        asset_observer_scope = frozenset({OBSERVER_READER, OBSERVER_SYSTEM})
    else:
        asset_observer_scope = frozenset({observer_id, OBSERVER_SYSTEM})

    # 7. File paths & Image generation
    image_file = None
    manifest_file = None
    if out_dir is not None:
        out_path = Path(out_dir)
        image_file = out_path / f"{asset_id}.png"
        manifest_file = out_path / f"{asset_id}_manifest.json"

    image_content_digest = ""
    if not dry_run and image_file is not None:
        from echotales.pipeline.render.panels import PanelImageRequest, get_engine
        img_engine = engine or get_engine("stub")
        image_file.parent.mkdir(parents=True, exist_ok=True)
        img_engine.generate(
            PanelImageRequest(
                prompt=prompt,
                out_path=image_file,
                negative_prompt=reference_negative(novel_id),
                width=width,
                height=height,
                seed=seed,
            )
        )
        if image_file.exists():
            image_content_digest = hashlib.sha256(image_file.read_bytes()).hexdigest()[:16]

    record = VisualAssetRecord(
        asset_id=asset_id,
        asset_kind=asset_kind,
        self_id=self_id,
        persona_id=active_persona_id,
        story_interval=story_interval,
        source_facts=tuple(source_facts_list),
        parent_asset_ids=tuple(parent_asset_ids),
        body_epoch_index=body_epoch_index,
        effective_cutoff=record_effective_cutoff,
        observer_scope=asset_observer_scope,
        story_pos=story_pos,
        discourse_cutoff=discourse_cutoff,
        observer_id=observer_id,
        policy=policy,
        prompt=prompt,
        manifest_path=str(manifest_file) if manifest_file else "",
        image_path=str(image_file) if image_file else "",
        prompt_digest=prompt_digest,
        image_content_digest=image_content_digest,
        engine_id=engine_id or getattr(engine, "name", "stub"),
        checkpoint_id=checkpoint_id,
        seed=seed,
        rendering_params=tuple(rendering_params),
    )

    if not dry_run and manifest_file is not None:
        record.save_manifest(manifest_file)

    if registry is not None:
        registry.register(record)

    status = EmissionStatus.SUCCESS if appearance else EmissionStatus.FALLBACK_PROMPT_ONLY
    return ScopedEmissionResult(
        status=status,
        asset_record=record,
        prompt=prompt,
        manifest_path=str(manifest_file) if manifest_file else "",
        image_path=str(image_file) if image_file else "",
    )
