"""The prompt compiler: the cliff scene reaches the prompt in both formats, and nothing is dropped or forced solo."""

from __future__ import annotations

import pytest
from echotales.pipeline.render.compiler import (
    AppearanceInText,
    CharacterBrief,
    CrowdBrief,
    OutputMode,
    PanelBrief,
    brief_from_direction,
    compile_prompt,
    derive_demeanour,
    genre_direction,
    identity_sentence,
    model_profile,
)

FANG = dict(
    name="Fang Yuan", gender="male", age_band="adult",
    appearance={"hair_color": "black", "eye_color": "dark brown", "skin_tone": "pale", "scar": "scar on cheek",
                "build": "lean"},
    attire="green robes", condition="wounded, blood",
    big_five={"o": 0.5, "c": 0.7, "e": 0.3, "a": 0.4, "n": 0.8}, lead=True,
)


#: These tests are about the SDXL tag profile; the compiler default is the configured model (Z-Image), no longer this one.
SDXL = model_profile("noobai-xl-1.1")


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
    col = compile_prompt(cliff(OutputMode.COLOUR), SDXL)
    assert "monochrome" not in col.positive and "colorful" not in col.negative
    assert "guofeng" in col.positive
    manga = compile_prompt(cliff(OutputMode.MANGA), SDXL)
    assert "colorful" in manga.negative and "chinese manhua" in manga.positive


def test_single_quiet_scene_says_one_person_and_rejects_crowd() -> None:
    quiet = cliff(crowd=None, mood="quiet", tension=0.0, shot="medium", action="reading a letter")
    out = compile_prompt(quiet, SDXL)
    assert "1boy" in out.positive and "solo" in out.positive
    assert "crowd" in out.negative


def test_two_characters_never_solo() -> None:
    other = CharacterBrief(name="Gu Yue", gender="female")
    out = compile_prompt(cliff(crowd=None, characters=[CharacterBrief(**FANG), other]), SDXL)
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
    out = compile_prompt(long, SDXL)
    assert all(f"detail {i}" in out.positive for i in range(120))


def test_appearance_switch() -> None:
    off = compile_prompt(cliff(), SDXL, appearance=AppearanceInText.OFF)
    short = compile_prompt(cliff(), SDXL)
    full = compile_prompt(cliff(), SDXL, appearance=AppearanceInText.FULL)
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


def test_scenery_only_brief_excludes_humans() -> None:
    brief = cliff(characters=[], crowd=None, setting="bamboo forest path, morning mist")
    compiled_z = compile_prompt(brief, model_profile("z-image-turbo"))
    comp_text = dict(compiled_z.section_texts())["composition"]
    assert "pure scenery" in comp_text and "empty of people" in comp_text

    compiled_sdxl = compile_prompt(brief, model_profile("noobai-xl-1.1"))
    count_text = dict(compiled_sdxl.section_texts())["count"]
    assert "no humans" in count_text or "no_humans" in count_text
    assert "person, people, human" in compiled_sdxl.negative


def test_indoor_setting_includes_indoor_cues_and_negates_outdoors() -> None:
    brief = cliff(setting="bamboo house room, wooden study desk, warm candlelight")
    compiled_z = compile_prompt(brief, model_profile("z-image-turbo"))
    setting_text = dict(compiled_z.section_texts())["setting"]
    assert "indoor interior" in setting_text and "enclosed space with walls and ceiling" in setting_text

    compiled_sdxl = compile_prompt(brief, model_profile("noobai-xl-1.1"))
    assert "outdoor" in compiled_sdxl.negative and "mountains" in compiled_sdxl.negative


def test_all_characters_get_expression_position_and_pose() -> None:
    c1 = CharacterBrief(**FANG, position="left", pose="standing", stated_expression="cold_expression")
    c2 = CharacterBrief(
        name="Bai Ning Bing", gender="male", age_band="adult",
        appearance={"hair_color": "silver", "eye_color": "blue"},
        attire="white robes", position="right", pose="fighting stance", stated_expression="sneering",
    )
    brief = cliff(characters=[c1, c2], crowd=None)
    compiled_z = compile_prompt(brief, model_profile("z-image-turbo"))
    others_text = dict(compiled_z.section_texts())["others"]
    assert "Bai Ning Bing" in others_text
    assert "positioned right" in others_text
    assert "fighting stance" in others_text
    assert "face is sneering" in others_text


def test_child_and_teenager_nouns() -> None:
    child_boy = CharacterBrief(name="Xiao Lin", gender="male", age_band="child")
    child_girl = CharacterBrief(name="Xiao Mei", gender="female", age_band="child")
    teen_boy = CharacterBrief(name="Lin Feng", gender="male", age_band="teenager")
    assert "young boy" in identity_sentence(child_boy)
    assert "young girl" in identity_sentence(child_girl)
    assert "teenage boy" in identity_sentence(teen_boy)


def test_creature_non_human_entity() -> None:
    creature = CharacterBrief(name="Golden Centipede", gender="creature", is_creature=True, condition="glowing armor")
    ident = identity_sentence(creature)
    assert "monstrous golden centipede" in ident.lower()
    assert "man" not in ident and "woman" not in ident


def test_twins_same_face_as() -> None:
    twin = CharacterBrief(name="Fang Zheng", gender="male", same_face_as="Fang Yuan", attire="white crane robes")
    ident = identity_sentence(twin)
    assert "identical facial features and face as Fang Yuan (twin)" in ident
    assert "wears white crane robes" in ident


def test_stable_assumed_appearance_marker() -> None:
    # Character with no recorded appearance in the graph gets a deterministic, stable assumed marker
    char_a = CharacterBrief(name="Gu Yue Mo Yan", gender="male")
    char_b = CharacterBrief(name="Gu Yue Chi Lian", gender="male")
    ident_a1 = identity_sentence(char_a)
    ident_a2 = identity_sentence(char_a)
    ident_b = identity_sentence(char_b)
    # Stable across calls
    assert ident_a1 == ident_a2
    assert "hair" in ident_a1
    # Different names get different markers
    assert ident_a1 != ident_b


def test_an_undescribed_character_gets_a_genre_neutral_marker_and_the_dark_style_has_no_typo() -> None:
    # The stand-in hair marker for a character with no appearance facts was drawn from a list that included "wooden
    # hairpin" and "cloth ribbon", which put cultivation-era hair on a Regency heroine.
    markers = {
        identity_sentence(CharacterBrief(name=f"Person {i}", gender="female")).split(" with ", 1)[1] for i in range(60)
    }
    assert len(markers) > 3
    assert not any(w in m for m in markers for w in ("hairpin", "wooden", "cloth"))
    dark = compile_prompt(cliff(OutputMode.MANGA, lighting="night", mood="dark"), model_profile("z-image-turbo"))
    assert "deep deep" not in dark.positive


def test_non_manhua_genre_styles_on_zimage() -> None:
    vic_brief = cliff(manhua=False, art_direction="victorian gothic", era_wardrobe="frock coats and top hats")
    compiled = compile_prompt(vic_brief, model_profile("z-image-turbo"))
    style_text = dict(compiled.section_texts())["style"]
    assert "Victorian gothic" in style_text
    assert "frock coats" in style_text

    mod_brief = cliff(manhua=False, art_direction="modern apocalypse", era_wardrobe="jackets and tactical gear")
    compiled_mod = compile_prompt(mod_brief, model_profile("z-image-turbo"))
    assert "modern cinematic" in dict(compiled_mod.section_texts())["style"]


def _two_person_store(tmp_path):
    from echotales.core.enums import TargetKind
    from echotales.core.models import DiscoursePosition, Self
    from echotales.core.store import Store

    store = Store(str(tmp_path / "t.db"))
    store.add_novel("n", "N", "x.epub", "generic")
    for sid, label in (("s1", "Fang Yuan"), ("s2", "Bai Ning Bing")):
        store.add_self(Self(id=sid, novel_id="n", canonical_label=label,
                            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.conn.commit()
    return store


def test_brief_from_direction_matches_director_characters_to_the_cast_by_name_not_index(tmp_path) -> None:
    # A director listing Bai first while self_ids run [Fang, Bai] swapped their bodies and poses when matched by index.
    from echotales.pipeline.render.direction import CharacterDirection, PanelDirection

    d = PanelDirection(characters=[
        CharacterDirection(name="Bai Ning Bing", position="right", pose="sitting"),
        CharacterDirection(name="Fang Yuan", position="left", pose="kneeling"),
    ])
    brief = brief_from_direction(_two_person_store(tmp_path), "n", ["s1", "s2"], 1.0, d)
    assert [(c.name, c.pose, c.position) for c in brief.characters] == [
        ("Bai Ning Bing", "sitting", "right"), ("Fang Yuan", "kneeling", "left"),
    ]
    assert brief.characters[0].lead and not brief.characters[1].lead


def test_brief_from_direction_drops_a_director_name_that_is_not_in_the_cast(tmp_path, caplog) -> None:
    from echotales.pipeline.render.direction import CharacterDirection, PanelDirection

    d = PanelDirection(characters=[CharacterDirection(name="Fang"), CharacterDirection(name="Lady Zed", pose="sitting")])
    with caplog.at_level("INFO"):
        brief = brief_from_direction(_two_person_store(tmp_path), "n", ["s1", "s2"], 1.0, d)
    assert [c.name for c in brief.characters] == ["Fang Yuan"]  # "Fang" matched as a part of the label
    assert "Lady Zed" in caplog.text


def test_brief_from_direction_falls_back_to_the_cast_when_no_director_name_matches(tmp_path) -> None:
    from echotales.pipeline.render.direction import CharacterDirection, PanelDirection

    d = PanelDirection(characters=[CharacterDirection(name="Somebody Else")])
    brief = brief_from_direction(_two_person_store(tmp_path), "n", ["s1", "s2"], 1.0, d)
    assert [c.name for c in brief.characters] == ["Fang Yuan", "Bai Ning Bing"]


def test_brief_from_direction_passes_beat_text_and_director_v2_fields(tmp_path) -> None:
    from echotales.core.enums import TargetKind
    from echotales.core.models import DiscoursePosition, Self
    from echotales.core.store import Store
    from echotales.pipeline.render.direction import CharacterDirection, OthersDirection, PanelDirection

    dir_obj = PanelDirection(
        shot="close",
        camera_angle="low-angle",
        characters=[
            CharacterDirection(name="Fang Yuan", position="center", pose="kneeling", expression="cold_expression", condition="bloodied"),
            CharacterDirection(name="Bai Ning Bing", position="right", pose="standing", expression="smirking"),
        ],
        others=OthersDirection(kind="elders", count=5, relation_to_lead="surrounding"),
        setting="bamboo room interior",
        props=["gu_worm", "lantern"],
    )

    store = Store(str(tmp_path / "t.db"))
    store.add_novel("reverend-insanity", "RI", "x.epub", "generic")
    store.add_self(Self(id="s1", novel_id="reverend-insanity", canonical_label="Fang Yuan", first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.add_self(Self(id="s2", novel_id="reverend-insanity", canonical_label="Bai Ning Bing", first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.conn.commit()

    brief = brief_from_direction(
        store, "reverend-insanity", ["s1", "s2"], 1.0, dir_obj,
        beat_text="Fang Yuan's robes were shredded and stained with blood as he knelt in the room.",
    )
    assert len(brief.characters) == 2
    assert brief.characters[0].position == "center"
    assert brief.characters[0].pose == "kneeling"
    assert brief.characters[1].position == "right"
    assert brief.characters[1].pose == "standing"
    assert brief.camera == "low-angle"
    assert "gu_worm" in brief.key_objects and "lantern" in brief.key_objects
    assert brief.crowd is not None and brief.crowd.description == "elders" and brief.crowd.count == 5
    assert brief.is_indoor is True

