"""The black-and-white manga look (EVOLUTION 4.187): a render-time look (`render --look bw`) and a page-time conversion of
colour panels (`pages --look bw`). Stub engine and unit tests only; no GPU."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from _panel_fixture import build_store
from echotales.core.models import Chapter, Job
from echotales.core.store import Store
from echotales.pipeline import paths
from echotales.pipeline.jobs import run_job
from echotales.pipeline.persona import genre
from echotales.pipeline.render import lightgrade
from echotales.pipeline.render.panels import render_panels
from echotales.pipeline.render.plan import load_panel_plan
from PIL import Image

#: Words that ask the model for colour or a colour grade. "no colour" (the lead's own negation) is removed before the check.
COLOUR_WORDS = re.compile(
    r"\b(colou?r\w*|warm|cool|cold|golden|gold|red|green|blue|yellow|orange|teal|crimson|sepia|palette|desaturated|"
    r"saturat\w*|tint\w*|painterly|painted|airbrushed|cel)\b", re.I,
)


def _colour_words(text: str) -> list[str]:
    return COLOUR_WORDS.findall(text.replace("no colour", ""))


# --- (a) the render-time look ----------------------------------------------------------------------------------------


def test_the_bw_lead_asks_for_ink_screentone_and_solid_blacks_and_names_no_colour() -> None:
    lead = genre.style_lead("", look="bw")
    assert lead == genre.BW_LEAD
    low = lead.lower()
    assert "black and white manga" in low and "ink" in low and "screentone" in low and "solid blacks" in low and "no colour" in low
    assert _colour_words(lead) == []
    # The default stays the colour lead.
    assert genre.style_lead("") == genre.STYLE_LEADS["xianxia"] and "colour" in genre.style_lead("")


LIGHTS = ["a night study lit by a lamp", "at dusk on the cliff", "a drizzle of rain", "bright morning daylight", "radiant glory"]


@pytest.mark.parametrize("text", LIGHTS)
def test_the_light_grade_of_a_bw_panel_has_no_colour_words(text: str) -> None:
    grade = lightgrade.light_grade(text, mood="ominous and grim", mono=True)
    assert grade and _colour_words(grade) == [], grade


def test_the_colour_light_grade_is_unchanged_and_the_mono_one_keeps_the_light() -> None:
    assert "warm rim light" in lightgrade.light_grade("at dusk on the cliff")  # colour default untouched
    assert "deep shadows" in lightgrade.light_grade("a night study", mono=True)
    assert lightgrade.light_grade("nothing is lit here", mono=True) == ""


def _render(tmp_path: Path, monkeypatch, **kw) -> list:
    monkeypatch.chdir(tmp_path)
    store = build_store(tmp_path / "t.db")
    render_panels("t", store, out_dir=paths.asset_dir("t", "panels"), version="v1_x", max_panels=20, **kw)
    return load_panel_plan(paths.asset_dir("t", "panels") / "ch1" / "v1_x")


def test_a_bw_render_compiles_with_the_ink_lead_and_no_colour_words_in_lead_or_grade(tmp_path, monkeypatch) -> None:
    rows = _render(tmp_path, monkeypatch, look="bw")
    assert rows
    for row in rows:
        sections = dict(row.prompt_sections or [])
        # A director-composed panel leads with the ink lead; a plain one carries the black-and-white style sentence instead.
        assert row.look == "bw" and ("black and white manga" in row.prompt.lower() or "black-and-white manga" in row.prompt.lower())
        assert "palette" not in row.prompt and "colour illustration" not in row.prompt
        for label in ("style", "grade"):
            assert _colour_words(sections.get(label, "")) == [], (label, sections.get(label))


def test_a_composed_bw_panel_leads_with_the_ink_lead_and_carries_a_mono_grade() -> None:
    """The director-composed path (the real render's): lead, then the grade section, both free of colour words."""
    from echotales.pipeline.render.compiler import (
        CharacterBrief,
        OutputMode,
        PanelBrief,
        compile_prompt,
        model_profile,
    )

    def compiled(mode: OutputMode):
        light = "Light: a lamp at dusk."
        return compile_prompt(PanelBrief(
            novel_id="", characters=[CharacterBrief(name="Fang Yuan", gender="male", age_band="adult", lead=True)], mode=mode,
            composition="Fang Yuan stands on a cliff.", lighting="dusk", mood="ominous",
            grade=lightgrade.light_grade(light, mood="ominous", mono=mode is OutputMode.MANGA),
        ), model_profile("z-image-turbo"))

    bw = dict(compiled(OutputMode.MANGA).section_texts())
    assert bw["style"] == genre.BW_LEAD and bw["grade"]
    assert _colour_words(bw["style"]) == [] and _colour_words(bw["grade"]) == []
    colour = dict(compiled(OutputMode.COLOUR).section_texts())
    assert _colour_words(colour["grade"])  # the colour grade still says warm / cold / colour


def test_the_default_render_stays_colour(tmp_path, monkeypatch) -> None:
    rows = _render(tmp_path, monkeypatch)
    assert rows
    for row in rows:
        sections = dict(row.prompt_sections or [])
        assert row.look == "colour" and "manga" not in sections["style"].lower()


def test_an_unknown_look_is_refused_with_the_choices(tmp_path, monkeypatch) -> None:
    with pytest.raises(ValueError, match="colour, bw"):
        _render(tmp_path, monkeypatch, look="sepia")


def _cli(tmp_path: Path, monkeypatch, extra: list[str]) -> dict:
    from echotales.pipeline import render as render_pkg
    from echotales.pipeline.cli import main
    from echotales.pipeline.render.panels import PanelReport
    from test_render_runner import _seeded_store

    _seeded_store(tmp_path).close()
    seen: dict = {}

    def fake(*args, **kw):
        seen.update(kw)
        return PanelReport(novel_id="t", panels=1)

    monkeypatch.setattr(render_pkg, "render_panels", fake)
    code = main(["--db", str(tmp_path / "t.db"), "render", "--novel", "t", "--image-engine", "stub", "--no-director",
                 "--skip-motion", "--skip-compose", "--panel-dir", str(tmp_path / "p"), "--motion-dir", str(tmp_path / "m"),
                 "--voice-dir", str(tmp_path / "a"), "--out", str(tmp_path / "v"), *extra])
    assert code == 0
    return seen


def test_render_look_flag_reaches_render_panels_and_defaults_to_the_configured_look(tmp_path, monkeypatch) -> None:
    assert _cli(tmp_path, monkeypatch, ["--look", "bw"])["look"] == "bw"


def test_render_without_the_flag_does_not_force_a_look(tmp_path, monkeypatch) -> None:
    assert _cli(tmp_path, monkeypatch, [])["look"] is None


def test_render_look_rejects_other_values(tmp_path, monkeypatch, capsys) -> None:
    with pytest.raises(SystemExit):
        _cli(tmp_path, monkeypatch, ["--look", "sepia"])


def test_config_json_render_look_selects_the_manga_panel_mode(tmp_path, monkeypatch) -> None:
    from echotales.pipeline import config

    cfg = tmp_path / "config.json"
    monkeypatch.setattr(config, "_CONFIG_JSON", cfg)
    cfg.write_text(json.dumps({"render": {"look": "bw"}}))
    assert config._load_config_json()["render_panel_mode"] == "manga"
    cfg.write_text(json.dumps({"render": {"look": "colour"}}))
    assert config._load_config_json()["render_panel_mode"] == "colour"
    cfg.write_text(json.dumps({"render": {}}))
    assert "render_panel_mode" not in config._load_config_json()


def _studio_render(tmp_path: Path, **params):
    store = build_store(tmp_path / "t.db")
    panels = tmp_path / "panels"
    params = {"engine": "stub", "chapters": [1.0], "panel_dir": str(panels), "seed": 1, **params}
    job = Job(job_id="t:render:1", novel_id="t", kind="render", created_at=0.0, params_json=json.dumps(params))
    store.add_job(job)
    run_job(store, job, params)
    return store.get_job(job.job_id), panels


def test_the_studio_render_job_takes_a_look_param(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    done, panels = _studio_render(tmp_path, look="bw")
    assert done.status.value == "SUCCEEDED", done.error_summary
    vdir = next(p for p in (panels / "ch1").iterdir() if p.is_dir())
    assert "bw" in vdir.name  # a bw render is told apart from a colour one in the folder name, as the convention asks
    assert all(r.look == "bw" for r in load_panel_plan(vdir))


def test_the_studio_render_job_refuses_an_unknown_look(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    done, _ = _studio_render(tmp_path, look="sepia")
    assert done.status.value == "FAILED" and "colour, bw" in (done.error_summary or "")


def test_a_redraw_of_a_bw_panel_stays_black_and_white(tmp_path, monkeypatch) -> None:
    from echotales.pipeline.render import regen
    from echotales.pipeline.render.panels import StubImageEngine

    monkeypatch.chdir(tmp_path)
    store = build_store(tmp_path / "t.db")
    render_panels("t", store, out_dir=paths.asset_dir("t", "panels"), version="v1_x", max_panels=20, look="bw")
    vdir = paths.asset_dir("t", "panels") / "ch1" / "v1_x"
    row = load_panel_plan(vdir)[0]
    regen.regenerate_panel(
        "t", chapter=1.0, panel_id=row.panel_id, engine=StubImageEngine(), direction="she turns toward the window",
        candidates=1, store=store,
    )
    prompt = json.loads((vdir / "regen" / str(row.panel_seq) / "index.json").read_text())["rounds"][0]["prompt"]
    assert "she turns toward the window" in prompt and "black-and-white manga" in prompt.lower() and "palette" not in prompt


# --- (b) the page-time conversion of colour panels --------------------------------------------------------------------


def test_manga_bw_is_screentone_halftone_with_crushed_blacks_and_white_highlights() -> None:
    from echotales.pipeline.pages.bwlook import to_manga_bw

    # Left to right: black, dark, mid grey, light, white.
    shades = [0, 40, 128, 215, 255]
    img = Image.new("RGB", (len(shades) * 80, 160))
    for i, v in enumerate(shades):
        img.paste((v, v, v), (i * 80, 0, i * 80 + 80, 160))
    out = to_manga_bw(img)
    assert out.size == img.size and out.mode == "L"
    arr = np.asarray(out)
    assert set(np.unique(arr)) <= {0, 255}  # ink and paper, nothing between
    cell = [arr[:, i * 80:(i + 1) * 80] for i in range(len(shades))]
    assert (cell[0] == 0).all() and (cell[1] == 0).all()  # blacks crushed solid
    assert (cell[4] == 255).all() and (cell[3] == 255).all()  # highlights are paper
    mid = (cell[2] == 255).mean()
    assert 0.2 < mid < 0.8  # a midtone is a dot screen: both ink and paper


def test_manga_bw_ignores_hue_and_is_deterministic() -> None:
    from echotales.pipeline.pages.bwlook import to_manga_bw

    red = Image.new("RGB", (60, 60), (200, 40, 40))
    grey = Image.new("RGB", (60, 60), (int(0.299 * 200 + 0.587 * 40 + 0.114 * 40),) * 3)
    assert np.array_equal(np.asarray(to_manga_bw(red)), np.asarray(to_manga_bw(red)))
    assert abs(float((np.asarray(to_manga_bw(red)) == 255).mean()) - float((np.asarray(to_manga_bw(grey)) == 255).mean())) < 0.05


def _pages(tmp_path: Path, **kw):
    from echotales.pipeline.pages.build import build_chapter_pages
    from test_pages_build import NOVEL, _render_panels, _store

    if not (tmp_path / "panels").exists():
        _render_panels(tmp_path)
    return build_chapter_pages(
        _store(tmp_path), NOVEL, 1.0, exports=["png", "cbz"], panel_dir=tmp_path / "panels", out_root=tmp_path / "pages", **kw,
    )


def _is_grey(path: Path) -> bool:
    img = Image.open(path)
    if img.mode == "L":
        return True
    a = np.asarray(img.convert("RGB"))
    return bool((a[..., 0] == a[..., 1]).all() and (a[..., 1] == a[..., 2]).all())


def test_bw_pages_are_greyscale_and_the_colour_default_is_not(tmp_path) -> None:
    bw = _pages(tmp_path, fmt="manga", look="bw")
    pngs = sorted(bw.out_dir.glob("*.png"))
    assert pngs and all(_is_grey(p) for p in pngs)
    manifest = json.loads((bw.out_dir / "pages.json").read_text())
    assert manifest["look"] == "bw" and bw.out_dir.name.endswith("_manga-bw")
    # Lettering stays black on white: the page keeps paper white and ink black.
    arr = np.asarray(Image.open(pngs[0]).convert("L"))
    assert arr.max() == 255 and arr.min() <= 20

    colour = _pages(tmp_path, fmt="manga")  # no look: unchanged
    cpngs = sorted(colour.out_dir.glob("*.png"))
    assert not all(_is_grey(p) for p in cpngs)
    assert json.loads((colour.out_dir / "pages.json").read_text())["look"] == "colour"


def test_bw_pages_dot_screen_is_applied_at_page_scale_not_resampled(tmp_path) -> None:
    pngs = sorted(_pages(tmp_path, fmt="manga", look="bw").out_dir.glob("*.png"))
    arr = np.asarray(Image.open(pngs[0]).convert("L"))
    # Only ink and paper (plus the lettering's own anti-aliased text edges): the bulk of the page is exactly 0 or 255.
    assert ((arr == 0) | (arr == 255)).mean() > 0.9


def test_the_page_format_follows_the_look_unless_one_is_named() -> None:
    from echotales.pipeline.pages.build import resolve_format

    assert resolve_format(None, "bw") == "manga"
    assert resolve_format(None, "colour") == "webtoon"
    assert resolve_format("comic", "bw") == "comic" and resolve_format("manga", "colour") == "manga"
    with pytest.raises(ValueError, match="colour, bw"):
        resolve_format(None, "sepia")


def test_pages_cli_look_bw_defaults_to_manga_and_colour_to_webtoon(tmp_path, monkeypatch) -> None:
    from echotales.pipeline import pages
    from echotales.pipeline.cli import main
    from test_pages_build import NOVEL, SPANS, _render_panels

    _render_panels(tmp_path)
    db = Store(str(tmp_path / "t.db"))
    db.add_novel(NOVEL, "The Novel", "x.epub", "generic")
    db.add_chapter(Chapter(novel_id=NOVEL, number=1.0, title="Opening", source_href="a", blocks=[]))
    db.add_spans(SPANS)
    db.conn.commit()
    db.close()
    seen: list[dict] = []
    real = pages.build.build_pages

    def spy(*a, **kw):
        seen.append(kw)
        return real(*a, **kw)

    monkeypatch.setattr(pages.build, "build_pages", spy)
    base = ["--db", str(tmp_path / "t.db"), "pages", "--novel", NOVEL, "--panel-dir", str(tmp_path / "panels"),
            "--out", str(tmp_path / "pages")]
    assert main([*base, "--look", "bw"]) == 0
    assert main(base) == 0
    assert (seen[0]["fmt"], seen[0]["look"]) == ("manga", "bw")
    assert (seen[1]["fmt"], seen[1]["look"]) == ("webtoon", "colour")  # the default stays colour and webtoon
