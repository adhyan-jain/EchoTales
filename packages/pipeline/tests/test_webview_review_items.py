"""A reviewer can act on a `resolve_deferred` item over HTTP: the decision becomes pending corrections, and the
graph changes only when Apply is pressed (the project's one model for human decisions).

The item is produced by a real `resolve_novel` run with the gate stubbed to defer, so the test exercises the
payload the resolver actually writes, not a hand-built look-alike.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest
from echotales.core.enums import Decision, Provenance, TargetKind
from echotales.core.models import Candidate, DiscoursePosition, ReviewItem, Self
from echotales.core.store import Store
from echotales.pipeline import flow
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.resolve import resolve_novel
from echotales.pipeline.resolve import runner as runner_mod
from echotales.pipeline.resolve.gate import GateDecision
from echotales.pipeline.resolve.runner import GlobalResolver
from echotales.pipeline.webview_server import NovelSource, Registry, make_handler
from test_resolve_review_items import _mention, _store

CANDS = [
    Candidate(target_kind=TargetKind.SELF, target_id=f"t:self:{i}", label=f"Cand{i}", retrieval_score=0.5, probability=p)
    for i, p in enumerate((0.30, 0.10))
]


def _defer_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    r = GlobalResolver("t", Store(":memory:"))
    monkeypatch.setattr(type(r.retriever), "retrieve", lambda self, surface, context: [c.model_copy() for c in CANDS])
    monkeypatch.setattr(runner_mod, "score_evidence", lambda *a, **k: CANDS[0].evidence)
    monkeypatch.setattr(type(r.model), "score_candidates", lambda self, cs: cs)
    monkeypatch.setattr(
        type(r.gate), "decide", lambda self, cs: GateDecision(Decision.DEFER, CANDS[0], "p=0.300 in deferred band")
    )
    monkeypatch.setattr(GlobalResolver, "_bind_alias", lambda *a, **k: None)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _defer_everything(monkeypatch)
    db = tmp_path / "t.db"
    seed = Store(str(db))
    mem = _store(_mention("m1", "g1"), _mention("m2", "g1"), _mention("m3", "g2", text="Other"))
    seed.add_novel("t", "T", "x.epub", "generic")
    for ch in mem.iter_chapters("t"):
        seed.add_chapter(ch)
    seed.add_mentions(mem.get_mentions("t"))
    seed.conn.commit()
    resolve_novel("t", seed)
    seed.close()

    registry = Registry([NovelSource(novel_id="t", label="T", db_path=db)], corrections_dir=tmp_path / "corrections")
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, JobQueue()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]

    def call(method: str, path: str, body: dict | None = None):
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request(method, path, body=json.dumps(body) if body is not None else b"",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, (json.loads(data) if data else None)

    try:
        yield call, db, tmp_path / "corrections" / "t.jsonl"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2.0)


def _items(call, qs: str = ""):
    status, body = call("GET", f"/api/novels/t/review-items{qs}")
    assert status == 200
    return body


def _item(call, surface: str = "Zorrin") -> dict:
    return next(i for i in _items(call)["items"] if surface in i["candidates"][0]["surfaces"])


def _path(item: dict, verb: str) -> str:
    return f"/api/novels/t/review-items/{quote(item['id'], safe='')}/{verb}"


def _targets(db: Path) -> dict[str, tuple[str | None, Provenance]]:
    s = Store(str(db))
    try:
        return {m.id: (m.target_id, m.provenance) for m in s.get_mentions("t")}
    finally:
        s.close()


def _audit(db: Path, log: Path, check) -> flow.CheckResult:
    s = Store(str(db))
    flow._corrections_path.set(str(log))
    try:
        return check(s, "t", None)
    finally:
        flow._corrections_path.set(None)
        s.close()


def test_get_parses_candidates_filters_and_counts(env) -> None:
    call, _, _ = env
    body = _items(call)
    assert body["total"] == 2 and body["open"] == 2
    item = _item(call)
    assert isinstance(item["candidates"], list) and item["candidates"][0]["role"] == "group"
    assert [c["label"] for c in item["candidates"][1:]] == ["Cand0", "Cand1"]
    assert item["decision_state"] == "open"
    assert _items(call, "?kind=nothing") == {"items": [], "total": 0, "open": 0}
    assert len(_items(call, "?kind=resolve_deferred&open=1")["items"]) == 2


def test_unknown_item_is_404_not_found(env) -> None:
    call, _, _ = env
    status, body = call("POST", "/api/novels/t/review-items/nope/resolve", {"action": "dismiss"})
    assert status == 404 and body["code"] == "NOT_FOUND"
    assert call("POST", "/api/novels/t/review-items/nope/reopen", {})[0] == 404


def test_link_makes_one_pending_correction_per_mention_and_apply_links_them(env) -> None:
    call, db, log = env
    s = Store(str(db))
    s.add_self(Self(id="t:self:0", novel_id="t", canonical_label="Cand0", first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    s.conn.commit()
    s.close()
    item = _item(call)
    status, body = call("POST", _path(item, "resolve"), {"action": "link", "target_id": "t:self:0"})
    assert status == 200 and len(body["correction_ids"]) == 2
    assert body["item"]["decision_state"] == "decided_pending_apply" and body["item"]["resolution"] == "human:link:t:self:0"
    assert body["summary"]["pending"] == 2
    assert _targets(db)["m1"][0] is None  # nothing changes before Apply
    assert _items(call)["open"] == 1

    assert call("POST", _path(item, "resolve"), {"action": "dismiss"})[0] == 409
    assert call("POST", "/api/novels/t/apply")[0] == 200
    t = _targets(db)
    assert t["m1"] == ("t:self:0", Provenance.HUMAN_AUTHORED) and t["m2"] == ("t:self:0", Provenance.HUMAN_AUTHORED)
    assert _item(call)["decision_state"] == "applied"
    assert _audit(db, log, flow.check_resolve_corrections).status is flow.Status.PASS
    # m3 is still unlinked, accounted for by its own open item.
    assert _audit(db, log, flow.check_resolve_outcome).status is flow.Status.PASS


def test_link_target_must_be_a_candidate_or_a_character(env) -> None:
    call, _, _ = env
    item = _item(call)
    assert call("POST", _path(item, "resolve"), {"action": "link", "target_id": "t:self:ghost"})[0] == 400
    assert call("POST", _path(item, "resolve"), {"action": "link"})[0] == 400
    assert call("POST", _path(item, "resolve"), {"action": "wat"})[0] == 400
    assert _item(call)["decision_state"] == "open"


def test_new_puts_every_mention_on_one_new_character(env) -> None:
    call, db, log = env
    item = _item(call)
    status, body = call("POST", _path(item, "resolve"), {"action": "new", "label": "Zorrin Vale"})
    assert status == 200 and body["item"]["resolution"] == "human:new:Zorrin Vale"
    call("POST", "/api/novels/t/apply")
    t = _targets(db)
    assert t["m1"][0] == t["m2"][0] and t["m1"][0].startswith("t:manual:")
    s = Store(str(db))
    try:
        manual = [e for e in s.all_selves("t") if e.id.startswith("t:manual:")]
        assert [e.canonical_label for e in manual] == ["Zorrin Vale"]
    finally:
        s.close()
    assert _audit(db, log, flow.check_resolve_corrections).status is flow.Status.PASS


def test_new_name_defaults_to_the_longest_surface(env) -> None:
    call, _, _ = env
    status, body = call("POST", _path(_item(call), "resolve"), {"action": "new"})
    assert status == 200 and body["item"]["resolution"] == "human:new:Zorrin"


def test_dismiss_creates_no_correction(env) -> None:
    call, db, _ = env
    status, body = call("POST", _path(_item(call), "resolve"), {"action": "dismiss", "note": "a place"})
    assert status == 200 and body["correction_ids"] == [] and body["item"]["decision_state"] == "dismissed"
    assert call("GET", "/api/novels/t/corrections")[1]["summary"]["total"] == 0
    assert _targets(db)["m1"][0] is None


def test_reopen_removes_pending_corrections_and_reopens(env) -> None:
    call, _, _ = env
    item = _item(call)
    call("POST", _path(item, "resolve"), {"action": "new"})
    status, body = call("POST", _path(item, "reopen"), {})
    assert status == 200 and len(body["removed"]) == 2 and body["summary"]["total"] == 0
    assert body["item"]["decision_state"] == "open" and not body["item"]["resolved"]
    assert call("POST", _path(item, "reopen"), {})[0] == 409  # nothing left to undo
    assert call("POST", _path(item, "resolve"), {"action": "dismiss"})[0] == 200  # and it can be decided again


def test_deleting_one_pending_correction_does_not_leave_a_phantom_decision(env) -> None:
    call, _, _ = env
    item = _item(call)
    _, body = call("POST", _path(item, "resolve"), {"action": "new"})
    assert call("DELETE", f"/api/novels/t/corrections/{body['correction_ids'][1]}")[0] == 200
    assert _item(call)["decision_state"] == "open"
    assert call("POST", _path(item, "reopen"), {})[0] == 200
    assert call("GET", "/api/novels/t/corrections")[1]["summary"]["total"] == 0


def test_reopen_after_apply_is_refused(env) -> None:
    call, db, _ = env
    item = _item(call)
    call("POST", _path(item, "resolve"), {"action": "new"})
    call("POST", "/api/novels/t/apply")
    status, body = call("POST", _path(item, "reopen"), {})
    assert status == 409 and body["code"] == "APPLIED_CORRECTION"
    assert _targets(db)["m1"][0].startswith("t:manual:")


def test_rerun_after_an_applied_decision_keeps_the_item_and_the_human_links(env) -> None:
    call, db, _ = env
    call("POST", _path(_item(call), "resolve"), {"action": "new", "label": "Zorrin Vale"})
    call("POST", "/api/novels/t/apply")
    before = _targets(db)

    s = Store(str(db))
    try:
        resolve_novel("t", s)
    finally:
        s.close()

    after = _item(call)
    assert after["decision_state"] == "applied" and after["resolution"] == "human:new:Zorrin Vale"
    now = _targets(db)
    assert now["m1"] == before["m1"] and now["m2"] == before["m2"]
    assert now["m1"][1] is Provenance.HUMAN_AUTHORED


def test_other_kinds_keep_the_plain_resolve_with_an_existence_check(env) -> None:
    call, db, _ = env
    s = Store(str(db))
    s.add_review_item(ReviewItem(id="bible:1", novel_id="t", chapter=1.0, kind="bible", message="m", candidates=[{"x": 1}]))
    s.close()
    status, body = call("POST", "/api/novels/t/review-items/bible:1/resolve", {"resolution": "ok"})
    assert status == 200 and body["resolution"] == "ok"
    assert call("POST", "/api/novels/t/review-items/bible:1/resolve", {"resolution": "ok"})[0] == 409
