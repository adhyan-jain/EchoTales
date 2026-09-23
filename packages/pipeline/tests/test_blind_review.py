"""The blind annotation format (COMPLETION_PLAN Track 2 item 7, EVOLUTION 4.81).

`gold.py`'s structural guard catches a record *drafted* from pipeline output.
It cannot catch a human shown the system's answer beside the text, who agrees
because it is there -- anchoring leaves no trace in the record. The only
defence is not showing it, which makes "the task file contains no system
field" a property worth testing rather than trusting.
"""

from __future__ import annotations

import json

import pytest
from echotales.core.enums import AliasType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.eval.blind_review import (
    FORBIDDEN_TASK_FIELDS,
    BlindTask,
    build_tasks,
    read_answers,
    write_tasks,
)
from echotales.pipeline.eval.gold import MentionKind, Provenance, ReviewDepth


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    s = Store(str(tmp_path / "b.db"))
    s.add_novel("n", "N", "", "")
    for number in (1.0, 2.0):
        s.add_chapter(
            Chapter(
                novel_id="n",
                number=number,
                title=f"C{number:g}",
                source_href=f"c{number:g}.html",
                blocks=[{"index": 0, "block_type": "PROSE",
                         "text": "Fang Yuan walked. " * 40}],
            )
        )
    s.add_mentions(
        [
            Mention(
                id=f"m{i}",
                novel_id="n",
                segment_id="seg",
                chapter=1.0 if i < 3 else 2.0,
                offset=i * 18,
                text="Fang Yuan",
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT,
                block_index=0,
                target_kind=TargetKind.SELF,
                target_id="n:self:fy",
            )
            for i in range(6)
        ]
    )
    s.conn.commit()
    yield s
    s.close()


class TestBlindness:
    def test_a_task_carries_no_system_field(self, store, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = write_tasks(build_tasks(store, "n"), tmp_path / "t.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines():
            assert not (FORBIDDEN_TASK_FIELDS & set(json.loads(line)))

    def test_a_leaking_task_is_refused(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        class Leaky(BlindTask):
            def as_dict(self):  # type: ignore[no-untyped-def]
                row = super().as_dict()
                row["target_id"] = "n:self:fy"
                return row

        task = Leaky("id", "n", 1.0, 0, "Fang Yuan", "window")
        with pytest.raises(ValueError, match="leak"):
            write_tasks([task], tmp_path / "t.jsonl")

    def test_a_prefilled_answer_is_refused(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """A suggested answer anchors the reviewer just as the system's would."""
        class Suggesting(BlindTask):
            def as_dict(self):  # type: ignore[no-untyped-def]
                row = super().as_dict()
                row["identity"] = "Fang Yuan"
                return row

        task = Suggesting("id", "n", 1.0, 0, "Fang Yuan", "window")
        with pytest.raises(ValueError, match="pre-filled"):
            write_tasks([task], tmp_path / "t.jsonl")

    def test_the_answer_slots_ship_empty(self, store, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = write_tasks(build_tasks(store, "n"), tmp_path / "t.jsonl")
        first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        assert first["identity"] == "" and first["not_an_entity"] is False


class TestSampling:
    def test_a_sample_is_drawn_after_shuffling(self, store) -> None:  # type: ignore[no-untyped-def]
        """Early chapters are the easy case -- few entities, no aliases yet.
        Annotating the first N mentions would overstate agreement."""
        chapters = {t.chapter for t in build_tasks(store, "n", sample=4, seed=1)}
        assert len(chapters) > 1

    def test_the_seed_makes_it_reproducible(self, store) -> None:  # type: ignore[no-untyped-def]
        a = [t.task_id for t in build_tasks(store, "n", sample=4, seed=7)]
        b = [t.task_id for t in build_tasks(store, "n", sample=4, seed=7)]
        assert a == b

    def test_chapters_can_be_restricted(self, store) -> None:  # type: ignore[no-untyped-def]
        assert {t.chapter for t in build_tasks(store, "n", chapters=[2.0])} == {2.0}


class TestReadBack:
    def _answered(self, store, tmp_path, rows_mutator):  # type: ignore[no-untyped-def]
        path = write_tasks(build_tasks(store, "n", sample=3, seed=3), tmp_path / "t.jsonl")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows_mutator(rows)
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def test_answers_come_back_as_per_record_confirmed_human_gold(self, store, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = self._answered(store, tmp_path, lambda rows: rows[0].update(identity="Fang Yuan"))
        gold = read_answers(path, novel_id="n", confirmed_by="a-person", store=store)
        assert len(gold.mentions) == 1
        record = gold.mentions[0]
        assert record.confirmed and record.confirmed_by == "a-person"
        assert record.review_depth is ReviewDepth.PER_RECORD
        assert record.provenance is Provenance.HUMAN
        assert record.drafted_by == ""

    def test_a_blank_task_is_skipped_never_counted_as_agreement(self, store, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """The exact failure EVOLUTION 4.74's bulk approval was: a record
        nobody looked at, counted as confirmed."""
        path = self._answered(store, tmp_path, lambda rows: None)
        assert read_answers(path, novel_id="n", confirmed_by="a-person").mentions == []

    def test_a_negative_becomes_a_not_an_entity_record(self, store, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = self._answered(store, tmp_path, lambda rows: rows[0].update(not_an_entity=True))
        record = read_answers(path, novel_id="n", confirmed_by="a-person").mentions[0]
        assert record.kind is MentionKind.NOT_AN_ENTITY
        assert record.identity == ""

    def test_confirmed_by_is_required(self, store, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = self._answered(store, tmp_path, lambda rows: rows[0].update(identity="Fang Yuan"))
        with pytest.raises(ValueError, match="confirmed_by"):
            read_answers(path, novel_id="n", confirmed_by="   ")
