"""Asset Studio reference approval lifecycle and render queue guard.

Ensures no unapproved character turnaround sheet or location plate enters
the keyframe or video rendering queue (enforcing consistency plan Phase 1).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from echotales.core.models import (
    RefImageCandidate,
    RefImageSelectionEvent,
)
from echotales.core.store import Store
from echotales.pipeline.screenplay.schema import ScreenplayShot


def register_asset_candidate(
    store: Store,
    *,
    novel_id: str,
    target_id: str,
    target_label: str,
    file_path: Path | str,
    role: str = "sheet",  # "sheet" | "location" | "expression"
    persona_id: str | None = None,
    quality_score: float = 1.0,
) -> RefImageCandidate:
    """Register a generated turnaround or plate candidate awaiting human approval."""
    path_str = str(file_path)
    file_bytes = Path(path_str).read_bytes() if Path(path_str).exists() else b""
    digest = hashlib.sha1(file_bytes).hexdigest()[:12] if file_bytes else "raw"
    cid = f"cand_{role}_{target_id}_{digest}"

    candidate = RefImageCandidate(
        id=cid,
        novel_id=novel_id,
        self_id=target_id,
        character_label=target_label,
        source_url=f"file://{path_str}",
        thumbnail_url=f"file://{path_str}",
        title=f"{target_label} {role}",
        backend="qwen-image",
        found_at=time.time(),
        user_uploaded=False,
        selected=False,
        persona_id=persona_id,
        quality_score=quality_score,
        role=role,
    )
    store.add_ref_image_candidate(candidate)
    return candidate


def approve_asset_candidate(
    store: Store,
    *,
    novel_id: str,
    candidate_id: str,
    note: str = "",
) -> RefImageSelectionEvent:
    """Approve candidate as active conditioning reference for generation."""
    cand = store.get_ref_image_candidate(candidate_id)
    if cand is None or cand.novel_id != novel_id:
        raise KeyError(f"candidate {candidate_id!r} not found for novel {novel_id!r}")

    # Demote previously selected candidates for this target, role, and persona
    existing = store.list_ref_image_candidates(
        novel_id, cand.self_id, persona_id=cand.persona_id, role=cand.role
    )
    for c in existing:
        if c.selected and c.id != candidate_id:
            c.selected = False
            store.add_ref_image_candidate(c)

    cand.selected = True
    store.add_ref_image_candidate(cand)

    event = RefImageSelectionEvent(
        novel_id=novel_id,
        self_id=cand.self_id,
        candidate_id=candidate_id,
        action="approve",
        actor="user",
        note=note,
        at=time.time(),
        persona_id=cand.persona_id,
    )
    store.log_ref_image_event(event)
    return event


def reject_asset_candidate(
    store: Store,
    *,
    novel_id: str,
    candidate_id: str,
    note: str = "",
) -> RefImageSelectionEvent:
    """Reject candidate from being used as conditioning reference."""
    cand = store.get_ref_image_candidate(candidate_id)
    if cand is None or cand.novel_id != novel_id:
        raise KeyError(f"candidate {candidate_id!r} not found for novel {novel_id!r}")

    cand.selected = False
    store.add_ref_image_candidate(cand)

    event = RefImageSelectionEvent(
        novel_id=novel_id,
        self_id=cand.self_id,
        candidate_id=candidate_id,
        action="reject",
        actor="user",
        note=note,
        at=time.time(),
        persona_id=cand.persona_id,
    )
    store.log_ref_image_event(event)
    return event


def get_approved_reference(
    store: Store,
    *,
    novel_id: str,
    target_id: str,
    role: str = "sheet",
    persona_id: str | None = None,
) -> RefImageCandidate | None:
    """Retrieve the currently approved reference candidate, if any."""
    candidates = store.list_ref_image_candidates(
        novel_id, target_id, persona_id=persona_id, role=role
    )
    for c in candidates:
        if c.selected:
            return c
    return None


def verify_shot_approved_references(
    shot: ScreenplayShot,
    store: Store,
    novel_id: str,
) -> list[str]:
    """Verify that all characters and location in shot have approved references.
    
    Returns a list of unapproved violation descriptors. Empty list means fully cleared.
    """
    violations: list[str] = []

    # Check location plate
    loc_ref = get_approved_reference(store, novel_id=novel_id, target_id=shot.location_id, role="location")
    if loc_ref is None:
        violations.append(f"UNAPPROVED_LOCATION_PLATE: location {shot.location_id} has no approved plate")

    # Check character turnaround sheets
    for char in shot.characters:
        char_ref = get_approved_reference(
            store,
            novel_id=novel_id,
            target_id=char.self_id,
            role="sheet",
            persona_id=char.persona_id,
        )
        if char_ref is None:
            violations.append(
                f"UNAPPROVED_CHARACTER_SHEET: character {char.self_id} (persona {char.persona_id}) has no approved sheet"
            )

    return violations
