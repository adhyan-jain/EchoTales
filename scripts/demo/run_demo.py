"""Drive the whole product over its real HTTP API, in stub mode, from a fresh clone.

    ECHOTALES_LLM_MODE=stub uv run python scripts/demo/run_demo.py [--keep] [--json]

Everything (databases, projects, corrections, audio, panels) lives in one temporary
directory and the process works from inside it: the pipeline's default output paths are
relative (`data/...`), so a working directory change is the only way to keep the repo's own
`data/` untouched without editing the pipeline.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import HTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_sample_epub import write_sample_epub

PROJECT_ID = "saltmere"
JOB_TIMEOUT_S = 120.0
_DONE = ("SUCCEEDED", "FAILED", "PARTIAL", "CANCELLED", "INTERRUPTED")


@dataclass
class Step:
    name: str
    ok: bool
    detail: str
    seconds: float
    #: A documented server refusal that the demo treats as the correct outcome, not a failure.
    expected_refusal: bool = False


class StepFailed(Exception):
    pass


class Client:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"

    def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return self._send(req)

    def upload(self, path: str, filename: str, payload: bytes) -> tuple[int, Any]:
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/epub+zip\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + path, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        return self._send(req)

    @staticmethod
    def _send(req: urllib.request.Request) -> tuple[int, Any]:
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, raw.decode("utf-8", "replace")


def _err(body: Any) -> str:
    return str(body.get("error", body)) if isinstance(body, dict) else str(body)


def _expect(cond: object, message: str) -> None:
    if not cond:
        raise StepFailed(message)


def _seed_voice_bank(root: Path) -> None:
    # The Studio voice job always loads `data/voice` (the server drops any client-supplied bank
    # path), so a tiny VCTK-shaped roster stands in for the real corpus, which is not in git.
    bank = root / "data" / "voice"
    bank.mkdir(parents=True)
    rows = [("p001", 25, "F"), ("p002", 30, "M"), ("p003", 22, "F"), ("p004", 40, "M")]
    lines = ["ID  AGE  GENDER  ACCENTS  REGION  COMMENTS"]
    lines += [f"{i}  {age}  {g}  English  Southern England" for i, age, g in rows]
    (bank / "speaker-info.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _start_server(workdir: Path) -> tuple[HTTPServer, threading.Thread, int]:
    from echotales.pipeline.jobs import JobQueue
    from echotales.pipeline.webview_server import Registry, make_handler

    registry = Registry(
        [], corrections_dir=workdir / "corrections", projects_dir=workdir / "projects"
    )
    queue = JobQueue()
    queue.start()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, int(httpd.server_address[1])


def _wait_job(c: Client, kind: str) -> dict[str, Any]:
    status, body = c.request("POST", f"/api/projects/{PROJECT_ID}/{kind}", {})
    return _wait_queued(c, status, body)


def _wait_queued(c: Client, status: int, body: Any) -> dict[str, Any]:
    _expect(status == 202, f"HTTP {status}: {_err(body)}")
    job_id = body["job_id"]
    deadline = time.time() + JOB_TIMEOUT_S
    while time.time() < deadline:
        st, job = c.request("GET", f"/api/projects/{PROJECT_ID}/jobs/{job_id}")
        _expect(st == 200, f"job poll HTTP {st}: {_err(job)}")
        if job["status"] in _DONE:
            return job
        time.sleep(0.1)
    raise StepFailed(f"job {job_id} still running after {JOB_TIMEOUT_S:.0f}s")


def run_demo(workdir: Path, on_step: Callable[[Step], None] | None = None) -> list[Step]:
    """Run every step inside `workdir`; stop at the first failure. Returns the steps run."""
    # Must be set before the pipeline reads settings; the demo is meaningless against a real model.
    os.environ["ECHOTALES_LLM_MODE"] = "stub"
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    previous_cwd = Path.cwd()
    os.chdir(workdir)
    from echotales.pipeline.config import get_settings

    get_settings(reload=True)
    _seed_voice_bank(workdir)
    epub = write_sample_epub(workdir / "sample.epub")
    httpd, thread, port = _start_server(workdir)
    c = Client(port)
    steps: list[Step] = []
    ctx: dict[str, Any] = {}

    def step(name: str, fn: Callable[[dict[str, Any]], tuple[str, bool]]) -> bool:
        start = time.time()
        try:
            detail, refusal = fn(ctx)
            result = Step(name, True, detail, time.time() - start, refusal)
        except StepFailed as exc:
            result = Step(name, False, str(exc), time.time() - start)
        except Exception as exc:  # a bug in the product surfaces as a failed step, not a traceback
            result = Step(name, False, f"{type(exc).__name__}: {exc}", time.time() - start)
        steps.append(result)
        if on_step:
            on_step(result)
        return result.ok

    novel = f"/api/novels/{PROJECT_ID}"

    def create(_: dict[str, Any]) -> tuple[str, bool]:
        status, body = c.request(
            "POST", "/api/projects", {"id": PROJECT_ID, "title": "The Lamp at Saltmere"}
        )
        _expect(status == 201, f"HTTP {status}: {_err(body)}")
        return f"project {PROJECT_ID}", False

    def upload(_: dict[str, Any]) -> tuple[str, bool]:
        status, body = c.upload(f"/api/projects/{PROJECT_ID}/source", "sample.epub", epub.read_bytes())
        _expect(status == 201, f"HTTP {status}: {_err(body)}")
        return f"{body['bytes']} bytes", False

    def build(_: dict[str, Any]) -> tuple[str, bool]:
        job = _wait_job(c, "pipeline")
        _expect(job["status"] == "SUCCEEDED", f"{job['status']}: {job.get('error_summary')}")
        runs = job.get("stage_runs") or []
        _expect(runs, "job detail lists no stage runs")
        bad = [r["stage_name"] for r in runs if r.get("status") != "SUCCEEDED"]
        _expect(not bad, f"stages not SUCCEEDED: {bad}")
        return f"SUCCEEDED {len(runs)} stages", False

    def reads(ctx: dict[str, Any]) -> tuple[str, bool]:
        got: dict[str, Any] = {}
        for key, path in (
            ("chapters", "/chapters"),
            ("characters", "/characters"),
            ("lines", "/review/lines"),
            ("bible", "/bible"),
        ):
            status, body = c.request("GET", novel + path)
            _expect(status == 200, f"GET {path}: HTTP {status}: {_err(body)}")
            got[key] = body
        chapters, chars, lines = got["chapters"], got["characters"]["characters"], got["lines"]["items"]
        _expect(len(chapters) == 2, f"expected 2 chapters, got {len(chapters)}")
        _expect(chars, "cast is empty")
        ctx.update(chapters=chapters, characters=chars, lines=lines)
        return f"{len(chapters)} chapters, {len(chars)} characters, {len(lines)} review lines", False

    def titles(ctx: dict[str, Any]) -> tuple[str, bool]:
        missing = [ch["number"] for ch in ctx["chapters"] if not ch.get("title")]
        _expect(not missing, f"/chapters returns an empty title for chapters {missing}")
        return "chapter titles served", False

    def correct(ctx: dict[str, Any]) -> tuple[str, bool]:
        if not ctx["lines"]:
            return "no review line to correct (skipped)", False
        line = ctx["lines"][0]
        chars = ctx["characters"]
        target = next((ch for ch in chars if ch.get("label") == "Mara"), chars[0])
        speaker = target["self_id"]
        payload = {
            "span_id": line["span_id"],
            "chapter": line["chapter"],
            "speaker_id": speaker,
        }
        status, body = c.request(
            "POST", f"{novel}/corrections", {"type": "reassign_speaker", "payload": payload}
        )
        _expect(status == 201, f"correction HTTP {status}: {_err(body)}")
        status, body = c.request("POST", f"{novel}/apply", {})
        _expect(status == 200, f"apply HTTP {status}: {_err(body)}")
        _expect(body["count"] == len(body["applied"]) >= 1, f"apply reported {body}")
        status, after = c.request("GET", f"{novel}/review/lines")
        _expect(status == 200, f"GET review/lines HTTP {status}: {_err(after)}")
        still = [i for i in after["items"] if i["span_id"] == line["span_id"]]
        _expect(not still, "a reviewed line is still in the review queue after apply")
        return f"reassigned {line['span_id']} to {target['label']}", False

    def lock(_: dict[str, Any]) -> tuple[str, bool]:
        status, body = c.request("POST", f"{novel}/bible/lock", {"note": "demo"})
        _expect(status == 200, f"HTTP {status}: {_err(body)}")
        status, bible = c.request("GET", f"{novel}/bible")
        _expect(status == 200, f"GET bible HTTP {status}: {_err(bible)}")
        locked = bible["current"]["locked_version"]
        _expect(locked is not None, "locked_version is not set after locking")
        return f"locked_version {locked}", False

    def produced(folder: str, pattern: str) -> str:
        files = list((workdir / "data" / "novels" / PROJECT_ID / folder).rglob(pattern))
        return f"{len(files)} {pattern} files"

    def job_step(
        kind: str, params: dict[str, Any], refusals: tuple[str, ...] = (), made: str = ""
    ):
        def run(_: dict[str, Any]) -> tuple[str, bool]:
            status, body = c.request("POST", f"/api/projects/{PROJECT_ID}/{kind}", params)
            if status in (400, 409) and any(r in _err(body) for r in refusals):
                return f"refused as documented: {_err(body)}", True
            job = _wait_queued(c, status, body)
            if job["status"] != "SUCCEEDED":
                text = str(job.get("error_summary"))
                if any(r in text for r in refusals):
                    return f"refused as documented: {text}", True
                raise StepFailed(f"{job['status']}: {text}")
            if not made:
                return f"SUCCEEDED run {job.get('run_id')}", False
            return f"SUCCEEDED, wrote {produced(*made.split(':'))}", False

        return run

    try:
        for name, fn in (
            ("project", create),
            ("upload", upload),
            ("build", build),
            ("read", reads),
            ("titles", titles),
            ("correct", correct),
            ("lock", lock),
            ("voice", job_step("voice", {"engine": "stub"}, made="audio:*.wav")),
            (
                "m4b",
                job_step(
                    "export_m4b", {}, refusals=("made by the stub engine", "ffmpeg")
                ),
            ),
            ("render", job_step("render", {"engine": "stub", "chapters": [1]}, made="panels:*.png")),
        ):
            if not step(name, fn):
                break
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        os.chdir(previous_cwd)
    return steps


def _line(step: Step) -> str:
    tag = "ok " if step.ok and not step.expected_refusal else ("ref" if step.ok else "FAIL")
    return f"{tag:<5}{step.name:<8}{step.detail} {step.seconds:.1f}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep the temp directory and print it")
    parser.add_argument("--json", action="store_true", help="print a JSON summary instead of lines")
    args = parser.parse_args(argv)

    workdir = Path(tempfile.mkdtemp(prefix="echotales-demo-"))
    on_step = None if args.json else lambda s: print(_line(s), flush=True)
    try:
        # The pipeline prints notices on stdout; --json must leave stdout parseable.
        with contextlib.redirect_stdout(sys.stderr) if args.json else contextlib.nullcontext():
            steps = run_demo(workdir, on_step)
    finally:
        if args.keep:
            print(f"kept: {workdir}", file=sys.stderr if args.json else sys.stdout)
        else:
            shutil.rmtree(workdir, ignore_errors=True)
    if args.json:
        print(json.dumps({"ok": all(s.ok for s in steps), "steps": [asdict(s) for s in steps]}, indent=2))
    return 0 if steps and all(s.ok for s in steps) else 1


if __name__ == "__main__":
    sys.exit(main())
