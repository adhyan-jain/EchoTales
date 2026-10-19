"""Unit tests for Asset Studio: character turnarounds, location plates, and approval lifecycle."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from echotales.core.models import CharacterBibleEntry, LocationBibleEntry
from echotales.core.store import Store
from echotales.pipeline.assets.approval import (
    approve_asset_candidate,
    get_approved_reference,
    register_asset_candidate,
    reject_asset_candidate,
    verify_shot_approved_references,
)
from echotales.pipeline.assets.location import generate_location_assets
from echotales.pipeline.assets.turnaround import (
    STANDARD_EXPRESSIONS,
    TurnaroundView,
    generate_character_assets,
)
from echotales.pipeline.screenplay.schema import (
    CharacterAppearanceRef,
    ScreenplayShot,
)


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def test_generate_character_turnarounds_and_expressions() -> None:
    char = CharacterBibleEntry(
        self_id="char:holmes",
        canonical_label="Sherlock Holmes",
        active_persona_id="body:holmes:1880s",
        active_outfit="dressing_gown",
        attributes={"hair": "black", "physique": "tall thin"},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        asset = generate_character_assets(char, tmpdir)
        assert Path(asset.sheet_image_path).is_file()
        assert len(asset.view_crops) == 3
        for view in TurnaroundView:
            assert view.value in asset.view_crops
            assert Path(asset.view_crops[view.value]).is_file()

        assert asset.expression_sheet_path is not None
        assert Path(asset.expression_sheet_path).is_file()
        assert len(asset.expression_crops) == len(STANDARD_EXPRESSIONS)
        for expr in STANDARD_EXPRESSIONS:
            assert expr.value in asset.expression_crops
            assert Path(asset.expression_crops[expr.value]).is_file()


def test_generate_location_plates() -> None:
    loc = LocationBibleEntry(
        location_id="loc:baker_st",
        canonical_name="221B Baker Street",
        description="Victorian sitting room with violin and fireplace",
        ambience_sound="hearth_and_rain",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        asset = generate_location_assets(loc, tmpdir)
        assert Path(asset.master_plate_path).is_file()
        assert "establishing" in asset.angle_variants
        assert "reverse" in asset.angle_variants
        assert "night" in asset.time_variants
        assert asset.ambience_sound == "hearth_and_rain"


def test_asset_approval_lifecycle(store: Store) -> None:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(b"fake_image_bytes")
        f.flush()

        cand = register_asset_candidate(
            store,
            novel_id="hound",
            target_id="char:holmes",
            target_label="Sherlock Holmes",
            file_path=f.name,
            role="sheet",
            persona_id="body:holmes",
        )
        assert cand.selected is False

        # Initially unapproved
        assert get_approved_reference(store, novel_id="hound", target_id="char:holmes", role="sheet", persona_id="body:holmes") is None

        # Approve
        approve_asset_candidate(store, novel_id="hound", candidate_id=cand.id, note="Approved by reviewer")
        approved = get_approved_reference(store, novel_id="hound", target_id="char:holmes", role="sheet", persona_id="body:holmes")
        assert approved is not None
        assert approved.id == cand.id
        assert approved.selected is True

        # Reject
        reject_asset_candidate(store, novel_id="hound", candidate_id=cand.id, note="Revision requested")
        assert get_approved_reference(store, novel_id="hound", target_id="char:holmes", role="sheet", persona_id="body:holmes") is None


def test_verify_shot_approved_references_gate(store: Store) -> None:
    shot = ScreenplayShot(
        shot_index=0,
        scene_id="sc01",
        location_id="loc:baker_st",
        characters=[
            CharacterAppearanceRef(
                self_id="char:holmes",
                persona_id="body:holmes",
            )
        ],
    )

    # Both location and character are initially unapproved
    violations = verify_shot_approved_references(shot, store, novel_id="hound")
    assert len(violations) == 2

    # Register and approve location plate
    with tempfile.NamedTemporaryFile(suffix=".png") as f_loc:
        f_loc.write(b"loc_plate")
        f_loc.flush()
        loc_cand = register_asset_candidate(
            store, novel_id="hound", target_id="loc:baker_st", target_label="Baker St", file_path=f_loc.name, role="location"
        )
        approve_asset_candidate(store, novel_id="hound", candidate_id=loc_cand.id)

    # Now only character turnaround is missing
    violations2 = verify_shot_approved_references(shot, store, novel_id="hound")
    assert len(violations2) == 1
    assert "UNAPPROVED_CHARACTER_SHEET" in violations2[0]

    # Register and approve character sheet
    with tempfile.NamedTemporaryFile(suffix=".png") as f_char:
        f_char.write(b"char_sheet")
        f_char.flush()
        char_cand = register_asset_candidate(
            store, novel_id="hound", target_id="char:holmes", target_label="Holmes", file_path=f_char.name, role="sheet", persona_id="body:holmes"
        )
        approve_asset_candidate(store, novel_id="hound", candidate_id=char_cand.id)

    # Now completely cleared!
    violations3 = verify_shot_approved_references(shot, store, novel_id="hound")
    assert len(violations3) == 0
