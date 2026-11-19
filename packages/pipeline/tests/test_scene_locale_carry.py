"""A scene whose text states no place keeps the place of the scene before it (or, at the chapter's start, the next stated one)."""

from __future__ import annotations

from echotales.pipeline.render.scenes import carry_locales


def test_an_unstated_scene_keeps_the_previous_scenes_place() -> None:
    # RI ch1: blocks 21-29 (the hero's memories on the cliff) state no place; the rotation gave them "a timber clan hall".
    assert carry_locales(["a narrow mountain path", "", "a small town street"]) == [
        "a narrow mountain path", "a narrow mountain path", "a small town street"]


def test_leading_unstated_scenes_take_the_first_stated_place_after_them() -> None:
    # RI ch1 block 0 is one line of shouted dialogue; the rotation put it in "a damp stone cave" before the cliff.
    assert carry_locales(["", "a narrow mountain path", ""]) == ["a narrow mountain path"] * 3


def test_a_chapter_with_no_stated_place_stays_unstated() -> None:
    assert carry_locales(["", ""]) == ["", ""]
