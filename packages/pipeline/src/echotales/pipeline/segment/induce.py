"""Learn how THIS novel marks scene changes, from its first volume.

Why shapes and not words (owner rule, 2026-11-27): every author marks a scene
change differently, and some do not mark it at all. LotM puts a one-line place
header after a `...` block, ORV uses `* * *`, RI uses `……` once and a bare cut
the next time. A list of marker words or regexes is a list about one novel. So
this module describes each block by its *shape* (length bucket, standalone
line, case pattern, symbol-only, opening character class, single-named-entity
and its NER type, structural block type) and asks one question of the volume:
which shapes recur AND sit on boundaries whose story-level change score
(`discontinuity.py`) is far above the base rate? Those, and only those, become
this novel's markers.

Thresholds (`MIN_SUPPORT`, `MIN_LIFT`, `MIN_HIT_RATE`, `HIGH_QUANTILE`) and the
measurement that chose them are in docs/results/SCENE_INDUCTION.md. The
confirmation pass asks a small local model a yes/no question about a few
examples per candidate; it can only veto, never add, so a bad model answer
costs recall on one convention, not a spurious cut on every chapter.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from echotales.core.models import Chapter, Mention
from echotales.pipeline.llm import LLMRequest
from echotales.pipeline.segment.cuts import SceneCut
from echotales.pipeline.segment.discontinuity import (
    Boundary,
    TopicModel,
    canonical_position,
    is_substantive,
    load_nlp,
    score_chapter,
)
from pydantic import BaseModel, Field

#: A shape must sit before this many boundaries to be called a convention.
#: Three because one occurrence is an anecdote and two can be a coincidence of
#: one chapter's pacing; the RI/LotM/ORV marker shapes all recur 4+ times in the
#: first ten chapters.
MIN_SUPPORT = 3
#: Hit rate over base rate. 2.5x with a 10% base rate is a 25% hit rate. LotM's
#: `...` block sits on a high boundary 4 times in 14 (lift 2.85) because it is a
#: pause that only sometimes precedes a cut; 3.0 rejected it, and rejecting it
#: lost the one convention that LotM's place headers hang from.
MIN_LIFT = 2.5
#: A convention at or above this hit rate cuts on its own ("strong"). Below it
#: the shape is only a candidate that the implicit pass must confirm ("weak"),
#: because a shape that precedes a cut 3 times in 10 would otherwise add 7 false
#: cuts for every 3 true ones.
STRONG_HIT_RATE = 0.5
#: "High discontinuity" is the top decile of this volume's own boundary scores,
#: so the base rate is ~10% by construction and no absolute score is assumed.
HIGH_QUANTILE = 0.90

SCHEMA_VERSION = 1


@dataclass(slots=True)
class Convention:
    id: str
    view: str
    key: str
    support: int
    hits: int
    hit_rate: float
    lift: float
    mean_score: float
    strength: str = "weak"  # "strong" cuts alone; "weak" only nominates a candidate
    examples: list[dict[str, Any]] = field(default_factory=list)
    llm: dict[str, Any] | None = None
    accepted: bool = False
    reason: str = ""


@dataclass(slots=True)
class ConventionSet:
    novel_id: str
    learned_chapters: list[float]
    base_rate: float
    high_threshold: float
    params: dict[str, float]
    #: p75 of the volume's boundary scores: the floor for asking the model about an unmarked boundary.
    candidate_threshold: float = 0.0
    conventions: list[Convention] = field(default_factory=list)

    def accepted(self) -> list[Convention]:
        return [c for c in self.conventions if c.accepted]

    def shape_index(self) -> set[tuple[str, str]]:
        return {(c.view, c.key) for c in self.accepted()}


# --------------------------------------------------------------------------- shapes


def _alpha_words(text: str) -> list[str]:
    return [w for w in text.split() if any(ch.isalpha() for ch in w)]


def _len_bucket(n: int) -> str:
    if n == 0:
        return "w0"
    if n == 1:
        return "w1"
    if n <= 3:
        return "w2-3"
    if n <= 8:
        return "w4-8"
    if n <= 30:
        return "w9-30"
    return "w31+"


def _case_pattern(text: str) -> str:
    words = _alpha_words(text)
    if not words:
        return "none"
    letters = "".join(ch for ch in text if ch.isalpha())
    if letters.isupper() and len(letters) > 1:
        return "upper"
    if all(w.lstrip("\"'“‘([")[:1].isupper() for w in words):
        return "title"
    if words[0].lstrip("\"'“‘([")[:1].isupper():
        return "sentence"
    return "lower"


def _is_symbol_only(text: str) -> bool:
    t = text.strip()
    return bool(t) and not any(ch.isalnum() for ch in t)


def _opener_class(text: str) -> str:
    t = text.lstrip()
    return unicodedata.category(t[0]) if t else "none"


_ENT_COARSE = {
    "GPE": "place",
    "LOC": "place",
    "FAC": "place",
    "PERSON": "person",
    "ORG": "org",
    "NORP": "org",
    "DATE": "time",
    "TIME": "time",
}


def _single_entity_type(text: str, nlp: Any | None) -> str:
    """NER type when one entity spans (nearly) the whole block, else 'none'."""
    if nlp is None:
        return "none"
    core = text.strip().strip(".,;:!?…\"'“”")
    if not core:
        return "none"
    doc = nlp(core)
    for ent in doc.ents:
        if len(ent.text) >= 0.8 * len(core):
            return _ENT_COARSE.get(ent.label_, "other")
    return "none"


def block_shapes(chapter: Chapter, block_index: int, nlp: Any | None = None) -> dict[str, str]:
    """The shape keys of one block, one per view. Contains no words of the text."""
    pos = {b.index: i for i, b in enumerate(chapter.blocks)}[block_index]
    block = chapter.blocks[pos]
    text = block.text
    aw = len(_alpha_words(text))
    lenb = _len_bucket(aw)
    shapes: dict[str, str] = {}
    if block.block_type.value not in ("PROSE", "DIALOGUE"):
        shapes["struct"] = block.block_type.value
    if _is_symbol_only(text):
        shapes["symbol"] = re.sub(r"\s+", " ", text.strip())
        return shapes
    if aw <= 6:
        prev_n = len(_alpha_words(chapter.blocks[pos - 1].text)) if pos > 0 else 0
        next_n = len(_alpha_words(chapter.blocks[pos + 1].text)) if pos + 1 < len(chapter.blocks) else 0
        standalone = "alone" if prev_n > aw and next_n > aw else "inline"
        ent = _single_entity_type(text, nlp) if aw <= 6 else "none"
        shapes["short"] = f"{lenb}|{_case_pattern(text)}|{ent}|{standalone}"
    opener = _opener_class(text)
    if opener[0] not in "LN" and opener not in ("Pi",):  # not a letter, digit or opening quote
        shapes["opener"] = f"{opener}|{lenb}"
    return shapes


# ------------------------------------------------------------------------- induction


class ExampleVerdict(BaseModel):
    marks_scene_change: bool = Field(description="true if the block in the middle starts or separates scenes")
    reason: str = ""


_CONFIRM_SYSTEM = (
    "You study how one translated novel marks scene changes. You are shown the end of the text before a block, "
    "the block itself, and the start of the text after it. Answer only whether the text after the block is a new "
    "scene (different place, different time, or different people on stage) compared with the text before it."
)


def _clip(text: str, n: int, tail: bool = False) -> str:
    t = " ".join(text.split())
    if len(t) <= n:
        return t
    return "..." + t[-n:] if tail else t[:n] + "..."


def _context(chapter: Chapter, position: int, marker_blocks: list[int]) -> tuple[str, str, str]:
    prev = [b for b in chapter.blocks if b.index < (marker_blocks[0] if marker_blocks else position)]
    nxt = [b for b in chapter.blocks if b.index >= position]
    before = " ".join(b.text for b in prev[-2:])
    marker = " / ".join(b.text for b in chapter.blocks if b.index in marker_blocks) or "(none)"
    after = " ".join(b.text for b in nxt[:2])
    return _clip(before, 420, tail=True), _clip(marker, 80), _clip(after, 420)


def _anchor(text: str, words: int = 5) -> str:
    return " ".join(text.split()[:words])


def induce_conventions(
    novel_id: str,
    chapters: list[Chapter],
    *,
    mentions_by_chapter: dict[float, list[Mention]] | None = None,
    llm: Any | None = None,
    nlp: Any | None = None,
    topic: TopicModel | None = None,
    min_support: int = MIN_SUPPORT,
    min_lift: float = MIN_LIFT,
    high_quantile: float = HIGH_QUANTILE,
    confirm_examples: int = 3,
) -> ConventionSet:
    """Induce this novel's scene-change conventions from `chapters`."""
    nlp = nlp if nlp is not None else load_nlp()
    mentions_by_chapter = mentions_by_chapter or {}
    scored: dict[float, list[Boundary]] = {}
    for ch in chapters:
        scored[ch.number] = score_chapter(ch, mentions_by_chapter.get(ch.number), nlp=nlp, topic=topic)
    all_scores = sorted(b.score for bs in scored.values() for b in bs)
    if not all_scores:
        return ConventionSet(novel_id, [c.number for c in chapters], 0.0, 1.0, {}, 1.0, [])
    thr = all_scores[min(len(all_scores) - 1, int(high_quantile * len(all_scores)))]
    base_rate = sum(1 for s in all_scores if s >= thr) / len(all_scores)

    # (view, key) -> {(chapter, position): (score, block, marker_blocks)}
    occ: dict[tuple[str, str], dict[tuple[float, int], tuple[float, int, list[int]]]] = defaultdict(dict)
    by_chapter = {c.number: c for c in chapters}
    for ch in chapters:
        by_pos = {b.position: b for b in scored[ch.number]}
        for block in ch.blocks:
            if block.index == 0 or not block.text.strip():
                continue
            pos = canonical_position(ch, block.index)
            boundary = by_pos.get(pos)
            if boundary is None:
                continue
            for view, key in block_shapes(ch, block.index, nlp).items():
                occ[(view, key)].setdefault((ch.number, pos), (boundary.score, block.index, boundary.marker_blocks))

    conventions: list[Convention] = []
    for (view, key), hits_map in sorted(occ.items()):
        n = len(hits_map)
        if n < min_support:
            continue
        hits = sum(1 for s, _, _ in hits_map.values() if s >= thr)
        hit_rate = hits / n
        lift = hit_rate / base_rate if base_rate else 0.0
        cid = f"{view}:{key}"
        conv = Convention(
            id=cid,
            view=view,
            key=key,
            support=n,
            hits=hits,
            hit_rate=round(hit_rate, 3),
            lift=round(lift, 2),
            mean_score=round(sum(s for s, _, _ in hits_map.values()) / n, 3),
        )
        for (chn, _pos), (s, bidx, _markers) in sorted(hits_map.items(), key=lambda kv: -kv[1][0])[:5]:
            blk = next(b for b in by_chapter[chn].blocks if b.index == bidx)
            conv.examples.append({"chapter": chn, "block": bidx, "score": round(s, 3), "anchor": _anchor(blk.text)})
        if lift >= min_lift and hits >= 2:
            conv.accepted = True
            conv.strength = "strong" if hit_rate >= STRONG_HIT_RATE else "weak"
            conv.reason = "stats"
        else:
            conv.reason = f"lift {conv.lift} / hit_rate {conv.hit_rate} below thresholds"
        conventions.append(conv)

    if llm is not None:
        for conv in conventions:
            if conv.accepted:
                _confirm(conv, occ[(conv.view, conv.key)], by_chapter, llm, confirm_examples)

    conventions.sort(key=lambda c: (-int(c.accepted), -c.lift, -c.support))
    return ConventionSet(
        novel_id=novel_id,
        learned_chapters=[c.number for c in chapters],
        base_rate=round(base_rate, 3),
        high_threshold=round(thr, 4),
        candidate_threshold=round(all_scores[int(0.75 * len(all_scores))], 4),
        params={
            "min_support": min_support,
            "min_lift": min_lift,
            "strong_hit_rate": STRONG_HIT_RATE,
            "high_quantile": high_quantile,
        },
        conventions=conventions,
    )


def _confirm(
    conv: Convention,
    hits_map: dict[tuple[float, int], tuple[float, int, list[int]]],
    by_chapter: dict[float, Chapter],
    llm: Any,
    n_examples: int,
) -> None:
    """Veto a statistically accepted convention the model cannot see a scene change in."""
    ranked = sorted(hits_map.items(), key=lambda kv: -kv[1][0])[:n_examples]
    yes = 0
    asked = 0
    reasons: list[str] = []
    for (chn, pos), (_s, _b, markers) in ranked:
        before, marker, after = _context(by_chapter[chn], pos, markers)
        prompt = (
            f"TEXT BEFORE: {before}\n\nBLOCK IN THE MIDDLE: {marker}\n\nTEXT AFTER: {after}\n\n"
            "Is the text after the block a new scene compared with the text before?"
        )
        try:
            res = llm.complete(
                LLMRequest(stage="scene_convention_confirm", prompt=prompt, system=_CONFIRM_SYSTEM, max_tokens=200),
                ExampleVerdict,
            )
        except Exception as exc:  # an unreachable model must not veto; the stats already passed
            reasons.append(f"llm error: {type(exc).__name__}")
            continue
        asked += 1
        yes += int(res.value.marks_scene_change)
        reasons.append(res.value.reason[:80])
    conv.llm = {"asked": asked, "yes": yes, "reasons": reasons}
    if asked and yes * 2 < asked:
        conv.accepted = False
        conv.reason = f"vetoed by model ({yes}/{asked} examples are scene changes)"
    elif asked:
        conv.reason = f"stats + model ({yes}/{asked})"


# ------------------------------------------------------------------------ application


def find_induced_cuts(
    chapter: Chapter,
    conventions: ConventionSet,
    *,
    nlp: Any | None = None,
) -> list[SceneCut]:
    """Cuts where a block has an accepted convention's shape.

    The cut is placed at the canonical position (first substantive block at or
    after the marker), the same normalisation the gold set uses, so a header,
    a `...` block and a symbol line all cut before the first real sentence.
    """
    strengths = {(c.view, c.key): c for c in conventions.accepted()}
    wanted = set(strengths)
    if not wanted:
        return []
    nlp = nlp if nlp is not None else load_nlp()
    story_first = next((b.index for b in chapter.blocks if is_substantive(b.text)), 0)
    cuts: dict[int, SceneCut] = {}
    for block in chapter.blocks:
        if block.index <= story_first:
            continue
        pos = canonical_position(chapter, block.index)
        if pos <= story_first:
            continue
        for view, key in block_shapes(chapter, block.index, nlp).items():
            if (view, key) in wanted and pos not in cuts:
                conv = strengths[(view, key)]
                cuts[pos] = SceneCut(
                    chapter=chapter.number,
                    block=pos,
                    source=f"induced-{conv.strength}:{view}:{key}",
                    confidence=conv.hit_rate,
                    evidence=[f"block {block.index} has the induced shape {view}={key}"],
                )
    return [cuts[k] for k in sorted(cuts)]


# ------------------------------------------------------------------------ persistence


def conventions_path(novel_id: str, out_dir: Path | str = "data/lexicons") -> Path:
    """Next to the novel's lexicon, so a reviewer finds both in one place."""
    return Path(out_dir) / f"{novel_id}.scene_conventions.json"


def save_conventions(cset: ConventionSet, path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA_VERSION, **asdict(cset)}
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def load_conventions(path: Path | str) -> ConventionSet:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw.pop("schema", None)
    convs = [Convention(**c) for c in raw.pop("conventions", [])]
    return ConventionSet(conventions=convs, **raw)
