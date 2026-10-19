"""Keyframe generation engine and automated 4-Check QA gate."""

from echotales.pipeline.keyframes.qa import (
    CheckResult,
    KeyframeQAGate,
    KeyframeQAReport,
)
from echotales.pipeline.keyframes.engine import (
    KeyframeCandidate,
    ShotKeyframeResult,
    build_shot_prompt,
    generate_keyframe_candidates,
    generate_shot_keyframe,
)

__all__ = [
    "CheckResult",
    "KeyframeQAGate",
    "KeyframeQAReport",
    "KeyframeCandidate",
    "ShotKeyframeResult",
    "build_shot_prompt",
    "generate_keyframe_candidates",
    "generate_shot_keyframe",
]
