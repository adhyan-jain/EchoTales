"""Character Turnaround & Expression Sheet Generator.

Generates 3-view turnaround model sheets (front, side, back) and 7-expression sets
(neutral, angry, shocked, crying, smirking, shouting, in_pain) using Qwen-Image-Edit
with Multiple Angles LoRA or offline worker stubs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from echotales.core.models import CharacterBibleEntry
from echotales.pipeline.persona.genre import ArtStyle, GenreProfile, art_style as resolve_art_style
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
def look_clauses(char: CharacterBibleEntry, defaults: dict[str, str] | None = None) -> list[str]:
    """Image-prompt tags for one character from its look attributes, in priority order (identity first).

    `defaults` fills hair, eye and skin when the book states none (the genre's own defaults, `GenreProfile.appearance`).
    Without them every separate image invents those traits, and Daly, whose hair the book never gives, came out blonde,
    green, grey and dark blue across one set of crops."""
    a = {k: str(v).strip().lower() for k, v in char.attributes.items() if v}
    for key, value in (defaults or {}).items():
        a.setdefault(key, value.lower())
    clauses: list[str] = []
    gender = a.get("gender", "")
    clauses.append({"male": "1boy", "female": "1girl"}.get(gender, "1person"))
    stage = a.get("age_stage", "")
    if not stage:
        # The persona stage's age band is only informative when it is not the default "adult": "elder" for an old man.
        stage = {"elder": "elderly", "child": "child", "teen": "teen", "youth": "young_adult", "young": "young_adult"}.get(
            a.get("age_band", ""), "")
    if not stage and a.get("age", "").isdigit():
        from echotales.pipeline.reader.facts_pass import stage_of_years

        stage = stage_of_years(int(a["age"]))
    tag = {"child": "child", "teen": "teenager", "young_adult": "young adult", "middle_aged": "middle-aged man" if gender == "male"
           else "middle-aged woman", "elderly": "elderly, old man" if gender == "male" else "elderly, old woman"}.get(stage)
    if tag:
        clauses.append(tag)
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
    outfit = (char.active_outfit or everyday_attire(a.get("typical_attire", ""))).strip()
    if outfit:
        clauses.append(outfit if outfit.startswith("wearing") else f"wearing {outfit}")
    return clauses


#: Plain-colour pools the genre default is varied within, so characters whose looks the book never states do not all
#: share one face. Keyed per character by a stable hash, flagged "assumed" like any genre default.
_HAIR_POOL = ("black", "dark brown", "brown", "auburn", "dark blond")
_EYE_POOL = ("dark brown", "grey", "green", "hazel", "blue")


def varied_defaults(char: CharacterBibleEntry, defaults: dict[str, str] | None) -> dict[str, str] | None:
    """Genre defaults with hair and eye colour picked per character. Klein and Dunn Smith, both stored with only an
    age band, came out as one identical face (owner, 2026-10-23); one shared default plus one shared seed was the cause."""
    if not defaults:
        return defaults
    h = int(hashlib.sha256(char.self_id.encode()).hexdigest(), 16)
    out = dict(defaults)
    if "hair_color" in out:
        out["hair_color"] = _HAIR_POOL[h % len(_HAIR_POOL)]
    if "eye_color" in out:
        out["eye_color"] = _EYE_POOL[(h // 7) % len(_EYE_POOL)]
    return out


def character_seed(char: CharacterBibleEntry, base: int = 42) -> int:
    """A stable seed per character, so two characters with similar prompts still get different faces."""
    return base + int(hashlib.sha256(char.self_id.encode()).hexdigest(), 16) % 100_000 * 100


def assumed_traits(char: CharacterBibleEntry, genre: GenreProfile | None) -> list[str]:
    """Look traits the book states nothing about, which `look_clauses` will fill from the genre default. Shown to the
    reviewer so an assumption is never mistaken for a fact from the text."""
    if genre is None:
        return []
    stated = {k for k, v in char.attributes.items() if v}
    return [f"{k}={v}" for k, v in (varied_defaults(char, genre.appearance) or {}).items() if k not in stated]


def everyday_attire(value: str) -> str:
    """A stated garment worth drawing on every image, or "" when it is not one.

    A uniform is worn on duty only (owner, 2026-10-23: Dunn Smith's Nighthawk uniform is for undercover-free missions; he
    otherwise wears ordinary clothes of the era), so it must not become the default look. Reader noise such as
    "smilingly shook his hand", stored as Klein's attire, is dropped the same way: a garment is a short noun phrase."""
    v = value.strip()
    words = v.lower().split()
    if not v or "uniform" in words or len(words) > 4 or any(w.endswith("ly") for w in words):
        return ""
    return v


def wardrobe_clause(char: CharacterBibleEntry, genre: GenreProfile | None) -> str:
    """The clothes people of this world wear, for this character's gender, but only when the book names none.

    When the book states a garment (Daly's "black robe", Klein's "linen shirt") that garment wins and the genre supplies
    just its era marker, the first phrase of the wardrobe ("victorian era"). Giving the full wardrobe turned Daly's
    robe into a corset dress."""
    if genre is None:
        return ""
    female = char.attributes.get("gender", "").strip().lower() == "female"
    full = genre.wardrobe_female if female and genre.wardrobe_female else genre.wardrobe
    stated = everyday_attire(char.attributes.get("typical_attire", ""))
    return full.split(",")[0].strip() if stated or char.active_outfit else full


def style_clauses(
    char: CharacterBibleEntry, genre: GenreProfile | None, visual_genre: str = "anime", art: ArtStyle | None = None
) -> list[str]:
    """Era clothing from the genre, then the art style. With no genre, the old one-word fallback."""
    if genre is None:
        return [f"{visual_genre} style"]
    style = art or resolve_art_style()
    return [c for c in (wardrobe_clause(char, genre), style.tags) if c]


def build_turnaround_prompt(
    char: CharacterBibleEntry, visual_genre: str = "anime", genre: GenreProfile | None = None, art: ArtStyle | None = None
) -> str:
    """Build standardized prompt for 3-view model turnaround.

    Priority runs identity -> era and style -> framing, because the image model reads about 77 tokens and the tail is cut:
    the first version of this prompt ended with "anime style" and no era at all, so LotM's Klein came out in a modern
    white shirt and black trousers (owner: "the genre is not taken into account at all")."""
    clauses = [
        "character design sheet, turnaround, front view, side view, back view",
        *look_clauses(char, varied_defaults(char, genre.appearance) if genre else None),
        *style_clauses(char, genre, visual_genre, art),
        "standing, full body, simple grey background",
    ]
    return fit_to_budget(clauses, limit=75)


def build_expression_prompt(
    char: CharacterBibleEntry, visual_genre: str = "anime", genre: GenreProfile | None = None, art: ArtStyle | None = None
) -> str:
    """Build standardized prompt for 7-expression character sheet."""
    expressions_str = ", ".join(e.value for e in STANDARD_EXPRESSIONS)
    clauses = [
        f"character expression sheet, 7 facial expressions: {expressions_str}",
        *look_clauses(char, varied_defaults(char, genre.appearance) if genre else None)[:6],
        *style_clauses(char, genre, visual_genre, art),
        "bust shot portraits grid, consistent face",
    ]
    return fit_to_budget(clauses, limit=75)


def generate_character_assets(
    char: CharacterBibleEntry,
    output_dir: Path | str,
    *,
    visual_genre: str = "anime",
    seed: int = 42,
    genre: GenreProfile | None = None,
    art_style_key: str | None = None,
    composite_sheets: bool = True,
) -> CharacterTurnaroundAsset:
    """Generate model turnaround and expression crops for a character.

    With a `genre`, every image carries that world's clothing and era (the art style is the same for all novels), the
    genre's negative list keeps out the wrong era, and traits the book leaves open (hair, eyes, skin) take the genre's
    defaults in every image so one character is not redrawn with a new hair colour each time."""
    style = resolve_art_style(art_style_key)
    negative = ", ".join(x for x in ((genre.negative_culture if genre is not None else ""), style.negative) if x)
    defaults = varied_defaults(char, genre.appearance) if genre is not None else None
    seed = character_seed(char, seed)
    out_dir = Path(output_dir) / char.self_id.replace(":", "_") / char.active_persona_id.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Turnaround Sheet. The composite can be switched off: with the "mature" preset its faces came out blank and its
    # title text garbled, but the default donghua recipe drew good full-body sheets (owner preferred v2).
    turnaround_prompt = build_turnaround_prompt(char, visual_genre, genre, style)
    req_turnaround = ImageWorkerRequest(
        prompt=turnaround_prompt,
        negative_prompt=negative,
        width=1920,
        height=1080,
        seed=seed,
    )
    res_turnaround = run_image_worker(req_turnaround) if composite_sheets else None

    sheet_path = out_dir / "turnaround_sheet.png"
    if res_turnaround is not None:
        sheet_path.write_bytes(res_turnaround.image_bytes)

    # In production with PIL/OpenCV, we slice the 3 views; for deterministic stubs,
    # generate dedicated cropped angles
    view_crops: dict[str, str] = {}
    for view in (TurnaroundView.FRONT, TurnaroundView.SIDE, TurnaroundView.BACK):
        view_req = ImageWorkerRequest(
            prompt=fit_to_budget([*look_clauses(char, defaults), f"{view.value} view", *style_clauses(char, genre, visual_genre, style), "full body, standing, simple grey background"], limit=75),
            negative_prompt=negative,
            width=1080,
            height=1920,
            seed=seed + len(view_crops),
        )
        view_res = run_image_worker(view_req)
        crop_path = out_dir / f"view_{view.value}.png"
        crop_path.write_bytes(view_res.image_bytes)
        view_crops[view.value] = str(crop_path)

    # 2. Expression Sheet
    expr_prompt = build_expression_prompt(char, visual_genre, genre, style)
    req_expr = ImageWorkerRequest(
        prompt=expr_prompt,
        negative_prompt=negative,
        width=1920,
        height=1080,
        seed=seed + 10,
    )
    expr_sheet_path = out_dir / "expression_sheet.png"
    if composite_sheets:
        expr_sheet_path.write_bytes(run_image_worker(req_expr).image_bytes)

    expression_crops: dict[str, str] = {}
    for expr in STANDARD_EXPRESSIONS:
        expr_req = ImageWorkerRequest(
            prompt=fit_to_budget([*look_clauses(char, defaults)[:6], f"{expr.value} expression, close-up portrait of one face", *style_clauses(char, genre, visual_genre, style), "simple background"], limit=75),
            negative_prompt=negative,
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
        sheet_image_path=str(sheet_path if composite_sheets else next(iter(view_crops.values()))),
        view_crops=view_crops,
        expression_sheet_path=str(expr_sheet_path) if composite_sheets else None,
        expression_crops=expression_crops,
        seed=seed,
    )


generate_character_turnaround = generate_character_assets
