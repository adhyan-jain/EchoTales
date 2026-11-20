"""A character merged away by a reviewer says so in the cast payload (2026-11 Studio walkthrough, EVOLUTION 4.178).

The merged-away entity stayed in the Cast list with its own dossier after the MERGE correction was applied. The row is
kept (the dossier route and any saved link keep working) but carries `merged_into`, which the Studio uses to hide it
from the list and to say "merged into X" on its page."""

from __future__ import annotations

from echotales.core.models import DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.corrections import Correction, CorrectionLog, CorrectionType, apply_pending
from echotales.pipeline.webview import build_character_dashboard


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    for sid, label in (("t:self1", "Elizabeth"), ("t:self2", "Lizzy")):
        store.add_self(Self(id=sid, novel_id="t", canonical_label=label,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.conn.commit()
    return store


def test_a_merged_away_character_is_marked_with_who_it_was_merged_into(tmp_path) -> None:
    store = _store()
    log = CorrectionLog(tmp_path / "t.jsonl")
    log.add(Correction(novel_id="t", type=CorrectionType.MERGE_ENTITIES,
                       payload={"from_id": "t:self2", "into_id": "t:self1"}))
    apply_pending(store, log)

    rows = {r["self_id"]: r for r in build_character_dashboard(store, "t")["characters"]}
    assert rows["t:self2"]["merged_into"] == {"id": "t:self1", "label": "Elizabeth"}
    assert rows["t:self1"]["merged_into"] is None


def test_an_unmerged_cast_has_no_marker() -> None:
    rows = build_character_dashboard(_store(), "t")["characters"]
    assert all(r["merged_into"] is None for r in rows)
