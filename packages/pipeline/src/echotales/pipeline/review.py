"""Human review of what the pipeline produced.

The pipeline is only trustworthy to the extent its decisions can be checked, so
this module exists to make every entity inspectable: what it is called, how
often it appears, over which chapters, and — critically — a citation back to
the source for each claim.

**Evidence is a short snippet plus a chapter/offset citation, never bulk text.**
The snippet is capped at `SNIPPET_CHARS` and centred on the mention. That is
enough to confirm or reject a decision at a glance, and it follows the same
convention as `data/gold/`: offsets are the record, text is a convenience.
Anything longer would turn a review artifact into a copy of the novel.

Three outputs, for three different jobs:

- **console** — a ranked table, for a quick sanity read after a run
- **HTML** — browsable, with evidence inline, for actually auditing entities
- **JSONL** — one entity per line, for scripting or for seeding annotation
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import EventType, SpanType
from echotales.core.store import Store

#: Characters of surrounding text shown per evidence citation. Deliberately
#: small: enough to judge a mention, far too little to reconstruct the source.
SNIPPET_CHARS = 110


@dataclass(slots=True)
class Evidence:
    """One citation supporting an entity's existence."""

    chapter: float
    offset: int
    surface: str
    snippet: str

    @property
    def citation(self) -> str:
        return f"ch{self.chapter:g}:{self.offset}"


@dataclass(slots=True)
class EntityRow:
    """One resolved entity, as a reviewer needs to see it."""

    target_id: str
    label: str
    mention_count: int
    first_chapter: float
    last_chapter: float
    aliases: list[str] = field(default_factory=list)
    alias_types: dict[str, int] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def chapter_span(self) -> str:
        if self.first_chapter == self.last_chapter:
            return f"ch{self.first_chapter:g}"
        return f"ch{self.first_chapter:g}–{self.last_chapter:g}"

    @property
    def spread(self) -> float:
        return self.last_chapter - self.first_chapter


@dataclass(slots=True)
class ScriptLine:
    """One span, as a TTS or manga pipeline would consume it.

    This is the view an entity table cannot give you: not "does Fang Yuan
    exist as one entity" but "line 40 of chapter 3 is spoken by Fang Yuan,
    directed at whoever the scene has established as present". Attribution
    coverage and entity precision are different failure surfaces -- an entity
    list can look clean while every third line of dialogue has no speaker, and
    that gap is invisible until the lines are read in order.
    """

    span_type: str
    text: str
    speaker_label: str | None
    attribution_method: str
    #: Mentions inside this span, resolved to their entity label where
    #: possible -- the "who is referred to" complement to "who is speaking".
    referenced: list[str] = field(default_factory=list)

    @property
    def is_dialogue(self) -> bool:
        return self.span_type == SpanType.DIALOGUE.value


@dataclass(slots=True)
class ChapterScript:
    number: float
    lines: list[ScriptLine] = field(default_factory=list)

    @property
    def dialogue_count(self) -> int:
        return sum(1 for line in self.lines if line.is_dialogue)

    @property
    def attributed_count(self) -> int:
        return sum(1 for line in self.lines if line.is_dialogue and line.speaker_label)


@dataclass(slots=True)
class ReviewReport:
    novel_id: str
    chapters: int = 0
    mentions: int = 0
    resolved_mentions: int = 0
    entities: list[EntityRow] = field(default_factory=list)
    event_counts: dict[str, int] = field(default_factory=dict)
    detector_events: dict[str, int] = field(default_factory=dict)
    #: Populated only when `build_review(..., script_chapters=...)` is asked
    #: for it -- rendering every chapter's script by default would make the
    #: HTML report scale with novel length instead of cast size.
    scripts: list[ChapterScript] = field(default_factory=list)

    @property
    def resolution_rate(self) -> float:
        return self.resolved_mentions / self.mentions if self.mentions else 0.0

    @property
    def singletons(self) -> int:
        """Entities seen exactly once.

        The clearest over-splitting signal available without gold: a cast is
        not mostly walk-ons, so a high share here means the resolver is minting
        an entity per mention rather than linking.
        """
        return sum(1 for e in self.entities if e.mention_count == 1)

    def render_console(self, limit: int = 30) -> str:
        lines = [
            f"\n=== review: {self.novel_id} ===",
            f"  chapters           {self.chapters:,}",
            f"  mentions           {self.mentions:,} "
            f"({self.resolved_mentions:,} resolved, {self.resolution_rate:.1%})",
            f"  entities           {len(self.entities):,}",
            f"  seen once only     {self.singletons:,} "
            f"({self.singletons / len(self.entities):.0%} — high means over-splitting)"
            if self.entities
            else "",
            "",
            f"  top {min(limit, len(self.entities))} entities by mention count:",
            f"    {'#':>4}  {'label':<28} {'ments':>6}  {'chapters':<14} aliases",
        ]
        for i, entity in enumerate(self.entities[:limit], start=1):
            aliases = ", ".join(entity.aliases[:4])
            if len(entity.aliases) > 4:
                aliases += f" (+{len(entity.aliases) - 4})"
            lines.append(
                f"    {i:>4}. {entity.label[:28]:<28} {entity.mention_count:>6}  "
                f"{entity.chapter_span:<14} {aliases}"
            )

        if self.event_counts:
            lines.append("\n  event log:")
            for name, count in sorted(self.event_counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {name:<22} {count:>7,}")
        return "\n".join(line for line in lines if line != "")


def _snippet(text: str, offset: int, surface: str) -> str:
    """A short window of source text centred on the mention."""
    half = SNIPPET_CHARS // 2
    start = max(0, offset - half)
    window = text[start : start + SNIPPET_CHARS].replace("\n", " ").strip()
    if start > 0:
        window = "…" + window
    if start + SNIPPET_CHARS < len(text):
        window = window + "…"
    return window


def _build_scripts(
    store: Store, novel_id: str, chapters: list[float]
) -> list[ChapterScript]:
    """One `ChapterScript` per requested chapter, in reading order."""
    label_cache: dict[str, str | None] = {}

    def label_of(self_id: str | None) -> str | None:
        if not self_id:
            return None
        if self_id not in label_cache:
            entity = store.get_self(self_id)
            label_cache[self_id] = entity.canonical_label if entity else self_id
        return label_cache[self_id]

    scripts: list[ChapterScript] = []
    for number in chapters:
        spans = store.get_spans(novel_id, number)
        mentions = store.get_mentions(novel_id, chapter=number)
        by_block: dict[int, list] = {}
        for m in mentions:
            by_block.setdefault(m.block_index, []).append(m)

        script = ChapterScript(number=number)
        for span in spans:
            # Mentions inside this span's character range, within its block --
            # see `eval/coref_score.py::_block_starts` for why offsets are
            # block-local and cannot be compared to a different block's span.
            in_span = [
                m
                for m in by_block.get(span.block_index, [])
                if span.start <= m.offset < span.end
            ]
            referenced = []
            seen = set()
            for m in in_span:
                shown = label_of(m.target_id) or m.text
                if shown not in seen:
                    referenced.append(shown)
                    seen.add(shown)

            script.lines.append(
                ScriptLine(
                    span_type=span.span_type.value,
                    text=span.text,
                    speaker_label=label_of(span.speaker_self_id),
                    attribution_method=span.attribution_method.value,
                    referenced=referenced,
                )
            )
        scripts.append(script)
    return scripts


def build_review(
    store: Store,
    novel_id: str,
    *,
    top_n: int = 200,
    samples: int = 3,
    script_chapters: list[float] | None = None,
) -> ReviewReport:
    """Assemble everything a reviewer needs from the graph.

    `script_chapters` renders the line-by-line speaker/reference view for those
    chapters specifically (see `ScriptLine`) -- omitted by default since it is
    sized for spot-checking a handful of chapters, not the whole novel.
    """
    report = ReviewReport(novel_id=novel_id)
    report.chapters = store.chapter_count(novel_id)
    if script_chapters:
        report.scripts = _build_scripts(store, novel_id, script_chapters)

    mentions = store.get_mentions(novel_id)
    report.mentions = len(mentions)

    by_target: dict[str, list] = {}
    for mention in mentions:
        if mention.target_id:
            by_target.setdefault(mention.target_id, []).append(mention)
    report.resolved_mentions = sum(len(v) for v in by_target.values())

    # Chapter text is loaded lazily and only for the chapters actually cited,
    # so a review of the top 200 entities never materialises the whole novel.
    text_cache: dict[float, str] = {}

    def chapter_text(number: float) -> str:
        if number not in text_cache:
            chapter = store.get_chapter(novel_id, number)
            text_cache[number] = chapter.story_text if chapter else ""
        return text_cache[number]

    ranked = sorted(by_target.items(), key=lambda kv: len(kv[1]), reverse=True)

    for target_id, group in ranked:
        entity = store.get_self(target_id)
        chapters = [m.chapter for m in group]
        surfaces: dict[str, int] = {}
        types: dict[str, int] = {}
        for mention in group:
            surfaces[mention.text] = surfaces.get(mention.text, 0) + 1
            types[mention.alias_type.value] = types.get(mention.alias_type.value, 0) + 1

        row = EntityRow(
            target_id=target_id,
            label=entity.canonical_label if entity else max(surfaces, key=surfaces.get),
            mention_count=len(group),
            first_chapter=min(chapters),
            last_chapter=max(chapters),
            aliases=sorted(surfaces, key=surfaces.get, reverse=True),
            alias_types=types,
        )

        # Evidence spread across the entity's range rather than clustered at
        # its first appearance — a reviewer checking a link needs to see it
        # hold up late as well as early.
        if len(report.entities) < top_n:
            ordered = sorted(group, key=lambda m: (m.chapter, m.offset))
            step = max(1, len(ordered) // max(samples, 1))
            for mention in ordered[:: step][:samples]:
                row.evidence.append(
                    Evidence(
                        chapter=mention.chapter,
                        offset=mention.offset,
                        surface=mention.text,
                        snippet=_snippet(
                            chapter_text(mention.chapter), mention.offset, mention.text
                        ),
                    )
                )
        report.entities.append(row)

    report.event_counts = store.event_counts()
    report.detector_events = {
        k: v
        for k, v in report.event_counts.items()
        if k
        in {
            EventType.REBIND.value,
            EventType.MERGE.value,
            EventType.SPLIT.value,
            EventType.DEATH.value,
            EventType.RESURRECTION.value,
            EventType.TIME_SKIP.value,
            EventType.REPUTATION_SPREAD.value,
        }
    }
    return report


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def write_jsonl(report: ReviewReport, path: Path | str) -> Path:
    """One entity per line.

    Doubles as the seed format for annotation: a reviewer can correct
    `label`/`aliases` in place and the result is already close to what the gold
    loader expects.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for entity in report.entities:
            fh.write(
                json.dumps(
                    {
                        "target_id": entity.target_id,
                        "label": entity.label,
                        "mentions": entity.mention_count,
                        "first_chapter": entity.first_chapter,
                        "last_chapter": entity.last_chapter,
                        "aliases": entity.aliases,
                        "alias_types": entity.alias_types,
                        "evidence": [
                            {
                                "citation": ev.citation,
                                "chapter": ev.chapter,
                                "offset": ev.offset,
                                "surface": ev.surface,
                                "snippet": ev.snippet,
                            }
                            for ev in entity.evidence
                        ],
                        "provenance": "MACHINE",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return p


_CSS = """
:root { color-scheme: light dark; }
body { font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
       margin: 0; padding: 2rem; max-width: 1200px; margin-inline: auto; }
h1 { font-size: 1.5rem; margin-bottom: .25rem; }
.sub { opacity: .7; margin-bottom: 1.5rem; }
.stats { display: flex; flex-wrap: wrap; gap: 1.5rem; margin-bottom: 2rem; }
.stat { border-left: 3px solid currentColor; padding-left: .75rem; opacity: .9; }
.stat b { display: block; font-size: 1.35rem; }
.warn { border-left-color: #c93; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid rgba(128,128,128,.25);
         vertical-align: top; }
th { position: sticky; top: 0; background: Canvas; font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
details { margin: 0; }
summary { cursor: pointer; }
.ev { font-size: .85rem; opacity: .85; margin: .4rem 0 .4rem 1rem;
      border-left: 2px solid rgba(128,128,128,.35); padding-left: .6rem; }
.cite { font-family: ui-monospace, monospace; font-size: .78rem; opacity: .65; }
.alias { display: inline-block; background: rgba(128,128,128,.15); border-radius: 3px;
         padding: 0 .35rem; margin: 0 .2rem .2rem 0; font-size: .82rem; }
.note { background: rgba(200,150,50,.12); border-left: 3px solid #c93;
        padding: .75rem 1rem; margin: 1.5rem 0; font-size: .9rem; }
.script { margin: 1rem 0 2.5rem; }
.line { display: grid; grid-template-columns: 11rem 1fr; gap: .75rem; padding: .35rem 0;
        border-bottom: 1px solid rgba(128,128,128,.15); }
.line.dialogue { background: rgba(100,150,255,.06); }
.speaker { font-weight: 600; text-align: right; }
.speaker.missing { color: #c93; font-weight: 400; font-style: italic; }
.method { display: block; font-size: .72rem; opacity: .55; font-weight: 400; text-align: right; }
.spantype { display: inline-block; font-size: .68rem; opacity: .5; text-transform: uppercase;
            letter-spacing: .03em; margin-right: .5rem; }
.refs { font-size: .78rem; opacity: .7; margin-top: .15rem; }
.refs .alias { padding: 0 .3rem; }
"""


def _render_entity_row(i: int, entity: EntityRow) -> str:
    aliases = "".join(
        f'<span class="alias">{html.escape(a)}</span>' for a in entity.aliases[:12]
    )
    if len(entity.aliases) > 12:
        aliases += f'<span class="alias">+{len(entity.aliases) - 12} more</span>'

    evidence = "".join(
        f'<div class="ev"><span class="cite">{html.escape(ev.citation)}</span> '
        f"&nbsp; {html.escape(ev.snippet)}</div>"
        for ev in entity.evidence
    )
    evidence_block = (
        f"<details><summary>{len(entity.evidence)} citation(s)</summary>{evidence}</details>"
        if entity.evidence
        else "<span style='opacity:.5'>—</span>"
    )

    return (
        f"<tr><td class='num'>{i}</td>"
        f"<td><b>{html.escape(entity.label)}</b><br>"
        f"<span class='cite'>{html.escape(entity.target_id)}</span></td>"
        f"<td class='num'>{entity.mention_count:,}</td>"
        f"<td>{html.escape(entity.chapter_span)}</td>"
        f"<td>{aliases}</td>"
        f"<td>{evidence_block}</td></tr>"
    )


def _render_line(line: ScriptLine) -> str:
    if line.speaker_label:
        speaker = (
            f"{html.escape(line.speaker_label)}"
            f"<span class='method'>{html.escape(line.attribution_method)}</span>"
        )
        speaker_cls = "speaker"
    else:
        speaker = "unattributed<span class='method'>&nbsp;</span>"
        speaker_cls = "speaker missing"

    refs = ""
    if line.referenced:
        refs = "<div class='refs'>refs: " + "".join(
            f"<span class='alias'>{html.escape(r)}</span>" for r in line.referenced
        ) + "</div>"

    row_cls = "line dialogue" if line.is_dialogue else "line"
    return (
        f"<div class='{row_cls}'><div class='{speaker_cls}'>{speaker}</div>"
        f"<div><span class='spantype'>{html.escape(line.span_type)}</span>"
        f"{html.escape(line.text)}{refs}</div></div>"
    )


def _render_script(script: ChapterScript) -> str:
    cov = (
        f"{script.attributed_count}/{script.dialogue_count} dialogue lines attributed"
        if script.dialogue_count
        else "no dialogue"
    )
    lines = "".join(_render_line(line) for line in script.lines)
    return (
        f"<div class='script'><h3>Chapter {script.number:g} "
        f"<span style='opacity:.6;font-weight:400'>({cov})</span></h3>{lines}</div>"
    )


def write_html(report: ReviewReport, path: Path | str, *, limit: int = 300) -> Path:
    """A browsable audit of the resolved entities."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    singleton_pct = (
        report.singletons / len(report.entities) if report.entities else 0.0
    )
    rows = "".join(
        _render_entity_row(i, e) for i, e in enumerate(report.entities[:limit], start=1)
    )
    events = "".join(
        f"<tr><td>{html.escape(k)}</td><td class='num'>{v:,}</td></tr>"
        for k, v in sorted(report.event_counts.items(), key=lambda kv: -kv[1])
    )

    scripts_html = ""
    if report.scripts:
        total_dialogue = sum(s.dialogue_count for s in report.scripts)
        total_attributed = sum(s.attributed_count for s in report.scripts)
        cov = total_attributed / total_dialogue if total_dialogue else 0.0
        scripts_html = (
            "<h2>Script view</h2>"
            "<div class='note'>Line-by-line, in reading order: who is speaking and who "
            "each line refers to, resolved to entities. This is what a TTS or manga "
            "pipeline actually consumes -- an entity table can look clean while "
            "attribution coverage underneath it is poor, and that gap only shows up "
            f"here. Coverage over the sampled chapters: {total_attributed:,}/"
            f"{total_dialogue:,} dialogue lines ({cov:.0%}).</div>"
            + "".join(_render_script(s) for s in report.scripts)
        )

    body = f"""<h1>EchoTales review — {html.escape(report.novel_id)}</h1>
<div class="sub">Machine output. Every row is a hypothesis, not a fact — check the citations.</div>

<div class="stats">
  <div class="stat"><b>{report.chapters:,}</b>chapters</div>
  <div class="stat"><b>{report.mentions:,}</b>mentions</div>
  <div class="stat"><b>{report.resolution_rate:.0%}</b>resolved</div>
  <div class="stat"><b>{len(report.entities):,}</b>entities</div>
  <div class="stat {"warn" if singleton_pct > 0.4 else ""}">
    <b>{singleton_pct:.0%}</b>seen once only</div>
</div>

<div class="note">
<b>How to review this.</b> Work top-down — the highest-mention entities carry the most
weight downstream. For each, ask three things:
<ol>
<li><b>Is the alias list one person?</b> Unrelated names bundled together means the
resolver over-merged. Expand the citations to check.</li>
<li><b>Should any two rows be one row?</b> The same character split across several
entries means it under-linked. Sort by label and scan for near-duplicates.</li>
<li><b>Does the chapter span look right?</b> A major character confined to a handful
of chapters usually means their later mentions went to a different entity.</li>
</ol>
A high <i>seen once only</i> percentage is the strongest over-splitting signal
available without annotations — a real cast is not mostly walk-ons.
</div>

<table>
<thead><tr><th>#</th><th>entity</th><th>mentions</th><th>chapters</th>
<th>surface forms</th><th>evidence</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<h2>Event log</h2>
<table><thead><tr><th>event</th><th>count</th></tr></thead><tbody>{events}</tbody></table>

{scripts_html}
"""

    p.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>EchoTales review — {html.escape(report.novel_id)}</title>"
        f"<style>{_CSS}</style></head><body>{body}</body></html>",
        encoding="utf-8",
    )
    return p
