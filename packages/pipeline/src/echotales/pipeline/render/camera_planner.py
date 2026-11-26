"""Camera and spatial continuity planner (P2).

Enforces the 180-degree axis rule, shot scale variety, and listener reaction allocation.
"""

from __future__ import annotations

import logging

from echotales.pipeline.render.storyboard_schema import (
    CameraAngle,
    NarrativeFunction,
    ScreenDirection,
    ShotType,
    StoryboardPanel,
    StoryboardSequence,
)

log = logging.getLogger(__name__)


def enforce_180_degree_axis(panels: list[StoryboardPanel], lead_character: str, counter_character: str) -> list[StoryboardPanel]:
    """Ensure characters maintain consistent screen direction across alternating dialogue shots.

    If lead_character is on screen left (facing_right), counter_character must be on screen right (facing_left).
    """
    adjusted: list[StoryboardPanel] = []
    # Anchor: lead on the left looking right, counter on right looking left
    lead_direction = ScreenDirection.FACING_RIGHT
    counter_direction = ScreenDirection.FACING_LEFT

    for panel in panels:
        p = panel.model_copy()
        if p.speaking_character == lead_character and not p.is_crowd_shot:
            p.screen_direction = lead_direction
        elif p.speaking_character == counter_character and not p.is_crowd_shot:
            p.screen_direction = counter_direction
        adjusted.append(p)

    return adjusted


def enforce_shot_variety(panels: list[StoryboardPanel]) -> list[StoryboardPanel]:
    """Prevent consecutive panels from using the identical shot scale on the same subject.

    If panel i and panel i+1 both feature the same single subject with the same ShotType,
    adjust the second panel to provide an angle or scale shift (e.g. close_up -> medium_portrait or insert).
    """
    if len(panels) < 2:
        return panels

    adjusted: list[StoryboardPanel] = [panels[0].model_copy()]

    for i in range(1, len(panels)):
        prev = adjusted[-1]
        curr = panels[i].model_copy()

        # Check if consecutive panels have the same primary subject and shot type
        same_subject = (
            prev.speaking_character and curr.speaking_character
            and prev.speaking_character == curr.speaking_character
            and not prev.is_crowd_shot and not curr.is_crowd_shot
        )
        if same_subject and prev.shot_type == curr.shot_type:
            # Alternating shift: if close_up, shift to medium_portrait; if wide, shift to medium
            if curr.shot_type == ShotType.CLOSE_UP:
                curr.shot_type = ShotType.MEDIUM_PORTRAIT
            elif curr.shot_type == ShotType.MEDIUM_PORTRAIT:
                curr.shot_type = ShotType.CLOSE_UP
            elif curr.shot_type == ShotType.WIDE:
                curr.shot_type = ShotType.EXTREME_WIDE

        adjusted.append(curr)

    return adjusted


def ensure_reaction_shots(sequence: StoryboardSequence, speaker: str, listener: str) -> StoryboardSequence:
    """Ensure high-tension dialogue beats allocate at least one listener reaction shot."""
    panels = list(sequence.panels)
    has_reaction = any(p.narrative_function == NarrativeFunction.REACTION for p in panels)

    if not has_reaction and len(panels) >= 2 and speaker and listener:
        # Inject or convert the second panel to a listener reaction shot
        reaction_panel = StoryboardPanel(
            panel_id=f"{sequence.beat_id}_reaction",
            scene_id=sequence.scene_id,
            beat_id=sequence.beat_id,
            panel_index=len(panels) + 1,
            narrative_function=NarrativeFunction.REACTION,
            shot_type=ShotType.CLOSE_UP,
            camera_angle=CameraAngle.EYE_LEVEL,
            screen_direction=ScreenDirection.FACING_LEFT,
            subjects=[listener],
            speaking_character=None,
            listening_character=listener,
            action_visual=f"{listener} reacting to words",
            expression_visual="stunned, guarded silence",
            segment_palette=sequence.segment_palette,
            invented=True,
            invention_rationale="Listener reaction shot allocated for dramatic dialogue pacing.",
        )
        panels.insert(1, reaction_panel)
        # Re-index panels
        for idx, p in enumerate(panels, start=1):
            p.panel_index = idx

    return StoryboardSequence(
        scene_id=sequence.scene_id,
        beat_id=sequence.beat_id,
        segment_palette=sequence.segment_palette,
        panels=panels,
    )
