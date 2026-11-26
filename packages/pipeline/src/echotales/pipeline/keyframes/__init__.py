"""Keyframe generation engine and automated 4-Check QA gate."""

from echotales.pipeline.keyframes.engine import (
    KeyframeCandidate,
    ShotKeyframeResult,
    build_shot_prompt,
    generate_keyframe_candidates,
    generate_shot_keyframe,
)
from echotales.pipeline.keyframes.qa import (
    CheckResult,
    KeyframeQAGate,
    KeyframeQAReport,
)

__all__ = [
    "CheckResult",
    "KeyframeCandidate",
    "KeyframeQAGate",
    "KeyframeQAReport",
    "ShotKeyframeResult",
    "build_shot_prompt",
    "generate_keyframe_candidates",
    "generate_shot_keyframe",
]
