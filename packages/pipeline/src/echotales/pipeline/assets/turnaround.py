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


#: Bible attributes that describe how a person *looks*. Everything else the bible holds for a character (`big_five`,
#: `archetype`, `reference_image_path`, appearance digests, voice ids) is bookkeeping, and the first version of this
#: builder wrote all of it into the image prompt as "key: value" ("reference_image_path: data/novels/..."), which an
#: image model can only misread. `current_condition` is left out on purpose: a wound or a state belongs to a scene, not to
#: a model sheet.
def look_clauses(char: CharacterBibleEntry) -> list[str]:
    """Image-prompt tags for one character from its look attributes, in priority order (identity first)."""
    a = {k: str(v).strip().lower() for k, v in char.attributes.items() if v}
    clauses: list[str] = []
    gender = a.get("gender", "")
    clauses.append({"male": "1boy", "female": "1girl"}.get(gender, "1person"))
    if a.get("age", "").isdigit() and int(a["age"]) < 20:
        clauses.append("teenager")
    if a.get("hair_color"):
        clauses.append(a["hair_color"] if "hair" in a["hair_color"] else f"{a['hair_color']} hair")
    if a.get("hair_style"):
        clauses.append(a["hair_style"])
    if a.get("eye_color"):
        clauses.append(a["eye_color"] if "eye" in a["eye_color"] else f"{a['eye_color']} eyes")
    if a.get("skin_tone"):
        clauses.append(a["skin_tone"] if "skin" in a["skin_tone"] else f"{a['skin_tone']} skin")
    if a.get("height_build"):
        clauses.append(a["height_build"])
    if a.get("distinguishing_features"):
        clauses.append(a["distinguishing_features"])
    outfit = (char.active_outfit or a.get("typical_attire") or "").strip()
    if outfit:
        clauses.append(outfit if outfit.startswith("wearing") else f"wearing {outfit}")
    return clauses


def build_turnaround_prompt(char: CharacterBibleEntry, visual_genre: str = "anime") -> str:
    """Build standardized prompt for 3-view model turnaround."""
    clauses = [
        "character design sheet, turnaround, front view, side view, back view, same character in all three angles",
        *look_clauses(char),
        f"standing, full body, neutral pose, simple grey background, {visual_genre} style",
    ]
    return fit_to_budget(clauses, limit=75)


def build_expression_prompt(char: CharacterBibleEntry, visual_genre: str = "anime") -> str:
    """Build standardized prompt for 7-expression character sheet."""
    expressions_str = ", ".join(e.value for e in STANDARD_EXPRESSIONS)
    clauses = [
        f"character expression sheet, 7 facial expressions: {expressions_str}",
        *look_clauses(char)[:6],
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
            prompt=", ".join([*look_clauses(char), f"{view.value} view", "full body, standing, simple grey background", f"{visual_genre} style"]),
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
            prompt=", ".join([*look_clauses(char)[:6], f"{expr.value} expression, portrait, face focus, simple background", f"{visual_genre} style"]),
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
