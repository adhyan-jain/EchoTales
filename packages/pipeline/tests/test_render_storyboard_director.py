from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.storyboard_director import plan_storyboard_for_beat
from echotales.pipeline.render.storyboard_schema import (
    CaptionStyle,
    ProseDisposition,
    ScreenDirection,
    ShotType,
)


def test_storyboard_director_dialogue_and_reaction():
    span1 = Span(
        id="s1",
        novel_id="ri",
        chapter=1,
        block_index=1,
        start=0,
        end=50,
        span_type=SpanType.DIALOGUE,
        text="Fang Yuan, hand over the Spring Autumn Cicada!",
        speaker_self_id="elder_tie",
        delivery_markers=["shouted"],
    )
    span2 = Span(
        id="s2",
        novel_id="ri",
        chapter=1,
        block_index=2,
        start=51,
        end=100,
        span_type=SpanType.DIALOGUE,
        text="Heh, righteous hypocrites.",
        speaker_self_id="fang_yuan",
        delivery_markers=["sneered"],
    )

    seq = plan_storyboard_for_beat(
        scene_id="cliff_scene",
        beat_id="beat_01",
        spans=[span1, span2],
        cast_names=["elder_tie", "fang_yuan"],
        segment_palette_id="battle_dusk",
    )

    # Assert sequence is populated
    assert seq.total_panels() >= 2
    # Verify shout style on span1
    shout_panel = next(p for p in seq.panels if p.speaking_character == "elder_tie")
    assert shout_panel.caption_style == CaptionStyle.SHOUT
    assert shout_panel.shot_type == ShotType.CLOSE_UP

    # Verify 180-degree axis directions
    assert shout_panel.screen_direction == ScreenDirection.FACING_RIGHT
    fy_panel = next(p for p in seq.panels if p.speaking_character == "fang_yuan")
    assert fy_panel.screen_direction == ScreenDirection.FACING_LEFT

    # Verify reaction shot exists
    assert seq.reaction_panel_count() >= 1


def test_storyboard_director_crowd_speech():
    crowd_span = Span(
        id="c1",
        novel_id="ri",
        chapter=1,
        block_index=3,
        start=0,
        end=40,
        span_type=SpanType.DIALOGUE,
        text="Kill him! Don't let the demon escape!",
        speaker_self_id=None,
        co_speaker_self_ids=["cultivator_1", "cultivator_2"],
    )

    seq = plan_storyboard_for_beat(
        scene_id="cliff_scene",
        beat_id="beat_02",
        spans=[crowd_span],
        cast_names=["fang_yuan"],
        segment_palette_id="battle_dusk",
    )

    crowd_panel = seq.panels[0]
    assert crowd_panel.is_crowd_shot is True
    assert crowd_panel.caption_style == CaptionStyle.CROWD_COLLECTIVE
    assert "crowd" in crowd_panel.subjects


def test_storyboard_director_prose_adaptation():
    action_span = Span(
        id="a1",
        novel_id="ri",
        chapter=1,
        block_index=4,
        start=0,
        end=60,
        span_type=SpanType.NARRATION_ACTION,
        text="Blood trickled from his wounded arm as he stepped back towards the precipice.",
    )
    thought_span = Span(
        id="t1",
        novel_id="ri",
        chapter=1,
        block_index=5,
        start=61,
        end=120,
        span_type=SpanType.INNER_MONOLOGUE,
        text="Five hundred years of cultivation... will it truly end today?",
        speaker_self_id="fang_yuan",
    )

    seq = plan_storyboard_for_beat(
        scene_id="cliff_scene",
        beat_id="beat_03",
        spans=[action_span, thought_span],
        cast_names=["fang_yuan"],
        segment_palette_id="battle_dusk",
    )

    assert seq.total_panels() >= 2
    # Verify thought is kept as caption
    thought_p = next(p for p in seq.panels if p.caption_style == CaptionStyle.THOUGHT)
    assert thought_p.prose_disposition == ProseDisposition.KEEP_TEXT

    # Verify action panel is SHOW
    action_p = next(p for p in seq.panels if p.source_span_ids == ["a1"])
    assert action_p.prose_disposition == ProseDisposition.SHOW
