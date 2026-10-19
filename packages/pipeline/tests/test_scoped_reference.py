"""Model-free tests for Phase 2: Cutoff-Scoped Visual Asset Emission.

Verifies:
1. Sequential reveal: facts disclosed after discourse cutoff k are excluded.
2. Retrospective reconstruction: flashback query (p < k) under RETROSPECTIVE admits facts disclosed up to k.
3. Body transitions: embodiment mismatch fails closed when requesting inactive body epoch.
4. Observer restriction: character observer without observation cannot see reader-stamped secret facts.
5. Retraction preservation and invalidation: facts believed before retraction cutoff are admitted; retracted facts after cutoff are excluded.
6. Transitive lineage: parent asset dependency enforces cutoff and observer constraints transitively.
7. Fail-closed fallback: ungrounded entities or missing parent assets fail closed.
8. Digest sensitivity: different cutoffs and admissible fact sets yield distinct prompt digests and asset IDs.
9. Manifest serialization: verifiable VisualAssetRecord round-trips to/from JSON cleanly with SQLite row IDs.
10. Legacy compatibility: existing un-scoped reference generation remains unaffected.
"""

from __future__ import annotations

import pytest
from echotales.core.enums import (
    OBSERVER_READER,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    Attribute,
    DiscoursePosition,
    Observation,
    Persona,
    Self,
    SelfPersonaBinding,
)
from echotales.core.readset import observable_ref
from echotales.core.store import Store
from echotales.core.visual_memory import (
    DisclosurePolicy,
    RejectionReason,
    VisualAssetKind,
    VisualAssetRecord,
    VisualAssetRegistry,
)
from echotales.pipeline.persona.reference_gen import generate_references
from echotales.pipeline.persona.scoped_reference import (
    EmissionStatus,
    emit_scoped_reference,
)

NOVEL = "test_novel"


@pytest.fixture
def store(tmp_path) -> Store:
    s = Store(str(tmp_path / "test.db"))
    s.add_novel(NOVEL, "Test Novel", "test.epub", "generic")
    return s


def test_sequential_reveal(store: Store, tmp_path) -> None:
    """A scar disclosed in chapter 100 must not contaminate an early reference at k=5."""
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
            body_label="Fang Yuan Body 1",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    # Hair color disclosed in chapter 1
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    # Scar disclosed in chapter 100 (retroactively valid from chapter 1)
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="distinguishing_features",
            value="a jagged scar across left cheek",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=100),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    res = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=5.0,
        discourse_cutoff=DiscoursePosition(chapter=5),
        policy=DisclosurePolicy.IN_SEQUENCE,
        dry_run=True,
    )

    assert res.status == EmissionStatus.SUCCESS
    assert res.asset_record is not None
    assert "black hair" in res.prompt
    assert "jagged scar" not in res.prompt
    # Manifest has only the chapter 1 fact
    fact_refs = [f.fact_ref for f in res.asset_record.source_facts]
    assert any("hair_color:black" in ref for ref in fact_refs)
    assert not any("distinguishing_features" in ref for ref in fact_refs)
    assert res.asset_record.effective_cutoff <= DiscoursePosition(chapter=5)


def test_retrospective_reconstruction(store: Store) -> None:
    """Flashback at p=5 admits the scar when rendered retrospectively at cutoff k=100."""
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
            body_label="Fang Yuan Body 1",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="distinguishing_features",
            value="a jagged scar across left cheek",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=100),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    res = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=5.0,
        discourse_cutoff=DiscoursePosition(chapter=100),
        policy=DisclosurePolicy.RETROSPECTIVE,
        dry_run=True,
    )

    assert res.status == EmissionStatus.SUCCESS
    assert res.asset_record is not None
    assert "black hair" in res.prompt
    assert "jagged scar" in res.prompt
    fact_refs = [f.fact_ref for f in res.asset_record.source_facts]
    assert any("hair_color:black" in ref for ref in fact_refs)
    assert any("distinguishing_features" in ref for ref in fact_refs)
    assert res.asset_record.effective_cutoff == DiscoursePosition(chapter=100)


def test_body_transition(store: Store) -> None:
    """Query at p=25 rejects Body 1 (active only on [1, 20]) and accepts Body 2 (active on [21, 50])."""
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
            body_label="Mortal Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_persona(
        Persona(
            id="p2",
            novel_id=NOVEL,
            body_label="Zombie Body",
            first_attested_pos=DiscoursePosition(chapter=21),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 20.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p2",
            interval=FuzzyInterval.point_known(21.0, 50.0),
            learned_at_pos=DiscoursePosition(chapter=21),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.point_known(1.0, 20.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p2",
            key="hair_color",
            value="white",
            interval=FuzzyInterval.point_known(21.0, 50.0),
            learned_at_pos=DiscoursePosition(chapter=21),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    # Query with persona_id="p1" at p=25 must fail closed
    res_mismatch = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        persona_id="p1",
        story_pos=25.0,
        discourse_cutoff=DiscoursePosition(chapter=25),
        dry_run=True,
    )
    assert res_mismatch.status == EmissionStatus.REJECTED
    assert RejectionReason.EMBODIMENT_MISMATCH in res_mismatch.rejection_reasons

    # Query with default persona resolution at p=25 binds p2
    res_valid = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        persona_id=None,
        story_pos=25.0,
        discourse_cutoff=DiscoursePosition(chapter=25),
        dry_run=True,
    )
    assert res_valid.status == EmissionStatus.SUCCESS
    assert res_valid.asset_record is not None
    assert res_valid.asset_record.persona_id == "p2"
    assert "white hair" in res_valid.prompt
    assert "black hair" not in res_valid.prompt


def test_observer_restriction(store: Store) -> None:
    """Observer 'wu_clan' cannot see facts stamped for READER unless witnessed."""
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
            body_label="Fang Yuan Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 50.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 50.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id="wu_clan",
        )
    )
    # Hair color observed by wu_clan
    hair_attr = Attribute(
        target_kind=TargetKind.PERSONA,
        target_id="p1",
        key="hair_color",
        value="black",
        interval=FuzzyInterval.point_known(1.0, 50.0),
        learned_at_pos=DiscoursePosition(chapter=1),
        observer_id=OBSERVER_READER,
    )
    store.add_attribute(NOVEL, hair_attr)
    store.add_observation(
        Observation(
            observer_id="wu_clan",
            fact_ref=observable_ref(hair_attr),
            learned_at_pos=DiscoursePosition(chapter=1),
        )
    )

    # Secret tattoo never witnessed by wu_clan
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="distinguishing_features",
            value="demonic blood tattoo",
            interval=FuzzyInterval.point_known(1.0, 50.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    # READER sees both
    res_reader = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=10.0,
        discourse_cutoff=DiscoursePosition(chapter=10),
        observer_id=OBSERVER_READER,
        dry_run=True,
    )
    assert "black hair" in res_reader.prompt
    assert "demonic blood tattoo" in res_reader.prompt

    # wu_clan sees only witnessed hair_color
    res_wu = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=10.0,
        discourse_cutoff=DiscoursePosition(chapter=10),
        observer_id="wu_clan",
        dry_run=True,
    )
    assert "black hair" in res_wu.prompt
    assert "demonic blood tattoo" not in res_wu.prompt
    fact_refs = [f.fact_ref for f in res_wu.asset_record.source_facts]  # type: ignore[union-attr]
    assert not any("distinguishing_features" in ref for ref in fact_refs)


def test_retraction_preservation_and_invalidation(store: Store) -> None:
    """Fact believed before retraction cutoff is admitted; after retraction cutoff it is excluded."""
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
            body_label="Fang Yuan Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    # White robes disguise believed from ch 1 until retracted at ch 50
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="typical_attire",
            value="white scholar robes",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            retracted_at=DiscoursePosition(chapter=50),
            truth_status=TruthStatus.FALSE,
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    # At k=20: held belief, admitted into reference
    res_early = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=10.0,
        discourse_cutoff=DiscoursePosition(chapter=20),
        dry_run=True,
    )
    assert res_early.status == EmissionStatus.SUCCESS
    assert "wearing white scholar robes" in res_early.prompt
    assert len(res_early.asset_record.source_facts) == 1  # type: ignore[union-attr]
    assert res_early.asset_record.source_facts[0].retracted_at == DiscoursePosition(chapter=50)  # type: ignore[union-attr]

    # At k=60: retracted belief, excluded from reference
    res_late = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=10.0,
        discourse_cutoff=DiscoursePosition(chapter=60),
        dry_run=True,
    )
    assert "white scholar robes" not in res_late.prompt
    assert len(res_late.asset_record.source_facts) == 0  # type: ignore[union-attr]


def test_transitive_lineage(store: Store) -> None:
    """Derived reference conditioned on parent asset inherits parent cutoff constraints."""
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
            body_label="Fang Yuan Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    parent = VisualAssetRecord(
        asset_id="parent_ch50",
        asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
        self_id="s1",
        persona_id="p1",
        story_interval=FuzzyInterval.point_known(1.0, 100.0),
        source_facts=(),
        effective_cutoff=DiscoursePosition(chapter=50),
    )

    registry = VisualAssetRegistry()
    registry.register(parent)

    # Derived asset at k=20 conditioned on parent at k=50 must fail closed
    res_early = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=10.0,
        discourse_cutoff=DiscoursePosition(chapter=20),
        parent_asset_ids=["parent_ch50"],
        registry=registry,
        dry_run=True,
    )
    assert res_early.status == EmissionStatus.REJECTED
    assert (
        RejectionReason.CUTOFF_EXCEEDED in res_early.rejection_reasons
        or RejectionReason.TRANSITIVE_LINEAGE_VIOLATION in res_early.rejection_reasons
    )

    # Derived asset at k=60 conditioned on parent at k=50 succeeds
    res_late = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=10.0,
        discourse_cutoff=DiscoursePosition(chapter=60),
        parent_asset_ids=["parent_ch50"],
        registry=registry,
        dry_run=True,
    )
    assert res_late.status == EmissionStatus.SUCCESS
    assert "parent_ch50" in res_late.asset_record.parent_asset_ids  # type: ignore[union-attr]
    assert res_late.asset_record.effective_cutoff >= DiscoursePosition(chapter=50)  # type: ignore[union-attr]


def test_fail_closed_fallback(store: Store) -> None:
    """Missing entities or missing parent assets fail closed without corrupting graph."""
    # Unknown entity
    res_unknown = emit_scoped_reference(
        store,
        NOVEL,
        "nonexistent_entity",
        story_pos=1.0,
        discourse_cutoff=DiscoursePosition(chapter=1),
        dry_run=True,
    )
    assert res_unknown.status == EmissionStatus.REJECTED
    assert RejectionReason.NO_ADMISSIBLE_EMBODIMENT in res_unknown.rejection_reasons

    # Existing entity but missing parent asset
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
            body_label="Fang Yuan Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.conn.commit()

    res_missing_parent = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=1.0,
        discourse_cutoff=DiscoursePosition(chapter=1),
        parent_asset_ids=["missing_parent_id"],
        dry_run=True,
    )
    assert res_missing_parent.status == EmissionStatus.REJECTED
    assert RejectionReason.TRANSITIVE_LINEAGE_VIOLATION in res_missing_parent.rejection_reasons


def test_digest_sensitivity(store: Store) -> None:
    """Different cutoffs yielding different admissible facts generate distinct digests and asset IDs."""
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
            body_label="Fang Yuan Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="distinguishing_features",
            value="a jagged scar across left cheek",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=100),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    res_k5 = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=5.0,
        discourse_cutoff=DiscoursePosition(chapter=5),
        policy=DisclosurePolicy.IN_SEQUENCE,
        dry_run=True,
    )
    res_k100 = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=5.0,
        discourse_cutoff=DiscoursePosition(chapter=100),
        policy=DisclosurePolicy.RETROSPECTIVE,
        dry_run=True,
    )

    assert res_k5.prompt != res_k100.prompt
    assert res_k5.asset_record.prompt_digest != res_k100.asset_record.prompt_digest  # type: ignore[union-attr]
    assert res_k5.asset_record.asset_id != res_k100.asset_record.asset_id  # type: ignore[union-attr]


def test_manifest_serialization(store: Store, tmp_path) -> None:
    """Verifiable manifest round-trips to/from JSON with source row IDs preserved."""
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
            body_label="Fang Yuan Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    res = emit_scoped_reference(
        store,
        NOVEL,
        "s1",
        story_pos=5.0,
        discourse_cutoff=DiscoursePosition(chapter=5),
        out_dir=tmp_path,
        dry_run=False,
    )

    assert res.status == EmissionStatus.SUCCESS
    assert res.manifest_path
    assert res.image_path

    # Check manifest file exists
    manifest_p = tmp_path / f"{res.asset_record.asset_id}_manifest.json"  # type: ignore[union-attr]
    assert manifest_p.exists()
    assert (tmp_path / f"{res.asset_record.asset_id}.png").exists()  # type: ignore[union-attr]

    # Load manifest and verify parity
    loaded = VisualAssetRecord.load_manifest(manifest_p)
    assert loaded.asset_id == res.asset_record.asset_id  # type: ignore[union-attr]
    assert loaded.prompt == res.asset_record.prompt  # type: ignore[union-attr]
    assert loaded.prompt_digest == res.asset_record.prompt_digest  # type: ignore[union-attr]
    assert loaded.effective_cutoff == res.asset_record.effective_cutoff  # type: ignore[union-attr]
    assert len(loaded.source_facts) == len(res.asset_record.source_facts)  # type: ignore[union-attr]
    assert loaded.source_facts[0].fact_ref == res.asset_record.source_facts[0].fact_ref  # type: ignore[union-attr]
    # Physical row ID was populated by store and serialized
    assert loaded.source_facts[0].source_row_id is not None


def test_legacy_compatibility(store: Store, tmp_path) -> None:
    """Existing legacy reference generation remains intact and functional."""
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
            body_label="Fang Yuan Body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="s1",
            persona_id="p1",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        )
    )
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="p1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.point_known(1.0, 100.0),
            learned_at_pos=DiscoursePosition(chapter=1),
            observer_id=OBSERVER_READER,
        ),
    )
    store.conn.commit()

    report = generate_references(NOVEL, store, out_dir=tmp_path)
    assert report.novel_id == NOVEL
    assert report.generated >= 0
