"""Round 4 (2026-11-20): semi-realistic colour lead, light and mood graded from the text, adults drawn as adults."""

from __future__ import annotations

import re

from echotales.pipeline.persona.genre import GENRES, STYLE_LEADS, style_lead
from echotales.pipeline.render.compiler import (
    CharacterBrief,
    OutputMode,
    PanelBrief,
    compile_prompt,
    identity_sentence,
    model_profile,
)
from echotales.pipeline.render.lightgrade import light_grade

_CARTOON = re.compile(r"flat cel|2D cel-shaded anime|ghibli|chibi(?!,? not)|\bcute\b|kawaii", re.I)


def test_every_style_lead_is_semi_realistic_webtoon_colour_not_cartoon() -> None:
    assert set(STYLE_LEADS) >= set(GENRES) - {"generic"} or "generic" in STYLE_LEADS
    for lead in STYLE_LEADS.values():
        low = lead.lower()
        assert "semi-realistic" in low and "webtoon" in low and "adult proportions" in low
        assert not _CARTOON.search(lead), lead


def test_the_genre_only_adds_setting_flavour_to_one_shared_look() -> None:
    assert "xianxia" in style_lead("") and "xianxia" not in STYLE_LEADS["victorian_gothic"].lower()
    common = {re.sub(r"Set in [^.]*\.", "", v) for v in STYLE_LEADS.values()}
    assert len(common) == 1


def test_a_lamp_lit_night_room_is_low_key_and_a_cliff_in_mist_is_soft_overcast() -> None:
    night = light_grade("Set: a study lit by a classical wall lamp. Light: faint crimson red.", "")
    assert "low-key" in night.lower() and "deep shadows" in night
    assert "soft overcast" in light_grade("bare rock cliff edge", "mist, jagged peaks").lower()
    assert "golden" in light_grade("Light: late afternoon, hard sun", "").lower()


def test_the_stated_light_field_wins_over_a_stray_word_in_the_paragraph() -> None:
    assert "low-key" not in light_grade("Light: bright lights radiating with glory", "a dimly lit room").lower()


def test_no_light_words_means_no_grade_and_a_mood_adds_an_accent() -> None:
    assert light_grade("a bare hill", "") == ""
    assert "red" in light_grade("Light: moonless night", "", mood="ominous, tense")


def _brief(**kw: object) -> PanelBrief:
    lead = CharacterBrief(name="Klein", gender="male", age_band="youth", appearance={"hair_color": "black"})
    return PanelBrief(novel_id="", characters=[lead], mode=OutputMode.COLOUR, composition="Klein sits at a desk.", **kw)  # type: ignore[arg-type]


def test_the_grade_sits_right_after_the_style_lead_and_framing() -> None:
    out = compile_prompt(_brief(staging="Set: a study lit by a lamp. Light: night.", framing="A medium shot.", grade=light_grade("Light: night")), model_profile("z-image-turbo"))
    labels = [s.label for s in out.sections]
    assert labels[:3] == ["style", "framing", "grade"]


def test_a_youth_band_without_a_stated_age_is_a_young_adult_not_a_teenage_boy() -> None:
    s = identity_sentence(CharacterBrief(name="Klein", gender="male", age_band="youth"))
    assert "young man" in s and "teenage" not in s and "boy" not in s and "adult face" in s


def test_a_stated_adult_age_makes_an_adult_and_a_stated_teen_age_stays_young() -> None:
    adult = identity_sentence(CharacterBrief(name="Klein", gender="male", age_band="youth", age_years=22))
    teen = identity_sentence(CharacterBrief(name="Fang Yuan", gender="male", age_band="youth", age_years=15))
    assert "adult face" in adult and "youthful" not in adult
    assert "15-year-old boy" in teen and "youthful" in teen
