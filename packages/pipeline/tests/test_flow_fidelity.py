"""Offset fidelity of ingest, spans and mentions (flow-audit defects D1-D4)."""

from __future__ import annotations

from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline.mentions import detect_mentions
from echotales.pipeline.spans import classify_block_spans


def _block(text: str, index: int = 0) -> Block:
    return Block(index=index, block_type=BlockType.PROSE, text=text)


def test_d4_span_offsets_select_exactly_the_span_text() -> None:
    # 2,527 of 20,479 RI spans stored `text` stripped but `start`/`end` unstripped.
    text = '"Hello there," said Klein. "Goodbye now."'
    spans = classify_block_spans(_block(text), novel_id="t", chapter=1.0)
    assert len(spans) >= 2
    assert any(s.start > 0 and text[s.start - 1] == " " for s in spans)
    for s in spans:
        assert text[s.start : s.end] == s.text


def test_d4_mention_offsets_select_their_surface_text() -> None:
    # mention.offset = span.start + hit.start: every mention after a space-led span was shifted.
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    blocks = [
        '"Run," he said. Fang Yuan stepped forward. "Go," said Wu An.',
        "Fang Yuan nodded. Then Wu An left.",
    ]
    store.add_chapter(
        Chapter(
            novel_id="t", number=1.0, title="T", source_href="a.html",
            blocks=[_block(t, i) for i, t in enumerate(blocks)],
        )
    )
    store.conn.commit()
    detect_mentions("t", store)
    mentions = store.get_mentions("t")
    assert mentions
    for m in mentions:
        assert blocks[m.block_index][m.offset : m.offset + len(m.text)] == m.text


def _italic_text(html: str) -> list[str]:
    from echotales.pipeline.ingest.adapters.base import extract_block
    from lxml import html as lxml_html

    raw = extract_block(lxml_html.fromstring(html))
    return [raw.text[a:b] for a, b in raw.italic_ranges]


def test_d3_italic_range_lands_on_its_own_occurrence() -> None:
    # text.find(fragment) put the range on the first occurrence: 173 of 999 RI emphasis blocks.
    assert _italic_text("<p>Run away, he thought. <i>Run away</i>, he said.</p>") == ["Run away"]
    html = "<p>Run away, he thought. <i>Run away</i>, he said.</p>"
    from echotales.pipeline.ingest.adapters.base import extract_block
    from lxml import html as lxml_html

    raw = extract_block(lxml_html.fromstring(html))
    assert raw.italic_ranges[0][0] == raw.text.rindex("Run away")


def test_d3_ranges_survive_whitespace_collapse() -> None:
    assert _italic_text("<p>a  b\n  <em> c   d </em>  e  <i>c d</i></p>") == ["c d", "c d"]


def _chapters(tmp_path, docs, toc, adapter="generic"):  # type: ignore[no-untyped-def]
    from echotales.pipeline.ingest import Epub
    from echotales.pipeline.ingest.adapters import get_adapter
    from test_ingest import build_epub

    epub = Epub(build_epub(tmp_path / "b.epub", docs, toc))
    return list(get_adapter(adapter)(epub, "n").chapters())


def test_d1_footnote_asides_become_translator_note_blocks_after_the_story(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # ORV lost 572 words in 22 chapters: `aside` was not a block tag.
    body = (
        "<p>First story paragraph.</p><p>Second story paragraph.</p><hr/>"
        "<section epub:type='endnotes' role='doc-endnotes'>"
        "<aside id='n1' epub:type='footnote'><a href='#r1'>[1]</a> <b>Dokja</b> means reader.</aside>"
        "<aside id='n2' epub:type='footnote'><a href='#r2'>[2]</a> ssi is an honorific.</aside>"
        "</section>"
    )
    (ch,) = _chapters(tmp_path, {"a.html": body}, [("Chapter 1: A", "a.html")])
    kinds = [b.block_type for b in ch.blocks]
    assert [b.text for b in ch.blocks[:2]] == ["First story paragraph.", "Second story paragraph."]
    assert kinds[:2] == [BlockType.PROSE, BlockType.PROSE]
    notes = [b for b in ch.blocks if "Dokja" in b.text or "ssi" in b.text]
    assert len(notes) == 2 and all(b.block_type is BlockType.TRANSLATOR_NOTE for b in notes)
    assert [b.index for b in ch.blocks] == list(range(len(ch.blocks)))


def test_d1_other_asides_are_still_skipped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    body = "<p>Story.</p><aside class='ad'>Buy my book.</aside>"
    (ch,) = _chapters(tmp_path, {"a.html": body}, [("Chapter 1: A", "a.html")])
    assert [b.text for b in ch.blocks] == ["Story."]


def test_d2_text_beside_block_children_is_kept_in_document_order(tmp_path) -> None:  # type: ignore[no-untyped-def]
    body = "<div>Lead text <i>here</i><p>Inner paragraph.</p>Tail text.</div><p>Next.</p>"
    (ch,) = _chapters(tmp_path, {"a.html": body}, [("Chapter 1: A", "a.html")])
    assert [b.text for b in ch.blocks] == ["Lead text here", "Inner paragraph.", "Tail text.", "Next."]
    assert ch.blocks[0].italic_ranges == [(10, 14)]


def test_d2_text_before_the_chapter_anchor_stays_out(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A naive fix pulled a title-page line into P&P chapter 1.
    body = (
        "<div>Title page line<h2 id='c1'>Chapter 1</h2><p>Body one.</p>"
        "<h2 id='c2'>Chapter 2</h2><p>Body two.</p>Trailing two.</div>"
    )
    chs = _chapters(
        tmp_path, {"a.html": body}, [("Chapter 1: A", "a.html#c1"), ("Chapter 2: B", "a.html#c2")]
    )
    t1 = [b.text for b in chs[0].blocks]
    t2 = [b.text for b in chs[1].blocks]
    assert "Title page line" not in " ".join(t1 + t2)
    assert t1 == ["Body one."]
    assert t2 == ["Body two.", "Trailing two."]


def test_d4_tiling_audit_rejects_a_span_whose_offsets_include_leading_whitespace() -> None:
    from echotales.pipeline.flow import _SpanRow, _tile_chapter

    text = '"Hi," he said. "Bye."'
    ch = Chapter(novel_id="t", number=1.0, title="x", source_href="a", blocks=[_block(text)])
    ok = [_SpanRow(0, 0, 5, '"Hi,"', "DIALOGUE", "a"), _SpanRow(0, 6, 21, 'he said. "Bye."', "X", "b")]
    assert _tile_chapter(ch, ok)[0] == []
    loose = [_SpanRow(0, 0, 5, '"Hi,"', "DIALOGUE", "a"), _SpanRow(0, 5, 21, 'he said. "Bye."', "X", "b")]
    assert any("differs from the block slice" in s.detail for s in _tile_chapter(ch, loose)[0])
