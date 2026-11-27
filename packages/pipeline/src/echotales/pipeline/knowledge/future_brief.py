"""Future-aware brief for a chapter: who and what mentioned here matters later, and what is set up for later.

The storyboard director reads it so a name spoken in chapter 1 can be drawn as a referenced inset when the book will
show that person in the flesh (owner gold, RI ch1: the rival genius is only discussed; his look is in later chapters).
A setup is an entity or item in this chapter whose sentence's event verb recurs in a later sentence naming the same
entity. Verbs common to the whole volume (said, looked) are learned from the text and ignored.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from echotales.core.enums import TargetKind
from echotales.core.store import Store
from echotales.pipeline.knowledge.common import artifact_id, get_artifact, put_artifact
from echotales.pipeline.knowledge.dossier import dossier_at, first_in_person_chapter

#: An entity "matters later" when this many distinct later chapters mention it.
MATTERS_LATER_CHAPTERS = 3
_SENT = re.compile(r"(?<=[.!?”\"])\s+")
_NLP: Any = None
_COMMON: dict[str, set[str]] = {}


def _nlp() -> Any:
    global _NLP
    if _NLP is None:
        import spacy

        _NLP = spacy.load("en_core_web_sm", disable=["ner"])
    return _NLP


def _verbs(sentence: str) -> set[str]:
    return {t.lemma_.lower() for t in _nlp()(sentence) if t.pos_ == "VERB" and not t.is_stop and len(t.lemma_) > 2}


def common_verbs(store: Store, novel_id: str, sample: int = 30) -> set[str]:
    """Verb lemmas in at least 40% of an evenly spaced chapter sample: the book's own filler, learned not listed."""
    if novel_id in _COMMON:
        return _COMMON[novel_id]
    numbers = store.chapter_numbers(novel_id)
    step = max(len(numbers) / sample, 1)
    df: Counter[str] = Counter()
    docs = 0
    for i in range(min(sample, len(numbers))):
        ch = store.get_chapter(novel_id, numbers[int(i * step)])
        if ch is None:
            continue
        docs += 1
        df.update({t.lemma_.lower() for t in _nlp()(ch.story_text[:6000]) if t.pos_ == "VERB"})
    _COMMON[novel_id] = {v for v, n in df.items() if n >= 0.4 * max(docs, 1)}
    return _COMMON[novel_id]


def _sentence_with(store: Store, novel_id: str, chapter: float, block: int, surface: str) -> str | None:
    ch = store.get_chapter(novel_id, chapter)
    if ch is None:
        return None
    text = next((b.text for b in ch.blocks if b.index == block), "")
    rx = re.compile(re.escape(surface), re.IGNORECASE)
    return next((s.strip() for s in _SENT.split(text) if rx.search(s)), None)


def _setups(
    store: Store, novel_id: str, chapter: float, target_id: str, surfaces: dict[int, str], later: list[tuple[float, int, str]],
) -> list[dict[str, Any]]:
    common = common_verbs(store, novel_id)
    here = {}
    for block, surface in list(surfaces.items())[:6]:
        sent = _sentence_with(store, novel_id, chapter, block, surface)
        if sent:
            for v in _verbs(sent) - common:
                here.setdefault(v, sent)
    if not here or not later:
        return []
    step = max(len(later) / 40, 1)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i in range(min(len(later), 40)):
        ch, block, surface = later[int(i * step)]
        sent = _sentence_with(store, novel_id, ch, block, surface)
        for v in (_verbs(sent) - common) & set(here) if sent else ():
            if v not in seen and len(out) < 3:
                seen.add(v)
                out.append({"event": v, "here": here[v][:200], "later_chapter": ch, "later": (sent or "")[:200]})
    return out


def build_brief(store: Store, novel_id: str, chapter: float, *, with_setups: bool = True) -> dict[str, Any]:
    mentions = [m for m in store.get_mentions(novel_id, chapter) if m.target_id]
    by_target: dict[str, list[Any]] = defaultdict(list)
    for m in mentions:
        by_target[m.target_id].append(m)
    entries = []
    for tid, ms in by_target.items():
        entity = store.get_self(tid)
        if entity is None or entity.kind in (TargetKind.LOCATION,):
            continue
        rows = store.conn.execute(
            "SELECT chapter, block_index, text FROM mention WHERE novel_id=? AND target_id=? ORDER BY chapter, block_index",
            (novel_id, tid)).fetchall()
        chapters = sorted({r["chapter"] for r in rows})
        after = [c for c in chapters if c > chapter]
        later = [(r["chapter"], r["block_index"], r["text"]) for r in rows if r["chapter"] > chapter]
        in_person = first_in_person_chapter(store, novel_id, tid)
        dossier = dossier_at(store, novel_id, tid, chapter) if entity.kind.is_person else None
        bits = []
        if dossier:
            bits += [f.value for f in dossier.roles[:2]] + [f.value for f in dossier.affiliations[:1]]
            bits += [f.value for f in dossier.appearance.get("apparent_age", [])[:1]]
        role = (f"{entity.canonical_label} ({entity.kind.value.lower()}, {entity.prominence.value.lower()}): "
                + ("; ".join(dict.fromkeys(bits)) or "no role recorded")
                + f". Mentioned in {len(chapters)} chapters (ch{chapters[0]:g} to ch{chapters[-1]:g})"
                + (f", first in person ch{in_person:g}" if in_person is not None else "") + ".")
        entries.append({
            "entity_id": tid, "label": entity.canonical_label, "kind": entity.kind.value, "prominence": entity.prominence.value,
            "mentions_here": len(ms), "first_mention_chapter": chapters[0], "first_in_person_chapter": in_person,
            "last_chapter": chapters[-1], "chapters_after": len(after), "matters_later": len(after) >= MATTERS_LATER_CHAPTERS,
            "role_summary": role,
            "setups": _setups(store, novel_id, chapter, tid, {m.block_index: m.text for m in ms}, later)
            if with_setups and after else [],
        })
    entries.sort(key=lambda e: (-int(e["matters_later"]), -e["chapters_after"]))
    payload = {"novel_id": novel_id, "chapter": chapter, "entities": entries}
    put_artifact(store, artifact_id("brief", novel_id, f"{chapter:g}"), payload)
    return payload


def build_briefs(store: Store, novel_id: str, chapters: list[float], *, say: Any = print) -> list[dict[str, Any]]:
    out = []
    for n in chapters:
        out.append(build_brief(store, novel_id, n))
        say(f"brief ch{n:g}: {len(out[-1]['entities'])} entities, {sum(1 for e in out[-1]['entities'] if e['matters_later'])} matter later")
    return out


def load_brief(store: Store, novel_id: str, chapter: float) -> dict[str, Any] | None:
    return get_artifact(store, artifact_id("brief", novel_id, f"{chapter:g}"))


__all__ = ["build_brief", "build_briefs", "load_brief"]
