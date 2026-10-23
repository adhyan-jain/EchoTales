"""Tests for webview server studio routes (screenplay, keyframe QA, assets)."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.core.store import Store
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import NovelSource, Registry, make_handler


@pytest.fixture
def studio_server(tmp_path: Path):
    db_path = tmp_path / "test.db"
    store = Store(str(db_path))
    source = NovelSource(novel_id="test_novel", label="Test Novel", db_path=db_path)
    registry = Registry([source], corrections_dir=tmp_path / "corrections")
    jobs = JobQueue()

    handler = make_handler(registry, jobs)
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    yield port, store

    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2.0)
    store.close()


def test_episodes_get_and_post(studio_server) -> None:
    port, _ = studio_server
    conn = HTTPConnection("127.0.0.1", port)

    # 1. GET /api/novels/test_novel/episodes (auto-creates default ep 1)
    conn.request("GET", "/api/novels/test_novel/episodes")
    resp = conn.getresponse()
    assert resp.status == 200
    episodes = json.loads(resp.read().decode())
    assert len(episodes) >= 1
    ep1 = episodes[0]
    ep_id = ep1["episode_id"]

    # 2. GET /api/novels/test_novel/episodes/<ep_id>
    conn.request("GET", f"/api/novels/test_novel/episodes/{ep_id}")
    resp = conn.getresponse()
    assert resp.status == 200
    ep_data = json.loads(resp.read().decode())
    assert ep_data["episode_id"] == ep_id

    # 3. POST /api/novels/test_novel/episodes/<ep_id> (update)
    ep_data["title"] = "Updated Episode Title"
    conn.request(
        "POST",
        f"/api/novels/test_novel/episodes/{ep_id}",
        body=json.dumps({"episode": ep_data}),
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    assert resp.status == 200
    post_res = json.loads(resp.read().decode())
    assert post_res["saved"] is True

    # 4. POST /api/novels/test_novel/episodes/<ep_id>/compile
    conn.request(
        "POST",
        f"/api/novels/test_novel/episodes/{ep_id}/compile",
        body=json.dumps({"chapters": [1.0], "chapter_text": "Sherlock Holmes sat quietly."}),
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    assert resp.status == 200
    compiled = json.loads(resp.read().decode())
    assert "scenes" in compiled


def test_shot_routes_refuse_instead_of_inventing_qa(studio_server) -> None:
    # They used to return 0.94 - i * 0.05 "scores" over recycled panels and a lock that stored nothing.
    port, _ = studio_server
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/api/novels/test_novel/episodes/ep1/shots/0/candidates")
    resp = conn.getresponse()
    assert resp.status == 501
    resp.read()
    for action in ("reroll", "lock"):
        conn.request("POST", f"/api/novels/test_novel/episodes/ep1/shots/0/{action}", body="{}",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 501
        resp.read()


def test_cross_site_writes_are_refused_and_cors_is_not_a_wildcard(studio_server) -> None:
    port, _ = studio_server
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("POST", "/api/novels/test_novel/episodes/ep1/shots/0/lock", body="{}",
                 headers={"Origin": "https://evil.example", "Content-Type": "text/plain"})
    resp = conn.getresponse()
    assert resp.status == 403
    resp.read()
    conn.request("GET", "/api/novels", headers={"Origin": "https://evil.example"})
    resp = conn.getresponse()
    assert resp.getheader("Access-Control-Allow-Origin") is None
    resp.read()
    conn.request("GET", "/api/novels", headers={"Origin": "http://localhost:3000"})
    resp = conn.getresponse()
    assert resp.getheader("Access-Control-Allow-Origin") == "http://localhost:3000"
    resp.read()


def test_missing_candidate_image_is_404_not_another_panel(studio_server) -> None:
    port, _ = studio_server
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/api/novels/test_novel/assets/candidate/nope/image")
    resp = conn.getresponse()
    assert resp.status == 404
    resp.read()


def test_turnaround_and_plate_generation(studio_server) -> None:
    port, _ = studio_server
    conn = HTTPConnection("127.0.0.1", port)

    # 1. POST generate turnaround
    conn.request("POST", "/api/novels/test_novel/characters/char_holmes/turnarounds/generate")
    resp = conn.getresponse()
    assert resp.status == 200
    turn_res = json.loads(resp.read().decode())
    assert turn_res["generated"] is True
    assert "candidate_id" in turn_res

    # 2. POST generate location plate
    conn.request("POST", "/api/novels/test_novel/locations/loc_study/plates/generate")
    resp = conn.getresponse()
    assert resp.status == 200
    plate_res = json.loads(resp.read().decode())
    assert plate_res["generated"] is True
    assert "candidate_id" in plate_res
