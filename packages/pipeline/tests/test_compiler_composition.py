"""Z-Image compiler: style lead, the director's composed paragraph, fixed identity sentences, setting; no boilerplate tail."""

from __future__ import annotations

from echotales.pipeline.persona.genre import style_lead
from echotales.pipeline.render.compiler import (
    CharacterBrief,
    OutputMode,
    PanelBrief,
    compile_prompt,
    identity_sentence,
    model_profile,
)

OLD = dict(name="Fang Yuan", gender="male", age_band="adult",
           appearance={"hair_color": "black", "eye_color": "dark brown"}, lead=True)
YOUNG = dict(OLD, age_band="youth", age_years=15)
COMPOSITION = (
    "A wide shot on a narrow mountain cliff at dusk. Fang Yuan stands alone in the centre in torn green robes, blood "
    "running down his temple, his face calm and contemptuous, while dozens of sect fighters ring him in a half circle."
)


def brief(**over) -> PanelBrief:
    fields = dict(novel_id="", characters=[CharacterBrief(**OLD)], mode=OutputMode.COLOUR, composition=COMPOSITION,
                  location="mountain cliff", lighting="dusk")
    fields.update(over)
    return PanelBrief(**fields)


def test_z_image_prompt_is_style_lead_then_composition_then_identity_then_setting_with_no_boilerplate_tail() -> None:
    out = compile_prompt(brief(), model_profile("z-image-turbo"))
    labels = [s.label for s in out.sections]
    assert labels[0] == "style" and labels[1] == "composition"
    assert labels.index("character:Fang Yuan") == 2
    assert out.positive.startswith("Chinese donghua style illustration, guofeng, detailed painterly xianxia art.")
    # The 2026-11-16 tail ("no panel borders, no speech bubbles ... hanfu with wide sleeves") is gone.
    assert "panel borders" not in out.positive and "speech bubbles" not in out.positive
    assert len(out.positive) < 900


def test_identity_wording_is_identical_on_every_panel_whatever_the_scene() -> None:
    a = compile_prompt(brief(), model_profile("z-image-turbo"))
    b = compile_prompt(
        brief(composition="A close-up of Fang Yuan laughing in the rain.", lighting="night"), model_profile("z-image-turbo"))
    pick = lambda c: next(s.text for s in c.sections if s.label == "character:Fang Yuan")  # noqa: E731
    assert pick(a) == pick(b) == identity_sentence(CharacterBrief(**OLD))


def test_a_youth_interval_says_his_age_plainly_and_keeps_the_same_hair_and_eyes() -> None:
    old, young = identity_sentence(CharacterBrief(**OLD)), identity_sentence(CharacterBrief(**YOUNG))
    assert "15-year-old boy" in young
    assert "black hair" in young and "dark brown eyes" in young and "black hair" in old
    assert "youthful" in young and "youthful" not in old


def test_the_style_lead_follows_the_genre_and_manga_mode_swaps_it_for_ink() -> None:
    assert "xianxia" in style_lead("")
    assert "xianxia" not in style_lead("some-regency-novel").lower()
    out = compile_prompt(brief(mode=OutputMode.MANGA), model_profile("z-image-turbo"))
    assert out.positive.startswith("Black and white manga")


def test_noobai_profile_ignores_the_composition() -> None:
    plain = compile_prompt(brief(composition=""), model_profile("noobai-xl-1.1"))
    composed = compile_prompt(brief(), model_profile("noobai-xl-1.1"))
    assert plain.positive == composed.positive and plain.negative == composed.negative
