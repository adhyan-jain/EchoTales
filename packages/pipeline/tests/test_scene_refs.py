"""Curated scene/character reference matching (`render/scene_refs.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from echotales.pipeline.render.scene_refs import (
    curated_character_reference,
    match_scene_references,
)


@pytest.fixture
def refs(tmp_path: Path) -> Path:
    for slug in (
        "one-vs-many-01",
        "one-vs-many-02",
        "ancestral-hall-exterior-01",
        "mountain-sect-01",
        "fang-yuan-ref-01",
        "fang-yuan-young-01",
    ):
        (tmp_path / f"{slug}.png").write_bytes(b"")
    return tmp_path


def test_one_vs_many_needs_a_mob(refs: Path) -> None:
    text = "Enemies surrounded the hall on every side."
    assert match_scene_references(text, has_mob=True, root=refs) == [
        refs / "one-vs-many-01.png"
    ]
    # Same words, two people in frame: the army composition would invent a
    # crowd the scene does not have.
    assert match_scene_references(text, has_mob=False, root=refs) == []


def test_closeups_get_no_composition_reference(refs: Path) -> None:
    assert (
        match_scene_references(
            "Enemies surrounded him", has_mob=True, closeup=True, root=refs
        )
        == []
    )


def test_locale_matches_without_a_mob(refs: Path) -> None:
    assert match_scene_references("the ancestral hall stood dark", root=refs) == [
        refs / "ancestral-hall-exterior-01.png"
    ]


def test_specific_composition_wins_over_general_locale(refs: Path) -> None:
    # Both cue: "besieged" (composition) and "mountain" (locale). One image
    # only, and it should be the one that answers the harder question.
    text = "Besieged on the mountain, he stood alone."
    assert match_scene_references(text, has_mob=True, root=refs) == [
        refs / "one-vs-many-01.png"
    ]


def test_limit_caps_the_set(refs: Path) -> None:
    text = "A crowd of disciples besieged the mountain sect."
    assert len(match_scene_references(text, has_mob=True, limit=2, root=refs)) == 2


def test_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert match_scene_references("besieged", has_mob=True, root=tmp_path) == []


def test_curated_portrait_beats_nothing_for_unknown_characters(refs: Path) -> None:
    assert curated_character_reference("Gu Yue Bo", chapter=1.0, root=refs) is None


def test_youth_portrait_applies_early_and_stops_later(refs: Path) -> None:
    assert (
        curated_character_reference("Fang Yuan", chapter=1.0, root=refs)
        == refs / "fang-yuan-young-01.png"
    )
    assert (
        curated_character_reference("Fang Yuan", chapter=500.0, root=refs)
        == refs / "fang-yuan-ref-01.png"
    )


def test_label_matching_is_case_insensitive(refs: Path) -> None:
    assert curated_character_reference("  FANG YUAN ", chapter=500.0, root=refs) is not None
