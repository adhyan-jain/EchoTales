"""Product Orchestration track: end-to-end HTTP coverage for
`webview_server.py`'s new routes -- project lifecycle, source upload,
ingestion trigger, job polling, and the output library.

Runs a real `HTTPServer` on an ephemeral port in a background thread (no
existing `test_webview_server.py` to extend -- the module had zero test
coverage before this track, per `docs/status/STATUS.md`'s own audit). Everything
here is local/stub: no GPU, no network, no real novel data.
"""

from __future__ import annotations

import json
import threading
import time
import zipfile
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import Registry, make_handler


def _build_epub_bytes() -> bytes:
    import io

    docs = {
        "page-0.html": (
            '<div class="chapter type-1"><div class="chapter-title-wrap">'
            '<h2 class="chapter-title">Chapter 1: First</h2></div>'
            '<div class="ugc chapter-ugc"><p><strong>Chapter 1 - First</strong></p>'
            "<p>Opening narration.</p></div></div>"
        )
    }
    toc = [("Chapter 1: First", "page-0.html")]
    nav = "".join(
        f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{label}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, (label, href) in enumerate(toc)
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f"<docTitle><text>Test</text></docTitle><navMap>{nav}</navMap></ncx>"
    )
    manifest = "".join(
        f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, href in enumerate(docs)
    )
    spine = "".join(f'<itemref idref="d{i}"/>' for i in range(len(docs)))
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Novel</dc:title><dc:language>en</dc:language>"
        '<dc:identifier id="id">test</dc:identifier></metadata>'
        f'<manifest>{manifest}<item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{spine}</spine></package>'
    )
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="book.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("book.opf", opf)
        z.writestr("toc.ncx", ncx)
        for href, body in docs.items():
            z.writestr(href, f"<html><body>{body}</body></html>")
    return buf.getvalue()


class LivePort(int):
    registry: Registry
    projects_dir: Path


@pytest.fixture
def live_server(tmp_path: Path):
    registry = Registry(
        [], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects"
    )
    job_queue = JobQueue()
    job_queue.start()
    handler = make_handler(registry, job_queue)
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = LivePort(httpd.server_address[1])
    port.registry = registry
    port.projects_dir = tmp_path / "projects"
    try:
        yield port
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        # Every `registry.handles` entry's `Store` was opened on the server
        # thread (each request that creates/discovers a project runs inside
        # `serve_forever`, which this fixture runs off-thread) -- sqlite3
        # forbids closing a connection from a different thread than the one
        # that created it, so this fixture leaves them for the OS/tmp_path
        # cleanup rather than cross-thread `close()`.


def _request(port: int, method: str, path: str, *, body: bytes = b"", headers: dict | None = None):
    conn = HTTPConnection("127.0.0.1", int(port), timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, (json.loads(data) if data else None)


class TestProjectLifecycleAndJobs:
    def test_create_upload_ingest_poll_output(self, live_server: int) -> None:
        port = live_server

        status, body = _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy", "title": "Toy Novel"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 201, body

        status, listed = _request(port, "GET", "/api/projects")
        assert status == 200
        assert any(p["id"] == "toy" for p in listed)
        toy = next(p for p in listed if p["id"] == "toy")
        assert toy["source_uploaded"] is False
        assert toy["ingested"] is False

        boundary = "TESTBOUNDARY"
        epub_bytes = _build_epub_bytes()
        multipart_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="toy.epub"\r\n'
            "Content-Type: application/epub+zip\r\n\r\n"
        ).encode() + epub_bytes + f"\r\n--{boundary}--\r\n".encode()
        status, body = _request(
            port, "POST", "/api/projects/toy/source",
            body=multipart_body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert status == 201, body

        status, body = _request(port, "POST", "/api/projects/toy/ingest", body=b"{}")
        assert status == 202, body
        job_id = body["job_id"]

        deadline = time.time() + 10
        job_status = None
        while time.time() < deadline:
            status, job_body = _request(port, "GET", f"/api/projects/toy/jobs/{job_id}")
            assert status == 200
            job_status = job_body["status"]
            if job_status in ("SUCCEEDED", "FAILED", "PARTIAL"):
                break
            time.sleep(0.1)
        assert job_status == "SUCCEEDED", job_body

        status, listed = _request(port, "GET", "/api/projects")
        toy = next(p for p in listed if p["id"] == "toy")
        assert toy["ingested"] is True
        assert toy["chapter_count"] == 1

        status, output = _request(port, "GET", "/api/novels/toy/output")
        assert status == 200
        assert output["novel_id"] == "toy"

        # Resumability: re-POSTing /ingest with the same params must be a
        # fast no-op (the stage's skip-on-matching-digest check firing),
        # not a full rerun -- the concrete check the plan's Verification
        # section calls for, not just an aspirational claim. `run_id` can
        # collide with the first job's (both timestamp-keyed to the same
        # second), so the real signal is "exactly one 'ingest' StageRun
        # exists across both jobs," not "job2 has zero" -- a shared run_id
        # would otherwise list job1's own row under job2 too.
        status, first_job_detail = _request(port, "GET", f"/api/projects/toy/jobs/{job_id}")
        status, body2 = _request(port, "POST", "/api/projects/toy/ingest", body=b"{}")
        assert status == 202
        job2_id = body2["job_id"]
        deadline = time.time() + 5
        job2_status = None
        while time.time() < deadline:
            status, job2_body = _request(port, "GET", f"/api/projects/toy/jobs/{job2_id}")
            job2_status = job2_body["status"]
            if job2_status in ("SUCCEEDED", "FAILED", "PARTIAL"):
                break
            time.sleep(0.05)
        assert job2_status == "SUCCEEDED", job2_body
        ingest_stage_run_ids = {
            r["stage_run_id"]
            for body in (first_job_detail, job2_body)
            for r in body["stage_runs"]
            if r["stage_name"] == "ingest"
        }
        assert len(ingest_stage_run_ids) == 1

    def test_render_generate_rejects_paid_engine(self, live_server: int) -> None:
        port = live_server
        _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy2", "title": "Toy Novel 2"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        status, body = _request(
            port, "POST", "/api/novels/toy2/render/generate",
            body=json.dumps({"engine": "gemini"}).encode(),
        )
        assert status == 400
        assert "gemini" in body["error"]

    def test_real_engine_is_refused_while_the_gpu_is_busy_but_stub_is_not(
        self, live_server: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from echotales.pipeline import gpu

        port = live_server
        _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy3", "title": "Toy Novel 3"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        monkeypatch.setattr(gpu, "gpu_status", lambda: gpu.GpuStatus("RTX", 5200, 8188))
        status, body = _request(
            port, "POST", "/api/novels/toy3/render/generate", body=json.dumps({"engine": "noobai"}).encode()
        )
        assert status == 409 and "GPU is busy" in body["error"] and "5200 of 8188" in body["error"]
        assert _request(port, "GET", "/api/gpu")[1] == {
            "available": True, "free": False, "name": "RTX", "used_mb": 5200, "total_mb": 8188,
        }
        status, _ = _request(port, "POST", "/api/novels/toy3/render/generate", body=json.dumps({"engine": "stub"}).encode())
        assert status == 202

        monkeypatch.setattr(gpu, "gpu_status", lambda: None)
        status, body = _request(
            port, "POST", "/api/novels/toy3/render/generate", body=json.dumps({"engine": "noobai"}).encode()
        )
        assert status == 409 and "NVIDIA GPU" in body["error"]

        # The generic job route used to skip the guard (and the genre digest) for render and reference_gen.
        monkeypatch.setattr(gpu, "gpu_status", lambda: gpu.GpuStatus("RTX", 5200, 8188))
        for kind in ("render", "reference_gen"):
            status, body = _request(
                port, "POST", f"/api/projects/toy3/{kind}", body=json.dumps({"engine": "noobai"}).encode()
            )
            assert status == 409 and "GPU is busy" in body["error"], kind

        # A malformed genre body is a 400, not a server error.
        for payload in ({"genre": []}, {"genre": "klingon"}, ["x"]):
            status, _ = _request(port, "POST", "/api/projects/toy3/genre", body=json.dumps(payload).encode())
            assert status == 400, payload

    def test_compute_route_and_a_hosted_engine_is_only_reachable_when_the_operator_chose_it(
        self, live_server: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from echotales.pipeline import compute
        from echotales.pipeline.config import Settings

        port = live_server
        _request(port, "POST", "/api/projects", body=json.dumps({"id": "toy4", "title": "T4"}).encode(),
                 headers={"Content-Type": "application/json"})
        original = compute.policy

        def configured(**kw):
            return lambda settings=None: original(Settings(_env_file=None, **kw))

        # Default laptop profile: the local engines, a preview scope, and no hosted engine reachable by name.
        monkeypatch.setattr(compute, "policy", configured())
        _, body = _request(port, "GET", "/api/compute")
        assert (body["mode"], body["default_tier"], body["scenes"]) == ("local-low", "preview", {"preview": 3, "full": 70})
        assert body["engines"] == ["stub", "noobai", "illustrious", "sdxl"] and body["images_per_scene"] == 3.3
        status, err = _request(port, "POST", "/api/novels/toy4/render/generate", body=json.dumps({"engine": "gemini"}).encode())
        assert status == 400 and "not allowed over HTTP" in err["error"]

        # Cloud preset with the image variables set: only the stub and RunPod, the language model still named as missing.
        monkeypatch.setattr(compute, "policy", configured(compute="cloud", runpod_api_key="k", runpod_image_endpoint="ep"))
        _, body = _request(port, "GET", "/api/compute")
        assert body["engines"] == ["stub", "runpod"] and body["refusals"] == {"stub": None, "runpod": None}
        assert body["llm_missing"] == ["ECHOTALES_RUNPOD_LLM_BASE_URL", "ECHOTALES_RUNPOD_LLM_MODEL"]
        assert "k" not in json.dumps(body["llm_missing"]) and "ep" not in body["llm_missing"]
        status, err = _request(port, "POST", "/api/novels/toy4/render/generate", body=json.dumps({"engine": "noobai"}).encode())
        assert status == 409 and "not enabled on this server" in err["error"]  # a local engine is off in cloud mode

    def test_delete_project(self, live_server: int) -> None:
        port = live_server
        _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy3", "title": "Toy Novel 3"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        status, body = _request(port, "DELETE", "/api/projects/toy3")
        assert status == 200
        assert body["removed"] is True

        status, listed = _request(port, "GET", "/api/projects")
        assert all(p["id"] != "toy3" for p in listed)

    def test_sheet_approve_route(self, live_server: LivePort) -> None:
        port = live_server
        _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": "toy_sheet", "title": "Toy Sheet Novel"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        db_path = live_server.projects_dir / "toy_sheet.db"
        from echotales.core.store import Store
        from echotales.pipeline.persona.refimg import register_sheet_candidate

        img = live_server.projects_dir / "hero.png"
        img.write_bytes(b"sheet_pixels")

        store = Store(str(db_path))
        cand = register_sheet_candidate(
            store, "toy_sheet", "toy_sheet:self:1", "toy_sheet:self:1:body1",
            img, "Hero"
        )
        store.close()

        status, sheets = _request(port, "GET", "/api/novels/toy_sheet/characters/toy_sheet:self:1/sheets")
        assert status == 200
        assert len(sheets) == 1
        assert sheets[0]["id"] == cand.id
        assert sheets[0]["selected"] is False
        assert sheets[0]["is_approved"] is False

        status, res = _request(
            port, "POST", "/api/novels/toy_sheet/characters/toy_sheet:self:1/sheets/toy_sheet:self:1:body1/approve",
            body=json.dumps({"candidate_id": cand.id}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        assert res["selected"] is True

        status, sheets = _request(port, "GET", "/api/novels/toy_sheet/characters/toy_sheet:self:1/sheets")
        assert status == 200
        assert sheets[0]["selected"] is True
        assert sheets[0]["is_approved"] is True

        status, res = _request(
            port, "POST", "/api/novels/toy_sheet/characters/toy_sheet:self:1/sheets/toy_sheet:self:1:body1/reject",
            body=json.dumps({"candidate_id": cand.id}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        assert res["selected"] is False


class TestUploadSafety:
    """Audit 2026-10-31 (ingest/UI B4, B5): the project id, the title and the upload were trusted as sent."""

    @staticmethod
    def _create(port: int, project_id: str, title: str = "T"):
        return _request(
            port, "POST", "/api/projects",
            body=json.dumps({"id": project_id, "title": title}).encode(),
            headers={"Content-Type": "application/json"},
        )

    @staticmethod
    def _upload(port: int, project_id: str, query: str = ""):
        boundary = "TESTBOUNDARY"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="b.epub"\r\n'
            "Content-Type: application/epub+zip\r\n\r\n"
        ).encode() + _build_epub_bytes() + f"\r\n--{boundary}--\r\n".encode()
        return _request(
            port, "POST", f"/api/projects/{project_id}/source{query}", body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    @pytest.mark.parametrize("bad", ["../x", "a/b", "Upper", "-lead", "has space", "x" * 65, ".."])
    def test_unsafe_project_ids_are_refused(self, live_server: int, bad: str) -> None:
        status, body = self._create(live_server, bad)
        assert status == 400, body

    def test_a_title_with_quotes_does_not_corrupt_sources_toml(self, live_server: int) -> None:
        assert self._create(live_server, "quoted", 'The "Quoted" \\ Title')[0] == 201
        assert self._upload(live_server, "quoted")[0] == 201
        status, body = _request(live_server, "POST", "/api/projects/quoted/ingest", body=b"{}")
        assert status == 202, body
        deadline = time.time() + 10
        while time.time() < deadline:
            _, job = _request(live_server, "GET", f"/api/projects/quoted/jobs/{body['job_id']}")
            if job["status"] in ("SUCCEEDED", "FAILED", "PARTIAL"):
                break
            time.sleep(0.1)
        assert job["status"] == "SUCCEEDED", job

    def test_upload_defaults_to_the_generic_adapter_with_given_name_first(self, live_server: int) -> None:
        import tomllib

        assert self._create(live_server, "plain")[0] == 201
        assert self._upload(live_server, "plain")[0] == 201
        sources = live_server.registry.project_asset_dir("plain") / "sources.toml"
        entry = tomllib.loads(sources.read_text(encoding="utf-8"))["novel"][0]
        assert (entry["adapter"], entry["name_order"]) == ("generic", "given_first")

    def test_an_unknown_adapter_or_name_order_is_refused(self, live_server: int) -> None:
        assert self._create(live_server, "odd")[0] == 201
        assert self._upload(live_server, "odd", "?adapter=nope")[0] == 400
        assert self._upload(live_server, "odd", "?name_order=sideways")[0] == 400

    def test_an_oversized_body_is_refused_before_it_is_read(self, live_server: int) -> None:
        conn = HTTPConnection("127.0.0.1", int(live_server), timeout=10)
        conn.putrequest("POST", "/api/projects")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(50 * 1024 * 1024))
        conn.endheaders()
        assert conn.getresponse().status == 413
        conn.close()


class TestPipelineJob:
    """One `pipeline` job runs ingest through personas; the per-stage kinds could not build an uploaded book."""

    @staticmethod
    def _wait(port: int, project: str, job_id: str) -> dict:
        deadline = time.time() + 30
        while time.time() < deadline:
            _, job = _request(port, "GET", f"/api/projects/{project}/jobs/{job_id}")
            if job["status"] in ("SUCCEEDED", "FAILED", "PARTIAL"):
                return job
            time.sleep(0.1)
        raise AssertionError("pipeline job did not finish")

    def test_an_uploaded_book_builds_end_to_end_and_a_rerun_skips_every_stage(self, live_server: int) -> None:
        port = live_server
        assert TestUploadSafety._create(port, "whole", "Whole Book")[0] == 201
        assert TestUploadSafety._upload(port, "whole")[0] == 201

        status, body = _request(port, "POST", "/api/projects/whole/pipeline", body=json.dumps({"no_llm": True}).encode(),
                                headers={"Content-Type": "application/json"})
        assert status == 202, body
        job = self._wait(port, "whole", body["job_id"])
        assert job["status"] == "SUCCEEDED", job

        _, listed = _request(port, "GET", "/api/projects")
        whole = next(p for p in listed if p["id"] == "whole")
        assert whole["ingested"] is True and whole["chapter_count"] == 1

        stages = [r["stage_name"] for r in job["stage_runs"]]
        for name in ("0 ingest", "2 segment", "3 mentions", "4 speakers", "5 anaphora", "6 resolve", "7 personas"):
            assert name in stages, (name, stages)

        # Same source, same params: every stage's digest matches a succeeded run, so nothing runs again.
        status, body2 = _request(port, "POST", "/api/projects/whole/pipeline", body=json.dumps({"no_llm": True}).encode(),
                                 headers={"Content-Type": "application/json"})
        assert status == 202
        job2 = self._wait(port, "whole", body2["job_id"])
        assert job2["status"] == "SUCCEEDED", job2
        assert {r["stage_run_id"] for r in job2["stage_runs"]} == {r["stage_run_id"] for r in job["stage_runs"]}


class TestJobRecovery:
    """The queue is in memory: jobs left PENDING or RUNNING by a stopped server must not spin forever."""

    def test_interrupted_jobs_are_failed_when_a_server_starts(self, tmp_path: Path) -> None:
        from echotales.core.models import Job, StageStatus
        from echotales.core.store import Store

        projects = tmp_path / "projects"
        projects.mkdir()
        store = Store(str(projects / "stuck.db"))
        store.add_novel("stuck", "Stuck", "x.epub", "generic")
        for job_id, status in (("j1", StageStatus.RUNNING), ("j2", StageStatus.PENDING), ("j3", StageStatus.SUCCEEDED)):
            store.add_job(Job(job_id=job_id, novel_id="stuck", kind="ingest", status=status, created_at=1.0))
        store.close()

        registry = Registry([], corrections_dir=tmp_path / "corrections", projects_dir=projects)
        after = {j.job_id: j for j in registry.handles["stuck"].store.list_jobs("stuck")}
        assert after["j1"].status is StageStatus.FAILED and "interrupted" in after["j1"].error_summary
        assert after["j2"].status is StageStatus.FAILED
        assert after["j3"].status is StageStatus.SUCCEEDED  # a finished job is left alone

    def test_a_queued_job_can_be_cancelled_but_a_finished_one_cannot(self, live_server: LivePort) -> None:
        from echotales.core.models import Job, StageStatus

        port = live_server
        assert TestUploadSafety._create(port, "cx")[0] == 201
        store = live_server.registry.handles["cx"].store
        store.add_job(Job(job_id="cx:ingest:queued", novel_id="cx", kind="ingest", status=StageStatus.PENDING, created_at=1.0))
        store.add_job(Job(job_id="cx:ingest:done", novel_id="cx", kind="ingest", status=StageStatus.SUCCEEDED, created_at=2.0))

        status, body = _request(port, "POST", "/api/projects/cx/jobs/cx:ingest:queued/cancel", body=b"{}")
        assert status == 200 and body["status"] == "FAILED" and "cancelled" in body["error_summary"]
        status, _ = _request(port, "POST", "/api/projects/cx/jobs/cx:ingest:done/cancel", body=b"{}")
        assert status == 409


class TestDensityOption:
    def test_compute_status_offers_both_tiers_and_says_which_is_measured(self, live_server: int) -> None:
        status, body = _request(live_server, "GET", "/api/compute")
        assert status == 200
        assert set(body["densities"]) == {"beat", "dense"}
        assert body["densities"]["beat"]["measured"] is True and body["densities"]["dense"]["measured"] is False
        assert body["densities"]["dense"]["blocks_per_panel"] < body["densities"]["beat"]["blocks_per_panel"]

    def test_a_render_job_with_an_unknown_density_is_refused(self, live_server: int) -> None:
        assert TestUploadSafety._create(live_server, "dens")[0] == 201
        status, body = _request(
            live_server, "POST", "/api/projects/dens/render",
            body=json.dumps({"engine": "stub", "density": "everything"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400 and "density" in body["error"]
