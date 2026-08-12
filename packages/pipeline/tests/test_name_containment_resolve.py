"""§4.15's ORV gap, end to end: a dropped *given* name should now merge into
the entity that introduced it, distinguished from a dropped *surname* (which
must still stay blocked, §4.5) by corpus-wide token ambiguity rather than a
pure token-count threshold. See `normalize.name_containment` and
`resolve/runner.py::GlobalResolver._ambiguous_tokens` for the mechanism;
`test_chapter_ner.py::TestNameContainment` covers the function in isolation.
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


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(_chapter(1.0, "Kim Dokja read the novel."))
    store.add_chapter(_chapter(2.0, "Kim Yuji watched him."))
    store.add_chapter(_chapter(3.0, "Dokja sighed."))
    return store


class TestDroppedGivenNameMerges:
    def test_bare_given_name_links_to_the_entity_that_introduced_it(self) -> None:
        store = _store()
        store.add_mentions(
            [
                _mention("m1", "Kim Dokja", chapter=1.0, group="g1"),
                _mention("m2", "Kim Yuji", chapter=2.0, group="g2"),
                _mention("m3", "Dokja", chapter=3.0, group="g3"),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)

        m3 = next(m for m in store.get_mentions("t", 3.0) if m.text == "Dokja")
        m1 = next(m for m in store.get_mentions("t", 1.0) if m.text == "Kim Dokja")
        assert m3.target_id is not None
        assert m3.target_id == m1.target_id

    def test_ambiguous_surname_alone_does_not_merge(self) -> None:
        """Sanity control: with two "Kim"s in the cast, a bare "Kim" (not
        "Dokja") must NOT pick one arbitrarily -- §4.5 still applies to the
        shared surname itself."""
        store = _store()
        store.add_mentions(
            [
                _mention("m1", "Kim Dokja", chapter=1.0, group="g1"),
                _mention("m2", "Kim Yuji", chapter=2.0, group="g2"),
                _mention("m3", "Kim", chapter=3.0, group="g3"),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)
        m3 = next(m for m in store.get_mentions("t", 3.0) if m.text == "Kim")
        m1 = next(m for m in store.get_mentions("t", 1.0) if m.text == "Kim Dokja")
        m2 = next(m for m in store.get_mentions("t", 2.0) if m.text == "Kim Yuji")
        assert m3.target_id not in (m1.target_id, m2.target_id) or m3.target_id is None
