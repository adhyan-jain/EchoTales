"""One reference image per character, for identity-consistent panels.

The gap this closes: nothing had ever generated a reference image for any
character, so IP-Adapter conditioning in `render/panels.py` had nothing to
condition *against* and every panel re-rolled a new face. A reference sheet
is the anchor that makes "the same character across panels" mean anything.

**Built from the appearance attributes, not from the prose.**
`resolve/appearance_extract.py` already turned scattered narration into
structured `Attribute` rows; this stage only has to phrase them. That split
matters: appearance is extracted once per novel and reused by every
downstream visual consumer, rather than each of them re-reading the text.

**Regenerated only when the appearance changes.** A digest of the character's
appearance attributes is stored alongside the image path, and generation is
skipped when the digest still matches -- re-generating every principal on
every run is not viable at a few seconds of GPU time each, and the source
data changes far more rarely than the pipeline is run.

**Prominence decides the budget**, as `plans.md` Phase 8 always specified:
principals get a full detailed sheet, recurring characters a shorter prompt,
and incidental characters no reference image at all (they fall back to the
archetype/faction defaults in `persona/attire.py`, which is what those tiers
exist for).

The engine is `render/panels.py`'s `PanelImageEngine` protocol, unchanged --
a reference sheet is one more text-to-image call, and giving it its own
parallel backend abstraction would mean two places to wire every new
checkpoint.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import (
    OBSERVER_READER,
    AssertedBy,
    Prominence,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute
from echotales.core.store import Store

log = logging.getLogger(__name__)

#: Attribute key holding the generated sheet's path.
REFERENCE_PATH_KEY = "reference_image_path"

#: Attribute key holding the digest of the appearance data that produced it.
#: Its whole job is cache invalidation -- see the module docstring.
REFERENCE_DIGEST_KEY = "reference_appearance_digest"

#: Appearance keys, in the order they read naturally in a prompt. Not the
#: same order as `appearance_extract.APPEARANCE_KEYS`, which is the storage
#: vocabulary; this is a sentence.
_PROMPT_ORDER = (
    "height_build",
    "hair_color",
    "hair_style",
    "eye_color",
    "skin_tone",
    "distinguishing_features",
    "typical_attire",
    "rank_insignia",
)

#: The style contract. Non-negotiable per the brief: the output must be
#: inked black-and-white manga, and a checkpoint that ignores this is the
#: wrong checkpoint (see `render/panels.py::MangaComfyEngine`).
REFERENCE_STYLE = (
    "manga style, black and white, ink lines, screentone shading, "
    "detailed face, neutral expression, front view, white background, "
    "character reference sheet"
)

REFERENCE_NEGATIVE = (
    "color, colored, photorealistic, 3d render, western comic, watermark, "
    "text, speech bubble, multiple views, extra limbs, deformed hands"
)


@dataclass(slots=True)
class ReferenceReport:
    novel_id: str
    generated: int = 0
    reused_cached: int = 0
    skipped_no_appearance: int = 0
    skipped_incidental: int = 0
    engine: str = "stub"
    paths: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.generated} reference sheets generated "
            f"({self.engine}), {self.reused_cached} reused from cache\n"
            f"  skipped: {self.skipped_incidental} incidental, "
            f"{self.skipped_no_appearance} with no appearance data"
        )


def appearance_of(store: Store, persona_id: str) -> dict[str, str]:
    """Standing appearance attributes for a persona, key -> value.

    Later attestations win on a repeated key: `appearance_extract` appends
    rather than overwrites (a character's condition changes; a scar is added
    later), so the most recent row is the current reading.
    """
    from echotales.pipeline.resolve.appearance_extract import APPEARANCE_KEYS

    out: dict[str, str] = {}
    for attr in store.get_attributes(TargetKind.PERSONA, persona_id):
        if attr.key in APPEARANCE_KEYS and attr.is_standing and attr.value:
            out[attr.key] = attr.value
    return out


def _demographics(store: Store, persona_id: str) -> tuple[str, str]:
    """`(gender, age_band)` from the trait profile `persona/build.py` wrote."""
    attrs = {
        a.key: a.value
        for a in store.get_attributes(TargetKind.PERSONA, persona_id)
        if a.is_standing
    }
    return attrs.get("gender", "unknown"), attrs.get("age_band", "adult")


def build_reference_prompt(
    label: str,
    appearance: dict[str, str],
    *,
    gender: str = "unknown",
    age_band: str = "adult",
    detailed: bool = True,
) -> str:
    """Phrase a character's stored appearance as a generation prompt.

    `detailed=False` (recurring characters) keeps only the strongest identity
    cues, which is the whole point of the prominence tiering: a walk-on does
    not need -- and has not got the evidence to support -- a full sheet.
    """
    parts: list[str] = []

    subject = age_band if age_band != "adult" else ""
    if gender in ("male", "female"):
        subject = f"{subject} {gender}".strip()
    parts.append(subject or "person")

    keys = _PROMPT_ORDER if detailed else ("hair_color", "hair_style", "typical_attire")
    for key in keys:
        value = appearance.get(key)
        if not value:
            continue
        if key == "hair_color":
            # Merged with hair_style below when both are present, so a
            # prompt reads "long black hair", not "black, long hair".
            continue
        if key == "hair_style":
            colour = appearance.get("hair_color", "")
            parts.append(f"{colour} {value} hair".strip())
        elif key == "eye_color":
            parts.append(f"{value} eyes")
        elif key == "typical_attire":
            parts.append(f"wearing {value}")
        else:
            parts.append(value)

    if appearance.get("hair_color") and not appearance.get("hair_style"):
        parts.append(f"{appearance['hair_color']} hair")

    parts.append(REFERENCE_STYLE)
    return ", ".join(p for p in parts if p)


def _digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _write_marker(
    store: Store, novel_id: str, persona_id: str, key: str, value: str, entity: object
) -> None:
    store.add_attribute(
        novel_id,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id=persona_id,
            key=key,
            value=value,
            interval=FuzzyInterval.open_ended(
                entity.first_attested_pos.chapter,  # type: ignore[attr-defined]
                last_evidence=entity.first_attested_pos.chapter,  # type: ignore[attr-defined]
            ),
            learned_at_pos=entity.first_attested_pos,  # type: ignore[attr-defined]
            observer_id=OBSERVER_READER,
            asserted_by=AssertedBy.INFERENCE,
            truth_status=TruthStatus.INFERRED,
        ),
    )


def generate_references(
    novel_id: str,
    store: Store,
    *,
    engine: object | None = None,
    out_dir: str | Path = "data/references",
    top: int | None = None,
    include_recurring: bool = True,
    width: int = 768,
    height: int = 1024,
    seed: int = 0,
) -> ReferenceReport:
    """Generate one cached reference sheet per prominent character.

    `top` limits the run to the N most-mentioned eligible characters, which
    is how a first pass gets reviewed before committing GPU time to a full
    cast.
    """
    from echotales.pipeline.render.panels import PanelImageRequest, get_engine
    from echotales.pipeline.resolve.appearance_extract import eligible_prominence

    engine = engine or get_engine("stub")
    out_dir = Path(out_dir) / novel_id
    report = ReferenceReport(novel_id=novel_id, engine=getattr(engine, "name", "?"))

    people = [e for e in store.all_selves(novel_id) if e.kind.is_person]
    ranked = sorted(
        people, key=lambda e: -store.mention_count_for(novel_id, e.id)
    )

    eligible: list[tuple[object, Prominence]] = []
    for entity in ranked:
        prominence = eligible_prominence(store, novel_id, entity)
        if prominence is Prominence.INCIDENTAL:
            report.skipped_incidental += 1
            continue
        if prominence is Prominence.RECURRING and not include_recurring:
            continue
        eligible.append((entity, prominence))

    if top is not None:
        eligible = eligible[:top]

    for entity, prominence in eligible:
        persona_id = f"{entity.id}:body1"  # type: ignore[attr-defined]
        appearance = appearance_of(store, persona_id)
        if not appearance:
            report.skipped_no_appearance += 1
            continue

        gender, age_band = _demographics(store, persona_id)
        prompt = build_reference_prompt(
            entity.canonical_label,  # type: ignore[attr-defined]
            appearance,
            gender=gender,
            age_band=age_band,
            detailed=prominence is Prominence.PRINCIPAL,
        )
        digest = _digest(prompt)

        stored = {
            a.key: a.value
            for a in store.get_attributes(TargetKind.PERSONA, persona_id)
            if a.is_standing
        }
        image_path = out_dir / f"{str(entity.id).replace(':', '_')}.png"  # type: ignore[attr-defined]

        if (
            stored.get(REFERENCE_DIGEST_KEY) == digest
            and image_path.exists()
        ):
            report.reused_cached += 1
            report.paths[str(entity.canonical_label)] = str(image_path)  # type: ignore[attr-defined]
            continue

        engine.generate(  # type: ignore[attr-defined]
            PanelImageRequest(
                prompt=prompt,
                out_path=image_path,
                negative_prompt=REFERENCE_NEGATIVE,
                width=width,
                height=height,
                seed=seed,
            )
        )

        if stored.get(REFERENCE_PATH_KEY) != str(image_path):
            _write_marker(
                store, novel_id, persona_id, REFERENCE_PATH_KEY, str(image_path), entity
            )
        _write_marker(store, novel_id, persona_id, REFERENCE_DIGEST_KEY, digest, entity)

        report.generated += 1
        report.paths[str(entity.canonical_label)] = str(image_path)  # type: ignore[attr-defined]

    store.conn.commit()
    return report


def reference_path_for(store: Store, persona_id: str) -> Path | None:
    """The stored reference sheet for a persona, if one exists on disk.

    Returns None rather than raising when the attribute points at a file
    that has since been deleted -- `render/panels.py` treats a missing
    reference as "fall back to prompt-only", which is a degradation, not a
    failure.
    """
    for attr in store.get_attributes(TargetKind.PERSONA, persona_id):
        if attr.key == REFERENCE_PATH_KEY and attr.is_standing and attr.value:
            path = Path(attr.value)
            if path.exists():
                return path
    return None
