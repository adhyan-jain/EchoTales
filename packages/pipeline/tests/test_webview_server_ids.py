"""Path-segment decoding, voice-override commit visibility and chapter titles over a real HTTP server.

The React client sends `encodeURIComponent(id)` and ids contain colons (`mybook:self:ab12cd`). Segments were
decoded on some routes only, so the voice route answered 200 while filing the override under the still-encoded id.
"""

from __future__ import annotations

import json
import sqlite3
from http.client import HTTPConnection
from urllib.parse import quote

import pytest
from echotales.core.enums import Prominence
from echotales.core.models import (
    Chapter,
    DiscoursePosition,
    RefImageCandidate,
    Self,
)
from echotales.pipeline.webview_server import _split_path
from test_webview_server_jobs import live_server  # noqa: F401  (fixture)

NOVEL = "idbook"
SELF_ID = f"{NOVEL}:self:ab12cd"
LOC_ID = f"{NOVEL}:loc:cd34ef"


def _call(port: int, method: str, path: str, body: dict | None = None):
    conn = HTTPConnection("127.0.0.1", int(port), timeout=10)
    raw = json.dumps(body).encode() if body is not None else b""
    conn.request(method, path, body=raw, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    try:
        return resp.status, json.loads(data) if data else None
    except ValueError:
        return resp.status, data


@pytest.fixture
def seeded(live_server, tmp_path):  # noqa: F811
    status, _ = _call(live_server, "POST", "/api/projects", {"id": NOVEL, "title": "Id Book", "content_type": "novel"})
    assert status in (200, 201)
    store = live_server.registry.handles[NOVEL].store
    store.add_self(Self(
        id=SELF_ID, novel_id=NOVEL, canonical_label="Mara",
        first_attested_pos=DiscoursePosition(chapter=1, offset=0), prominence=Prominence.PRINCIPAL,
    ))
    img = tmp_path / "ref.png"
    img.write_bytes(b"\x89PNG-bytes")
    store.add_ref_image_candidate(RefImageCandidate(
        id=f"{NOVEL}:cand:1", novel_id=NOVEL, self_id=SELF_ID, character_label="Mara",
        source_url=f"file://{img}",
    ))
    store.add_ref_image_candidate(RefImageCandidate(
        id=f"{NOVEL}:sheet:1", novel_id=NOVEL, self_id=SELF_ID, character_label="Mara",
        source_url=f"file://{img}", role="sheet", persona_id=f"{SELF_ID}:body1",
    ))
    store.add_ref_image_candidate(RefImageCandidate(
        id=f"{NOVEL}:plate:1", novel_id=NOVEL, self_id=LOC_ID, character_label="Hall",
        source_url=f"file://{img}", role="location",
    ))
    store.add_chapter(Chapter(novel_id=NOVEL, number=1, title="The First Night", source_href="a.html", blocks=[]))
    store.add_chapter(Chapter(novel_id=NOVEL, number=2, title="Second Dawn", source_href="b.html", blocks=[]))
    store.conn.commit()
    return live_server


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/api/novels/b/characters/b%3Aself%3Aab/voice", ["api", "novels", "b", "characters", "b:self:ab", "voice"]),
        ("/api/x/a%2Fb/y", ["api", "x", "a/b", "y"]),  # split first: an encoded slash is not a separator
        ("/api/x/100%25/y", ["api", "x", "100%", "y"]),  # literal percent survives a single decode
        ("/api/x/a%253Ab", ["api", "x", "a%3Ab"]),  # double-encoded input is decoded once only
        ("/", [""]),
    ],
)
def test_split_path_decodes_each_segment_once(raw: str, expected: list[str]) -> None:
    assert _split_path(raw) == expected


def _enc(v: str) -> str:
    return quote(v, safe="")


def _ids_routes():
    s, sh, p = _enc(SELF_ID), _enc(f"{NOVEL}:sheet:1"), _enc(f"{NOVEL}:plate:1")
    loc = _enc(LOC_ID)
    base = f"/api/novels/{NOVEL}"
    cand = f"{NOVEL}:cand:1"
    return [
        ("GET", f"{base}/characters/{s}/timeline", None, lambda b: b["self_id"] == SELF_ID),
        ("GET", f"{base}/characters/{s}/reference/candidates", None, lambda b: cand in [x["id"] for x in b]),
        ("GET", f"{base}/characters/{s}/sheets", None, lambda b: [x["id"] for x in b] == [f"{NOVEL}:sheet:1"]),
        ("GET", f"{base}/locations/{loc}/plates", None, lambda b: [x["id"] for x in b] == [f"{NOVEL}:plate:1"]),
        ("GET", f"{base}/assets/candidate/{p}/image", None, lambda b: True),
        ("POST", f"{base}/characters/{s}/voice", {"speaker_id": "v1"}, lambda b: b["self_id"] == SELF_ID),
        ("POST", f"{base}/characters/{s}/reference", {"candidate_id": cand}, lambda b: b["id"] == cand),
        ("POST", f"{base}/characters/{s}/reference/search", {}, lambda b: b["kind"] == "refimg_search"),
        ("POST", f"{base}/characters/{s}/sheets/{_enc(f'{SELF_ID}:body1')}/approve", {"candidate_id": f"{NOVEL}:sheet:1"},
         lambda b: b["self_id"] == SELF_ID),
        ("POST", f"{base}/characters/{s}/turnarounds/{sh}/approve", {},
         lambda b: b["self_id"] == SELF_ID and b["id"] == f"{NOVEL}:sheet:1"),
        ("POST", f"{base}/locations/{loc}/plates/{p}/approve", {},
         lambda b: b["location_id"] == LOC_ID and b["id"] == f"{NOVEL}:plate:1"),
    ]


@pytest.mark.parametrize("idx", range(len(_ids_routes())))
def test_every_id_route_sees_the_decoded_id(seeded, idx: int) -> None:
    method, path, body, check = _ids_routes()[idx]
    status, resp = _call(seeded, method, path, body)
    assert status in (200, 202), (path, status, resp)
    assert check(resp), (path, resp)


def test_search_job_carries_the_decoded_self_id(seeded) -> None:
    _call(seeded, "POST", f"/api/novels/{NOVEL}/characters/{_enc(SELF_ID)}/reference/search", {})
    jobs = seeded.registry.handles[NOVEL].store.list_jobs(NOVEL)
    assert json.loads(jobs[0].params_json) == {"self_ids": [SELF_ID]}


@pytest.mark.parametrize(
    ("suffix", "body"),
    [
        ("voice", {"speaker_id": "v1"}),
        ("reference", {"candidate_id": "x"}),
        ("reference/search", {}),
    ],
)
def test_unknown_character_is_404(seeded, suffix: str, body: dict) -> None:
    status, resp = _call(seeded, "POST", f"/api/novels/{NOVEL}/characters/{_enc('nope:self:zz')}/{suffix}", body)
    assert status == 404, resp


def test_unknown_character_upload_is_404(seeded) -> None:
    conn = HTTPConnection("127.0.0.1", int(seeded), timeout=10)
    conn.request("POST", f"/api/novels/{NOVEL}/characters/{_enc('nope:self:zz')}/reference/upload",
                 body=b"", headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert conn.getresponse().status == 404


def test_voice_override_is_stored_under_the_decoded_persona_and_committed(seeded) -> None:
    status, _ = _call(seeded, "POST", f"/api/novels/{NOVEL}/characters/{_enc(SELF_ID)}/voice", {"speaker_id": "v9"})
    assert status == 200
    db_path = seeded.registry.handles[NOVEL].source.db_path
    # A second connection sees only committed rows; the route used to leave the INSERT in an open transaction,
    # so this read found nothing and a write here failed with "database is locked".
    other = sqlite3.connect(db_path, timeout=0.5)
    try:
        rows = other.execute("SELECT target_id, value FROM attribute WHERE key='voice_override'").fetchall()
        assert rows == [(f"{SELF_ID}:body1", "v9")]
        other.execute("CREATE TABLE IF NOT EXISTS probe(x)")
        other.commit()
    finally:
        other.close()


@pytest.mark.parametrize("idx", [i for i, r in enumerate(_ids_routes()) if r[0] == "POST"])
def test_write_routes_leave_no_open_transaction(seeded, idx: int) -> None:
    """A route that answers before committing holds a write lock against every other connection."""
    method, path, body, _ = _ids_routes()[idx]
    status, _resp = _call(seeded, method, path, body)
    assert status in (200, 202)
    assert not seeded.registry.handles[NOVEL].store.conn.in_transaction, path


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (f"/api/projects/{NOVEL}/genre", {"genre": "xianxia"}),
        (f"/api/novels/{NOVEL}/bible/lock", {"note": "t"}),
    ],
)
def test_other_write_routes_leave_no_open_transaction(seeded, path: str, body: dict) -> None:
    _call(seeded, "POST", path, body)
    assert not seeded.registry.handles[NOVEL].store.conn.in_transaction, path


def test_chapters_route_serves_titles_from_the_store(seeded) -> None:
    status, body = _call(seeded, "GET", f"/api/novels/{NOVEL}/chapters")
    assert status == 200
    assert body == [{"number": 1, "title": "The First Night"}, {"number": 2, "title": "Second Dawn"}]
