"""Tests for approved character reference sheets (Phase 1a).

Spec: docs/design/consistency_plan.md Phase 1.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from echotales.core.enums import (
    AliasType,
    AssertedBy,
    OBSERVER_READER,
    Prominence,
    ReferenceMode,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import generate_references
from echotales.pipeline.persona.refimg import (
    approve_sheet,
    approved_reference_path,
    list_sheets,
    register_sheet_candidate,
    reject_sheet,
)
from echotales.pipeline.render.panels import StubImageEngine


def _setup_store(tmp_path: Path, novel_id: str = "test-novel") -> Store:
    db_path = tmp_path / f"{novel_id}.db"
    store = Store(db_path)
    store.add_novel(novel_id, "Test Novel", source_path="test.txt", adapter="generic")
    return store


def _add_person(
    store: Store,
    novel_id: str,
    self_id: str,
    label: str,
    *,
    prominence: Prominence = Prominence.PRINCIPAL,
) -> None:
    store.add_self(
        Self(
            id=self_id,
            novel_id=novel_id,
            canonical_label=label,
            kind=TargetKind.SELF,
            prominence=prominence,
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
        )
    )
    # Add standing appearance attribute so reference_gen has appearance to generate from
    store.add_attribute(
        novel_id,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id=f"{self_id}:body1",
            key="hair_color",
            value="black",
            interval=FuzzyInterval.open_ended(1.0),
            learned_at_pos=DiscoursePosition(chapter=1.0, offset=0),
            observer_id=OBSERVER_READER,
            asserted_by=AssertedBy.INFERENCE,
            truth_status=TruthStatus.INFERRED,
        ),
    )
    # Add mentions to clear the RECURRING/PRINCIPAL floor for eligible_prominence
    store.add_mentions(
        [
            Mention(
                id=f"m_{self_id}_{i}",
                novel_id=novel_id,
                segment_id="seg1",
                chapter=1.0,
                offset=i * 10,
                block_index=0,
                text=label,
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_DESCRIPTION,
                reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF,
                target_id=self_id,
            )
            for i in range(35)
        ]
    )
    store.conn.commit()


def test_generated_sheet_registers_unselected(tmp_path: Path) -> None:
    """A generated reference sheet registers as a ref_image_candidate with selected=0."""
    store = _setup_store(tmp_path)
    _add_person(store, "test-novel", "test-novel:self:hero", "Hero")

    out_dir = tmp_path / "refs"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = generate_references(
        "test-novel", store, engine=StubImageEngine(), out_dir=out_dir
    )
    assert report.generated == 1

    sheets = list_sheets(store, "test-novel", "test-novel:self:hero")
    assert len(sheets) == 1
    sheet = sheets[0]
    assert sheet.backend == "generated-sheet"
    assert sheet.role == "sheet"
    assert sheet.selected is False
    assert sheet.persona_id == "test-novel:self:hero:body1"

    img_path = out_dir / "test-novel_self_hero_body1.png"
    assert img_path.exists()
    expected_sha = hashlib.sha1(img_path.read_bytes()).hexdigest()[:10]
    assert sheet.id == f"test-novel:self:hero:body1:sheet:{expected_sha}"
    assert sheet.source_url == f"file://{img_path.resolve()}"


def test_select_scopes_by_persona_id(tmp_path: Path) -> None:
    """Selecting a candidate for body2 does not unselect an approved candidate for body1."""
    store = _setup_store(tmp_path)
    self_id = "test-novel:self:transmigrator"
    _add_person(store, "test-novel", self_id, "Protagonist")

    img1 = tmp_path / "body1.png"
    img1.write_bytes(b"image_content_body1")
    img2 = tmp_path / "body2.png"
    img2.write_bytes(b"image_content_body2")
    img1_alt = tmp_path / "body1_alt.png"
    img1_alt.write_bytes(b"image_content_body1_alt")

    cand1 = register_sheet_candidate(
        store, "test-novel", self_id, f"{self_id}:body1", img1, "Protagonist [body1]"
    )
    cand2 = register_sheet_candidate(
        store, "test-novel", self_id, f"{self_id}:body2", img2, "Protagonist [body2]"
    )
    cand1_alt = register_sheet_candidate(
        store, "test-novel", self_id, f"{self_id}:body1", img1_alt, "Protagonist [body1]"
    )

    # Approve body 1
    approve_sheet(store, "test-novel", self_id, cand1.id)
    assert store.get_ref_image_candidate(cand1.id).selected is True
    assert store.get_ref_image_candidate(cand2.id).selected is False

    # Approve body 2: body 1 must remain selected
    approve_sheet(store, "test-novel", self_id, cand2.id)
    assert store.get_ref_image_candidate(cand1.id).selected is True
    assert store.get_ref_image_candidate(cand2.id).selected is True

    # Approve alternate sheet for body 1: body 1 cand1 is unselected, but body 2 stays selected
    approve_sheet(store, "test-novel", self_id, cand1_alt.id)
    assert store.get_ref_image_candidate(cand1.id).selected is False
    assert store.get_ref_image_candidate(cand1_alt.id).selected is True
    assert store.get_ref_image_candidate(cand2.id).selected is True


def test_approved_reference_path_requires_selection(tmp_path: Path) -> None:
    """approved_reference_path returns None until human approval."""
    store = _setup_store(tmp_path)
    self_id = "test-novel:self:scholar"
    persona_id = f"{self_id}:body1"
    _add_person(store, "test-novel", self_id, "Scholar")

    img = tmp_path / "scholar.png"
    img.write_bytes(b"scholar_pixels")

    cand = register_sheet_candidate(store, "test-novel", self_id, persona_id, img, "Scholar")

    # Unapproved -> None
    assert approved_reference_path(store, "test-novel", persona_id) is None

    # Approved -> returns Path
    approve_sheet(store, "test-novel", self_id, cand.id)
    assert approved_reference_path(store, "test-novel", persona_id) == img.resolve()

    # Rejected -> None
    reject_sheet(store, "test-novel", self_id, cand.id)
    assert approved_reference_path(store, "test-novel", persona_id) is None


def test_regenerated_sheet_revokes_approval(tmp_path: Path) -> None:
    """If a sheet file changes on disk, the old approval no longer matches and returns None."""
    store = _setup_store(tmp_path)
    self_id = "test-novel:self:mage"
    persona_id = f"{self_id}:body1"
    _add_person(store, "test-novel", self_id, "Mage")

    img = tmp_path / "mage.png"
    img.write_bytes(b"first_draw_pixels")

    cand = register_sheet_candidate(store, "test-novel", self_id, persona_id, img, "Mage")
    approve_sheet(store, "test-novel", self_id, cand.id)

    assert approved_reference_path(store, "test-novel", persona_id) == img.resolve()

    # Regenerate sheet with new pixels
    img.write_bytes(b"second_draw_different_pixels")

    # Old approval is now stale because sha1 does not match cand.id
    assert approved_reference_path(store, "test-novel", persona_id) is None

    # Re-registering the new sheet creates a new candidate with selected=False
    new_cand = register_sheet_candidate(store, "test-novel", self_id, persona_id, img, "Mage")
    assert new_cand.id != cand.id
    assert new_cand.selected is False
    assert approved_reference_path(store, "test-novel", persona_id) is None
