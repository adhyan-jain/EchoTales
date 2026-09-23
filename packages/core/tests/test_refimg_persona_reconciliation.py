"""Visual Rendering Track Phase 1d: `RefImageCandidate`/`RefImageSelectionEvent`
gain an optional `persona_id` (reconciling their self_id-only keying with
`persona/reference_gen.py`'s persona_id-keyed generated sheets) and
`RefImageCandidate` gains `quality_score` (persisting
`evaluate_candidate_quality`'s score instead of discarding it after search).

Both fields are additive and nullable -- a pre-existing row, and a candidate
found before a body split is known, genuinely have neither.
"""

from __future__ import annotations

from echotales.core.models import RefImageCandidate, RefImageSelectionEvent
from echotales.core.store import Store


def test_ref_image_candidate_persists_persona_id_and_quality_score(tmp_path):
    store = Store(str(tmp_path / "t.db"))

    candidate = RefImageCandidate(
        id="c1",
        novel_id="n1",
        self_id="self1",
        character_label="Fang Yuan",
        source_url="https://example.com/a.png",
        persona_id="self1:body2",
        quality_score=0.8,
    )
    store.add_ref_image_candidate(candidate)

    fetched = store.get_ref_image_candidate("c1")
    assert fetched is not None
    assert fetched.persona_id == "self1:body2"
    assert fetched.quality_score == 0.8


def test_ref_image_candidate_persona_id_and_quality_score_are_optional(tmp_path):
    store = Store(str(tmp_path / "t.db"))

    candidate = RefImageCandidate(
        id="c2",
        novel_id="n1",
        self_id="self1",
        character_label="Fang Yuan",
        source_url="https://example.com/b.png",
    )
    store.add_ref_image_candidate(candidate)

    fetched = store.get_ref_image_candidate("c2")
    assert fetched is not None
    assert fetched.persona_id is None
    assert fetched.quality_score is None


def test_ref_image_selection_event_persists_persona_id(tmp_path):
    store = Store(str(tmp_path / "t.db"))

    event = RefImageSelectionEvent(
        novel_id="n1",
        self_id="self1",
        candidate_id="c1",
        action="select",
        actor="user",
        persona_id="self1:body2",
    )
    store.log_ref_image_event(event)

    logged = store.get_ref_image_selection_log("n1", "self1")
    assert len(logged) == 1
    assert logged[0].persona_id == "self1:body2"


def test_migration_backfills_new_columns_on_pre_existing_database(tmp_path):
    """A database created before Phase 1d must not break -- PRAGMA-driven
    ALTER TABLE runs again on open and leaves old rows with NULL new columns."""
    db_path = str(tmp_path / "old.db")
    store = Store(db_path)
    store.add_ref_image_candidate(
        RefImageCandidate(
            id="c1",
            novel_id="n1",
            self_id="self1",
            character_label="Fang Yuan",
            source_url="https://example.com/a.png",
        )
    )
    store.close()

    # Re-opening re-runs _migrate(); this must be idempotent and non-destructive.
    reopened = Store(db_path)
    fetched = reopened.get_ref_image_candidate("c1")
    assert fetched is not None
    assert fetched.persona_id is None
    assert fetched.quality_score is None
