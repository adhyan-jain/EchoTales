"""B2 and A7 (CHIMERA defect backlog): `resolve --chapters` selects the chapters to resolve, and a prefix run is causal.

Before B2 the flag was accepted and ignored: a "prefix" run silently resolved the whole volume. Now chapters outside
the range are left unresolved, and the whole-volume passes (title holders, transmigration), which read later
chapters, are skipped in prefix mode so nothing after the prefix can influence a decision inside it. Synthetic
strings only.
"""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.ingest.adapters import ChapterRange
from echotales.pipeline.resolve import resolve_novel

N = "t"


def _store() -> Store:
    s = Store(":memory:")
    s.add_novel(N, "T", "x.epub", "generic")
    texts = {
        1.0: "Everyone watched the clan head closely. Zorrin Vale waited.",
        2.0: "Clan head Zorrin Vale rose. Zorrin Vale spoke. Clan head Zorrin Vale rose again.",
        3.0: "Zorrin Vale left the hall.",
    }
    ms, k = [], 0
    for n, t in texts.items():
        s.add_chapter(Chapter(novel_id=N, number=n, title="T", source_href=f"{n}.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=t)]))
        for name, at in (("Zorrin Vale", AliasType.RIGID_NAME), ("the clan head", AliasType.TRANSFERABLE_TITLE)):
            pos = 0
            while (i := t.find(name, pos)) != -1:
                k += 1
                ms.append(Mention(id=f"m{k}", novel_id=N, segment_id="s", chapter=n, offset=i, text=name,
                                  alias_type=at, span_type=SpanType.NARRATION_ACTION,
                                  reference_mode=ReferenceMode.PRESENT, block_index=0, local_group_id=f"g{k}"))
                pos = i + len(name)
    s.add_mentions(ms)
    s.conn.commit()
    return s


def _linked_chapters(s: Store) -> set[float]:
    return {m.chapter for m in s.get_mentions(N) if m.target_id is not None}


def test_chapters_range_limits_which_chapters_are_resolved() -> None:
    full = _store()
    resolve_novel(N, full)
    assert _linked_chapters(full) == {1.0, 2.0, 3.0}
    prefix = _store()
    resolve_novel(N, prefix, chapters=ChapterRange.parse("1-2"))
    assert _linked_chapters(prefix) == {1.0, 2.0}              # chapter 3 untouched


def test_prefix_run_does_not_link_a_title_backwards_from_later_text() -> None:
    prefix = _store()
    resolve_novel(N, prefix, chapters=ChapterRange.parse("1-1"))
    title = [m for m in prefix.get_mentions(N, 1.0) if m.text == "the clan head"][0]
    assert title.target_id is None        # the declarations are in chapter 2, outside the prefix


def test_prefix_volume_passes_can_be_requested_explicitly() -> None:
    s = _store()
    resolve_novel(N, s, chapters=ChapterRange.parse("1-2"), prefix_volume_passes=True)
    title = [m for m in s.get_mentions(N, 1.0) if m.text == "the clan head"][0]
    assert title.target_id is not None    # the old, non-causal behaviour, only on request
