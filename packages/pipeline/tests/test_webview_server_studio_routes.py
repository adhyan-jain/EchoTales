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
from echotales.pipeline.webview_server import NovelHandle, NovelSource, Registry, make_handler


@pytest.fixture
def studio_server(tmp_path: Path):
    db_path = tmp_path / "test.db"
    store = Store(str(db_path))
    corr_path = tmp_path / "corrections.jsonl"
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
    port, store = studio_server
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


def test_shot_candidates_qa_and_locking(studio_server) -> None:
    port, store = studio_server
    conn = HTTPConnection("127.0.0.1", port)

    # 1. GET shot candidates
    conn.request("GET", "/api/novels/test_novel/episodes/ep1/shots/0/candidates")
    resp = conn.getresponse()
    assert resp.status == 200
    cands = json.loads(resp.read().decode())
    assert len(cands) == 4
    assert "qa_report" in cands[0]
    assert cands[0]["qa_report"]["face_match"]["score"] >= 0.85

    # 2. POST reroll candidates
    conn.request(
        "POST",
        "/api/novels/test_novel/episodes/ep1/shots/0/reroll",
        body=json.dumps({"seed_offset": 50}),
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    assert resp.status == 200
    reroll_res = json.loads(resp.read().decode())
    assert reroll_res["rerolled"] is True
    assert len(reroll_res["candidates"]) == 4

    # 3. POST lock candidate
    conn.request(
        "POST",
        "/api/novels/test_novel/episodes/ep1/shots/0/lock",
        body=json.dumps({"candidate_id": "cand_ep1_0_1"}),
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    assert resp.status == 200
    lock_res = json.loads(resp.read().decode())
    assert lock_res["locked"] is True
    assert lock_res["candidate_id"] == "cand_ep1_0_1"


def test_turnaround_and_plate_generation(studio_server) -> None:
    port, store = studio_server
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
