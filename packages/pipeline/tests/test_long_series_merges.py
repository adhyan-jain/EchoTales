"""An alias merge a reviewer makes once must survive a re-run of resolve.

Translations name one person differently ("Fang Yuan" / "Wang Ju Chi"); the reviewer merges them once. The
corrections log marks a correction applied and never replays it, so a re-resolve that wipes every target left the
log saying "merged" while the mentions pointed at two entities again.
"""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.corrections import Correction, CorrectionLog, CorrectionType, apply_pending
from echotales.pipeline.resolve import resolve_novel


def _mention(mid: str, text: str, offset: int) -> Mention:
    return Mention(
        id=mid, novel_id="t", segment_id="s", chapter=1.0, offset=offset, text=text, alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT, block_index=0,
        local_group_id=mid, entity_label="character",
    )


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="1.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text="filler " * 10)]))
    store.add_mentions([_mention("m1", "Fang Yuan", 0), _mention("m2", "Wang Ju Chi", 20)])
    store.conn.commit()
    return store


def _targets(store: Store) -> dict[str, str | None]:
    return {m.id: m.target_id for m in store.get_mentions("t")}


def test_a_merge_survives_a_rerun_of_resolve(tmp_path) -> None:
    store = _store()
    log = CorrectionLog(tmp_path / "t.jsonl")
    resolve_novel("t", store, corrections_log=log)
    before = _targets(store)
    assert before["m1"] != before["m2"]

    log.add(Correction(novel_id="t", type=CorrectionType.MERGE_ENTITIES,
                       payload={"from_id": before["m2"], "into_id": before["m1"]}))
    apply_pending(store, log)
    assert _targets(store)["m2"] == before["m1"]

    resolve_novel("t", store, corrections_log=log)
    after = _targets(store)
    assert after["m1"] == after["m2"]
