"""A description that sits in its own block next to the block that names the character is theirs.

LotM ch1 (round-2 review, 2026-11-20): block 35 "Zhou Mingrui noticed himself in the mirror", block 36 "Black hair, brown
eyes, a linen shirt, thinly built ..." with no name in it. Appearance extraction required a mention in the block itself,
so the lead had no hair fact at all, the genre default (brown) filled in and he was drawn brown-haired in 16 of 16 panels."""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.resolve.appearance_extract import (
    find_adjacent_descriptive_blocks,
    gather_appearance_passages,
)

TEXTS = [
    "The room was small.",                                                       # 0
    "Zhou Mingrui noticed himself in the mirror, the present him.",              # 1  names him
    "Black hair, brown eyes, a linen shirt, thinly built, average-looking features.",  # 2  describes, no name
    "Zhou Mingrui gasped as guesses surfaced in his mind.",                      # 3  names him
    "Across the room Klein Moretti's rival stood tall, with grey hair and pale eyes.",  # 4 other person
]


def _store(tmp_path, others_at=(4,)) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="a.html",
                              blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(TEXTS)]))
    for sid, label in (("t:self1", "Zhou Mingrui"), ("t:self2", "Klein Moretti")):
        store.add_self(Self(id=sid, novel_id="t", canonical_label=label,
                            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.add_spans([Span(id=f"s{i}", novel_id="t", chapter=1.0, block_index=i, start=0, end=len(t), text=t,
                          span_type=SpanType.NARRATION_DESCRIPTION) for i, t in enumerate(TEXTS)])

    def m(i, block, text, target):
        return Mention(id=f"m{i}", novel_id="t", segment_id="s", chapter=1.0, offset=0, block_index=block, text=text,
                       alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                       reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=target)

    rows = [m(0, 1, "Zhou Mingrui", "t:self1"), m(1, 3, "Zhou Mingrui", "t:self1")]
    rows += [m(10 + b, b, "Klein Moretti", "t:self2") for b in others_at]
    store.add_mentions(rows)
    store.conn.commit()
    return store


def test_a_nameless_description_between_two_blocks_naming_him_is_his(tmp_path) -> None:
    store = _store(tmp_path)
    assert (1.0, 2) in find_adjacent_descriptive_blocks(store, "t", "t:self1")
    got = [p for p in gather_appearance_passages(store, "t", "t:self1") if "Black hair, brown eyes" in p]
    assert got and "Zhou Mingrui noticed himself" in got[0], "the naming sentence travels with the description"
    store.close()


def test_a_description_beside_another_person_is_not_attributed(tmp_path) -> None:
    store = _store(tmp_path, others_at=(2, 4))
    assert (1.0, 2) not in find_adjacent_descriptive_blocks(store, "t", "t:self1")
    store.close()


def test_a_block_two_away_from_his_name_is_not_adjacent(tmp_path) -> None:
    store = _store(tmp_path)
    assert (1.0, 4) not in find_adjacent_descriptive_blocks(store, "t", "t:self1")
    store.close()


def test_a_description_in_the_sentence_after_his_naming_sentence_is_grounded_unless_it_names_someone_else() -> None:
    from echotales.pipeline.resolve.appearance_extract import _grounded

    p = "With a sweep of his gaze, Zhou Mingrui noticed himself in the mirror—the present him. Black hair, brown eyes, a linen shirt."
    assert _grounded("black", {"zhou mingrui"}, [p]) and _grounded("brown", {"zhou mingrui"}, [p])
    other = "Zhou Mingrui looked at the old cracked dressing mirror for a long while. Dunn Smith had black hair and a long coat."
    assert not _grounded("black", {"zhou mingrui"}, [other])
    assert not _grounded("red", {"zhou mingrui"}, [p])
