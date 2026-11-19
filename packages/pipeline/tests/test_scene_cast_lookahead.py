"""A beat that addresses a character by name, in a scene where he is present later, has him in its cast."""

from __future__ import annotations

from types import SimpleNamespace

from echotales.core.enums import ReferenceMode
from echotales.pipeline.render.panels import addressed_scene_cast


def m(block: int, target: str, mode: ReferenceMode) -> SimpleNamespace:
    return SimpleNamespace(block_index=block, target_id=target, reference_mode=mode)


def test_the_hero_shouted_at_in_the_opening_blocks_is_in_the_cast_because_the_scene_shows_him_present_later() -> None:
    """RI ch1 blocks 0-3 are the sect fighters' ultimatum; Fang Yuan is named in them (dialogue reference) and first
    PRESENT in block 5, so the 2026-11-16 render drew the crowd panels with CAST empty and no Fang Yuan in them."""
    mentions = [
        m(0, "fy", ReferenceMode.DIALOGUE_REFERENCE), m(1, "fy", ReferenceMode.DIALOGUE_REFERENCE),
        m(5, "fy", ReferenceMode.PRESENT), m(9, "elder", ReferenceMode.PRESENT),
    ]
    assert addressed_scene_cast(mentions, beat_blocks=[0, 1], scene_blocks=list(range(0, 20))) == ["fy"]


def test_someone_merely_named_in_the_beat_and_never_present_in_the_scene_is_not_pulled_in() -> None:
    mentions = [m(0, "ghost", ReferenceMode.DIALOGUE_REFERENCE), m(5, "fy", ReferenceMode.PRESENT)]
    assert addressed_scene_cast(mentions, beat_blocks=[0], scene_blocks=list(range(10))) == []


def test_a_present_character_of_the_scene_not_named_in_this_beat_is_not_pulled_in() -> None:
    mentions = [m(0, "fy", ReferenceMode.DIALOGUE_REFERENCE), m(5, "elder", ReferenceMode.PRESENT)]
    assert addressed_scene_cast(mentions, beat_blocks=[0], scene_blocks=list(range(10))) == []
