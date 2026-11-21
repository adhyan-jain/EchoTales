"""The render-side vision pass: extra candidates per panel, the VLM picks, the chosen image replaces the first."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from echotales.pipeline.keyframes import qa
from echotales.pipeline.render import vision_pass as vp
from echotales.pipeline.render.panels import PanelImageRequest

EXPECT = qa.PanelExpectation(people=1, hair_colour="dark", lead="X")


@pytest.fixture(autouse=True)
def _no_real_worker(monkeypatch) -> None:
    """These tests name the model "m"; no real image worker exists to release."""
    monkeypatch.setattr(vp, "release_worker", lambda key: None)


class FakeVLM:
    """Answers by file content: 'good' passes, anything else has the wrong hair."""

    model = "fake"

    def look(self, path):
        good = Path(path).read_text() == "good"
        return qa.VisionAnswer(people=1, lead_visible=True, hair_colour="black" if good else "red")

    def unload(self) -> None:
        self.unloaded = True


def _requests(tmp_path, n=2):
    reqs, secs = [], []
    for i in range(n):
        p = tmp_path / f"p{i}.png"
        p.write_text("bad")
        reqs.append(PanelImageRequest(prompt=f"prompt {i}", out_path=p, seed=100 + i))
        secs.append([("style", "s")])
    return reqs, secs


def fake_generate(contents):
    """A stand-in for `generate_compiled_batch`: writes `contents[k]` for each candidate index parsed from its name."""
    calls = []

    def gen(requests, sections, model_key, *, greyscale):
        calls.append([(r.out_path.name, r.seed) for r in requests])
        for r in requests:
            k = int(r.out_path.stem.rsplit(".cand", 1)[1])
            r.out_path.write_text(contents[k])
        return []

    gen.calls = calls
    return gen


def test_a_failing_first_candidate_is_replaced_by_the_first_passing_extra(tmp_path, monkeypatch) -> None:
    reqs, secs = _requests(tmp_path)
    gen = fake_generate({1: "bad", 2: "good"})
    monkeypatch.setattr(vp, "generate_compiled_batch", gen)
    vlm = FakeVLM()
    rows = vp.run(reqs, secs, {r.out_path: EXPECT for r in reqs}, vlm=vlm, candidates=3, model_key="m", greyscale=False)
    assert [r.out_path.read_text() for r in reqs] == ["good", "good"]
    assert all(r["chosen"] == 2 and r["passed"] and not r["first_passed"] for r in rows)
    # one batch for candidate 1 and one for candidate 2, every panel in each: the worker loads once per batch
    assert len(gen.calls) == 2 and len(gen.calls[0]) == 2
    assert gen.calls[0][0][1] != 100, "an extra candidate is a different seed"
    assert not list(tmp_path.glob("*.cand*")), "extra images are removed after the choice"
    assert vlm.unloaded


def test_a_passing_first_candidate_is_kept_and_costs_no_extra_image_when_one_candidate(tmp_path, monkeypatch) -> None:
    reqs, secs = _requests(tmp_path, 1)
    reqs[0].out_path.write_text("good")
    monkeypatch.setattr(vp, "generate_compiled_batch", fake_generate({}))
    rows = vp.run(reqs, secs, {reqs[0].out_path: EXPECT}, vlm=FakeVLM(), candidates=1, model_key="m", greyscale=False)
    assert rows[0]["first_passed"] and rows[0]["candidates"] == 1 and reqs[0].out_path.read_text() == "good"


def test_a_panel_without_an_expectation_is_left_alone(tmp_path, monkeypatch) -> None:
    reqs, secs = _requests(tmp_path, 1)
    gen = fake_generate({1: "good"})
    monkeypatch.setattr(vp, "generate_compiled_batch", gen)
    assert vp.run(reqs, secs, {}, vlm=FakeVLM(), candidates=2, model_key="m", greyscale=False) == []
    assert gen.calls == [] and reqs[0].out_path.read_text() == "bad"


def test_rows_are_written_for_audit_and_summarised(tmp_path, monkeypatch) -> None:
    reqs, secs = _requests(tmp_path, 1)
    monkeypatch.setattr(vp, "generate_compiled_batch", fake_generate({1: "good"}))
    rows = vp.run(reqs, secs, {reqs[0].out_path: EXPECT}, vlm=FakeVLM(), candidates=2, model_key="m", greyscale=False)
    out = tmp_path / "vision_check.jsonl"
    qa.write_rows(out, rows)
    assert json.loads(out.read_text().splitlines()[0])["panel"] == "p0.png"
    assert qa.summarise(rows)["rescued"] == 1


def test_choose_vlm_is_off_with_a_clear_message_when_nothing_is_installed(monkeypatch, caplog) -> None:
    monkeypatch.setattr(qa.OllamaVLM, "installed", staticmethod(lambda host=None: ["gemma2:9b"]))
    with caplog.at_level("WARNING"):
        assert vp.choose_vlm(vision_model="", candidates=0) is None
    assert "ollama pull" in caplog.text
    # explicitly one candidate: nothing to choose between, no message and no model needed
    caplog.clear()
    assert vp.choose_vlm(vision_model="", candidates=1) is None and "ollama pull" not in caplog.text


def test_a_stub_run_never_uses_an_installed_vision_model(monkeypatch) -> None:
    from echotales.pipeline.config import get_settings
    from echotales.pipeline.render import panels

    def boom(**kw):
        raise AssertionError("looked for a vision model in a stub run")

    # The guard reads `model_backend`, not `llm_mode`: a developer's `.env` with ECHOTALES_MODEL_BACKEND=ollama would
    # otherwise make this a real run. Pin both, plus the candidate count. The cached settings are reloaded after the
    # env is restored, so nothing leaks into later tests.
    monkeypatch.setenv("ECHOTALES_LLM_MODE", "stub")
    monkeypatch.setenv("ECHOTALES_MODEL_BACKEND", "stub")
    monkeypatch.setenv("ECHOTALES_RENDER_CANDIDATES", "0")
    get_settings(reload=True)
    try:
        monkeypatch.setattr(vp, "choose_vlm", boom)
        rows = panels._vision_check([], {Path("x.png"): EXPECT}, [])
        assert [r.get("skipped") for r in rows] == [True]  # recorded as not checked (4.187), no model looked
    finally:
        monkeypatch.undo()
        get_settings(reload=True)


def test_choose_vlm_returns_the_model_and_default_two_candidates(monkeypatch) -> None:
    monkeypatch.setattr(qa.OllamaVLM, "installed", staticmethod(lambda host=None: ["gemma2:9b", "granite3.2-vision:2b"]))
    vlm = vp.choose_vlm(vision_model="", candidates=0)
    assert vlm is not None and vlm.model == "granite3.2-vision:2b"
    assert vp.candidates_for(0, vlm) == 2 and vp.candidates_for(3, vlm) == 3 and vp.candidates_for(0, None) == 1


def _audit_store(tmp_path):
    from echotales.core.store import Store

    store = Store(str(tmp_path / "a.db"))
    store.add_novel("test", "T", "t.epub", "generic")
    store.conn.commit()
    return store


def test_audit_reports_the_vision_pass_rate_and_regenerations(tmp_path, monkeypatch) -> None:
    from echotales.pipeline import flow, paths

    d = tmp_path / "panels" / "ch1" / "v3_x"
    d.mkdir(parents=True)
    (d / "panel_plan.jsonl").write_text("{}\n")
    qa.write_rows(d / "vision_check.jsonl", [
        {"panel": "a", "candidates": 2, "chosen": 0, "passed": True, "first_passed": True, "unchecked": False, "failed": []},
        {"panel": "b", "candidates": 2, "chosen": 1, "passed": True, "first_passed": False, "unchecked": False, "failed": []},
        {"panel": "c", "candidates": 2, "chosen": 0, "passed": False, "first_passed": False, "unchecked": False, "failed": ["hair"]},
    ])
    monkeypatch.setattr(paths, "asset_dir", lambda novel_id, kind: tmp_path / kind)
    res = flow._find(flow.Stage.DIRECTOR, "director.vision").fn(_audit_store(tmp_path), "test", None)
    assert res.stats["panels_checked"] == 3 and res.stats["rescued"] == 1 and res.stats["extra_images"] == 3
    assert res.stats["first_pass_rate"] == round(1 / 3, 3) and res.stats["final_pass_rate"] == round(2 / 3, 3)
    assert res.count_in == 3 and res.count_out == 2 and any("hair" in w for w in res.warnings)


def test_audit_says_the_check_was_off_when_nothing_was_checked(tmp_path, monkeypatch) -> None:
    from echotales.pipeline import flow, paths

    (tmp_path / "panels" / "ch1" / "v1_x").mkdir(parents=True)
    (tmp_path / "panels" / "ch1" / "v1_x" / "panel_plan.jsonl").write_text("{}\n")
    monkeypatch.setattr(paths, "asset_dir", lambda novel_id, kind: tmp_path / kind)
    res = flow._find(flow.Stage.DIRECTOR, "director.vision").fn(_audit_store(tmp_path), "test", None)
    assert res.status is flow.Status.SKIPPED and "ollama pull" in res.skipped_reason


def test_the_image_worker_is_released_before_the_vision_model_looks(tmp_path, monkeypatch) -> None:
    reqs, secs = _requests(tmp_path, 1)
    events: list[str] = []
    monkeypatch.setattr(vp, "generate_compiled_batch", fake_generate({1: "good"}))
    monkeypatch.setattr(vp, "release_worker", lambda key: events.append("release"))

    class Spy(FakeVLM):
        def look(self, path):
            events.append("look")
            return super().look(path)

    vp.run(reqs, secs, {reqs[0].out_path: EXPECT}, vlm=Spy(), candidates=2, model_key="m", greyscale=False)
    assert events[0] == "release" and "look" in events
