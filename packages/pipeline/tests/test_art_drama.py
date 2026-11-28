"""The drama compiler and FX layer (docs/results/ART_DRAMA.md). Stub-free: pure text and PIL, no GPU."""

from __future__ import annotations

import dataclasses
import re

from _art_bakeoff_panels import bakeoff_panels
from echotales.pipeline.pages import drama_fx
from echotales.pipeline.persona.genre import style_lead
from echotales.pipeline.render.drama import (
    compile_drama,
    compile_neutral,
    compile_noobai_tags,
    drama_identity_sentence,
    drama_spec,
    is_peak,
)
from PIL import Image

PANELS = {bp.panel_id: bp for bp in bakeoff_panels()}


def test_thirteen_panels_with_right_cast():
    assert len(PANELS) == 13
    assert PANELS["p12_eyes"].panel.cast == []  # a withheld identity stays withheld
    assert [c.name for c in PANELS["p10_bainingbing"].panel.cast] == ["Bai Ning Bing"]
    assert PANELS["p10_bainingbing"].invented_look
    assert "15-year-old" in compile_drama(PANELS["p13_young"].brief, PANELS["p13_young"].panel).positive
    assert "middle-aged" in compile_drama(PANELS["p07_clanhead"].brief, PANELS["p07_clanhead"].panel).positive


def test_style_anchor_stays_first_in_both_arms():
    for bp in PANELS.values():
        lead = style_lead(bp.brief.novel_id, people=True)
        for comp in (compile_neutral(bp.brief, bp.panel), compile_drama(bp.brief, bp.panel)):
            assert comp.sections[0].label == "style"
            assert comp.positive.startswith(lead[:60])


def test_peaks_get_low_angle_and_chiaroscuro_calm_beats_do_not():
    hero = compile_drama(PANELS["p01_hero"].brief, PANELS["p01_hero"].panel).positive
    assert "low-angle" in hero and "chiaroscuro" in hero and "saturated blood-red accent light" in hero
    calm = compile_drama(PANELS["p07_clanhead"].brief, PANELS["p07_clanhead"].panel).positive
    assert "chiaroscuro" not in calm and "dutch" not in calm
    assert not is_peak(PANELS["p06_village"].panel) and is_peak(PANELS["p04_laugh"].panel)


def test_motion_only_when_the_text_has_motion():
    assert drama_spec(PANELS["p01_hero"].panel).motion  # "wind tearing his robe"
    assert not drama_spec(PANELS["p09_elder"].panel).motion


def test_drama_block_sits_before_identity_and_is_listed():
    comp = compile_drama(PANELS["p01_hero"].brief, PANELS["p01_hero"].panel)
    labels = [s.label for s in comp.sections]
    assert labels.index("drama") < labels.index("character:Fang Yuan")


def test_noobai_tags_carry_drama_on_peaks_only():
    bp = PANELS["p01_hero"]
    pos, neg, _ = compile_noobai_tags(bp.panel, identity_tags=bp.identity_tags, scene_tags=bp.scene_tags)
    assert pos.startswith("score_9") and "chiaroscuro" in pos and "from below" in pos and "worst quality" in neg
    cb = PANELS["p07_clanhead"]
    calm, _, _ = compile_noobai_tags(cb.panel, identity_tags=cb.identity_tags, scene_tags=cb.scene_tags)
    assert "chiaroscuro" not in calm


def test_fx_changes_peaks_and_is_size_stable():
    img = Image.new("RGB", (320, 480), (120, 130, 140))
    hero = drama_fx.apply_panel_fx(img, PANELS["p01_hero"].panel, seed=1)
    assert hero.size == img.size and hero.tobytes() != img.tobytes()
    mem = PANELS["p01_hero"].panel.model_copy(update={"layer": "memory"})
    assert drama_fx.apply_panel_fx(img, mem).size == img.size


def test_screentone_is_binary_dots():
    t = drama_fx.screentone((64, 64), pitch=8)
    assert set(t.flatten().tolist()) <= {0.0, 1.0} and 0.05 < t.mean() < 0.5


def test_brush_sfx_and_burst_are_rgba_with_ink():
    b = drama_fx.brush_sfx("THUD", 90, (255, 255, 255), (0, 0, 0), seed=3)
    assert b.mode == "RGBA" and b.getbbox() is not None
    assert drama_fx.burst(200, seed=2).getbbox() is not None


def test_strip_with_fx_switch_differs_and_keeps_layout():
    from echotales.pipeline.pages.storyboard_render import render_storyboard_strip
    from echotales.pipeline.storyboard.schema import Storyboard

    panels = [PANELS[k].panel for k in ("p04_laugh", "p07_clanhead")]
    sb = Storyboard(novel_id="n", chapter=1, panels=panels)
    off = render_storyboard_strip(sb, {})
    on = render_storyboard_strip(sb, {}, drama_fx=True)
    assert on.strip.size == off.strip.size and on.cuts == off.cuts
    assert on.strip.tobytes() != off.strip.tobytes()


# ---- round 2 fixes (docs/results/ART_DRAMA.md, B2)

def _drama(pid):
    bp = PANELS[pid]
    return compile_drama(bp.brief, bp.panel)


def _char(comp, name):
    return next(s.text for s in comp.sections if s.label == f"character:{name}")


def test_age_markers_lead_the_character_clause():
    clan = _char(_drama("p07_clanhead"), "The clan head")
    assert "middle-aged man with greying temples" in clan and "lined face" in clan and "mature" in clan
    assert "adult face with a defined jaw" not in clan  # it told the model to draw a thirty-year-old
    young = _char(_drama("p13_young"), "Fang Yuan")
    assert "15-year-old boy with a youthful soft round face" in young and "slight narrow frame" in young
    elder = _char(_drama("p09_elder"), "An elder")
    assert elder.count("long white beard") == 1 and "frail stooped build" in elder  # the beard only because the cast's own facts say one
    # age comes before hair and clothes, and the section sits before the scene paragraph
    assert clan.index("greying") < clan.index("black topknotted") < clan.index("wearing")
    comp = _drama("p07_clanhead")
    labels = [s.label for s in comp.sections]
    assert labels.index("character:The clan head") < labels.index("composition")
    assert "greying temples" in comp.positive


def test_elder_beard_not_invented():
    bp = PANELS["p09_elder"]
    c = bp.brief.characters[0]
    bare = dataclasses.replace(c, appearance={"hair": "long white"})
    assert "beard" not in drama_identity_sentence(bare)
    nohair = dataclasses.replace(c, appearance={})
    assert "white hair" in drama_identity_sentence(nohair)


def test_gender_explicit_in_every_character_clause():
    for pid, bp in PANELS.items():
        comp = _drama(pid)
        for c in bp.brief.characters:
            clause = _char(comp, c.name)
            word = {"male": r"\b(man|boy)\b", "female": r"\b(woman|girl)\b"}[c.gender]
            assert re.search(word, clause), (pid, clause)
    assert PANELS["p10_bainingbing"].brief.characters[0].gender == "male"  # male in this story time; the look is invented, flagged
    assert re.search(r"\byoung man\b", _char(_drama("p10_bainingbing"), "Bai Ning Bing"))


def test_imagined_panel_has_no_place_and_no_bystanders():
    comp = _drama("p10_bainingbing")
    text = comp.positive
    assert "isolated figure floating in an abstract void" in text and "no other people" in text
    assert not any(s.label in ("setting", "others") for s in comp.sections)
    for banned in ("hall", "temple", "elders", "kneel"):
        assert banned not in text.lower()
    assert "pale-blue glow" in text


def test_empty_cast_panels_forbid_people_and_faces():
    det = _drama("p05_detonation").positive
    assert "no people, no bodies, no faces and no silhouettes" in det
    assert "face and body" not in det and "figures" not in det and "silhouettes in the foreground" not in det
    assert "Wind whips the hair" not in det
    eyes = _drama("p12_eyes").positive
    assert "one single pair of eyes, filling the whole frame" in eyes and "no second person, no figures" in eyes
    assert "brow" not in eyes and "half the face" not in eyes
    village = _drama("p06_village").positive
    assert "no people" in village
    # a crowd or a cast keeps its people
    assert "no people" not in _drama("p08_elders").positive
    assert "no people" not in _drama("p01_hero").positive


def test_peaks_get_perspective_and_saturated_accent():
    hero = _drama("p01_hero").positive
    assert "foreshortening" in hero and "diagonal composition" in hero and "dynamic pose" in hero
    assert "intensely saturated blood-red accent light" in hero
    assert "foreshortening" not in _drama("p07_clanhead").positive


def test_fx_peak_lines_are_thicker_and_denser_and_vignette_stronger():
    import numpy as np

    thin = drama_fx.speed_lines((400, 600), count=100, seed=1)
    thick = drama_fx.speed_lines((400, 600), count=240, seed=1, width=2.6, opacity=1.6)
    assert np.asarray(thick.getchannel("A")).astype(float).mean() > 2 * np.asarray(thin.getchannel("A")).astype(float).mean()
    img = Image.new("RGB", (320, 480), (128, 128, 128))
    corner = lambda im: np.asarray(im)[:20, :20].mean()  # noqa: E731
    base = PANELS["p07_clanhead"].panel
    # TEXT_ONLY draws no lines, so the corner difference is the vignette alone
    peak = drama_fx.apply_panel_fx(img, base.model_copy(update={"purpose": "hero", "shape": "text_only"}), seed=1)
    calm = drama_fx.apply_panel_fx(img, base, seed=1)
    assert corner(peak) < corner(calm) - 10
