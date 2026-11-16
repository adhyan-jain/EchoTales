"""The prompt compiler: the cliff scene reaches the prompt in both formats, and nothing is dropped or forced solo."""

from __future__ import annotations

import pytest
from echotales.pipeline.render.compiler import (
    AppearanceInText,
    CharacterBrief,
    CrowdBrief,
    OutputMode,
    PanelBrief,
    compile_prompt,
    derive_demeanour,
    genre_direction,
    model_profile,
)

FANG = dict(
    name="Fang Yuan", gender="male", age_band="adult",
    appearance={"hair_color": "black", "eye_color": "dark brown", "skin_tone": "pale", "scar": "scar on cheek",
                "build": "lean"},
    attire="green robes", condition="wounded, blood",
    big_five={"o": 0.5, "c": 0.7, "e": 0.3, "a": 0.4, "n": 0.8}, lead=True,
)


def cliff(mode: OutputMode = OutputMode.MANGA, **over) -> PanelBrief:
    art, wardrobe, manhua = genre_direction("")  # "" is the xianxia profile; RI is registered with its genre only at runtime
    fields = dict(
        novel_id="reverend-insanity", characters=[CharacterBrief(**FANG)],
        crowd=CrowdBrief("righteous sect martial artists", "many", "male", "surround him, weapons drawn"),
        location="mountain cliff edge", setting="cliff, mountain_background, mist", lighting="dusk",
        shot="wide", action="standing at the cliff edge", mood="tense", tension=0.8, mode=mode,
        art_direction=art, era_wardrobe=wardrobe, manhua=manhua, key_objects=["sword"],
    )
    fields.update(over)
    return PanelBrief(**fields)


@pytest.mark.parametrize("key", ["noobai-xl-1.1", "anima"])
def test_cliff_scene_carries_setting_crowd_demeanour_and_style(key: str) -> None:
    out = compile_prompt(cliff(), model_profile(key))
    text = out.positive
    assert "cliff" in text and "mountain" in text
    assert "surround him" in text and "martial artists" in text
    assert "cold" in text and "sad" not in text
    assert "monochrome" in text and "greyscale" in text
    assert "solo" not in text
    assert "crowd, multiple people" not in out.negative


def test_colour_mode_has_no_monochrome_and_manga_mode_rejects_colour() -> None:
    col = compile_prompt(cliff(OutputMode.COLOUR))
    assert "monochrome" not in col.positive and "colorful" not in col.negative
    assert "guofeng" in col.positive
    manga = compile_prompt(cliff(OutputMode.MANGA))
    assert "colorful" in manga.negative and "chinese manhua" in manga.positive


def test_single_quiet_scene_says_one_person_and_rejects_crowd() -> None:
    quiet = cliff(crowd=None, mood="quiet", tension=0.0, shot="medium", action="reading a letter")
    out = compile_prompt(quiet)
    assert "1boy" in out.positive and "solo" in out.positive
    assert "crowd" in out.negative


def test_two_characters_never_solo() -> None:
    other = CharacterBrief(name="Gu Yue", gender="female")
    out = compile_prompt(cliff(crowd=None, characters=[CharacterBrief(**FANG), other]))
    assert "solo" not in out.positive
    assert "girl" in out.positive


def test_sections_ordered_per_format_and_text_is_their_join() -> None:
    sdxl = compile_prompt(cliff(), model_profile("noobai-xl-1.1"))
    labels = [s.label for s in sdxl.sections]
    order = ["quality", "count", "character:Fang Yuan", "expression", "action", "crowd", "setting", "composition",
             "lighting", "objects", "mood", "style"]
    assert labels == order
    assert sdxl.positive == ", ".join(s.text for s in sdxl.sections)
    anima = compile_prompt(cliff(), model_profile("anima"))
    assert [s.label for s in anima.sections][:3] == ["quality", "count", "character:Fang Yuan"]
    assert anima.sections[-1].label == "prose"
    assert 2 <= anima.sections[-1].text.count(".") <= 4


def test_never_truncates_a_long_brief() -> None:
    long = cliff(setting=", ".join(f"detail_{i}" for i in range(120)))
    out = compile_prompt(long)
    assert all(f"detail {i}" in out.positive for i in range(120))


def test_appearance_switch() -> None:
    off = compile_prompt(cliff(), appearance=AppearanceInText.OFF)
    short = compile_prompt(cliff())
    full = compile_prompt(cliff(), appearance=AppearanceInText.FULL)
    assert off.appearance_written == {"Fang Yuan": False} and "black hair" not in off.positive
    assert short.appearance_written == {"Fang Yuan": True} and "black hair" in short.positive
    assert "pale" not in short.positive and "pale" in full.positive
    n_short = len(short.sections[2].text.split(", "))
    assert n_short <= 1 + 4 + 2  # name, up to 4 identity items, the beat's two condition tags


def test_demeanour_ruthless_in_tense_scene_is_cold_not_sad() -> None:
    d = derive_demeanour(CharacterBrief(**FANG), "tense", 0.8)
    assert "cold eyes" in d.tags and "contemptuous" in d.tags
    assert not {"sorrowful", "anxious", "wary"} & set(d.tags)
    assert any(f.startswith("big_five.a=") for f in d.fields_used) and "scene.mood=tense" in d.fields_used


def test_stated_expression_beats_traits_and_anxious_shows_only_when_undisciplined() -> None:
    stated = derive_demeanour(CharacterBrief(**{**FANG, "stated_expression": "calm_expression"}), "tense")
    assert stated.tags == ["calm expression"] and "stated_expression=calm_expression" in stated.fields_used
    nervous = CharacterBrief(name="X", big_five={"a": 0.6, "n": 0.8, "c": 0.3, "e": 0.5})
    assert "anxious" in derive_demeanour(nervous, "tense").tags


def test_unknown_model_raises() -> None:
    with pytest.raises(ValueError):
        model_profile("nope")
