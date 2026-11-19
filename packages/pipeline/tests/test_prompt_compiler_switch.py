"""`render.prompt_compiler`: off changes nothing, on routes the prompt through the compiler and records its sections."""

from __future__ import annotations

import json
from pathlib import Path

from _panel_fixture import FakeDirector, build_store
from echotales.pipeline import config
from echotales.pipeline.render.panels import render_panels
from echotales.pipeline.render.plan import load_panel_plan


def _render(tmp_path: Path, name: str):
    store = build_store(tmp_path / f"{name}.db")
    render_panels("t", store, out_dir=tmp_path / name, version="v1", max_panels=20, client=FakeDirector())
    vdir = tmp_path / name / "ch1" / "v1"
    return load_panel_plan(vdir), (vdir / "manifest.jsonl").read_text()


def test_the_compiler_and_z_image_are_the_default():
    # Owner, 2026-11-19: the Z-Image panels are the product; NoobAI is kept only for comparison.
    s = config.Settings()
    assert s.render_prompt_compiler is True and s.render_image_model == "z-image-turbo"


def test_panels_are_colour_by_default_and_manga_stays_an_option():
    # Owner, 2026-11-19: the video product is colour. Monochrome manga is chosen with render.panel_mode=manga.
    assert config.Settings().render_panel_mode == "colour"
    assert config.Settings(render_panel_mode="manga").render_panel_mode == "manga"


def test_off_leaves_prompts_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_settings", config.Settings(render_prompt_compiler=False))
    rows, _ = _render(tmp_path, "off")
    assert all(r.prompt_sections is None for r in rows)


def test_on_records_sections_that_join_to_the_prompt_and_never_say_solo_for_a_crowd(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_settings", config.Settings(render_prompt_compiler=True, render_image_model="noobai-xl-1.1", render_panel_mode="manga"))
    rows, manifest = _render(tmp_path, "on")
    assert rows and all(r.prompt_sections for r in rows)
    for r in rows:
        assert r.prompt_sections[0][0] == "quality"
        assert "monochrome" in r.prompt and "colorful" in r.negative_prompt
    crowd = [r for r in rows if r.slot_kind == "crowd"]
    assert crowd and all("solo" not in r.prompt for r in crowd)
    assert json.loads(manifest.splitlines()[0])  # the manifest still parses
