"""Defect #6 (HANDOFF "Open defects"): does a bare given-name-pair surname-dropped
form ("Dong Tu") actually link to the house-prefixed introduction ("Gu Yue Dong
Tu") through the real resolve pipeline?

This is the >=2-token branch of `normalize.name_containment` (no
`ambiguous_tokens` needed -- see its docstring), already wired as a FORCE_LINK
pre-filter in `resolve/score.py`. `test_name_containment_resolve.py` only
covers the 1-token dropped-given-name case (Kim Dokja/Dokja); this file
exercises the 2-token house-prefix case end to end to confirm whether the
defect is real or already closed by that mechanism.
"""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.resolve import resolve_novel


def _chapter(number: float, text: str) -> Chapter:
    return Chapter(
        novel_id="t",
        number=number,
        title="T",
        source_href=f"{number}.html",
        blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
    )


def _mention(mid: str, text: str, *, chapter: float, group: str) -> Mention:
    return Mention(
        id=mid,
        novel_id="t",
        segment_id="s",
        chapter=chapter,
        offset=0,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT,
        block_index=0,
        local_group_id=group,
    )


class TestClanPrefixDrop:
    def test_bare_two_token_name_links_to_house_prefixed_introduction(self) -> None:
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(_chapter(1.0, "Gu Yue Dong Tu walked into the hall."))
        store.add_chapter(_chapter(2.0, "Dong Tu frowned at the news."))
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Dong Tu", chapter=1.0, group="g1"),
                _mention("m2", "Dong Tu", chapter=2.0, group="g2"),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)

        m1 = next(m for m in store.get_mentions("t", 1.0) if m.text == "Gu Yue Dong Tu")
        m2 = next(m for m in store.get_mentions("t", 2.0) if m.text == "Dong Tu")
        assert m1.target_id is not None
        assert m2.target_id == m1.target_id
