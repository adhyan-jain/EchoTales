"""Hand-authored staging for panels a general-purpose director gets wrong
(§4.30 -- requested after watching the composed video, not from a single
generation)."""

from __future__ import annotations

from echotales.pipeline.render.beat_canon import beat_canon_for


class TestBeatCanonLookup:
    def test_a_seeded_block_returns_its_entry(self) -> None:
        entry = beat_canon_for("reverend-insanity", 1.0, 83)
        assert entry is not None
        assert "pool of blood" in entry.staging

    def test_an_unseeded_block_returns_none(self) -> None:
        """Zero coverage on an unseeded block, never a generic guess --
        same trade-off `persona/canon.py::CANON_APPEARANCE` makes."""
        assert beat_canon_for("reverend-insanity", 1.0, 40) is None

    def test_an_unseeded_novel_returns_none(self) -> None:
        assert beat_canon_for("lord-of-the-mysteries", 1.0, 83) is None

    def test_an_unseeded_chapter_returns_none(self) -> None:
        assert beat_canon_for("reverend-insanity", 2.0, 83) is None

    def test_block_range_boundaries_are_inclusive(self) -> None:
        entry = beat_canon_for("reverend-insanity", 1.0, 0)
        assert entry is not None
        assert entry.block_from == 0
        assert beat_canon_for("reverend-insanity", 1.0, 1) is entry

    def test_the_opening_forces_an_establishing_shot(self) -> None:
        entry = beat_canon_for("reverend-insanity", 1.0, 0)
        assert entry is not None
        assert entry.style_override == "establishing"

    def test_the_rebirth_forces_a_scene_shot_not_a_closeup(self) -> None:
        """A tight face close-up -- the default for a dialogue block --
        would crop out the raised palms and the cicada, which are the
        point of the staging."""
        entry = beat_canon_for("reverend-insanity", 1.0, 83)
        assert entry is not None
        assert entry.style_override == "scene"
