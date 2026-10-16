"""The Research page's backend: stored-result summary, demo items, and the live local-model probe.

No test here talks to ollama: `research_demo._http_json` (the module's only network call) is replaced. What is pinned:

- the allow-list: only the five local models can ever be called, so no paid API is reachable from this route;
- error messages tell a person what to do (build the items, start ollama, pull the model);
- summary() reads only stored files, survives a missing one, and never emits NaN (invalid JSON in a browser);
- letter correctness: an answer is "premature" only when it equals the true-identity letter, UNDETERMINED is the
  correct first-reader answer, and any other letter is `other`;
- resource rules: model unloaded after the last arm even on failure, a CPU-offloaded model is refused, a RAM-starved
  machine is refused.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.pipeline import research_demo as R
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.webview_server import Registry, make_handler

REPO = Path(__file__).resolve().parents[3]


def _item(item_id: str = "XX-pre001", true_letter: str = "C") -> dict:
    names = {"A": ["Ann", "Bo", "Cy"], "B": ["Qk", "Zr", "Vm"], "B3": ["Dora", "Eli", "Finn"]}
    cands = {arm: [{"letter": L, "name": n} for L, n in zip("ABC", ns)] for arm, ns in names.items()}
    return dict(
        id=item_id, event="XX", dataset="pd_v3", gutenberg=1, book="A Test Book", surface={"A": "the stranger", "B": "the stranger", "B3": "the stranger"},
        window="a [[stranger]] arrived", windows={a: "a [[stranger]] arrived" for a in R.ARMS},
        prompts={a: f"PROMPT-{a}" for a in R.ARMS}, candidates=cands, true_letter=true_letter, true_identity="Cy",
        reveal_note="Fixed reveal: ...", distance_chars_to_cutoff=1234, stored_runs=dict(models=5, A=4, B=0, B3=0),
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    f = tmp_path / R.ITEMS_REL
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(dict(items=[_item(), _item("XX-pre002", "A")], label_provenance="x", selection="y")))
    return tmp_path


class FakeOllama:
    """Records every call; `answers` maps a prompt marker to the JSON answer for that arm."""

    def __init__(self, answers: dict[str, str], ps_models: list[dict] | None = None, fail_on: str | None = None):
        self.answers, self.calls, self.fail_on = answers, [], fail_on
        self.ps_models = ps_models if ps_models is not None else [{"name": "qwen2.5:7b", "size": 10, "size_vram": 10}]

    def __call__(self, method, url, payload=None, timeout=240.0):
        self.calls.append((method, url, payload))
        if url.endswith("/api/chat"):
            prompt = payload["messages"][0]["content"]
            if self.fail_on and self.fail_on in prompt:
                raise R.ResearchDemoError("ollama exploded", 502)
            ans = self.answers[prompt.removeprefix("PROMPT-")]
            return {"message": {"content": json.dumps({"answer": ans})}, "load_duration": 2_000_000_000}
        if url.endswith("/api/ps"):
            return {"models": self.ps_models}
        return {}


@pytest.fixture(autouse=True)
def plenty_of_ram(monkeypatch):
    monkeypatch.setattr(R, "_mem_available_gib", lambda: 8.0)


# ---------------------------------------------------------------- allow-list
def test_only_the_five_local_models_are_allowed():
    assert set(R.ALLOWED_MODELS) == {"qwen2.5:7b", "llama3.1:8b", "mistral:7b-instruct", "phi4-mini:latest", "gemma2:9b"}
    for bad in ("gpt-5.6-luna", "gpt-4o", "claude-sonnet-5-5", "gemma3:12b", "", "qwen2.5:7b; rm -rf"):
        with pytest.raises(R.ResearchDemoError) as e:
            R.normalize_model(bad)
        assert e.value.status == 400
        assert "not allowed" in str(e.value) and "qwen2.5:7b" in str(e.value)
    assert R.normalize_model("phi4-mini") == "phi4-mini:latest"


def test_a_disallowed_model_never_reaches_the_network(root, monkeypatch):
    fake = FakeOllama({})
    monkeypatch.setattr(R, "_http_json", fake)
    with pytest.raises(R.ResearchDemoError):
        R.probe("XX-pre001", "gpt-5.6-luna", root=root)
    assert fake.calls == []


# ---------------------------------------------------------------- items and error messages
def test_items_missing_file_says_how_to_build_it(tmp_path):
    with pytest.raises(R.ResearchDemoError) as e:
        R.items(tmp_path)
    assert e.value.status == 404
    assert "build_demo_items.py" in str(e.value)


def test_items_keep_windows_and_candidates_but_not_prompts(root):
    out = R.items(root)
    assert [i["id"] for i in out["items"]] == ["XX-pre001", "XX-pre002"]
    assert "prompts" not in out["items"][0]
    assert out["items"][0]["candidates"]["B3"][0] == {"letter": "A", "name": "Dora"}
    assert out["models"] == list(R.ALLOWED_MODELS)
    assert "no human labels" in out["provenance"]


def test_probe_rejects_unknown_item_and_bad_arms(root, monkeypatch):
    monkeypatch.setattr(R, "_http_json", FakeOllama({}))
    with pytest.raises(R.ResearchDemoError, match="Unknown demo item"):
        R.probe("nope", "qwen2.5:7b", root=root)
    for arms in (["A", "Z"], ["A", "A"]):
        with pytest.raises(R.ResearchDemoError, match="arms must be"):
            R.probe("XX-pre001", "qwen2.5:7b", arms, root=root)


def test_ollama_down_gives_an_actionable_message(root, monkeypatch):
    import urllib.error

    def refuse(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(R.urllib.request, "urlopen", refuse)
    with pytest.raises(R.ResearchDemoError) as e:
        R.probe("XX-pre001", "qwen2.5:7b", ["A"], root=root)
    assert e.value.status == 503 and "ollama serve" in str(e.value)


# ---------------------------------------------------------------- letter-correctness logic
def test_classify_truth_abstain_other_invalid():
    assert R.classify("C", "C") == "true_identity"
    assert R.classify("UNDETERMINED", "C") == "abstain"
    assert R.classify("A", "C") == "other"
    assert R.classify("INVALID", "C") == "invalid"
    assert R.classify("", "C") == "invalid"


def test_probe_reports_answer_latency_and_correctness_per_arm(root, monkeypatch):
    fake = FakeOllama({"A": "C", "B": "UNDETERMINED", "B3": "A"})
    monkeypatch.setattr(R, "_http_json", fake)
    out = R.probe("XX-pre001", "qwen2.5:7b", root=root)
    a, b, b3 = (out["arms"][k] for k in ("A", "B", "B3"))
    assert (a["answer"], a["is_true_identity"], a["outcome"]) == ("C", True, "true_identity")
    assert a["answer_name"] == "Cy"
    assert (b["answer"], b["is_true_identity"], b["outcome"]) == ("UNDETERMINED", False, "abstain")
    assert (b3["answer"], b3["outcome"], b3["answer_name"]) == ("A", "other", "Dora")
    assert all(r["seconds"] >= 0 and r["load_seconds"] == 2.0 for r in out["arms"].values())
    assert out["total_seconds"] >= sum(r["seconds"] for r in out["arms"].values()) - 0.01
    assert out["true_letter"] == "C" and out["model"] == "qwen2.5:7b"
    assert out["verdict"].startswith("Original names: answers the true identity before the book reveals it")
    assert "Letter cipher: abstains" in out["verdict"] and "Cue-preserving pseudonyms: other" in out["verdict"]


def test_probe_asks_with_the_study_decoding_and_a_schema_over_that_arms_letters(root, monkeypatch):
    fake = FakeOllama({"A": "UNDETERMINED", "B": "UNDETERMINED", "B3": "UNDETERMINED"})
    monkeypatch.setattr(R, "_http_json", fake)
    R.probe("XX-pre001", "llama3.1:8b", root=root)
    chats = [c for c in fake.calls if c[1].endswith("/api/chat")]
    assert len(chats) == 3
    for _m, url, p in chats:
        assert url == "http://127.0.0.1:11434/api/chat"
        assert p["stream"] is False and p["model"] == "llama3.1:8b"
        assert p["options"] == {"temperature": 0, "seed": 20261016, "num_predict": 24, "num_ctx": 2048}
        assert p["format"]["properties"]["answer"]["enum"] == ["A", "B", "C", "UNDETERMINED"]


def test_an_answer_outside_the_enum_is_invalid_not_correct(root, monkeypatch):
    monkeypatch.setattr(R, "_http_json", FakeOllama({"A": "Z", "B": "Z", "B3": "Z"}))
    out = R.probe("XX-pre001", "qwen2.5:7b", ["A"], root=root)
    assert out["arms"]["A"]["answer"] == "INVALID" and out["arms"]["A"]["outcome"] == "invalid"
    assert out["arms"]["A"]["is_true_identity"] is False


# ---------------------------------------------------------------- resource rules
def test_model_is_unloaded_after_the_last_arm(root, monkeypatch):
    fake = FakeOllama({"A": "A", "B": "A", "B3": "A"})
    monkeypatch.setattr(R, "_http_json", fake)
    R.probe("XX-pre001", "qwen2.5:7b", root=root)
    last = fake.calls[-1]
    assert last[1].endswith("/api/generate") and last[2]["keep_alive"] == 0 and last[2]["model"] == "qwen2.5:7b"


def test_model_is_unloaded_and_lock_released_when_an_arm_fails(root, monkeypatch):
    fake = FakeOllama({"A": "A", "B": "A", "B3": "A"}, fail_on="PROMPT-B")
    monkeypatch.setattr(R, "_http_json", fake)
    with pytest.raises(R.ResearchDemoError, match="exploded"):
        R.probe("XX-pre001", "qwen2.5:7b", root=root)
    assert fake.calls[-1][2]["keep_alive"] == 0
    monkeypatch.setattr(R, "_http_json", FakeOllama({"A": "A", "B": "A", "B3": "A"}))
    assert R.probe("XX-pre001", "qwen2.5:7b", ["A"], root=root)["arms"]["A"]["answer"] == "A"  # lock was released


def test_cpu_offloaded_model_is_refused_and_unloaded(root, monkeypatch):
    fake = FakeOllama({"A": "A", "B": "A", "B3": "A"}, ps_models=[{"name": "qwen2.5:7b", "size": 10, "size_vram": 6}])
    monkeypatch.setattr(R, "_http_json", fake)
    with pytest.raises(R.ResearchDemoError, match="not fully in GPU memory") as e:
        R.probe("XX-pre001", "qwen2.5:7b", root=root)
    assert e.value.status == 507
    assert len([c for c in fake.calls if c[1].endswith("/api/chat")]) == 1  # stopped after the first arm
    assert fake.calls[-1][2]["keep_alive"] == 0


def test_low_ram_refuses_before_any_call(root, monkeypatch):
    fake = FakeOllama({})
    monkeypatch.setattr(R, "_http_json", fake)
    monkeypatch.setattr(R, "_mem_available_gib", lambda: 0.4)
    with pytest.raises(R.ResearchDemoError, match="RAM"):
        R.probe("XX-pre001", "qwen2.5:7b", root=root)
    assert fake.calls == []


def test_second_concurrent_probe_is_refused(root, monkeypatch):
    monkeypatch.setattr(R, "_http_json", FakeOllama({"A": "A", "B": "A", "B3": "A"}))
    assert R._probe_lock.acquire(blocking=False)
    try:
        with pytest.raises(R.ResearchDemoError) as e:
            R.probe("XX-pre001", "qwen2.5:7b", ["A"], root=root)
        assert e.value.status == 409
    finally:
        R._probe_lock.release()


# ---------------------------------------------------------------- summary
def test_summary_survives_missing_files_and_lists_them(tmp_path):
    s = R.summary(tmp_path)
    assert s["gap_by_model"] is None and s["cue_preserving"] is None and s["dose_response"] is None
    assert len(s["missing"]) == len(R.FILES)
    assert "no human labels" in s["provenance"]


@pytest.mark.skipif(not (REPO / R.EVAL_DIR / R.FILES["pooled"]).exists(), reason="stored study results not present")
def test_summary_shape_from_the_stored_results():
    s = R.summary(REPO)
    assert s["missing"] == []
    json.dumps(s, allow_nan=False)  # NaN in the v6 recovered fractions must not leak through
    h = s["headline"]
    assert h["reference_gap"]["gap"] == pytest.approx(0.2596, abs=1e-4) and h["reference_gap"]["lo"] < h["reference_gap"]["hi"]
    assert h["local_pool_gap"]["gap"] == pytest.approx(0.1151, abs=1e-4) and h["local_pool_gap"]["events"] == 38
    assert h["cue_recovered"]["fraction"] < 1 / 3  # B3 does not recover the gap
    g = s["gap_by_model"]
    assert [d["key"] for d in g["datasets"]] == ["v2", "v3", "v6"]
    models = [r["model"] for r in g["rows"]]
    assert models[0] == "gpt-5.6-luna" and set(models[1:]) == set(R.LOCAL_MODELS)
    assert all({"gap", "lo", "hi"} <= set(c) for r in g["rows"] for c in r["cells"].values())
    pool = next(p for p in s["cue_preserving"]["pools"] if p["models"] != ["gpt-5.6-luna"])
    arms = {a["arm"]: a for a in pool["arms"]}
    assert set(arms) == {"A", "B", "B3"}
    assert arms["A"]["premature"] - arms["B"]["premature"] == pytest.approx(0.1456, abs=2e-3)  # the stored pooled gap
    assert all(0 <= a["control_accuracy"] <= 1 for a in arms.values())
    d = s["dose_response"]["table"]
    assert [r["recognised"] for r in d] == [0, 1, 2, 3, 4, 5] and sum(r["events"] for r in d) == 38
    v = {r["model"]: r for r in s["validity"]["rows"]}
    assert v["qwen2.5:7b"]["cells"]["v2"]["valid"] is False and v["llama3.1:8b"]["cells"]["v2"]["valid"] is True
    assert {x["name"] for x in s["design"]} == {"Lean", "Core", "Wide"}
    assert all(x["a100_usd"] > 0 for x in s["design"])


# ---------------------------------------------------------------- routes
@pytest.fixture
def server(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(R, "default_root", lambda: tmp_path)
    registry = Registry([], corrections_dir=tmp_path / "corrections", projects_dir=tmp_path / "projects")
    queue = JobQueue()
    queue.start()
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, queue))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], tmp_path
    httpd.shutdown()
    httpd.server_close()


def _call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    out = json.loads(resp.read())
    conn.close()
    return resp.status, out


def test_routes_summary_items_and_probe(server, monkeypatch):
    port, tmp = server
    status, out = _call(port, "GET", "/api/research/summary")
    assert status == 200 and out["missing"]  # empty root: every file listed missing, still 200
    status, out = _call(port, "GET", "/api/research/items")
    assert status == 404 and "build_demo_items.py" in out["error"]
    status, out = _call(port, "POST", "/api/research/probe", {"item_id": "x", "model": "gpt-5.6-luna"})
    assert status == 400 and "not allowed" in out["error"]

    f = tmp / R.ITEMS_REL
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(dict(items=[_item()])))
    monkeypatch.setattr(R, "_http_json", FakeOllama({"A": "C", "B": "UNDETERMINED", "B3": "UNDETERMINED"}))
    status, out = _call(port, "GET", "/api/research/items")
    assert status == 200 and out["items"][0]["id"] == "XX-pre001"
    status, out = _call(port, "POST", "/api/research/probe", {"item_id": "XX-pre001", "model": "qwen2.5:7b"})
    assert status == 200 and out["arms"]["A"]["is_true_identity"] is True and out["arms"]["B"]["outcome"] == "abstain"
