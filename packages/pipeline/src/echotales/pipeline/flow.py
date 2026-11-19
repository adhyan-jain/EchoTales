"""Data-conservation auditor: does the text a stage was given come out the other side?

A stage that silently drops half a chapter leaves every later stage reporting success, so nothing
measured it. Each check here states one invariant about what a stage must conserve and computes it on
demand from what is stored (plus the source EPUB for ingest). Nothing is written: the auditor adds no
table and opens the database read-only (`open_readonly`).

Adding a stage is appending checks to `CHECKS` under a new `Stage` member.

Ingest coverage method (the one non-obvious comparison): the source side is read independently of the
adapters, as every text node of every spine document's <body> split into whitespace-delimited words
(block-level tags and <br> separate words, inline tags do not, as in `extract_block`). The stored side is
the words of every block of the chapters read from that document. Ingest normalises only whitespace, so
the two word sequences are aligned exactly with difflib; a source word that aligns to nothing is either in
a named exclusion category or a shortfall. Entities are not a tolerance: lxml decodes them identically on
both sides.
"""

from __future__ import annotations

import contextvars
import itertools
import json
import re
import sqlite3
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path
from typing import Any

from echotales.core.enums import BlockType, SpanType
from echotales.core.models import Chapter
from echotales.core.store import Store
from echotales.pipeline.ingest.adapters import ChapterRange
from echotales.pipeline.ingest.adapters.base import BLOCK_TAGS
from echotales.pipeline.ingest.classify import is_appendix_heading
from echotales.pipeline.ingest.epub import Epub, TocEntry, parse_chapter_label
from lxml import etree
from lxml import html as lxml_html

#: Listed shortfalls per check; the true total is always reported beside them.
MAX_LISTED = 20


class Stage(StrEnum):
    INGEST = "ingest"
    SEGMENT = "segment"
    SPANS = "spans"
    MENTIONS = "mentions"
    SPEAKERS = "speakers"
    RESOLVE = "resolve"
    DIRECTOR = "director"


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(slots=True)
class Shortfall:
    chapter: float | None
    location: str
    detail: str
    excerpt: str = ""

    def render(self) -> str:
        who = f"chapter {self.chapter:g}: " if self.chapter is not None else ""
        quoted = f" {self.excerpt!r}" if self.excerpt else ""
        return f"{who}{self.detail} [{self.location}]{quoted}"


@dataclass(slots=True)
class CheckResult:
    stage: Stage
    check_id: str
    invariant: str
    status: Status
    count_in: int = 0
    count_out: int = 0
    unit: str = ""
    shortfalls: list[Shortfall] = field(default_factory=list)
    total_shortfalls: int = 0
    #: Anomalies that do not fail the check (a hint of a parsing fault, a deliberately dropped section).
    warnings: list[str] = field(default_factory=list)
    skipped_reason: str = ""
    #: Named, counted exclusions (ingest coverage) or other measured detail.
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "check": self.check_id,
            "invariant": self.invariant,
            "status": self.status.value,
            "count_in": self.count_in,
            "count_out": self.count_out,
            "unit": self.unit,
            "total_shortfalls": self.total_shortfalls,
            "shortfalls": [
                {"chapter": s.chapter, "location": s.location, "detail": s.detail, "excerpt": s.excerpt}
                for s in self.shortfalls
            ],
            "warnings": self.warnings,
            "skipped_reason": self.skipped_reason,
            "stats": self.stats,
        }


def _excerpt(text: str, limit: int = 80) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# Context: read-only store, and the source EPUB when one can be found
# ---------------------------------------------------------------------------


def open_readonly(path: Path | str) -> Store:
    """A Store over a read-only connection. `Store()` runs the schema script and stamps schema_meta, which would
    write to a database the auditor only inspects, and would create an empty one for a mistyped path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"database not found: {p}")
    store = Store.__new__(Store)
    store.path = str(p)
    store.conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False)
    store.conn.row_factory = sqlite3.Row
    return store


@dataclass(slots=True)
class DocText:
    """One spine document as the auditor reads it, independent of the adapters."""

    words: list[str]
    #: anchor id -> word index at the start of the block holding it (ingest keeps that block on the anchor's side).
    anchors: dict[str, int]


_SEPARATORS = BLOCK_TAGS | {
    "br", "hr", "tr", "td", "th", "table", "ul", "ol", "section", "article", "header", "footer",
    "nav", "aside", "figure", "figcaption", "dl", "dt", "dd", "body", "html",
}
_SKIP_TAGS = {"script", "style", "head", "title"}


def read_doc_text(raw: bytes) -> DocText:
    tree = lxml_html.fromstring(raw)
    body = tree.xpath("//body")
    root = body[0] if body else tree
    words: list[str] = []
    anchors: dict[str, int] = {}
    cur: list[str] = []
    block_start = 0

    def flush() -> None:
        if cur:
            words.append("".join(cur))
            cur.clear()

    def feed(text: str | None) -> None:
        if not text:
            return
        for part in re.split(r"(\s+)", text):
            if not part:
                continue
            if part.isspace():
                flush()
            else:
                cur.append(part)

    def walk(node: etree._Element) -> None:
        nonlocal block_start
        if not isinstance(node.tag, str):
            return
        tag = etree.QName(node).localname.lower()
        if tag in _SKIP_TAGS:
            return
        if tag in _SEPARATORS:
            flush()
            block_start = len(words)
        for key in ("id", "name"):
            if node.get(key):
                anchors.setdefault(node.get(key), block_start)
        feed(node.text)
        for child in node:
            walk(child)
            if isinstance(child.tag, str) and etree.QName(child).localname.lower() in _SEPARATORS:
                flush()
            feed(child.tail)
        if tag in _SEPARATORS:
            flush()

    walk(root)
    flush()
    return DocText(words=words, anchors=anchors)


@dataclass(slots=True)
class SourceContext:
    path: Path
    adapter: str
    chapters: ChapterRange | None
    #: True when no sources config was found and the range was taken from the stored chapters.
    range_inferred: bool = False
    _epub: Epub | None = None
    _docs: dict[str, DocText] = field(default_factory=dict)
    _spine: list[str] | None = None
    _toc: list[TocEntry] | None = None

    @property
    def epub(self) -> Epub:
        if self._epub is None:
            self._epub = Epub(self.path)
        return self._epub

    def close(self) -> None:
        if self._epub is not None:
            self._epub.close()
            self._epub = None

    def spine(self) -> list[str]:
        if self._spine is None:
            self._spine = self.epub.spine()
        return self._spine

    def toc(self) -> list[TocEntry]:
        if self._toc is None:
            self._toc = self.epub.toc()
        return self._toc

    def doc(self, href: str) -> DocText | None:
        if href not in self._docs:
            try:
                self._docs[href] = read_doc_text(self.epub.read(href))
            except KeyError:
                return None
        return self._docs[href]


def resolve_source(
    store: Store,
    novel_id: str,
    *,
    source: str | None = None,
    sources_path: str | None = None,
) -> tuple[SourceContext | None, str]:
    """Find the source EPUB: `--source`, else the sources config, else the path the novel row recorded.
    Returns (context, "") or (None, why-not)."""
    row = store.get_novel(novel_id)
    adapter = (row or {}).get("adapter", "generic")
    wanted: ChapterRange | None = None
    path: Path | None = None
    if sources_path:
        from echotales.pipeline.ingest.sources import get_source

        try:
            cfg = get_source(novel_id, sources_path)
        except (KeyError, FileNotFoundError) as exc:
            return None, f"sources config: {exc}"
        path, adapter, wanted = cfg.path, cfg.adapter, cfg.chapters
    if source:
        path = Path(source)
    elif path is None and row and row.get("source_path"):
        path = Path(row["source_path"])
    if path is None:
        return None, "no source path (pass --source or --sources-path)"
    if not path.exists():
        return None, f"source file not available: {path}"
    inferred = False
    if wanted is None and not sources_path:
        numbers = store.chapter_numbers(novel_id)
        if numbers:
            wanted, inferred = ChapterRange(numbers[0], numbers[-1]), True
    return SourceContext(path=path, adapter=adapter, chapters=wanted, range_inferred=inferred), ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CheckFn = Callable[[Store, str, "SourceContext | None"], CheckResult]


@dataclass(frozen=True, slots=True)
class Check:
    stage: Stage
    check_id: str
    invariant: str
    fn: CheckFn
    needs_source: bool = False


CHECKS: dict[Stage, list[Check]] = {stage: [] for stage in Stage}


def check(stage: Stage, check_id: str, invariant: str, *, needs_source: bool = False):  # type: ignore[no-untyped-def]
    def register(fn: CheckFn) -> CheckFn:
        CHECKS[stage].append(Check(stage, check_id, invariant, fn, needs_source))
        return fn

    return register


def _result(
    chk: Check,
    shortfalls: list[Shortfall],
    *,
    count_in: int = 0,
    count_out: int = 0,
    unit: str = "",
    warnings: list[str] | None = None,
    stats: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        stage=chk.stage,
        check_id=chk.check_id,
        invariant=chk.invariant,
        status=Status.FAIL if shortfalls else Status.PASS,
        count_in=count_in,
        count_out=count_out,
        unit=unit,
        shortfalls=shortfalls[:MAX_LISTED],
        total_shortfalls=len(shortfalls),
        warnings=warnings or [],
        stats=stats or {},
    )


def _skipped(chk: Check, reason: str) -> CheckResult:
    return CheckResult(
        stage=chk.stage, check_id=chk.check_id, invariant=chk.invariant, status=Status.SKIPPED,
        skipped_reason=reason,
    )


def run_checks(
    store: Store,
    novel_id: str,
    source: SourceContext | None,
    *,
    source_reason: str = "",
    stages: list[Stage] | None = None,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for stage in stages or list(Stage):
        for chk in CHECKS[stage]:
            if chk.needs_source and source is None:
                results.append(_skipped(chk, source_reason or "source not available"))
                continue
            try:
                results.append(chk.fn(store, novel_id, source))
            except Exception as exc:  # reported as a FAIL, never swallowed: a crashed check proves nothing
                results.append(
                    CheckResult(
                        stage=chk.stage, check_id=chk.check_id, invariant=chk.invariant,
                        status=Status.FAIL, total_shortfalls=1,
                        shortfalls=[Shortfall(None, "auditor", f"check crashed: {type(exc).__name__}: {exc}")],
                    )
                )
    return results


def _find(stage: Stage, check_id: str) -> Check:
    return next(c for c in CHECKS[stage] if c.check_id == check_id)


# ---------------------------------------------------------------------------
# INGEST
# ---------------------------------------------------------------------------


def _chapters(store: Store, novel_id: str) -> list[Chapter]:
    return list(store.iter_chapters(novel_id))


def _words(chapter: Chapter, *, story_only: bool = False) -> list[str]:
    out: list[str] = []
    for block in chapter.blocks:
        if block.block_type is BlockType.NON_DIEGETIC and block.text == "* * *":
            continue  # synthesised from <hr>; not source text
        if story_only and not block.block_type.is_story_content:
            continue
        out.extend(block.text.split())
    return out


@dataclass(slots=True)
class EntryInfo:
    entry: TocEntry
    number: float | None
    status: str  # stored | unnumbered | out_of_range | back_matter | missing
    lo: int = 0
    hi: int = 0


def classify_entries(
    entries: list[TocEntry], source: SourceContext, stored: set[float]
) -> list[EntryInfo]:
    """Mirror of `SourceAdapter.chapters`' decisions: unnumbered entries are dropped, an appendix heading after the
    first real chapter latches everything after it, and the configured range filters the rest."""
    infos: list[EntryInfo] = []
    in_appendix = False
    seen = False
    for entry in entries:
        parsed = parse_chapter_label(entry.label)
        if parsed.number is None:
            if seen and is_appendix_heading(entry.label):
                in_appendix = True
            infos.append(EntryInfo(entry, None, "back_matter" if in_appendix else "unnumbered"))
            continue
        if in_appendix:
            infos.append(EntryInfo(entry, parsed.number, "back_matter"))
            continue
        seen = True
        if source.chapters is not None and parsed.number not in source.chapters:
            infos.append(EntryInfo(entry, parsed.number, "out_of_range"))
        elif parsed.number in stored:
            infos.append(EntryInfo(entry, parsed.number, "stored"))
        else:
            infos.append(EntryInfo(entry, parsed.number, "missing"))
    return infos


def _windows(infos: list[EntryInfo], href: str, doc: DocText) -> list[EntryInfo]:
    """The entries of one document with their word windows, as `_anchor_window` cuts them."""
    here = [i for i in infos if i.entry.path == href]
    for pos, info in enumerate(here):
        frag = info.entry.fragment
        info.lo = doc.anchors.get(frag, 0) if frag else 0
        info.hi = len(doc.words)
        if frag:
            for later in here[pos + 1 :]:
                if later.entry.fragment and later.entry.fragment != frag and later.entry.fragment in doc.anchors:
                    info.hi = doc.anchors[later.entry.fragment]
                    break
    return here


def _ownership(
    spine: list[str], docs: dict[str, DocText], infos: list[EntryInfo]
) -> list[tuple[str, int, int, EntryInfo | None, bool]]:
    """(document, first word, end word, owning TOC entry, whether the entry points into this document) tiling every
    spine document. Text before a document's first anchor, and a whole document no entry points at, belong to the entry
    that precedes it in the book, provided another entry follows (after the last entry it is licence or colophon, which
    has no chapter to belong to) and that entry is a chapter: an unnumbered entry or back matter keeps what follows it."""
    has_entries = [any(i.entry.path == href for i in infos) for href in spine]
    last_with = max((n for n, flag in enumerate(has_entries) if flag), default=-1)
    out: list[tuple[str, int, int, EntryInfo | None, bool]] = []
    carry: EntryInfo | None = None
    for n, href in enumerate(spine):
        doc = docs.get(href)
        if doc is None:
            continue
        here = _windows(infos, href, doc)
        first = min((i.lo for i in here), default=len(doc.words))
        cuts = sorted({0, len(doc.words), *(p for i in here for p in (i.lo, i.hi))})
        for p, q in itertools.pairwise(cuts):
            owner = next((i for i in here if i.lo <= p < i.hi), None)
            if owner is not None:
                out.append((href, p, q, owner, True))
            elif p < first and n < last_with:
                out.append((href, p, q, carry, False))
            else:
                out.append((href, p, q, None, False))
        if here:
            carry = here[-1]
    return out


def _alnum(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def _is_label_echo(text: str, label: str) -> bool:
    """The dropped heading: the TOC label, or several copies of it (LightNovelWorld prints a heading and a bold
    title paragraph), ignoring punctuation and case."""
    t, lab = _alnum(text), _alnum(label)
    return len(t) >= 3 and bool(lab) and (t in lab or t.replace(lab, "") == "")


def _licence_start(words: list[str]) -> int | None:
    low = [re.sub(r"\W+", "", w.casefold()) for w in words]
    for i in range(len(low) - 3):
        if low[i] == "end" and low[i + 1] == "of" and "gutenberg" in low[i + 2 : i + 6]:
            while i > 0 and not low[i - 1]:  # the "***" fence belongs to the marker
                i -= 1
            return i
    return None


def _chars(words: list[str]) -> int:
    return sum(len(w) for w in words) + max(len(words) - 1, 0)


@check(
    Stage.INGEST,
    "ingest.coverage",
    "every word of every spine document is in exactly one stored block or in a named, counted exclusion",
    needs_source=True,
)
def check_ingest_coverage(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.INGEST, "ingest.coverage")
    assert source is not None
    chapters = _chapters(store, novel_id)
    stored_numbers = {c.number for c in chapters}
    infos = classify_entries(source.toc(), source, stored_numbers)
    total_in = total_matched = total_added = 0
    exclusions: dict[str, int] = {}
    shortfalls: list[Shortfall] = []
    warnings: list[str] = []
    unnumbered_words: dict[str, int] = {}

    def exclude(category: str, n: int) -> None:
        exclusions[category] = exclusions.get(category, 0) + n

    spine = source.spine()
    docs: dict[str, DocText] = {}
    for href in spine:
        doc = source.doc(href)
        if doc is None:
            shortfalls.append(Shortfall(None, href, "spine document is listed in the manifest but cannot be read"))
            continue
        docs[href] = doc
        total_in += len(doc.words)

    # Every source word gets exactly one owner. Text before a document's first anchor, and a document no entry points
    # at, belong to the chapter that began before it, not to "outside the TOC": Pride and Prejudice breaks chapters
    # across files, and those continuations were filed as front matter, so chapters cut short at a file boundary passed.
    pieces = _ownership(spine, docs, infos)
    source_of: dict[float, list[tuple[str, int, int]]] = {}
    for href, lo, hi, owner, in_doc in pieces:
        if owner is not None and owner.status == "stored" and owner.number is not None:
            source_of.setdefault(owner.number, []).append((href, lo, hi))
        else:
            _classify_piece(docs[href], href, owner, in_doc, lo, hi, _licence_start(docs[href].words),
                            exclude, shortfalls, unnumbered_words)

    for chapter in chapters:
        parts = source_of.get(chapter.number, [])
        source_words = [w for href, lo, hi in parts for w in docs[href].words[lo:hi]]
        stored_words = _words(chapter)
        vocab: dict[str, int] = {}
        a = [vocab.setdefault(w, len(vocab)) for w in source_words]
        b = [vocab.setdefault(w, len(vocab)) for w in stored_words]
        sm = SequenceMatcher(None, a, b, autojunk=False)
        # chapter-relative word index -> (document, offset), to cut an unmatched run at the file boundaries
        starts = list(itertools.accumulate((hi - lo for _, lo, hi in parts), initial=0))
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                total_matched += i2 - i1
                continue
            if i2 > i1:
                for n, (href, plo, phi) in enumerate(parts):
                    p, q = max(i1, starts[n]), min(i2, starts[n + 1])
                    if p < q:
                        owner = next(i for i in infos if i.number == chapter.number and i.status == "stored")
                        _classify_piece(
                            docs[href], href, owner, owner.entry.path == href,
                            plo + p - starts[n], plo + q - starts[n], _licence_start(docs[href].words),
                            exclude, shortfalls, unnumbered_words,
                        )
            if j2 > j1:
                total_added += j2 - j1
                shortfalls.append(
                    Shortfall(
                        chapter.number,
                        f"chapter {chapter.number:g}, stored words {j1}-{j2}",
                        f"{j2 - j1} stored words are not in the source document",
                        _excerpt(" ".join(stored_words[j1:j2])),
                    )
                )

    for label, n in unnumbered_words.items():
        if n >= 300:
            warnings.append(f"unnumbered TOC entry {label!r} ({n} words) is not ingested")
    excluded = sum(exclusions.values())
    unaccounted = total_in - total_matched - excluded
    result = _result(
        chk,
        shortfalls,
        count_in=total_in,
        count_out=total_matched,
        unit="words",
        warnings=warnings,
        stats={
            "exclusions_words": dict(sorted(exclusions.items())),
            "unaccounted_words": unaccounted,
            "stored_words_not_in_source": total_added,
            "range_inferred": source.range_inferred,
        },
    )
    return result


def _classify_piece(
    doc: DocText,
    href: str,
    owner: EntryInfo | None,
    in_doc: bool,
    lo: int,
    hi: int,
    licence: int | None,
    exclude: Callable[[str, int], None],
    shortfalls: list[Shortfall],
    unnumbered_words: dict[str, int],
) -> None:
    n = hi - lo
    if owner is None:
        exclude("outside_toc (cover, title page, licence header, navigation)", n)
        return
    label = owner.entry.label
    if owner.status == "unnumbered":
        exclude("unnumbered_toc_entry (front/back matter, prologue, parts)", n)
        unnumbered_words[label] = unnumbered_words.get(label, 0) + n
        return
    if owner.status == "back_matter":
        exclude("back_matter_after_appendix_heading", n)
        return
    if owner.status == "out_of_range":
        exclude("outside_configured_range", n)
        return
    if owner.status == "stored":
        text = " ".join(doc.words[lo:hi])
        if in_doc and lo - owner.lo <= 40 and n <= 80 and _is_label_echo(text, label):
            exclude("chapter_heading_repeating_toc_label", n)
            return
        if licence is not None and lo >= licence:
            exclude("licence_footer", n)
            return
    shortfalls.append(
        Shortfall(
            owner.number,
            f"{href}, source words {lo}-{hi}",
            f"{n:,} words ({_chars(doc.words[lo:hi]):,} characters) reached no block"
            + (" (TOC entry has no stored chapter)" if owner.status == "missing" else ""),
            _excerpt(" ".join(doc.words[lo:hi])),
        )
    )


_SHINGLE = 12


def _repeats(
    words: list[str], number: float, seen: dict[tuple[str, ...], float]
) -> list[tuple[float, int, int]]:
    """(earlier chapter, start, length in words) for each run of shingles this chapter shares with one earlier
    chapter. Registers this chapter's own shingles in `seen` afterwards, so a chapter never matches itself."""
    runs: list[tuple[float, int, int]] = []
    current: tuple[float, int, int] | None = None
    keys = [tuple(words[i : i + _SHINGLE]) for i in range(len(words) - _SHINGLE + 1)]
    for i, key in enumerate(keys):
        first = seen.get(key)
        if first is not None and first != number:
            if current is not None and current[0] == first and current[1] + current[2] - _SHINGLE + 1 == i:
                current = (first, current[1], current[2] + 1)
            else:
                if current is not None:
                    runs.append(current)
                current = (first, i, _SHINGLE)
        elif current is not None:
            runs.append(current)
            current = None
    if current is not None:
        runs.append(current)
    for key in keys:
        seen.setdefault(key, number)
    return runs


def _source_repeats(source: SourceContext, href_a: str, href_b: str, shingle: list[str]) -> bool:
    """Whether the source itself says this passage twice (a recap, a prayer, a recurring system message), so storing
    it under two chapters is faithful rather than a duplication."""
    needle = f" {' '.join(shingle)} "
    counts = 0
    for href in ([href_a] if href_a == href_b else [href_a, href_b]):
        doc = source.doc(href)
        if doc is None:
            return False
        counts += f" {' '.join(doc.words)} ".count(needle)
    return counts >= 2


@check(
    Stage.INGEST,
    "ingest.no_duplicates",
    "no passage of 150 or more words, or half a chapter, of story text is stored under two chapters (shorter "
    "repeats of 30+ words, and any repeat the source itself contains, are warnings: prayers, recaps and recurring "
    "system messages repeat in a novel)",
)
def check_ingest_no_duplicates(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.INGEST, "ingest.no_duplicates")
    min_run, fail_run = 30, 150
    seen: dict[tuple[str, ...], float] = {}
    chapter_words: dict[float, int] = {}
    hrefs: dict[float, str] = {}
    shortfalls: list[Shortfall] = []
    warnings: list[str] = []
    total_words = 0
    for ch in _chapters(store, novel_id):
        words = _words(ch, story_only=True)
        chapter_words[ch.number] = len(words)
        hrefs[ch.number] = ch.source_href
        total_words += len(words)
        for first, start, length in _repeats(words, ch.number, seen):
            if length < min_run:
                continue
            found = Shortfall(
                ch.number,
                f"words {start}-{start + length}",
                f"{length} words repeat chapter {first:g}",
                _excerpt(" ".join(words[start : start + 20])),
            )
            in_source = source is not None and _source_repeats(
                source, hrefs[first], ch.source_href, words[start : start + _SHINGLE]
            )
            long = length >= fail_run or length * 2 >= min(len(words), chapter_words[first])
            if long and not in_source:
                shortfalls.append(found)
            else:
                warnings.append(found.render() + (" (the source repeats it too)" if in_source else ""))
    shown = warnings[:MAX_LISTED]
    if len(warnings) > MAX_LISTED:
        shown.append(f"... {len(warnings) - MAX_LISTED} more short repeats")
    return _result(chk, shortfalls, count_in=total_words, count_out=total_words, unit="story words", warnings=shown,
                   stats={"short_repeats": len(warnings)})


@check(
    Stage.INGEST,
    "ingest.toc_agreement",
    "every numbered in-range TOC entry has exactly one stored chapter, none are extra, and storage follows TOC order",
    needs_source=True,
)
def check_ingest_toc(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.INGEST, "ingest.toc_agreement")
    assert source is not None
    stored = {c.number: c for c in _chapters(store, novel_id)}
    infos = classify_entries(source.toc(), source, set(stored))
    wanted = [i for i in infos if i.status in ("stored", "missing")]
    shortfalls: list[Shortfall] = []
    warnings: list[str] = []
    seen_numbers: dict[float, TocEntry] = {}
    for info in wanted:
        assert info.number is not None
        if info.number in seen_numbers:
            shortfalls.append(
                Shortfall(
                    info.number, info.entry.href,
                    f"TOC entries {seen_numbers[info.number].label!r} and {info.entry.label!r} both parse as "
                    f"chapter {info.number:g}; only one can be stored",
                )
            )
        else:
            seen_numbers[info.number] = info.entry
        if info.status == "missing":
            try:
                source.epub.read(info.entry.path)
                why = "its blocks came out empty"
            except KeyError:
                why = "its document is not in the container"
            shortfalls.append(
                Shortfall(info.number, info.entry.href, f"TOC entry {info.entry.label!r} has no stored chapter ({why})")
            )
    for number in sorted(set(stored) - set(seen_numbers)):
        shortfalls.append(
            Shortfall(number, stored[number].source_href, "stored chapter matches no numbered in-range TOC entry")
        )
    order = [i.number for i in wanted if i.status == "stored" and i.number is not None]
    for prev, cur in itertools.pairwise(order):
        if cur <= prev:
            shortfalls.append(
                Shortfall(cur, "toc order", f"stored chapter {cur:g} follows {prev:g} in the TOC (order disagrees)")
            )
    numbers = sorted(stored)
    holes = [int(a) for a, b in itertools.pairwise(numbers) if int(b) - int(a) > 1]
    if holes:
        warnings.append(f"numbering skips after chapter(s) {', '.join(map(str, holes[:10]))}")
    if source.range_inferred:
        warnings.append("range inferred from stored chapters; pass --sources-path to check the configured range")
    return _result(
        chk, shortfalls, count_in=len(seen_numbers), count_out=len(stored), unit="chapters", warnings=warnings,
        stats={"toc_entries": len(infos), "unnumbered_entries": sum(i.status == "unnumbered" for i in infos)},
    )


@check(
    Stage.INGEST,
    "ingest.chapter_shape",
    "no chapter is empty, every chapter has a title, and chapter numbers are distinct, finite and ascending",
)
def check_ingest_shape(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.INGEST, "ingest.chapter_shape")
    shortfalls: list[Shortfall] = []
    chapters = _chapters(store, novel_id)
    prev: float | None = None
    for ch in chapters:
        if not ch.blocks:
            shortfalls.append(Shortfall(ch.number, ch.source_href, "chapter has no blocks"))
        elif not any(b.text.strip() for b in ch.blocks):
            shortfalls.append(Shortfall(ch.number, ch.source_href, "chapter has only blank blocks"))
        if not ch.title.strip():
            shortfalls.append(Shortfall(ch.number, ch.source_href, "chapter has no title"))
        if ch.number != ch.number or (prev is not None and ch.number <= prev):
            shortfalls.append(Shortfall(ch.number, ch.source_href, f"number does not increase after {prev}"))
        prev = ch.number
    if not chapters:
        shortfalls.append(Shortfall(None, novel_id, "the novel has no stored chapters"))
    return _result(chk, shortfalls, count_in=len(chapters), count_out=len(chapters) - len(shortfalls), unit="chapters")


@check(
    Stage.INGEST,
    "ingest.block_order",
    "block indexes of each chapter are 0..n-1 in order, with no gap and no blank block",
)
def check_ingest_block_order(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.INGEST, "ingest.block_order")
    shortfalls: list[Shortfall] = []
    total = 0
    for ch in _chapters(store, novel_id):
        for pos, block in enumerate(ch.blocks):
            total += 1
            if block.index != pos:
                shortfalls.append(
                    Shortfall(ch.number, f"block position {pos}", f"index is {block.index}, expected {pos}",
                              _excerpt(block.text))
                )
            if not block.text.strip():
                shortfalls.append(Shortfall(ch.number, f"block {pos}", "block text is blank"))
    return _result(chk, shortfalls, count_in=total, count_out=total - len(shortfalls), unit="blocks")


# ---------------------------------------------------------------------------
# SEGMENT
# ---------------------------------------------------------------------------


@check(
    Stage.SEGMENT,
    "segment.tiling",
    "the segments of each chapter tile its blocks: first starts at block 0, each starts right after the previous "
    "ends, the last ends at the final block, none is empty, and each stays in one chapter",
)
def check_segment_tiling(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SEGMENT, "segment.tiling")
    segments = store.get_segments(novel_id)
    if not segments:
        return _skipped(chk, "no segments stored (the segment stage has not run)")
    by_chapter: dict[float, list[Any]] = {}
    shortfalls: list[Shortfall] = []
    for seg in segments:
        if seg.chapter_from != seg.chapter_to:
            shortfalls.append(Shortfall(seg.chapter_from, seg.id, f"segment spans chapters {seg.chapter_from:g}-{seg.chapter_to:g}"))
            continue
        by_chapter.setdefault(seg.chapter_from, []).append(seg)
    blocks_covered = blocks_total = 0
    known: set[float] = set()
    for ch in _chapters(store, novel_id):
        known.add(ch.number)
        n_blocks = len(ch.blocks)
        blocks_total += n_blocks
        segs = sorted(by_chapter.get(ch.number, []), key=lambda s: (s.offset_from, s.offset_to))
        if not segs:
            shortfalls.append(Shortfall(ch.number, "segments", f"no segment covers its {n_blocks} blocks"))
            continue
        cursor = 0
        for seg in segs:
            if seg.offset_to < seg.offset_from:
                shortfalls.append(Shortfall(ch.number, seg.id, f"empty segment (blocks {seg.offset_from}-{seg.offset_to})"))
                continue
            if seg.offset_from > cursor:
                shortfalls.append(
                    Shortfall(ch.number, seg.id, f"blocks {cursor}-{seg.offset_from - 1} belong to no segment",
                              _excerpt(ch.blocks[cursor].text) if cursor < n_blocks else "")
                )
            elif seg.offset_from < cursor:
                shortfalls.append(
                    Shortfall(ch.number, seg.id, f"blocks {seg.offset_from}-{min(cursor, seg.offset_to + 1) - 1} belong to two segments")
                )
            blocks_covered += max(0, min(seg.offset_to, n_blocks - 1) - max(seg.offset_from, cursor) + 1)
            cursor = max(cursor, seg.offset_to + 1)
        if cursor < n_blocks:
            shortfalls.append(
                Shortfall(ch.number, "end of chapter", f"blocks {cursor}-{n_blocks - 1} belong to no segment",
                          _excerpt(ch.blocks[cursor].text))
            )
        elif cursor > n_blocks:
            shortfalls.append(Shortfall(ch.number, "end of chapter", f"a segment ends at block {cursor - 1} but the chapter has {n_blocks}"))
    for number in sorted(set(by_chapter) - known):
        shortfalls.append(Shortfall(number, "segments", "segments exist for a chapter that is not stored"))
    return _result(chk, shortfalls, count_in=blocks_total, count_out=blocks_covered, unit="blocks")


# ---------------------------------------------------------------------------
# SPANS
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _SpanRow:
    block_index: int
    start: int
    end: int
    text: str
    span_type: str
    id: str


def _computed_spans(chapter: Chapter) -> list[_SpanRow]:
    from echotales.pipeline.spans import classify_chapter

    return [
        _SpanRow(s.block_index, s.start, s.end, s.text, str(s.span_type), s.id)
        for s in classify_chapter(chapter)
    ]


def _stored_spans(store: Store, chapter: Chapter) -> list[_SpanRow]:
    # A plain SELECT, not `store.get_spans`: that validates each row into a Span, so one bad span_type would crash
    # the audit instead of being reported by `spans.typed`.
    rows = store.conn.execute(
        "SELECT id, block_index, start, end, span_type, text FROM span WHERE novel_id=? AND chapter=?"
        " ORDER BY block_index, start",
        (chapter.novel_id, chapter.number),
    )
    return [_SpanRow(r["block_index"], r["start"], r["end"], r["text"], r["span_type"], r["id"]) for r in rows]


def _tile_chapter(chapter: Chapter, spans: list[_SpanRow]) -> tuple[list[Shortfall], int, int]:
    """Returns (shortfalls, characters in blocks, characters inside spans).

    A span's text is exactly its [start:end) slice (mention offsets are built from span.start); the only characters
    left uncovered are whitespace between spans."""
    shortfalls: list[Shortfall] = []
    per_block: dict[int, list[_SpanRow]] = {}
    for s in spans:
        per_block.setdefault(s.block_index, []).append(s)
    n_chars = n_covered = 0
    by_index = {b.index: b for b in chapter.blocks}
    for idx in sorted(set(per_block) - set(by_index)):
        shortfalls.append(Shortfall(chapter.number, f"block {idx}", "spans refer to a block the chapter does not have"))
    for block in chapter.blocks:
        text = block.text
        n_chars += len(text)
        rows = sorted(per_block.get(block.index, []), key=lambda r: (r.start, r.end))
        if not rows:
            if text.strip():
                shortfalls.append(Shortfall(chapter.number, f"block {block.index}", "block has no span", _excerpt(text)))
            continue
        cursor = 0
        joined: list[str] = []
        for r in rows:
            if not (0 <= r.start < r.end <= len(text)):
                shortfalls.append(
                    Shortfall(chapter.number, f"block {block.index}, span {r.id}",
                              f"span range {r.start}-{r.end} is outside the block (length {len(text)})")
                )
                continue
            if r.start < cursor:
                shortfalls.append(
                    Shortfall(chapter.number, f"block {block.index}, span {r.id}",
                              f"overlaps the previous span by {cursor - r.start} characters",
                              _excerpt(text[r.start : cursor]))
                )
            elif text[cursor : r.start].strip():
                shortfalls.append(
                    Shortfall(chapter.number, f"block {block.index}, chars {cursor}-{r.start}",
                              f"{len(text[cursor : r.start].strip())} characters reach no span",
                              _excerpt(text[cursor : r.start]))
                )
            if r.text != text[r.start : r.end]:
                shortfalls.append(
                    Shortfall(chapter.number, f"block {block.index}, span {r.id}",
                              "span text differs from the block slice it claims", _excerpt(r.text))
                )
            n_covered += r.end - r.start
            cursor = max(cursor, r.end)
            joined.append(r.text)
        if text[cursor:].strip():
            shortfalls.append(
                Shortfall(chapter.number, f"block {block.index}, chars {cursor}-{len(text)}",
                          f"{len(text[cursor:].strip())} trailing characters reach no span", _excerpt(text[cursor:]))
            )
        if "".join("".join(joined).split()) != "".join(text.split()) and not any(
            "reach no span" in s.detail or "overlaps" in s.detail for s in shortfalls[-3:]
        ):
            shortfalls.append(
                Shortfall(chapter.number, f"block {block.index}", "concatenated span texts do not reproduce the block",
                          _excerpt(text))
            )
    return shortfalls, n_chars, n_covered


@check(
    Stage.SPANS,
    "spans.tiling",
    "the spans of each block (as classify_chapter builds them from the stored blocks) tile its text with no gap and "
    "no overlap; a span's text is exactly its [start:end) slice and only whitespace between spans is uncovered",
)
def check_spans_tiling(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPANS, "spans.tiling")
    shortfalls: list[Shortfall] = []
    chars = covered = n_spans = 0
    for ch in _chapters(store, novel_id):
        rows = _computed_spans(ch)
        n_spans += len(rows)
        found, c, k = _tile_chapter(ch, rows)
        shortfalls += found
        chars += c
        covered += k
    return _result(chk, shortfalls, count_in=chars, count_out=covered, unit="characters", stats={"spans": n_spans})


@check(
    Stage.SPANS,
    "spans.stored_rows",
    "the span rows stored in the database (written once speakers are attributed) tile their blocks the same way",
)
def check_spans_stored(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPANS, "spans.stored_rows")
    if not store.conn.execute("SELECT 1 FROM span WHERE novel_id=? LIMIT 1", (novel_id,)).fetchone():
        return _skipped(chk, "no span rows stored (speaker attribution has not run)")
    shortfalls: list[Shortfall] = []
    warnings: list[str] = []
    chars = covered = 0
    without: list[str] = []
    for ch in _chapters(store, novel_id):
        rows = _stored_spans(store, ch)
        if not rows:
            without.append(f"{ch.number:g}")
            continue
        found, c, k = _tile_chapter(ch, rows)
        shortfalls += found
        chars += c
        covered += k
    if without:
        warnings.append(f"{len(without)} chapters have no stored spans yet: {', '.join(without[:10])}")
    return _result(chk, shortfalls, count_in=chars, count_out=covered, unit="characters", warnings=warnings)


@check(Stage.SPANS, "spans.typed", "every span has a type from the SpanType vocabulary and non-empty text")
def check_spans_typed(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPANS, "spans.typed")
    valid = {t.value for t in SpanType}
    shortfalls: list[Shortfall] = []
    total = 0
    stored = store.conn.execute("SELECT 1 FROM span WHERE novel_id=? LIMIT 1", (novel_id,)).fetchone() is not None
    for ch in _chapters(store, novel_id):
        rows = _stored_spans(store, ch) if stored else _computed_spans(ch)
        for r in rows:
            total += 1
            if r.span_type not in valid:
                shortfalls.append(Shortfall(ch.number, r.id, f"unknown span type {r.span_type!r}", _excerpt(r.text)))
            if not r.text.strip():
                shortfalls.append(Shortfall(ch.number, r.id, "span text is empty"))
    return _result(chk, shortfalls, count_in=total, count_out=total - len(shortfalls), unit="spans")


_QUOTE_PAIRS = (("“", "”"), ("«", "»"), ("「", "」"), ("『", "』"))


def quote_imbalances(chapter: Chapter) -> list[Shortfall]:
    """Quote marks that do not pair up across the chapter. A paragraph that ends inside a quote and the next one
    opening with a quote mark again is the printed convention for a speech over several paragraphs, not an error."""
    out: list[Shortfall] = []
    for opener, closer in _QUOTE_PAIRS:
        depth = 0
        for block in chapter.blocks:
            if not block.block_type.is_story_content:
                continue
            text = block.text
            if depth > 0 and text.lstrip().startswith(opener):
                depth = 0
            for i, ch in enumerate(text):
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    if depth == 0:
                        out.append(Shortfall(chapter.number, f"block {block.index}, char {i}",
                                             f"closing {closer} with nothing open", _excerpt(text[max(0, i - 40) : i + 20])))
                    else:
                        depth -= 1
        if depth > 0:
            last = next((b for b in reversed(chapter.blocks) if opener in b.text), None)
            out.append(Shortfall(chapter.number, f"block {last.index if last else '?'}",
                                 f"{depth} opening {opener} never closed", _excerpt(last.text if last else "")))
    straight_open = False
    for block in chapter.blocks:
        if not block.block_type.is_story_content:
            continue
        count = block.text.count('"')
        if straight_open and block.text.lstrip().startswith('"'):
            straight_open = False
        straight_open ^= bool(count % 2)
    if straight_open:
        out.append(Shortfall(chapter.number, "end of chapter", 'a straight " quote is never closed'))
    return out


@check(
    Stage.SPANS,
    "spans.quote_balance",
    "quotation marks pair up within each chapter (imbalances are warnings: a source fault, not lost text)",
)
def check_spans_quotes(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPANS, "spans.quote_balance")
    warnings: list[str] = []
    chapters = 0
    flagged = 0
    for ch in _chapters(store, novel_id):
        chapters += 1
        found = quote_imbalances(ch)
        if found:
            flagged += 1
        warnings += [s.render() for s in found]
    shown = warnings[:MAX_LISTED]
    if len(warnings) > MAX_LISTED:
        shown.append(f"... {len(warnings) - MAX_LISTED} more quote imbalances")
    return _result(chk, [], count_in=chapters, count_out=chapters - flagged, unit="chapters", warnings=shown,
                   stats={"imbalances": len(warnings)})


@check(
    Stage.SPANS,
    "spans.type_profile",
    "per-chapter span-type counts; a chapter whose dialogue share is an extreme outlier is flagged (a hint of "
    "quote-parsing failure, warning only)",
)
def check_spans_profile(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPANS, "spans.type_profile")
    per_chapter: dict[str, dict[str, int]] = {}
    shares: dict[float, float] = {}
    for ch in _chapters(store, novel_id):
        counts: dict[str, int] = {}
        story_chars = dialogue_chars = 0
        for s in _computed_spans(ch):
            counts[s.span_type] = counts.get(s.span_type, 0) + 1
            if s.span_type not in (SpanType.NON_DIEGETIC.value, SpanType.SYSTEM_WINDOW.value):
                story_chars += len(s.text)
                dialogue_chars += len(s.text) if s.span_type == SpanType.DIALOGUE.value else 0
        per_chapter[f"{ch.number:g}"] = counts
        if story_chars >= 400:
            shares[ch.number] = dialogue_chars / story_chars
    warnings: list[str] = []
    if len(shares) >= 8:
        med = statistics.median(shares.values())
        mad = statistics.median(abs(v - med) for v in shares.values())
        for number, share in sorted(shares.items()):
            z = 0.6745 * (share - med) / max(mad, 0.03)
            if abs(z) >= 4 and abs(share - med) >= 0.25:
                warnings.append(
                    f"chapter {number:g}: dialogue share {share:.0%} against a book median of {med:.0%}"
                )
    return _result(chk, [], count_in=len(per_chapter), count_out=len(per_chapter), unit="chapters",
                   warnings=warnings, stats={"span_types_per_chapter": per_chapter})


# ---------------------------------------------------------------------------
# MENTIONS
# ---------------------------------------------------------------------------

#: The corrections log for r4, set by `audit_novel` (`--corrections`); None means the check is skipped.
_corrections_path: contextvars.ContextVar[str | None] = contextvars.ContextVar("corrections_path", default=None)

_QUOTED = (SpanType.DIALOGUE.value, SpanType.INNER_MONOLOGUE.value, SpanType.CROWD_REACTION.value)


def _mention_rows(store: Store, novel_id: str) -> list[sqlite3.Row]:
    # Plain SELECT, not `store.get_mentions`: that validates every row into a Mention, so one bad enum value would
    # crash the audit instead of being reported.
    return store.conn.execute(
        "SELECT id, chapter, block_index, offset, text, alias_type, span_type, target_kind, target_id, method,"
        " local_group_id, provenance, entity_label FROM mention WHERE novel_id=? ORDER BY chapter, block_index, offset",
        (novel_id,),
    ).fetchall()


def _has_mentions(store: Store, novel_id: str) -> bool:
    return store.conn.execute("SELECT 1 FROM mention WHERE novel_id=? LIMIT 1", (novel_id,)).fetchone() is not None


def _nearest(block: str, text: str, offset: int) -> int | None:
    """Start of the occurrence of `text` in `block` closest to `offset`, or None."""
    best: int | None = None
    pos = block.find(text)
    while pos >= 0:
        if best is None or abs(pos - offset) < abs(best - offset):
            best = pos
        pos = block.find(text, pos + 1)
    return best


@check(
    Stage.MENTIONS,
    "mentions.offsets",
    "every stored mention lies inside its block and its (block_index, offset, length) selects exactly its text",
)
def check_mentions_offsets(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.MENTIONS, "mentions.offsets")
    rows = _mention_rows(store, novel_id)
    if not rows:
        return _skipped(chk, "no mentions stored (the mentions stage has not run)")
    blocks = {(c.number, b.index): b.text for c in _chapters(store, novel_id) for b in c.blocks}
    shortfalls: list[Shortfall] = []
    shifts: dict[int, int] = {}
    ok = 0
    for r in rows:
        text = blocks.get((r["chapter"], r["block_index"]))
        where = f"{r['id']}, block {r['block_index']}, offset {r['offset']}"
        if text is None:
            shortfalls.append(Shortfall(r["chapter"], where, "mention refers to a block the chapter does not have",
                                        _excerpt(r["text"])))
            continue
        end = r["offset"] + len(r["text"])
        if r["offset"] < 0 or end > len(text):
            shortfalls.append(Shortfall(r["chapter"], where, f"range ends at {end} but the block has {len(text)} characters",
                                        _excerpt(r["text"])))
        elif text[r["offset"]:end] == r["text"]:
            ok += 1
            continue
        else:
            near = _nearest(text, r["text"], r["offset"])
            shift = None if near is None else near - r["offset"]
            if shift is not None:
                shifts[shift] = shifts.get(shift, 0) + 1
            shortfalls.append(
                Shortfall(r["chapter"], where,
                          f"offsets select {text[r['offset']:end]!r}, not the mention text; "
                          + (f"the text sits {shift:+d} characters away" if shift is not None else "the text is not in the block"),
                          _excerpt(r["text"]))
            )
    return _result(chk, shortfalls, count_in=len(rows), count_out=ok, unit="mentions",
                   stats={"shift_histogram": dict(sorted(shifts.items(), key=lambda kv: -kv[1])[:10])})


@check(
    Stage.MENTIONS,
    "mentions.no_overlap",
    "no two mentions of one block overlap (the runner replaces a gazetteer hit by the longer name containing it, "
    "so nesting is never intended)",
)
def check_mentions_overlap(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.MENTIONS, "mentions.no_overlap")
    rows = _mention_rows(store, novel_id)
    if not rows:
        return _skipped(chk, "no mentions stored (the mentions stage has not run)")
    shortfalls: list[Shortfall] = []
    prev: sqlite3.Row | None = None
    prev_end = 0
    for r in rows:  # ordered by chapter, block, offset
        same_block = prev is not None and (prev["chapter"], prev["block_index"]) == (r["chapter"], r["block_index"])
        if same_block and prev is not None and r["offset"] < prev_end:
            shortfalls.append(
                Shortfall(r["chapter"], f"block {r['block_index']}, offset {r['offset']}",
                          f"{r['text']!r} overlaps {prev['text']!r} ({prev['id']}) by {prev_end - r['offset']} characters",
                          _excerpt(r["text"]))
            )
        end = r["offset"] + len(r["text"])
        if not same_block or end > prev_end:
            prev, prev_end = r, end
    return _result(chk, shortfalls, count_in=len(rows), count_out=len(rows) - len(shortfalls), unit="mentions")


_NAME_RUN = re.compile(r"\b[A-Z][a-z’'\-]+(?:\s+(?:of|the|de|van|von)\s+[A-Z][a-z’'\-]+|\s+[A-Z][a-z’'\-]+)+\b")


@check(
    Stage.MENTIONS,
    "mentions.name_coverage",
    "every capitalised multi-token name and every surface the detector learned occurs only where a mention covers it, "
    "or in a counted exclusion (warning only: a heuristic cannot prove a missed name)",
)
def check_mentions_coverage(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    from echotales.pipeline.mentions.alias_type import classify_alias_type
    from echotales.pipeline.mentions.commonness import build_profile, looks_like_credit
    from echotales.pipeline.mentions.ner import _STOPWORDS

    chk = _find(Stage.MENTIONS, "mentions.name_coverage")
    rows = _mention_rows(store, novel_id)
    if not rows:
        return _skipped(chk, "no mentions stored (the mentions stage has not run)")
    chapters = _chapters(store, novel_id)
    covered: dict[tuple[float, int], list[tuple[int, int]]] = {}
    first_chapter: dict[str, float] = {}
    for r in rows:
        covered.setdefault((r["chapter"], r["block_index"]), []).append((r["offset"], r["offset"] + len(r["text"])))
        if r["alias_type"] == "RIGID_NAME" and r["text"] not in first_chapter:
            first_chapter[r["text"]] = r["chapter"]
    learned = sorted((t for t in first_chapter if len(t) >= 3), key=len, reverse=True)
    learned_re = re.compile(r"(?<![\w’'])(?:" + "|".join(map(re.escape, learned[:3000])) + r")(?![\w’'])") if learned else None
    # A mention whose offsets are shifted (mentions.offsets) still covers the text it names.
    for r in rows:
        text = next((b.text for c in chapters if c.number == r["chapter"] for b in c.blocks if b.index == r["block_index"]), None)
        if text is not None and text[r["offset"]: r["offset"] + len(r["text"])] != r["text"]:
            near = _nearest(text, r["text"], r["offset"])
            if near is not None:
                covered[(r["chapter"], r["block_index"])].append((near, near + len(r["text"])))
    found: dict[str, list[tuple[float, int, str]]] = {}
    for ch in chapters:
        for b in ch.blocks:
            if not b.block_type.is_story_content:
                continue
            spans = covered.get((ch.number, b.index), [])
            cands = [(m.start(), m.end(), m.group(0)) for m in _NAME_RUN.finditer(b.text)]
            if learned_re:
                cands += [(m.start(), m.end(), m.group(0)) for m in learned_re.finditer(b.text)]
            for lo, hi, surf in cands:
                toks = [t for t in surf.split() if t not in _STOPWORDS]
                if not toks or any(s < hi and lo < e for s, e in spans):
                    continue
                found.setdefault(" ".join(toks), []).append((ch.number, b.index, b.text[max(0, lo - 30): hi + 30]))
    exclusions: dict[str, int] = {}
    top = sorted(found.items(), key=lambda kv: -len(kv[1]))[:300]
    profile = build_profile("\n".join(c.story_text for c in chapters), [s for s, _ in top]) if top else None
    uncovered: list[tuple[str, int]] = []
    for surf, occ in sorted(found.items(), key=lambda kv: -len(kv[1])):
        reason = ""
        if surf in first_chapter and all(n < first_chapter[surf] for n, _, _ in occ):
            reason = "before_first_detection (the gazetteer learns forward only)"
        elif not classify_alias_type(surf)[0].enters_graph:
            reason = "generic_descriptor (non-negotiable 4)"
        elif looks_like_credit(surf):
            reason = "translation_credit"
        elif profile is not None and surf in dict(top) and profile.is_common_noun(surf):
            reason = "common_noun_filter"
        elif len(surf.split()) == 1:
            reason = "single_token_after_stopword_strip"
        if reason:
            exclusions[reason] = exclusions.get(reason, 0) + len(occ)
        else:
            uncovered.append((surf, len(occ)))
    warnings = [f"{n}x {s!r} occurs uncovered (e.g. chapter {found[s][0][0]:g}: {_excerpt(found[s][0][2])!r})"
                for s, n in uncovered[:10]]
    if len(uncovered) > 10:
        warnings.append(f"... {len(uncovered) - 10} more uncovered surfaces ({sum(n for _, n in uncovered)} occurrences)")
    return _result(chk, [], count_in=sum(len(v) for v in found.values()),
                   count_out=sum(n for _, n in uncovered), unit="uncovered occurrences (out) of candidates (in)",
                   warnings=warnings,
                   stats={"exclusions_occurrences": dict(sorted(exclusions.items())),
                          "top_uncovered": uncovered[:15], "uncovered_surfaces": len(uncovered),
                          "note": "rejected candidates (generic, common noun, credit) are counted only in the "
                                  "stage's in-memory report, never stored; the exclusions above are re-derived"})


@check(
    Stage.MENTIONS,
    "mentions.chapter_coverage",
    "every chapter with story text has at least one mention (a chapter with none under 1500 story characters is "
    "only a warning)",
)
def check_mentions_chapters(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.MENTIONS, "mentions.chapter_coverage")
    if not _has_mentions(store, novel_id):
        return _skipped(chk, "no mentions stored (the mentions stage has not run)")
    have = {r[0] for r in store.conn.execute("SELECT DISTINCT chapter FROM mention WHERE novel_id=?", (novel_id,))}
    shortfalls: list[Shortfall] = []
    warnings: list[str] = []
    with_text = 0
    for ch in _chapters(store, novel_id):
        chars = len(ch.story_text.strip())
        if not chars:
            continue
        with_text += 1
        if ch.number in have:
            continue
        found = Shortfall(ch.number, ch.source_href, f"no mention in a chapter with {chars:,} story characters",
                          _excerpt(ch.story_text))
        if chars >= 1500:
            shortfalls.append(found)
        else:
            warnings.append(found.render())
    return _result(chk, shortfalls, count_in=with_text, count_out=with_text - len(shortfalls) - len(warnings),
                   unit="chapters", warnings=warnings)


@check(
    Stage.MENTIONS,
    "mentions.ner_coverage",
    "if the NER tier ran, every chapter was sent to it under the current window geometry and nothing failed "
    "(evidence: llm_call rows for task 'ner', else the per-chapter name cache)",
)
def check_mentions_ner(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    from echotales.pipeline.config import get_settings
    from echotales.pipeline.mentions.chapter_ner import (
        CHUNK_CHARS,
        PLAUSIBILITY_VERSION,
        chunk_text,
    )
    from echotales.pipeline.mentions.ner import _windows, ner_pass_fingerprint

    chk = _find(Stage.MENTIONS, "mentions.ner_coverage")
    calls: dict[float, int] = {}
    for r in store.conn.execute(
        "SELECT chapter, COUNT(*) AS n FROM llm_call WHERE novel_id=? AND stage='ner' GROUP BY chapter", (novel_id,)
    ):
        calls[r["chapter"]] = r["n"]
    cache: dict[str, Any] = {}
    cache_path = Path(get_settings().lexicon_path) / f"{novel_id}-ner-cache.json"
    try:
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    except (OSError, ValueError):
        cache = {}
    if not calls and not cache:
        return _skipped(chk, "the NER tier did not run: no llm_call rows for task 'ner' and no name cache at "
                             f"{cache_path} (a deterministic or cache-less run records nothing else)")
    import hashlib

    current = f"{ner_pass_fingerprint()}:{PLAUSIBILITY_VERSION}"
    keys = {k.rsplit(":", 1)[1]: k.rsplit(":", 1)[0] for k in cache}
    shortfalls: list[Shortfall] = []
    warnings: list[str] = []
    chapters = _chapters(store, novel_id)
    covered = stale = 0
    for ch in chapters:
        text = ch.story_text
        expected = sum(len(_windows(c)) for c in chunk_text(text, CHUNK_CHARS))
        if not expected:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        prefix = keys.get(digest)
        n = calls.get(ch.number, 0)
        if prefix is not None and not prefix.endswith(current):
            stale += 1
            warnings.append(f"chapter {ch.number:g}: name cache entry was made under another window geometry or filter")
        if n and n < expected:
            shortfalls.append(Shortfall(ch.number, "llm_call", f"{n} NER calls logged but {expected} windows were needed "
                                                              f"for {len(text):,} characters"))
        elif not n and prefix is None:
            shortfalls.append(Shortfall(ch.number, "llm_call", f"no NER call and no cache entry for a chapter of "
                                                              f"{len(text):,} characters ({expected} windows)"))
        else:
            covered += 1
    warnings.append("a failed chunk is logged to the Python log only and its names are dropped; llm_call records "
                    "successes only, so a chapter with some calls cannot be proven complete beyond the window count")
    return _result(chk, shortfalls, count_in=len(chapters), count_out=covered, unit="chapters", warnings=warnings,
                   stats={"chapters_with_llm_calls": len(calls), "cache_entries": len(cache),
                          "stale_cache_chapters": stale})


# ---------------------------------------------------------------------------
# SPEAKERS (and anaphora)
# ---------------------------------------------------------------------------

#: Methods that assert an identity; with no speaker they are a lie (the runner writes the method and the speaker
#: together, `speakers/runner.py::attribute_novel`).
_NO_IDENTITY_METHODS = frozenset({"UNRESOLVED", "UNATTRIBUTED_CHORUS"})
_SLOT_KINDS = ("anon", "epithet", "title")


def _entity_ids(store: Store, novel_id: str) -> set[str]:
    return {r[0] for r in store.conn.execute("SELECT id FROM self_entity WHERE novel_id=?", (novel_id,))}


def _span_rows(store: Store, novel_id: str) -> list[sqlite3.Row]:
    return store.conn.execute(
        "SELECT id, chapter, block_index, start, span_type, text, speaker_self_id, attribution_method, confidence,"
        " co_speaker_json FROM span WHERE novel_id=? ORDER BY chapter, block_index, start", (novel_id,)
    ).fetchall()


def _surface_keys(store: Store, novel_id: str) -> set[str]:
    """Comparison keys of every entity label and mention text: what an attributed speaker surface can resolve to."""
    from echotales.pipeline.ingest.normalize import comparison_key

    texts = [r[0] for r in store.conn.execute("SELECT canonical_label FROM self_entity WHERE novel_id=?", (novel_id,))]
    texts += [r[0] for r in store.conn.execute("SELECT DISTINCT text FROM mention WHERE novel_id=?", (novel_id,))]
    keys = {comparison_key(t) for t in texts}
    keys |= {comparison_key(w) for t in texts for w in t.split() if len(w) >= 3}  # "Alice" for "Alice Smith"
    return keys - {""}


def _speaker_kind(novel_id: str, speaker: str, entities: set[str], keys: set[str] | None = None) -> str:
    """'entity', a slot kind ('anon'...), 'surface' (a name string: the ladder stores the attributed surface in
    `speaker_self_id`, persona/build.py:136) or 'dangling' (a missing entity id, or a surface that no entity or mention
    in the book carries)."""
    from echotales.pipeline.ingest.normalize import comparison_key

    if speaker in entities:
        return "entity"
    for kind in _SLOT_KINDS:
        if speaker.startswith(f"{novel_id}:{kind}:"):
            return kind
    if speaker.startswith(f"{novel_id}:"):
        return "dangling"
    return "surface" if keys is not None and comparison_key(speaker) in keys else "dangling"


def _no_spans(store: Store, novel_id: str) -> bool:
    return store.conn.execute("SELECT 1 FROM span WHERE novel_id=? LIMIT 1", (novel_id,)).fetchone() is None


@check(
    Stage.SPEAKERS,
    "speakers.dialogue_end_state",
    "every quoted span (DIALOGUE, INNER_MONOLOGUE, CROWD_REACTION: the types the ladder attributes) ends in an existing "
    "entity or a slot id with a method that names it, or an explicit UNRESOLVED / UNATTRIBUTED_CHORUS with no speaker; "
    "never a method claiming an identity with no speaker, nor a speaker that is no entity (dangling or a surface string)",
)
def check_speakers_end_state(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPEAKERS, "speakers.dialogue_end_state")
    if _no_spans(store, novel_id):
        return _skipped(chk, "no span rows stored (speaker attribution has not run)")
    entities = _entity_ids(store, novel_id)
    keys = _surface_keys(store, novel_id)
    resolved_ran = bool(entities)
    shortfalls: list[Shortfall] = []
    total = 0
    kinds: dict[str, int] = {}
    for r in _span_rows(store, novel_id):
        if r["span_type"] not in _QUOTED:
            continue
        total += 1
        sp, method = r["speaker_self_id"], r["attribution_method"]
        where = f"span {r['id']}, block {r['block_index']}"
        if sp:
            kind = _speaker_kind(novel_id, sp, entities, keys)
            kinds[kind] = kinds.get(kind, 0) + 1
            if kind == "dangling":
                if not resolved_ran:
                    continue  # no entity table yet: a speaker cannot dangle before resolve has run
                looks_like_id = sp.startswith(f"{novel_id}:")
                shortfalls.append(Shortfall(r["chapter"], where,
                                            (f"speaker id {sp!r} points at no entity (deleted by a re-resolve?)"
                                             if looks_like_id else
                                             f"speaker surface {sp!r} matches no entity label or mention text"),
                                            _excerpt(r["text"])))
            if method in _NO_IDENTITY_METHODS:
                shortfalls.append(Shortfall(r["chapter"], where, f"method {method} but speaker {sp!r} is set", _excerpt(r["text"])))
        elif method not in _NO_IDENTITY_METHODS:
            shortfalls.append(Shortfall(r["chapter"], where, f"method {method} claims an attribution but there is no speaker",
                                        _excerpt(r["text"])))
        for co in json.loads(r["co_speaker_json"] or "[]"):
            if resolved_ran and _speaker_kind(novel_id, co, entities, keys) == "dangling":
                shortfalls.append(Shortfall(r["chapter"], where, f"co-speaker {co!r} points at no entity", _excerpt(r["text"])))
    warnings = [] if resolved_ran else ["no entities stored yet (resolve has not run): dangling speaker ids cannot be judged"]
    if kinds.get("surface"):
        warnings.append(f"{kinds['surface']} quoted spans store a speaker name string, not an entity id (the documented "
                        "model, persona/build.py:136); they resolve to an entity only by name comparison")
    return _result(chk, shortfalls, count_in=total, count_out=total - len({s.location for s in shortfalls}), unit="quoted spans",
                   warnings=warnings, stats={"speaker_kinds": kinds})


@check(Stage.SPEAKERS, "speakers.narration_has_no_speaker",
       "no span outside the quoted types carries a speaker or co-speaker")
def check_speakers_narration(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPEAKERS, "speakers.narration_has_no_speaker")
    if _no_spans(store, novel_id):
        return _skipped(chk, "no span rows stored (speaker attribution has not run)")
    shortfalls: list[Shortfall] = []
    total = 0
    for r in _span_rows(store, novel_id):
        if r["span_type"] in _QUOTED:
            continue
        total += 1
        if r["speaker_self_id"] or json.loads(r["co_speaker_json"] or "[]"):
            shortfalls.append(Shortfall(r["chapter"], f"span {r['id']}, block {r['block_index']}",
                                        f"{r['span_type']} span has speaker {r['speaker_self_id']!r}", _excerpt(r["text"])))
    return _result(chk, shortfalls, count_in=total, count_out=total - len(shortfalls), unit="non-quoted spans")


@check(Stage.SPEAKERS, "speakers.method_vocabulary",
       "attribution method is an AttributionMethod member, confidence lies in [0, 1], and a HUMAN decision has "
       "confidence 1.0 (a method per book is reported)")
def check_speakers_vocabulary(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    from echotales.core.enums import AttributionMethod

    chk = _find(Stage.SPEAKERS, "speakers.method_vocabulary")
    if _no_spans(store, novel_id):
        return _skipped(chk, "no span rows stored (speaker attribution has not run)")
    valid = {m.value for m in AttributionMethod}
    shortfalls: list[Shortfall] = []
    methods: dict[str, int] = {}
    total = 0
    for r in _span_rows(store, novel_id):
        if r["span_type"] not in _QUOTED:
            continue
        total += 1
        m, c = r["attribution_method"], r["confidence"]
        methods[m] = methods.get(m, 0) + 1
        where = f"span {r['id']}"
        if m not in valid:
            shortfalls.append(Shortfall(r["chapter"], where, f"unknown attribution method {m!r}", _excerpt(r["text"])))
        elif c is None or not 0.0 <= c <= 1.0:
            shortfalls.append(Shortfall(r["chapter"], where, f"confidence {c!r} outside [0, 1]", _excerpt(r["text"])))
        elif m == "HUMAN" and c != 1.0:
            shortfalls.append(Shortfall(r["chapter"], where, f"HUMAN decision with confidence {c}", _excerpt(r["text"])))
    warnings = [f"{methods['TURN_TAKING']} spans carry the legacy TURN_TAKING method (the tier was removed)"] \
        if methods.get("TURN_TAKING") else []
    return _result(chk, shortfalls, count_in=total, count_out=total - len(shortfalls), unit="quoted spans",
                   warnings=warnings, stats={"methods": dict(sorted(methods.items()))})


@check(Stage.SPEAKERS, "speakers.queue_visibility",
       "every quoted span not confidently attributed to a real entity or slot is in the review queue "
       "(review_gate.speaker_queue); nothing settled has a dangling speaker or a no-identity method")
def check_speakers_queue(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    from echotales.pipeline.review_gate import _reason

    chk = _find(Stage.SPEAKERS, "speakers.queue_visibility")
    if _no_spans(store, novel_id):
        return _skipped(chk, "no span rows stored (speaker attribution has not run)")
    entities = _entity_ids(store, novel_id)
    keys = _surface_keys(store, novel_id)
    shortfalls: list[Shortfall] = []
    reasons: dict[str, int] = {}
    total = 0
    for r in _span_rows(store, novel_id):
        if r["span_type"] not in _QUOTED:
            continue
        total += 1
        reason = _reason(r["speaker_self_id"], r["attribution_method"], r["confidence"])
        reasons[reason or "settled"] = reasons.get(reason or "settled", 0) + 1
        if reason is not None:
            continue
        sp, m = r["speaker_self_id"], r["attribution_method"]
        bad = ""
        if m in _NO_IDENTITY_METHODS or m == "ANONYMOUS_SLOT":
            bad = f"settled with method {m}"
        elif entities and _speaker_kind(novel_id, sp, entities, keys) == "dangling":
            bad = f"settled but speaker {sp!r} is no entity and matches no name in the book"
        if bad:
            shortfalls.append(Shortfall(r["chapter"], f"span {r['id']}, block {r['block_index']}",
                                        f"{bad}, so the queue never shows it", _excerpt(r["text"])))
    hidden = reasons.get("model_guess", 0)
    warnings = [f"{hidden} named model guesses at confidence >= 0.8 are hidden from the default queue "
                "(include_guesses=False; deliberate, non-negotiable 7)"] if hidden else []
    return _result(chk, shortfalls, count_in=total, count_out=total - len(shortfalls), unit="quoted spans",
                   warnings=warnings, stats={"queue_reasons": dict(sorted(reasons.items()))})


@check(Stage.SPEAKERS, "speakers.unresolved_profile",
       "per-chapter share of quoted lines with no speaker; an extreme outlier is flagged (warning only)")
def check_speakers_profile(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.SPEAKERS, "speakers.unresolved_profile")
    if _no_spans(store, novel_id):
        return _skipped(chk, "no span rows stored (speaker attribution has not run)")
    per: dict[float, list[int]] = {}
    for r in _span_rows(store, novel_id):
        if r["span_type"] in _QUOTED:
            n = per.setdefault(r["chapter"], [0, 0])
            n[0] += 1
            n[1] += 0 if r["speaker_self_id"] else 1
    shares = {c: u / n for c, (n, u) in per.items() if n >= 5}
    warnings: list[str] = []
    if len(shares) >= 8:
        med = statistics.median(shares.values())
        mad = statistics.median(abs(v - med) for v in shares.values())
        for c, v in sorted(shares.items()):
            z = 0.6745 * (v - med) / max(mad, 0.03)
            if abs(z) >= 4 and abs(v - med) >= 0.25:
                warnings.append(f"chapter {c:g}: {v:.0%} of {per[c][0]} quoted lines have no speaker (book median {med:.0%})")
    return _result(chk, [], count_in=len(per), count_out=len(per), unit="chapters", warnings=warnings,
                   stats={"unresolved_share": {f"{c:g}": round(v, 3) for c, v in sorted(shares.items())}})


# ---------------------------------------------------------------------------
# RESOLVE
# ---------------------------------------------------------------------------

_NON_NAMING = ("RELATIONAL_DEICTIC", "TRANSFERABLE_TITLE")  # resolve/runner.py::_NON_FOUNDING_ALIAS_TYPES


def _no_entities(store: Store, novel_id: str) -> bool:
    return store.conn.execute("SELECT 1 FROM self_entity WHERE novel_id=? LIMIT 1", (novel_id,)).fetchone() is None


@check(
    Stage.RESOLVE,
    "resolve.mention_outcome",
    "every mention ends linked to an entity (new or existing); a group containing a naming mention that is still "
    "unlinked was deferred or exhausted and must be recorded as a resolve_deferred review item",
)
def check_resolve_outcome(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.RESOLVE, "resolve.mention_outcome")
    if _no_entities(store, novel_id):
        return _skipped(chk, "no entities stored (the resolve stage has not run)")
    rows = _mention_rows(store, novel_id)
    groups: dict[tuple[float, str], list[sqlite3.Row]] = {}
    for r in rows:
        groups.setdefault((r["chapter"], r["local_group_id"] or r["id"]), []).append(r)
    # Older databases predate the review_item table; reading it must not crash the audit.
    has_table = store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='review_item'").fetchone() is not None
    # An item accounts for its mentions while open, or once a reviewer (not the machine's "auto:" close) settled it.
    covered: set[str] = set()
    recorded = 0
    if has_table:
        for it in store.list_review_items(novel_id):
            if it.kind != "resolve_deferred" or (it.resolved and (it.resolution or "").startswith("auto:")):
                continue
            recorded += 1
            covered.update(str(i) for c in it.candidates if c.get("role") == "group" for i in c.get("mention_ids", []))
    shortfalls: list[Shortfall] = []
    linked = unlinked_mentions = 0
    non_naming = accounted = 0
    for (chapter, gid), ms in groups.items():
        open_ms = [m for m in ms if not m["target_id"]]
        linked += len(ms) - len(open_ms)
        unlinked_mentions += len(open_ms)
        if not open_ms:
            continue
        if all(m["alias_type"] in _NON_NAMING for m in ms):
            non_naming += len(open_ms)  # deliberate: no naming mention to found an entity on
            continue
        if any(m["id"] in covered for m in open_ms):
            accounted += 1  # deferred, and a review item records it
            continue
        shortfalls.append(Shortfall(chapter, f"group {gid}", f"{len(open_ms)} mention(s) of {open_ms[0]['text']!r} never linked "
                                    "and no resolve_deferred review item records the deferral", _excerpt(open_ms[0]["text"])))
    return _result(chk, shortfalls, count_in=len(rows), count_out=linked, unit="mentions",
                   stats={"unlinked_mentions": unlinked_mentions, "unlinked_non_naming_groups_mentions": non_naming,
                          "deferred_groups_recorded": accounted, "deferred_groups_unrecorded": len(shortfalls),
                          "resolve_deferred_items": recorded})


@check(Stage.RESOLVE, "resolve.no_orphans",
       "every mention target exists (self_entity, persona for PERSONA), and every entity has a mention or an alias "
       "binding (manual entities are exempt)")
def check_resolve_orphans(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.RESOLVE, "resolve.no_orphans")
    if _no_entities(store, novel_id):
        return _skipped(chk, "no entities stored (the resolve stage has not run)")
    ents = {r["id"]: r["canonical_label"] for r in store.conn.execute(
        "SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (novel_id,))}
    personas = {r[0] for r in store.conn.execute("SELECT id FROM persona WHERE novel_id=?", (novel_id,))}
    used: set[str] = set()
    shortfalls: list[Shortfall] = []
    n_linked = 0
    for r in _mention_rows(store, novel_id):
        t = r["target_id"]
        if not t:
            continue
        n_linked += 1
        used.add(t)
        if t not in ents and t not in personas:
            shortfalls.append(Shortfall(r["chapter"], f"mention {r['id']}", f"target {t!r} does not exist", _excerpt(r["text"])))
    for r in store.conn.execute("SELECT DISTINCT target_id FROM alias_binding WHERE novel_id=?", (novel_id,)):
        used.add(r[0])
    for eid, label in ents.items():
        if eid not in used and ":manual:" not in eid:
            shortfalls.append(Shortfall(None, f"entity {eid}", "entity has no mention and no alias binding", label))
    return _result(chk, shortfalls, count_in=len(ents), count_out=len(ents) - sum("entity" in s.location for s in shortfalls),
                   unit="entities", stats={"linked_mentions": n_linked})


@check(Stage.RESOLVE, "resolve.bindings",
       "alias bindings point at existing entities with well-formed intervals; a retracted fact carries truth_status "
       "FALSE (retraction stamps it) and is not retracted before it was learned; applies to alias, attribute and "
       "relation facts")
def check_resolve_bindings(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.RESOLVE, "resolve.bindings")
    if _no_entities(store, novel_id):
        return _skipped(chk, "no entities stored (the resolve stage has not run)")
    ents = _entity_ids(store, novel_id)
    personas = {r[0] for r in store.conn.execute("SELECT id FROM persona WHERE novel_id=?", (novel_id,))}
    shortfalls: list[Shortfall] = []
    total = 0
    for table, tgt in (("alias_binding", "target_id"), ("attribute", "target_id"), ("relation", None)):
        cols = "id, truth_status, story_from_lb, story_from_ub, story_to_lb, story_to_ub, learned_chapter, " \
               "retracted_chapter, " + (f"{tgt} AS tgt, target_kind" if tgt else "src_self, dst_self")
        for r in store.conn.execute(f"SELECT {cols} FROM {table} WHERE novel_id=?", (novel_id,)):
            total += 1
            where = f"{table} {r['id']}"
            ids = [(r["tgt"], r["target_kind"])] if tgt else [(r["src_self"], "SELF"), (r["dst_self"], "SELF")]
            for i, kind in ids:
                if i not in ents and i not in personas and kind != "MOB_GROUP":
                    shortfalls.append(Shortfall(None, where, f"target {i!r} does not exist"))
            a, b, c, d = (r[k] for k in ("story_from_lb", "story_from_ub", "story_to_lb", "story_to_ub"))
            if any(x != x for x in (a, b, c, d)) or a > b or c > d or a > d:
                shortfalls.append(Shortfall(None, where, f"malformed interval from [{a}, {b}] to [{c}, {d}]"))
            ret = r["retracted_chapter"]
            if ret is not None and r["truth_status"] != "FALSE":
                shortfalls.append(Shortfall(float(ret), where, f"retracted at chapter {ret} but truth_status is {r['truth_status']}"))
            if ret is not None and r["learned_chapter"] is not None and ret < r["learned_chapter"]:
                shortfalls.append(Shortfall(float(ret), where, f"retracted at chapter {ret}, before it was learned at {r['learned_chapter']}"))
    return _result(chk, shortfalls, count_in=total, count_out=total - len(shortfalls), unit="facts")


@check(Stage.RESOLVE, "resolve.corrections_present",
       "every applied correction in the corrections log (--corrections) is still reflected in the store: its manual "
       "entity exists and the span or mention carries the decided target")
def check_resolve_corrections(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.RESOLVE, "resolve.corrections_present")
    path = _corrections_path.get()
    if not path:
        return _skipped(chk, "no corrections log given (--corrections)")
    p = Path(path)
    if not p.exists():
        return _skipped(chk, f"corrections log not found: {p}")
    items = []
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                items.append(json.loads(line))
            except ValueError:
                items.append({"id": "?", "type": "unparsable", "applied": False, "novel_id": novel_id, "payload": {}})
    ents = _entity_ids(store, novel_id)
    mentions = {r["id"]: r["target_id"] for r in _mention_rows(store, novel_id)}
    spans = {r["id"]: r["speaker_self_id"] for r in _span_rows(store, novel_id)}
    shortfalls: list[Shortfall] = []
    applied = 0
    for c in items:
        if c.get("novel_id") != novel_id or not c.get("applied") or c.get("type") == "flag":
            continue
        applied += 1
        cid, kind, pl = c["id"], c["type"], c.get("payload", {})
        where = f"correction {cid} ({kind})"
        manual = f"{novel_id}:manual:{cid}"
        if pl.get("new_label") and manual not in ents:
            shortfalls.append(Shortfall(None, where, f"applied, but its entity {manual!r} ({pl['new_label']!r}) is gone"))
        if kind == "reassign_speaker" and pl.get("span_id") in spans:
            want = manual if pl.get("new_label") else (pl.get("speaker_id") or None)
            if want and not pl.get("anon_slot") and spans[pl["span_id"]] != want:
                shortfalls.append(Shortfall(float(pl.get("chapter", 0)), where, f"span {pl['span_id']} has speaker "
                                            f"{spans[pl['span_id']]!r}, the log says {want!r}"))
        elif kind == "reassign_speaker" and pl.get("span_id") not in spans:
            shortfalls.append(Shortfall(float(pl.get("chapter", 0)), where, f"span {pl.get('span_id')} no longer exists"))
        if kind == "reassign_mention" and pl.get("mention_id") in mentions:
            want = manual if pl.get("new_label") else (pl.get("target_id") or None)
            if mentions[pl["mention_id"]] != want:
                shortfalls.append(Shortfall(None, where, f"mention {pl['mention_id']} targets {mentions[pl['mention_id']]!r}, "
                                                          f"the log says {want!r}"))
        elif kind == "reassign_mention":
            shortfalls.append(Shortfall(None, where, f"mention {pl.get('mention_id')} no longer exists"))
        if kind == "merge_entities" and any(t == pl.get("from_id") for t in mentions.values()):
            shortfalls.append(Shortfall(None, where, f"mentions still target {pl.get('from_id')!r}, merged into {pl.get('into_id')!r}"))
    return _result(chk, shortfalls, count_in=applied, count_out=applied - len(shortfalls), unit="applied corrections")


@check(Stage.RESOLVE, "resolve.entity_profile",
       "entity count, mentions per entity, singleton share and the most-mentioned entities with their surfaces; "
       "hints (warnings) for possible splits and merges")
def check_resolve_profile(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    from echotales.pipeline.ingest.normalize import comparison_key

    chk = _find(Stage.RESOLVE, "resolve.entity_profile")
    if _no_entities(store, novel_id):
        return _skipped(chk, "no entities stored (the resolve stage has not run)")
    labels = {r["id"]: r["canonical_label"] for r in store.conn.execute(
        "SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (novel_id,))}
    surfaces: dict[str, dict[str, int]] = {e: {} for e in labels}
    for r in _mention_rows(store, novel_id):
        if r["target_id"] in surfaces:
            d = surfaces[r["target_id"]]
            d[r["text"]] = d.get(r["text"], 0) + 1
    counts = {e: sum(d.values()) for e, d in surfaces.items()}
    vals = sorted(counts.values())
    singles = sum(v <= 1 for v in vals)
    top = sorted(counts, key=lambda e: -counts[e])[:10]
    warnings: list[str] = []
    by_key: dict[str, list[str]] = {}
    by_family: dict[str, list[str]] = {}
    for e, label in labels.items():
        if counts[e] < 3:
            continue
        key = comparison_key(label)
        by_key.setdefault(key, []).append(e)
        toks = key.split()
        if len(toks) >= 2 and len(toks[-1]) >= 3:
            by_family.setdefault(toks[-1], []).append(e)
    for es in by_key.values():
        if len(es) > 1:
            warnings.append("possible split: " + " / ".join(f"{labels[e]!r} ({counts[e]})" for e in es))
    for fam, es in by_family.items():
        keys = {comparison_key(labels[e]) for e in es}
        if len(keys) > 1 and len(es) <= 4:
            warnings.append(f"shared family token {fam!r} (check for a merge or a split): "
                            + " / ".join(f"{labels[e]!r} ({counts[e]})" for e in es))
    shown = warnings[:MAX_LISTED]
    if len(warnings) > MAX_LISTED:
        shown.append(f"... {len(warnings) - MAX_LISTED} more hints")
    return _result(
        chk, [], count_in=len(labels), count_out=len(labels), unit="entities", warnings=shown,
        stats={"entities": len(labels), "singleton_share": round(singles / len(labels), 3),
               "mentions_per_entity": {"min": vals[0], "median": statistics.median(vals), "p90": vals[int(0.9 * (len(vals) - 1))],
                                       "max": vals[-1]},
               "top_entities": [{"id": e, "label": labels[e], "mentions": counts[e],
                                 "surfaces": sorted(surfaces[e].items(), key=lambda kv: -kv[1])[:5]} for e in top],
               "hints": len(warnings)},
    )


# ---------------------------------------------------------------------------
# Stage 7: Director checks
# ---------------------------------------------------------------------------


def _latest_plan_files(panel_root: Path) -> list[Path]:
    """Each chapter's newest `panel_plan.jsonl`: `panels/chN/vN_suffix/` keeps every render, and the audit used to glob
    them all, so a chapter rendered ten times was judged on its first nine (worse) directions as well. The version
    number is compared as an integer (v10 is newer than v9); a plan outside that layout counts as its own group."""
    best: dict[Path, tuple[int, Path]] = {}
    for pf in sorted(panel_root.glob("**/panel_plan.jsonl")):
        head = pf.parent.name[1:].split("_")[0]
        if pf.parent.name.startswith("v") and head.isdigit():
            group, num = pf.parent.parent, int(head)
        else:
            group, num = pf.parent, -1
        if group not in best or num > best[group][0]:
            best[group] = (num, pf)
    return [pf for _, pf in best.values()]


@check(Stage.DIRECTOR, "director.conservation", "every person, place and prop in beat text is captured in panel direction or counted as dropped")
def check_director_conservation(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    chk = _find(Stage.DIRECTOR, "director.conservation")
    import json
    from echotales.pipeline import paths
    from echotales.pipeline.render.direction import check_direction_conservation as _conserve_check
    from echotales.pipeline.render.direction import PanelDirection

    panel_root = paths.asset_dir(novel_id, "panels")
    plan_path = panel_root / "panel_plan.jsonl"
    plan_files = [plan_path] if plan_path.exists() else _latest_plan_files(panel_root)
    if not plan_files:
        return _skipped(chk, "no panel_plan.jsonl found on disk")

    plans_raw = []
    for pf in plan_files:
        plans_raw.extend(json.loads(line) for line in pf.read_text(encoding="utf-8").splitlines() if line)
    if not plans_raw:
        return _skipped(chk, "panel_plan.jsonl is empty")

    shortfalls: list[Shortfall] = []
    total_in = 0
    total_out = 0
    warnings: list[str] = []

    for row in plans_raw:
        direction_data = row.get("direction")
        if not direction_data:
            continue
        try:
            direction = PanelDirection(**direction_data)
        except Exception:
            continue

        chapter_num = row.get("chapter", 1.0)
        block_indexes = row.get("block_indexes", [])
        if not block_indexes and "lead_block" in row:
            block_indexes = [row["lead_block"]]

        chapter_obj = store.get_chapter(novel_id, chapter_num)
        if not chapter_obj:
            continue
        blocks_by_idx = {b.index: b.text for b in chapter_obj.blocks}
        beat_text = " ".join(blocks_by_idx.get(idx, "") for idx in block_indexes)
        if not beat_text:
            continue

        cast_names = {c.get("label", "") for c in row.get("cast", []) if c.get("label")}
        audit_res = _conserve_check(beat_text, direction, cast_names)

        items_in = (
            len(audit_res.captured_people) + len(audit_res.dropped_people) +
            len(audit_res.captured_places) + len(audit_res.dropped_places) +
            len(audit_res.captured_props) + len(audit_res.dropped_props)
        )
        items_out = (
            len(audit_res.captured_people) +
            len(audit_res.captured_places) +
            len(audit_res.captured_props)
        )
        total_in += items_in
        total_out += items_out

        if audit_res.dropped_people or audit_res.dropped_places or audit_res.dropped_props:
            dropped_desc = []
            if audit_res.dropped_people:
                dropped_desc.append(f"people: {', '.join(audit_res.dropped_people)}")
            if audit_res.dropped_places:
                dropped_desc.append(f"places: {', '.join(audit_res.dropped_places)}")
            if audit_res.dropped_props:
                dropped_desc.append(f"props: {', '.join(audit_res.dropped_props)}")
            warnings.append(f"chapter {chapter_num:g} panel {row.get('panel_seq', 0)} dropped {'; '.join(dropped_desc)}")

    return _result(
        chk,
        shortfalls,
        count_in=total_in,
        count_out=total_out,
        unit="items",
        warnings=warnings[:MAX_LISTED],
        stats={"total_in": total_in, "total_out": total_out, "dropped": total_in - total_out},
    )


@check(Stage.DIRECTOR, "director.vision", "a local vision model checked each panel's person count, hair colour, outfit colour and presence")
def check_vision(store: Store, novel_id: str, source: SourceContext | None) -> CheckResult:
    """Pass rate and regenerations of the render-time vision check (`render/vision_pass.py`), from the newest render of
    each chapter. Skipped, with the install line, when no render was checked: the check is off without a vision model."""
    chk = _find(Stage.DIRECTOR, "director.vision")
    import json
    from echotales.pipeline import paths
    from echotales.pipeline.keyframes import qa

    panel_root = paths.asset_dir(novel_id, "panels")
    rows: list[dict] = []
    for pf in _latest_plan_files(panel_root):
        vf = pf.parent / "vision_check.jsonl"
        if vf.exists():
            rows.extend(json.loads(line) for line in vf.read_text(encoding="utf-8").splitlines() if line)
    if not rows:
        return _skipped(chk, qa.NO_VLM_MESSAGE)
    s = qa.summarise(rows)
    warnings = [
        f"{r['panel']}: still fails {', '.join(r.get('failed', []))} after {r.get('candidates', 1)} candidate(s)"
        for r in rows if not r.get("passed") and not r.get("unchecked")
    ]
    return _result(
        chk, [], count_in=s["panels_checked"], count_out=sum(bool(r.get("passed")) for r in rows if not r.get("unchecked")),
        unit="panels", warnings=warnings[:MAX_LISTED], stats=s,
    )


# ---------------------------------------------------------------------------
# Running and reporting
# ---------------------------------------------------------------------------


def totals(results: list[CheckResult]) -> dict[str, int]:
    return {
        "pass": sum(r.status is Status.PASS for r in results),
        "fail": sum(r.status is Status.FAIL for r in results),
        "skipped": sum(r.status is Status.SKIPPED for r in results),
        "warnings": sum(len(r.warnings) for r in results),
    }


def audit_novel(
    store: Store,
    novel_id: str,
    *,
    stage: Stage | None = None,
    source: str | None = None,
    sources_path: str | None = None,
    corrections: str | None = None,
) -> tuple[list[CheckResult], dict[str, Any]]:
    ctx, reason = resolve_source(store, novel_id, source=source, sources_path=sources_path)
    token = _corrections_path.set(corrections)
    try:
        results = run_checks(store, novel_id, ctx, source_reason=reason, stages=[stage] if stage else None)
    finally:
        _corrections_path.reset(token)
        if ctx is not None:
            ctx.close()
    info = {
        "path": str(ctx.path) if ctx else None,
        "adapter": ctx.adapter if ctx else None,
        "range": str(ctx.chapters) if ctx and ctx.chapters else None,
        "range_inferred": ctx.range_inferred if ctx else None,
        "unavailable": reason or None,
    }
    return results, info


def render_json(novel_id: str, results: list[CheckResult], source_info: dict[str, Any]) -> str:
    return json.dumps(
        {
            "novel": novel_id,
            "source": source_info,
            "stages": [s.value for s in Stage if any(r.stage is s for r in results)],
            "checks": [r.to_dict() for r in results],
            "totals": totals(results),
        },
        indent=2,
    )


def render_text(novel_id: str, results: list[CheckResult]) -> str:
    lines = [f"audit: {novel_id}"]
    for r in results:
        counts = f"  {r.count_in:,} -> {r.count_out:,} {r.unit}" if r.unit else ""
        tail = f"  ({r.skipped_reason})" if r.status is Status.SKIPPED else counts
        lines.append(f"{r.status.value:<7} {r.check_id:<24} {r.invariant if r.status is Status.FAIL else ''}{tail}".rstrip())
        if r.status is Status.FAIL:
            for s in r.shortfalls:
                lines.append(f"    - {s.render()}")
            if r.total_shortfalls > len(r.shortfalls):
                lines.append(f"    ... {r.total_shortfalls - len(r.shortfalls)} more ({r.total_shortfalls} in total)")
        for w in r.warnings:
            lines.append(f"    ! {w}")
        excl = r.stats.get("exclusions_words") if r.stats else None
        if excl:
            for name, n in excl.items():
                lines.append(f"    . excluded {n:,} words: {name}")
    t = totals(results)
    lines.append(f"totals: {t['pass']} pass, {t['fail']} fail, {t['skipped']} skipped, {t['warnings']} warnings")
    return "\n".join(lines)
