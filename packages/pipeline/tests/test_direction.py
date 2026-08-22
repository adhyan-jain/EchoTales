"""Director cast-constraint guardrails (render/direction.py)."""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.render.direction import PanelDirection, _validate_direction


def _store_with_two_characters(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="Fang Yuan stood alone.")],
        )
    )
    store.add_self(
        Self(
            id="t:self1",
            novel_id="t",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
            kind=TargetKind.SELF,
        )
    )
    # A real character who is simply not present in this beat's cast --
    # e.g. a later-chapter character, mirroring the Bai Ning Bing/ch1 case.
    store.add_self(
        Self(
            id="t:self2",
            novel_id="t",
            canonical_label="Bai Ning Bing",
            first_attested_pos=DiscoursePosition(chapter=108.0, offset=0),
            kind=TargetKind.SELF,
        )
    )
    store.conn.commit()
    return store


class TestValidateCharacterNames:
    def test_cast_member_is_kept(self, tmp_path) -> None:
        store = _store_with_two_characters(tmp_path)
        d = PanelDirection(action="Fang Yuan stands alone in the courtyard.")
        d = _validate_direction(
            d,
            beat_text="Fang Yuan stood alone.",
            cast={"Fang Yuan": "black hair, white robe"},
            novel_id="t",
            store=store,
        )
        assert "Fang Yuan" in d.action

    def test_out_of_scene_known_character_is_stripped(self, tmp_path) -> None:
        store = _store_with_two_characters(tmp_path)
        d = PanelDirection(action="Fang Yuan stands beside Bai Ning Bing.")
        d = _validate_direction(
            d,
            beat_text="Fang Yuan stood alone.",
            cast={"Fang Yuan": "black hair, white robe"},
            novel_id="t",
            store=store,
        )
        assert "Bai Ning Bing" not in d.action
        assert "Fang Yuan" in d.action

    def test_fabricated_name_is_stripped(self, tmp_path) -> None:
        store = _store_with_two_characters(tmp_path)
        d = PanelDirection(action="Fang Yuan stands beside Zhang Wei.")
        d = _validate_direction(
            d,
            beat_text="Fang Yuan stood alone.",
            cast={"Fang Yuan": "black hair, white robe"},
            novel_id="t",
            store=store,
        )
        assert "Zhang Wei" not in d.action
        assert "Fang Yuan" in d.action

    def test_possessive_cast_member_is_not_flagged_as_fabricated(self, tmp_path) -> None:
        store = _store_with_two_characters(tmp_path)
        d = PanelDirection(action="Fang Yuan's sword glints in the light.")
        d = _validate_direction(
            d,
            beat_text="Fang Yuan stood alone.",
            cast={"Fang Yuan": "black hair, white robe"},
            novel_id="t",
            store=store,
        )
        assert "Fang Yuan" in d.action

    def test_indefinite_pronoun_is_not_flagged_as_fabricated(self, tmp_path) -> None:
        store = _store_with_two_characters(tmp_path)
        d = PanelDirection(action="Everyone falls silent.")
        d = _validate_direction(
            d,
            beat_text="Fang Yuan stood alone.",
            cast={"Fang Yuan": "black hair, white robe"},
            novel_id="t",
            store=store,
        )
        assert "Everyone" in d.action

    def test_no_store_skips_name_validation(self, tmp_path) -> None:
        d = PanelDirection(action="Fang Yuan stands beside Bai Ning Bing.")
        d = _validate_direction(
            d,
            beat_text="Fang Yuan stood alone.",
            cast={"Fang Yuan": "black hair, white robe"},
            novel_id="t",
            store=None,
        )
        # No store/novel_id -> validation is skipped, not crashed.
        assert "Bai Ning Bing" in d.action
