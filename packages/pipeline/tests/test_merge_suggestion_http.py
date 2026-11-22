"""A reviewer acts on a `merge_suggestion` over HTTP: `merge` queues a merge_entities correction, which changes the
graph only when Apply is pressed; nothing is merged on the suggestion's own account (non-negotiable 9)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from echotales.core.models import DiscoursePosition, ReviewItem, Self
from echotales.core.store import Store
from test_webview_review_items import env  # noqa: F401  (the fixture)

ITEM = "merge_suggestion:t:diminutive:t:self:lizzy:t:self:eliz"


def _seed(db: Path) -> None:
    s = Store(str(db))
    for sid, label in (("t:self:lizzy", "Lizzy"), ("t:self:eliz", "Elizabeth")):
        s.add_self(Self(id=sid, novel_id="t", canonical_label=label, first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    s.add_review_item(ReviewItem(
        id=ITEM, novel_id="t", chapter=0.0, kind="merge_suggestion",
        message="'Lizzy' may be the same person as 'Elizabeth'",
        candidates=[
            {"role": "group", "from_id": "t:self:lizzy", "from_label": "Lizzy", "cue": "diminutive", "evidence_hash": "h"},
            {"role": "candidate", "target_id": "t:self:eliz", "label": "Elizabeth", "reason": "short form"},
        ],
    ))
    s.conn.commit()
    s.close()


def _merged(db: Path) -> dict[str, str]:
    s = Store(str(db))
    try:
        return s.merged_into("t")
    finally:
        s.close()


def test_merge_waits_for_apply(env) -> None:  # noqa: F811
    call, db, _ = env
    _seed(db)
    path = f"/api/novels/t/review-items/{quote(ITEM, safe='')}/resolve"
    assert call("POST", path, {"action": "merge", "into_id": "t:self:someone-else"})[0] == 400
    status, body = call("POST", path, {"action": "merge", "into_id": "t:self:eliz"})
    assert status == 200 and len(body["correction_ids"]) == 1
    assert body["item"]["decision_state"] == "decided_pending_apply"
    assert _merged(db) == {}
    assert call("POST", "/api/novels/t/apply")[0] == 200
    assert _merged(db) == {"t:self:lizzy": "t:self:eliz"}


def test_dismiss_changes_nothing(env) -> None:  # noqa: F811
    call, db, _ = env
    _seed(db)
    status, body = call("POST", f"/api/novels/t/review-items/{quote(ITEM, safe='')}/resolve", {"action": "dismiss"})
    assert status == 200 and body["correction_ids"] == []
    assert _merged(db) == {}
