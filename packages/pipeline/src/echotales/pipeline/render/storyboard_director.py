"""The Storyboard Director (P2).

Translates narrative beats into structured StoryboardSequences using:
- The Volume Bible (appearance epochs, reveals, setup/payoffs, segment palettes)
- Camera & spatial continuity planning (180-degree axis, shot variety)
- Selective prose adaptation (KEEP_TEXT / SHOW / CUT)
- Collective crowd voice resolution
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from echotales.core.bible import VolumeBible
from echotales.core.enums import SpanType
from echotales.core.models import DiscoursePosition, Span
from echotales.pipeline.render.camera_planner import (
    enforce_180_degree_axis,
    enforce_shot_variety,
    ensure_reaction_shots,
)
from echotales.pipeline.render.selective_adaptation import adapt_spans
from echotales.pipeline.render.storyboard_schema import (
    CameraAngle,
    CaptionStyle,
    NarrativeFunction,
    ProseDisposition,
    ScreenDirection,
    ShotType,
    StoryboardPanel,
    StoryboardSequence,
)

log = logging.getLogger(__name__)


def plan_storyboard_for_beat(
    *,
    scene_id: str,
    beat_id: str,
    spans: Sequence[Span],
    cast_names: list[str],
    bible: VolumeBible | None = None,
    discourse_pos: DiscoursePosition | None = None,
    segment_palette_id: str = "battle_dusk",
) -> StoryboardSequence:
    """Plan a structured StoryboardSequence from a dramatic beat and its spans."""
    pos = discourse_pos or DiscoursePosition(chapter=1, offset=0)
    palette_id = segment_palette_id

    # 1. Classify spans for prose disposition
    decisions = adapt_spans(spans)

    # 2. Extract dialogue and narrative beats
    panels: list[StoryboardPanel] = []
    p_idx = 1

    dialogue_spans = [s for s in spans if s.span_type == SpanType.DIALOGUE]
    prose_spans = [s for s in spans if s.span_type != SpanType.DIALOGUE]

    # If this beat opens a scene, add an establishing shot
    if not panels and prose_spans:
        panels.append(
            StoryboardPanel(
                panel_id=f"{beat_id}_p{p_idx:02d}",
                scene_id=scene_id,
                beat_id=beat_id,
                panel_index=p_idx,
                narrative_function=NarrativeFunction.ESTABLISHING,
                shot_type=ShotType.WIDE,
                camera_angle=CameraAngle.EYE_LEVEL,
                screen_direction=ScreenDirection.FRONT,
                subjects=cast_names[:2],
                environment_visual="Setting and spatial layout",
                segment_palette=palette_id,
                prose_disposition=ProseDisposition.SHOW,
                source_span_ids=[prose_spans[0].id],
            )
        )
        p_idx += 1

    # Plan panels for dialogue and action
    for span, dec in zip(spans, decisions):
        if dec.disposition == ProseDisposition.CUT:
            continue

        if span.span_type == SpanType.DIALOGUE:
            speaker = span.speaker_self_id or "unattributed_crowd"
            is_crowd = (speaker == "unattributed_crowd" or len(span.co_speaker_self_ids) > 0)
            caption_style = CaptionStyle.CROWD_COLLECTIVE if is_crowd else CaptionStyle.SPEECH
            if "shout" in " ".join(span.delivery_markers).lower():
                caption_style = CaptionStyle.SHOUT

            # Determine listener (first cast member not the speaker)
            listeners = [c for c in cast_names if c != speaker]
            listener = listeners[0] if listeners else None

            panels.append(
                StoryboardPanel(
                    panel_id=f"{beat_id}_p{p_idx:02d}",
                    scene_id=scene_id,
                    beat_id=beat_id,
                    panel_index=p_idx,
                    narrative_function=NarrativeFunction.PEAK if caption_style == CaptionStyle.SHOUT else NarrativeFunction.PROLONGATION,
                    shot_type=ShotType.CLOSE_UP if caption_style == CaptionStyle.SHOUT else ShotType.MEDIUM_PORTRAIT,
                    camera_angle=CameraAngle.LOW_ANGLE if caption_style == CaptionStyle.SHOUT else CameraAngle.EYE_LEVEL,
                    screen_direction=ScreenDirection.FACING_RIGHT if p_idx % 2 == 1 else ScreenDirection.FACING_LEFT,
                    subjects=[speaker] if not is_crowd else ["crowd"],
                    speaking_character=speaker if not is_crowd else None,
                    listening_character=listener,
                    is_crowd_shot=is_crowd,
                    dialogue_text=span.text,
                    caption_style=caption_style,
                    prose_disposition=ProseDisposition.KEEP_TEXT,
                    source_span_ids=[span.id],
                    segment_palette=palette_id,
                )
            )
            p_idx += 1

        elif span.span_type == SpanType.INNER_MONOLOGUE:
            speaker = span.speaker_self_id or (cast_names[0] if cast_names else "protagonist")
            panels.append(
                StoryboardPanel(
                    panel_id=f"{beat_id}_p{p_idx:02d}",
                    scene_id=scene_id,
                    beat_id=beat_id,
                    panel_index=p_idx,
                    narrative_function=NarrativeFunction.INITIAL,
                    shot_type=ShotType.CLOSE_UP,
                    camera_angle=CameraAngle.EYE_LEVEL,
                    screen_direction=ScreenDirection.FRONT,
                    subjects=[speaker],
                    speaking_character=speaker,
                    expression_visual="thoughtful, calculating gaze",
                    dialogue_text=span.text,
                    caption_style=CaptionStyle.THOUGHT,
                    prose_disposition=ProseDisposition.KEEP_TEXT,
                    source_span_ids=[span.id],
                    segment_palette=palette_id,
                )
            )
            p_idx += 1

        elif dec.disposition == ProseDisposition.SHOW:
            # Create a visual action panel
            panels.append(
                StoryboardPanel(
                    panel_id=f"{beat_id}_p{p_idx:02d}",
                    scene_id=scene_id,
                    beat_id=beat_id,
                    panel_index=p_idx,
                    narrative_function=NarrativeFunction.PROLONGATION,
                    shot_type=ShotType.MEDIUM_PORTRAIT,
                    camera_angle=CameraAngle.EYE_LEVEL,
                    screen_direction=ScreenDirection.FACING_RIGHT,
                    subjects=cast_names[:1],
                    action_visual=span.text[:120],
                    segment_palette=palette_id,
                    prose_disposition=ProseDisposition.SHOW,
                    source_span_ids=[span.id],
                )
            )
            p_idx += 1

    # If empty, add a default panel
    if not panels:
        panels.append(
            StoryboardPanel(
                panel_id=f"{beat_id}_p01",
                scene_id=scene_id,
                beat_id=beat_id,
                panel_index=1,
                narrative_function=NarrativeFunction.ESTABLISHING,
                shot_type=ShotType.WIDE,
                camera_angle=CameraAngle.EYE_LEVEL,
                screen_direction=ScreenDirection.FRONT,
                subjects=cast_names[:1],
                segment_palette=palette_id,
            )
        )

    # 3. Apply Camera & Spatial Continuity rules
    if len(cast_names) >= 2:
        panels = enforce_180_degree_axis(panels, cast_names[0], cast_names[1])

    panels = enforce_shot_variety(panels)

    seq = StoryboardSequence(
        scene_id=scene_id,
        beat_id=beat_id,
        segment_palette=palette_id,
        panels=panels,
    )

    # 4. Ensure listener reaction shots in dialogue
    if len(cast_names) >= 2 and dialogue_spans:
        seq = ensure_reaction_shots(seq, cast_names[0], cast_names[1])

    return seq
