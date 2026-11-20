"""Reference pictures reach the browser over http, never file:// (2026-11 Studio walkthrough, EVOLUTION 4.178)."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import Registry, make_handler
from test_security_studio import _multipart, _png
from test_webview_server_jobs import _request, live_server  # noqa: F401  (fixture)


def _mira(handle) -> None:  # type: ignore[no-untyped-def]
    from echotales.core.enums import TargetKind
    from echotales.core.models import DiscoursePosition, Self

    handle.store.add_self(Self(id="ru:mira", novel_id="ru", canonical_label="Mira", kind=TargetKind.SELF,
                               first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    handle.store.conn.commit()


def test_an_uploaded_reference_is_listed_and_served_over_http(live_server, tmp_path: Path, monkeypatch) -> None:  # noqa: F811
    """The upload answered `source_url: file://...`, which the browser blocks, so the dossier showed broken images."""
    monkeypatch.chdir(tmp_path)
    port = live_server
    _request(port, "POST", "/api/projects", body=json.dumps({"id": "ru", "title": "R"}).encode())
    _mira(live_server.registry.handles["ru"])
    body, headers = _multipart("x.png", _png())
    status, out = _request(port, "POST", "/api/novels/ru/characters/ru%3Amira/reference/upload", body=body, headers=headers)
    assert status == 201 and "file://" not in json.dumps(out)
    assert out["image_url"] == f"/api/novels/ru/assets/candidate/{out['id']}/image"

    status, listed = _request(port, "GET", "/api/novels/ru/characters/ru%3Amira/reference/candidates")
    assert status == 200 and listed, listed
    assert "file://" not in json.dumps(listed)
    assert listed[0]["image_url"] == out["image_url"]

    # The dossier reads its pictures from the character list, not the candidates route.
    status, dossier = _request(port, "GET", "/api/novels/ru/characters")
    assert status == 200 and "file://" not in json.dumps(dossier)
    refs = [r for c in dossier["characters"] for r in c["reference_images"]]
    assert refs and refs[0]["image_url"] == out["image_url"]

    conn = HTTPConnection("127.0.0.1", int(port), timeout=10)
    conn.request("GET", out["image_url"])
    resp = conn.getresponse()
    resp.read()
    assert resp.status == 200 and resp.getheader("Content-Type", "").startswith("image/")
    conn.close()


def test_the_candidate_image_takes_the_access_token_when_a_password_is_set(tmp_path: Path, monkeypatch) -> None:
    """An <img> cannot send Authorization, so the picture route must accept `?access_token=` like the output route."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ECHOTALES_WEBVIEW_PASSWORD", "pw")
    registry = Registry([], corrections_dir=tmp_path / "c", projects_dir=tmp_path / "p")
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, JobQueue()))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    try:
        _, login = _request(port, "POST", "/api/auth/login", body=json.dumps({"password": "pw"}).encode())
        token = login["token"]
        auth = {"Authorization": f"Bearer {token}"}
        _request(port, "POST", "/api/projects", body=json.dumps({"id": "ru", "title": "R"}).encode(), headers=auth)
        _mira(registry.handles["ru"])
        body, headers = _multipart("x.png", _png())
        status, out = _request(port, "POST", "/api/novels/ru/characters/ru%3Amira/reference/upload",
                               body=body, headers={**headers, **auth})
        assert status == 201, out

        def get(path: str) -> int:
            c = HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", path)
            r = c.getresponse()
            r.read()
            c.close()
            return r.status

        assert get(out["image_url"]) == 401
        assert get(f"{out['image_url']}?access_token={token}") == 200
        assert get(f"{out['image_url']}?access_token=wrong") == 401
        # The token in the query string is for the picture route, not the JSON API.
        assert get(f"/api/projects?access_token={token}") == 401
    finally:
        httpd.shutdown()
        t.join(timeout=5)
