"""The drama compiler and FX layer (docs/results/ART_DRAMA.md). Stub-free: pure text and PIL, no GPU."""

from __future__ import annotations

from _art_bakeoff_panels import bakeoff_panels
from echotales.pipeline.pages import drama_fx
from echotales.pipeline.persona.genre import style_lead
from echotales.pipeline.render.drama import (
    compile_drama,
    compile_neutral,
    compile_noobai_tags,
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
    assert "low-angle" in hero and "chiaroscuro" in hero and "blood-red accent" in hero
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
