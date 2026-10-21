"""Scoring the extraction against a reader-gold chapter: speakers, persona links, kind, age and appearance.

`eval/gold.py` answers "which individual does this *mention* denote". The Phase A gates are about different
things -- who speaks each quoted line, whether `Justice` is linked to Audrey, whether a place was typed as a
place, whether "had just turned seventeen" became an age -- and nothing measured them. LotM ch7 scored 16/39
(41%) on speakers only because a person counted it by hand once (audit 2026-10-22).

Reference files live in `data/gold/reader/` and are **model-drafted silver** (`provenance: "model"`,
`confirmed: false`): they are one reading of the text by a model that never saw the pipeline's output, which is
what makes them usable as a measurement, and they stay silver until a person confirms them record by record
(`eval/gold.py` contract). Every report from here says so; a number from this module is not a "gold" result.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import SpanType, TargetKind
from echotales.core.store import Store

# A quote runs to its closing mark or, when the paragraph ends first, to the end of the block: multi-paragraph
# speech opens a quote in every paragraph and closes only in the last (LotM ch7 blocks 10, 26, 27).
# ORV is set in straight quotes, LotM and RI in curly ones (ORV ch2 had zero curly matches).
_QUOTE = re.compile(r"“[^”]*(?:”|$)|\"[^\"]*(?:\"|$)")

#: gold `kind` -> the store kinds that count as correct. Kinds with no counterpart are not scored.
_KIND_MAP: dict[str, frozenset[TargetKind]] = {
    "person": frozenset({TargetKind.SELF, TargetKind.PERSONA}),
    "person_mentioned": frozenset({TargetKind.SELF, TargetKind.PERSONA}),
    "location": frozenset({TargetKind.LOCATION}),
    "organization": frozenset({TargetKind.ORGANIZATION}),
}


#: Gold speaker for a line whose speaker the text never names.
ANON = "_anon"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower().replace("’", "'")).strip()


@dataclass(slots=True)
class GoldChapter:
    novel_id: str
    chapter: int
    provenance: str
    confirmed: bool
    characters: dict[str, dict] = field(default_factory=dict)  # type: ignore[type-arg]
    non_characters: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    personas: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    appearance: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    age_facts: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    lines: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    #: False when only the quotes whose speaker the drafter could establish are listed. A pipeline dialogue span
    #: over an unlisted quote is then not evidence of false dialogue, so that count is not reported for the chapter.
    lines_complete: bool = True


def _expand_line(line: dict | str) -> dict:  # type: ignore[type-arg]
    """`"12.1:audrey"` or `"75.0:klein:thought"` -> the dict form. Labelling 15 chapters by hand is the cost of
    this reference set, so the compact form keeps a chapter's 40-60 lines to one short string each."""
    if isinstance(line, dict):
        return line
    ref, speaker, *kind = line.split(":")
    block, q = ref.split(".")
    return {"block": int(block), "q": int(q), "speaker": speaker, "type": kind[0] if kind else "speech"}


def load_reader_gold(path: str | Path) -> GoldChapter:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return GoldChapter(
        novel_id=raw["novel_id"],
        chapter=int(raw["chapter"]),
        provenance=raw["provenance"],
        confirmed=bool(raw["confirmed"]),
        characters={c["id"]: c for c in raw["characters"]},
        non_characters=raw.get("non_characters", []),
        personas=raw.get("personas", []),
        appearance=raw.get("appearance", []),
        age_facts=raw.get("age_facts", []),
        lines=[_expand_line(x) for x in raw["lines"]],
        lines_complete=bool(raw.get("lines_complete", True)),
    )


@dataclass(slots=True)
class Score:
    correct: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass(slots=True)
class SpeakerScore(Score):
    #: Pipeline dialogue spans that cover no gold line: scare quotes and narration voiced as speech.
    false_dialogue: int = 0


def _names_of(store: Store, self_id: str) -> set[str]:
    entity = store.get_self(self_id)
    # The speaker column often holds the surface label itself ("Audrey", "Zhou Mingrui") rather than an entity id,
    # so an id with no entity row is read as a name. Anonymous slot ids ("...:anon:7:1") normalise to a string no
    # gold name equals, which is correct: an unnamed slot is never the right speaker.
    names = {_norm(entity.canonical_label)} if entity else {_norm(self_id)}
    for target in (TargetKind.SELF, TargetKind.PERSONA):
        names |= {_norm(a.alias) for a in store.get_aliases_for(target, self_id)}
    return names


def _gold_names(character: dict) -> set[str]:  # type: ignore[type-arg]
    return {_norm(character["name"])} | {_norm(a) for a in character.get("aliases", [])}


def _self_is(store: Store, self_id: str | None, character: dict) -> bool:  # type: ignore[type-arg]
    """Whether a pipeline entity is this gold character. Matched by names, never by id: gold must stay
    independent of the pipeline's own inventory (`eval/gold.py`)."""
    if not self_id:
        return False
    return bool(_names_of(store, self_id) & _gold_names(character))


def _find_self(store: Store, novel_id: str, character: dict) -> str | None:  # type: ignore[type-arg]
    rows = store.conn.execute("SELECT id FROM self_entity WHERE novel_id=?", (novel_id,)).fetchall()
    for row in rows:
        if _self_is(store, row["id"], character):
            return str(row["id"])
    return None


def score_speakers(gold: GoldChapter, store: Store) -> SpeakerScore:
    chapter = store.get_chapter(gold.novel_id, gold.chapter)
    if chapter is None:
        raise ValueError(f"{gold.novel_id} chapter {gold.chapter} is not in the database")
    blocks = {b.index: b.text for b in chapter.blocks}
    spans = [s for s in store.get_spans(gold.novel_id, gold.chapter) if s.span_type is SpanType.DIALOGUE]
    out = SpeakerScore()
    covered: set[str] = set()
    for line in gold.lines:
        out.total += 1
        starts = [m.start() for m in _QUOTE.finditer(blocks.get(line["block"], ""))]
        label = f"block {line['block']} quote {line['q']}"
        if line["q"] >= len(starts):
            out.misses.append(f"{label}: quote not found in the text")
            continue
        start = starts[line["q"]]
        hit = next((s for s in spans if s.block_index == line["block"] and s.start <= start < s.end), None)
        if hit is None:
            out.misses.append(f"{label}: no dialogue span (the line was not detected as speech)")
            continue
        covered.add(hit.id)
        if line["speaker"] == ANON:
            # An unnamed speaker ("a voice from the crowd") is right when left unnamed. Pinning it on a named
            # character is the failure: it would be cast that character's voice.
            correct = not hit.speaker_self_id or ":anon:" in hit.speaker_self_id
        else:
            correct = _self_is(store, hit.speaker_self_id, gold.characters[line["speaker"]])
        if correct:
            out.correct += 1
        else:
            out.misses.append(f"{label}: expected {line['speaker']}, got {hit.speaker_self_id}")
    if gold.lines_complete:
        out.false_dialogue = sum(1 for s in spans if s.id not in covered)
    return out


def score_persona_links(gold: GoldChapter, store: Store) -> Score:
    """Every gold persona name must be an alias bound to the right character (Fool -> Klein, Justice -> Audrey)."""
    out = Score()
    for p in gold.personas:
        out.total += 1
        self_id = _find_self(store, gold.novel_id, gold.characters[p["character"]])
        if self_id is not None and _norm(p["name"]) in _names_of(store, self_id):
            out.correct += 1
        else:
            out.misses.append(f"{p['name']!r} is not linked to {p['character']}")
    return out


def score_kinds(gold: GoldChapter, store: Store) -> Score:
    """Typed correctly, over the entities that exist. A place the pipeline never minted is not a kind error."""
    out = Score()
    rows = store.conn.execute(
        "SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (gold.novel_id,)
    ).fetchall()
    by_name: dict[str, str] = {}
    for row in rows:
        by_name.setdefault(_norm(row["canonical_label"]), row["id"])
    named = [(c["name"], c["kind"]) for c in gold.characters.values()]
    named += [(n["name"], n["kind"]) for n in gold.non_characters]
    for name, kind in named:
        allowed = _KIND_MAP.get(kind)
        self_id = by_name.get(_norm(name))
        entity = store.get_self(self_id) if self_id else None
        if allowed is None or entity is None:
            continue
        out.total += 1
        if entity.kind in allowed:
            out.correct += 1
        else:
            out.misses.append(f"{name!r} is typed {entity.kind.value}, expected {kind}")
    return out


def _attribute_values(store: Store, self_id: str | None, keys: set[str]) -> list[str]:
    if not self_id:
        return []
    return [
        a.value
        for target in (TargetKind.SELF, TargetKind.PERSONA)
        for a in store.get_attributes(target, self_id)
        if a.key in keys
    ]


def score_ages(gold: GoldChapter, store: Store) -> Score:
    """An explicit age cue ("had just turned seventeen") must reach the graph as a number. An "adult" band for a
    seventeen-year-old is the audit's Audrey defect, so a band alone does not pass."""
    out = Score()
    for fact in gold.age_facts:
        out.total += 1
        self_id = _find_self(store, gold.novel_id, gold.characters[fact["character"]])
        values = _attribute_values(store, self_id, {"age", "age_band"})
        if any(str(fact["value"]) == v.strip() for v in values):
            out.correct += 1
        else:
            out.misses.append(f"{fact['character']}: age {fact['value']} not recorded (have {sorted(set(values))})")
    return out


def score_appearance(gold: GoldChapter, store: Store) -> Score:
    """Recall of appearance facts: the value must appear under that attribute on the character or a persona."""
    out = Score()
    for fact in gold.appearance:
        out.total += 1
        self_id = _find_self(store, gold.novel_id, gold.characters[fact["character"]])
        values = _attribute_values(store, self_id, {fact["attribute"]})
        if any(_norm(fact["value"]) in _norm(v) for v in values):
            out.correct += 1
        else:
            out.misses.append(f"{fact['character']}.{fact['attribute']}={fact['value']!r} missing")
    return out
