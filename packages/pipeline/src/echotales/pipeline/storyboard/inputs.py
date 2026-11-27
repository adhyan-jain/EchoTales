"""What the director reads for one chapter, and the adapters to the two contracts built in parallel.

Why adapters: `segment.presence.present_cast` and `persona.looks.look_at` are being written by other workstreams. The
director codes against their signatures through `try: import`, with a fallback that is deliberately weaker, so this stage
runs today and gets better when they land without a code change here. Every fallback use is recorded on the input
(`presence_contract`, `look_contract`) and printed in the scorecard, so a result is never read as having had the real
presence model when it did not.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from echotales.core.store import Store
from echotales.pipeline.storyboard.schema import Layer

#: A block that is only an ellipsis or a rule: the unmarked-cut tell in web-novel text (RI ch1 block 30 precedes a cut).
_SEPARATOR = re.compile(r"^\s*(?:[.…。·*\-—–_~\s]|…)+\s*$")
_SPEECH_KINDS = {"DIALOGUE"}
_THOUGHT_KINDS = {"INNER_MONOLOGUE"}
#: Windows are bounded so one call fits the 8 GB card at num_ctx 8192 with the grammar, few-shots and the answer.
MAX_WINDOW_BLOCKS = 14
MAX_WINDOW_WORDS = 520
#: A heuristic scene split is only trusted when both halves are real scenes: RI ch1's "……" at block 4 ends the hook, not a
#: scene (reference S1 and S2 are one place), while the one at block 30 precedes the ritual.
MIN_SCENE_BLOCKS = 8


@dataclass(slots=True)
class Line:
    """One unit of source text the director can letter into a panel: a quoted line or a narration span."""

    id: str  # "s12": stable tag the model refers to, so it never retypes (and so never alters) source text
    block: int
    kind: str  # "speech" | "thought" | "narration"
    text: str
    speaker_id: str | None = None
    speaker_name: str = ""
    span_id: str | None = None  # the DB span (or `<novel>:<chapter>:b<block>` for a block the span pass left whole)


@dataclass(slots=True)
class RosterEntry:
    entity_id: str
    name: str
    look: str = ""  # one-line current look, for the prompt only
    look_id: str | None = None

    @property
    def tokens(self) -> frozenset[str]:
        return frozenset(_norm(self.name).split())


@dataclass(slots=True)
class Scene:
    block_from: int
    block_to: int  # inclusive
    layer: Layer = Layer.PRESENT
    story_time: str = ""
    place: str = ""
    present_ids: list[str] = field(default_factory=list)
    referenced_ids: list[str] = field(default_factory=list)
    cut_signal: str = ""
    from_graph: bool = True  # False: boundary found by the director itself


@dataclass(slots=True)
class ChapterInput:
    novel_id: str
    chapter: float
    blocks: dict[int, str]  # story blocks only (translator notes and rules removed)
    lines: list[Line]
    roster: list[RosterEntry]
    scenes: list[Scene]
    presence_contract: bool = False
    look_contract: bool = False
    #: display names of people the model named who are not in the graph (`extra:`/`ref:` ids), filled by the director
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def block_ids(self) -> list[int]:
        return sorted(self.blocks)

    def line(self, line_id: str) -> Line | None:
        return next((ln for ln in self.lines if ln.id == line_id), None)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("-", " ").replace("_", " ")).strip()


def match_entry(name: str, roster: list[RosterEntry]) -> RosterEntry | None:
    """Resolve a model- or reader-written name to a roster entry: exact, else one name's tokens inside the other's.

    "Gu Yue Fang Yuan" and "Fang Yuan" are the same person; "Mr. Bennet" must not match "Mrs. Bennet" (so a lone
    shared surname token is refused when the other side has a distinguishing honorific token).
    """
    n = _norm(name)
    if not n:
        return None
    toks = frozenset(n.split())
    for r in roster:
        if _norm(r.name) == n:
            return r
    best: tuple[int, RosterEntry] | None = None
    for r in roster:
        rt = r.tokens
        if not rt:
            continue
        small, big = (toks, rt) if len(toks) <= len(rt) else (rt, toks)
        if small <= big and not (len(small) == 1 and len(big) > 1 and _is_honorific(next(iter(big - small)))):
            score = len(small)
            if best is None or score > best[0]:
                best = (score, r)
    return best[1] if best else None


_HONORIFICS = {"mr", "mrs", "miss", "ms", "sir", "lady", "lord", "master", "elder", "old", "young"}


def _is_honorific(tok: str) -> bool:
    return tok in _HONORIFICS


def _speaker_label(store: Store, entity_id: str) -> str:
    row = store.conn.execute("SELECT canonical_label FROM self_entity WHERE id=?", (entity_id,)).fetchone()
    if row:
        return str(row[0])
    # epithet / title ids carry the label in their tail ("...:epithet:1:clan-head"): better than the opaque id in a prompt
    tail = entity_id.rsplit(":", 1)[-1]
    return tail.replace("-", " ").replace("_", " ")


def build_roster(store: Store, novel_id: str, speaker_ids: set[str]) -> list[RosterEntry]:
    """Characters the director may cast: SELF entities (not items, places or organisations) plus any id a span names as speaker."""
    rows = store.conn.execute(
        "SELECT id, canonical_label FROM self_entity WHERE novel_id=? AND kind='SELF'", (novel_id,)
    ).fetchall()
    out: dict[str, RosterEntry] = {str(r[0]): RosterEntry(str(r[0]), str(r[1])) for r in rows}
    for sid in speaker_ids:
        if sid and sid not in out and ":" in sid:  # a raw label like "Fang Yuan" is resolved by name below, not added
            out[sid] = RosterEntry(sid, _speaker_label(store, sid))
    return list(out.values())


def _look_fallback(store: Store, entity_id: str) -> str:
    """Persona attributes as one line. The real per-epoch `Look` supersedes this (persona.looks.look_at)."""
    keys = ("gender", "age_band", "hair", "hair_color", "skin_tone", "typical_attire", "current_condition", "build")
    rows = store.conn.execute(
        "SELECT key, value FROM attribute WHERE target_id LIKE ? ORDER BY key", (entity_id + ":%",)
    ).fetchall()
    seen: dict[str, str] = {}
    for k, v in rows:
        if k in keys and k not in seen:
            seen[k] = str(v)
    return "; ".join(f"{k.replace('_', ' ')} {v}" for k, v in seen.items())


# --- the two parallel contracts -------------------------------------------------------------------------------------


def _load_present_cast() -> Callable[..., tuple[list[str], list[str]]] | None:
    try:
        from echotales.pipeline.segment.presence import (
            present_cast,  # type: ignore[import-not-found]
        )

        return present_cast
    except Exception:  # not landed yet (ImportError) or its optional deps are missing
        return None


def _load_look_at() -> Callable[..., Any] | None:
    try:
        from echotales.pipeline.persona.looks import look_at  # type: ignore[import-not-found]

        return look_at
    except Exception:
        return None


def presence_for(
    store: Store, novel_id: str, chapter: float, b0: int, b1: int, lines: list[Line], roster: list[RosterEntry]
) -> tuple[list[str], list[str], bool]:
    """`(present ids, referenced-only ids, real_contract)` for a block range.

    Fallback: present = attributed speakers plus every roster member named in the range, referenced = []. That over-claims
    presence on purpose (RI ch1 blocks 31-79 name Fang Yuan as a topic and the reader even attributes two clan-head
    lines to him), and the director's own scene read then moves people to `referenced`; a fallback result is therefore
    only as good as that model read, which is why the contract flag is reported.
    """
    fn = _load_present_cast()
    if fn is not None:
        try:
            present, referenced = fn(store, novel_id, chapter, b0, b1)
            return list(present), list(referenced), True
        except Exception:
            pass
    ids: list[str] = []
    for ln in lines:
        if b0 <= ln.block <= b1 and ln.speaker_id and ln.speaker_id not in ids:
            ids.append(ln.speaker_id)
    return ids, [], False


def look_for(store: Store, novel_id: str, entry: RosterEntry, chapter: float, block: int) -> tuple[str, str | None, bool]:
    """`(description, look_id, real_contract)` of a character at this story position."""
    fn = _load_look_at()
    if fn is not None:
        try:
            lk = fn(store, novel_id, entry.entity_id, chapter=chapter, block=block)
            desc = getattr(lk, "description", "") or ""
            facts = getattr(lk, "facts", None)
            if facts and not desc:
                desc = "; ".join(str(f) for f in facts)
            return desc, getattr(lk, "look_id", None), True
        except Exception:
            pass
    return _look_fallback(store, entry.entity_id), None, False


# --- loading ---------------------------------------------------------------------------------------------------------

_LAYER_BY_SEGMENT = {
    "MAIN": Layer.PRESENT,
    "FLASHBACK_OWN": Layer.PAST,
    "REGRESSION_PRIOR_LOOP": Layer.PAST,
    "DREAM_OTHER": Layer.DREAM,
    "VISION": Layer.DREAM,
    "PROPHECY": Layer.DREAM,
    "ILLUSION": Layer.DREAM,
    "HEARSAY": Layer.IMAGINED,
}


def _scenes_from_graph(store: Store, novel_id: str, chapter: float, block_ids: list[int]) -> list[Scene]:
    lo, hi = block_ids[0], block_ids[-1]
    scenes: list[Scene] = []
    for seg in store.get_segments(novel_id, chapter):
        b0 = int(seg.offset_from) if seg.chapter_from == chapter else lo
        b1 = int(seg.offset_to) if seg.chapter_to == chapter else hi
        b0, b1 = max(b0, lo), min(b1, hi)
        if b1 < b0:
            continue
        layer = _LAYER_BY_SEGMENT.get(str(seg.segment_type), Layer.PRESENT)
        scenes.append(Scene(b0, b1, layer=layer, from_graph=True))
    if not scenes:
        scenes = [Scene(lo, hi)]
    scenes.sort(key=lambda s: s.block_from)
    return scenes


def split_on_separators(scene: Scene, blocks: dict[int, str]) -> list[Scene]:
    """Split a long scene at ellipsis/rule blocks when both halves are scene-sized (see MIN_SCENE_BLOCKS)."""
    ids = [b for b in sorted(blocks) if scene.block_from <= b <= scene.block_to]
    cuts = [b for b in ids if _SEPARATOR.match(blocks[b])]
    out: list[Scene] = []
    start = ids[0]
    for c in cuts:
        left = [b for b in ids if start <= b <= c]
        right = [b for b in ids if b > c]
        if len(left) >= MIN_SCENE_BLOCKS and len(right) >= MIN_SCENE_BLOCKS:
            out.append(_clone(scene, start, c, from_graph=False if out or start != scene.block_from else scene.from_graph))
            start = right[0]
    out.append(_clone(scene, start, ids[-1], from_graph=scene.from_graph if not out else False))
    return out


def _clone(scene: Scene, b0: int, b1: int, *, from_graph: bool) -> Scene:
    return Scene(b0, b1, layer=scene.layer, story_time=scene.story_time, place=scene.place, from_graph=from_graph)


def load_chapter(store: Store, novel_id: str, chapter: float) -> ChapterInput:
    ch = store.get_chapter(novel_id, chapter)
    if ch is None:
        raise ValueError(f"{novel_id} has no chapter {chapter:g}")
    blocks = {b.index: b.text for b in ch.blocks if b.block_type.is_story_content}
    if not blocks:
        raise ValueError(f"{novel_id} chapter {chapter:g} has no story blocks")

    spans = store.get_spans(novel_id, chapter)
    by_block: dict[int, list[Any]] = {}
    for sp in spans:
        by_block.setdefault(sp.block_index, []).append(sp)

    speaker_ids = {sp.speaker_self_id for sp in spans if sp.speaker_self_id}
    roster = build_roster(store, novel_id, {s for s in speaker_ids if s})

    def speaker_of(raw: str | None) -> tuple[str | None, str]:
        if not raw:
            return None, ""
        for r in roster:
            if r.entity_id == raw:
                return r.entity_id, r.name
        hit = match_entry(raw.rsplit(":", 1)[-1], roster)  # the reader sometimes stores a bare label, not an id
        return (hit.entity_id, hit.name) if hit else (raw, raw)

    lines: list[Line] = []
    k = 0
    for b in sorted(blocks):
        sps = sorted(by_block.get(b, []), key=lambda s: s.start)
        if not sps:
            lines.append(Line(f"s{k}", b, "narration", blocks[b].strip(), span_id=f"{novel_id}:{chapter:g}:b{b}"))
            k += 1
            continue
        for sp in sps:
            stype = str(sp.span_type)
            kind = "speech" if stype in _SPEECH_KINDS else "thought" if stype in _THOUGHT_KINDS else "narration"
            sid, sname = speaker_of(sp.speaker_self_id) if kind != "narration" else (None, "")
            lines.append(Line(f"s{k}", b, kind, sp.text.strip(), sid, sname, span_id=sp.id))
            k += 1

    scenes: list[Scene] = []
    for sc in _scenes_from_graph(store, novel_id, chapter, sorted(blocks)):
        scenes.extend(split_on_separators(sc, blocks))
    for i, sc in enumerate(scenes):
        sc.cut_signal = "" if i == 0 else sc.cut_signal

    inp = ChapterInput(novel_id, chapter, blocks, lines, roster, scenes)
    refresh_presence(store, inp)
    return inp


def refresh_presence(store: Store, inp: ChapterInput) -> None:
    """(Re)compute each scene's present/referenced ids and every roster member's look, through the contracts."""
    contract = False
    for sc in inp.scenes:
        present, referenced, ok = presence_for(
            store, inp.novel_id, inp.chapter, sc.block_from, sc.block_to, inp.lines, inp.roster
        )
        sc.present_ids = _resolve_ids(present, inp.roster)
        sc.referenced_ids = _resolve_ids(referenced, inp.roster)
        contract = contract or ok
    inp.presence_contract = contract
    any_look = False
    first_block = inp.block_ids[0]
    for r in inp.roster:
        desc, look_id, ok = look_for(store, inp.novel_id, r, inp.chapter, first_block)
        r.look, r.look_id = desc, look_id
        any_look = any_look or ok
    inp.look_contract = any_look


def _resolve_ids(ids: list[str], roster: list[RosterEntry]) -> list[str]:
    out: list[str] = []
    for i in ids:
        hit = next((r for r in roster if r.entity_id == i), None) or match_entry(i.rsplit(":", 1)[-1], roster)
        eid = hit.entity_id if hit else i
        if eid not in out:
            out.append(eid)
    return out


def windows(inp: ChapterInput, scene: Scene) -> list[tuple[int, int]]:
    """Block ranges (inclusive) the model plans in one call, never spanning a scene, preferring to end on a separator."""
    ids = [b for b in inp.block_ids if scene.block_from <= b <= scene.block_to]
    out: list[tuple[int, int]] = []
    cur: list[int] = []
    words = 0
    for b in ids:
        w = len(inp.blocks[b].split())
        if cur and (len(cur) >= MAX_WINDOW_BLOCKS or words + w > MAX_WINDOW_WORDS):
            out.append((cur[0], cur[-1]))
            cur, words = [], 0
        cur.append(b)
        words += w
    if cur:
        # a one- or two-block tail is merged back: a window that small gives the model nothing to storyboard
        if out and len(cur) <= 2:
            out[-1] = (out[-1][0], cur[-1])
        else:
            out.append((cur[0], cur[-1]))
    return out
