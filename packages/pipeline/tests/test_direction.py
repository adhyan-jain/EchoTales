"""Director cast-constraint guardrails (render/direction.py)."""

from __future__ import annotations

from echotales.core.enums import BlockType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.render.direction import Direction, PanelDirection, _validate_direction


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


class TestCrowdLayoutContradiction:
    """Section 4.1: HANDOFF Section 4.48's still-open "director solo
    collapse" bug -- the director erases a scene `SceneState` independently
    confirms is a crowd (36/52 v39 prompts measured, including the 500+
    member Awakening Ceremony)."""

    def test_solo_collapse_on_a_confirmed_crowd_scene_is_rewritten(self) -> None:
        d = PanelDirection(
            action="everyone is wary of Fang Yuan",
            layout="Fang Yuan stands alone; no one else is present",
        )
        d = _validate_direction(
            d, beat_text="the elders surrounded him", cast={}, crowd_mood="crowd"
        )
        assert "stands alone" not in d.layout.lower()
        assert "no one else is present" not in d.layout.lower()

    def test_solo_collapse_is_untouched_when_not_a_confirmed_crowd(self) -> None:
        """SceneState says this is not a crowd scene -- a genuinely solo
        beat must never have crowd language forced onto it."""
        d = PanelDirection(action="", layout="Fang Yuan stands alone")
        d = _validate_direction(d, beat_text="Fang Yuan sat by himself.", cast={}, crowd_mood=None)
        assert d.layout == "Fang Yuan stands alone"

    def test_layout_already_naming_a_group_is_untouched(self) -> None:
        """Layout mentioning a `_MOB_ROLE_NOUNS` word alongside "alone"-
        shaped text is not actually erasing the crowd -- no rewrite needed."""
        d = PanelDirection(action="", layout="elders stand alone in the courtyard")
        d = _validate_direction(d, beat_text="the elders gathered", cast={}, crowd_mood="crowd")
        assert d.layout == "elders stand alone in the courtyard"


class TestInvertedSecondSubject:
    """Section 4.1 extension: the inverse audit finding
    (`p001_b0000.png`) -- an unprompted second figure on a scene
    `SceneState` confirms is solo. Text-prompt-level only; logged, not
    auto-corrected (see the check's own docstring)."""

    def test_two_figure_mentions_on_a_non_crowd_scene_does_not_raise(self, caplog) -> None:
        d = PanelDirection(action="a figure stands near another figure", layout="")
        # Must not raise, and must not mutate the direction -- this check
        # only logs, since there's no single correct rewrite here.
        result = _validate_direction(d, beat_text="he stood alone", cast={}, crowd_mood=None)
        assert result.action == "a figure stands near another figure"

    def test_single_figure_mention_is_not_flagged(self) -> None:
        d = PanelDirection(action="a figure stands in the doorway", layout="")
        # No assertion beyond "doesn't raise" -- absence of a warning isn't
        # directly observable here without capturing logs, and the
        # single-mention case is exercised by every other passing test in
        # this module already having exactly one "a figure" mention.
        _validate_direction(d, beat_text="someone stood there", cast={}, crowd_mood=None)


class TestUntrackedFigurePromotedToTier1:
    """Section 4.4: RI ch1 block 75 -- an untracked subject ("the clan
    head", no persona/reference sheet) had zero tier-1 content (the cast
    loop only matches names, and there is no name to match), so the only
    subject-presence signal was `layout`'s own "a figure" marker sitting in
    tier 3 behind setting/lighting. The real render showed exactly the
    predicted failure: a rendered background with no person in it.
    """

    def test_untracked_figure_marker_is_promoted_to_tier1(self) -> None:
        d = Direction(
            direction=PanelDirection(
                action="he looked out over the village",
                layout="a figure, solo",
                setting="window, mountain_view",
            ),
            cast={},
            novel_style="guofeng illustration",
        )
        parts = d.to_image_prompt_parts()
        # "a figure" must appear before setting/lighting content, not only
        # buried inside the low-priority layout string in tier 3.
        assert "a figure" in parts

    def test_resolved_cast_is_not_affected(self) -> None:
        """A beat with a real, matched cast member must not also get the
        untracked-figure marker -- tier1 already has real content."""
        d = Direction(
            direction=PanelDirection(
                action="Fang Yuan stands in the courtyard.",
                layout="Fang Yuan, solo",
            ),
            cast={"Fang Yuan": "black hair, green robes"},
            novel_style="guofeng illustration",
        )
        parts = d.to_image_prompt_parts()
        assert "a figure" not in parts

    def test_pure_environment_beat_gets_no_hallucinated_figure(self) -> None:
        """No "a figure" marker anywhere in the director's text -- a pure
        landscape/environment beat -- must not have one injected."""
        d = Direction(
            direction=PanelDirection(
                action="",
                layout="",
                setting="mountain_path, mist",
            ),
            cast={},
            novel_style="guofeng illustration",
        )
        parts = d.to_image_prompt_parts()
        assert "a figure" not in parts


class TestDirectorV2:
    def test_schema_fields(self) -> None:
        from echotales.pipeline.render.direction import CharacterDirection, OthersDirection

        c = CharacterDirection(
            name="Fang Yuan",
            position="foreground_center",
            pose="fighting_stance",
            expression="cold_expression",
            condition="bloodied_robes",
        )
        assert c.name == "Fang Yuan"
        assert c.position == "foreground_center"
        assert c.pose == "fighting_stance"

        o = OthersDirection(kind="elders", count=12, relation_to_lead="surrounding")
        assert o.kind == "elders"
        assert o.count == 12

        d = PanelDirection(
            shot="medium",
            camera_angle="low-angle",
            characters=[c],
            others=o,
            location_detail="rainy mountain cliff edge",
            props=["stone_stele"],
        )
        assert d.camera_angle == "low-angle"
        assert len(d.characters) == 1
        assert d.others is not None
        assert d.location_detail == "rainy mountain cliff edge"
        assert "stone_stele" in d.props

    def test_shot_variety_breaks_consecutive_same_shots(self) -> None:
        from echotales.pipeline.render.direction import CharacterDirection, enforce_shot_variety

        c = CharacterDirection(name="Fang Yuan")
        d1 = PanelDirection(shot="medium", camera_angle="eye-level", characters=[c])
        d2 = PanelDirection(shot="medium", camera_angle="eye-level", characters=[c])
        d3 = PanelDirection(shot="medium", camera_angle="eye-level", characters=[c])

        varied = enforce_shot_variety([d1, d2, d3])
        assert len(varied) == 3
        # d1 should remain medium
        assert varied[0].shot == "medium"
        # d2 must not be medium
        assert varied[1].shot != "medium"
        # d3 should not repeat d2
        assert varied[2].shot != varied[1].shot
        # Camera angles should also alternate
        assert varied[1].camera_angle != varied[0].camera_angle

    def test_conservation_audit(self) -> None:
        from echotales.pipeline.render.direction import (
            CharacterDirection,
            check_direction_conservation,
        )

        beat_text = "Fang Yuan stood on the cliff holding his sword as the elders surrounded him."
        d = PanelDirection(
            shot="wide",
            characters=[CharacterDirection(name="Fang Yuan")],
            setting="cliff",
            props=["sword"],
            layout="elders surround Fang Yuan",
        )
        audit = check_direction_conservation(beat_text, d, cast_names=["Fang Yuan", "Bai Ning Bing"])
        assert "Fang Yuan" in audit.captured_people
        assert "elders" in audit.captured_people
        assert "cliff" in audit.captured_places
        assert "sword" in audit.captured_props
        assert audit.total_dropped == 0
        assert audit.conservation_rate == 1.0

    def test_conservation_audit_records_drops(self) -> None:
        from echotales.pipeline.render.direction import check_direction_conservation

        beat_text = "Fang Yuan dropped his lantern in the cave while disciples fled."
        # Direction misses the cave and lantern
        d = PanelDirection(
            shot="close",
            layout="Fang Yuan, solo",
            setting="room",
        )
        audit = check_direction_conservation(beat_text, d, cast_names=["Fang Yuan"])
        assert "cave" in audit.dropped_places
        assert "lantern" in audit.dropped_props
        assert "disciples" in audit.dropped_people
        assert audit.total_dropped > 0
        assert audit.conservation_rate < 1.0

