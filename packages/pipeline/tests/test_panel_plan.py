"""The panel plan record, the direction two-phase rendering keeps, and the loader.

No model is involved: the stub image engine and `FakeDirector` stand in for both.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _panel_fixture import FakeDirector, build_store, manifest_rows
from echotales.pipeline.render.panels import get_engine, render_panels
from echotales.pipeline.render.plan import (
    PANEL_PLAN_FILE,
    PLAN_SCHEMA_VERSION,
    CachedPrompt,
    PanelPlanSchemaError,
    dropped_clauses,
    load_panel_plan,
    load_prompt_cache,
)

SNAPSHOT = Path(__file__).with_name("_panel_fixture_nodirector_snapshot.json")


@pytest.fixture(autouse=True)
def _legacy_inline_prompts(monkeypatch):
    """These tests pin the inline NoobAI prompt path byte for byte; Z-Image through the compiler became the default
    on 2026-11-19, so they name the legacy path explicitly."""
    from echotales.pipeline import config

    monkeypatch.setattr(config, "_settings", config.Settings(render_prompt_compiler=False, render_image_model="noobai-xl-1.1"))


def _single(tmp_path: Path, name: str = "single", *, client=None):
    store = build_store(tmp_path / "t.db")
    render_panels("t", store, out_dir=tmp_path / name, version="v1", max_panels=20, client=client)
    return store, tmp_path / name / "ch1" / "v1"


def _two_phase(tmp_path: Path, store, cache: Path | None = None):
    """The two `render_panels` calls `cmd_render` makes: a directed pass into a scratch
    directory, then a client-less pass that reads the prompt cache."""
    cache = cache or tmp_path / "prompt_cache.json"
    render_panels(
        "t", store, out_dir=tmp_path / "scratch", engine=get_engine("stub"), max_panels=20,
        client=FakeDirector(), prompt_cache_path=cache, version="v1",
    )
    render_panels(
        "t", store, out_dir=tmp_path / "two", max_panels=20, client=None,
        prompt_cache_path=cache, version="v1",
    )
    return tmp_path / "two" / "ch1" / "v1"


def test_single_phase_writes_one_row_per_image_with_scene_blocks_cast_and_direction(tmp_path):
    _, vdir = _single(tmp_path, client=FakeDirector())
    rows = load_panel_plan(vdir)
    images = {r["image_path"] for r in map(json.loads, (vdir / "manifest.jsonl").read_text().splitlines())}
    assert len(rows) == len(images) == 7
    assert [r.panel_seq for r in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert {r.panel_id for r in rows} == {f"t:1:{n}" for n in range(1, 8)}
    assert all(r.schema_version == PLAN_SCHEMA_VERSION and r.segment_id == "s1" for r in rows)
    assert [r.scene_index for r in rows] == [0, 0, 0, 1, 1, 1, 2]  # "clansmen" is no longer a village cue (whole-word cues)
    assert rows[4].slot_kind == "crowd" and rows[4].block_indexes == [8]
    assert rows[1].slot_kind == "closeup" and rows[1].block_indexes == [2]
    assert rows[0].block_indexes == [1, 3, 4] and rows[0].lead_block == 1
    # Each scene has its own state row and its own place, though they share a segment.
    assert len({r.scene_state_id for r in rows}) == 3
    assert len({r.location for r in rows}) == 3  # the clansmen scene keeps the temple hall instead of a false village
    assert all(r.direction is not None and r.direction_source == "director" for r in rows)
    assert rows[0].direction.shot == "wide" and rows[0].direction.expression == "calm_expression"
    assert rows[0].direction.key_objects == ["lantern"]
    assert [m.self_id for m in rows[0].cast] == ["t:fang"] and rows[0].cast[0].label == "Fang Yuan"
    assert rows[0].cast_source == "present"
    # The scene's second chunk names nobody and carries the first chunk's cast.
    assert rows[2].cast_source == "carried" and [m.self_id for m in rows[2].cast] == ["t:fang"]
    assert all((vdir / r.image_path).exists() and r.provenance in {"generated", "deduped"} for r in rows)
    assert all(r.cache_key and r.plan_digest and r.state_digest for r in rows)
    assert all(r.prompt_tokens and r.prompt_tokens_before_fit for r in rows)
    assert all(r.dropped_clauses is not None for r in rows)


def test_two_phase_keeps_direction_and_matches_single_phase_exactly(tmp_path):
    """Before, phase 2 had no direction: the negative prompt's style bucket followed the
    mechanical slot instead of the director's shot, a crowd cut lost the director's layout,
    and the cache key hashed empty shot/layout/mood -- so the two paths disagreed."""
    store, single_dir = _single(tmp_path, client=FakeDirector())
    two_dir = _two_phase(tmp_path, store)
    assert manifest_rows(two_dir) == manifest_rows(single_dir)
    one, two = load_panel_plan(single_dir), load_panel_plan(two_dir)
    assert len(one) == len(two)
    for a, b in zip(one, two, strict=True):
        assert b.direction == a.direction and b.direction is not None
        assert (b.prompt, b.negative_prompt, b.cache_key) == (a.prompt, a.negative_prompt, a.cache_key)
        assert (b.plan_digest, b.state_digest) == (a.plan_digest, a.state_digest)
        assert (b.direction_source, a.direction_source) == ("prompt_cache", "director")
        assert (b.block_indexes, b.cast, b.slot_kind) == (a.block_indexes, a.cast, a.slot_kind)
        assert b.dropped_clauses == a.dropped_clauses


def _scene_state_by_segment_as_before(store, novel_id, scene, *args, **kwargs):
    """The lookup `get_or_derive_scene_state` had when SNAPSHOT was taken: by segment alone,
    so every scene reused the segment's first row. The scene-state fix changes later scenes'
    locations on purpose; pinning the old lookup isolates everything else."""
    from echotales.pipeline.render.scene_state import derive_scene_state

    if scene.segment_id:
        existing = store.get_scene_state(novel_id, scene.segment_id)
        if existing is not None and not existing.closed:
            return existing
    state = derive_scene_state(store, novel_id, scene, *args, **kwargs)
    store.add_scene_state(state)
    return state


def test_no_director_rows_have_no_direction_and_prompts_are_byte_identical_to_before(
    tmp_path, monkeypatch
):
    """SNAPSHOT was taken from the code at product/finish b4cf73b, before the plan existed (a
    render with no director). To regenerate it deliberately, `git archive` the commit whose
    behaviour should be pinned, run `build_store` + `render_panels(..., version="v1")` there with
    PYTHONPATH on that tree, and dump `manifest_rows` of the version dir as sorted JSON."""
    monkeypatch.setattr(
        "echotales.pipeline.render.panels.get_or_derive_scene_state", _scene_state_by_segment_as_before
    )
    _, vdir = _single(tmp_path)
    got = manifest_rows(vdir)
    want = {int(k): v for k, v in json.loads(SNAPSHOT.read_text()).items()}
    assert got == want
    rows = load_panel_plan(vdir)
    assert all(r.direction is None and r.direction_source is None for r in rows)
    assert {r.direction_reason for r in rows} == {"no director client"}


def test_old_format_prompt_cache_still_loads_and_yields_no_direction(tmp_path):
    cache = tmp_path / "old.json"
    cache.write_text(json.dumps({"1:1:abc:": "a bare prompt"}))
    entry = load_prompt_cache(cache)["1:1:abc:"]
    assert entry.prompt == "a bare prompt" and entry.direction is None
    assert "v1" in entry.direction_reason

    # And a whole phase 2 over such a cache runs, with the prompts it holds.
    store = build_store(tmp_path / "t.db")
    full = tmp_path / "full.json"
    render_panels("t", store, out_dir=tmp_path / "scratch", max_panels=20, client=FakeDirector(),
                  prompt_cache_path=full, version="v1")
    legacy = {k: v["prompt"] for k, v in json.loads(full.read_text()).items()}
    full.write_text(json.dumps(legacy))
    render_panels("t", store, out_dir=tmp_path / "two", max_panels=20, prompt_cache_path=full, version="v1")
    rows = load_panel_plan(tmp_path / "two" / "ch1" / "v1")
    assert all(r.direction is None and "v1" in r.direction_reason for r in rows)
    assert {r.prompt for r in rows if r.slot_kind != "crowd"} <= set(legacy.values())


def test_unreadable_prompt_cache_entries_are_misses(tmp_path):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"a": {"v": 99, "prompt": "x"}, "b": 7, "c": {"v": 2, "prompt": "ok"}}))
    assert list(load_prompt_cache(cache)) == ["c"]
    cache.write_text("{not json")
    assert load_prompt_cache(cache) == {}
    assert CachedPrompt.from_json({"v": 2, "prompt": "p", "direction": {"shot": "close"}}).direction.shot == "close"


def test_every_story_block_reaches_exactly_one_panel(tmp_path):
    store, vdir = _single(tmp_path, client=FakeDirector())
    chapter = store.get_chapter("t", 1.0)
    story = {
        b.index for b in chapter.blocks
        if b.block_type.is_story_content and b.text.strip() and any(c.isalnum() for c in b.text)
    }
    seen: list[int] = []
    for row in load_panel_plan(vdir):
        seen += row.block_indexes
    assert sorted(seen) == sorted(story)  # none missing, none on two images
    assert set(manifest_rows(vdir)) == story


def test_plan_survives_an_engine_error_on_the_nth_panel(tmp_path):
    class Boom(type(get_engine("stub"))):
        calls = 0

        def generate(self, request):
            Boom.calls += 1
            if Boom.calls == 3:
                raise RuntimeError("gpu fell over")
            return super().generate(request)

    store = build_store(tmp_path / "t.db")
    with pytest.raises(RuntimeError):
        render_panels("t", store, engine=Boom(), out_dir=tmp_path / "p", version="v1", max_panels=20)
    rows = load_panel_plan(tmp_path / "p" / "ch1" / "v1")
    assert [r.panel_seq for r in rows] == [1, 2]


def test_rerun_into_the_same_version_directory_does_not_double_the_rows(tmp_path):
    store, vdir = _single(tmp_path)
    render_panels("t", store, out_dir=tmp_path / "single", version="v1", max_panels=20)
    rows = load_panel_plan(vdir)
    assert len(rows) == 7
    assert {r.provenance for r in rows} <= {"cached", "deduped"}


def test_load_panel_plan_rejects_an_unknown_schema_version_and_a_missing_file(tmp_path):
    _, vdir = _single(tmp_path)
    path = vdir / PANEL_PLAN_FILE
    row = json.loads(path.read_text().splitlines()[0])
    row["schema_version"] = 99
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(PanelPlanSchemaError, match="schema_version 99"):
        load_panel_plan(vdir)
    with pytest.raises(FileNotFoundError):
        load_panel_plan(tmp_path / "nowhere")


def test_root_manifest_keeps_chapters_from_earlier_runs_and_replaces_this_one(tmp_path):
    store = build_store(tmp_path / "t.db")
    root = tmp_path / "p"
    root.mkdir()
    stale = {"chapter": 9.0, "block_index": 0, "prompt": "p", "image_path": "x.png",
             "conditioned_on": [], "negative_prompt": "", "cache_key": "k"}
    old_ch1 = dict(stale, chapter=1.0, prompt="old chapter one")
    (root / "manifest.jsonl").write_text(json.dumps(stale) + "\n" + json.dumps(old_ch1) + "\n")
    render_panels("t", store, out_dir=root, version="v1", max_panels=20)
    rows = [json.loads(line) for line in (root / "manifest.jsonl").read_text().splitlines()]
    assert [r["chapter"] for r in rows].count(9.0) == 1
    assert all(r["prompt"] != "old chapter one" for r in rows)
    assert {r["block_index"] for r in rows if r["chapter"] == 1.0} == set(range(1, 13))


def test_dropped_clauses_replays_the_fit_output():
    parts = ["a, b", "", "dropped one", "c", "d"]
    assert dropped_clauses(parts, "a, b, c, d") == ["dropped one"]
    assert dropped_clauses(parts, "a, b, c") == ["dropped one", "d"]
    assert dropped_clauses(["x"], "x") == []
