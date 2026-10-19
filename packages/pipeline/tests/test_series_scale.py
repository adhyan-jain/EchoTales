"""Unit tests for Phase 3: Pre-Render Cost Meter, Arc Continuity, and Screenplay Persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from echotales.core.enums import Prominence
from echotales.core.models import DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.bible.arc import audit_arc_continuity
from echotales.pipeline.cost import estimate_episode_cost
from echotales.pipeline.screenplay.schema import (
    CameraMove,
    CharacterAppearanceRef,
    RenderTier,
    ScreenplayEpisode,
    ScreenplayScene,
    ScreenplayShot,
    ShotDialogue,
    ShotSize,
)


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


@pytest.fixture
def sample_episode() -> ScreenplayEpisode:
    shots = [
        ScreenplayShot(
            shot_index=i,
            scene_id="scene_001",
            location_id="loc_221b",
            characters=[
                CharacterAppearanceRef("holmes", "persona_holmes", expression="neutral")
            ],
            shot_size=ShotSize.MEDIUM,
            camera_move=CameraMove.SLOW_PUSH_IN,
            duration_s=3.5,
            render_tier=RenderTier.PARALLAX_2_5D,
            dialogue=[
                ShotDialogue(
                    speaker_id="holmes",
                    text="Eliminate all other factors, and the one which remains must be the truth.",
                    emotion="neutral",
                    intensity=1,
                )
            ],
        )
        for i in range(16)
    ]
    scene = ScreenplayScene(
        scene_index=1,
        scene_id="scene_001",
        location_id="loc_221b",
        time_of_day="day",
        shots=shots,
    )
    return ScreenplayEpisode(
        episode_id="ep_001",
        novel_id="showcase",
        chapter_range=(1.0, 1.0),
        title="Chapter 1: Mr. Sherlock Holmes",
        scenes=[scene],
    )


def test_cost_estimator_path1_and_path2(sample_episode: ScreenplayEpisode) -> None:
    # 1. Path 1 Cost Estimate (2.5D Reels)
    p1 = estimate_episode_cost(sample_episode, novel_id="showcase", tier="path1")
    assert p1.num_shots == 16
    assert p1.total_cost_usd > 0.0
    # Path 1 finished minute cost is <= $0.50
    assert p1.cost_per_finished_minute_usd <= 0.50
    assert p1.video_cost_usd == pytest.approx(0.0)

    # 2. Path 2 Cost Estimate (Wan 2.2 Video Upgrade)
    p2 = estimate_episode_cost(sample_episode, novel_id="showcase", tier="path2")
    assert p2.video_cost_usd > 0.0
    # Path 2 finished minute cost target is <= $1.80
    assert p2.cost_per_finished_minute_usd <= 1.80


def test_screenplay_episode_persistence(store: Store, sample_episode: ScreenplayEpisode) -> None:
    store.save_screenplay_episode(
        episode_id=sample_episode.episode_id,
        novel_id=sample_episode.novel_id,
        episode_dict=sample_episode.to_dict(),
        title=sample_episode.title,
    )

    retrieved = store.get_screenplay_episode(sample_episode.episode_id)
    assert retrieved is not None
    assert retrieved["episode_id"] == "ep_001"
    assert len(retrieved["scenes"]) == 1
    assert len(retrieved["scenes"][0]["shots"]) == 16

    all_eps = store.list_screenplay_episodes("showcase")
    assert len(all_eps) == 1
    assert all_eps[0]["title"] == "Chapter 1: Mr. Sherlock Holmes"


def test_arc_continuity_audit(store: Store) -> None:
    # Set up character in chapter 1
    store.add_self(
        Self(
            id="char_watson",
            novel_id="showcase",
            canonical_label="Dr. Watson",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
            prominence=Prominence.PRINCIPAL,
        )
    )
    store.conn.execute(
        "INSERT INTO attribute(novel_id, target_kind, target_id, key, value, timeline_id, "
        "story_from_lb, story_from_ub, story_to_lb, story_to_ub, learned_chapter, learned_offset, "
        "observer_id, asserted_by, truth_status) "
        "VALUES('showcase', 'SELF', 'char_watson', 'hair_color', 'brown', 'tl', 1, 1, 20, 20, 1, 0, 'OBS', 'NARR', 'TRUE')"
    )

    # In chapter 2, attribute mutates to 'blonde' without retraction or persona shift
    store.conn.execute(
        "INSERT INTO attribute(novel_id, target_kind, target_id, key, value, timeline_id, "
        "story_from_lb, story_from_ub, story_to_lb, story_to_ub, learned_chapter, learned_offset, "
        "observer_id, asserted_by, truth_status) "
        "VALUES('showcase', 'SELF', 'char_watson', 'hair_color', 'blonde', 'tl', 2, 2, 20, 20, 2, 0, 'OBS', 'NARR', 'TRUE')"
    )
    store.conn.commit()

    report = audit_arc_continuity(store, "showcase", chapter_start=1.0, chapter_end=2.0)
    assert report.total_snapshots_audited == 2
    assert len(report.issues) == 1
    assert report.issues[0].kind == "unrecorded_appearance_mutation"
    assert "hair_color" in report.issues[0].message
