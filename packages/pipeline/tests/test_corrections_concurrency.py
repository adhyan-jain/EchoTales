"""CorrectionLog must stay correct with several writers on one file, and
reviewer mention edits must carry a human marker."""

from __future__ import annotations

import json
import multiprocessing
import threading

import pytest
from echotales.core.enums import (
    AliasType,
    AttributionMethod,
    BlockType,
    Provenance,
    ReferenceMode,
    ResolutionMethod,
    SpanType,
    TargetKind,
)
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline import corrections as corrections_mod
from echotales.pipeline.corrections import (
    AppliedCorrectionError,
    Correction,
    CorrectionLog,
    CorrectionType,
    apply_pending,
)


def _flag(note: str = "x") -> Correction:
    return Correction(novel_id="t", type=CorrectionType.FLAG, payload={"note": note})


def _records(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _store() -> Store:
    text = '"Old bastard Fang, stop."'
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
        )
    )
    store.add_spans(
        [
            Span(
                id="t:1:0:0",
                novel_id="t",
                chapter=1.0,
                block_index=0,
                start=0,
                end=len(text),
                span_type=SpanType.DIALOGUE,
                text=text,
                attribution_method=AttributionMethod.UNRESOLVED,
            )
        ]
    )
    for n in (1, 2):
        store.add_self(
            Self(
                id=f"t:self{n}",
                novel_id="t",
                canonical_label=f"Person {n}",
                first_attested_pos=DiscoursePosition(chapter=1, offset=0),
            )
        )
    store.conn.commit()
    return store


class TestInterleavedInstances:
    def test_add_from_a_stale_instance_keeps_the_others_records(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        server, job = CorrectionLog(path), CorrectionLog(path)
        a, b = _flag("a"), _flag("b")
        server.add(a)
        job.add(b)  # `job` loaded before `a` existed
        assert {r["id"] for r in _records(path)} == {a.id, b.id}
        assert len(server) == 2

    def test_stale_instance_cannot_reset_applied(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        a = Correction(novel_id="t", type=CorrectionType.MERGE_LINES, payload={})
        CorrectionLog(path).add(a)
        stale, fresh = CorrectionLog(path), CorrectionLog(path)
        fresh.mark_applied(a.id)
        stale.add(_flag())
        by_id = {r["id"]: r for r in _records(path)}
        assert by_id[a.id]["applied"] is True

    def test_remove_does_not_resurrect_or_drop_others(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        one, two = CorrectionLog(path), CorrectionLog(path)
        a, b = _flag("a"), _flag("b")
        one.add(a)
        two.add(b)
        one.remove(a.id)  # `one` never saw `b`
        two.remove("nope")
        assert [r["id"] for r in _records(path)] == [b.id]

    def test_summary_sees_another_instances_records(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        one, two = CorrectionLog(path), CorrectionLog(path)
        two.add(_flag())
        assert one.summary()["total"] == 1
        assert len(list(one)) == 1


def test_threads_with_own_instances_lose_nothing(tmp_path) -> None:
    path = tmp_path / "t.jsonl"
    threads_n, per = 8, 15

    def work() -> None:
        log = CorrectionLog(path)
        for _ in range(per):
            log.add(_flag())

    threads = [threading.Thread(target=work) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ids = [r["id"] for r in _records(path)]
    assert len(ids) == threads_n * per == len(set(ids))


def _proc_work(path: str, n: int) -> None:
    log = CorrectionLog(path)
    for _ in range(n):
        log.add(_flag())


def test_processes_lose_nothing(tmp_path) -> None:
    path = tmp_path / "t.jsonl"
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_proc_work, args=(str(path), 10)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    assert all(p.exitcode == 0 for p in procs)
    assert len(_records(path)) == 40


def test_flush_leaves_no_temp_files(tmp_path) -> None:
    CorrectionLog(tmp_path / "t.jsonl").add(_flag())
    assert not list(tmp_path.glob("*.tmp"))


class TestRemoveAppliedRecord:
    def test_refuses_and_leaves_file_untouched(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        log = CorrectionLog(path)
        c = Correction(novel_id="t", type=CorrectionType.MERGE_LINES, payload={})
        log.add(c)
        log.mark_applied(c.id)
        before = path.read_bytes()
        with pytest.raises(AppliedCorrectionError):
            log.remove(c.id)
        assert path.read_bytes() == before

    def test_refuses_via_a_stale_instance(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        stale = CorrectionLog(path)
        c = Correction(novel_id="t", type=CorrectionType.MERGE_LINES, payload={})
        stale.add(c)
        CorrectionLog(path).mark_applied(c.id)
        with pytest.raises(AppliedCorrectionError):
            stale.remove(c.id)

    def test_pending_and_flags_still_removable(self, tmp_path) -> None:
        log = CorrectionLog(tmp_path / "t.jsonl")
        f = _flag()
        log.add(f)
        assert log.remove(f.id) is True
        assert log.remove(f.id) is False


def test_two_applies_in_the_same_millisecond_get_distinct_events(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(corrections_mod.time, "time", lambda: 1_700_000_000.0)
    store = _store()
    log = CorrectionLog(tmp_path / "t.jsonl")
    for _ in range(2):
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.REASSIGN_SPEAKER,
                payload={"span_id": "t:1:0:0", "chapter": 1.0, "speaker_id": "t:self1"},
            )
        )
        assert apply_pending(store, log)["count"] == 1
    seqs = [r["seq"] for r in store.conn.execute("SELECT seq FROM resolution_event")]
    assert len(seqs) == 2 == len(set(seqs))


class TestMentionEditsAreHuman:
    def _mention(self) -> Mention:
        return Mention(
            id="t:m1",
            novel_id="t",
            segment_id="",
            chapter=1.0,
            offset=0,
            text="Fang",
            alias_type=AliasType.RIGID_NAME,
            span_type=SpanType.DIALOGUE,
            reference_mode=ReferenceMode.DIALOGUE_REFERENCE,
            target_kind=TargetKind.SELF,
            target_id="t:self1",
            method=ResolutionMethod.SCORED,
            provenance=Provenance.MACHINE,
        )

    def test_reassign_mention(self, tmp_path) -> None:
        store = _store()
        store.add_mentions([self._mention()])
        log = CorrectionLog(tmp_path / "t.jsonl")
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.REASSIGN_MENTION,
                payload={"mention_id": "t:m1", "target_id": "t:self2"},
            )
        )
        assert apply_pending(store, log)["count"] == 1
        m = store.get_mentions("t", 1.0)[0]
        assert (m.target_id, m.method, m.provenance) == (
            "t:self2",
            ResolutionMethod.MANUAL,
            Provenance.HUMAN_AUTHORED,
        )

    def test_create_mention(self, tmp_path) -> None:
        store = _store()
        log = CorrectionLog(tmp_path / "t.jsonl")
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.CREATE_MENTION,
                payload={
                    "span_id": "t:1:0:0",
                    "chapter": 1.0,
                    "local_start": 1,
                    "local_end": 4,
                    "target_id": "t:self1",
                },
            )
        )
        assert apply_pending(store, log)["count"] == 1
        m = store.get_mentions("t", 1.0)[0]
        assert (m.method, m.provenance) == (ResolutionMethod.MANUAL, Provenance.HUMAN_AUTHORED)
