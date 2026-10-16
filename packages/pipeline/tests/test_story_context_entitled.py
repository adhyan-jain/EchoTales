"""A1/A2 and A7 (CHIMERA defect backlog): a brief must not name an entity through a link the reader has not been told.

The title-holder pass links a bare "the clan head" in chapter 1 to the holder first declared in chapter 2 (volume-first
by design). `story_context` then listed that holder as PRESENT in the chapter-1 brief: 5 of 547 sampled briefs on the
real database. `reader_entitled=True` drops such mentions at the prompt boundary; `causal_titles=True` stops the pass
from creating the retroactive link at all. Both default to the shipped behaviour. Synthetic strings only.
"""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.resolve import resolve_novel
from echotales.pipeline.world.context import story_context

N = "t"


def _world(**resolve_kwargs) -> Store:
    s = Store(":memory:")
    s.add_novel(N, "T", "x.epub", "generic")
    texts = {
        1.0: "Everyone watched the clan head closely.",
        2.0: "Clan head Zorrin Vale rose. Zorrin Vale spoke. Clan head Zorrin Vale rose again.",
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
    resolve_novel(N, s, **resolve_kwargs)
    return s


def _labels(s: Store, chapter: float, **kw) -> list[str]:
    return [c.label for c in story_context(N, s, chapter, [0], include_appearance=False, **kw).characters]


def test_default_brief_names_the_holder_in_chapter_one_through_the_retroactive_link() -> None:
    s = _world()
    assert "Zorrin Vale" in _labels(s, 1.0)                    # the shipped (leaking) behaviour, unchanged


def test_reader_entitled_drops_the_retroactive_link_at_the_prompt_boundary() -> None:
    s = _world()
    assert _labels(s, 1.0, reader_entitled=True) == []         # the reader is not told until chapter 2
    assert "Zorrin Vale" in _labels(s, 2.0, reader_entitled=True)   # and is told from then on


def test_causal_titles_prevents_the_retroactive_link_in_the_first_place() -> None:
    s = _world(causal_titles=True)
    assert _labels(s, 1.0) == []
    assert "Zorrin Vale" in _labels(s, 2.0)
