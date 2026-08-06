"""Tests for Phase 0 ingestion.

Most tests build synthetic EPUBs in a temp directory so CI can run without the
source novels. The handful that need the real files are marked `corpus` and
skip cleanly when `data/raw/` is empty.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from echotales.core.enums import BlockType
from echotales.core.store import Store
from echotales.pipeline.ingest import (
    ChapterRange,
    Epub,
    classify_block,
    comparison_key,
    ingest_config,
    is_system_window,
    load_sources,
    normalize_romanization,
    parse_chapter_label,
    parse_system_window,
    strip_honorifics,
)
from echotales.pipeline.ingest.adapters import get_adapter
from echotales.pipeline.ingest.adapters.base import extract_block
from echotales.pipeline.ingest.sources import SourceConfig
from lxml import html as lxml_html

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Chapter label parsing -- the TOC is the authority on chapter identity
# ---------------------------------------------------------------------------


class TestParseChapterLabel:
    @pytest.mark.parametrize(
        ("label", "number"),
        [
            ("Chapter 1: The heart of a demon", 1.0),
            ("Chapter 213: Another Look", 213.0),
            ("chapter 7 - Code Names", 7.0),
            ("Ch. 12: Here Again", 12.0),
            ("Chapter 45.1: Split chapter", 45.1),
            ("Episode 3: Something", 3.0),
        ],
    )
    def test_extracts_numbers(self, label: str, number: float) -> None:
        assert parse_chapter_label(label).number == number

    def test_split_chapters_survive_as_floats(self) -> None:
        """45.1 must not collapse onto 45 -- they are different chapters."""
        assert parse_chapter_label("Chapter 45.1: A").number == 45.1
        assert parse_chapter_label("Chapter 45: B").number == 45.0

    def test_title_is_separated_from_the_number(self) -> None:
        assert parse_chapter_label("Chapter 6: Beyonder").title == "Beyonder"

    def test_label_without_a_title_keeps_the_whole_label(self) -> None:
        assert parse_chapter_label("Chapter 9").title == "Chapter 9"

    @pytest.mark.parametrize(
        "label",
        ["Front Cover", "Pathways Guide", "Characters", "Table of Contents", "End of Volume 1"],
    )
    def test_non_chapters_yield_no_number(self, label: str) -> None:
        assert parse_chapter_label(label).number is None

    @pytest.mark.parametrize(
        "label", ["Side Story: Extra", "Interlude", "Prologue", "Epilogue", "Bonus Chapter"]
    )
    def test_side_chapters_are_flagged_not_numbered(self, label: str) -> None:
        """Numbering them 0 would collide them into the main sequence."""
        parsed = parse_chapter_label(label)
        assert parsed.number is None
        assert parsed.is_side


class TestChapterRange:
    def test_parses_a_range(self) -> None:
        r = ChapterRange.parse("1-199")
        assert (r.start, r.end) == (1.0, 199.0)

    def test_is_inclusive_at_both_ends(self) -> None:
        r = ChapterRange.parse("1-199")
        assert 1 in r and 199 in r
        assert 200 not in r and 0 not in r

    def test_split_chapters_fall_inside(self) -> None:
        assert 45.1 in ChapterRange.parse("1-199")

    def test_single_chapter(self) -> None:
        r = ChapterRange.parse("7")
        assert 7 in r and 8 not in r

    def test_open_ended(self) -> None:
        r = ChapterRange.parse("5-")
        assert 5 in r and 10_000 in r and 4 not in r


# ---------------------------------------------------------------------------
# Block classification
# ---------------------------------------------------------------------------


class TestClassifyBlock:
    def test_ordinary_narration_is_prose(self) -> None:
        assert classify_block("He walked into the hall.").block_type is BlockType.PROSE

    def test_dialogue_stays_prose_at_block_level(self) -> None:
        """Dialogue vs narration is a span-level decision in Phase 1.

        A paragraph routinely mixes a spoken line with its narration, so
        committing the whole block to one label would lose that.
        """
        out = classify_block('"Speak," he said coldly.')
        assert out.block_type is BlockType.PROSE

    @pytest.mark.parametrize(
        "text",
        [
            "Read the next chapter at example.com",
            "Visit us at example.net for more",
            "Next Chapter",
            "Advertisement",
            "Please support us on Patreon",
            "All rights reserved",
        ],
    )
    def test_navigation_and_promo_are_non_diegetic(self, text: str) -> None:
        assert classify_block(text).block_type is BlockType.NON_DIEGETIC

    def test_translator_notes_are_separated(self) -> None:
        out = classify_block("TL Note: 'Gu' refers to a venomous insect.")
        assert out.block_type is BlockType.TRANSLATOR_NOTE

    def test_author_notes_are_separated(self) -> None:
        assert classify_block("Author's Note: sorry for the delay!").block_type is (
            BlockType.AUTHOR_NOTE
        )

    def test_headings_are_headings(self) -> None:
        assert classify_block("Chapter 5", tag="h1").block_type is BlockType.HEADING

    def test_appendix_headings_are_non_diegetic(self) -> None:
        """Back matter describes end-of-volume state and must not enter the graph."""
        for name in ("Pathways Guide", "Characters", "Locations"):
            assert classify_block(name, tag="h1").block_type is BlockType.NON_DIEGETIC

    def test_empty_block_is_non_diegetic(self) -> None:
        assert classify_block("   ").block_type is BlockType.NON_DIEGETIC


class TestSystemWindows:
    def test_bracketed_stat_block_is_detected(self) -> None:
        text = "[ Name: Kim Dokja\nLevel: 7\nStamina: 20 ]"
        assert is_system_window(text)
        fields = parse_system_window(text)
        assert fields["Level"] == "7"
        assert fields["Name"] == "Kim Dokja"

    def test_fields_are_parsed_into_the_block(self) -> None:
        out = classify_block("[ Skill: Fourth Wall\nLevel: 3 ]")
        assert out.block_type is BlockType.SYSTEM_WINDOW
        assert out.system_fields == {"Skill": "Fourth Wall", "Level": "3"}

    def test_prose_with_one_colon_is_not_a_stat_block(self) -> None:
        """Misreading prose as a stat block would inject fabricated attributes
        at the highest-confidence tier in the pipeline."""
        assert not is_system_window("He had one thought: escape.")

    def test_dialogue_is_not_a_stat_block(self) -> None:
        assert not is_system_window('"Elder: I have something to report."')

    def test_cjk_brackets_are_supported(self) -> None:
        assert is_system_window("【 Status: Active\nRank: 3 】")

    def test_unbracketed_without_keywords_is_not_a_window(self) -> None:
        assert not is_system_window("Name: Klein\nAge: 22")


# ---------------------------------------------------------------------------
# Romanization
# ---------------------------------------------------------------------------


class TestNormalization:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("Fang Yuan", "FangYuan"),
            ("Shi-Cheng", "Shi Cheng"),
            ("Lü Bu", "Lu Bu"),
            ("Xi'an", "Xian"),
            ("Tu Shi Cheng", "TuShiCheng"),
        ],
    )
    def test_variants_normalise_together(self, a: str, b: str) -> None:
        assert normalize_romanization(a) == normalize_romanization(b)

    def test_distinct_names_stay_distinct(self) -> None:
        assert normalize_romanization("Fang Yuan") != normalize_romanization("Fang Zheng")

    @pytest.mark.parametrize(
        ("surface", "bare"),
        [
            ("Elder Wang", "Wang"),
            ("Senior Brother Wang", "Wang"),
            ("Sect Master Li", "Li"),
            ("Young Master Chen", "Chen"),
            ("Klein-san", "Klein"),
        ],
    )
    def test_honorifics_are_stripped_for_comparison(self, surface: str, bare: str) -> None:
        assert strip_honorifics(surface) == bare

    def test_stacked_honorifics_are_stripped(self) -> None:
        assert strip_honorifics("Senior Brother Wang-ge") == "Wang"

    def test_comparison_key_combines_both(self) -> None:
        assert comparison_key("Elder Lü Bu") == comparison_key("lubu")

    def test_normalisation_is_a_key_not_a_display_form(self) -> None:
        """The original surface string is always what gets stored."""
        assert normalize_romanization("Fang Yuan") != "Fang Yuan"


# ---------------------------------------------------------------------------
# Emphasis extraction -- the signal that only survives because we chose EPUB
# ---------------------------------------------------------------------------


class TestExtractBlock:
    def parse(self, html: str):  # type: ignore[no-untyped-def]
        return extract_block(lxml_html.fragment_fromstring(html))

    def test_plain_paragraph(self) -> None:
        assert self.parse("<p>Hello there.</p>").text == "Hello there."

    def test_italic_range_is_recorded(self) -> None:
        block = self.parse("<p><i>Where am I?</i> he wondered.</p>")
        start, end = block.italic_ranges[0]
        assert block.text[start:end] == "Where am I?"

    def test_em_counts_as_emphasis(self) -> None:
        block = self.parse("<p>He said <em>no</em> firmly.</p>")
        start, end = block.italic_ranges[0]
        assert block.text[start:end] == "no"

    def test_trailing_text_is_not_marked(self) -> None:
        block = self.parse("<p><i>thought</i> narration</p>")
        start, end = block.italic_ranges[0]
        assert "narration" not in block.text[start:end]

    def test_offsets_are_valid_against_normalised_text(self) -> None:
        block = self.parse("<p>a\n  <i>b   c</i>\n  d</p>")
        for start, end in block.italic_ranges:
            assert 0 <= start < end <= len(block.text)

    def test_no_emphasis_yields_no_ranges(self) -> None:
        assert self.parse("<p>plain</p>").italic_ranges == []

    def test_css_classes_are_captured(self) -> None:
        assert self.parse('<p class="block_7">x</p>').css_classes == ("block_7",)


# ---------------------------------------------------------------------------
# Adapters, against synthetic EPUBs
# ---------------------------------------------------------------------------


def build_epub(path: Path, docs: dict[str, str], toc: list[tuple[str, str]]) -> Path:
    """Write a minimal but valid EPUB."""
    nav = "".join(
        f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{label}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, (label, href) in enumerate(toc)
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f"<docTitle><text>Test</text></docTitle><navMap>{nav}</navMap></ncx>"
    )
    manifest = "".join(
        f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, href in enumerate(docs)
    )
    spine = "".join(f'<itemref idref="d{i}"/>' for i in range(len(docs)))
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Novel</dc:title><dc:language>en</dc:language>"
        '<dc:identifier id="id">test</dc:identifier></metadata>'
        f'<manifest>{manifest}<item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{spine}</spine></package>'
    )
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="book.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("book.opf", opf)
        z.writestr("toc.ncx", ncx)
        for href, body in docs.items():
            z.writestr(href, f"<html><body>{body}</body></html>")
    return path


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


class TestLightNovelWorldAdapter:
    def build(self, tmp_path: Path) -> Path:
        def chapter(n: int, title: str, body: str) -> str:
            return (
                f'<div class="chapter type-1"><div class="chapter-title-wrap">'
                f'<h2 class="chapter-title">Chapter {n}: {title}</h2></div>'
                f'<div class="ugc chapter-ugc"><p><strong>Chapter {n} - {title}</strong></p>'
                f"{body}</div></div>"
            )

        docs = {
            "page-0.html": chapter(1, "First", "<p>Opening narration.</p><p>More.</p>"),
            "page-1.html": chapter(2, "Second", "<p>Second chapter.</p><hr/><p>After break.</p>"),
        }
        toc = [
            ("Information", "page-0.html"),
            ("Table of Contents", "page-0.html"),
            ("Chapter 1: First", "page-0.html"),
            ("Chapter 2: Second", "page-1.html"),
        ]
        return build_epub(tmp_path / "ri.epub", docs, toc)

    def test_front_matter_does_not_suppress_the_novel(self, tmp_path: Path) -> None:
        """'Table of Contents' is front matter, not back matter.

        Latching the appendix flag on it skipped every chapter -- a real bug
        this test pins down.
        """
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("lightnovelworld")(epub, "ri")
        assert len(list(adapter.chapters())) == 2

    def test_chapter_numbers_come_from_the_toc_not_the_filename(self, tmp_path: Path) -> None:
        """page-0.html is Chapter 1."""
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("lightnovelworld")(epub, "ri")
        chapters = list(adapter.chapters())
        assert chapters[0].number == 1.0
        assert chapters[0].source_href == "page-0.html"

    def test_repeated_title_paragraph_is_dropped(self, tmp_path: Path) -> None:
        """Left in, it manufactures a context-free mention at offset 0."""
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("lightnovelworld")(epub, "ri")
        first = next(iter(adapter.chapters()))
        assert not any(b.text.lower().startswith("chapter 1") for b in first.blocks)
        assert first.blocks[0].text == "Opening narration."

    def test_scene_breaks_are_preserved(self, tmp_path: Path) -> None:
        """Free evidence for Phase 2 segmentation."""
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("lightnovelworld")(epub, "ri")
        second = list(adapter.chapters())[1]
        assert any(b.text == "* * *" for b in second.blocks)

    def test_range_filtering(self, tmp_path: Path) -> None:
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("lightnovelworld")(epub, "ri")
        only_first = list(adapter.chapters(ChapterRange.parse("1")))
        assert [c.number for c in only_first] == [1.0]


class TestCalibreAdapter:
    def build(self, tmp_path: Path) -> Path:
        docs = {
            "c1.html": (
                '<h1 class="block_">Chapter 1: Crimson</h1>'
                '<p class="block_7">Narration here.</p>'
                '<p class="block_7"><i class="calibre6">Where am I?</i> he wondered.</p>'
            ),
            "back.html": '<h1 class="block_">Characters</h1><p>Klein Moretti - protagonist</p>',
        }
        toc = [
            ("Front Cover", "c1.html"),
            ("Chapter 1: Crimson", "c1.html"),
            ("Characters", "back.html"),
        ]
        return build_epub(tmp_path / "lotm.epub", docs, toc)

    def test_inner_monologue_emphasis_survives(self, tmp_path: Path) -> None:
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("calibre")(epub, "lotm")
        chapter = next(iter(adapter.chapters()))
        marked = [b for b in chapter.blocks if b.italic_ranges]
        assert marked, "italic markup should be preserved"
        start, end = marked[0].italic_ranges[0]
        assert marked[0].text[start:end].startswith("Where am I")

    def test_chapter_heading_is_dropped(self, tmp_path: Path) -> None:
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("calibre")(epub, "lotm")
        chapter = next(iter(adapter.chapters()))
        assert chapter.blocks[0].text == "Narration here."

    def test_back_matter_after_the_last_chapter_is_excluded(self, tmp_path: Path) -> None:
        """Appendices describe end-of-volume state and would leak reader knowledge."""
        epub = Epub(self.build(tmp_path))
        adapter = get_adapter("calibre")(epub, "lotm")
        assert [c.number for c in adapter.chapters()] == [1.0]


class TestIngestRunner:
    def test_report_counts_and_persists(self, tmp_path: Path, store: Store) -> None:
        docs = {"c1.html": "<h1>Chapter 1: A</h1><p>One.</p><p>Two.</p>"}
        path = build_epub(tmp_path / "g.epub", docs, [("Chapter 1: A", "c1.html")])
        config = SourceConfig(id="g", title="G", path=path, adapter="generic")

        report = ingest_config(config, store)
        assert report.chapters == 1
        assert report.blocks == 2
        assert store.chapter_count("g") == 1

    def test_missing_chapters_are_reported(self, tmp_path: Path, store: Store) -> None:
        """A silently skipped chapter is a hole in the discourse timeline."""
        docs = {"a.html": "<p>One.</p>", "c.html": "<p>Three.</p>"}
        path = build_epub(
            tmp_path / "gap.epub",
            docs,
            [("Chapter 1: A", "a.html"), ("Chapter 3: C", "c.html")],
        )
        config = SourceConfig(id="gap", title="Gap", path=path, adapter="generic")
        assert ingest_config(config, store).missing_chapters == [2.0]


class TestSourcesConfig:
    def test_repo_config_parses(self) -> None:
        sources = load_sources(REPO_ROOT / "data" / "sources.toml")
        assert "reverend-insanity" in sources
        assert sources["reverend-insanity"].chapters == ChapterRange(1.0, 199.0)
        assert sources["lord-of-the-mysteries"].chapters == ChapterRange(1.0, 213.0)

    def test_unknown_novel_lists_the_known_ones(self) -> None:
        from echotales.pipeline.ingest.sources import get_source

        with pytest.raises(KeyError, match="reverend-insanity"):
            get_source("nope", REPO_ROOT / "data" / "sources.toml")

    def test_unknown_adapter_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown adapter"):
            get_adapter("nonexistent")


# ---------------------------------------------------------------------------
# Against the real corpus
# ---------------------------------------------------------------------------


def _corpus_available(novel_id: str) -> bool:
    try:
        sources = load_sources(REPO_ROOT / "data" / "sources.toml")
    except FileNotFoundError:
        return False
    cfg = sources.get(novel_id)
    return bool(cfg and (REPO_ROOT / cfg.path).exists())


@pytest.mark.corpus
@pytest.mark.skipif(
    not _corpus_available("reverend-insanity"), reason="RI EPUB not in data/raw/"
)
class TestRealReverendInsanity:
    def test_ingests_exactly_the_configured_range(self, store: Store) -> None:
        sources = load_sources(REPO_ROOT / "data" / "sources.toml")
        cfg = sources["reverend-insanity"]
        cfg.path = REPO_ROOT / cfg.path
        report = ingest_config(cfg, store)
        assert report.chapters == 199
        assert not report.missing_chapters

    def test_chapter_one_starts_at_narration(self, store: Store) -> None:
        sources = load_sources(REPO_ROOT / "data" / "sources.toml")
        cfg = sources["reverend-insanity"]
        cfg.path = REPO_ROOT / cfg.path
        ingest_config(cfg, store, chapters=ChapterRange.parse("1"))
        chapter = store.get_chapter("reverend-insanity", 1.0)
        assert chapter is not None
        assert not chapter.blocks[0].text.lower().startswith("chapter")


@pytest.mark.corpus
@pytest.mark.skipif(
    not _corpus_available("lord-of-the-mysteries"), reason="LOTM EPUB not in data/raw/"
)
class TestRealLordOfTheMysteries:
    def test_ingests_exactly_volume_one(self, store: Store) -> None:
        sources = load_sources(REPO_ROOT / "data" / "sources.toml")
        cfg = sources["lord-of-the-mysteries"]
        cfg.path = REPO_ROOT / cfg.path
        report = ingest_config(cfg, store)
        assert report.chapters == 213
        assert not report.missing_chapters

    def test_emphasis_markup_is_captured_across_the_volume(self, store: Store) -> None:
        """The inner-monologue signal this source is uniquely good for."""
        sources = load_sources(REPO_ROOT / "data" / "sources.toml")
        cfg = sources["lord-of-the-mysteries"]
        cfg.path = REPO_ROOT / cfg.path
        report = ingest_config(cfg, store)
        assert report.italic_blocks > 500

    def test_appendices_are_excluded(self, store: Store) -> None:
        sources = load_sources(REPO_ROOT / "data" / "sources.toml")
        cfg = sources["lord-of-the-mysteries"]
        cfg.path = REPO_ROOT / cfg.path
        ingest_config(cfg, store)
        numbers = [c.number for c in store.iter_chapters("lord-of-the-mysteries")]
        assert max(numbers) == 213.0
