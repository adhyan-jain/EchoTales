"""Reveal-Aware Visual Memory for Long-Form Narrative Adaptation.

Implements a provenance-scoped compiler layer that chooses reusable
character-reference assets according to:
1. Story-world time and physical embodiment depicted (Self vs Persona epoch).
2. Information available at the selected narrative/discourse cutoff (k).
3. The intended audience or observer policy (reader vs character vs omniscient).
4. The source facts and prior assets on which each reference depends (transitive lineage).

Design decisions:
- Distinguishes generation-time inputs from pixel claims: this selector
  guarantees provenance admissibility of inputs and conditioning reference
  chains; it does not claim that a diffusion model cannot independently hallucinate.
- Fully conservative: an asset conditioned on parent assets transitively
  inherits all dependencies, cutoffs, and observer constraints of those parents.
- Preserves historical beliefs: facts retracted before cutoff k are rejected,
  while facts retracted after cutoff k were believed at k.
- Separates story position p from discourse cutoff k: supports in-sequence
  spoiler-safe rendering, retrospective flashback rendering, and character-specific views.
- Deterministic: reproducible ordering with inspectable rejection reasons and
  minimal counterexamples. Fallback to prompt-only generation when references are unsafe.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
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
from echotales.core.models import (
    MAIN_TIMELINE,
    DiscoursePosition,
)
from echotales.core.state import StateResolver, observer_scope

if TYPE_CHECKING:
    from echotales.core.store import Store


class VisualAssetKind(StrEnum):
    """Classification of reusable visual assets."""

    #: Standard neutral portrait / character reference sheet.
    CHARACTER_PORTRAIT = "character_portrait"
    #: Specific body epoch or state-transition sheet (e.g. regressed, aged, wounded).
    BODY_STATE = "body_state"
    #: Scene or framing reference for layout/composition.
    COMPOSITION_GUIDE = "composition_guide"


class DisclosurePolicy(StrEnum):
    """View policy governing information disclosure."""

    #: Standard in-sequence rendering: discourse cutoff k matches narrative reading order.
    #: Facts or assets disclosed after k are strictly inadmissible.
    IN_SEQUENCE = "in_sequence"
    #: Retrospective rendering (e.g. flashback to story position p < k):
    #: Permitted to use all facts and assets disclosed to the audience up to discourse cutoff k.
    RETROSPECTIVE = "retrospective"
    #: Omniscient evaluator/system mode: discourse cutoff is ignored (k = infinity).
    OMNISCIENT = "omniscient"


class SelectionStatus(StrEnum):
    """Outcome of visual reference selection."""

    #: An admissible, embodiment-compatible asset was selected.
    SELECTED = "selected"
    #: No reference asset could be safely used; caller must fall back to prompt-only generation.
    FALLBACK_PROMPT_ONLY = "fallback_prompt_only"
    #: The request cannot be safely satisfied (e.g. invalid target entity).
    REJECTED = "rejected"


class RejectionReason(StrEnum):
    """Formal reason code for candidate asset rejection or selection fallback."""

    #: The asset meets all constraints and is admitted.
    ADMISSIBLE = "admissible"
    #: No visual assets are registered for this target entity.
    NO_ASSET_REGISTERED = "no_asset_registered"
    #: Target character has no admissible embodiment bound at (p, k, o).
    NO_ADMISSIBLE_EMBODIMENT = "no_admissible_embodiment"
    #: Asset is tied to a different, incompatible Persona/body epoch.
    EMBODIMENT_MISMATCH = "embodiment_mismatch"
    #: Persona binding is uncertain/plausible and allow_plausible=False.
    EMBODIMENT_UNCERTAIN = "embodiment_uncertain"
    #: Asset depends on facts first disclosed after discourse cutoff k.
    CUTOFF_EXCEEDED = "cutoff_exceeded"
    #: Asset depends on a fact that has been retracted as of cutoff k.
    FACT_RETRACTED = "fact_retracted"
    #: Asset depends on a fact with PLAUSIBLE certainty and allow_plausible=False.
    FACT_UNCERTAINTY_EXCLUDED = "fact_uncertainty_excluded"
    #: Asset observer scope excludes the requested observer, or observer has not witnessed facts.
    OBSERVER_UNAUTHORIZED = "observer_unauthorized"
    #: Asset features or story interval are incompatible with story position p.
    STORY_TIME_INCOMPATIBLE = "story_time_incompatible"
    #: A parent asset conditioned by this asset violates cutoff, embodiment, or observer policy.
    TRANSITIVE_LINEAGE_VIOLATION = "transitive_lineage_violation"
    #: All candidate assets were evaluated and rejected.
    NO_ADMISSIBLE_ASSET = "no_admissible_asset"


@dataclass(frozen=True, slots=True)
class FactProvenance:
    """Provenance record for a single source fact on which a visual asset depends."""

    #: Fact reference string (e.g. "attr:FY:body1:hair_color:black").
    fact_ref: str
    #: Discourse position at which the fact was first narrated/disclosed.
    learned_at_pos: DiscoursePosition
    #: Story-time interval over which the fact is valid.
    valid_interval: FuzzyInterval
    #: Discourse position at which the fact was retracted, if any.
    retracted_at: DiscoursePosition | None = None
    #: Observer who witnessed or asserted the fact.
    observer_id: str = OBSERVER_READER
    #: Truth status of the fact.
    truth_status: TruthStatus = TruthStatus.TRUE
    #: Epistemic certainty of the fact.
    certainty: Certainty = Certainty.CERTAIN
    #: Physical SQLite row ID, if persisted in store.
    source_row_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_ref": self.fact_ref,
            "learned_at_pos": {
                "chapter": self.learned_at_pos.chapter,
                "offset": self.learned_at_pos.offset,
            },
            "valid_interval": {
                "from_lb": self.valid_interval.from_lb,
                "from_ub": self.valid_interval.from_ub,
                "to_lb": self.valid_interval.to_lb,
                "to_ub": self.valid_interval.to_ub,
            },
            "retracted_at": (
                {
                    "chapter": self.retracted_at.chapter,
                    "offset": self.retracted_at.offset,
                }
                if self.retracted_at is not None
                else None
            ),
            "observer_id": self.observer_id,
            "truth_status": self.truth_status.value,
            "certainty": self.certainty.value,
            "source_row_id": self.source_row_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FactProvenance:
        learned = DiscoursePosition(
            chapter=data["learned_at_pos"]["chapter"],
            offset=data["learned_at_pos"].get("offset", 0),
        )
        vi = data["valid_interval"]
        interval = FuzzyInterval(
            from_lb=vi["from_lb"],
            from_ub=vi["from_ub"],
            to_lb=vi["to_lb"],
            to_ub=vi["to_ub"],
        )
        retracted = None
        if data.get("retracted_at") is not None:
            retracted = DiscoursePosition(
                chapter=data["retracted_at"]["chapter"],
                offset=data["retracted_at"].get("offset", 0),
            )
        return cls(
            fact_ref=data["fact_ref"],
            learned_at_pos=learned,
            valid_interval=interval,
            retracted_at=retracted,
            observer_id=data.get("observer_id", OBSERVER_READER),
            truth_status=TruthStatus(data["truth_status"]) if "truth_status" in data else TruthStatus.TRUE,
            certainty=Certainty(data["certainty"]) if "certainty" in data else Certainty.CERTAIN,
            source_row_id=data.get("source_row_id"),
        )


@dataclass(frozen=True, slots=True)
class VisualAssetRecord:
    """The minimal typed representation of a reusable visual asset.

    Every field is justified by the selection algorithm:
    - asset_id, asset_kind: stable identity and modality disambiguation.
    - self_id, persona_id, body_epoch_index: embodiment binding and epoch scoping.
    - story_interval: story-time validity bounds.
    - source_facts, parent_asset_ids: conservative transitive lineage.
    - effective_cutoff: earliest discourse cutoff at which the asset is admissible.
    - observer_scope: observer-facing access control.
    - prompt_digest, image_content_digest, engine_id, checkpoint_id, seed: content-addressed
      reproducibility and separation of generation inputs from pixel claims.
    """

    asset_id: str
    asset_kind: VisualAssetKind
    self_id: str
    persona_id: str
    story_interval: FuzzyInterval
    source_facts: tuple[FactProvenance, ...]
    parent_asset_ids: tuple[str, ...] = ()
    body_epoch_index: int | None = 1
    effective_cutoff: DiscoursePosition = field(default_factory=lambda: DiscoursePosition(chapter=0, offset=0))
    observer_scope: frozenset[str] = frozenset({OBSERVER_READER, OBSERVER_SYSTEM})
    story_pos: float = 0.0
    discourse_cutoff: DiscoursePosition = field(default_factory=lambda: DiscoursePosition(chapter=0, offset=0))
    observer_id: str = OBSERVER_READER
    policy: DisclosurePolicy = DisclosurePolicy.IN_SEQUENCE
    prompt: str = ""
    manifest_path: str = ""
    image_path: str = ""
    prompt_digest: str = ""
    image_content_digest: str = ""
    engine_id: str = "stub"
    checkpoint_id: str = ""
    seed: int = 0
    rendering_params: tuple[tuple[str, str], ...] = ()
    provenance_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_kind": self.asset_kind.value,
            "self_id": self.self_id,
            "persona_id": self.persona_id,
            "story_pos": self.story_pos,
            "discourse_cutoff": {
                "chapter": self.discourse_cutoff.chapter,
                "offset": self.discourse_cutoff.offset,
            },
            "observer_id": self.observer_id,
            "policy": self.policy.value,
            "story_interval": {
                "from_lb": self.story_interval.from_lb,
                "from_ub": self.story_interval.from_ub,
                "to_lb": self.story_interval.to_lb,
                "to_ub": self.story_interval.to_ub,
            },
            "source_facts": [f.to_dict() for f in self.source_facts],
            "parent_asset_ids": list(self.parent_asset_ids),
            "body_epoch_index": self.body_epoch_index,
            "effective_cutoff": {
                "chapter": self.effective_cutoff.chapter,
                "offset": self.effective_cutoff.offset,
            },
            "observer_scope": sorted(self.observer_scope),
            "prompt": self.prompt,
            "image_path": self.image_path,
            "manifest_path": self.manifest_path,
            "prompt_digest": self.prompt_digest,
            "image_content_digest": self.image_content_digest,
            "engine_id": self.engine_id,
            "checkpoint_id": self.checkpoint_id,
            "seed": self.seed,
            "rendering_params": list(self.rendering_params),
            "provenance_version": self.provenance_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualAssetRecord:
        dc = data.get("discourse_cutoff", {"chapter": 0, "offset": 0})
        ec = data.get("effective_cutoff", {"chapter": 0, "offset": 0})
        si = data["story_interval"]
        interval = FuzzyInterval(
            from_lb=si["from_lb"],
            from_ub=si["from_ub"],
            to_lb=si["to_lb"],
            to_ub=si["to_ub"],
        )
        return cls(
            asset_id=data["asset_id"],
            asset_kind=VisualAssetKind(data["asset_kind"]),
            self_id=data["self_id"],
            persona_id=data["persona_id"],
            story_pos=data.get("story_pos", 0.0),
            discourse_cutoff=DiscoursePosition(
                chapter=dc["chapter"], offset=dc.get("offset", 0)
            ),
            observer_id=data.get("observer_id", OBSERVER_READER),
            policy=DisclosurePolicy(data["policy"]) if "policy" in data else DisclosurePolicy.IN_SEQUENCE,
            story_interval=interval,
            source_facts=tuple(FactProvenance.from_dict(f) for f in data.get("source_facts", ())),
            parent_asset_ids=tuple(data.get("parent_asset_ids", ())),
            body_epoch_index=data.get("body_epoch_index", 1),
            effective_cutoff=DiscoursePosition(
                chapter=ec["chapter"], offset=ec.get("offset", 0)
            ),
            observer_scope=frozenset(data.get("observer_scope", {OBSERVER_READER, OBSERVER_SYSTEM})),
            prompt=data.get("prompt", ""),
            image_path=data.get("image_path", ""),
            manifest_path=data.get("manifest_path", ""),
            prompt_digest=data.get("prompt_digest", ""),
            image_content_digest=data.get("image_content_digest", ""),
            engine_id=data.get("engine_id", "stub"),
            checkpoint_id=data.get("checkpoint_id", ""),
            seed=data.get("seed", 0),
            rendering_params=tuple(tuple(p) for p in data.get("rendering_params", ())),
            provenance_version=data.get("provenance_version", "1.0"),
        )

    def save_manifest(self, path: str | Path) -> None:
        """Serialize this visual asset record to a JSON provenance manifest."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load_manifest(cls, path: str | Path) -> VisualAssetRecord:
        """Load a visual asset record from a JSON provenance manifest."""
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def transitive_facts(
        self, registry: Mapping[str, VisualAssetRecord], visited: set[str] | None = None
    ) -> set[FactProvenance]:
        """Compute the transitive closure of all source facts across this asset and its parents."""
        if visited is None:
            visited = set()
        if self.asset_id in visited:
            return set()
        visited.add(self.asset_id)

        facts = set(self.source_facts)
        for parent_id in self.parent_asset_ids:
            parent = registry.get(parent_id)
            if parent is not None:
                facts.update(parent.transitive_facts(registry, visited))
        return facts

    def transitive_parent_ids(
        self, registry: Mapping[str, VisualAssetRecord], visited: set[str] | None = None
    ) -> set[str]:
        """Compute all direct and indirect parent asset IDs."""
        if visited is None:
            visited = set()
        if self.asset_id in visited:
            return set()
        visited.add(self.asset_id)

        parents = set(self.parent_asset_ids)
        for parent_id in self.parent_asset_ids:
            parent = registry.get(parent_id)
            if parent is not None:
                parents.update(parent.transitive_parent_ids(registry, visited))
        return parents

    def compute_effective_cutoff(
        self, registry: Mapping[str, VisualAssetRecord]
    ) -> DiscoursePosition:
        """Calculate the earliest discourse cutoff at which all transitive facts and parents are disclosed."""
        facts = self.transitive_facts(registry)
        positions = [f.learned_at_pos for f in facts]
        if self.parent_asset_ids:
            for pid in self.transitive_parent_ids(registry):
                parent = registry.get(pid)
                if parent is not None:
                    positions.append(parent.effective_cutoff)
        if not positions:
            return self.effective_cutoff
        return max(positions)


@dataclass(frozen=True, slots=True)
class VisualRequest:
    """Request for a character reference asset under explicit narrative coordinates.

    Story-world position `story_pos` (p) and narrative cutoff `discourse_cutoff` (k)
    are strictly separated to prevent silent conflation of story time and reveal time.
    """

    self_id: str
    story_pos: float
    discourse_cutoff: DiscoursePosition
    observer_id: str = OBSERVER_READER
    policy: DisclosurePolicy = DisclosurePolicy.IN_SEQUENCE
    allow_plausible: bool = False
    target_persona_id: str | None = None
    modality: str = "character_reference"
    requested_asset_kind: VisualAssetKind = VisualAssetKind.CHARACTER_PORTRAIT
    timeline_id: str = MAIN_TIMELINE


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    """Detailed evaluation report for a single candidate visual asset."""

    asset_id: str
    admissible: bool
    rejection_reason: RejectionReason
    details: str = ""
    counterexample_ref: str | None = None


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Deterministic selection decision with inspectable audit trail."""

    status: SelectionStatus
    selected_asset: VisualAssetRecord | None
    reason: RejectionReason
    message: str
    candidate_evaluations: tuple[CandidateEvaluation, ...] = ()
    permitted_facts: tuple[str, ...] = ()


class VisualAssetRegistry:
    """In-memory or scratch registry of visual assets with provenance indexing."""

    def __init__(self) -> None:
        self._assets_by_id: dict[str, VisualAssetRecord] = {}
        self._assets_by_self: dict[str, list[VisualAssetRecord]] = {}

    def register(self, asset: VisualAssetRecord) -> None:
        """Register a visual asset, ensuring transitive cutoff consistency."""
        computed_cutoff = asset.compute_effective_cutoff(self._assets_by_id)
        if computed_cutoff > asset.effective_cutoff:
            asset = VisualAssetRecord(
                asset_id=asset.asset_id,
                asset_kind=asset.asset_kind,
                self_id=asset.self_id,
                persona_id=asset.persona_id,
                story_interval=asset.story_interval,
                source_facts=asset.source_facts,
                parent_asset_ids=asset.parent_asset_ids,
                body_epoch_index=asset.body_epoch_index,
                effective_cutoff=computed_cutoff,
                observer_scope=asset.observer_scope,
                image_path=asset.image_path,
                prompt_digest=asset.prompt_digest,
                image_content_digest=asset.image_content_digest,
                engine_id=asset.engine_id,
                checkpoint_id=asset.checkpoint_id,
                seed=asset.seed,
                rendering_params=asset.rendering_params,
                provenance_version=asset.provenance_version,
            )
        self._assets_by_id[asset.asset_id] = asset
        self._assets_by_self.setdefault(asset.self_id, []).append(asset)

    def get(self, asset_id: str) -> VisualAssetRecord | None:
        return self._assets_by_id.get(asset_id)

    def find_for_self(
        self, self_id: str, kind: VisualAssetKind | None = None
    ) -> list[VisualAssetRecord]:
        candidates = self._assets_by_self.get(self_id, [])
        if kind is not None:
            return [c for c in candidates if c.asset_kind == kind]
        return list(candidates)

    def as_mapping(self) -> Mapping[str, VisualAssetRecord]:
        return self._assets_by_id


class VisualMemorySelector:
    """Provenance-scoped deterministic compiler for visual reference reuse."""

    def __init__(
        self,
        store: Store,
        *,
        novel_id: str = "",
        resolver: StateResolver | None = None,
    ) -> None:
        self.store = store
        self.novel_id = novel_id
        self.resolver = resolver or StateResolver(store, novel_id)

    def evaluate_candidate(
        self,
        candidate: VisualAssetRecord,
        request: VisualRequest,
        registry: VisualAssetRegistry,
        admissible_personas: set[str],
        observations: Mapping[str, DiscoursePosition] | None = None,
    ) -> CandidateEvaluation:
        """Evaluate a candidate asset against the request policy and 5 correctness gates."""
        mapping = registry.as_mapping()

        # Gate 1 — Embodiment compatibility (Property R2, Case C)
        if candidate.persona_id not in admissible_personas:
            return CandidateEvaluation(
                asset_id=candidate.asset_id,
                admissible=False,
                rejection_reason=RejectionReason.EMBODIMENT_MISMATCH,
                details=(
                    f"Asset persona '{candidate.persona_id}' not in admissible personas "
                    f"{sorted(admissible_personas)} for Self '{request.self_id}' at story pos {request.story_pos}"
                ),
            )

        cert = candidate.story_interval.contains(request.story_pos)
        if cert is Certainty.EXCLUDED:
            return CandidateEvaluation(
                asset_id=candidate.asset_id,
                admissible=False,
                rejection_reason=RejectionReason.STORY_TIME_INCOMPATIBLE,
                details=(
                    f"Story interval {candidate.story_interval} excludes story pos {request.story_pos}"
                ),
            )
        if cert is Certainty.PLAUSIBLE and not request.allow_plausible:
            return CandidateEvaluation(
                asset_id=candidate.asset_id,
                admissible=False,
                rejection_reason=RejectionReason.EMBODIMENT_UNCERTAIN,
                details=(
                    f"Story interval {candidate.story_interval} is only plausible at {request.story_pos}"
                ),
            )

        # Gate 2 — Observer authorization (Case D)
        if request.observer_id != OBSERVER_SYSTEM:
            scope = observer_scope(request.observer_id)
            if scope is not None and not candidate.observer_scope.intersection(scope | {request.observer_id}):
                return CandidateEvaluation(
                    asset_id=candidate.asset_id,
                    admissible=False,
                    rejection_reason=RejectionReason.OBSERVER_UNAUTHORIZED,
                    details=(
                        f"Observer '{request.observer_id}' not in asset observer scope {sorted(candidate.observer_scope)}"
                    ),
                )

        # Gate 3 — Missing / Broken parent lineage (Property R5)
        for parent_id in candidate.parent_asset_ids:
            if parent_id not in mapping:
                return CandidateEvaluation(
                    asset_id=candidate.asset_id,
                    admissible=False,
                    rejection_reason=RejectionReason.TRANSITIVE_LINEAGE_VIOLATION,
                    details=f"Parent asset '{parent_id}' not found in registry",
                    counterexample_ref=parent_id,
                )

        # Gate 4 — Transitive facts: Cutoff, Retraction, and Certainty (Properties R1, R3, R4, R5, Case A, Case B, Case E)
        transitive_facts = candidate.transitive_facts(mapping)

        # Retrospective vs In-Sequence disclosure cutoff
        is_omniscient = (
            request.policy is DisclosurePolicy.OMNISCIENT
            or request.observer_id == OBSERVER_SYSTEM
        )

        for fact in transitive_facts:
            # Observer observation check for non-reader character observers
            if (
                not is_omniscient
                and request.observer_id not in (OBSERVER_READER, OBSERVER_SYSTEM)
            ):
                if fact.observer_id != request.observer_id:
                    witnessed_at = observations.get(fact.fact_ref) if observations else None
                    if witnessed_at is None:
                        return CandidateEvaluation(
                            asset_id=candidate.asset_id,
                            admissible=False,
                            rejection_reason=RejectionReason.OBSERVER_UNAUTHORIZED,
                            details=(
                                f"Character observer '{request.observer_id}' has not witnessed fact '{fact.fact_ref}'"
                            ),
                            counterexample_ref=fact.fact_ref,
                        )
                    if witnessed_at > request.discourse_cutoff:
                        return CandidateEvaluation(
                            asset_id=candidate.asset_id,
                            admissible=False,
                            rejection_reason=RejectionReason.CUTOFF_EXCEEDED,
                            details=(
                                f"Fact '{fact.fact_ref}' witnessed at {witnessed_at} > cutoff {request.discourse_cutoff}"
                            ),
                            counterexample_ref=fact.fact_ref,
                        )

            # Disclosure cutoff check
            if not is_omniscient:
                if fact.learned_at_pos > request.discourse_cutoff:
                    return CandidateEvaluation(
                        asset_id=candidate.asset_id,
                        admissible=False,
                        rejection_reason=RejectionReason.CUTOFF_EXCEEDED,
                        details=(
                            f"Fact '{fact.fact_ref}' first learned at {fact.learned_at_pos} > cutoff {request.discourse_cutoff}"
                        ),
                        counterexample_ref=fact.fact_ref,
                    )

                # Retraction check: if retracted at or before cutoff k, fact is retracted
                if fact.retracted_at is not None and fact.retracted_at <= request.discourse_cutoff:
                    return CandidateEvaluation(
                        asset_id=candidate.asset_id,
                        admissible=False,
                        rejection_reason=RejectionReason.FACT_RETRACTED,
                        details=(
                            f"Fact '{fact.fact_ref}' was retracted at {fact.retracted_at} <= cutoff {request.discourse_cutoff}"
                        ),
                        counterexample_ref=fact.fact_ref,
                    )

            # Fact certainty check (Case E)
            if fact.certainty is Certainty.PLAUSIBLE and not request.allow_plausible:
                return CandidateEvaluation(
                    asset_id=candidate.asset_id,
                    admissible=False,
                    rejection_reason=RejectionReason.FACT_UNCERTAINTY_EXCLUDED,
                    details=f"Fact '{fact.fact_ref}' has certainty PLAUSIBLE and allow_plausible=False",
                    counterexample_ref=fact.fact_ref,
                )

        return CandidateEvaluation(
            asset_id=candidate.asset_id,
            admissible=True,
            rejection_reason=RejectionReason.ADMISSIBLE,
            details="All embodiment, observer, disclosure, and lineage gates passed",
        )

    def select(
        self,
        request: VisualRequest,
        registry: VisualAssetRegistry,
    ) -> SelectionResult:
        """Deterministically select an admissible visual reference asset or return explicit fallback."""
        effective_k = (
            DiscoursePosition(chapter=9999999, offset=0)
            if (
                request.policy is DisclosurePolicy.OMNISCIENT
                or request.observer_id == OBSERVER_SYSTEM
            )
            else request.discourse_cutoff
        )

        # 1. Resolve admissible persona bindings for target Self at (p, k, o)
        state_res = self.resolver.state_of(
            target_kind=TargetKind.SELF,
            target_id=request.self_id,
            position=request.story_pos,
            knowledge_pos=effective_k,
            observer_id=request.observer_id,
            timeline_id=request.timeline_id,
            include_plausible=request.allow_plausible,
        )

        admissible_personas = set(state_res.persona_ids)
        if request.target_persona_id is not None:
            admissible_personas = admissible_personas.intersection({request.target_persona_id})

        # Pre-resolve permitted facts for safe prompt-only fallback
        permitted_facts: list[str] = [f"attr:{k}={v}" for k, v in state_res.attributes.items()]
        for pid in sorted(admissible_personas):
            p_res = self.resolver.state_of(
                target_kind=TargetKind.PERSONA,
                target_id=pid,
                position=request.story_pos,
                knowledge_pos=effective_k,
                observer_id=request.observer_id,
                timeline_id=request.timeline_id,
                include_plausible=request.allow_plausible,
            )
            for k, v in sorted(p_res.attributes.items()):
                permitted_facts.append(f"attr:{pid}:{k}={v}")

        if not admissible_personas:
            return SelectionResult(
                status=SelectionStatus.FALLBACK_PROMPT_ONLY,
                selected_asset=None,
                reason=RejectionReason.NO_ADMISSIBLE_EMBODIMENT,
                message=(
                    f"No admissible embodiment persona found for Self '{request.self_id}' "
                    f"at story pos {request.story_pos}, cutoff {request.discourse_cutoff}, observer '{request.observer_id}'"
                ),
                permitted_facts=tuple(permitted_facts),
            )

        # 2. Retrieve candidates from registry
        candidates = registry.find_for_self(request.self_id, request.requested_asset_kind)
        if not candidates:
            return SelectionResult(
                status=SelectionStatus.FALLBACK_PROMPT_ONLY,
                selected_asset=None,
                reason=RejectionReason.NO_ASSET_REGISTERED,
                message=f"No visual assets registered for Self '{request.self_id}' of kind '{request.requested_asset_kind}'",
                permitted_facts=tuple(permitted_facts),
            )

        # Fetch observations if character observer
        observations: Mapping[str, DiscoursePosition] | None = None
        if request.observer_id not in (OBSERVER_READER, OBSERVER_SYSTEM):
            observations = self.store.observations_for(request.observer_id)

        # 3. Evaluate each candidate against correctness gates
        evaluations: list[CandidateEvaluation] = []
        admissible_assets: list[VisualAssetRecord] = []

        for candidate in candidates:
            ev = self.evaluate_candidate(
                candidate,
                request,
                registry,
                admissible_personas,
                observations=observations,
            )
            evaluations.append(ev)
            if ev.admissible:
                admissible_assets.append(candidate)

        # 4. If none admissible, report explicit fallback (Property R6)
        if not admissible_assets:
            primary_reason = evaluations[0].rejection_reason if evaluations else RejectionReason.NO_ADMISSIBLE_ASSET
            return SelectionResult(
                status=SelectionStatus.FALLBACK_PROMPT_ONLY,
                selected_asset=None,
                reason=primary_reason,
                message=f"All {len(candidates)} candidate assets rejected: {evaluations[0].details}",
                candidate_evaluations=tuple(evaluations),
                permitted_facts=tuple(permitted_facts),
            )

        # 5. Deterministic tie-breaking among admissible assets
        def _sort_key(asset: VisualAssetRecord) -> tuple[int, float, int, str]:
            # Preferred persona: match lead persona
            lead_persona = state_res.persona_ids[0] if state_res.persona_ids else ""
            persona_pref = 0 if asset.persona_id == lead_persona else 1
            # Interval proximity: distance between story_pos and interval midpoint
            mid = (asset.story_interval.from_lb + (asset.story_interval.to_ub or asset.story_interval.from_lb)) / 2.0
            dist = abs(mid - request.story_pos)
            # Cutoff informativeness: later cutoff carries more permitted knowledge
            cutoff_val = -asset.effective_cutoff.as_sortable()
            # Stable identifier
            return (persona_pref, dist, cutoff_val, asset.asset_id)

        admissible_assets.sort(key=_sort_key)
        chosen = admissible_assets[0]

        return SelectionResult(
            status=SelectionStatus.SELECTED,
            selected_asset=chosen,
            reason=RejectionReason.ADMISSIBLE,
            message=f"Selected asset '{chosen.asset_id}' for persona '{chosen.persona_id}'",
            candidate_evaluations=tuple(evaluations),
            permitted_facts=tuple(permitted_facts),
        )


def compute_asset_input_digest(
    prompt: str,
    rendering_params: Mapping[str, Any] | None = None,
    parent_digests: Sequence[str] = (),
) -> str:
    """Compute deterministic SHA-256 digest of generation inputs."""
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    if rendering_params:
        for k, v in sorted(rendering_params.items()):
            h.update(f"::{k}={v}".encode("utf-8"))
    for pd in sorted(parent_digests):
        h.update(f"::parent={pd}".encode("utf-8"))
    return h.hexdigest()
