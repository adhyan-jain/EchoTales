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
    by_href: dict[str, list[Chapter]] = {}
    for ch in chapters:
        by_href.setdefault(ch.source_href, []).append(ch)

    total_in = total_matched = total_added = 0
    exclusions: dict[str, int] = {}
    shortfalls: list[Shortfall] = []
    warnings: list[str] = []
    unnumbered_words: dict[str, int] = {}

    def exclude(category: str, n: int) -> None:
        exclusions[category] = exclusions.get(category, 0) + n

    for href in source.spine():
        doc = source.doc(href)
        if doc is None:
            shortfalls.append(Shortfall(None, href, "spine document is listed in the manifest but cannot be read"))
            continue
        total_in += len(doc.words)
        here = _windows(infos, href, doc)
        chs = by_href.get(href, [])
        order = {id(i.entry): n for n, i in enumerate(infos)}
        number_order = {i.number: order[id(i.entry)] for i in here if i.number is not None}
        chs = sorted(chs, key=lambda c: number_order.get(c.number, 10**9))
        stored_words = [w for c in chs for w in _words(c)]

        vocab: dict[str, int] = {}
        a = [vocab.setdefault(w, len(vocab)) for w in doc.words]
        b = [vocab.setdefault(w, len(vocab)) for w in stored_words]
        sm = SequenceMatcher(None, a, b, autojunk=False)
        unmatched: list[tuple[int, int]] = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                total_matched += i2 - i1
                continue
            if i2 > i1:
                unmatched.append((i1, i2))
            if j2 > j1:
                total_added += j2 - j1
                shortfalls.append(
                    Shortfall(
                        chs[0].number if len(chs) == 1 else None,
                        f"{href}, stored words {j1}-{j2}",
                        f"{j2 - j1} stored words are not in the source document",
                        _excerpt(" ".join(stored_words[j1:j2])),
                    )
                )

        licence = _licence_start(doc.words)
        for lo, hi in unmatched:
            cuts = sorted({lo, hi, *(p for i in here for p in (i.lo, i.hi) if lo < p < hi)})
            for p, q in itertools.pairwise(cuts):
                _classify_piece(
                    doc, href, here, p, q, licence, exclude, shortfalls, unnumbered_words,
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
    here: list[EntryInfo],
    lo: int,
    hi: int,
    licence: int | None,
    exclude: Callable[[str, int], None],
    shortfalls: list[Shortfall],
    unnumbered_words: dict[str, int],
) -> None:
    n = hi - lo
    owner = next((i for i in here if i.lo <= lo < i.hi), None)
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
        if lo - owner.lo <= 40 and n <= 80 and _is_label_echo(text, label):
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

    Allowed normalisation, and nothing else: a span's text is its [start:end) slice with surrounding whitespace
    stripped, and whitespace between spans is not covered (`split_block` drops whitespace-only pieces)."""
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
            if r.text != text[r.start : r.end].strip():
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
    "no overlap; only whitespace between spans and a span's surrounding whitespace is dropped",
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
) -> tuple[list[CheckResult], dict[str, Any]]:
    ctx, reason = resolve_source(store, novel_id, source=source, sources_path=sources_path)
    try:
        results = run_checks(store, novel_id, ctx, source_reason=reason, stages=[stage] if stage else None)
    finally:
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
