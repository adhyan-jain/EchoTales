"""Redraw one panel, list its candidates, pick one (EVOLUTION 4.179). Stub image engine: no GPU, no model."""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest
from _panel_fixture import build_store
from echotales.core.models import Job
from echotales.pipeline import paths
from echotales.pipeline.jobs import JobQueue, new_job_id, run_job
from echotales.pipeline.render import regen
from echotales.pipeline.render.panels import render_panels
from echotales.pipeline.render.plan import load_panel_plan

from echotales.pipeline.webview_server import NovelSource, Registry, make_handler, sanitize_job_params


@pytest.fixture
def rendered(tmp_path, monkeypatch):
    """A stub render of chapter 1 under a temporary `data/` (DATA_ROOT is relative to the working directory)."""
    monkeypatch.chdir(tmp_path)
    store = build_store(tmp_path / "t.db")
    render_panels("t", store, out_dir=paths.asset_dir("t", "panels"), version="v1_stub", max_panels=20)
    store.conn.commit()  # the server opens its own connection to this file
    vdir = paths.asset_dir("t", "panels") / "ch1" / "v1_stub"
    return store, vdir


def _redraw(store, **params) -> Job:
    params = {"engine": "stub", "chapter": 1.0, **params}
    job = Job(job_id=new_job_id("t", "render"), novel_id="t", kind="render", params_json=json.dumps(params), created_at=time.time())
    store.add_job(job)
    run_job(store, job, params)
    return store.get_job(job.job_id)


def test_redraw_writes_candidates_beside_the_render_and_never_over_it(rendered):
    store, vdir = rendered
    row = load_panel_plan(vdir)[0]
    original = (vdir / row.image_path).read_bytes()
    done = _redraw(store, panel_id=row.panel_id, direction="she turns toward the window", candidates=3)
    assert done.status.value == "SUCCEEDED", done.error_summary
    index = json.loads((vdir / "regen" / str(row.panel_seq) / "index.json").read_text())
    assert index["rounds"][0]["direction"] == "she turns toward the window"
    assert index["rounds"][0]["prompt"].startswith("she turns toward the window")
    assert [c["id"] for c in index["rounds"][0]["candidates"]] == ["r1c0", "r1c1", "r1c2"]
    assert all((vdir / c["file"]).is_file() for c in index["rounds"][0]["candidates"])
    assert (vdir / row.image_path).read_bytes() == original

    # The same request again is a second round with new files, not a skipped or overwriting run.
    again = _redraw(store, panel_id=row.panel_id, candidates=1)
    assert again.status.value == "SUCCEEDED"
    ids = [c["id"] for p in regen.list_panels("t", 1.0)["panels"] if p["panel_id"] == row.panel_id for c in p["candidates"]]
    assert ids == ["original", "r1c0", "r1c1", "r1c2", "r2c0"]
    assert "redraw round 2" in (vdir.parent / "VERSIONS.md").read_text()


def test_direction_comes_from_the_saved_screenplay_shot(rendered):
    store, vdir = rendered
    store.save_screenplay_episode(
        episode_id="ep1", novel_id="t", title="E", source_chapters=[1.0],
        episode_json=json.dumps({"shots": [{"shot_index": 2, "action": "a storm breaks"}]}),
    )
    row = load_panel_plan(vdir)[0]
    done = _redraw(store, panel_id=row.panel_id, episode_id="ep1", shot_index=2, candidates=1)
    assert done.status.value == "SUCCEEDED", done.error_summary
    assert regen.list_panels("t", 1.0)["panels"][0]["direction"] == "a storm breaks"


def test_choice_reaches_the_plan_that_pages_and_video_read_and_can_be_undone(rendered):
    store, vdir = rendered
    row = load_panel_plan(vdir)[0]
    _redraw(store, panel_id=row.panel_id, candidates=2)
    regen.choose_candidate("t", chapter=1.0, panel_id=row.panel_id, candidate_id="r1c1")
    chosen = next(r for r in load_panel_plan(vdir) if r.panel_id == row.panel_id)
    assert chosen.image_path.endswith("r1c1.png") and (vdir / chosen.image_path).is_file()
    assert load_panel_plan(vdir, apply_choices=False)[0].image_path == row.image_path
    assert regen.list_panels("t", 1.0)["panels"][0]["chosen"] == "r1c1"
    regen.choose_candidate("t", chapter=1.0, panel_id=row.panel_id, candidate_id="original")
    assert load_panel_plan(vdir)[0].image_path == row.image_path
    with pytest.raises(regen.PanelRegenError):
        regen.choose_candidate("t", chapter=1.0, panel_id=row.panel_id, candidate_id="r9c9")


def test_bad_requests_fail_with_a_reason(rendered):
    store, vdir = rendered
    row = load_panel_plan(vdir)[0]
    assert "no panel" in (_redraw(store, panel_id="t:1:999").error_summary or "")
    assert "candidates must be" in (_redraw(store, panel_id=row.panel_id, candidates=99).error_summary or "")
    assert "version" in (_redraw(store, panel_id=row.panel_id, version="../x").error_summary or "")
    assert "chapter" in (_redraw(store, panel_id=row.panel_id, chapter=None).error_summary or "")


def test_server_owned_paths_are_dropped_from_a_redraw_request():
    params = sanitize_job_params({"panel_id": "t:1:0", "chapter": 1, "panel_dir": "/etc", "out_dir": "/tmp"})
    assert "panel_dir" not in params and "out_dir" not in params and params["panel_id"] == "t:1:0"


@pytest.fixture
def server(rendered, tmp_path):
    store, vdir = rendered
    registry = Registry([NovelSource(novel_id="t", label="T", db_path=tmp_path / "t.db")], corrections_dir=tmp_path / "corr")
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, JobQueue()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1], store, vdir
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2.0)


def _call(port, method, path, body=None):
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read().decode() or "{}")


def test_routes_list_queue_and_choose(server):
    port, store, vdir = server
    status, listing = _call(port, "GET", "/api/novels/t/panels?chapter=1")
    assert status == 200 and listing["version"] == "v1_stub"
    panel = listing["panels"][0]
    assert panel["chosen"] == "original" and panel["candidates"][0]["path"].startswith("panels/ch1/v1_stub/")
    assert not any("file://" in c["path"] for c in panel["candidates"])

    # A queued redraw carries the panel and drops the client's folders.
    status, queued = _call(port, "POST", "/api/projects/t/render", {
        "engine": "stub", "chapter": 1, "panel_id": panel["panel_id"], "direction": "closer", "panel_dir": "/etc",
    })
    assert status == 202
    queued_params = json.loads(store.get_job(queued["job_id"]).params_json)
    assert queued_params["panel_id"] == panel["panel_id"] and "panel_dir" not in queued_params
    assert _call(port, "POST", "/api/projects/t/render", {"engine": "stub", "panel_id": "x"})[0] == 400
    assert _call(port, "POST", "/api/projects/t/render", {"engine": "stub", "chapter": 1, "panel_id": "x", "candidates": 50})[0] == 400

    _redraw(store, panel_id=panel["panel_id"], candidates=2)
    status, picked = _call(port, "POST", "/api/novels/t/panels/choose", {"chapter": 1, "panel_id": panel["panel_id"], "candidate_id": "r1c0"})
    assert status == 200 and picked["image"].endswith("r1c0.png")
    assert _call(port, "GET", "/api/novels/t/panels?chapter=1")[1]["panels"][0]["chosen"] == "r1c0"
    assert _call(port, "POST", "/api/novels/t/panels/choose", {"chapter": 1, "panel_id": panel["panel_id"], "candidate_id": "nope"})[0] == 400
    assert _call(port, "GET", "/api/novels/t/panels?chapter=7")[0] == 400
    assert _call(port, "GET", "/api/novels/zzz/panels?chapter=1")[0] == 404
