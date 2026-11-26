"""Pipeline builder for the Volume Bible (P1).

Assembles VolumeBible instances from graph entities, persona epochs, and scene structures.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from echotales.core.bible import (
    AppearanceEpoch,
    SegmentPalette,
    VolumeBible,
)
from echotales.pipeline.persona.split import bodies_of, standing_values

if TYPE_CHECKING:
    from echotales.core.store import Store

log = logging.getLogger(__name__)


STANDARD_PALETTES: dict[str, SegmentPalette] = {
    "battle_dusk": SegmentPalette(
        palette_id="battle_dusk",
        name="Battle at Dusk",
        mood="violent, desperate, high-tension confrontation",
        primary_color="crimson red",
        accent_color="magenta and charcoal",
        lighting_style="harsh directional rim light, heavy mist, dramatic backlighting",
        contrast_level="harsh",
        prompt_keywords=["red dusk light", "crimson shadows", "harsh contrast", "fog and smoke"],
    ),
    "poem_wash": SegmentPalette(
        palette_id="poem_wash",
        name="Poetic Contemplation",
        mood="calm, philosophical, unyielding defiance",
        primary_color="parchment cream",
        accent_color="golden amber",
        lighting_style="soft diffused moonlight, ink-wash aesthetic",
        contrast_level="medium",
        prompt_keywords=["pale cream wash", "moonlight", "ink wash style", "minimalist background"],
    ),
    "memory_montage": SegmentPalette(
        palette_id="memory_montage",
        name="Memory and Rebirth",
        mood="nostalgic, surreal, disorienting temporal transition",
        primary_color="deep oceanic blue",
        accent_color="golden light rings",
        lighting_style="subaquatic diffuse glow, ethereal rays of light",
        contrast_level="high",
        prompt_keywords=["deep blue wash", "golden light leaks", "vignette", "dreamlike atmospheric haze"],
    ),
    "ceremony_ancestral": SegmentPalette(
        palette_id="ceremony_ancestral",
        name="Ancestral Ceremony",
        mood="solemn, tense, traditional",
        primary_color="ochre and timber brown",
        accent_color="verdant bamboo green",
        lighting_style="warm lantern light, atmospheric dust motes",
        contrast_level="medium",
        prompt_keywords=["warm amber lantern light", "timber architecture", "ancient ceremonial stone"],
    ),
    "night_stealth": SegmentPalette(
        palette_id="night_stealth",
        name="Night and Shadows",
        mood="secretive, conspiratorial, cold",
        primary_color="midnight navy",
        accent_color="silver highlights",
        lighting_style="high-contrast silver moonlight, deep black shadows",
        contrast_level="harsh",
        prompt_keywords=["midnight blue", "deep black shadows", "silver rim lighting", "obscured framing"],
    ),
}


def build_volume_bible(store: Store, novel_id: str, volume_index: int = 1) -> VolumeBible:
    """Construct the director's bible for a novel volume from stored graph state."""
    bible = VolumeBible(novel_id=novel_id, volume_index=volume_index, palettes=dict(STANDARD_PALETTES))

    # 1. Appearance Epochs per self
    selves = store.all_selves(novel_id)
    for self_row in selves:
        self_id = self_row.id
        bodies = bodies_of(store, self_id)
        epochs: list[AppearanceEpoch] = []
        for p_idx, (persona_id, p_interval) in enumerate(bodies):
            # Fetch attributes for this persona
            attrs = standing_values(store, persona_id)
            hair = attrs.get("hair", "")
            eyes = attrs.get("eyes", "")
            face = attrs.get("face", "")
            build = attrs.get("build", "")
            attire = attrs.get("attire", "")
            age = attrs.get("age_band", "adult")

            epoch = AppearanceEpoch(
                self_id=self_id,
                persona_id=persona_id,
                epoch_label=f"epoch_{p_idx + 1}_{persona_id}",
                interval=p_interval,
                age_band=age,
                hair_desc=hair,
                eye_desc=eyes,
                facial_desc=face,
                base_build=build,
                default_attire=attire,
                features=attrs,
            )
            epochs.append(epoch)
        if epochs:
            bible.epochs_by_self[self_id] = epochs

    return bible
