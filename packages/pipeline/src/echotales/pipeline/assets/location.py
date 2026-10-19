"""Location Master Plate & Environment Generator.

Generates consistent environment plates, angle variants (establishing wide,
reverse angle, interior close-up), and day/night lighting pairs using
Qwen-Image or offline worker stubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from echotales.core.models import LocationBibleEntry
from echotales.pipeline.workers_contract import ImageWorkerRequest, run_image_worker


@dataclass(slots=True)
class LocationPlateAsset:
    """A master location environment plate with angle and lighting variants."""

    location_id: str
    canonical_name: str
    master_plate_path: str
    angle_variants: dict[str, str] = field(default_factory=dict)
    time_variants: dict[str, str] = field(default_factory=dict)
    ambience_sound: str | None = None
    seed: int = 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "canonical_name": self.canonical_name,
            "master_plate_path": self.master_plate_path,
            "angle_variants": dict(self.angle_variants),
            "time_variants": dict(self.time_variants),
            "ambience_sound": self.ambience_sound,
            "seed": self.seed,
        }


def build_location_prompt(
    loc: LocationBibleEntry,
    *,
    angle: str = "establishing",
    time_of_day: str = "day",
    visual_genre: str = "anime",
) -> str:
    """Build standardized prompt for an environment plate."""
    desc = loc.description or "detailed architectural interior"
    angle_phrase = {
        "establishing": "wide establishing shot, panoramic view",
        "reverse": "reverse angle shot, looking across the room",
        "detail": "interior medium shot, detailed environmental architecture",
    }.get(angle, "establishing wide shot")

    lighting_phrase = {
        "day": "clear daylight through windows, warm illumination",
        "night": "night scene, glowing oil/gas lamps, deep atmospheric shadows",
        "dusk": "golden hour dusk, orange and violet sky, moody lighting",
    }.get(time_of_day, "natural ambient light")

    from echotales.pipeline.persona.prompt import fit_to_budget
    clauses = [
        f"environment concept art, background plate, {loc.canonical_name}",
        desc,
        angle_phrase,
        lighting_phrase,
        f"clean background scenery, no people, matte painting, {visual_genre} style",
    ]
    return fit_to_budget(clauses, limit=75)


def generate_location_assets(
    loc: LocationBibleEntry,
    output_dir: Path | str,
    *,
    visual_genre: str = "anime",
    seed: int = 100,
) -> LocationPlateAsset:
    """Generate master plate and angle/lighting variants for a location."""
    out_dir = Path(output_dir) / loc.location_id.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Master Establishing Plate (Day)
    master_prompt = build_location_prompt(loc, angle="establishing", time_of_day="day", visual_genre=visual_genre)
    req_master = ImageWorkerRequest(
        prompt=master_prompt,
        width=1920,
        height=1080,
        seed=seed,
    )
    res_master = run_image_worker(req_master)
    master_path = out_dir / "master_plate.png"
    master_path.write_bytes(res_master.image_bytes)

    # 2. Angle Variants
    angle_variants: dict[str, str] = {}
    for angle in ("establishing", "reverse", "detail"):
        prompt = build_location_prompt(loc, angle=angle, time_of_day="day", visual_genre=visual_genre)
        req = ImageWorkerRequest(prompt=prompt, width=1920, height=1080, seed=seed + len(angle_variants) + 1)
        res = run_image_worker(req)
        path = out_dir / f"angle_{angle}.png"
        path.write_bytes(res.image_bytes)
        angle_variants[angle] = str(path)

    # 3. Time-of-Day Variants
    time_variants: dict[str, str] = {}
    for tod in ("day", "night", "dusk"):
        prompt = build_location_prompt(loc, angle="establishing", time_of_day=tod, visual_genre=visual_genre)
        req = ImageWorkerRequest(prompt=prompt, width=1920, height=1080, seed=seed + len(time_variants) + 10)
        res = run_image_worker(req)
        path = out_dir / f"time_{tod}.png"
        path.write_bytes(res.image_bytes)
        time_variants[tod] = str(path)

    ambience = loc.ambience_sound or f"ambient_{loc.canonical_name.lower().replace(' ', '_')}"

    return LocationPlateAsset(
        location_id=loc.location_id,
        canonical_name=loc.canonical_name,
        master_plate_path=str(master_path),
        angle_variants=angle_variants,
        time_variants=time_variants,
        ambience_sound=ambience,
        seed=seed,
    )
