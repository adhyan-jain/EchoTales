"""Pre-Render Cost Meter for RunPod GPU and token resource estimation.

Solves defect 24: Provides full cost and runtime visibility before launching renders.
Calculates itemized cost breakdowns for Path 1 (2.5D Reels) and Path 2 (Wan 2.2 Video).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from echotales.pipeline.screenplay.schema import (
    RenderTier,
    ScreenplayEpisode,
)

# Benchmark pricing constants (RunPod Serverless Flex & Frontier API rates)
RUNPOD_GPU_PER_SEC_USD = 0.44 / 3600.0  # $0.44/hr for RTX 4090 flex worker
DEEPSEEK_V4_INPUT_PER_M_TOKENS = 0.14
DEEPSEEK_V4_OUTPUT_PER_M_TOKENS = 0.28
QWEN_IMAGE_PER_RENDER_USD = 0.003  # ~25 steps on flex worker
QWEN_TTS_PER_1K_CHARS_USD = 0.0015
WAN_VIDEO_PER_SEC_USD = 0.012  # ~1.2 cents per second of generated video


@dataclass(slots=True)
class CostEstimate:
    """Itemized pre-render cost estimate."""

    novel_id: str
    episode_id: str
    episode_duration_s: float
    num_shots: int
    num_dialogue_lines: int
    tier: str  # "path1" | "path2"
    llm_cost_usd: float
    image_cost_usd: float
    tts_cost_usd: float
    video_cost_usd: float
    total_cost_usd: float
    cost_per_finished_minute_usd: float
    estimated_render_time_s: float
    breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "episode_id": self.episode_id,
            "episode_duration_s": round(self.episode_duration_s, 2),
            "num_shots": self.num_shots,
            "num_dialogue_lines": self.num_dialogue_lines,
            "tier": self.tier,
            "llm_cost_usd": round(self.llm_cost_usd, 4),
            "image_cost_usd": round(self.image_cost_usd, 4),
            "tts_cost_usd": round(self.tts_cost_usd, 4),
            "video_cost_usd": round(self.video_cost_usd, 4),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cost_per_finished_minute_usd": round(self.cost_per_finished_minute_usd, 4),
            "estimated_render_time_s": round(self.estimated_render_time_s, 1),
            "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()},
        }


def estimate_episode_cost(
    episode: ScreenplayEpisode,
    novel_id: str = "showcase",
    *,
    tier: str = "path1",
    candidates_per_shot: int = 4,
    qa_reroll_factor: float = 1.25,
) -> CostEstimate:
    """Calculate pre-render resource and GPU cost estimate for an episode screenplay."""
    shots = episode.all_shots if isinstance(episode.all_shots, list) else episode.all_shots()
    num_shots = len(shots)
    total_dur_s = sum(s.duration_s for s in shots)
    total_mins = max(0.1, total_dur_s / 60.0)

    # 1. LLM Screenplay & Delta Extraction Cost
    # Approx 6,000 input tokens + 2,500 output tokens per episode
    llm_cost = (
        (6000 / 1_000_000.0) * DEEPSEEK_V4_INPUT_PER_M_TOKENS
        + (2500 / 1_000_000.0) * DEEPSEEK_V4_OUTPUT_PER_M_TOKENS
    )

    # 2. Keyframe Generation Cost (4 candidates per shot + 25% QA re-rolls)
    total_image_renders = int(num_shots * candidates_per_shot * qa_reroll_factor)
    image_cost = total_image_renders * QWEN_IMAGE_PER_RENDER_USD

    # 3. Speech Synthesis Cost (Dialogue + Narration)
    dialogue_lines = [d for s in shots for d in s.dialogue]
    total_chars = sum(len(d.text) for d in dialogue_lines)
    tts_cost = (total_chars / 1000.0) * QWEN_TTS_PER_1K_CHARS_USD

    # 4. Video / Compositor Cost
    if tier.lower() == "path2":
        # Video on Wan 2.2: assume ~50% video screen time, 50% 2.5D fallback
        video_dur_s = total_dur_s * 0.5
        video_cost = video_dur_s * WAN_VIDEO_PER_SEC_USD
        render_time_s = total_dur_s * 4.0  # ~4x realtime on flex GPU
    else:  # Path 1 2.5D
        video_cost = 0.0  # purely 2.5D ffmpeg compositor
        render_time_s = total_dur_s * 0.8  # faster than realtime

    total_cost = llm_cost + image_cost + tts_cost + video_cost
    cost_per_min = total_cost / total_mins

    breakdown = {
        "llm_adaptation": llm_cost,
        "keyframe_diffusion": image_cost,
        "voice_synthesis": tts_cost,
        "video_generation": video_cost,
    }

    return CostEstimate(
        novel_id=novel_id,
        episode_id=episode.episode_id,
        episode_duration_s=total_dur_s,
        num_shots=num_shots,
        num_dialogue_lines=len(dialogue_lines),
        tier=tier,
        llm_cost_usd=llm_cost,
        image_cost_usd=image_cost,
        tts_cost_usd=tts_cost,
        video_cost_usd=video_cost,
        total_cost_usd=total_cost,
        cost_per_finished_minute_usd=cost_per_min,
        estimated_render_time_s=render_time_s,
        breakdown=breakdown,
    )
