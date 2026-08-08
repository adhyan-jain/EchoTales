"""A browsable, multi-novel viewer for judging NER/coref/attribution quality.

`review.py` already answers "is this entity list right" (a table) and "is this
chapter's attribution right" (boxed line-by-line). This module answers a third
question that neither does well: **read the prose as prose**, with every
resolved mention underlined and colour-coded by entity, and every line of
dialogue headed by who the pipeline thinks said it. That is the fastest way
for a person to spot a wrong merge or a missed speaker, because it is close to
how the mistake would actually be experienced by a reader or a TTS listener.

One static HTML file plus one small JS data file per novel. No server, no
build step, no framework: `data/webview/index.html` opens directly in a
browser (`file://` works — data is loaded via `<script src>`, not `fetch`,
specifically so the same-origin restriction that blocks local `fetch()` of
`file://` JSON never bites). Every entity gets a stable colour from its rank by
mention count, not a hash, so the most important characters get the most
distinguishable colours and a long tail of walk-ons doesn't fight for hue.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from echotales.core.store import Store

#: Matches the id `speakers/runner.py::_assign_anonymous_slots` mints --
#: `f"{novel_id}:anon:{chapter:g}:{slot}"`. Never a `Self` row, so
#: `store.get_self` would return None for it; this is the display-layer half
#: of "distinct voice, no identity" -- see that function's docstring for why
#: an id exists here at all rather than just leaving the speaker blank.
_ANON_SPEAKER_RE = re.compile(r":anon:[\d.]+:(?P<slot>\d+)$")

#: Deliberately not in `_PALETTE` -- an anonymous slot must never look like it
#: could be a ranked, named entity at a glance.
_ANON_COLOURS = ["#8895A7", "#A78895", "#95A788", "#A79A88"]


def _anon_slot_label(self_id: str) -> str | None:
    m = _ANON_SPEAKER_RE.search(self_id)
    return f"Unknown Speaker {m.group('slot')}" if m else None


def _anon_slot_colour(self_id: str) -> str | None:
    m = _ANON_SPEAKER_RE.search(self_id)
    if not m:
        return None
    return _ANON_COLOURS[(int(m.group("slot")) - 1) % len(_ANON_COLOURS)]

#: Distinct, colourblind-considerate categorical palette (Okabe-Ito derived,
#: extended). Cycled by mention-count rank, so `Fang Yuan` always gets the
#: same slot in every novel and the highest-traffic characters are the easiest
#: to tell apart at a glance.
_PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    "#1B9E77", "#D95F02", "#7570B3", "#E7298A", "#66A61E",
    "#E6AB02",
]
#: Beyond this rank, entities share a neutral colour rather than exhausting
#: distinguishable hues — a 700-entity novel cannot have 700 legible colours,
#: and a reviewer scanning for the wrong thing is helped more by the top cast
#: standing out than by every walk-on having a unique shade nobody can recall.
_COLOURED_RANKS = len(_PALETTE)


@dataclass(slots=True)
class NovelSource:
    db_path: str
    novel_id: str
    label: str = ""

    def __post_init__(self) -> None:
        self.label = self.label or self.novel_id.replace("-", " ").title()


def _entity_colour(rank: int) -> str:
    if rank < _COLOURED_RANKS:
        return _PALETTE[rank]
    return "#8a8a8a"


def build_novel_payload(store: Store, novel_id: str, label: str) -> dict:
    """Everything the viewer needs for one novel, JSON-serialisable."""
    mentions = store.get_mentions(novel_id)
    by_target: dict[str, list] = {}
    for m in mentions:
        if m.target_id:
            by_target.setdefault(m.target_id, []).append(m)

    ranked = sorted(by_target.items(), key=lambda kv: len(kv[1]), reverse=True)
    colour_of: dict[str, str] = {}
    entities = []
    for rank, (target_id, group) in enumerate(ranked):
        entity = store.get_self(target_id)
        surfaces: dict[str, int] = {}
        for m in group:
            surfaces[m.text] = surfaces.get(m.text, 0) + 1
        colour = _entity_colour(rank)
        colour_of[target_id] = colour
        chapters = [m.chapter for m in group]
        entities.append(
            {
                "id": target_id,
                "label": entity.canonical_label if entity else max(surfaces, key=surfaces.get),
                "count": len(group),
                "first_chapter": min(chapters),
                "last_chapter": max(chapters),
                "aliases": sorted(surfaces, key=surfaces.get, reverse=True)[:10],
                "colour": colour,
                "speaks": False,  # filled in below once spans are walked
            }
        )
    entity_index = {e["id"]: e for e in entities}

    dialogue_total = 0
    dialogue_attributed = 0
    dialogue_anonymous = 0
    #: Shared across all chapters rather than rebuilt per chapter -- a
    #: recurring speaker's label is looked up once for the whole novel.
    speaker_label_cache: dict[str, str | None] = {}

    def speaker_label(self_id: str | None) -> str | None:
        if not self_id:
            return None
        if self_id not in speaker_label_cache:
            anon = _anon_slot_label(self_id)
            if anon is not None:
                speaker_label_cache[self_id] = anon
            else:
                e = store.get_self(self_id)
                speaker_label_cache[self_id] = e.canonical_label if e else self_id
        return speaker_label_cache[self_id]

    chapters_out = []
    for chapter in store.iter_chapters(novel_id):
        n = chapter.number
        spans = store.get_spans(novel_id, n)
        chapter_mentions = store.get_mentions(novel_id, chapter=n)
        by_block: dict[int, list] = {}
        for m in chapter_mentions:
            by_block.setdefault(m.block_index, []).append(m)

        span_rows = []
        for span in spans:
            in_span = sorted(
                (
                    m
                    for m in by_block.get(span.block_index, [])
                    if span.start <= m.offset < span.end
                ),
                key=lambda m: m.offset,
            )
            marks = []
            for m in in_span:
                local_start = m.offset - span.start
                local_end = local_start + len(m.text)
                if local_end > len(span.text) or local_start < 0:
                    # A mention that doesn't fit its own span's text is a data
                    # inconsistency, not a rendering choice -- skip rather than
                    # emit a mark that would slice the wrong characters.
                    continue
                entity = entity_index.get(m.target_id) if m.target_id else None
                marks.append(
                    {
                        "s": local_start,
                        "e": local_end,
                        "id": m.target_id,
                        "label": entity["label"] if entity else m.text,
                        "colour": entity["colour"] if entity else "#8a8a8a",
                        "resolved": m.target_id is not None,
                        "conf": round(float(m.confidence), 2),
                        "alias_type": m.alias_type.value,
                        # `Mention.id`, not a derived key -- this is what makes
                        # a mention individually correctable (reassign this one
                        # occurrence, independent of every other mention that
                        # happens to share its surface text).
                        "mention_id": m.id,
                        "surface": m.text,
                    }
                )

            speaker = speaker_label(span.speaker_self_id)
            is_anon_speaker = bool(span.speaker_self_id and _anon_slot_label(span.speaker_self_id))
            if speaker and span.speaker_self_id and span.speaker_self_id in entity_index:
                entity_index[span.speaker_self_id]["speaks"] = True
            is_dialogue = span.span_type.value == "DIALOGUE"
            if is_dialogue:
                dialogue_total += 1
                if speaker and not is_anon_speaker:
                    dialogue_attributed += 1
                elif is_anon_speaker:
                    dialogue_anonymous += 1

            span_rows.append(
                {
                    "span_id": span.id,
                    "type": span.span_type.value,
                    "text": span.text,
                    "speaker": speaker,
                    "speaker_id": span.speaker_self_id,
                    "method": span.attribution_method.value,
                    "marks": marks,
                    # A distinct voice, not a distinct *identity* -- see
                    # `speakers/runner.py::_assign_anonymous_slots`. The
                    # frontend styles this differently from both a named
                    # speaker and genuinely missing attribution.
                    "anonymous_speaker": is_anon_speaker,
                    "speaker_colour": (
                        _anon_slot_colour(span.speaker_self_id) if is_anon_speaker else None
                    ),
                }
            )
        chapters_out.append({"number": n, "spans": span_rows})

    resolved = sum(len(v) for v in by_target.values())
    singletons = sum(1 for e in entities if e["count"] == 1)

    return {
        "novel_id": novel_id,
        "label": label,
        "stats": {
            "chapters": len(chapters_out),
            "mentions": len(mentions),
            "resolved": resolved,
            "resolution_rate": (resolved / len(mentions)) if mentions else 0.0,
            "entities": len(entities),
            "singletons": singletons,
            "singleton_rate": (singletons / len(entities)) if entities else 0.0,
            "dialogue_total": dialogue_total,
            "dialogue_attributed": dialogue_attributed,
            "dialogue_anonymous": dialogue_anonymous,
            "attribution_rate": (
                dialogue_attributed / dialogue_total if dialogue_total else 0.0
            ),
        },
        "entities": entities,
        "chapters": chapters_out,
    }


def write_webview(sources: list[NovelSource], out_dir: Path | str) -> Path:
    """Build the full static app: one data file per novel plus the shell."""
    out = Path(out_dir)
    (out / "data").mkdir(parents=True, exist_ok=True)

    manifest = []
    for src in sources:
        store = Store(src.db_path)
        payload = build_novel_payload(store, src.novel_id, src.label)
        store.close()
        data_path = out / "data" / f"{src.novel_id}.js"
        data_path.write_text(
            f"window.NOVELS=window.NOVELS||{{}};"
            f"window.NOVELS[{json.dumps(src.novel_id)}]={json.dumps(payload, ensure_ascii=False)};",
            encoding="utf-8",
        )
        manifest.append({"id": src.novel_id, "label": src.label, "file": data_path.name})

    (out / "manifest.js").write_text(
        f"window.NOVEL_MANIFEST={json.dumps(manifest, ensure_ascii=False)};",
        encoding="utf-8",
    )
    (out / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
    (out / "app.js").write_text(_APP_JS, encoding="utf-8")
    (out / "style.css").write_text(_STYLE_CSS, encoding="utf-8")
    return out / "index.html"


def write_webview_json(sources: list[NovelSource], out_dir: Path | str) -> Path:
    """The same payload as `write_webview`, as plain JSON for the React app.

    Meant for `webview/public/data/` -- Create React App serves `public/` as
    static files reachable by `fetch()` at runtime, both from `npm start` and
    from a production `npm run build` served over HTTP. That's the opposite
    tradeoff from `write_webview`: this needs a server (`fetch()` of a `file://`
    JSON is blocked by same-origin, same reason the static build avoids fetch
    entirely), but plain JSON is what a normal SPA data-fetch expects, rather
    than the `<script src>`-as-global-variable trick the dependency-free static
    version needs to work around that same restriction.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest = []
    for src in sources:
        store = Store(src.db_path)
        payload = build_novel_payload(store, src.novel_id, src.label)
        store.close()
        data_path = out / f"{src.novel_id}.json"
        data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        manifest.append({"id": src.novel_id, "label": src.label, "file": data_path.name})

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path


_STYLE_CSS = """
:root {
  color-scheme: light dark;
  --bg: Canvas; --fg: CanvasText; --muted: color-mix(in srgb, CanvasText 55%, transparent);
  --panel: color-mix(in srgb, CanvasText 6%, Canvas);
  --border: color-mix(in srgb, CanvasText 15%, transparent);
  --accent: #4E79A7;
}
* { box-sizing: border-box; }
body {
  margin: 0; font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--fg);
  display: grid; grid-template-columns: 300px 1fr; grid-template-rows: auto 1fr; height: 100vh;
}
header {
  grid-column: 1 / -1; display: flex; align-items: center; gap: 1rem;
  padding: .6rem 1rem; border-bottom: 1px solid var(--border); background: var(--panel);
}
header h1 { font-size: 1rem; margin: 0; font-weight: 600; }
header .sub { font-size: .8rem; color: var(--muted); }
select, input[type=search] {
  font: inherit; padding: .35rem .5rem; border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg); color: var(--fg);
}
#novel-select { font-weight: 600; }
.stats-strip { display: flex; gap: 1.1rem; margin-left: auto; font-size: .78rem; color: var(--muted); }
.stats-strip b { color: var(--fg); font-variant-numeric: tabular-nums; }
.stats-strip .warn b { color: #c9532b; }

aside {
  border-right: 1px solid var(--border); overflow-y: auto; background: var(--panel);
  display: flex; flex-direction: column;
}
aside .search { padding: .6rem; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--panel); }
aside .search input { width: 100%; }
#entity-list { list-style: none; margin: 0; padding: .3rem; overflow-y: auto; flex: 1; }
#entity-list li {
  display: flex; align-items: center; gap: .5rem; padding: .38rem .5rem; border-radius: 6px;
  cursor: pointer; font-size: .86rem;
}
#entity-list li:hover { background: color-mix(in srgb, CanvasText 8%, transparent); }
#entity-list li.active { background: color-mix(in srgb, var(--accent) 22%, transparent); }
#entity-list .swatch { width: .7rem; height: .7rem; border-radius: 50%; flex: none; }
#entity-list .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#entity-list .count { color: var(--muted); font-variant-numeric: tabular-nums; font-size: .78rem; }
#entity-list .speaks { opacity: .55; font-size: .7rem; }

main { overflow-y: auto; padding: 0; }
#chapter-nav {
  display: flex; align-items: center; gap: .5rem; padding: .5rem 1.2rem; border-bottom: 1px solid var(--border);
  position: sticky; top: 0; background: var(--bg); z-index: 2;
}
#chapter-nav button {
  font: inherit; border: 1px solid var(--border); background: var(--panel); color: var(--fg);
  border-radius: 6px; padding: .3rem .6rem; cursor: pointer;
}
#chapter-nav button:disabled { opacity: .35; cursor: default; }
#chapter-nav select { flex: none; }
#chapter-nav .cov { margin-left: auto; font-size: .78rem; color: var(--muted); }

#script { max-width: 780px; margin: 0 auto; padding: 1.4rem 1.4rem 6rem; }
.line { display: grid; grid-template-columns: 9.5rem 1fr; gap: .8rem; padding: .55rem 0; }
.line + .line { border-top: 1px solid color-mix(in srgb, CanvasText 8%, transparent); }
.line.dialogue { background: color-mix(in srgb, var(--accent) 6%, transparent); border-radius: 8px; padding-inline: .6rem; margin-inline: -.6rem; }
.line.dim .body { opacity: .35; }
.speaker { text-align: right; font-weight: 600; font-size: .86rem; padding-top: .05rem; }
.speaker.missing { color: #c9532b; font-weight: 400; font-style: italic; opacity: .8; }
.speaker.anonymous { font-weight: 400; font-style: italic; }
.speaker .method { display: block; font-weight: 400; font-size: .68rem; color: var(--muted); }
.speaker .thinking { font-weight: 400; font-style: italic; opacity: .85; }
.tag { display: inline-block; font-size: .65rem; text-transform: uppercase; letter-spacing: .04em;
       color: var(--muted); margin-right: .5rem; vertical-align: 1px; }
.body { }
mark {
  background: transparent; color: inherit; font-weight: 600;
  border-bottom: 2px solid var(--mk, #8a8a8a); padding: 0 1px; cursor: help; position: relative;
}
mark.unresolved { border-bottom-style: dotted; font-weight: 400; }
mark.dim { opacity: .3; }
mark.focus { background: color-mix(in srgb, var(--mk, #8a8a8a) 30%, transparent); border-radius: 3px; }

#tooltip {
  position: fixed; pointer-events: none; background: var(--fg); color: var(--bg);
  font-size: .78rem; padding: .3rem .55rem; border-radius: 5px; z-index: 50; display: none;
  max-width: 260px; box-shadow: 0 2px 10px rgba(0,0,0,.25);
}
#empty { padding: 3rem; text-align: center; color: var(--muted); }
"""

_INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EchoTales — coref &amp; attribution viewer</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <h1>EchoTales viewer</h1>
  <select id="novel-select"></select>
  <span class="sub" id="novel-sub"></span>
  <div class="stats-strip" id="stats-strip"></div>
</header>
<aside>
  <div class="search"><input type="search" id="entity-search" placeholder="Filter entities…"></div>
  <ul id="entity-list"></ul>
</aside>
<main>
  <div id="chapter-nav">
    <button id="prev-ch">&larr;</button>
    <select id="chapter-select"></select>
    <button id="next-ch">&rarr;</button>
    <span class="cov" id="chapter-cov"></span>
  </div>
  <div id="script"></div>
  <div id="empty" style="display:none">No data. Run <code>echotales webview</code> to build this file.</div>
</main>
<div id="tooltip"></div>
<script src="manifest.js"></script>
<script>
(function loadAll(manifest, i){
  if (i >= manifest.length) { window.dispatchEvent(new Event('novels-ready')); return; }
  var s = document.createElement('script');
  s.src = 'data/' + manifest[i].file;
  s.onload = function(){ loadAll(manifest, i+1); };
  document.head.appendChild(s);
})(window.NOVEL_MANIFEST || [], 0);
</script>
<script src="app.js"></script>
</body>
</html>
"""

_APP_JS = r"""
'use strict';
var state = { novelId: null, chapterIdx: 0, filterEntityId: null, search: '' };

function el(tag, attrs, children) {
  var e = document.createElement(tag);
  for (var k in (attrs || {})) {
    if (k === 'class') e.className = attrs[k];
    else if (k === 'text') e.textContent = attrs[k];
    else e.setAttribute(k, attrs[k]);
  }
  (children || []).forEach(function(c) { if (c) e.appendChild(c); });
  return e;
}

function currentNovel() { return window.NOVELS[state.novelId]; }

function pct(x) { return Math.round(x * 100) + '%'; }

function renderStats() {
  var n = currentNovel(), s = n.stats;
  var strip = document.getElementById('stats-strip');
  strip.innerHTML = '';
  function stat(label, value, warn) {
    var d = el('div', { class: warn ? 'warn' : '' });
    d.appendChild(el('b', { text: value }));
    d.appendChild(document.createTextNode(' ' + label));
    strip.appendChild(d);
  }
  stat('chapters', s.chapters);
  stat('mentions', s.mentions.toLocaleString());
  stat('resolved', pct(s.resolution_rate));
  stat('entities', s.entities);
  stat('seen once', pct(s.singleton_rate), s.singleton_rate > 0.4);
  stat('dialogue attributed', pct(s.attribution_rate), s.attribution_rate < 0.6);
  if (s.dialogue_anonymous > 0) stat('anonymous', s.dialogue_anonymous.toLocaleString());
  document.getElementById('novel-sub').textContent =
    n.chapters.length + ' chapters loaded';
}

function renderEntityList() {
  var n = currentNovel();
  var list = document.getElementById('entity-list');
  list.innerHTML = '';
  var q = state.search.toLowerCase();
  n.entities.forEach(function(ent) {
    if (q && ent.label.toLowerCase().indexOf(q) === -1) return;
    var li = el('li', { class: ent.id === state.filterEntityId ? 'active' : '' }, [
      el('span', { class: 'swatch', style: 'background:' + ent.colour }),
      el('span', { class: 'name', text: ent.label }),
      ent.speaks ? el('span', { class: 'speaks', text: '\u{1F5E3}' }) : null,
      el('span', { class: 'count', text: ent.count })
    ]);
    li.title = ent.aliases.join(', ') + '  ·  ch' + ent.first_chapter + '–' + ent.last_chapter;
    li.onclick = function() {
      state.filterEntityId = state.filterEntityId === ent.id ? null : ent.id;
      renderEntityList();
      renderChapter();
    };
    list.appendChild(li);
  });
}

function renderChapterSelect() {
  var n = currentNovel();
  var sel = document.getElementById('chapter-select');
  sel.innerHTML = '';
  n.chapters.forEach(function(ch, i) {
    sel.appendChild(el('option', { value: i, text: 'Chapter ' + ch.number }));
  });
  sel.value = state.chapterIdx;
}

function buildLineBody(span, focusId) {
  var text = span.text;
  var marks = span.marks.slice().sort(function(a, b) { return a.s - b.s; });
  var frag = document.createDocumentFragment();
  var pos = 0;
  marks.forEach(function(m) {
    if (m.s < pos || m.e > text.length) return; // defensive: skip malformed offsets
    if (m.s > pos) frag.appendChild(document.createTextNode(text.slice(pos, m.s)));
    var cls = 'mark' + (m.resolved ? '' : ' unresolved') +
      (focusId && m.id !== focusId ? ' dim' : '') +
      (focusId && m.id === focusId ? ' focus' : '');
    var mk = el('mark', { class: cls.replace('mark', '').trim(), style: '--mk:' + m.colour });
    mk.textContent = text.slice(m.s, m.e);
    mk.dataset.tip = m.label + (m.resolved ? '' : '  (unresolved)') + '  ·  conf ' + m.conf;
    frag.appendChild(mk);
    pos = m.e;
  });
  if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
  return frag;
}

function renderChapter() {
  var n = currentNovel();
  var ch = n.chapters[state.chapterIdx];
  var root = document.getElementById('script');
  root.innerHTML = '';
  var focusId = state.filterEntityId;

  var dialogueTotal = 0, dialogueAttr = 0;
  ch.spans.forEach(function(s) {
    if (s.type === 'DIALOGUE') { dialogueTotal++; if (s.speaker) dialogueAttr++; }
  });
  document.getElementById('chapter-cov').textContent =
    dialogueTotal ? (dialogueAttr + '/' + dialogueTotal + ' dialogue lines attributed') : 'no dialogue';

  ch.spans.forEach(function(span) {
    var isDialogue = span.type === 'DIALOGUE';
    // Whose thought this is matters as much as who's speaking. The pipeline
    // already resolves it (speakers/attribution.py::pov_holder, logged as
    // POV_INFERRED) but this view used to only ever show the speaker column
    // for DIALOGUE, so a paragraph of inner monologue gave no way to tell
    // whose head it was inside without cross-referencing chapter POV by hand.
    var isInnerMonologue = span.type === 'INNER_MONOLOGUE';
    var relevant = !focusId || span.marks.some(function(m) { return m.id === focusId; }) ||
      span.speaker_id === focusId;
    var rowClass = 'line' + (isDialogue ? ' dialogue' : '') + (focusId && !relevant ? ' dim' : '');
    var speakerCell;
    if (isDialogue) {
      var speakerCls = 'speaker' + (span.speaker ? '' : ' missing') + (span.anonymous_speaker ? ' anonymous' : '');
      speakerCell = el('div', { class: speakerCls });
      if (span.anonymous_speaker && span.speaker_colour) speakerCell.style.color = span.speaker_colour;
      speakerCell.appendChild(document.createTextNode(span.speaker || 'unattributed'));
      speakerCell.appendChild(el('span', {
        class: 'method',
        text: span.anonymous_speaker ? 'anonymous' : (span.speaker ? span.method : '')
      }));
    } else if (isInnerMonologue && span.speaker) {
      speakerCell = el('div', { class: 'speaker' });
      speakerCell.appendChild(el('span', { class: 'thinking', text: span.speaker }));
      speakerCell.appendChild(el('span', { class: 'method', text: 'thinking' }));
    } else {
      speakerCell = el('div', { class: 'speaker', style: 'opacity:.3', text: '' });
    }
    var bodyCell = el('div', { class: 'body' });
    bodyCell.appendChild(el('span', { class: 'tag', text: span.type.replace(/_/g, ' ') }));
    bodyCell.appendChild(buildLineBody(span, focusId));
    root.appendChild(el('div', { class: rowClass }, [speakerCell, bodyCell]));
  });

  document.querySelectorAll('#script mark').forEach(function(m) {
    m.addEventListener('mouseenter', showTip);
    m.addEventListener('mousemove', moveTip);
    m.addEventListener('mouseleave', hideTip);
  });
}

var tooltip = null;
function showTip(e) {
  tooltip = tooltip || document.getElementById('tooltip');
  tooltip.textContent = e.target.dataset.tip;
  tooltip.style.display = 'block';
  moveTip(e);
}
function moveTip(e) {
  if (!tooltip) return;
  tooltip.style.left = (e.clientX + 14) + 'px';
  tooltip.style.top = (e.clientY + 14) + 'px';
}
function hideTip() { if (tooltip) tooltip.style.display = 'none'; }

function setNovel(id) {
  state.novelId = id;
  state.chapterIdx = 0;
  state.filterEntityId = null;
  renderStats();
  renderEntityList();
  renderChapterSelect();
  renderChapter();
}

function init() {
  var manifest = window.NOVEL_MANIFEST || [];
  var loaded = manifest.filter(function(m) { return window.NOVELS && window.NOVELS[m.id]; });
  if (!loaded.length) {
    document.getElementById('empty').style.display = 'block';
    return;
  }
  var novelSelect = document.getElementById('novel-select');
  loaded.forEach(function(m) {
    novelSelect.appendChild(el('option', { value: m.id, text: m.label }));
  });
  novelSelect.onchange = function() { setNovel(novelSelect.value); };

  document.getElementById('chapter-select').onchange = function(e) {
    state.chapterIdx = parseInt(e.target.value, 10);
    renderChapter();
  };
  document.getElementById('prev-ch').onclick = function() {
    if (state.chapterIdx > 0) { state.chapterIdx--; syncChapterSelect(); renderChapter(); }
  };
  document.getElementById('next-ch').onclick = function() {
    if (state.chapterIdx < currentNovel().chapters.length - 1) {
      state.chapterIdx++; syncChapterSelect(); renderChapter();
    }
  };
  document.getElementById('entity-search').oninput = function(e) {
    state.search = e.target.value;
    renderEntityList();
  };

  setNovel(loaded[0].id);
}

function syncChapterSelect() {
  document.getElementById('chapter-select').value = state.chapterIdx;
}

if (window.NOVEL_MANIFEST && window.NOVEL_MANIFEST.every(function(m){ return window.NOVELS && window.NOVELS[m.id]; })) {
  init();
} else {
  window.addEventListener('novels-ready', init);
}
"""
