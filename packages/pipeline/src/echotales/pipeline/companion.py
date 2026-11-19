"""The spoiler-safe companion: "who is this again?" as a reader who has finished chapter N knows it.

Everything is filtered on the server side, from the graph, before it is written: the page cannot reveal a later
chapter because the later chapter is not in it. Cards come from `webview.build_reader_cast` (whose
`tests/test_reader_cast.py` checks it against a book truncated at the reading position); relationships and
timeline names go through the same knowledge-time filter `state_of` uses (`core.state._visible_to_observer`), so one
rule decides what the reader knows. No sentence of the book is carried: labels, aliases, relation types and chapter
numbers only. Relation `evidence` and chapter titles are left out on purpose (a title is book text).
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from echotales.core.enums import OBSERVER_READER, AliasType
from echotales.core.models import DiscoursePosition
from echotales.core.state import _visible_to_observer
from echotales.core.store import Store
from echotales.pipeline.webview import build_reader_cast


def build_companion(store: Store, novel_id: str, through: float) -> dict[str, Any]:
    cast = build_reader_cast(store, novel_id, through)["entities"]
    # The same position `build_reader_cast` reads persona traits at: the end of chapter `through`.
    known_by = DiscoursePosition(chapter=int(through), offset=10**6)
    label_of = {e["id"]: e["label"] for e in cast}

    cards = [
        {
            "id": e["id"], "label": e["label"], "aliases": e["aliases"], "first_chapter": _n(e["first_chapter"]),
            "last_chapter": _n(e["last_chapter"]), "mentions": e["count"], "speaks": e["speaks"],
            "traits": e["traits"], "colour": e["colour"],
        }
        for e in cast if e["is_person"]
    ]
    glossary = [
        {"id": e["id"], "term": e["label"], "kind": e["kind"].lower(), "aliases": e["aliases"],
         "first_chapter": _n(e["first_chapter"])}
        for e in sorted((e for e in cast if not e["is_person"]), key=lambda e: e["label"].lower())
    ]

    relationships = []
    for e in cast:
        if not e["is_person"]:
            continue
        for r in store.get_relations(e["id"]):
            # Both ends must be someone the reader has met: a relation whose other end first appears later would
            # name that character.
            if r.dst_self in label_of and _visible_to_observer(r, OBSERVER_READER, known_by):
                relationships.append({"from": r.src_self, "from_label": label_of[r.src_self],
                                      "to": r.dst_self, "to_label": label_of[r.dst_self], "type": r.type,
                                      "since": r.learned_at_pos.chapter})
    relationships.sort(key=lambda r: (r["since"], r["from"], r["to"], r["type"]))

    timeline = [{"chapter": c["first_chapter"], "text": f"{c['label']} first appears"} for c in cards]
    timeline += [{"chapter": g["first_chapter"], "text": f"{g['term']} is first mentioned"} for g in glossary]
    timeline += [{"chapter": r["since"], "text": f"{r['from_label']} and {r['to_label']}: {r['type']}"}
                 for r in relationships]
    for b in store.all_aliases(novel_id):
        if (b.target_id in label_of and b.alias_type is AliasType.RIGID_NAME
                and b.alias != label_of[b.target_id] and _visible_to_observer(b, OBSERVER_READER, known_by)):
            timeline.append({"chapter": b.learned_at_pos.chapter, "text": f"{label_of[b.target_id]} is also called {b.alias}"})
    timeline.sort(key=lambda e: (e["chapter"], e["text"]))

    novel = store.get_novel(novel_id) or {}
    return {
        "novel_id": novel_id, "title": novel.get("title", novel_id), "through": _n(through),
        "cards": cards, "relationships": relationships, "timeline": timeline, "glossary": glossary,
    }


def _n(x: float) -> int | float:
    return int(x) if float(x).is_integer() else x


_CSS = """\
:root { --bg: #fbfaf7; --fg: #1f1d1a; --muted: #6b665e; --line: #dcd7cd; --card: #fff; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161513; --fg: #eeebe4; --muted: #a29d93; --line: #35322d; --card: #1f1d1a; }
}
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; }
main { max-width: 52rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
h1 { margin: 0 0 .25rem; } h2 { margin-top: 2.5rem; border-bottom: 1px solid var(--line); padding-bottom: .25rem; }
.note { color: var(--muted); margin: 0 0 1rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: .75rem; padding: 0; list-style: none; }
.card { background: var(--card); border: 1px solid var(--line); border-left-width: 6px; border-radius: 6px; padding: .6rem .8rem; }
.card h3 { margin: 0 0 .2rem; font-size: 1.05rem; }
.meta { color: var(--muted); font-size: .875rem; }
ul.plain { padding-left: 1.1rem; } dt { font-weight: 600; } dd { margin: 0 0 .6rem; }
"""


def _e(x: object) -> str:
    return html.escape(str(x), quote=True)


def write_companion_site(data: dict[str, Any], out_dir: Path | str) -> Path:
    """index.html (everything inline, no script, no fetch), style.css and companion.json.

    JSON is written beside the page for tools; the page itself carries no script because a `file://` page cannot
    fetch a sibling file in most browsers, and the companion has to work offline from a double-click.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cards = "".join(
        f'<li class="card" style="border-left-color:{_e(c["colour"])}"><h3>{_e(c["label"])}</h3>'
        f'<div class="meta">chapters {_e(c["first_chapter"])} to {_e(c["last_chapter"])}'
        + (", " + _e(", ".join(f"{k}: {v}" for k, v in c["traits"].items())) if c["traits"] else "")
        + ("" if not c["speaks"] else ", speaks")
        + "</div>"
        + (f'<div class="meta">also: {_e(", ".join(a for a in c["aliases"] if a != c["label"]))}</div>'
           if any(a != c["label"] for a in c["aliases"]) else "")
        + "</li>"
        for c in data["cards"]
    )
    rels = "".join(
        f'<li>{_e(r["from_label"])} and {_e(r["to_label"])}: {_e(r["type"])} <span class="meta">(chapter {_e(r["since"])})</span></li>'
        for r in data["relationships"]
    )
    timeline = "".join(f'<li><span class="meta">chapter {_e(e["chapter"])}</span> {_e(e["text"])}</li>' for e in data["timeline"])
    glossary = "".join(
        f'<dt>{_e(g["term"])}</dt><dd>{_e(g["kind"])}, first mentioned in chapter {_e(g["first_chapter"])}</dd>'
        for g in data["glossary"]
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(data["title"])} companion</title><link rel="stylesheet" href="style.css"></head>
<body><main>
<h1>{_e(data["title"])}</h1>
<p class="note">Spoiler-safe through chapter {_e(data["through"])}. Nothing from later chapters is in this page.</p>
<h2>Characters</h2><ul class="cards">{cards or "<li>No one yet.</li>"}</ul>
<h2>Relationships</h2><ul class="plain">{rels or "<li>None yet.</li>"}</ul>
<h2>Timeline</h2><ul class="plain">{timeline or "<li>Nothing yet.</li>"}</ul>
<h2>Glossary</h2><dl>{glossary or "<dd>None yet.</dd>"}</dl>
</main></body></html>
"""
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "style.css").write_text(_CSS, encoding="utf-8")
    (out / "companion.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
