"""Time-indexed character dossiers: what each person looks like, and is, at each point in story time.

Map: one model call per window of a chapter, shown only the entities the stored mentions place in that window.
Check: a fact survives only if its quote is verbatim in its block and refers to this entity (a stored mention in the
block, else a yes/no question). Reduce: accepted facts become bitemporal `attribute` rows; a changed value closes the
earlier interval (an interval end, never a retraction) so `state_of` answers "what did X look like at chapter N".

Why a second extractor next to `reader/facts_pass.py`: that pass writes 21 appearance facts for 90 RI people because it
only reads windows where a known name sits beside a physical cue word, and it never records whether the person was
physically there. A rival-clan genius discussed in chapter 1 and met in chapter 45 needs both: the look comes only from
the chapters where he is present in person (owner gold 2026-11-28).
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from echotales.core.enums import OBSERVER_SYSTEM, AssertedBy, TargetKind, TruthStatus
from echotales.core.interval import Certainty, FuzzyInterval
from echotales.core.models import Attribute, Chapter, DiscoursePosition, Mention
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.pipeline.knowledge.common import (
    artifact_id,
    artifacts_like,
    has_artifact,
    model_id_of,
    norm,
    put_artifact,
    quote_in,
)
from echotales.pipeline.llm.tasks import Task
from pydantic import BaseModel, Field

APPEARANCE_KEYS = (
    "hair_color", "hair_style", "eye_color", "skin_tone", "face", "height_build",
    "distinguishing_features", "typical_attire", "current_condition", "apparent_age",
)
SELF_KEYS = ("role", "affiliation")
ALL_KEYS = APPEARANCE_KEYS + SELF_KEYS
#: One value at a time: a new value ends the old one. Every other key is additive (a person wears several things).
SINGLE_VALUED = frozenset({"hair_color", "hair_style", "eye_color", "skin_tone", "height_build", "apparent_age"})
#: Hold from the start of the body once seen: hair or eye colour stated in chapter 45 was true in chapter 1.
INNATE = frozenset({"hair_color", "eye_color", "skin_tone"})
#: A costume or an injury is a state of the scene; it ends with the chapter that states it unless restated.
SCENE_BOUND = frozenset({"typical_attire", "current_condition"})

OBSERVER = "reader"
CONFIDENCE = 0.7
_EVIDENCE = re.compile(r'^"(?P<quote>.*)" \[ch(?P<ch>[\d.]+) #(?P<block>\d+) (?P<model>.+)\]$', re.S)


class FactOut(BaseModel):
    attribute: str
    value: str
    quote: str
    block: int | None = None


class CharOut(BaseModel):
    name: str
    in_person: bool = False
    facts: list[FactOut] = Field(default_factory=list)


class WindowOut(BaseModel):
    characters: list[CharOut] = Field(default_factory=list)


class YesNo(BaseModel):
    answer: bool = False


@dataclass(slots=True)
class MapReport:
    chapters: int = 0
    skipped: int = 0
    windows: int = 0
    proposed: int = 0
    accepted: int = 0
    duplicates: int = 0
    rejected_key: int = 0
    rejected_quote: int = 0
    rejected_subject: int = 0
    rejected_not_present: int = 0
    asked_attribution: int = 0
    seconds: float = 0.0
    per_chapter_seconds: dict[float, float] = field(default_factory=dict)

    def add(self, other: MapReport) -> None:
        for name in ("chapters", "skipped", "windows", "proposed", "accepted", "duplicates", "rejected_key",
                     "rejected_quote", "rejected_subject", "rejected_not_present", "asked_attribution", "seconds"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.per_chapter_seconds.update(other.per_chapter_seconds)


@dataclass(slots=True)
class DossierFact:
    key: str
    value: str
    quote: str
    source_chapter: float
    block: int
    model: str
    #: True when no fact holds at the asked time and this is the nearest later one (a look known only from later chapters).
    extrapolated: bool = False


@dataclass(slots=True)
class Dossier:
    entity_id: str
    label: str
    chapter: float
    appearance: dict[str, list[DossierFact]] = field(default_factory=dict)
    roles: list[DossierFact] = field(default_factory=list)
    affiliations: list[DossierFact] = field(default_factory=list)
    first_in_person: float | None = None

    def facts(self) -> list[DossierFact]:
        return [f for fs in self.appearance.values() for f in fs] + self.roles + self.affiliations


def parse_evidence(evidence: str) -> tuple[str, float, int, str] | None:
    m = _EVIDENCE.match(evidence or "")
    return (m["quote"], float(m["ch"]), int(m["block"]), m["model"]) if m else None


def _is_kb(attr: Attribute) -> bool:
    return parse_evidence(attr.evidence) is not None


def _short(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().strip(".,;").lower()[:80]


def _same_value(a: str, b: str) -> bool:
    """Paraphrase-tolerant: "black" and "jet black" are one value, so they must not read as a change of hair."""
    a, b = _short(a), _short(b)
    return a == b or (len(a) >= 3 and len(b) >= 3 and (a in b or b in a))


# ---------------------------------------------------------------- map ----------------------------------------------


def _people(store: Store, novel_id: str) -> dict[str, str]:
    return {e.id: e.canonical_label for e in store.all_selves(novel_id) if e.kind.is_person}


def _window_blocks(window: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in window.split("\n#"):
        m = re.match(r"#?(\d+): (.*)", line, re.S)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def _prompt(cast: list[tuple[str, list[str]]], window: str) -> str:
    people = "\n".join(f"- {n}" + (f" (also: {', '.join(al)})" if al else "") for n, al in cast)
    keys = ", ".join(ALL_KEYS)
    return (
        f"Characters whose names appear in this passage (use these names exactly):\n{people}\n\n"
        "For each listed character the passage actually shows, report:\n"
        "- in_person: true only if the character is physically in the scene (acting, speaking, being seen). "
        "false if they are only talked about, remembered, imagined, or named in passing.\n"
        f"- facts: physical details and role details the passage states about that character. attribute is one of: {keys}. "
        "role is a title or position (clan head, elder, student); apparent_age is a stated or described age "
        "(middle-aged, about 15, young). value is 1-4 words. block is the number after # of the line the quote is in. "
        "quote is copied EXACTLY from that line, at most 12 words.\n"
        "Only what the passage states about that character. No outside knowledge. Leave out characters with nothing.\n"
        'Example: {"characters": [{"name": "Tom", "in_person": true, "facts": [{"attribute": "hair_color", '
        '"value": "red", "block": 3, "quote": "red-haired man"}]}]}\n\n'
        f"Passage (each line starts with its block number):\n{window}"
    )


def _entity_surfaces(mentions: list[Mention], ids: set[str]) -> dict[str, dict[int, set[str]]]:
    """self_id -> block index -> lower-cased surface forms the stored mentions found there."""
    out: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for m in mentions:
        if m.target_id in ids:
            out[m.target_id][m.block_index].add(norm(m.text))
    return out


def _subject_ok(
    client: Any, store: Store, novel_id: str, chapter: float, self_id: str, label: str, quote: str, block: int,
    surfaces: dict[str, dict[int, set[str]]], report: MapReport, text: str,
) -> bool:
    """Stored mention in the block and no rival name in the quote -> accepted; otherwise ask a yes/no question.

    A model shown "Fang Yuan" and "Fang Zhi" put one's eyes on the other in the first full pass over RI, so the quote
    must be tied to this entity by evidence the model did not produce."""
    from echotales.pipeline.reader.facts_pass import _recorded_gender, gender_conflict

    if gender_conflict(_recorded_gender(store, self_id), quote):
        return False
    own = surfaces.get(self_id, {}).get(block, set())
    rivals = {s for sid, by_block in surfaces.items() if sid != self_id for s in by_block.get(block, set())}
    q = norm(quote)
    rival_in_quote = any(len(s) >= 3 and s in q for s in rivals - own)
    if own and not rival_in_quote:
        return True
    report.asked_attribution += 1
    ask = (
        f"Passage:\n{text}\n\nQuestion: does the phrase \"{quote}\" describe {label} (not someone else in the passage)? "
        'Answer {"answer": true} or {"answer": false}.'
    )
    return bool(client.complete(Task.READER, ask, YesNo, novel_id=novel_id, chapter=chapter, max_tokens=40).value.answer)


def _norm_key(raw: str) -> str:
    key = norm(raw).replace(" ", "_").replace("-", "_")
    aliases = {"hair": "hair_color", "eyes": "eye_color", "skin": "skin_tone", "build": "height_build",
               "clothing": "typical_attire", "attire": "typical_attire", "marks": "distinguishing_features",
               "condition": "current_condition", "age": "apparent_age", "title": "role", "position": "role"}
    return aliases.get(key, key)


def build_dossiers(
    store: Store,
    client: Any,
    novel_id: str,
    chapters: list[float] | None = None,
    *,
    only_entities: list[str] | None = None,
    force: bool = False,
    say: Any = print,
) -> MapReport:
    """Map + check + reduce for each chapter in reading order. Resumable: a chapter already done for this model is skipped.

    `only_entities` are ids or case-insensitive label fragments; with it the chapter key includes the filter so a
    targeted run never marks a chapter as fully done."""
    from echotales.pipeline.reader.speakers_pass import windows

    model = model_id_of(client)
    people = _people(store, novel_id)
    scope = None
    tag = "all"
    if only_entities:
        wanted = [w.lower() for w in only_entities]
        scope = {sid for sid, name in people.items() if sid.lower() in wanted or any(w in name.lower() for w in wanted)}
        tag = "only-" + "+".join(sorted(wanted))
    report = MapReport()
    for number in chapters if chapters is not None else store.chapter_numbers(novel_id):
        art = artifact_id("dossier-map", novel_id, f"{number:g}", model, tag)
        full = artifact_id("dossier-map", novel_id, f"{number:g}", model, "all")
        if not force and (has_artifact(store, art) or has_artifact(store, full)):
            report.skipped += 1
            continue
        chapter = store.get_chapter(novel_id, number)
        if chapter is None:
            continue
        started = time.perf_counter()
        one, presence = _map_chapter(store, client, novel_id, chapter, people, scope, model, windows)
        one.seconds = time.perf_counter() - started
        one.per_chapter_seconds[number] = one.seconds
        put_artifact(store, art, {
            "chapter": number, "model": model, "scope": tag, "presence": presence,
            "stats": {k: getattr(one, k) for k in MapReport.__slots__ if k not in ("per_chapter_seconds",)},
        })
        report.add(one)
        report.chapters += 1
        say(f"dossier ch{number:g}: {one.accepted} facts from {one.windows} windows in {one.seconds:.0f}s")
    return report


def _map_chapter(
    store: Store, client: Any, novel_id: str, chapter: Chapter, people: dict[str, str], scope: set[str] | None,
    model: str, windows_fn: Any,
) -> tuple[MapReport, dict[str, Any]]:
    report = MapReport()
    number = chapter.number
    mentions = [m for m in store.get_mentions(novel_id, number) if m.target_id in people and (scope is None or m.target_id in scope)]
    if not mentions:
        return report, {}
    surfaces = _entity_surfaces(mentions, set(people))
    # Surfaces of rivals must also include people outside the scope, or the rival check is blind to them.
    surfaces.update(_entity_surfaces([m for m in store.get_mentions(novel_id, number) if m.target_id in people], set(people)))
    n_blocks = max((b.index for b in chapter.blocks), default=0) + 1
    presence: dict[str, dict[str, Any]] = {}
    for window in windows_fn(chapter, tagged=False):
        blocks = _window_blocks(window)
        here: dict[str, set[str]] = defaultdict(set)
        for m in mentions:
            if m.block_index in blocks:
                here[m.target_id].add(m.text)
        if not here:
            continue
        report.windows += 1
        cast = [(people[sid], sorted(t for t in texts if norm(t) != norm(people[sid]))[:4]) for sid, texts in here.items()]
        by_name = {norm(people[sid]): sid for sid in here}
        for sid, texts in here.items():
            for t in texts:
                by_name.setdefault(norm(t), sid)
        out = client.complete(Task.READER, _prompt(cast, window), WindowOut, novel_id=novel_id, chapter=number,
                              max_tokens=1800).value
        for char in out.characters:
            sid = by_name.get(norm(char.name))
            if sid is None:
                continue
            rec = presence.setdefault(sid, {"in_person": False, "blocks": []})
            if char.in_person:
                rec["in_person"] = True
                rec["blocks"] = sorted(set(rec["blocks"]) | {m.block_index for m in mentions
                                                              if m.target_id == sid and m.block_index in blocks})
            for fact in char.facts:
                report.proposed += 1
                _accept(store, client, novel_id, number, n_blocks, sid, people[sid], fact, char.in_person, blocks, window,
                        surfaces, model, report)
    return report, presence


def _accept(
    store: Store, client: Any, novel_id: str, number: float, n_blocks: int, sid: str, label: str, fact: FactOut,
    in_person: bool, blocks: dict[int, str], window: str, surfaces: dict[str, dict[int, set[str]]], model: str,
    report: MapReport,
) -> None:
    key = _norm_key(fact.attribute)
    value = _short(fact.value)
    if key not in ALL_KEYS or not value or value in {"unknown", "none", "n/a", "not stated"}:
        report.rejected_key += 1
        return
    # Looks come only from people physically there: a description of an absent person is hearsay and may be
    # exaggerated or false. Roles are accepted either way (a title is stated about the absent as often as the present).
    if key in APPEARANCE_KEYS and not in_person:
        report.rejected_not_present += 1
        return
    block = fact.block if fact.block in blocks and quote_in(fact.quote, blocks[fact.block]) else next(
        (i for i, text in blocks.items() if quote_in(fact.quote, text)), None)
    if block is None:
        report.rejected_quote += 1
        return
    if not _subject_ok(client, store, novel_id, number, sid, label, fact.quote, block, surfaces, report, window):
        report.rejected_subject += 1
        return
    if _write_fact(store, novel_id, sid, key, value, fact.quote.strip(), number, block, n_blocks, model):
        report.accepted += 1
    else:
        report.duplicates += 1


# ---------------------------------------------------------------- reduce -------------------------------------------


def _target_for(store: Store, sid: str, key: str, pos: float) -> tuple[TargetKind, str]:
    from echotales.pipeline.persona.split import persona_at

    return (TargetKind.SELF, sid) if key in SELF_KEYS else (TargetKind.PERSONA, persona_at(store, sid, pos))


def _body_start(store: Store, sid: str, persona_id: str) -> float:
    from echotales.pipeline.persona.split import bodies_of

    return float(next((iv.from_lb for pid, iv in bodies_of(store, sid) if pid == persona_id), 0.0))


def _write_fact(
    store: Store, novel_id: str, sid: str, key: str, value: str, quote: str, number: float, block: int, n_blocks: int,
    model: str,
) -> bool:
    pos = number + block / max(n_blocks, 1)
    kind, target = _target_for(store, sid, key, pos)
    rows = [a for a in store.get_attributes(kind, target) if a.key == key and _is_kb(a)]
    rows.sort(key=lambda a: a.interval.from_lb)
    if key in SINGLE_VALUED:
        governing = [a for a in rows if a.interval.from_lb <= pos]
        if governing and _same_value(governing[-1].value, value):
            return False
    elif any(_same_value(a.value, value) and (key not in SCENE_BOUND or a.interval.from_lb // 1 == number // 1) for a in rows):
        return False
    interval = FuzzyInterval.point_known(pos, float(int(number) + 1)) if key in SCENE_BOUND else FuzzyInterval.open_ended(pos, last_evidence=pos)
    store.add_attribute(novel_id, Attribute(
        target_kind=kind, target_id=target, key=key, value=value, interval=interval,
        learned_at_pos=DiscoursePosition(chapter=int(number), offset=block), observer_id=OBSERVER,
        asserted_by=AssertedBy.INFERENCE, truth_status=TruthStatus.TRUE,
        evidence=f'"{quote}" [ch{number:g} #{block} {model}]', confidence=CONFIDENCE,
    ))
    if key in SINGLE_VALUED:
        _rechain(store, sid, kind, target, key)
    store.conn.commit()
    return True


def _rechain(store: Store, sid: str, kind: TargetKind, target: str, key: str) -> None:
    """Re-derive the interval chain of one single-valued key from its rows, whatever order they were written in.

    Each row ends where the next different value starts; the last stays open. An innate trait's first row reaches back
    to the start of its body (RI: hair colour read in chapter 45 holds in chapter 1)."""
    rows = sorted((a for a in store.get_attributes(kind, target) if a.key == key and _is_kb(a)),
                  key=lambda a: (a.interval.from_ub, a.source_row_id or 0))
    begin = [a.interval.from_ub for a in rows]
    if key in INNATE and rows:
        begin[0] = min(begin[0], _body_start(store, sid, target) if kind is TargetKind.PERSONA else 0.0)
    for i, a in enumerate(rows):
        if i + 1 < len(rows):
            interval = FuzzyInterval.point_known(begin[i], max(begin[i + 1], begin[i]))
        else:
            interval = FuzzyInterval.open_ended(begin[i], last_evidence=begin[i])
        if a.source_row_id is not None:
            store.set_attribute_interval(a.source_row_id, interval)


# ---------------------------------------------------------------- read ---------------------------------------------


def _fact(a: Attribute, *, extrapolated: bool = False) -> DossierFact | None:
    p = parse_evidence(a.evidence)
    return DossierFact(a.key, a.value, p[0], p[1], p[2], p[3], extrapolated) if p else None


def first_in_person_chapter(store: Store, novel_id: str, entity_id: str) -> float | None:
    """First chapter whose map pass saw the entity physically present, from the stored presence records."""
    best: float | None = None
    for payload in artifacts_like(store, f"kb:dossier-map:{novel_id}:"):
        if payload.get("presence", {}).get(entity_id, {}).get("in_person"):
            best = payload["chapter"] if best is None else min(best, payload["chapter"])
    return best


def dossier_at(
    store: Store, novel_id: str, entity_id: str, chapter: float, *, whole_novel: bool = True, extrapolate: bool = True,
) -> Dossier:
    """The dossier for `entity_id` at story chapter `chapter`, on `state_of()`.

    `whole_novel=True` reads every fact the volume ever stated (observer SYSTEM): the adapter of chapter 1 is allowed to
    know a rival's look from chapter 45. `False` is the reader's view: only what chapters <= `chapter` had told them.
    With `extrapolate`, a key nothing covers at that time falls back to the nearest later fact, flagged `extrapolated`."""
    from echotales.pipeline.persona.split import persona_at

    entity = store.get_self(entity_id)
    label = entity.canonical_label if entity else entity_id
    resolver = StateResolver(store, novel_id)
    observer = OBSERVER_SYSTEM if whole_novel else "READER"
    kn = None if whole_novel else DiscoursePosition(chapter=int(chapter), offset=10**6)
    position = float(chapter)
    out = Dossier(entity_id, label, chapter, first_in_person=first_in_person_chapter(store, novel_id, entity_id))
    persona = persona_at(store, entity_id, position)
    seen_keys: set[str] = set()
    for kind, target in ((TargetKind.PERSONA, persona), (TargetKind.SELF, entity_id)):
        state = resolver.state_of(target, target_kind=kind, position=position, observer_id=observer, knowledge_pos=kn)
        del state  # the winning-per-key dict is not enough for additive keys; provenance rows come next
        winners = resolver.resolve_admissible_attributes(
            target, target_kind=kind, position=position, observer_id=observer, knowledge_pos=kn, include_plausible=True)
        rows = {a.source_row_id: a for a in winners if _is_kb(a)}
        for a in store.get_attributes(kind, target):
            known_by = whole_novel or (parse_evidence(a.evidence) or ("", 1e9))[1] <= chapter
            if (_is_kb(a) and a.key not in SINGLE_VALUED and a.retracted_at is None and known_by
                    and a.interval.contains(position) is not Certainty.EXCLUDED):
                rows.setdefault(a.source_row_id, a)
        for a in rows.values():
            f = _fact(a)
            if f is None:
                continue
            seen_keys.add(a.key)
            _file(out, f)
    if extrapolate:
        for kind, target in ((TargetKind.PERSONA, persona), (TargetKind.SELF, entity_id)):
            later: dict[str, Attribute] = {}
            for a in store.get_attributes(kind, target):
                nearer = a.key not in later or a.interval.from_lb < later[a.key].interval.from_lb
                if (_is_kb(a) and a.key not in seen_keys and a.key not in SCENE_BOUND
                        and a.interval.from_lb > position and nearer):
                    later[a.key] = a
            for a in later.values():
                f = _fact(a, extrapolated=True)
                if f is not None:
                    _file(out, f)
    return out


def _file(d: Dossier, f: DossierFact) -> None:
    if f.key == "role":
        d.roles.append(f)
    elif f.key == "affiliation":
        d.affiliations.append(f)
    else:
        d.appearance.setdefault(f.key, []).append(f)
