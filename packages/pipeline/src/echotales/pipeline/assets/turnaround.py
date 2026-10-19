"""Character Turnaround & Expression Sheet Generator.

Generates 3-view turnaround model sheets (front, side, back) and 7-expression sets
(neutral, angry, shocked, crying, smirking, shouting, in_pain) using Qwen-Image-Edit
with Multiple Angles LoRA or offline worker stubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from echotales.core.models import CharacterBibleEntry
from echotales.pipeline.persona.prompt import fit_to_budget
from echotales.pipeline.workers_contract import ImageWorkerRequest, run_image_worker


class TurnaroundView(StrEnum):
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class ExpressionType(StrEnum):
    NEUTRAL = "neutral"
    ANGRY = "angry"
    SHOCKED = "shocked"
    CRYING = "crying"
    SMIRKING = "smirking"
    SHOUTING = "shouting"
    IN_PAIN = "in_pain"


STANDARD_EXPRESSIONS: list[ExpressionType] = [
    ExpressionType.NEUTRAL,
    ExpressionType.ANGRY,
    ExpressionType.SHOCKED,
    ExpressionType.CRYING,
    ExpressionType.SMIRKING,
    ExpressionType.SHOUTING,
    ExpressionType.IN_PAIN,
]


@dataclass(slots=True)
class CharacterTurnaroundAsset:
    """A generated model turnaround sheet and sliced view crops."""

    self_id: str
    persona_id: str
    sheet_image_path: str
    view_crops: dict[str, str] = field(default_factory=dict)
    expression_sheet_path: str | None = None
    expression_crops: dict[str, str] = field(default_factory=dict)
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return {
            "self_id": self.self_id,
            "persona_id": self.persona_id,
            "sheet_image_path": self.sheet_image_path,
            "view_crops": dict(self.view_crops),
            "expression_sheet_path": self.expression_sheet_path,
            "expression_crops": dict(self.expression_crops),
            "seed": self.seed,
        }


def build_turnaround_prompt(char: CharacterBibleEntry, visual_genre: str = "anime") -> str:
    """Build standardized prompt for 3-view model turnaround."""
    attr_clauses = [f"{k}: {v}" for k, v in char.attributes.items() if k not in ("voice_id", "voice_profile")]
    attr_desc = ", ".join(attr_clauses) if attr_clauses else "detailed character design"
    outfit = f"wearing {char.active_outfit}" if char.active_outfit else ""

    clauses = [
        "character design sheet, 3-view turnaround, front view, side profile view, back view",
        f"same character in all three angles, {char.canonical_label}",
        attr_desc,
        outfit,
        f"neutral pose, standing, clean lines, neutral grey background, master character sheet, {visual_genre} style",
    ]
    return fit_to_budget(clauses, limit=75)


def build_expression_prompt(char: CharacterBibleEntry, visual_genre: str = "anime") -> str:
    """Build standardized prompt for 7-expression character sheet."""
    expressions_str = ", ".join(e.value for e in STANDARD_EXPRESSIONS)
    clauses = [
        f"character expression sheet, 7 facial expressions: {expressions_str}",
        f"same character, {char.canonical_label}",
        "bust shot portraits grid, consistent face, high quality",
        f"neutral background, {visual_genre} style",
    ]
    return fit_to_budget(clauses, limit=75)


def generate_character_assets(
    char: CharacterBibleEntry,
    output_dir: Path | str,
    *,
    visual_genre: str = "anime",
    seed: int = 42,
) -> CharacterTurnaroundAsset:
    """Generate model turnaround and expression crops for a character."""
    out_dir = Path(output_dir) / char.self_id.replace(":", "_") / char.active_persona_id.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Turnaround Sheet
    turnaround_prompt = build_turnaround_prompt(char, visual_genre)
    req_turnaround = ImageWorkerRequest(
        prompt=turnaround_prompt,
        width=1920,
        height=1080,
        seed=seed,
    )
    res_turnaround = run_image_worker(req_turnaround)

    sheet_path = out_dir / "turnaround_sheet.png"
    sheet_path.write_bytes(res_turnaround.image_bytes)

    # In production with PIL/OpenCV, we slice the 3 views; for deterministic stubs,
    # generate dedicated cropped angles
    view_crops: dict[str, str] = {}
    for view in (TurnaroundView.FRONT, TurnaroundView.SIDE, TurnaroundView.BACK):
        view_req = ImageWorkerRequest(
            prompt=f"{char.canonical_label}, {view.value} view crop, {visual_genre}",
            width=1080,
            height=1920,
            seed=seed + len(view_crops),
        )
        view_res = run_image_worker(view_req)
        crop_path = out_dir / f"view_{view.value}.png"
        crop_path.write_bytes(view_res.image_bytes)
        view_crops[view.value] = str(crop_path)

    # 2. Expression Sheet
    expr_prompt = build_expression_prompt(char, visual_genre)
    req_expr = ImageWorkerRequest(
        prompt=expr_prompt,
        width=1920,
        height=1080,
        seed=seed + 10,
    )
    res_expr = run_image_worker(req_expr)
    expr_sheet_path = out_dir / "expression_sheet.png"
    expr_sheet_path.write_bytes(res_expr.image_bytes)

    expression_crops: dict[str, str] = {}
    for expr in STANDARD_EXPRESSIONS:
        expr_req = ImageWorkerRequest(
            prompt=f"{char.canonical_label}, facial expression {expr.value}, portrait crop, {visual_genre}",
            width=1024,
            height=1024,
            seed=seed + 20 + len(expression_crops),
        )
        expr_res = run_image_worker(expr_req)
        expr_crop_path = out_dir / f"expr_{expr.value}.png"
        expr_crop_path.write_bytes(expr_res.image_bytes)
        expression_crops[expr.value] = str(expr_crop_path)

    return CharacterTurnaroundAsset(
        self_id=char.self_id,
        persona_id=char.active_persona_id,
        sheet_image_path=str(sheet_path),
        view_crops=view_crops,
        expression_sheet_path=str(expr_sheet_path),
        expression_crops=expression_crops,
        seed=seed,
    )


generate_character_turnaround = generate_character_assets
