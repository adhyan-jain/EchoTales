"""Storyboard -> drama-compiled pictures -> FX'd webtoon (pages/storyboard_art.py), on the stub worker: no GPU, no model."""

from __future__ import annotations

import json

import pytest
from echotales.pipeline.pages import drama_fx
from echotales.pipeline.pages.storyboard_art import StubZImageWorker, compile_panel, draw_storyboard
from echotales.pipeline.pages.storyboard_render import render_storyboard_webtoon
from echotales.pipeline.pages.storyboard_style import StyleTable
from echotales.pipeline.persona.genre import style_lead
from echotales.pipeline.persona.prompt import count_tokens
from echotales.pipeline.render import compiled_route
from echotales.pipeline.render.compiler import CharacterBrief
from echotales.pipeline.storyboard.schema import (
    CastMember,
    Layer,
    Letter,
    LetterKind,
    Panel,
    Purpose,
    Segment,
    Shape,
    Shot,
    Storyboard,
)

HERO = CharacterBrief(name="Hero", gender="male", age_band="adult", appearance={"hair": "long black hair", "eyes": "dark eyes"},
                      attire="a torn green robe")
VISION = CharacterBrief(name="Vision", gender="male", age_band="youth", appearance={"hair": "long straight black hair"},
                        attire="a flowing white robe")
LOOKS = {"look_hero": HERO, "vision": VISION}


def _panel(pid: str, purpose: Purpose, shape: Shape, shot: Shot, visual: str, *, layer: Layer = Layer.PRESENT, cast=(), letters=()):
    return Panel(panel_id=pid, segment_id="s1", layer=layer, purpose=purpose, shape=shape, shot=shot, visual=visual,
                 cast=list(cast), letters=list(letters))


def _storyboard() -> Storyboard:
    return Storyboard(
        novel_id="", chapter=1,
        segments=[Segment(segment_id="s1", chapter=1, block_from=0, block_to=9, layer=Layer.PRESENT, place="a cliff at dusk",
                          palette="grim")],
        panels=[
            _panel("cold", Purpose.COLD_OPEN, Shape.BLEED, Shot.LOW_ANGLE, "the hero stands on the cliff, wind tearing his robe",
                   cast=[CastMember(entity_id="hero", name="Hero", look_id="look_hero")],
                   letters=[Letter(kind=LetterKind.SFX, text="BOOM")]),
            _panel("wide", Purpose.ESTABLISHING, Shape.WIDE, Shot.EXTREME_WIDE, "a bare cliff and a red dusk sky over a valley"),
            _panel("eyes", Purpose.EXTREME_CLOSE, Shape.WIDE, Shot.EXTREME_CLOSE,
                   "A pair of clear eyes stare out. A stern old face with a long beard."),
            _panel("inset", Purpose.REFERENCED_INSET, Shape.INSET, Shot.MEDIUM, "a calm young man in white, pictured in someone's mind",
                   layer=Layer.IMAGINED, cast=[CastMember(entity_id="vision", name="Vision")]),
            _panel("card", Purpose.TITLE_CARD, Shape.TEXT_ONLY, Shot.MEDIUM, "",
                   letters=[Letter(kind=LetterKind.NARRATION, text="Chapter One")]),
        ],
    )


@pytest.fixture
def drawn(tmp_path):
    compiled_route.set_worker("z-image-turbo", StubZImageWorker())
    yield draw_storyboard(_storyboard(), tmp_path / "art", LOOKS)
    compiled_route.set_worker("z-image-turbo", None)


def _text(drawn, pid: str) -> str:
    return " ".join(t for _, t in drawn.prompts[pid])


def test_text_only_card_is_not_drawn(drawn):
    assert set(drawn.images) == {"cold", "wide", "eyes", "inset"}
    assert "card" not in drawn.prompts and all(p.exists() for p in drawn.images.values())


def test_style_anchor_first_and_drama_before_identity(drawn):
    for pid, secs in drawn.prompts.items():
        assert secs[0][0] == "style", pid
    cold = _text(drawn, "cold")
    assert cold.startswith(style_lead("", people=True)[:60])
    labels = [k for k, _ in drawn.prompts["cold"]]
    assert labels.index("drama") < labels.index("character:Hero")
    assert "Hero is a man" in cold and "long black hair" in cold and "chiaroscuro" in cold


def test_cold_open_gets_peak_light_and_the_look(drawn):
    cold = _text(drawn, "cold")
    assert "low-angle" in cold and "saturated cold teal-green accent light" in cold and "dark eyes" in cold


def test_wide_establishing_has_no_people(drawn):
    wide = _text(drawn, "wide")
    assert not any(k.startswith("character:") for k, _ in drawn.prompts["wide"])
    assert "no bodies" in wide or "A wide" in wide
    assert "hanfu" not in wide and "mature faces" not in wide  # the people clause of the genre lead is gone


def test_eyes_only_close_adds_no_face_no_name_and_no_tinted_irises(drawn):
    eyes = _text(drawn, "eyes")
    assert not any(k.startswith("character:") for k, _ in drawn.prompts["eyes"])
    assert "one single pair of eyes" in eyes and "no forehead, no nose, no mouth, no second person, no figures" in eyes
    assert "beard" not in eyes  # the paragraph is cropped to eye sentences: "a stern old face with a long beard" is dropped
    assert "never tints the irises" in eyes
    assert "Hero" not in eyes and "cliff" not in eyes  # a frame of eyes has no place to name


def test_referenced_inset_is_an_isolated_subject_on_a_void(drawn):
    inset = _text(drawn, "inset")
    assert "isolated figure floating in a pure empty black void lit only by a soft cold pale-blue glow" in inset
    assert "no landscape, no sky, no mountains and no horizon" in inset
    assert "cliff" not in inset and not any(k in ("setting", "others") for k, _ in drawn.prompts["inset"])
    assert "young man" in inset  # gender and age come from the cast's look
    assert "Vision" in inset


def test_prompts_fit_the_text_window_and_keep_the_priority_sections(drawn):
    for pid, secs in drawn.prompts.items():
        text = " ".join(t for _, t in secs)
        assert count_tokens(text) <= 500, pid
        assert [k for k, _ in secs][:2] == ["style", "framing"] or secs[0][0] == "style"
    assert "drama" in [k for k, _ in drawn.prompts["eyes"]]


def test_a_long_scene_drops_setting_before_identity_or_drama():
    sb = _storyboard()
    sb.panels[0].visual = "the hero stands on the cliff. " + "Banners snap in the wind above the valley, " * 80
    comp = compile_panel(sb.panels[0], sb, LOOKS)
    labels = [s.label for s in comp.sections]
    assert count_tokens(comp.positive) <= 500
    assert {"style", "drama", "character:Hero"} <= set(labels) and "composition" not in labels


def test_fx_run_on_the_right_panels_by_default(tmp_path, drawn, monkeypatch):
    fx_panels, bursts = [], []
    real = drama_fx.apply_panel_fx
    monkeypatch.setattr(drama_fx, "apply_panel_fx", lambda img, p, **kw: (fx_panels.append(p.panel_id), real(img, p, **kw))[1])
    real_b = drama_fx.draw_burst_and_brush
    monkeypatch.setattr(drama_fx, "draw_burst_and_brush", lambda *a, **kw: (bursts.append(a[1].letter.text), real_b(*a, **kw))[1])
    render_storyboard_webtoon(_storyboard(), drawn.images, tmp_path / "out", StyleTable(width=500))
    assert fx_panels == ["cold", "wide", "eyes", "inset"]  # every picture, never the text-only card
    assert bursts == ["BOOM"]  # the burst and brush lettering sit behind the SFX only


def test_fx_off_switch(tmp_path, drawn, monkeypatch):
    called = []
    monkeypatch.setattr(drama_fx, "apply_panel_fx", lambda *a, **k: called.append(1))
    render_storyboard_webtoon(_storyboard(), drawn.images, tmp_path / "off", StyleTable(width=500), drama_fx=False)
    assert not called


def test_cli_draw_stub_writes_prompts_and_slices(tmp_path):
    from echotales.pipeline import cli

    sb = tmp_path / "sb.json"
    sb.write_text(_storyboard().model_dump_json())
    looks = tmp_path / "looks.json"
    looks.write_text(json.dumps({"look_hero": {"name": "Hero", "gender": "male"}}))
    out = tmp_path / "pages"
    try:
        rc = cli.main(["pages", "--novel", "x", "--storyboard", str(sb), "--draw", "stub", "--looks", str(looks), "--out", str(out)])
    finally:
        compiled_route.set_worker("z-image-turbo", None)
    assert rc == 0
    art = next(out.glob("*/art"))
    assert (art / "prompts.json").exists() and (art / "cold.png").exists()
