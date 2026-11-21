"""A period setting keeps modern objects off the desk (P&P e2e 2026-11-22).

A modern computer keyboard sat on the desk in 7 panels of a Regency chapter: the "high over-the-shoulder view looking down"
sentence says "the desk and its objects below", the style lead said only "a period drama world", and Z-Image (no CFG, so no
negative prompt) filled "a desk and its objects" from its prior. The cue is per genre, from the genre profile, never per book.
"""

from __future__ import annotations

from echotales.pipeline.persona import genre
from echotales.pipeline.render import framing as fr
from echotales.pipeline.render.compiler import (
    CharacterBrief,
    OutputMode,
    PanelBrief,
    compile_prompt,
    model_profile,
)

PERIOD = ("generic", "victorian_gothic", "western_fantasy", "xianxia")
MODERN = ("contemporary", "modern_apocalypse", "science_fiction")


def test_every_period_genre_names_what_lies_on_its_desks_and_no_modern_genre_does() -> None:
    for name in PERIOD:
        assert genre.GENRES[name].desk_objects, name
    for name in MODERN:
        assert genre.GENRES[name].desk_objects == "", name


def test_the_period_style_lead_says_every_object_belongs_to_the_period() -> None:
    for name in ("generic", "victorian_gothic", "western_fantasy"):
        assert "true to" in genre.STYLE_LEADS[name], name
    assert "true to" not in genre.STYLE_LEADS["contemporary"]


def test_the_look_down_view_names_the_period_objects_instead_of_the_desks_objects() -> None:
    f = fr.Framing("medium", "high-angle", "down")
    plain = fr.framing_sentence(f, "Mr. Bennet", alone=True)
    period = fr.framing_sentence(f, "Mr. Bennet", alone=True, desk="a quill, an inkwell and sheets of paper")
    assert "its objects" in plain
    assert "quill" in period and "its objects" not in period


def test_the_compiled_prompt_of_a_period_novel_keeps_the_desk_cue() -> None:
    genre._PROJECT_GENRE["pnp-era"] = "generic"  # the registry of per-project genres is process-wide
    try:
        f = fr.Framing("medium", "high-angle", "down")
        sentence = fr.framing_sentence(f, "Mr. Bennet", alone=True, desk=genre.desk_objects("pnp-era"))
        brief = PanelBrief(
            novel_id="pnp-era", characters=[CharacterBrief(name="Mr. Bennet", gender="male", age_band="adult")],
            mode=OutputMode.COLOUR, framing=sentence, frame_focus="down", shot="medium",
        )
        out = compile_prompt(brief, model_profile("z-image-turbo")).positive
        assert "quill" in out and "keyboard" not in out.lower()
        assert "true to" in out
    finally:
        genre._PROJECT_GENRE.pop("pnp-era", None)


def test_a_modern_novel_gets_no_desk_cue() -> None:
    genre._PROJECT_GENRE["mod-era"] = "contemporary"
    try:
        assert genre.desk_objects("mod-era") == ""
    finally:
        genre._PROJECT_GENRE.pop("mod-era", None)
