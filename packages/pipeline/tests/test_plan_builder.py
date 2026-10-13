"""Visual Rendering Track Phase 1c: `build_render_plan` must use the real
state at the panel's own story position, never the latest state in the
database -- "a panel at position P must use state corresponding to P" is the
whole point of deriving `VisualRenderPlan` from `state_of()` instead of
picking a persona some other way."""

from __future__ import annotations

import pytest
from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    Attribute,
    DiscoursePosition,
    Persona,
    Self,
    SelfPersonaBinding,
)
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import REFERENCE_PATH_KEY
from echotales.pipeline.render.contract import CharacterRole
from echotales.pipeline.render.plan_builder import build_render_plan

NOVEL = "t"


@pytest.fixture
def store(tmp_path) -> Store:
    s = Store(str(tmp_path / "t.db"))
    s.add_novel(NOVEL, "T", "x.epub", "generic")
    return s


def test_plan_round_trips_persona_role_and_reference(store: Store, tmp_path) -> None:
    store.add_self(
        Self(
            id="s1",
            novel_id=NOVEL,
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_persona(
        Persona(
            id="p1",
            novel_id=NOVEL,
            body_label="Fang Yuan's body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    ref_path = tmp_path / "p1.png"
    ref_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key=REFERENCE_PATH_KEY,
            value=str(ref_path),
            interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    plan = build_render_plan(
        store,
        NOVEL,
        chapter=5.0,
        beat_id="t:5:0",
        panel_seq=0,
        cast_self_ids=["s1"],
        lead_self_id="s1",
        pose_hint="standing, calm",
        expression_hint="calm_expression",
    )

    assert len(plan.characters) == 1
    char = plan.characters[0]
    assert char.persona_id == "p1"
    assert char.self_id == "s1"
    assert char.role is CharacterRole.PRINCIPAL
    assert char.reference_paths == (ref_path,)
    assert char.pose_hint == "standing, calm"
    assert char.expression_hint == "calm_expression"
    assert plan.resolver == "state_of"
    assert plan.state_digest


def test_panel_at_chapter_10_does_not_pick_up_a_body_bound_at_chapter_300(
    store: Store,
) -> None:
    """Two personas bound sequentially to one self (a reincarnation/
    transmigration case, same shape as core/tests/test_state.py's
    `TestReincarnation`) must resolve to whichever body is active at THIS
    panel's own chapter -- never the later body merely because it already
    exists in the database by the time this render runs."""
    store.add_self(
        Self(
            id="s_soul",
            novel_id=NOVEL,
            canonical_label="The Traveller",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_persona(
        Persona(
            id="p_old",
            novel_id=NOVEL,
            body_label="original body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_persona(
        Persona(
            id="p_new",
            novel_id=NOVEL,
            body_label="reborn body",
            first_attested_pos=DiscoursePosition(chapter=300),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s_soul",
            persona_id="p_old",
            interval=FuzzyInterval.point_known(1, 300),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s_soul",
            persona_id="p_new",
            interval=FuzzyInterval.open_ended(300, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=300),
            observer_id=OBSERVER_READER,
        )
    )
    store.conn.commit()

    early_plan = build_render_plan(
        store,
        NOVEL,
        chapter=10.0,
        beat_id="b1",
        panel_seq=0,
        cast_self_ids=["s_soul"],
        lead_self_id="s_soul",
    )
    late_plan = build_render_plan(
        store,
        NOVEL,
        chapter=350.0,
        beat_id="b2",
        panel_seq=0,
        cast_self_ids=["s_soul"],
        lead_self_id="s_soul",
    )

    assert early_plan.characters[0].persona_id == "p_old"
    assert late_plan.characters[0].persona_id == "p_new"
    assert early_plan.state_digest != late_plan.state_digest


def test_self_with_no_bound_persona_yet_produces_no_character_spec(
    store: Store,
) -> None:
    """A self with no persona bound at this position has nothing to draw --
    a missing `CharacterRenderSpec`, not a fabricated or default one -- but
    the plan still records the attempt in `state_digest` rather than acting
    as if this cast member were never considered."""
    store.add_self(
        Self(
            id="s1",
            novel_id=NOVEL,
            canonical_label="Someone",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.conn.commit()

    plan = build_render_plan(
        store,
        NOVEL,
        chapter=1.0,
        beat_id="b1",
        panel_seq=0,
        cast_self_ids=["s1"],
    )

    assert plan.characters == ()
    assert plan.state_digest


def test_build_render_plan_with_visual_registry_integration(store: Store, tmp_path) -> None:
    """Integration test: build_render_plan with visual_registry uses VisualMemorySelector."""
    from echotales.core.visual_memory import (
        FactProvenance,
        VisualAssetKind,
        VisualAssetRecord,
        VisualAssetRegistry,
    )
    from echotales.core.readset import fact_ref

    store.add_self(
        Self(id="s1", novel_id=NOVEL, canonical_label="Hero", first_attested_pos=DiscoursePosition(chapter=1))
    )
    store.add_persona(
        Persona(id="p1", novel_id=NOVEL, body_label="Hero Body", first_attested_pos=DiscoursePosition(chapter=1))
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=100.0, to_ub=100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.conn.commit()

    # Asset with fact revealed at chapter 50
    asset_file = tmp_path / "hero_sheet.png"
    asset_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    registry = VisualAssetRegistry()
    asset = VisualAssetRecord(
        asset_id="hero_sheet",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id="s1",
        persona_id="p1",
        story_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=100.0, to_ub=100.0),
        source_facts=(
            FactProvenance(
                fact_ref=fact_ref("attr", "p1", "sword", "dragon"),
                learned_at_pos=DiscoursePosition(chapter=50),
                valid_interval=FuzzyInterval(from_lb=1.0, from_ub=1.0, to_lb=100.0, to_ub=100.0),
            ),
        ),
        image_path=str(asset_file),
    )
    registry.register(asset)

    # Cutoff 10: detail not revealed yet -> reference is suppressed, prompt-only fallback
    plan_early = build_render_plan(
        store,
        NOVEL,
        chapter=5.0,
        beat_id="t:5:1",
        panel_seq=0,
        cast_self_ids=["s1"],
        visual_registry=registry,
        discourse_cutoff=DiscoursePosition(chapter=10),
    )
    assert len(plan_early.characters) == 1
    assert plan_early.characters[0].reference_paths == ()

    # Cutoff 60: detail revealed -> reference is safely admitted
    plan_late = build_render_plan(
        store,
        NOVEL,
        chapter=5.0,
        beat_id="t:5:1",
        panel_seq=0,
        cast_self_ids=["s1"],
        visual_registry=registry,
        discourse_cutoff=DiscoursePosition(chapter=60),
    )
    assert len(plan_late.characters) == 1
    assert plan_late.characters[0].reference_paths == (asset_file,)
