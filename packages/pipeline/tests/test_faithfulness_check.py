"""`echotales faithfulness` (eval/faithfulness.py) and the body-change confirmation it found.

A five-chapter book: Fang Yuan is reborn in chapter 3 and next seen in chapter 5. `find_change_candidates` accepts a
change only once the character is seen after it, so a book cut at chapter 3 or 4 has one body, but the whole-volume
build stamped the second body as learned at chapter 3 -- a reader at chapter 3 was served a fact that needs chapter 5.
LotM's Benson is the real case (ch30 change, next seen ch39). The prefix-causal build stamps the change at its
confirmation and the check passes; the legacy build fails it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    BlockType,
    ReferenceMode,
    SpanType,
    TargetKind,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    Block,
    Chapter,
    DiscoursePosition,
    Mention,
    Self,
    SelfPersonaBinding,
    Span,
)
from echotales.core.state import current_bindings, state_of
from echotales.core.store import Store
from echotales.pipeline.cli import main
from echotales.pipeline.eval.faithfulness import check_reader_faithfulness

TEXT = {
    1: "Fang Yuan looked at Mira.",
    2: "Fang Yuan spoke to Mira.",
    3: "Fang Yuan had been reborn, five hundred years back.",
    4: "Mira waited alone.",
    5: "Fang Yuan returned to Mira.",
}
MENTIONS = [(1, "Fang Yuan", "t:fy"), (1, "Mira", "t:mira"), (2, "Fang Yuan", "t:fy"), (2, "Mira", "t:mira"),
            (3, "Fang Yuan", "t:fy"), (4, "Mira", "t:mira"), (5, "Fang Yuan", "t:fy"), (5, "Mira", "t:mira")]


def _book(path) -> str:
    store = Store(str(path))
    store.add_novel("t", "T", "x.epub", "generic")
    for c, text in TEXT.items():
        store.add_chapter(Chapter(novel_id="t", number=float(c), title="T", source_href=f"{c}.html",
                                  blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)]))
    for sid, label in (("t:fy", "Fang Yuan"), ("t:mira", "Mira")):
        store.add_self(Self(id=sid, novel_id="t", canonical_label=label,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0), kind=TargetKind.SELF))
    store.add_spans([Span(id=f"sp{c}", novel_id="t", chapter=float(c), block_index=0, start=0, end=len(t),
                          span_type=SpanType.NARRATION_ACTION, text=t) for c, t in TEXT.items()])
    store.add_mentions([
        Mention(id=f"m{i}", novel_id="t", segment_id="s", chapter=float(c), offset=TEXT[c].index(t), block_index=0,
                text=t, alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=tid)
        for i, (c, t, tid) in enumerate(MENTIONS)
    ])
    store.conn.commit()
    store.close()
    return str(path)


def test_the_legacy_build_serves_the_second_body_before_it_is_confirmed(tmp_path) -> None:
    report = check_reader_faithfulness(_book(tmp_path / "b.db"), "t", [3, 4], work_dir=tmp_path / "w", prefix_causal=False)
    assert not report.ok
    assert [c.persona_divergent for c in report.cuts] == [[("t:fy", "persona_set")], [("t:fy", "persona_set")]]


def test_the_prefix_causal_build_is_faithful_and_still_splits_the_body(tmp_path) -> None:
    report = check_reader_faithfulness(_book(tmp_path / "b.db"), "t", [1, 2, 3, 4], work_dir=tmp_path / "w")
    assert report.ok, [c.summary() for c in report.cuts]
    full = Store(str(tmp_path / "w" / "full.db"))
    def reader(k):
        return state_of(full, "t", "t:fy", position=k + 0.5, knowledge_pos=DiscoursePosition(chapter=k, offset=10**6))

    assert reader(4).persona_ids == ["t:fy:body1"]  # the change at ch3 is not confirmed yet
    assert reader(5).persona_ids == ["t:fy:body2"]  # and once it is, the old body's open binding is superseded
    full.close()


def test_current_bindings_supersedes_a_revision_but_keeps_a_second_stint() -> None:
    def b(start, end, learned):
        interval = FuzzyInterval.open_ended(start) if end is None else FuzzyInterval.point_known(start, end)
        return SelfPersonaBinding(self_id="s", persona_id="p", interval=interval,
                                  learned_at_pos=DiscoursePosition(chapter=learned, offset=0), observer_id=OBSERVER_READER)

    provisional, closed, later_stint = b(1.0, None, 1), b(1.0, 3.2, 5), b(9.0, 12.0, 9)
    assert current_bindings([provisional, closed, later_stint]) == [closed, later_stint]
    assert current_bindings([provisional, later_stint]) == [provisional, later_stint]


def test_cli_exit_codes_and_the_source_database_is_untouched(tmp_path, capsys) -> None:
    db = _book(tmp_path / "b.db")
    before = hashlib.sha256(Path(db).read_bytes()).hexdigest()
    common = ["--db", db, "faithfulness", "--novel", "t", "--work-dir", str(tmp_path / "w")]
    assert main([*common, "--cuts", "3,4"]) == 0
    assert main([*common, "--cuts", "3,4", "--whole-volume-personas", "--out", str(tmp_path / "r.json")]) == 1
    assert '"ok": false' in (tmp_path / "r.json").read_text()
    assert main([*common, "--cuts", "5"]) == 2  # the last chapter: nothing after it to leak
    assert main(["--db", str(tmp_path / "missing.db"), "faithfulness", "--novel", "t"]) == 2
    assert "NOT faithful" in capsys.readouterr().out
    assert hashlib.sha256(Path(db).read_bytes()).hexdigest() == before


def test_persona_at_hands_a_reader_the_old_body_until_the_change_is_confirmed(tmp_path) -> None:
    from echotales.pipeline.persona.split import persona_at

    check_reader_faithfulness(_book(tmp_path / "b.db"), "t", [4], work_dir=tmp_path / "w")
    full = Store(str(tmp_path / "w" / "full.db"))
    try:
        for chapter, body in ((3, "body1"), (4, "body1"), (5, "body2")):
            known = DiscoursePosition(chapter=chapter, offset=10**6)
            assert persona_at(full, "t:fy", chapter + 0.5, known_by=known) == f"t:fy:{body}", chapter
        assert persona_at(full, "t:fy", 3.5) == "t:fy:body2"  # no reader position: the whole-novel answer, unchanged
    finally:
        full.close()
