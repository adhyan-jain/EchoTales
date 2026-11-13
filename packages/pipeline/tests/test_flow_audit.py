"""The data-conservation auditor (`pipeline/flow.py`): each check passes on a clean ingest and fails, naming the
chapter and quoting the text, on a deliberately damaged database."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import ClassVar
from xml.sax.saxutils import escape

import pytest
from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter, NarrativeSegment
from echotales.core.store import Store
from echotales.pipeline import cli, flow
from echotales.pipeline.flow import Stage, Status
from echotales.pipeline.ingest import ingest_config
from echotales.pipeline.ingest.adapters import ChapterRange
from echotales.pipeline.ingest.sources import SourceConfig
from echotales.pipeline.segment import segment_novel

DEMO_DIR = Path(__file__).resolve().parents[3] / "scripts" / "demo"

NOVEL = "t"


def _words(seed: str, n: int) -> str:
    return " ".join(f"{seed}{i}" for i in range(n)) + "."


def make_epub(path: Path, files: dict[str, str], toc: list[tuple[str, str]]) -> Path:
    """A minimal EPUB: `files` maps a document name to its body HTML; `toc` is (label, href)."""
    manifest = "".join(
        f'<item id="d{i}" href="{name}" media-type="application/xhtml+xml"/>' for i, name in enumerate(files)
    )
    spine = "".join(f'<itemref idref="d{i}"/>' for i in range(len(files)))
    points = "".join(
        f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{escape(label)}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, (label, href) in enumerate(toc, start=1)
    )
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title></metadata>'
        f'<manifest>{manifest}<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{spine}</spine></package>'
    )
    ncx = (
        '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f"<navMap>{points}</navMap></ncx>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("content.opf", opf)
        z.writestr("toc.ncx", ncx)
        for name, body in files.items():
            z.writestr(name, f"<html><body>{body}</body></html>")
    return path


def build(tmp_path: Path, epub: Path, *, chapters: str | None = None) -> tuple[Store, flow.SourceContext]:
    store = Store(tmp_path / "t.db")
    cfg = SourceConfig(
        id=NOVEL, title="T", path=epub, adapter="generic",
        chapters=ChapterRange.parse(chapters) if chapters else None,
    )
    ingest_config(cfg, store)
    segment_novel(NOVEL, store)
    ctx = flow.SourceContext(path=epub, adapter="generic", chapters=cfg.chapters)
    return store, ctx


@pytest.fixture
def book(tmp_path: Path) -> tuple[Store, flow.SourceContext]:
    paras = [f"<p>Para {c}-{p} {_words(f'w{c}x{p}x', 40)}</p>" for c in (1, 2, 3) for p in range(6)]
    files = {
        f"c{c}.xhtml": f"<h2>Chapter {c}: Title {c}</h2>" + "".join(paras[(c - 1) * 6 : c * 6])
        for c in (1, 2, 3)
    }
    epub = make_epub(tmp_path / "t.epub", files, [(f"Chapter {c}: Title {c}", f"c{c}.xhtml") for c in (1, 2, 3)])
    store, ctx = build(tmp_path, epub)
    yield store, ctx
    ctx.close()
    store.close()


def run(store: Store, ctx: flow.SourceContext | None, check_id: str) -> flow.CheckResult:
    stage = next(s for s in Stage if any(c.check_id == check_id for c in flow.CHECKS[s]))
    chk = next(c for c in flow.CHECKS[stage] if c.check_id == check_id)
    if chk.needs_source and ctx is None:
        return flow._skipped(chk, "no source")
    return chk.fn(store, NOVEL, ctx)


def rewrite(store: Store, number: float, blocks: list[Block], title: str | None = None) -> None:
    old = store.get_chapter(NOVEL, number)
    assert old is not None
    store.add_chapter(
        Chapter(novel_id=NOVEL, number=number, title=old.title if title is None else title,
                source_href=old.source_href, blocks=blocks)
    )
    store.conn.commit()


def reindexed(blocks: list[Block]) -> list[Block]:
    return [b.model_copy(update={"index": i}) for i, b in enumerate(blocks)]


# ---------------------------------------------------------------------------


def test_clean_book_passes_every_implemented_check(book) -> None:
    store, ctx = book
    results = flow.run_checks(store, NOVEL, ctx)
    bad = [(r.check_id, r.status, [s.render() for s in r.shortfalls]) for r in results
           if r.status not in (Status.PASS, Status.SKIPPED)]
    assert not bad
    skipped = {r.check_id for r in results if r.status is Status.SKIPPED}
    assert skipped == {"spans.stored_rows"}
    coverage = next(r for r in results if r.check_id == "ingest.coverage")
    # The h2 heading of each chapter is the one named exclusion: 3 chapters x 4 words.
    assert coverage.stats["exclusions_words"] == {"chapter_heading_repeating_toc_label": 12}
    assert coverage.count_in - coverage.count_out == 12


def test_sample_book_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(DEMO_DIR))
    import make_sample_epub

    epub = make_sample_epub.write_sample_epub(tmp_path / "sample.epub")
    store, ctx = build(tmp_path, epub)
    try:
        results = flow.run_checks(store, NOVEL, ctx)
        assert [r.check_id for r in results if r.status is Status.FAIL] == []
        assert {r.check_id for r in results if r.status is Status.PASS} >= {
            "ingest.coverage", "ingest.no_duplicates", "ingest.toc_agreement", "ingest.chapter_shape",
            "ingest.block_order", "segment.tiling", "spans.tiling", "spans.typed",
        }
        # Corrupt: lose one paragraph from chapter 1 (indexes renumbered, so only coverage can see it).
        chapter = store.get_chapter(NOVEL, 1)
        assert chapter is not None
        lost = chapter.blocks[5].text
        rewrite(store, 1, reindexed(chapter.blocks[:5] + chapter.blocks[6:]))
        failed = flow.run_checks(store, NOVEL, ctx)
        coverage = next(r for r in failed if r.check_id == "ingest.coverage")
        assert coverage.status is Status.FAIL
        assert lost.split()[0] in coverage.shortfalls[0].excerpt
        assert coverage.shortfalls[0].chapter == 1
    finally:
        ctx.close()
        store.close()


def test_coverage_names_the_dropped_paragraph(book) -> None:
    store, ctx = book
    chapter = store.get_chapter(NOVEL, 2)
    assert chapter is not None
    rewrite(store, 2, reindexed(chapter.blocks[:2] + chapter.blocks[3:]))
    r = run(store, ctx, "ingest.coverage")
    assert r.status is Status.FAIL
    assert r.total_shortfalls == 1
    s = r.shortfalls[0]
    assert s.chapter == 2
    assert "42 words" in s.detail
    assert chapter.blocks[2].text.split()[0] in s.excerpt
    assert r.stats["unaccounted_words"] == 42


def test_coverage_skipped_without_the_source(book) -> None:
    store, _ = book
    r = flow.run_checks(store, NOVEL, None, source_reason="source file not available: x", stages=[Stage.INGEST])[0]
    assert r.status is Status.SKIPPED
    assert "not available" in r.skipped_reason


def test_deleted_block_breaks_block_order_and_segments(book) -> None:
    store, ctx = book
    chapter = store.get_chapter(NOVEL, 1)
    assert chapter is not None
    rewrite(store, 1, chapter.blocks[:3] + chapter.blocks[4:])  # index 3 is gone, indexes not renumbered
    order = run(store, ctx, "ingest.block_order")
    assert order.status is Status.FAIL
    assert order.shortfalls[0].chapter == 1
    assert "expected 3" in order.shortfalls[0].detail
    seg = run(store, ctx, "segment.tiling")
    assert seg.status is Status.FAIL
    assert "chapter has" in seg.shortfalls[0].detail


def test_duplicated_chapter_is_found(book) -> None:
    store, ctx = book
    first = store.get_chapter(NOVEL, 1)
    assert first is not None
    rewrite(store, 3, list(first.blocks))
    r = run(store, ctx, "ingest.no_duplicates")
    assert r.status is Status.FAIL
    assert r.shortfalls[0].chapter == 3
    assert "repeat chapter 1" in r.shortfalls[0].detail


def test_short_repeat_is_only_a_warning(tmp_path: Path) -> None:
    prayer = _words("prayer", 40)
    files = {
        f"c{c}.xhtml": f"<h2>Chapter {c}</h2><p>{_words(f'a{c}', 300)}</p><p>{prayer}</p><p>{_words(f'b{c}', 300)}</p>"
        for c in (1, 2)
    }
    epub = make_epub(tmp_path / "t.epub", files, [(f"Chapter {c}", f"c{c}.xhtml") for c in (1, 2)])
    store, ctx = build(tmp_path, epub)
    r = run(store, ctx, "ingest.no_duplicates")
    assert r.status is Status.PASS
    assert r.warnings and "repeat chapter 1" in r.warnings[0]


def test_toc_agreement_finds_a_missing_chapter(book) -> None:
    store, ctx = book
    store.conn.execute("DELETE FROM chapter WHERE number=2")
    store.conn.commit()
    r = run(store, ctx, "ingest.toc_agreement")
    assert r.status is Status.FAIL
    assert r.shortfalls[0].chapter == 2
    assert "no stored chapter" in r.shortfalls[0].detail
    cov = run(store, ctx, "ingest.coverage")
    assert cov.status is Status.FAIL
    assert "TOC entry has no stored chapter" in cov.shortfalls[0].detail


def test_toc_agreement_finds_a_second_entry_with_the_same_number(tmp_path: Path) -> None:
    files = {"a.xhtml": f"<p>{_words('a', 30)}</p>", "b.xhtml": f"<p>{_words('b', 30)}</p>"}
    epub = make_epub(tmp_path / "t.epub", files, [("Chapter 5: One", "a.xhtml"), ("Chapter 5: Two", "b.xhtml")])
    store, ctx = build(tmp_path, epub)
    r = run(store, ctx, "ingest.toc_agreement")
    assert r.status is Status.FAIL
    assert "both parse as chapter 5" in r.shortfalls[0].detail


def test_chapter_shape_flags_blank_title_and_empty_chapter(book) -> None:
    store, ctx = book
    rewrite(store, 1, [], title="")
    r = run(store, ctx, "ingest.chapter_shape")
    assert r.status is Status.FAIL
    details = " ".join(s.detail for s in r.shortfalls)
    assert "no blocks" in details and "no title" in details


def test_unnumbered_big_entry_is_excluded_but_warned(tmp_path: Path) -> None:
    files = {
        "pro.xhtml": f"<p>{_words('pro', 400)}</p>",
        "c1.xhtml": f"<p>{_words('one', 50)}</p>",
    }
    epub = make_epub(tmp_path / "t.epub", files, [("Prologue", "pro.xhtml"), ("Chapter 1: Start", "c1.xhtml")])
    store, ctx = build(tmp_path, epub)
    r = run(store, ctx, "ingest.coverage")
    assert r.status is Status.PASS
    assert any("Prologue" in w for w in r.warnings)
    assert r.stats["exclusions_words"]["unnumbered_toc_entry (front/back matter, prologue, parts)"] == 400


def test_gutenberg_footer_and_anchored_chapters(tmp_path: Path) -> None:
    body = (
        '<h2><a id="c1"></a>CHAPTER I.</h2><p>' + _words("one", 30) + "</p>"
        '<h2><a id="c2"></a>CHAPTER II.</h2><p>' + _words("two", 30) + "</p>"
        "<p>*** END OF THE PROJECT GUTENBERG EBOOK TEST ***</p><p>Licence terms follow here.</p>"
    )
    epub = make_epub(tmp_path / "t.epub", {"b.xhtml": body},
                     [("CHAPTER I.", "b.xhtml#c1"), ("CHAPTER II.", "b.xhtml#c2")])
    store, ctx = build(tmp_path, epub)
    r = run(store, ctx, "ingest.coverage")
    assert r.status is Status.PASS, [s.render() for s in r.shortfalls]
    assert r.stats["exclusions_words"]["licence_footer"] == 13


def test_line_break_does_not_glue_words(tmp_path: Path) -> None:
    doc = flow.read_doc_text(b"<html><body><p>one<br/>two <i>th</i>ree</p></body></html>")
    assert doc.words == ["one", "two", "three"]


# ---- segment ----------------------------------------------------------------


def test_segment_gap_overlap_and_empty(book) -> None:
    store, ctx = book
    assert run(store, ctx, "segment.tiling").status is Status.PASS
    segs = store.get_segments(NOVEL, 1)
    assert len(segs) == 1

    def seg(id_: str, lo: int, hi: int) -> NarrativeSegment:
        return segs[0].model_copy(update={"id": id_, "offset_from": lo, "offset_to": hi})

    store.conn.execute("DELETE FROM narrative_segment WHERE chapter_from=1")
    store.add_segments([seg("a", 0, 1), seg("b", 3, 5)])
    store.conn.commit()
    r = run(store, ctx, "segment.tiling")
    assert r.status is Status.FAIL
    assert any("blocks 2-2 belong to no segment" in s.detail and s.chapter == 1 for s in r.shortfalls)

    store.conn.execute("DELETE FROM narrative_segment WHERE chapter_from=1")
    store.add_segments([seg("a", 0, 3), seg("b", 3, 5)])
    store.conn.commit()
    assert any("belong to two segments" in s.detail for s in run(store, ctx, "segment.tiling").shortfalls)

    store.conn.execute("DELETE FROM narrative_segment WHERE chapter_from=1")
    store.add_segments([seg("a", 0, 5), seg("b", 4, 3)])
    store.conn.commit()
    assert any("empty segment" in s.detail for s in run(store, ctx, "segment.tiling").shortfalls)

    store.conn.execute("DELETE FROM narrative_segment WHERE chapter_from=1")
    store.conn.commit()
    assert any("no segment covers" in s.detail for s in run(store, ctx, "segment.tiling").shortfalls)


def test_segment_check_skipped_before_the_stage_runs(tmp_path: Path) -> None:
    store = Store(tmp_path / "x.db")
    store.add_novel(NOVEL, "T", "x", "generic")
    chk = flow._find(Stage.SEGMENT, "segment.tiling")
    assert chk.fn(store, NOVEL, None).status is Status.SKIPPED


# ---- spans ------------------------------------------------------------------


def test_span_boundary_shift_is_found(book, monkeypatch: pytest.MonkeyPatch) -> None:
    store, ctx = book
    assert run(store, ctx, "spans.tiling").status is Status.PASS
    from echotales.pipeline import spans as spans_mod

    real = spans_mod.classify_chapter

    def shifted(chapter):  # type: ignore[no-untyped-def]
        out = real(chapter)
        out[0] = out[0].model_copy(update={"start": out[0].start + 5})
        return out

    monkeypatch.setattr(spans_mod, "classify_chapter", shifted)
    r = run(store, ctx, "spans.tiling")
    assert r.status is Status.FAIL
    details = " ".join(s.detail for s in r.shortfalls)
    assert "characters reach no span" in details
    assert "differs from the block slice" in details


def test_stored_span_rows_are_checked(book) -> None:
    store, ctx = book
    assert run(store, ctx, "spans.stored_rows").status is Status.SKIPPED
    from echotales.pipeline.spans import classify_chapter

    chapter = store.get_chapter(NOVEL, 1)
    assert chapter is not None
    spans = classify_chapter(chapter)
    store.add_spans(spans)
    store.conn.commit()
    assert run(store, ctx, "spans.stored_rows").status is Status.PASS
    store.add_spans([spans[1].model_copy(update={"start": spans[1].start + 3})])
    store.conn.commit()
    r = run(store, ctx, "spans.stored_rows")
    assert r.status is Status.FAIL
    assert "3 characters reach no span" in r.shortfalls[0].detail
    assert r.shortfalls[0].chapter == 1


def test_spans_typed_rejects_an_unknown_type(book) -> None:
    store, ctx = book
    from echotales.pipeline.spans import classify_chapter

    chapter = store.get_chapter(NOVEL, 1)
    assert chapter is not None
    store.add_spans(classify_chapter(chapter))
    store.conn.execute("UPDATE span SET span_type='BOGUS' WHERE id=(SELECT id FROM span LIMIT 1)")
    store.conn.commit()
    r = run(store, ctx, "spans.typed")
    assert r.status is Status.FAIL
    assert "BOGUS" in r.shortfalls[0].detail


def _synthetic(store: Store, chapters: dict[float, list[str]]) -> None:
    store.add_novel(NOVEL, "T", "x", "generic")
    for number, paragraphs in chapters.items():
        store.add_chapter(
            Chapter(
                novel_id=NOVEL, number=number, title=f"Chapter {number:g}", source_href="x",
                blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(paragraphs)],
            )
        )
    store.conn.commit()


def test_quote_imbalance_is_a_located_warning_not_a_failure(tmp_path: Path) -> None:
    store = Store(tmp_path / "q.db")
    _synthetic(store, {
        1: ["He said, “Come here.” She came.", "A stray close” in the middle of a line."],
        2: ["“A speech that runs on", "“and carries over a paragraph,” he said."],
    })
    r = flow._find(Stage.SPANS, "spans.quote_balance").fn(store, NOVEL, None)
    assert r.status is Status.PASS
    assert len(r.warnings) == 1
    assert "chapter 1" in r.warnings[0] and "block 1" in r.warnings[0] and "stray close" in r.warnings[0]


def test_dialogue_share_outlier_is_flagged(tmp_path: Path) -> None:
    talk = ["“" + _words("t", 60) + "” he said."] * 3
    store = Store(tmp_path / "d.db")
    chapters = {float(n): list(talk) for n in range(1, 11)}
    chapters[11.0] = [_words("n", 120)] * 3  # same length, no quoted speech at all
    _synthetic(store, chapters)
    r = flow._find(Stage.SPANS, "spans.type_profile").fn(store, NOVEL, None)
    assert r.status is Status.PASS
    assert len(r.warnings) == 1 and "chapter 11" in r.warnings[0]
    assert "DIALOGUE" in r.stats["span_types_per_chapter"]["1"]


# ---- CLI --------------------------------------------------------------------


def test_cli_exit_codes_json_and_read_only(book, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store, ctx = book
    store.conn.commit()
    db = tmp_path / "t.db"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    argv = ["--db", str(db), "audit", "--novel", NOVEL, "--source", str(ctx.path)]

    assert cli.main([*argv, "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["novel"] == NOVEL and doc["totals"]["fail"] == 0
    assert doc["stages"] == ["ingest", "segment", "spans"]
    assert {"check", "invariant", "status", "count_in", "count_out", "shortfalls", "total_shortfalls"} <= set(
        doc["checks"][0]
    )

    assert cli.main([*argv, "--stage", "segment"]) == 0
    assert "segment.tiling" in capsys.readouterr().out
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before

    assert cli.main(["--db", str(tmp_path / "missing.db"), "audit", "--novel", NOVEL]) == 2
    assert cli.main(["--db", str(db), "audit", "--novel", "nope"]) == 2
    capsys.readouterr()

    chapter = store.get_chapter(NOVEL, 1)
    assert chapter is not None
    rewrite(store, 1, reindexed(chapter.blocks[:-1]))
    store.close()
    assert cli.main(argv) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "chapter 1" in out


def test_findings_are_capped_but_the_total_is_true(tmp_path: Path) -> None:
    store = Store(tmp_path / "c.db")
    _synthetic(store, {float(n): [] for n in range(1, 31)})
    r = flow._find(Stage.INGEST, "ingest.chapter_shape").fn(store, NOVEL, None)
    assert r.status is Status.FAIL
    assert len(r.shortfalls) == flow.MAX_LISTED and r.total_shortfalls == 30
    assert "more (30 in total)" in flow.render_text(NOVEL, [r])


# ---- stage bugs the auditor surfaced ----------------------------------------


def test_br_inside_a_paragraph_does_not_glue_words() -> None:
    from echotales.pipeline.ingest.adapters.base import extract_block
    from lxml import html as lxml_html

    para = lxml_html.fromstring("<p>para one<br/>line two<i>x</i><br/>end</p>")
    assert extract_block(para).text == "para one line twox end"


def test_llm_boundary_never_leaves_blocks_without_a_segment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import echotales.pipeline.segment.runner as runner
    from echotales.pipeline.segment.detect import segment_chapter

    class Proposal:
        kind, start_block, end_block = "DREAM", 3, 5

    class Response:
        boundaries: ClassVar = [Proposal()]
        confidence = 0.9

    store = Store(tmp_path / "s.db")
    _synthetic(store, {1.0: [f"Block {i} {_words('b', 5)}" for i in range(10)]})
    chapter = store.get_chapter(NOVEL, 1)
    assert chapter is not None
    rules = segment_chapter(chapter)
    assert len(rules) == 1
    monkeypatch.setattr(runner, "propose_boundaries", lambda *_: Response())
    merged = runner._merge_llm_proposals(chapter, rules, None)  # type: ignore[arg-type]
    store.add_segments(merged)
    store.conn.commit()
    assert flow._find(Stage.SEGMENT, "segment.tiling").fn(store, NOVEL, None).status is Status.PASS
