"""The CLI and Studio doors to `comic/fetch.py`: `echotales comic fetch` and the `comic_fetch` job route.

The fixture site is on loopback, which the real guard refuses; these tests swap the module's default guard for a
loopback-tolerant one with monkeypatch (never an environment variable) and still go through the real routes."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from echotales.pipeline.cli import main
from echotales.pipeline.comic import fetch
from test_comic_fetch import AllowLoopback, Site, _chapter
from test_webview_server_jobs import _request, live_server  # noqa: F401  (fixture)


@pytest.fixture
def site():
    s = Site()
    yield s
    s.httpd.shutdown()


@pytest.fixture
def loopback_ok(monkeypatch):
    monkeypatch.setattr(fetch, "_DEFAULT_GUARD", AllowLoopback())


def test_comic_fetch_cli_saves_pages_prints_summary_and_next_step(site, tmp_path, monkeypatch, capsys, loopback_ok) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["comic", "fetch", _chapter(site), "--id", "t1", "--delay", "0", "--i-own-rights"])
    out = capsys.readouterr().out
    assert code == 0
    assert "responsible for having the right" in out
    assert "5 images (600x900)" in out and "echotales comic build --novel <novel-id> --input" in out
    folder = tmp_path / "data" / "raw" / "comics" / "t1"
    assert (folder / "0001.jpg").is_file()
    assert json.loads((folder / "source.json").read_text())["rights_confirmed"] is True


def test_comic_fetch_cli_refuses_a_private_address(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["comic", "fetch", "http://192.168.1.5/ch1", "--id", "x"]) == 2
    assert "not allowed" in capsys.readouterr().err
    assert not (tmp_path / "data").exists()


def test_raw_comics_are_gitignored() -> None:
    import subprocess

    root = Path(__file__).resolve().parents[3]
    r = subprocess.run(["git", "check-ignore", "-q", "data/raw/comics/x/source.json"], cwd=root)
    assert r.returncode == 0


def _post(port, path: str, body: dict):
    return _request(port, "POST", path, body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})


@pytest.fixture
def project(live_server, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.chdir(tmp_path)
    status, body = _post(live_server, "/api/projects", {"id": "pc", "title": "Pepper"})
    assert status == 201, body
    return live_server


@pytest.mark.parametrize("link", ["", "file:///etc/passwd", "http://127.0.0.1:8787/", "http://10.0.0.2/x", "ftp://a/b", 5])
def test_the_route_refuses_bad_or_private_links_before_queueing(project, link) -> None:
    status, body = _post(project, "/api/projects/pc/comic_fetch", {"url": link})
    assert status == 400 and body["error"]
    _, jobs_list = _request(project, "GET", "/api/projects/pc/jobs")
    assert not any(j["kind"] == "comic_fetch" for j in jobs_list)


def test_the_route_queues_a_job_that_fills_the_projects_comic_source(project, site, loopback_ok) -> None:
    status, body = _post(project, "/api/projects/pc/comic_fetch",
                         {"url": _chapter(site), "rights_confirmed": True, "out_dir": "/tmp/evil"})
    assert status in (200, 202), body
    for _ in range(100):
        _, job = _request(project, "GET", f"/api/projects/pc/jobs/{body['job_id']}")
        if job["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert job["status"] == "SUCCEEDED", job
    _, listing = _request(project, "GET", "/api/projects/pc/comic")
    assert [(s["pages"], s["kind"]) for s in listing["sources"]] == [(5, "images")]
    stamp = json.loads(next(Path("data/novels/pc/comic/source").glob("*/source.json")).read_text())
    assert stamp["rights_confirmed"] is True


def test_a_locked_chapter_fails_the_job_with_a_plain_message(project, site, loopback_ok) -> None:
    site.routes["/locked"] = (403, {}, b"")
    status, body = _post(project, "/api/projects/pc/comic_fetch", {"url": site.base + "/locked"})
    assert status in (200, 202), body
    for _ in range(100):
        _, job = _request(project, "GET", f"/api/projects/pc/jobs/{body['job_id']}")
        if job["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert job["status"] == "FAILED" and "HTTP 403" in job["error_summary"]
