"""Tests for Keyframe generation engine and 4-Check automated QA gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from echotales.core.store import Store
from echotales.pipeline.assets.approval import (
    approve_asset_candidate,
    register_asset_candidate,
)
from echotales.pipeline.keyframes.engine import (
    generate_keyframe_candidates,
    generate_shot_keyframe,
)
from echotales.pipeline.keyframes.qa import (
    KeyframeQAGate,
    cosine_similarity,
)
from echotales.pipeline.screenplay.schema import (
    CameraMove,
    CharacterAppearanceRef,
    RenderTier,
    ScreenplayShot,
    ShotDialogue,
    ShotSize,
)


@pytest.fixture
def temp_store() -> Store:
    return Store(":memory:")


@pytest.fixture
def sample_shot() -> ScreenplayShot:
    return ScreenplayShot(
        shot_index=1,
        scene_id="scene_001",
        location_id="loc_study",
        characters=[
            CharacterAppearanceRef(
                self_id="char_sherlock",
                persona_id="persona_sherlock_default",
                expression="shocked",
                pose="leaning forward",
                screen_position="center",
            )
        ],
        shot_size=ShotSize.CLOSE,
        camera_move=CameraMove.SLOW_PUSH_IN,
        axis_angle=20.0,
        action="Sherlock examines the walking stick with intense focus",
        props=["walking stick", "magnifying glass"],
        duration_s=3.5,
        render_tier=RenderTier.PARALLAX_2_5D,
        dialogue=[
            ShotDialogue(
                speaker_id="char_sherlock",
                text="Look closely, Watson!",
                emotion="intense",
                intensity=2,
            )
        ],
    )


def test_cosine_similarity() -> None:
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert cosine_similarity(v1, v2) == pytest.approx(1.0)

    v3 = [0.0, 1.0, 0.0]
    assert cosine_similarity(v1, v3) == pytest.approx(0.0)

    v4 = [0.7071, 0.7071, 0.0]
    assert cosine_similarity(v1, v4) == pytest.approx(0.7071, abs=0.01)


def test_qa_individual_checks(tmp_path: Path, sample_shot: ScreenplayShot) -> None:
    img_file = tmp_path / "frame.png"
    from workers.common.stub import _generate_solid_png_b64
    import base64
    img_file.write_bytes(base64.b64decode(_generate_solid_png_b64(1080, 1920, (100, 120, 140))))

    gate = KeyframeQAGate(face_threshold=0.85, background_threshold=0.70)

    # 1. Face match with identical image reference
    res_face = gate.check_face_match(str(img_file), sample_shot, [str(img_file)])
    assert res_face.passed is True
    assert res_face.score >= 0.85

    # 2. Background match
    res_bg = gate.check_background_match(str(img_file), str(img_file))
    assert res_bg.passed is True
    assert res_bg.score >= 0.70

    # 3. VLM checklist
    res_vlm = gate.check_vlm_checklist(str(img_file), sample_shot)
    assert res_vlm.passed is True

    # 4. Artifact filter
    res_art = gate.check_artifact_filter(str(img_file))
    assert res_art.passed is True


def test_unapproved_reference_guard(temp_store: Store, sample_shot: ScreenplayShot, tmp_path: Path) -> None:
    # Neither location nor character is approved
    with pytest.raises(ValueError, match="unapproved references detected"):
        generate_keyframe_candidates(
            sample_shot,
            temp_store,
            novel_id="test_novel",
            output_dir=tmp_path / "keyframes",
        )


def test_generate_candidates_and_qa_lifecycle(
    temp_store: Store,
    sample_shot: ScreenplayShot,
    tmp_path: Path,
) -> None:
    # Setup approved dummy assets
    from workers.common.stub import _generate_solid_png_b64
    import base64

    loc_img = tmp_path / "loc_study.png"
    loc_img.write_bytes(base64.b64decode(_generate_solid_png_b64(1080, 1920, (50, 50, 70))))
    loc_cand = register_asset_candidate(
        temp_store,
        novel_id="test_novel",
        target_id="loc_study",
        target_label="221B Baker Street Study",
        file_path=loc_img,
        role="location",
    )
    approve_asset_candidate(temp_store, novel_id="test_novel", candidate_id=loc_cand.id)

    char_img = tmp_path / "char_sherlock.png"
    char_img.write_bytes(base64.b64decode(_generate_solid_png_b64(1080, 1920, (50, 50, 70))))
    char_cand = register_asset_candidate(
        temp_store,
        novel_id="test_novel",
        target_id="char_sherlock",
        target_label="Sherlock Holmes",
        file_path=char_img,
        role="sheet",
        persona_id="persona_sherlock_default",
    )
    approve_asset_candidate(temp_store, novel_id="test_novel", candidate_id=char_cand.id)

    # Generate 4 candidates
    cands = generate_keyframe_candidates(
        sample_shot,
        temp_store,
        novel_id="test_novel",
        output_dir=tmp_path / "cands",
        num_candidates=4,
    )
    assert len(cands) == 4
    for c in cands:
        assert Path(c.image_path).exists()
        assert Path(c.image_path).stat().st_size > 0

    # Test full generation pipeline with passing QA
    custom_gate = KeyframeQAGate(
        face_feature_fn=lambda path: [1.0, 0.0],
        bg_feature_fn=lambda path: [1.0, 0.0],
    )
    res_pass = generate_shot_keyframe(
        sample_shot,
        temp_store,
        novel_id="test_novel",
        output_dir=tmp_path / "pass_run",
        qa_gate=custom_gate,
    )
    assert res_pass.first_try_passed is True
    assert res_pass.flagged_for_review is False
    assert res_pass.selected_candidate.selected is True
    assert res_pass.selected_candidate.qa_report is not None
    assert res_pass.selected_candidate.qa_report.passed is True


def test_qa_failure_escalation_to_review_queue(
    temp_store: Store,
    sample_shot: ScreenplayShot,
    tmp_path: Path,
) -> None:
    # Setup approved dummy assets
    from workers.common.stub import _generate_solid_png_b64
    import base64

    loc_img = tmp_path / "loc.png"
    loc_img.write_bytes(base64.b64decode(_generate_solid_png_b64(1080, 1920, (20, 20, 20))))
    loc_cand = register_asset_candidate(
        temp_store, novel_id="test_novel", target_id="loc_study", target_label="Study", file_path=loc_img, role="location"
    )
    approve_asset_candidate(temp_store, novel_id="test_novel", candidate_id=loc_cand.id)

    char_img = tmp_path / "char.png"
    char_img.write_bytes(base64.b64decode(_generate_solid_png_b64(1080, 1920, (20, 20, 20))))
    char_cand = register_asset_candidate(
        temp_store,
        novel_id="test_novel",
        target_id="char_sherlock",
        target_label="Sherlock",
        file_path=char_img,
        role="sheet",
        persona_id="persona_sherlock_default",
    )
    approve_asset_candidate(temp_store, novel_id="test_novel", candidate_id=char_cand.id)

    # Forcing QA failure by custom failing artifact check
    strict_failing_gate = KeyframeQAGate(
        artifact_eval_fn=lambda path: ["severe_limb_distortion", "floating_watermark"],
    )

    res_fail = generate_shot_keyframe(
        sample_shot,
        temp_store,
        novel_id="test_novel",
        output_dir=tmp_path / "fail_run",
        max_retries=3,
        num_candidates_per_try=2,
        qa_gate=strict_failing_gate,
    )

    assert res_fail.first_try_passed is False
    assert res_fail.flagged_for_review is True
    assert res_fail.total_attempts == 3
    assert len(res_fail.all_candidates) == 6  # 3 attempts * 2 candidates
    assert res_fail.review_item_id is not None

    # Check that ReviewItem was recorded in store
    items = temp_store.list_review_items("test_novel")
    assert len(items) == 1
    assert items[0].id == res_fail.review_item_id
    assert items[0].kind == "keyframe_qa_failure"
    assert "failed QA after 3 attempts" in items[0].message
