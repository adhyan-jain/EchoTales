"""Studio wiring routes (roadmap M5 surface): language note, run estimate, packs, companion, gender, delivery, voices.

One real `HTTPServer` per test over a small built book ("t", three chapters), run from a temporary working directory
because `paths.DATA_ROOT` is relative.
"""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import LANGUAGE_SUPPORT, NovelSource, Registry, make_handler
from test_reader_cast import _book


class Server:
    def __init__(self, port: int, registry: Registry, root: Path, queue: JobQueue) -> None:
        self.port, self.registry, self.root, self.queue = port, registry, root, queue

    def run_job(self, kind: str, params: dict | None = None) -> dict:
        """Queue `kind` over HTTP, start the worker, and wait for the job to end."""
        status, queued = self.call("POST", f"/api/projects/t/{kind}", params or {})
        assert status == 202, queued
        self.queue.start()
        deadline = time.time() + 20
        while time.time() < deadline:
            _, job = self.call("GET", f"/api/projects/t/jobs/{queued['job_id']}")
            if job["status"] not in ("PENDING", "RUNNING"):
                return job
            time.sleep(0.05)
        raise AssertionError("job did not finish")

    def call(self, method: str, path: str, body: object = None, *, raw: bytes | None = None, headers: dict | None = None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        data = raw
        if raw is None and body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        conn.request(method, path, body=data, headers=h)
        resp = conn.getresponse()
        payload = resp.read()
        ctype = resp.getheader("Content-Type") or ""
        conn.close()
        return resp.status, (json.loads(payload) if payload and "json" in ctype else payload)


def multipart(filename: str, data: bytes) -> tuple[bytes, dict]:
    boundary = "XBOUNDARYX"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


@pytest.fixture
def srv(tmp_path, monkeypatch):
    yield from _serve(tmp_path, monkeypatch)


@pytest.fixture
def srv_password(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHOTALES_WEBVIEW_PASSWORD", "hunter2")
    yield from _serve(tmp_path, monkeypatch)


def _serve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book = _book(tmp_path, 3, "t")
    registry = Registry([NovelSource(novel_id="t", label="T", db_path=book.path)], corrections_dir=tmp_path / "corrections")
    queue = JobQueue()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield Server(httpd.server_address[1], registry, tmp_path, queue)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_project_status_carries_the_language_statement(srv) -> None:
    status, projects = srv.call("GET", "/api/projects")
    assert status == 200
    assert projects[0]["language"]["statement"] == LANGUAGE_SUPPORT["statement"]
    assert projects[0]["language"]["supported"] == ["en"]


def test_a_queued_pipeline_job_keeps_its_estimate_in_the_job_list(srv) -> None:
    status, queued = srv.call("POST", "/api/projects/t/pipeline", {})
    assert status == 202
    assert queued["estimate"]["stages"] and queued["estimate"]["seconds"] > 0
    status, jobs = srv.call("GET", "/api/projects/t/jobs")
    assert status == 200
    listed = next(j for j in jobs if j["job_id"] == queued["job_id"])
    # The Studio reads this while the job runs, so it must survive past the 202 reply.
    assert listed["estimate"] == queued["estimate"]
    assert {r["basis"] for r in listed["estimate"]["stages"]} <= {"measured", "estimate"}


def test_other_job_kinds_carry_no_estimate(srv) -> None:
    status, queued = srv.call("POST", "/api/projects/t/pack_export", {})
    assert status == 202
    _, jobs = srv.call("GET", "/api/projects/t/jobs")
    assert "estimate" not in next(j for j in jobs if j["job_id"] == queued["job_id"])


# --- packs ------------------------------------------------------------------------------------------------------------


def _pack_bytes(srv) -> bytes:
    from echotales.pipeline import packs

    out = srv.root / "made.etpack"
    packs.export_pack(srv.registry.handles["t"].store, "t", out)
    return out.read_bytes()


def test_packs_list_is_names_only_and_empty_at_first(srv) -> None:
    status, body = srv.call("GET", "/api/projects/t/packs")
    assert status == 200 and body == {"packs": []}
    assert srv.call("GET", "/api/projects/nope/packs")[0] == 404


def test_an_uploaded_pack_is_listed_by_name_and_never_by_path(srv) -> None:
    raw, headers = multipart("../../sneaky name.etpack", _pack_bytes(srv))
    status, body = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 201, body
    assert body["name"] == "sneaky_name.etpack"
    stored = srv.root / "data" / "novels" / "t" / "packs" / "sneaky_name.etpack"
    assert stored.is_file() and not (srv.root / "sneaky name.etpack").exists()
    status, listed = srv.call("GET", "/api/projects/t/packs")
    assert [p["name"] for p in listed["packs"]] == ["sneaky_name.etpack"]
    assert listed["packs"][0]["bytes"] > 0 and listed["packs"][0]["report"] is None
    assert str(srv.root) not in json.dumps(listed)


def test_a_pack_upload_must_be_a_readable_etpack(srv) -> None:
    raw, headers = multipart("notes.txt", b"hello")
    status, body = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 400 and ".etpack" in body["error"]
    raw, headers = multipart("fake.etpack", b"this is not a zip")
    status, body = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 400
    assert not (srv.root / "data" / "novels" / "t" / "packs" / "fake.etpack").exists()
    assert srv.call("POST", "/api/projects/t/packs", {"x": 1})[0] == 400  # not multipart


def test_a_pack_upload_over_the_cap_is_refused(srv, monkeypatch) -> None:
    from echotales.pipeline import webview_server

    monkeypatch.setattr(webview_server, "_MAX_PACK_BODY", 1000)
    raw, headers = multipart("big.etpack", b"x" * 5000)
    status, _ = srv.call("POST", "/api/projects/t/packs", raw=raw, headers=headers)
    assert status == 413


def test_exporting_then_importing_leaves_a_report_beside_the_pack(srv) -> None:
    done = srv.run_job("pack_export", {"name": "mine"})
    assert done["status"] == "SUCCEEDED", done
    _, listed = srv.call("GET", "/api/projects/t/packs")
    assert [p["name"] for p in listed["packs"]] == ["mine.etpack"]
    done = srv.run_job("pack_import", {"name": "mine"})
    assert done["status"] == "SUCCEEDED", done
    _, listed = srv.call("GET", "/api/projects/t/packs")
    report = listed["packs"][0]["report"]
    assert set(report) >= {"applied", "skipped"} and isinstance(report["applied"], dict)
    # The report file is not itself a pack.
    assert [p["name"] for p in listed["packs"]] == ["mine.etpack"]


# --- companion --------------------------------------------------------------------------------------------------------


def test_the_companion_job_builds_into_the_projects_companion_folder(srv) -> None:
    done = srv.run_job("companion", {"through": 2})
    assert done["status"] == "SUCCEEDED", done
    site = srv.root / "data" / "novels" / "t" / "companion" / "through_2"
    assert (site / "index.html").is_file() and (site / "style.css").is_file()
    # Spoiler safety is companion.py's own tested rule; here only that chapter 3's name stays out of a through-2 page.
    assert "Arthur Vane" not in (site / "index.html").read_text(encoding="utf-8")


def test_a_companion_needs_a_positive_finite_chapter(srv) -> None:
    for bad in ({}, {"through": 0}, {"through": -1}, {"through": "x"}, {"through": "nan"}, {"through": True}):
        status, body = srv.call("POST", "/api/projects/t/companion", bad)
        assert status == 400 and "through" in body["error"], bad


def test_a_built_companion_is_listed_and_served_page_and_stylesheet(srv) -> None:
    assert srv.call("GET", "/api/projects/t/companions") == (200, {"companions": []})
    assert srv.run_job("companion", {"through": 3})["status"] == "SUCCEEDED"
    status, listed = srv.call("GET", "/api/projects/t/companions")
    assert status == 200 and [c["through"] for c in listed["companions"]] == [3]
    status, page = srv.call("GET", "/api/novels/t/companion/through_3/index.html")
    assert status == 200 and b"<h1>T</h1>" in page
    status, css = srv.call("GET", "/api/novels/t/companion/through_3/style.css")
    assert status == 200 and b"--bg" in css


def test_a_password_protected_server_opens_the_companion_page_with_the_session_token_in_the_link(srv_password) -> None:
    srv = srv_password
    site = srv.root / "data" / "novels" / "t" / "companion" / "through_3"
    site.mkdir(parents=True)
    (site / "index.html").write_text("<h1>T</h1>", encoding="utf-8")
    page = "/api/novels/t/companion/through_3/index.html"
    assert srv.call("GET", page)[0] == 401  # a link opened in a new tab cannot send a header...
    _, login = srv.call("POST", "/api/auth/login", {"password": "hunter2"})
    assert srv.call("GET", f"{page}?access_token={login['token']}")[0] == 200  # ...so the link carries the token
    assert srv.call("GET", f"{page}?access_token=wrong")[0] == 401
    assert srv.call("GET", f"/api/projects/t/packs?access_token={login['token']}")[0] == 401  # JSON API: header only


# --- gender -----------------------------------------------------------------------------------------------------------


def _character(srv, self_id: str) -> dict:
    _, body = srv.call("GET", "/api/novels/t/characters")
    return next(c for c in body["characters"] if c["self_id"] == self_id)


def test_the_character_list_carries_each_gender_and_whether_a_reviewer_set_it(srv) -> None:
    mira = _character(srv, "t:mira")
    assert mira["gender"] in ("male", "female", "unknown") and mira["gender_by_reviewer"] is False


def test_a_reviewer_gender_round_trips_through_corrections_and_survives_the_automatic_pass(srv) -> None:
    from echotales.pipeline.persona.gender import infer_missing_genders

    before = _character(srv, "t:corin")["gender"]
    new = "female" if before != "female" else "male"
    status, logged = srv.call("POST", "/api/novels/t/corrections", {"type": "set_gender", "payload": {"self_id": "t:corin", "gender": new}})
    assert status == 201 and logged["type"] == "set_gender"
    status, applied = srv.call("POST", "/api/novels/t/apply", {})
    assert status == 200 and applied["applied"][0].get("gender") == new, applied

    corin = _character(srv, "t:corin")
    assert corin["gender"] == new and corin["gender_by_reviewer"] is True

    # The automatic gender pass (stage 7a) runs again on every rebuild; it must leave the reviewer's value alone.
    report = infer_missing_genders("t", srv.registry.handles["t"].store, None)
    assert report.skipped_human >= 1
    srv.registry.handles["t"].invalidate()
    assert _character(srv, "t:corin")["gender"] == new


def test_a_gender_that_is_not_male_female_or_unknown_is_not_applied(srv) -> None:
    srv.call("POST", "/api/novels/t/corrections", {"type": "set_gender", "payload": {"self_id": "t:corin", "gender": "robot"}})
    _, applied = srv.call("POST", "/api/novels/t/apply", {})
    assert "error" in applied["applied"][0]
    assert _character(srv, "t:corin")["gender_by_reviewer"] is False


# --- per-line delivery ------------------------------------------------------------------------------------------------


def _set_delivery(srv, **payload) -> dict:
    srv.call("POST", "/api/novels/t/corrections", {"type": "set_delivery", "payload": {"span_id": "sp3d", **payload}})
    _, applied = srv.call("POST", "/api/novels/t/apply", {})
    return applied["applied"][-1]


def test_a_delivery_correction_is_what_the_voice_stage_reads_for_that_line(srv) -> None:
    store = srv.registry.handles["t"].store
    # What the reader's delivery pass wrote for the chapter before the reviewer looked at it.
    store.set_span_emotions("t", 3.0, {"sp3d": ("serenity", 1)})
    assert store.span_emotions("t", 3.0)["sp3d"] == ("serenity", 1)

    result = _set_delivery(srv, emotion="anger", intensity=3)
    assert "error" not in result, result
    # `voice/runner.py` reads exactly this call; no engine code was touched to make the override reach it.
    assert store.span_emotions("t", 3.0)["sp3d"] == ("anger", 3)
    assert store.span_emotions("t")["sp3d"] == ("anger", 3)

    # The delivery pass rewrites a whole chapter on every rerun; the reviewer's line must still win.
    store.set_span_emotions("t", 3.0, {"sp3d": ("fear", 2)})
    assert store.span_emotions("t", 3.0)["sp3d"] == ("anger", 3)


def test_a_delivery_correction_for_a_line_the_pass_never_scored_still_applies(srv) -> None:
    store = srv.registry.handles["t"].store
    assert "sp3d" not in store.span_emotions("t", 3.0)
    assert "error" not in _set_delivery(srv, emotion="whisper", intensity=2)
    assert store.span_emotions("t", 3.0)["sp3d"] == ("whisper", 2)


def test_a_second_delivery_correction_for_the_same_line_replaces_the_first(srv) -> None:
    store = srv.registry.handles["t"].store
    _set_delivery(srv, emotion="anger", intensity=3)
    _set_delivery(srv, emotion="sadness", intensity=1)
    assert store.span_emotions("t", 3.0)["sp3d"] == ("sadness", 1)


@pytest.mark.parametrize("payload", [
    {"emotion": "rage", "intensity": 2},          # not an emotion the voice bank knows
    {"emotion": "anger", "intensity": 0},
    {"emotion": "anger", "intensity": 4},
    {"emotion": "anger", "intensity": True},
    {"emotion": "anger", "intensity": "loud"},
    {"emotion": "anger", "span_id": "nope"},      # no such line
    {"emotion": "anger", "span_id": "sp1"},       # narration is read in a mood, not given a line emotion
])
def test_a_bad_delivery_correction_is_refused_and_changes_nothing(srv, payload) -> None:
    store = srv.registry.handles["t"].store
    result = _set_delivery(srv, **({"intensity": 2} | payload))
    assert "error" in result, result
    assert store.span_emotions("t") == {}


def test_a_delivery_correction_is_a_known_correction_type_with_its_payload_kept(srv) -> None:
    status, logged = srv.call("POST", "/api/novels/t/corrections",
                              {"type": "set_delivery", "payload": {"span_id": "sp3d", "emotion": "anger", "intensity": 2}})
    assert status == 201 and logged["payload"]["emotion"] == "anger"
    _, listed = srv.call("GET", "/api/novels/t/corrections")
    assert listed["summary"]["by_type"]["set_delivery"] == 1


def _line(srv, span_id: str = "sp3d") -> dict:
    _, payload = srv.call("GET", "/api/novels/t")
    return next(s for c in payload["chapters"] for s in c["spans"] if s["span_id"] == span_id)


def test_the_review_payload_shows_a_lines_delivery_pending_then_applied(srv) -> None:
    assert "delivery" not in _line(srv)
    srv.call("POST", "/api/novels/t/corrections", {"type": "set_delivery", "payload": {"span_id": "sp3d", "emotion": "anger", "intensity": 3}})
    assert _line(srv)["delivery"] == {"emotion": "anger", "intensity": 3, "pending": True}
    srv.call("POST", "/api/novels/t/apply", {})
    assert _line(srv)["delivery"] == {"emotion": "anger", "intensity": 3, "pending": False}
    # Narration carries none.
    assert "delivery" not in _line(srv, "sp1")


def test_the_dropdown_offers_exactly_the_emotions_the_server_accepts() -> None:
    import re

    from echotales.pipeline.reader.delivery_pass import LABELS

    js = (Path(__file__).resolve().parents[3] / "webview" / "src" / "lib" / "delivery.js").read_text(encoding="utf-8")
    offered = re.findall(r"value: '([a-z]+)'", js)
    assert sorted(offered) == sorted(set(LABELS.values()))


# --- own-voice upload -------------------------------------------------------------------------------------------------


def _wav(seconds: float, rate: int = 16000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def _flac_header(seconds: float, rate: int = 16000) -> bytes:
    """The bytes of a FLAC stream's marker and STREAMINFO block: all the duration check reads."""
    total = int(seconds * rate)
    packed = (rate << 44) | (0 << 41) | (15 << 36) | total  # 20 bits rate, 3 channels-1, 5 bits per sample-1, 36 samples
    return b"fLaC" + b"\x80\x00\x00\x22" + b"\x10\x00\x10\x00" + b"\x00\x00\x00\x00\x00\x00" + packed.to_bytes(8, "big") + b"\x00" * 16


VOICE = "/api/projects/t/voices"
Q = "?name=My%20Voice&gender=female&age=34&consent=true"


def _upload_voice(srv, data: bytes, filename: str = "me.wav", query: str = Q):
    raw, headers = multipart(filename, data)
    return srv.call("POST", VOICE + query, raw=raw, headers=headers)


def test_a_voice_is_refused_without_consent_and_nothing_is_stored(srv) -> None:
    for query in ("?name=me&gender=female&age=30", "?name=me&gender=female&age=30&consent=false", "?name=me&gender=female&age=30&consent=yes"):
        status, body = _upload_voice(srv, _wav(5), query=query)
        assert status == 400 and "permission" in body["error"], query
    assert not (srv.root / "data" / "novels" / "t" / "voices").exists()
    status, listed = srv.call("GET", VOICE)
    assert status == 200 and listed["voices"] == []
    assert listed["statement"] == "This is my voice or I have the speaker's permission."
    assert listed["limits"]["max_seconds"] == 60.0


def test_a_consented_voice_is_stored_with_a_consent_record(srv) -> None:
    status, body = _upload_voice(srv, _wav(5))
    assert status == 201, body
    assert body["voice_id"] == "project:my-voice" and body["gender"] == "female" and body["age"] == 34
    folder = srv.root / "data" / "novels" / "t" / "voices"
    assert (folder / "my-voice.wav").is_file()
    record = json.loads((folder / "my-voice.consent.json").read_text(encoding="utf-8"))
    assert record["statement"] == "This is my voice or I have the speaker's permission."
    assert record["voice_id"] == "project:my-voice" and record["timestamp"] and len(record["sha256"]) == 64
    status, listed = srv.call("GET", VOICE)
    assert [v["voice_id"] for v in listed["voices"]] == ["project:my-voice"]
    assert listed["voices"][0]["consent_at"] == record["timestamp"]
    assert str(srv.root) not in json.dumps(listed)


def test_only_wav_and_flac_of_a_sensible_length_and_size_are_accepted(srv, monkeypatch) -> None:
    assert _upload_voice(srv, _wav(5), "me.mp3")[0] == 400
    assert _upload_voice(srv, b"RIFF not really a wav", "me.wav")[0] == 400
    assert _upload_voice(srv, b"fLaC garbage", "me.flac")[0] == 400
    assert _upload_voice(srv, _wav(1), "short.wav", "?name=short&gender=male&age=30&consent=true")[0] == 400
    assert _upload_voice(srv, _wav(120), "long.wav", "?name=long&gender=male&age=30&consent=true")[0] == 400
    assert _upload_voice(srv, _wav(5), "me.wav", "?name=a&gender=robot&age=30&consent=true")[0] == 400
    assert _upload_voice(srv, _wav(5), "me.wav", "?name=a&gender=male&age=1&consent=true")[0] == 400
    assert _upload_voice(srv, _wav(5), "me.wav", "?name=%2E%2E%2F&gender=male&age=30&consent=true")[0] == 400
    assert _upload_voice(srv, _flac_header(5), "me.flac", "?name=ok-flac&gender=male&age=30&consent=true")[0] == 201

    from echotales.pipeline import webview_server

    monkeypatch.setattr(webview_server, "_MAX_VOICE_BODY", 1000)
    assert _upload_voice(srv, _wav(5), "big.wav", "?name=big&gender=male&age=30&consent=true")[0] == 413


def test_a_voice_name_cannot_be_reused_or_escape_the_voices_folder(srv) -> None:
    assert _upload_voice(srv, _wav(5), "../../x.wav", "?name=a%2Fb%2F..%2Fc&gender=male&age=30&consent=true")[0] == 201
    folder = srv.root / "data" / "novels" / "t" / "voices"
    assert sorted(p.name for p in folder.iterdir()) == ["a-b-c.consent.json", "a-b-c.wav"]
    assert _upload_voice(srv, _wav(5), "again.wav", "?name=a-b-c&gender=male&age=30&consent=true")[0] == 409


def test_project_voices_join_the_bank_the_voice_job_casts_from(srv) -> None:
    from echotales.pipeline.project_voices import load_project_voices
    from echotales.pipeline.voice.bank import VoiceBank

    assert _upload_voice(srv, _wav(5))[0] == 201
    voices = load_project_voices("t")
    assert [(v.speaker_id, v.gender, v.age) for v in voices] == [("project:my-voice", "female", 34)]
    assert voices[0].reference_clip.is_file() and voices[0].clip_for("anger") == voices[0].reference_clip
    from echotales.pipeline.project_voices import with_project_voices

    bank = with_project_voices(VoiceBank([], bank_id="audiobook", licence="CC BY 4.0"), "t")
    assert [v.speaker_id for v in bank.voices] == ["project:my-voice"] and bank.bank_id == "audiobook"


def test_the_companion_route_serves_nothing_outside_the_built_site(srv) -> None:
    assert srv.run_job("companion", {"through": 3})["status"] == "SUCCEEDED"
    secret = srv.root / "data" / "novels" / "t" / "companion" / "secret.txt"
    secret.write_text("no", encoding="utf-8")
    for path in (
        "/api/novels/t/companion/through_3/..%2Fsecret.txt",
        "/api/novels/t/companion/..%2Fsecret.txt/index.html",
        "/api/novels/t/companion/through_3/%2e%2e/secret.txt",
        "/api/novels/t/companion/through_3/other.txt",
        "/api/novels/t/companion/through_9/index.html",
        "/api/novels/t/companion/through_x/index.html",
    ):
        status, _ = srv.call("GET", path)
        assert status in (400, 404), path
    assert srv.call("GET", "/api/novels/nope/companion/through_3/index.html")[0] == 404
