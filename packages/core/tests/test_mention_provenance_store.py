"""The mention provenance columns (D69): round trip, and an older database opening with NULLs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from echotales.core.enums import AliasType, ReferenceMode, SpanType
from echotales.core.models import Mention
from echotales.core.store import Store


def _mention(id: str = "n:1:m0", **extra: object) -> Mention:
    return Mention(
        id=id, novel_id="n", segment_id="n:1:main0", chapter=1, offset=4, text="Fang Yuan",
        alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT, **extra,
    )  # type: ignore[arg-type]


def test_provenance_round_trips() -> None:
    store = Store(":memory:")
    store.add_mentions([
        _mention(
            end_offset=13, search_key="fang yuan", detector="hybrid", model_id="urchade/gliner_medium-v2.1",
            model_version="abc123", ner_score=0.83, evidence_json='{"route": "accept"}',
        )
    ])
    (got,) = store.get_mentions("n")
    assert (got.end_offset, got.search_key, got.detector) == (13, "fang yuan", "hybrid")
    assert (got.model_id, got.model_version, got.ner_score) == ("urchade/gliner_medium-v2.1", "abc123", 0.83)
    assert got.evidence_json == '{"route": "accept"}'


def test_unrecorded_provenance_is_none() -> None:
    store = Store(":memory:")
    store.add_mentions([_mention()])
    (got,) = store.get_mentions("n")
    assert got.end_offset is None and got.detector is None and got.ner_score is None


def test_a_database_from_before_the_columns_opens_and_reads_null(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    # The mention table exactly as it was before D69 (through `entity_label`).
    old.executescript(
        """
        CREATE TABLE mention (
            id TEXT PRIMARY KEY, novel_id TEXT NOT NULL, segment_id TEXT NOT NULL, chapter REAL NOT NULL,
            offset INTEGER NOT NULL, text TEXT NOT NULL, alias_type TEXT NOT NULL, span_type TEXT NOT NULL,
            reference_mode TEXT NOT NULL, speaker_self_id TEXT, target_kind TEXT, target_id TEXT,
            local_group_id TEXT, confidence REAL NOT NULL DEFAULT 1.0, method TEXT,
            provenance TEXT NOT NULL DEFAULT 'MACHINE', block_index INTEGER NOT NULL DEFAULT 0, entity_label TEXT
        );
        """
    )
    old.execute(
        "INSERT INTO mention(id, novel_id, segment_id, chapter, offset, text, alias_type, span_type, reference_mode)"
        " VALUES ('n:1:m0','n','s',1,0,'Fang Yuan',?,?,?)",
        (AliasType.RIGID_NAME.value, SpanType.NARRATION_ACTION.value, ReferenceMode.PRESENT.value),
    )
    old.commit()
    old.close()

    store = Store(path)
    (got,) = store.get_mentions("n")
    assert got.text == "Fang Yuan" and got.detector is None and got.evidence_json is None
    # and the migrated table accepts a new-style row
    store.add_mentions([_mention("n:1:m1", detector="hybrid", ner_score=0.5)])
    assert {m.id: m.detector for m in store.get_mentions("n")} == {"n:1:m0": None, "n:1:m1": "hybrid"}
    store.conn.commit()
    Store(path)  # reopening is idempotent
