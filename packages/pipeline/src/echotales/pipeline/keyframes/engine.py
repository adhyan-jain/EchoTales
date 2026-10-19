"""Keyframe Generation Engine.

Generates multi-candidate keyframes (default 4 candidates per shot) conditioned on
approved character turnarounds, expression sheets, and location master plates.
Enforces the 4-Check automated QA gate with automatic re-rolls and human review escalation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from echotales.core.models import ReviewItem
from echotales.core.store import Store
from echotales.pipeline.assets.approval import (
    get_approved_reference,
    verify_shot_approved_references,
)
from echotales.pipeline.bible.schema import StoryBibleSnapshot
from echotales.pipeline.keyframes.qa import (
    KeyframeQAGate,
    KeyframeQAReport,
)
from echotales.pipeline.screenplay.schema import (
    CameraMove,
    ScreenplayShot,
    ShotSize,
)
from workers.common.contract import ImageWorkerRequest, ImageWorkerResponse
from workers.common.stub import run_image_worker


@dataclass(slots=True)
class KeyframeCandidate:
    """An individual generated keyframe candidate."""

    id: str
    shot_index: int
    image_path: str
    seed: int
    prompt: str
    negative_prompt: str
    selected: bool = False
    qa_report: KeyframeQAReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "shot_index": self.shot_index,
            "image_path": self.image_path,
            "seed": self.seed,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "selected": self.selected,
            "qa_report": self.qa_report.to_dict() if self.qa_report else None,
        }


@dataclass(slots=True)
class ShotKeyframeResult:
    """The result of rendering keyframes for a shot, including QA outcomes."""

    shot_index: int
    selected_candidate: KeyframeCandidate
    all_candidates: list[KeyframeCandidate]
    total_attempts: int
    first_try_passed: bool
    flagged_for_review: bool
    review_item_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_index": self.shot_index,
            "selected_candidate": self.selected_candidate.to_dict(),
            "all_candidates": [c.to_dict() for c in self.all_candidates],
            "total_attempts": self.total_attempts,
            "first_try_passed": self.first_try_passed,
            "flagged_for_review": self.flagged_for_review,
            "review_item_id": self.review_item_id,
        }


def _strip_file_protocol(uri: str) -> str:
    """Convert file:// URI to local filesystem path."""
    if uri.startswith("file://"):
        return uri[len("file://"):]
    return uri


def build_shot_prompt(
    shot: ScreenplayShot,
    bible_snapshot: StoryBibleSnapshot | None = None,
) -> tuple[str, str]:
    """Compile positive and negative diffusion prompts for a shot."""
    framing_map = {
        ShotSize.ESTABLISHING: "grand cinematic establishing wide angle shot",
        ShotSize.WIDE: "full wide environmental shot",
        ShotSize.MEDIUM: "medium shot, upper body visible",
        ShotSize.CLOSE: "intense dramatic close-up shot",
        ShotSize.EXTREME_CLOSE: "extreme close-up detail shot, cinematic depth of field",
        ShotSize.REACTION: "reaction shot focusing on facial emotion",
        ShotSize.INSERT: "focused insert shot of key object or prop",
    }
    camera_map = {
        CameraMove.STATIC: "steady camera frame",
        CameraMove.SLOW_PUSH_IN: "slow push-in camera motion, dynamic leading lines",
        CameraMove.PULL_OUT: "dramatic camera pull-out revealing environment",
        CameraMove.PAN_LEFT: "horizontal pan framing",
        CameraMove.PAN_RIGHT: "horizontal pan framing",
        CameraMove.TILT_UP: "low angle looking upward",
        CameraMove.TILT_DOWN: "high angle looking downward",
        CameraMove.RACK_FOCUS: "shallow depth of field, sharp foreground",
        CameraMove.IMPACT_SHAKE: "high action impact frame, dynamic shockwave lines",
    }

    framing_desc = framing_map.get(shot.shot_size, "cinematic medium shot")
    camera_desc = camera_map.get(shot.camera_move, "steady frame")

    char_descs: list[str] = []
    for c in shot.characters:
        name = c.self_id
        if bible_snapshot:
            char_entry = bible_snapshot.get_character(c.self_id)
            if char_entry:
                name = char_entry.canonical_name
        char_descs.append(
            f"{name} ({c.expression} expression, {c.pose} pose, positioned {c.screen_position})"
        )

    chars_str = ", ".join(char_descs) if char_descs else "empty environmental scene"
    props_str = f", holding {', '.join(shot.props)}" if shot.props else ""

    positive = (
        f"{framing_desc}, {camera_desc}, {chars_str}{props_str}. "
        f"Action: {shot.action}. Location: {shot.location_id}. "
        f"Masterpiece, cinematic lighting, 8k resolution, crisp manhwa digital illustration, "
        f"vibrant colors, dramatic shadows, highly detailed artwork."
    )

    negative = (
        "low quality, blurry, distorted hands, missing fingers, extra limbs, "
        "floating text, speech bubbles, watermark, border artifacts, deformed anatomy, "
        "poorly drawn face, bad proportions, noisy background, oversaturated clipping."
    )

    return positive, negative


def generate_keyframe_candidates(
    shot: ScreenplayShot,
    store: Store,
    novel_id: str,
    output_dir: Path | str,
    *,
    num_candidates: int = 4,
    base_seed: int = 42,
    width: int = 1080,
    height: int = 1920,
    bible_snapshot: StoryBibleSnapshot | None = None,
    run_worker: Callable[[ImageWorkerRequest], ImageWorkerResponse] = run_image_worker,
) -> list[KeyframeCandidate]:
    """Generate multi-candidate keyframes conditioned on approved references."""
    violations = verify_shot_approved_references(shot, store, novel_id)
    if violations:
        raise ValueError(
            f"Cannot generate keyframes for shot {shot.shot_index}: "
            f"unapproved references detected: {'; '.join(violations)}"
        )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Collect reference image paths
    ref_image_paths: list[str] = []

    # 1. Location plate
    loc_ref = get_approved_reference(
        store, novel_id=novel_id, target_id=shot.location_id, role="location"
    )
    if loc_ref:
        ref_image_paths.append(_strip_file_protocol(loc_ref.source_url))

    # 2. Character turnarounds
    for char in shot.characters:
        char_ref = get_approved_reference(
            store,
            novel_id=novel_id,
            target_id=char.self_id,
            role="sheet",
            persona_id=char.persona_id,
        )
        if char_ref:
            ref_image_paths.append(_strip_file_protocol(char_ref.source_url))

    # Convert references to base64
    import base64

    ref_b64_list: list[str] = []
    for p in ref_image_paths:
        path_obj = Path(p)
        if path_obj.exists():
            ref_b64_list.append(base64.b64encode(path_obj.read_bytes()).decode("ascii"))

    pos_prompt, neg_prompt = build_shot_prompt(shot, bible_snapshot)

    candidates: list[KeyframeCandidate] = []
    for idx in range(num_candidates):
        seed = base_seed + idx * 1000 + shot.shot_index * 17
        req = ImageWorkerRequest(
            prompt=pos_prompt,
            negative_prompt=neg_prompt,
            reference_images_b64=ref_b64_list,
            width=width,
            height=height,
            seed=seed,
        )
        resp = run_worker(req)

        cand_filename = f"shot_{shot.shot_index:03d}_cand_{idx}.png"
        cand_path = out_path / cand_filename
        cand_path.write_bytes(resp.image_bytes)

        cand_id = f"cand_shot_{shot.shot_index}_{idx}"
        candidates.append(
            KeyframeCandidate(
                id=cand_id,
                shot_index=shot.shot_index,
                image_path=str(cand_path),
                seed=seed,
                prompt=pos_prompt,
                negative_prompt=neg_prompt,
                selected=False,
            )
        )

    return candidates


def generate_shot_keyframe(
    shot: ScreenplayShot,
    store: Store,
    novel_id: str,
    output_dir: Path | str,
    *,
    chapter: float = 1.0,
    max_retries: int = 3,
    num_candidates_per_try: int = 4,
    qa_gate: KeyframeQAGate | None = None,
    base_seed: int = 42,
    width: int = 1080,
    height: int = 1920,
    bible_snapshot: StoryBibleSnapshot | None = None,
    run_worker: Callable[[ImageWorkerRequest], ImageWorkerResponse] = run_image_worker,
) -> ShotKeyframeResult:
    """Render shot keyframe with 4-Check QA Gate, retries, and review escalation."""
    gate = qa_gate or KeyframeQAGate()
    all_evaluated_candidates: list[KeyframeCandidate] = []

    # Retrieve approved references for QA comparison
    turnaround_paths: list[str] = []
    for char in shot.characters:
        char_ref = get_approved_reference(
            store,
            novel_id=novel_id,
            target_id=char.self_id,
            role="sheet",
            persona_id=char.persona_id,
        )
        if char_ref:
            turnaround_paths.append(_strip_file_protocol(char_ref.source_url))

    loc_ref = get_approved_reference(
        store, novel_id=novel_id, target_id=shot.location_id, role="location"
    )
    loc_path = _strip_file_protocol(loc_ref.source_url) if loc_ref else None

    first_try_passed = False
    for attempt in range(max_retries):
        attempt_seed = base_seed + attempt * 10000
        batch = generate_keyframe_candidates(
            shot,
            store,
            novel_id,
            output_dir,
            num_candidates=num_candidates_per_try,
            base_seed=attempt_seed,
            width=width,
            height=height,
            bible_snapshot=bible_snapshot,
            run_worker=run_worker,
        )

        passing_candidates: list[KeyframeCandidate] = []
        for cand in batch:
            report = gate.evaluate(
                cand.image_path,
                shot,
                turnaround_paths,
                loc_path,
                re_roll_count=attempt,
                candidate_id=cand.id,
            )
            cand.qa_report = report
            if report.passed:
                passing_candidates.append(cand)

        all_evaluated_candidates.extend(batch)

        if passing_candidates:
            # Pick highest overall score
            passing_candidates.sort(
                key=lambda c: c.qa_report.overall_score if c.qa_report else 0.0,
                reverse=True,
            )
            best = passing_candidates[0]
            best.selected = True
            first_try_passed = (attempt == 0)

            return ShotKeyframeResult(
                shot_index=shot.shot_index,
                selected_candidate=best,
                all_candidates=all_evaluated_candidates,
                total_attempts=attempt + 1,
                first_try_passed=first_try_passed,
                flagged_for_review=False,
                review_item_id=None,
            )

    # All attempts failed QA: select the highest scoring candidate across all attempts
    all_evaluated_candidates.sort(
        key=lambda c: c.qa_report.overall_score if c.qa_report else 0.0,
        reverse=True,
    )
    best = all_evaluated_candidates[0]
    best.selected = True

    # Escalate to human review item queue
    rev_id = f"rev_qa_shot_{shot.shot_index}_{int(time.time())}"
    score_str = f"{best.qa_report.overall_score:.3f}" if best.qa_report else "0.0"
    reasons_str = "; ".join(best.qa_report.reasons) if best.qa_report else "all checks failed"
    review_item = ReviewItem(
        id=rev_id,
        novel_id=novel_id,
        chapter=chapter,
        kind="keyframe_qa_failure",
        message=(
            f"Shot {shot.shot_index} failed QA after {max_retries} attempts "
            f"(best score: {score_str}). Reasons: {reasons_str}"
        ),
        candidates=[c.to_dict() for c in all_evaluated_candidates[:4]],
        resolved=False,
        created_at=time.time(),
    )
    store.add_review_item(review_item)

    return ShotKeyframeResult(
        shot_index=shot.shot_index,
        selected_candidate=best,
        all_candidates=all_evaluated_candidates,
        total_attempts=max_retries,
        first_try_passed=False,
        flagged_for_review=True,
        review_item_id=rev_id,
    )
