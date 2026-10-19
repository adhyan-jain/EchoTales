"""Model-free correctness tests for Reveal-Aware Visual Memory.

Verifies the six correctness properties (R1-R6) and conceptual cases (A-E):
- R1 — Provenance admissibility: transitive source-fact lineage must be admissible under the request policy.
- R2 — Embodiment compatibility: reference tied to incompatible body epoch must not be selected.
- R3 — Cutoff independence: adding facts/assets disclosed after cutoff k does not alter selection for <= k.
- R4 — Retrospective distinction: request at p with k > p behaves according to explicit policy, not k = p.
- R5 — Transitive lineage: reference inheriting from parent reference inherits parent dependencies.
- R6 — Conservative fallback: explicit fallback with reason and permitted facts when no reference is safe.

All tests are model-free (no GPU, no diffusion models, deterministic SQLite scratch databases).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from echotales.core.enums import (
    OBSERVER_READER,
    OBSERVER_SYSTEM,
    TargetKind,
)
from echotales.core.interval import Certainty, FuzzyInterval
from echotales.core.models import (
    Attribute,
    DiscoursePosition,
    Observation,
    Persona,
    Self,
    SelfPersonaBinding,
)
from echotales.core.readset import fact_ref
from echotales.core.store import Store
from echotales.core.visual_memory import (
    DisclosurePolicy,
    FactProvenance,
    RejectionReason,
    SelectionStatus,
    VisualAssetKind,
    VisualAssetRecord,
    VisualAssetRegistry,
    VisualMemorySelector,
    VisualRequest,
)

SELF_ID = "n:self:fang_yuan"
BODY1 = "n:self:fang_yuan:body1"
BODY2 = "n:self:fang_yuan:body2"


@pytest.fixture
def base_store(tmp_path: pytest.TempPathFactory) -> Store:
    """Fixture creating a scratch store with a two-body character."""
    db_path = tmp_path / "test_vm.db"
    store = Store(str(db_path))
    store.add_novel("n", "Test Novel", "", "")

    # Add Self
    store.add_self(
        Self(
            id=SELF_ID,
            novel_id="n",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
        )
    )

    # Body 1 (chapters 1.0 to 10.0)
    store.add_persona(
        Persona(
            id=BODY1,
            novel_id="n",
            body_label="Fang Yuan (Scholar)",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id=SELF_ID,
            persona_id=BODY1,
            interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id=OBSERVER_READER,
        )
    )

    # Body 2 (chapters 10.0 to 50.0)
    store.add_persona(
        Persona(
            id=BODY2,
            novel_id="n",
            body_label="Fang Yuan (Immortal)",
            first_attested_pos=DiscoursePosition(chapter=10, offset=0),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id=SELF_ID,
            persona_id=BODY2,
            interval=FuzzyInterval(from_lb=10.0, from_ub=10.0, to_lb=50.0, to_ub=50.0),
            learned_at_pos=DiscoursePosition(chapter=10, offset=0),
            observer_id=OBSERVER_READER,
        )
    )

    # Standing attributes for Body 1
    store.add_attribute(
        "n",
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id=BODY1,
            key="hair_color",
            value="black",
            interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id=OBSERVER_READER,
        ),
    )

    store.conn.commit()
    return store


def _make_provenance(
    key: str,
    val: str,
    learned_ch: int,
    *,
    persona_id: str = BODY1,
    from_pos: float = 1.0,
    to_pos: float = 10.0,
    retracted_ch: int | None = None,
    certainty: Certainty = Certainty.CERTAIN,
    observer_id: str = OBSERVER_READER,
) -> FactProvenance:
    return FactProvenance(
        fact_ref=fact_ref("attr", persona_id, key, val),
        learned_at_pos=DiscoursePosition(chapter=learned_ch, offset=0),
        valid_interval=FuzzyInterval(from_lb=from_pos, from_ub=from_pos, to_lb=to_pos, to_ub=to_pos),
        retracted_at=DiscoursePosition(chapter=retracted_ch, offset=0) if retracted_ch is not None else None,
        certainty=certainty,
        observer_id=observer_id,
    )


# ---------------------------------------------------------------------------
# R1: Provenance Admissibility
# ---------------------------------------------------------------------------


def test_r1_provenance_admissibility(base_store: Store) -> None:
    """R1: Every selected reference's transitive source-fact lineage must be admissible under the request policy."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Asset A depends on an early fact (ch 1) AND a late-revealed fact (ch 50)
    fact_early = _make_provenance("hair_color", "black", learned_ch=1)
    fact_late = _make_provenance("dragon_scar", "forehead", learned_ch=50)

    asset_a = VisualAssetRecord(
        asset_id="asset_a",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(fact_early, fact_late),
    )
    registry.register(asset_a)

    # Request at cutoff k = 10 (before dragon scar is revealed)
    req_k10 = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=10, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res_k10 = selector.select(req_k10, registry)

    assert res_k10.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res_k10.selected_asset is None
    assert res_k10.reason == RejectionReason.CUTOFF_EXCEEDED
    # Minimal counterexample verified
    assert len(res_k10.candidate_evaluations) == 1
    eval_report = res_k10.candidate_evaluations[0]
    assert not eval_report.admissible
    assert eval_report.counterexample_ref == fact_late.fact_ref
    assert "ch50:0 > cutoff ch10:0" in eval_report.details

    # Request at cutoff k = 60 (after dragon scar is revealed)
    req_k60 = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=60, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res_k60 = selector.select(req_k60, registry)

    assert res_k60.status == SelectionStatus.SELECTED
    assert res_k60.selected_asset is not None
    assert res_k60.selected_asset.asset_id == "asset_a"


# ---------------------------------------------------------------------------
# R2: Embodiment Compatibility
# ---------------------------------------------------------------------------


def test_r2_embodiment_compatibility(base_store: Store) -> None:
    """R2: Reference tied to an incompatible body epoch must not be selected solely because the Self matches."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Asset 1 belongs to Body 1 (scholar, ch 1-10)
    asset_body1 = VisualAssetRecord(
        asset_id="asset_body1",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(_make_provenance("hair_color", "black", learned_ch=1, persona_id=BODY1),),
    )
    registry.register(asset_body1)

    # Request at story pos 25.0 (character is in Body 2, ch 10-50)
    req_body2 = VisualRequest(
        self_id=SELF_ID,
        story_pos=25.0,
        discourse_cutoff=DiscoursePosition(chapter=30, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res_body2 = selector.select(req_body2, registry)

    # Even though self_id matches SELF_ID, Body 1 reference must be rejected!
    assert res_body2.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res_body2.reason == RejectionReason.EMBODIMENT_MISMATCH
    assert "not in admissible personas" in res_body2.candidate_evaluations[0].details

    # Now register an asset for Body 2
    asset_body2 = VisualAssetRecord(
        asset_id="asset_body2",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY2,
        story_interval=FuzzyInterval(from_lb=10.0, from_ub=10.0, to_lb=50.0, to_ub=50.0),
        source_facts=(_make_provenance("robes", "white", learned_ch=10, persona_id=BODY2, from_pos=10.0, to_pos=50.0),),
    )
    registry.register(asset_body2)

    res_body2_after = selector.select(req_body2, registry)
    assert res_body2_after.status == SelectionStatus.SELECTED
    assert res_body2_after.selected_asset is not None
    assert res_body2_after.selected_asset.asset_id == "asset_body2"
    assert res_body2_after.selected_asset.persona_id == BODY2


# ---------------------------------------------------------------------------
# R3: Cutoff Independence
# ---------------------------------------------------------------------------


def test_r3_cutoff_independence_deterministic(base_store: Store) -> None:
    """R3: Adding a fact or reference disclosed after cutoff k must not change selection at cutoff <= k."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Asset early (learned at ch 2)
    asset_early = VisualAssetRecord(
        asset_id="asset_early",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(_make_provenance("eyes", "dark", learned_ch=2),),
    )
    registry.register(asset_early)

    req = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=5, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    initial_res = selector.select(req, registry)
    assert initial_res.status == SelectionStatus.SELECTED
    assert initial_res.selected_asset is not None
    assert initial_res.selected_asset.asset_id == "asset_early"

    # Now add future fact to the store and future asset to registry at cutoff 100
    base_store.add_attribute(
        "n",
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id=BODY1,
            key="secret_mark",
            value="crimson",
            interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
            learned_at_pos=DiscoursePosition(chapter=100, offset=0),
            observer_id=OBSERVER_READER,
        ),
    )
    base_store.conn.commit()

    asset_future = VisualAssetRecord(
        asset_id="asset_future",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(
            _make_provenance("eyes", "dark", learned_ch=2),
            _make_provenance("secret_mark", "crimson", learned_ch=100),
        ),
    )
    registry.register(asset_future)

    # Re-run selection at cutoff 5: result must be completely invariant!
    subsequent_res = selector.select(req, registry)
    assert subsequent_res.status == SelectionStatus.SELECTED
    assert subsequent_res.selected_asset is not None
    assert subsequent_res.selected_asset.asset_id == "asset_early"


@settings(max_examples=30, deadline=None)
@given(future_chapter=st.integers(min_value=20, max_value=500))
def test_r3_cutoff_independence_hypothesis(tmp_path_factory: pytest.TempPathFactory, future_chapter: int) -> None:
    """R3 (Property test): For any future disclose chapter > 10, cutoff k=5 selection is invariant."""
    tmp_path = tmp_path_factory.mktemp("hypo_r3")
    store = Store(str(tmp_path / "hypo.db"))
    store.add_novel("n", "N", "", "")
    store.add_self(Self(id=SELF_ID, novel_id="n", canonical_label="FY", first_attested_pos=DiscoursePosition(chapter=1)))
    store.add_persona(Persona(id=BODY1, novel_id="n", body_label="B1", first_attested_pos=DiscoursePosition(chapter=1)))
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id=SELF_ID,
            persona_id=BODY1,
            interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=500.0, to_ub=500.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.conn.commit()

    selector = VisualMemorySelector(store, novel_id="n")
    registry = VisualAssetRegistry()

    asset_base = VisualAssetRecord(
        asset_id="asset_base",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=500.0, to_ub=500.0),
        source_facts=(_make_provenance("hair", "black", learned_ch=1, from_pos=1.0, to_pos=500.0),),
    )
    registry.register(asset_base)

    req = VisualRequest(
        self_id=SELF_ID,
        story_pos=2.0,
        discourse_cutoff=DiscoursePosition(chapter=5),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res1 = selector.select(req, registry)

    # Add arbitrary future asset
    asset_hypo = VisualAssetRecord(
        asset_id=f"asset_future_{future_chapter}",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval.open_ended(1.0),
        source_facts=(_make_provenance("tattoo", "dragon", learned_ch=future_chapter),),
    )
    registry.register(asset_hypo)

    res2 = selector.select(req, registry)
    assert res1.status == res2.status == SelectionStatus.SELECTED
    assert res1.selected_asset.asset_id == res2.selected_asset.asset_id == "asset_base"


# ---------------------------------------------------------------------------
# R4: Retrospective Distinction
# ---------------------------------------------------------------------------


def test_r4_retrospective_distinction(base_store: Store) -> None:
    """R4: A request at story position p with cutoff k > p obeys its view policy; p and k are not equated."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Detail was true at story position 3.0, but first revealed at chapter 50
    fact_retrospective = _make_provenance("hidden_insignia", "cicada", learned_ch=50, from_pos=1.0, to_pos=10.0)
    asset = VisualAssetRecord(
        asset_id="asset_with_cicada",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(fact_retrospective,),
    )
    registry.register(asset)

    # In-sequence rendering at chapter 5: cannot use cicada asset (spoiler!)
    req_in_sequence = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=5, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res_in_sequence = selector.select(req_in_sequence, registry)
    assert res_in_sequence.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res_in_sequence.reason == RejectionReason.CUTOFF_EXCEEDED

    # Retrospective flashback rendering: story position is still 3.0, but reader cutoff is 60
    req_flashback = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=60, offset=0),
        policy=DisclosurePolicy.RETROSPECTIVE,
    )
    res_flashback = selector.select(req_flashback, registry)
    assert res_flashback.status == SelectionStatus.SELECTED
    assert res_flashback.selected_asset is not None
    assert res_flashback.selected_asset.asset_id == "asset_with_cicada"


# ---------------------------------------------------------------------------
# R5: Transitive Lineage
# ---------------------------------------------------------------------------


def test_r5_transitive_lineage(base_store: Store) -> None:
    """R5: If asset A depends on parent asset B, and B depends on a later-revealed fact, A inherits that dependency."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Parent asset B depends on fact revealed at chapter 80
    fact_ch80 = _make_provenance("eye_scar", "jagged", learned_ch=80)
    asset_parent_b = VisualAssetRecord(
        asset_id="asset_parent_b",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(fact_ch80,),
    )
    registry.register(asset_parent_b)

    # Child asset A conditioned via img2img on B, but its own prompt fact is early (ch 1)
    fact_ch1 = _make_provenance("hair_color", "black", learned_ch=1)
    asset_child_a = VisualAssetRecord(
        asset_id="asset_child_a",
        asset_kind=VisualAssetKind.BODY_STATE,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(fact_ch1,),
        parent_asset_ids=("asset_parent_b",),
    )
    registry.register(asset_child_a)

    # Request at cutoff k = 20
    req_k20 = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=20, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
        requested_asset_kind=VisualAssetKind.BODY_STATE,
    )
    res_k20 = selector.select(req_k20, registry)

    # Child A MUST inherit parent B's dependency on fact_ch80!
    assert res_k20.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res_k20.reason == RejectionReason.CUTOFF_EXCEEDED
    eval_report = res_k20.candidate_evaluations[0]
    assert eval_report.counterexample_ref == fact_ch80.fact_ref
    assert "ch80:0 > cutoff ch20:0" in eval_report.details


# ---------------------------------------------------------------------------
# R6: Conservative Fallback
# ---------------------------------------------------------------------------


def test_r6_conservative_fallback(base_store: Store) -> None:
    """R6: If no compatible reference is safe to select, report reason and explicit fallback with permitted facts."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Empty registry: no asset registered
    req = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=5, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res = selector.select(req, registry)

    assert res.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res.selected_asset is None
    assert res.reason == RejectionReason.NO_ASSET_REGISTERED
    # Permitted facts are populated from state_of so caller can safely construct prompt-only fallback
    assert len(res.permitted_facts) > 0
    assert any("hair_color=black" in f for f in res.permitted_facts)


# ---------------------------------------------------------------------------
# Conceptual Cases D & E
# ---------------------------------------------------------------------------


def test_case_d_observer_specific_knowledge(base_store: Store) -> None:
    """Case D: A character-facing rendering must respect that observer's recorded knowledge permissions."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Wu Clan knows Fang Yuan in Body 1, but does not know his secret facts
    base_store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id=SELF_ID,
            persona_id=BODY1,
            interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id="n:self:wu_clan",
        )
    )
    base_store.conn.commit()

    # Fact revealed to reader at ch 5
    fact_secret = _make_provenance("cultivation_rank", "rank_3", learned_ch=5)
    asset = VisualAssetRecord(
        asset_id="asset_rank3",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(fact_secret,),
        observer_scope=frozenset({OBSERVER_READER, OBSERVER_SYSTEM, "n:self:wu_clan"}),
    )
    registry.register(asset)

    # Observer Wu Clan has no observation record of rank 3
    req_wu = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=10, offset=0),
        observer_id="n:self:wu_clan",
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res_wu = selector.select(req_wu, registry)
    assert res_wu.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res_wu.reason == RejectionReason.OBSERVER_UNAUTHORIZED
    assert "has not witnessed fact" in res_wu.candidate_evaluations[0].details

    # Now record an observation for Wu Clan at chapter 15
    base_store.add_observation(
        Observation(
            observer_id="n:self:wu_clan",
            fact_ref=fact_secret.fact_ref,
            learned_at_pos=DiscoursePosition(chapter=15, offset=0),
        ),
    )
    base_store.conn.commit()

    # At cutoff 12 (before Wu Clan witnesses it): still rejected
    req_wu_12 = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=12, offset=0),
        observer_id="n:self:wu_clan",
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    assert selector.select(req_wu_12, registry).status == SelectionStatus.FALLBACK_PROMPT_ONLY

    # At cutoff 20 (after Wu Clan witnesses it): admitted
    req_wu_20 = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=20, offset=0),
        observer_id="n:self:wu_clan",
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    assert selector.select(req_wu_20, registry).status == SelectionStatus.SELECTED


def test_case_e_uncertain_facts_conservative(base_store: Store) -> None:
    """Case E: Missing or uncertain facts must not be silently promoted to certain facts."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Fact has PLAUSIBLE certainty
    fact_plausible = _make_provenance(
        "disguise_hue", "amber", learned_ch=2, certainty=Certainty.PLAUSIBLE
    )
    asset = VisualAssetRecord(
        asset_id="asset_plausible",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(fact_plausible,),
    )
    registry.register(asset)

    # By default, allow_plausible=False: must reject
    req_strict = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=10, offset=0),
        allow_plausible=False,
    )
    res_strict = selector.select(req_strict, registry)
    assert res_strict.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res_strict.reason == RejectionReason.FACT_UNCERTAINTY_EXCLUDED

    # Explicit allow_plausible=True: permitted
    req_lenient = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=10, offset=0),
        allow_plausible=True,
    )
    res_lenient = selector.select(req_lenient, registry)
    assert res_lenient.status == SelectionStatus.SELECTED


def test_retraction_preservation_and_invalidation(base_store: Store) -> None:
    """Historical belief preservation: facts retracted after cutoff k were believed at k; retracted at <= k are invalid."""
    selector = VisualMemorySelector(base_store, novel_id="n")
    registry = VisualAssetRegistry()

    # Belief learned at ch 2, retracted at ch 40
    fact_retracted = _make_provenance(
        "identity_claim", "righteous_disciple", learned_ch=2, retracted_ch=40
    )
    asset = VisualAssetRecord(
        asset_id="asset_disciple",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id=SELF_ID,
        persona_id=BODY1,
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=10.0, to_ub=10.0),
        source_facts=(fact_retracted,),
    )
    registry.register(asset)

    # At cutoff k = 20 (before retraction): belief was active and believed! Admitted.
    req_k20 = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=20, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res_k20 = selector.select(req_k20, registry)
    assert res_k20.status == SelectionStatus.SELECTED

    # At cutoff k = 50 (after retraction at 40): belief is known to be false. Rejected!
    req_k50 = VisualRequest(
        self_id=SELF_ID,
        story_pos=3.0,
        discourse_cutoff=DiscoursePosition(chapter=50, offset=0),
        policy=DisclosurePolicy.IN_SEQUENCE,
    )
    res_k50 = selector.select(req_k50, registry)
    assert res_k50.status == SelectionStatus.FALLBACK_PROMPT_ONLY
    assert res_k50.reason == RejectionReason.FACT_RETRACTED
    assert "retracted at ch40:0 <= cutoff ch50:0" in res_k50.candidate_evaluations[0].details
