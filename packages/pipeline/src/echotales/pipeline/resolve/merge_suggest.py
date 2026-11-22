"""Merge suggestions: entity pairs that are probably one person, offered to a reviewer and never applied.

Why this exists (P&P e2e 2026-11-22, defect 11): after ch1-3 the review queue was empty although "Lizzy" and
"Elizabeth" were two entities, and so were "Miss Bennet" and "Jane". Both are splits the resolver cannot close by
arithmetic (a nickname and a title-plus-surname share no tokens with the name), so they never reached the deferred
gate and no item recorded them. A reviewer had to find them by reading the cast list, and a missed one meant two
voices for one character (defect 12).

Two cues, both cheap and both deliberately narrow:

- **diminutive**: two given names where the shorter is a clipped form of the longer (Lizzy / Elizabeth, Beth /
  Elizabeth), with compatible surnames and genders, and the two never named in the same paragraph. A paragraph that
  names both is the author telling two people apart ("Elizabeth smiled at Lizzy" would be two people).
- **title + surname**: "Miss Bennet" with no given name, where other entities carry the surname ("Mr. Bennet") and
  some untitled family-member candidates share chapters with them (a name that only ever appears away from the
  family is not a candidate: "Bingley" shared a chapter with "Miss Bennet" and no chapter with the Bennets). Several candidates are listed, ranked by shared
  chapters; the reviewer picks, or dismisses.

Precision over recall (non-negotiable 9): these are suggestions only. Nothing here writes a correction, rebinds a
mention or touches an entity. A reviewer-resolved item stays resolved while its candidate set is unchanged, and a
pair that was merged since is closed with an `auto:` resolution, the same rules as `resolve/review.py`.
"""

from __future__ import annotations

import hashlib
import re
import time

from echotales.core.models import ReviewItem
from echotales.core.store import Store

KIND = "merge_suggestion"
AUTO_MERGED = "auto:merged_since"
AUTO_GONE = "auto:no_longer_suggested"
MAX_CANDIDATES = 5

_TITLES = {
    "mr": "male", "mister": "male", "sir": "male",
    "mrs": "female", "miss": "female", "ms": "female", "madam": "female", "madame": "female", "lady": "female",
    "dame": "female", "dr": None, "lord": None, "master": None, "professor": None, "captain": None, "colonel": None,
}
_LETTERS = re.compile(r"[^a-z]")


def _parse(label: str) -> tuple[str | None, list[str], str | None]:
    """(title, given names, surname). "Miss Bennet" -> ("miss", [], "Bennet"); "Lizzy" -> (None, ["Lizzy"], None)."""
    tokens = [t.strip(".,") for t in label.split() if t.strip(".,")]
    title = None
    if tokens and tokens[0].casefold() in _TITLES:
        title = tokens.pop(0).casefold()
        if not tokens:
            return title, [], None
        return (title, [], tokens[-1]) if len(tokens) == 1 else (title, tokens[:-1], tokens[-1])
    if len(tokens) == 1:
        return None, tokens, None
    return None, tokens[:-1], tokens[-1]


def _core(name: str) -> str:
    """A name with its diminutive ending and doubled letters removed: Lizzy -> liz, Betsy -> bets."""
    s = _LETTERS.sub("", name.casefold())
    s = re.sub(r"(ie|ey|y|i)$", "", s) if len(s) > 4 else s
    return re.sub(r"(.)\1", r"\1", s)


def clipped_form(short: str, long: str) -> bool:
    """True when `short` reads as a clipped form of `long`: its core opens `long` (Eliz-) or sits just after its first
    letter (E-liz-abeth) or closes it (Eliza-beth). At least three letters, so "Al" or "Em" match nothing."""
    a, b = _core(short), _LETTERS.sub("", long.casefold())
    b_core = re.sub(r"(.)\1", r"\1", b)
    if len(a) < 3 or len(a) >= len(b_core) or a == b_core:
        return False
    return b_core.startswith(a) or b_core[1:].startswith(a) or b_core.endswith(a)


def _gender_of(store: Store, entity_id: str, title: str | None) -> str | None:
    """Recorded gender if any (a reviewer's or a pass's), else what a title says, else None."""
    from echotales.pipeline.persona.split import bodies_of, standing_values

    for persona_id, _ in bodies_of(store, entity_id) or []:
        value = standing_values(store, persona_id).get("gender")
        if value in ("male", "female"):
            return value
    return _TITLES.get(title) if title else None


def _evidence_hash(item_kind: str, from_id: str, targets: list[str]) -> str:
    return hashlib.sha1(f"{item_kind}|{from_id}|{','.join(sorted(targets))}".encode()).hexdigest()[:12]


def _build(novel_id: str, from_id: str, from_label: str, cue: str, picks: list[tuple[str, str, str]]) -> ReviewItem:
    group = {
        "role": "group", "from_id": from_id, "from_label": from_label, "cue": cue,
        "evidence_hash": _evidence_hash(cue, from_id, [p[0] for p in picks]),
    }
    candidates = [{"role": "candidate", "target_id": tid, "label": label, "reason": why} for tid, label, why in picks]
    names = ", ".join(repr(p[1]) for p in picks)
    return ReviewItem(
        id=f"{KIND}:{novel_id}:{cue}:{from_id}" + (f":{picks[0][0]}" if cue == "diminutive" else ""),
        novel_id=novel_id,
        chapter=0.0,
        kind=KIND,
        message=f"{from_label!r} may be the same person as {names} (suggestion only; nothing was merged)",
        candidates=[group, *candidates],
    )


def suggestions(store: Store, novel_id: str) -> list[ReviewItem]:
    merged = store.merged_into(novel_id)
    people = [e for e in store.all_selves(novel_id) if e.kind.is_person and e.id not in merged]
    parsed = {e.id: _parse(e.canonical_label) for e in people}
    label = {e.id: e.canonical_label for e in people}

    chapters: dict[str, set[float]] = {}
    blocks: dict[str, set[tuple[float, int]]] = {}
    for row in store.conn.execute(
        "SELECT DISTINCT chapter, block_index, target_id FROM mention WHERE novel_id=? AND target_id IS NOT NULL",
        (novel_id,),
    ):
        chapters.setdefault(row["target_id"], set()).add(float(row["chapter"]))
        blocks.setdefault(row["target_id"], set()).add((float(row["chapter"]), int(row["block_index"])))

    out: list[ReviewItem] = []
    ids = sorted(parsed)

    # diminutive: Lizzy / Elizabeth
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            (ta, ga, sa), (tb, gb, sb) = parsed[a], parsed[b]
            if not ga or not gb or len(ga) != 1 or len(gb) != 1 or ga[0].casefold() == gb[0].casefold():
                continue
            if sa and sb and sa.casefold() != sb.casefold():
                continue
            short, long_ = (a, b) if len(ga[0]) < len(gb[0]) else (b, a)
            if not clipped_form(parsed[short][1][0], parsed[long_][1][0]):
                continue
            g1, g2 = _gender_of(store, a, ta), _gender_of(store, b, tb)
            if g1 and g2 and g1 != g2:
                continue
            if blocks.get(a, set()) & blocks.get(b, set()):
                continue
            out.append(_build(
                novel_id, short, label[short], "diminutive",
                [(long_, label[long_], f"{label[short]!r} reads as a short form of {label[long_]!r}")],
            ))

    # title + surname with no given name: "Miss Bennet"
    for x in ids:
        title, given, surname = parsed[x]
        if title is None or given or not surname or _TITLES.get(title) is None:
            continue
        family = [y for y in ids if y != x and parsed[y][2] and parsed[y][2].casefold() == surname.casefold()]
        if not family:
            continue
        family_chapters = set().union(*(chapters.get(y, set()) for y in family))
        scored: list[tuple[int, str]] = []
        for y in ids:
            ty, gy, sy = parsed[y]
            if y == x or ty is not None or not gy or (sy and sy.casefold() != surname.casefold()):
                continue
            side = _gender_of(store, y, None)
            if side and side != _TITLES[title]:
                continue
            shared = chapters.get(y, set()) & family_chapters
            if shared:
                scored.append((len(shared), y))
        scored.sort(key=lambda p: (-p[0], p[1]))
        if scored:
            out.append(_build(
                novel_id, x, label[x], "title_surname",
                [
                    (y, label[y], f"shares {n} chapter(s) with the {surname} family and has no surname of its own")
                    for n, y in scored[:MAX_CANDIDATES]
                ],
            ))
    return out


def sync(store: Store, novel_id: str) -> int:
    """Write the current suggestions into the review queue; returns how many open items there are afterwards."""
    live: set[str] = set()
    for item in suggestions(store, novel_id):
        live.add(item.id)
        existing = store.get_review_item(item.id)
        if existing is None:
            item.created_at = time.time()
        else:
            item.created_at = existing.created_at
            same = (existing.candidates or [{}])[0].get("evidence_hash") == item.candidates[0]["evidence_hash"]
            machine = (existing.resolution or "").startswith("auto:")
            if existing.resolved and same and not machine:
                continue
        store.add_review_item(item)
    merged = store.merged_into(novel_id)
    for old in store.list_review_items(novel_id, resolved=False):
        if old.kind != KIND or old.id in live:
            continue
        group = old.candidates[0] if old.candidates else {}
        gone = group.get("from_id") in merged
        store.resolve_review_item(old.id, AUTO_MERGED if gone else AUTO_GONE)
    return sum(1 for i in store.list_review_items(novel_id, resolved=False) if i.kind == KIND)
