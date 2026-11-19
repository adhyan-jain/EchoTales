"""The panel plan: one persisted record per generated image.

**Why this exists.** A normal real render runs two phases and deletes phase 1's
scratch directory; phase 2 then built its plan with no shot, layout, mood or
expression, and `manifest.jsonl` has one row per *block* with a prompt and
nothing else. So after a render nothing said what the director decided, which
scene an image belonged to, or which blocks it covers -- the inputs a shot
planner, a per-panel regenerate and a "every block reached a panel" audit all
need. This module is that record, written next to the images.

It carries only what no existing type does. The render plan's own fields
(environment, composition, characters) stay in `VisualRenderPlan` /
`render_artifact.jsonl`; a row points at them by `plan_digest` and
`state_digest`. The director's decision is embedded whole as `PanelDirection`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from echotales.pipeline.render.direction import PanelDirection
from pydantic import BaseModel, Field

#: Bump when a field changes meaning or is removed. Adding an optional field
#: does not need a bump; `load_panel_plan` refuses a version it does not know
#: rather than guess what an old or newer row means.
PLAN_SCHEMA_VERSION = 1
PANEL_PLAN_FILE = "panel_plan.jsonl"

SlotKind = Literal["establishing", "closeup", "scene", "crowd"]
CastSource = Literal["present", "carried", "none"]
Provenance = Literal["generated", "deduped", "cached"]


class PanelPlanSchemaError(ValueError):
    """A plan file this code cannot read."""


class PlanCastMember(BaseModel):
    self_id: str
    #: None when the self had no bound persona at this position.
    persona_id: str | None = None
    label: str = ""


class PanelPlan(BaseModel):
    schema_version: int = PLAN_SCHEMA_VERSION
    novel_id: str
    chapter: float
    panel_seq: int
    #: `{novel}:{chapter:g}:{panel_seq}`, the same id `VisualRenderPlan.beat_id` carries.
    panel_id: str

    scene_index: int
    segment_id: str = ""
    scene_state_id: str = ""
    slot_kind: SlotKind
    lead_block: int
    #: Every story block this image is shown over, ascending.
    block_indexes: list[int]

    cast: list[PlanCastMember] = Field(default_factory=list)
    #: "carried" is a pronoun-only beat reusing the previous beat's cast.
    cast_source: CastSource = "none"
    location: str = ""
    location_source: Literal["scene", "chapter", "carried"] = "scene"

    #: The director's full decision, or None with `direction_reason` saying why.
    direction: PanelDirection | None = None
    direction_source: Literal["director", "prompt_cache"] | None = None
    direction_reason: str | None = None

    prompt: str
    negative_prompt: str = ""
    #: CLIP tokens of the final prompt, and of the joined parts before the 77-token
    #: fit when the fit ran in this run or was recorded by phase 1. None when the
    #: prompt came from the mechanical assembler, whose fit is inside `persona/`.
    prompt_tokens: int | None = None
    prompt_tokens_before_fit: int | None = None
    #: Whole clauses `fit_to_budget` left out. None means "not recorded", [] means none dropped.
    dropped_clauses: list[str] | None = None
    #: `(label, text)` per compiler section (`render/compiler.py`), so a report shows which section carried the setting, the
    #: cast, the action. None when the legacy assembly built the prompt (`render.prompt_compiler` off).
    prompt_sections: list[tuple[str, str]] | None = None

    engine: str
    width: int
    height: int
    seed: int
    #: Relative to the directory this file sits in.
    image_path: str
    cache_key: str
    #: Joins this row to `render_artifact.jsonl`.
    plan_digest: str = ""
    state_digest: str = ""
    provenance: Provenance


def append_panel_plan(path: Path, row: PanelPlan, *, truncate: bool = False) -> None:
    """Append one row. A crash on the next panel keeps everything written so far."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if truncate else "a", encoding="utf-8") as fh:
        fh.write(row.model_dump_json() + "\n")


def load_panel_plan(version_dir: str | Path) -> list[PanelPlan]:
    """Every panel row of one version directory, in play order.

    Raises `FileNotFoundError` when the directory has no plan (a version rendered
    before plans existed: an empty list would read as "no panels") and
    `PanelPlanSchemaError` for a row of a schema version this code does not know.
    """
    path = Path(version_dir) / PANEL_PLAN_FILE
    if not path.exists():
        raise FileNotFoundError(f"no {PANEL_PLAN_FILE} in {version_dir}")
    rows: list[PanelPlan] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        version = raw.get("schema_version")
        if version != PLAN_SCHEMA_VERSION:
            raise PanelPlanSchemaError(
                f"{path} line {n}: panel plan schema_version {version!r}, "
                f"this code reads {PLAN_SCHEMA_VERSION}"
            )
        rows.append(PanelPlan.model_validate(raw))
    return rows


def dropped_clauses(parts: list[str], fitted: str) -> list[str]:
    """Which of `parts` the fit left out, read back from its output.

    `fit_to_budget` keeps whole parts, in order, joined by ", ", so replaying the
    parts against its result recovers the dropped ones without changing it
    (`persona/` is not ours to touch for this).
    """
    remaining = fitted
    dropped: list[str] = []
    for part in parts:
        if not part:
            continue
        if remaining == part:
            remaining = ""
        elif remaining.startswith(part + ", "):
            remaining = remaining[len(part) + 2 :]
        else:
            dropped.append(part)
    return dropped


# ---------------------------------------------------------------------------
# prompt cache: what phase 1 hands to phase 2
# ---------------------------------------------------------------------------

#: Entry format of `prompt_cache.json`. Version 1 was a bare prompt string.
PROMPT_CACHE_VERSION = 2


@dataclass(slots=True)
class CachedPrompt:
    prompt: str
    direction: PanelDirection | None = None
    #: Why there is no direction (phase 1 had no director, or it failed).
    direction_reason: str | None = None
    tokens_before_fit: int | None = None
    dropped: list[str] | None = None

    def to_json(self) -> dict:
        return {
            "v": PROMPT_CACHE_VERSION,
            "prompt": self.prompt,
            "direction": self.direction.model_dump() if self.direction is not None else None,
            "direction_reason": self.direction_reason,
            "tokens_before_fit": self.tokens_before_fit,
            "dropped": self.dropped,
        }

    @classmethod
    def from_json(cls, raw: object) -> CachedPrompt | None:
        if isinstance(raw, str):  # v1: prompt only, no direction was ever saved
            return cls(prompt=raw, direction_reason="old prompt cache (v1) holds no direction")
        if not isinstance(raw, dict) or raw.get("v") != PROMPT_CACHE_VERSION:
            return None
        direction = raw.get("direction")
        return cls(
            prompt=raw["prompt"],
            direction=PanelDirection.model_validate(direction) if direction else None,
            direction_reason=raw.get("direction_reason"),
            tokens_before_fit=raw.get("tokens_before_fit"),
            dropped=raw.get("dropped"),
        )


def load_prompt_cache(path: Path) -> dict[str, CachedPrompt]:
    """Both entry formats; an unreadable file or entry is a miss, never an error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, CachedPrompt] = {}
    for key, raw in data.items():
        try:
            entry = CachedPrompt.from_json(raw)
        except (KeyError, ValueError):
            entry = None
        if entry is not None:
            out[key] = entry
    return out


def dump_prompt_cache(path: Path, cache: dict[str, CachedPrompt]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({k: v.to_json() for k, v in cache.items()}, indent=2), encoding="utf-8"
    )
