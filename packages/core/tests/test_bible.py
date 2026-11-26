from echotales.core.bible import (
    AppearanceEpoch,
    RevealEvent,
    SegmentPalette,
    VolumeBible,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import DiscoursePosition


def test_volume_bible_epoch_lookup():
    fy_epoch1 = AppearanceEpoch(
        self_id="fang_yuan",
        persona_id="fang_yuan:old",
        epoch_label="cliff_500yo",
        interval=FuzzyInterval.point_known(1.0, 1.5),
        age_band="adult",
        hair_desc="long white hair",
        facial_desc="weathered cold face",
        default_attire="torn green robes",
        condition_notes="bleeding from wounds",
    )
    fy_epoch2 = AppearanceEpoch(
        self_id="fang_yuan",
        persona_id="fang_yuan:youth",
        epoch_label="reborn_15yo",
        interval=FuzzyInterval.point_known(1.5, 20.0),
        age_band="youth",
        hair_desc="short black hair",
        facial_desc="unblemished youthful face",
        default_attire="clean clan student robes",
    )

    bible = VolumeBible(
        novel_id="reverend-insanity",
        epochs_by_self={"fang_yuan": [fy_epoch1, fy_epoch2]},
    )

    # At chapter 1.0 (cliff)
    look_cliff = bible.get_look_at("fang_yuan", DiscoursePosition(chapter=1, offset=10))
    assert look_cliff is not None
    assert look_cliff.persona_id == "fang_yuan:old"
    assert "long white hair" in look_cliff.summary_prompt_clause()

    # At chapter 2.0 (academy)
    look_reborn = bible.get_look_at("fang_yuan", DiscoursePosition(chapter=2, offset=50))
    assert look_reborn is not None
    assert look_reborn.persona_id == "fang_yuan:youth"
    assert "short black hair" in look_reborn.summary_prompt_clause()


def test_volume_bible_reveals_leak_prevention():
    rev1 = RevealEvent(
        event_id="earth_past_life",
        story_time=0.1,
        revealed_at=DiscoursePosition(chapter=1, offset=500),
        involved_self_ids=["fang_yuan"],
        short_summary="Fang Yuan lived on Earth as an ordinary modern scholar",
        visual_motifs=["modern library", "business suit"],
        eligible_for_memory_montage=True,
    )
    rev2 = RevealEvent(
        event_id="mermaid_drowning",
        story_time=0.5,
        revealed_at=DiscoursePosition(chapter=3, offset=100),
        involved_self_ids=["fang_yuan"],
        short_summary="Fang Yuan drowned in the Eastern Sea",
        visual_motifs=["ocean abyss", "bubbles"],
        eligible_for_memory_montage=True,
    )

    bible = VolumeBible(
        novel_id="reverend-insanity",
        reveals=[rev1, rev2],
    )

    # Chapter 1 can access Earth memory montage after revealed_at
    montages_ch1 = bible.get_eligible_montages(DiscoursePosition(chapter=1, offset=600))
    assert len(montages_ch1) == 1
    assert montages_ch1[0].event_id == "earth_past_life"

    # Chapter 3 can access both
    montages_ch3 = bible.get_eligible_montages(DiscoursePosition(chapter=3, offset=200))
    assert len(montages_ch3) == 2


def test_volume_bible_palettes():
    palette = SegmentPalette(
        palette_id="battle_dusk",
        name="Battle at Dusk",
        mood="tense and violent",
        primary_color="crimson red",
        accent_color="magenta",
        lighting_style="harsh rim light, mist",
        contrast_level="harsh",
        prompt_keywords=["red dusk light", "dark jagged rocks", "fog"],
    )
    bible = VolumeBible(
        novel_id="reverend-insanity",
        palettes={"battle_dusk": palette},
    )

    retrieved = bible.get_palette("battle_dusk")
    assert retrieved is not None
    assert retrieved.primary_color == "crimson red"
    assert retrieved.contrast_level == "harsh"
