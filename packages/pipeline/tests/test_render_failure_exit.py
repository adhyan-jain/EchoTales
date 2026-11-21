"""A render that did not draw every panel must not exit as success, and a skipped vision check must say so on disk.

EVOLUTION 4.181 found the job runner reported PARTIAL for a chapter with holes while the CLI render returned 0; and a render
with no vision model wrote no `vision_check.jsonl`, so `audit` could not tell "not checked" from "passed" (4.187).
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest
from _panel_fixture import build_store
from echotales.pipeline.render import compiled_route
from echotales.pipeline.render.panels import PanelReport, render_panels
from echotales.pipeline.workers_contract import ImageWorkerResponse
from PIL import Image
from test_panel_batching import MockNonStubEngine, _chapter_store


def _png_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class _FirstSingleFails:
    """The batch call raises (so each panel is retried alone) and the first panel retried alone fails too."""

    def __init__(self) -> None:
        self.singles = 0

    def generate_many(self, requests, sections=None, *, greyscale=False):
        if len(requests) > 1:
            raise RuntimeError("CUDA out of memory")
        self.singles += 1
        if self.singles == 1:
            raise RuntimeError("bad prompt")
        return [ImageWorkerResponse(image_b64=_png_b64(), seed=r.seed, duration_s=0.01) for r in requests]


class _AlwaysFails:
    def generate_many(self, requests, sections=None, *, greyscale=False):
        raise RuntimeError("CUDA out of memory")


@pytest.fixture
def compiled(monkeypatch):
    from echotales.pipeline.config import ModelBackend, get_settings

    s = get_settings()
    monkeypatch.setattr(s, "render_prompt_compiler", True)
    monkeypatch.setattr(s, "render_image_model", "z-image-turbo")
    monkeypatch.setattr(s, "render_panel_mode", "manga")
    # Never look for an installed vision model (or an ollama daemon) from these tests.
    monkeypatch.setattr(s, "model_backend", ModelBackend.STUB)
    monkeypatch.setattr(s, "render_candidates", 0)
    yield
    compiled_route.set_worker("z-image-turbo", None)


def test_report_counts_the_panels_the_worker_did_not_draw(tmp_path: Path, compiled) -> None:
    compiled_route.set_worker("z-image-turbo", _AlwaysFails())
    report = render_panels("test_novel", _chapter_store(tmp_path), engine=MockNonStubEngine(), out_dir=tmp_path / "p", max_panels=5)
    assert report.panels >= 1
    assert report.failed == report.panels
    assert report.status == "failed" and "FAILED" in report.summary()


def test_report_is_partial_when_some_panels_were_drawn(tmp_path: Path, compiled) -> None:
    compiled_route.set_worker("z-image-turbo", _FirstSingleFails())
    report = render_panels("t", build_store(tmp_path / "t.db"), engine=MockNonStubEngine(), out_dir=tmp_path / "p", max_panels=20)
    assert 0 < report.failed < report.panels, (report.failed, report.panels)
    assert report.status == "partial" and "PARTIAL" in report.summary()
    # The check cannot run in this stub-backend render, and the file says so instead of being absent (4.187).
    rows = [json.loads(ln) for f in (tmp_path / "p").glob("**/vision_check.jsonl") for ln in f.read_text().splitlines()]
    assert rows and all(r["skipped"] for r in rows), rows


def test_a_clean_report_is_ok() -> None:
    r = PanelReport(novel_id="t", panels=3)
    assert r.status == "ok" and "PARTIAL" not in r.summary() and "FAILED" not in r.summary()


def _cli_render(tmp_path: Path, monkeypatch, report: PanelReport) -> int:
    from echotales.pipeline import render as render_pkg
    from echotales.pipeline.cli import main
    from test_render_runner import _seeded_store

    _seeded_store(tmp_path).close()
    monkeypatch.setattr(render_pkg, "render_panels", lambda *a, **k: report)
    return main(["--db", str(tmp_path / "t.db"), "render", "--novel", "t", "--image-engine", "stub", "--no-director",
                 "--skip-motion", "--skip-compose", "--panel-dir", str(tmp_path / "p"), "--motion-dir", str(tmp_path / "m"),
                 "--voice-dir", str(tmp_path / "a"), "--out", str(tmp_path / "v")])


def test_cli_render_exits_nonzero_and_says_partial_when_a_panel_was_not_drawn(tmp_path, monkeypatch, capsys) -> None:
    code = _cli_render(tmp_path, monkeypatch, PanelReport(novel_id="t", panels=4, failed=1))
    out = capsys.readouterr()
    assert code != 0
    assert "PARTIAL" in out.out + out.err and "1 of 4" in out.out + out.err


def test_cli_render_exits_nonzero_when_every_panel_failed(tmp_path, monkeypatch, capsys) -> None:
    code = _cli_render(tmp_path, monkeypatch, PanelReport(novel_id="t", panels=4, failed=4))
    out = capsys.readouterr()
    assert code != 0 and "FAILED" in out.out + out.err


def test_cli_render_still_exits_zero_when_nothing_failed(tmp_path, monkeypatch) -> None:
    assert _cli_render(tmp_path, monkeypatch, PanelReport(novel_id="t", panels=4)) == 0


# --- the vision check says when it did not run -------------------------------------------------------------------


def _settings(monkeypatch, *, backend: str, candidates: int) -> None:
    from echotales.pipeline.config import get_settings

    monkeypatch.setenv("ECHOTALES_LLM_MODE", "stub")
    monkeypatch.setenv("ECHOTALES_MODEL_BACKEND", backend)
    monkeypatch.setenv("ECHOTALES_RENDER_CANDIDATES", str(candidates))
    get_settings(reload=True)


@pytest.fixture
def reload_settings():
    from echotales.pipeline.config import get_settings

    yield
    get_settings(reload=True)


def test_a_stub_run_records_that_the_check_was_skipped_and_why(monkeypatch, reload_settings) -> None:
    from echotales.pipeline.render import panels
    from test_vision_pass import EXPECT

    _settings(monkeypatch, backend="stub", candidates=0)
    rows = panels._vision_check([], {Path("x.png"): EXPECT}, [])
    assert len(rows) == 1 and rows[0]["skipped"] is True and rows[0]["unchecked"] is True
    assert "stub" in rows[0]["reason"]


def test_no_installed_vision_model_records_the_install_line(monkeypatch, reload_settings) -> None:
    from echotales.pipeline.keyframes import qa
    from echotales.pipeline.render import panels
    from echotales.pipeline.render import vision_pass as vp
    from test_vision_pass import EXPECT

    _settings(monkeypatch, backend="ollama", candidates=0)
    monkeypatch.setattr(vp, "choose_vlm", lambda **kw: None)
    rows = panels._vision_check([], {Path("x.png"): EXPECT}, [])
    assert [r["skipped"] for r in rows] == [True] and rows[0]["reason"] == qa.NO_VLM_MESSAGE


def test_one_candidate_records_that_nothing_was_there_to_choose_between(monkeypatch, reload_settings) -> None:
    from echotales.pipeline.render import panels
    from echotales.pipeline.render import vision_pass as vp
    from test_vision_pass import EXPECT

    _settings(monkeypatch, backend="ollama", candidates=1)
    monkeypatch.setattr(vp, "choose_vlm", lambda **kw: None)
    rows = panels._vision_check([], {Path("x.png"): EXPECT}, [])
    assert rows[0]["skipped"] is True and "render.candidates" in rows[0]["reason"]


def test_a_skipped_record_is_not_counted_as_a_checked_panel() -> None:
    from echotales.pipeline.keyframes import qa

    s = qa.summarise([{"panel": "", "skipped": True, "unchecked": True, "reason": "x"}])
    assert s["panels_checked"] == 0 and s["unchecked"] == 0


def test_audit_says_not_checked_when_the_file_holds_only_a_skip_record(tmp_path, monkeypatch) -> None:
    from echotales.pipeline import flow, paths
    from test_vision_pass import _audit_store

    monkeypatch.setattr(paths, "asset_dir", lambda novel_id, kind: tmp_path / kind)
    store = _audit_store(tmp_path)
    vdir = tmp_path / "panels" / "ch1" / "v1"
    vdir.mkdir(parents=True)
    (vdir / "panel_plan.jsonl").write_text("{}\n", encoding="utf-8")
    (vdir / "vision_check.jsonl").write_text(
        json.dumps({"panel": "", "skipped": True, "unchecked": True, "reason": "no vision model installed"}) + "\n",
        encoding="utf-8",
    )
    result = flow.check_vision(store, "test", None)
    assert result.status.value == "SKIPPED" and "no vision model installed" in result.skipped_reason
    assert "not checked" in result.skipped_reason
