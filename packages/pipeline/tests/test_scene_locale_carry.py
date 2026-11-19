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


def test_a_scene_break_marker_block_ends_the_scene() -> None:
    # RI ch1: block 30 is "......" between the cliff self-detonation (29) and the rainy mountain night (31); both landed in one
    # scene, so the rebirth night got the cliff's staging.
    from echotales.core.enums import BlockType
    from echotales.core.models import Block, Chapter
    from echotales.pipeline.render.scenes import group_scenes

    texts = ["Fang Yuan stood on the cliff.", "The group surged forward.", "……", "The spring rain fell on the mountain.", "He stood at the window."]
    chapter = Chapter(novel_id="x", number=1.0, title="T", source_href="a.html",
                      blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)])
    scenes = group_scenes("x", chapter, [], [], [])
    assert [s.blocks for s in scenes] == [[0, 1], [3, 4]]


def test_a_word_that_merely_contains_a_place_cue_is_not_a_place() -> None:
    # RI ch1 render of 2026-11-19: "buried deep inside the heart" (cue "inside") and "I shall still be a demon" ("shall" contains "hall")
    # each gave the cliff memories "a timber clan hall", so carry_locales then carried that hall to the self-detonation too.
    from echotales.pipeline.persona import genre
    from echotales.pipeline.persona.attire import scene_locale

    genre._PROJECT_GENRE["reverend-insanity"] = "xianxia"
    memories = ("So many memories that were buried deep inside the heart begun to relive themselves. "
                '"If the Spring Autumn Cicada that I have just cultivated is effective, I shall still be a demon in my next life!"')
    assert scene_locale("reverend-insanity", memories, strict=True) == ""
    assert scene_locale("reverend-insanity", "They walked into the great hall.", strict=True)
    genre._PROJECT_GENRE.pop("reverend-insanity", None)
