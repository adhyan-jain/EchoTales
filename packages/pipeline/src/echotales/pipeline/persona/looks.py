"""Look-by-epoch: how one character looks at one story time, read from the text and never from a name.

Why (RI ch1 render v57, `data/novels/RI/panels/ch1/v57_round8/manifest.jsonl`): every named person got the same sentence
("a man with long black hair tied up in a topknot with a hairpin, dark brown eyes and an average build ... an adult face"),
because `identity_lock` fills every gap from a three-entry genre table (two of the three are topknots) and carries one lock
per body, and a body only splits when two chapters state a change. So the Gu Yue clan head, Fang Zhi and Fang Yuan were one
face, and Fang Yuan wore the cliff's torn green robes and bloody hair in the hall 500 years earlier and after the rebirth,
where block 83 says "his own young and soft, pale palms".

What this does instead, per character per chapter:

1. Cut the chapter into scene windows (explicit scene breaks, the text's own reset statements such as a rebirth, a size cap)
   and read, per window the character is in, what the text states: age, gender, hair, eyes, build, face, clothes,
   condition. Every value a model returns is kept only if the block it cites actually contains its words (a small model
   fills these from the genre when the text is silent).
2. Merge neighbouring windows into epochs: a new epoch starts where the stated age band changes (the 500-year-old at the
   cliff against the youth the clan head thinks about), or where clothes differ across a reset statement. A stated
   condition belongs to its own epoch only, so torn robes are never carried into the next one.
3. Fill what the text leaves open from a per-novel slot bank, allocated once and stored, so two people never share the
   invented hair+build+face tuple, and flag every such field `invented` with a reason.

No per-novel canon tables and no name-suffix gender rules; gender is a stored/owner value, else pronoun evidence in the
character's own passages, else None.
"""

from __future__ import annotations

import contextlib
import hashlib
import itertools
import json
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

TIER = "LOOK"

AGE_BANDS = ("child", "teen", "young adult", "adult", "middle-aged", "elderly", "ageless-ancient")
_FIELDS = ("hair_colour", "hair_style", "eyes", "build", "face", "skin", "clothes", "condition", "marks")

#: Reader/graph attribute keys -> this module's fields.
_GRAPH_KEYS = {
    "hair_color": "hair_colour", "hair_style": "hair_style", "eye_color": "eyes", "height_build": "build",
    "skin_tone": "skin", "typical_attire": "clothes", "current_condition": "condition",
    "distinguishing_features": "marks",
}


class LookFact(BaseModel):
    field: str
    value: str
    source_block: int | None = None
    invented: bool = False
    reason: str = ""


class Look(BaseModel):
    """One character's look over one stretch of story. The storyboard director calls `look_at` and copies `look_id`."""

    look_id: str
    entity_id: str
    epoch_label: str
    age_band: str
    gender: str | None = None
    #: Prompt-ready, concrete visual words: hair, eyes, build, face, clothes, condition.
    description: str
    facts: list[LookFact] = Field(default_factory=list)
    #: The parts `description` is joined from, for callers that place them separately (`identity_lock.LockedIdentity`).
    hair: str = ""
    eyes: str = ""
    build: str = ""
    face: str = ""
    outfit: str = ""
    condition: str = ""
    marks: str = ""
    #: First and last block of the epoch (inclusive) in this chapter.
    block_from: int = 0
    block_to: int = 0

    def fact(self, name: str) -> LookFact | None:
        return next((f for f in self.facts if f.field == name), None)


# ---------------------------------------------------------------------------
# what the text says
# ---------------------------------------------------------------------------


class _ReadFact(BaseModel):
    field: str = ""
    value: str = ""
    block: int | None = None


class WindowRead(BaseModel):
    """A model's reading of one scene window for one character. Everything here is re-checked against the cited block."""

    present: bool = False
    gender: str = ""
    gender_block: int | None = None
    age_band: str = ""
    age_block: int | None = None
    facts: list[_ReadFact] = Field(default_factory=list)


READ_SYSTEM = (
    "You read numbered blocks of a novel and report ONLY what the text states about how ONE named character looks. "
    "Return JSON: present (true if this character is in or described in these blocks), gender (male/female, only if a "
    "pronoun or noun for THIS character states it, else empty), gender_block, age_band, age_block, and facts. "
    "age_band is one of child, teen, young adult, adult, middle-aged, elderly, ageless-ancient; use a stated age or "
    "stated life span, or a word the text uses for this character (boy, youth, middle-aged, old, lived hundreds of years "
    "= ageless-ancient); empty if the blocks give no cue. facts is a list of {field, value, block} where field is one of "
    "hair_colour, hair_style, eyes, build, face, skin, clothes, condition, marks. clothes: the garment and colour as "
    "stated. build: body shape only (tall, lean, stocky). eyes: colour or shape in at most four words. Keep every value to a "
    "short phrase copied from the text. condition: damage or state of body or clothes (torn robes, covered in blood, disheveled hair). block is the "
    "number of the block that states it. Never guess from the genre and never add what the text does not say. A person "
    "who is only talked about still gets age and gender if the text states them."
)


# ---------------------------------------------------------------------------
# deterministic cues (used to confirm a model, and when there is no model)
# ---------------------------------------------------------------------------

_AGE_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmiddle[- ]aged?\b", re.I), "middle-aged"),
    (re.compile(r"\b(?:elderly|aged|old man|old woman|grandfather|grandmother|greybeard|graybeard|white[- ]haired old)\b", re.I), "elderly"),
    (re.compile(r"\b(?:infant|baby|toddler|little boy|little girl|child)\b", re.I), "child"),
    (re.compile(r"\b(?:teenag\w*|adolescent|youth|juvenile|boy|girl|young and soft)\b", re.I), "teen"),
    (re.compile(r"\b(?:young man|young woman|young master|young lady)\b", re.I), "young adult"),
    # Last, because a reborn youth also says "500 years of experience": a lived span names the body only as "of his life".
    (re.compile(r"\b(?:\d{3,} years of (?:his |her )?(?:life|cultivation)|(?:life|lived|living)\b[^.]{0,40}\b\d{3,} years|"
                r"hundreds? of years of (?:his |her )?life|centuries of (?:his |her )?life)", re.I), "ageless-ancient"),
)
#: A role noun is evidence about age only when it names the character itself, e.g. the label "Elder Gu".
_ROLE_AGE = (
    (re.compile(r"\b(?:elder|patriarch|ancestor|grandmaster|old)\b", re.I), "elderly"),
)
_YEARS = re.compile(r"\b(\d{1,3})[- ]years?[- ]old\b", re.I)
_BREAK = re.compile(r"^[\W_]*$|^\s*(?:\*\s*){2,}$")
#: The text itself says time was reversed or the person came back: the story clock restarts, so what the character looked
#: like before is not what they look like after (RI block 81-83: "reverse time ... reborn ... young and soft, pale palms").
_RESET = re.compile(
    r"\b(?:reverse time|turn back time|back in time|reborn|rebirth|reincarnat\w*|regress(?:ed|ion)|travell?ed back|"
    r"sent back|returned to the past)\b", re.I)
_SENT = re.compile(r"(?<=[.!?”\"])\s+")
_SUBJECT = re.compile(r"^\W*(?:he|she|his|her)\b", re.I)
_STOP = {"of", "the", "a", "an", "and"}
_PRONOUN_M = re.compile(r"\b(he|his|him)\b", re.I)
_PRONOUN_F = re.compile(r"\b(she|her|hers)\b", re.I)

#: Characters of text one read covers. A window is a scene, capped, so one call sees one story time.
WINDOW_CHARS = 3600


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{3,}", text.casefold())}


#: Longest value (in words) each field may carry into an image prompt. A 7B model reading RI ch1 returned whole clauses
#: ("like deep pools of water in a well, so deep that ...") as an eye colour and a sentence fragment as a build.
_MAX_WORDS = {"hair_colour": 3, "hair_style": 7, "eyes": 4, "build": 5, "face": 7, "skin": 4, "clothes": 9,
              "condition": 11, "marks": 9}
_BUILD_WORDS = re.compile(
    r"\b(tall|short|lean|thin|slim|slender|stocky|broad|muscular|burly|frail|heavy|plump|fat|build|frame|stature|petite|"
    r"sturdy|wiry|hunched|stooped|strong|small|large|towering|gaunt|lanky|bulky|average)\b", re.I)


_STATE = re.compile(
    r"\b(?:torn|tore|shred\w*|rip\w*|blood\w*|bleed\w*|wound\w*|injur\w*|bruis\w*|gash\w*|bandag\w*|stain\w*|soak\w*|drench\w*|"
    r"burn\w*|scorch\w*|batter\w*|dishevel\w*|ragged|scratch\w*|mangled|exhaust\w*|weary|limp\w*|muddy|dusty|ash\w*)\b", re.I)


def _clean(field_name: str, value: str) -> str:
    v = re.sub(r"\s+", " ", value or "").strip().strip(".,;")
    if not v or len(v.split()) > _MAX_WORDS.get(field_name, 9) or re.search(r"[;:]", v):
        return ""
    if field_name == "build" and not _BUILD_WORDS.search(v):
        return ""
    if field_name in ("hair_colour", "skin", "eyes", "face") and (_STATE.search(v) or _HAIR_STATE.search(v)):
        return ""  # "disheveled" as a hair colour, "covered in blood" as a skin: a state, which belongs to condition
    if field_name == "condition" and not _STATE.search(v):
        return ""  # a pose or a time of day ("kneeling on the floor", "late in the night") is not a state of the body
    return v


def _grounded(value: str, block_text: str) -> bool:
    """A value is kept only when most of its content words are in the block it cites (a small model fills fields from the
    genre when the text is silent, and mixes in words of a neighbouring person's sentence)."""
    mine = _stems(value)
    if not mine:
        return False
    need = len(mine) if len(mine) <= 2 else -(-len(mine) * 2 // 3)
    return len(mine & _stems(block_text)) >= need


def band_from_years(years: int) -> str:
    if years < 13:
        return "child"
    if years < 20:
        return "teen"
    if years < 30:
        return "young adult"
    if years < 50:
        return "adult"
    if years < 65:
        return "middle-aged"
    return "elderly"


def age_cue(text: str) -> str:
    """The age band a passage states for its subject, or ''. A stated number of years wins over a word."""
    m = _YEARS.search(text)
    if m:
        return band_from_years(int(m.group(1)))
    for pat, band in _AGE_CUES:
        if pat.search(text):
            return band
    return ""


# ---------------------------------------------------------------------------
# chapter evidence
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Window:
    first: int
    last: int
    present: list[int]
    reset_before: bool = False
    read: WindowRead | None = None


def surface_names(store: Any, novel_id: str, entity_id: str, chapter: float) -> list[str]:
    """Every string that names this entity in this chapter: label, aliases, and the unresolved title mentions that share a
    content word with the label (the clan head is `head of gu` in the graph and "Gu Yue clan head", "the clan head" in the
    prose, and those mentions carry no target id)."""
    from echotales.core.enums import TargetKind

    ent = store.get_self(entity_id)
    names: list[str] = [ent.canonical_label] if ent is not None and ent.canonical_label else []
    with contextlib.suppress(Exception):  # an entity kind with no alias table row
        names += [a.alias for a in store.get_aliases_for(TargetKind.SELF, entity_id)]
    stop = {"of", "the", "a", "an", "and"}
    label_words = {w for n in names[:1] for w in re.findall(r"[a-z]+", n.casefold()) if w not in stop}
    if ent is not None and entity_id.split(":")[1:2] == ["title"] and label_words:
        for r in store.conn.execute(
            "SELECT DISTINCT text FROM mention WHERE novel_id=? AND chapter=? AND target_id IS NULL"
            " AND alias_type='TRANSFERABLE_TITLE'", (novel_id, chapter),
        ):
            if label_words & set(re.findall(r"[a-z]+", r["text"].casefold())):
                names.append(r["text"])
    out: list[str] = []
    for n in names:
        n = n.strip()
        if n and n.casefold() not in {x.casefold() for x in out}:
            out.append(n)
    return out


def _present_blocks(store: Any, novel_id: str, entity_id: str, chapter: float, blocks: list[Any], names: list[str]) -> list[int]:
    hits: set[int] = set()
    pats = [re.compile(rf"\b{re.escape(n)}\b", re.I) for n in names if len(n) > 2]
    ent = store.get_self(entity_id)
    # A title entity ("head of gu") is written in the prose as "the head of the Gu Yue clan": all its content words in one block.
    words = ({w for w in re.findall(r"[a-z]+", ent.canonical_label.casefold()) if w not in {"of", "the", "a", "an", "and"}}
             if ent is not None and ":title:" in entity_id else set())
    for b in blocks:
        if any(p.search(b.text) for p in pats) or (words and words <= set(re.findall(r"[a-z]+", b.text.casefold()))):
            hits.add(b.index)
    for r in store.conn.execute(
        "SELECT block_index FROM mention WHERE novel_id=? AND chapter=? AND target_id=?", (novel_id, chapter, entity_id)
    ):
        hits.add(int(r["block_index"]))
    return sorted(hits)


def _cut_windows(blocks: list[Any], present: list[int]) -> list[_Window]:
    """Scene windows: cut after a break-only block, before a reset statement's lead-in, and at the size cap."""
    by_idx = {b.index: b for b in blocks}
    order = [b.index for b in blocks]
    pset = set(present)
    cuts: set[int] = set()
    for pos, i in enumerate(order):
        if _BREAK.match(by_idx[i].text.strip() or ".") and pos + 1 < len(order):
            cuts.add(order[pos + 1])
    reset_blocks: set[int] = set()
    for pos, i in enumerate(order):
        if _RESET.search(by_idx[i].text):
            # Back up to the earliest block just before the statement that names the character: the reborn person is already
            # looking out of the window one block earlier (RI block 80 names him, block 81 explains).
            lead = [j for j in order[max(0, pos - 3): pos + 1] if j in pset]
            start = lead[0] if lead else i
            reset_blocks.add(start)
            cuts.add(start)
            break  # the first reset statement of the chapter; later ones restate it
    windows: list[_Window] = []
    cur: list[int] = []
    size = 0
    for i in order:
        if cur and (i in cuts or size + len(by_idx[i].text) > WINDOW_CHARS):
            windows.append(_mk(cur, pset, reset_blocks))
            cur, size = [], 0
        cur.append(i)
        size += len(by_idx[i].text)
    if cur:
        windows.append(_mk(cur, pset, reset_blocks))
    return windows


def _mk(idx: list[int], pset: set[int], reset_blocks: set[int]) -> _Window:
    return _Window(idx[0], idx[-1], [i for i in idx if i in pset], reset_before=idx[0] in reset_blocks)


def _read_window(store: Any, client: Any, novel_id: str, entity_id: str, name: str, chapter: float, w: _Window,
                 blocks: dict[int, Any]) -> WindowRead | None:
    # Only the blocks the character is in or next to: the whole window let the model hand the elders' white ceremonial
    # garments (block 39) to the clan head who is named in blocks 40-78.
    near = sorted({j for i in w.present for j in range(i - 2, i + 3) if w.first <= j <= w.last and j in blocks})
    text = "\n".join(f"[{i}] {blocks[i].text}" for i in near)
    key = hashlib.md5(f"{name}|{text}".encode()).hexdigest()[:12]
    aid = f"look_read:{entity_id}:{chapter:g}:{w.first}-{w.last}:{key}"
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (aid,)).fetchone()
    if row is not None:
        return WindowRead(**json.loads(row["payload_json"]))
    if client is None:
        return None
    from echotales.pipeline.llm.tasks import Task

    prompt = f"Character: {name}\nBlocks:\n{text}\n\nReturn only the JSON object."
    try:
        res = client.complete(Task.READER, prompt, WindowRead, system=READ_SYSTEM, novel_id=novel_id, chapter=chapter)
    except Exception as exc:
        log.warning("look read for %s %g:%d-%d failed: %s", name, chapter, w.first, w.last, exc)
        return None
    if not isinstance(res.value, WindowRead):
        return None
    read = res.value
    store.record_artifact(aid, TIER, [], "", json.dumps(read.model_dump()))
    store.conn.commit()
    return read


# ---------------------------------------------------------------------------
# slot bank: the invented parts, distinct per person
# ---------------------------------------------------------------------------

_HAIR_LEN_STYLE = (
    "short, neatly combed", "short and swept back", "medium-length, combed to one side", "long and worn loose over the shoulders",
    "long, tied up in a topknot", "long, tied back in a low ponytail", "shoulder-length with a side parting", "cropped close to the scalp",
    "long and braided over one shoulder", "shoulder-length and tied back with a cord",
)
_HAIR_COLOURS = ("black", "dark brown", "chestnut brown", "auburn", "deep brown-black", "ash brown")
_BUILDS = ("a lean build", "a broad-shouldered build", "a slight build", "a stocky build", "a tall wiry build", "an average build")
_FACES = (
    "a narrow face with high cheekbones", "a square jaw and heavy brows", "a round face with soft features",
    "a long face with a straight nose", "a sharp chin and deep-set eyes", "a broad forehead and thin lips",
)
_COLOURS = ("charcoal grey", "deep navy", "dark maroon", "moss green", "ochre", "slate blue", "plum", "rust brown")
_GARMENT = {
    True: "robe with wide sleeves and a plain sash",
    False: "frock coat and waistcoat over a white shirt",
}
_FEMALE_GARMENT = {True: "layered robe dress with a plain sash", False: "long dress with a high collar"}
_AGED_HAIR = {"middle-aged": "{c} hair graying at the temples", "elderly": "white hair",
              "ageless-ancient": "{c} hair with a few silver strands"}
_YOUNG_BUILD = {"child": "a small child's frame", "teen": "a slim boyish build"}

_HAIR_STATE = re.compile(r"(?:dishevel\w*|messy|unkempt|tangled|matted|wild|bloodied|bloody|disarrayed|ruffled)(?: and \w+)?")
_DIMS = 5  # hair style, hair colour, build, face, outfit colour


def _bank() -> list[tuple[int, ...]]:
    combos = list(itertools.product(range(len(_HAIR_LEN_STYLE)), range(len(_HAIR_COLOURS)), range(len(_BUILDS)),
                                    range(len(_FACES)), range(len(_COLOURS))))
    random.Random(20261127).shuffle(combos)  # a fixed shuffle: the bank order never changes
    return combos


def _slot_for(store: Any, novel_id: str, entity_id: str) -> tuple[int, ...]:
    """The invented tuple of this entity: allocated once per novel, stored, and at least three of five dimensions away from
    every earlier allocation, so two people in one scene never share their invented hair, build and face. The first pick
    follows a hash of the entity id (so it is stable even without the store), then probes forward."""
    aid = f"look_slots:{novel_id}"
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (aid,)).fetchone()
    table: dict[str, list[int]] = json.loads(row["payload_json"]) if row is not None else {}
    if entity_id in table:
        return tuple(table[entity_id])
    bank = _bank()
    start = int(hashlib.md5(entity_id.encode()).hexdigest(), 16) % len(bank)
    taken = [tuple(v) for v in table.values()]
    chosen = bank[start]
    for step in range(len(bank)):
        cand = bank[(start + step) % len(bank)]
        if all(sum(a != b for a, b in zip(cand, t, strict=True)) >= 3 for t in taken):
            chosen = cand
            break
    table[entity_id] = list(chosen)
    store.record_artifact(aid, TIER, [], "", json.dumps(table))
    store.conn.commit()
    return chosen


# ---------------------------------------------------------------------------
# epochs
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Epoch:
    first: int
    last: int
    age_band: str = ""
    age_block: int | None = None
    gender: str = ""
    fields: dict[str, tuple[str, int | None]] = field(default_factory=dict)
    reset_start: bool = False


def _graph_facts(store: Any, entity_id: str, chapter: float, nblocks: int) -> list[tuple[str, str, int]]:
    """The reader's stored appearance facts for this entity's bodies, each placed at the block where it was first stated."""
    out: list[tuple[str, str, int]] = []
    rows = store.conn.execute(
        "SELECT a.key, a.value, a.story_from_lb, a.evidence FROM attribute a JOIN self_persona_binding b ON b.persona_id=a.target_id"
        " WHERE b.self_id=? AND a.target_kind='PERSONA' AND a.truth_status='TRUE' AND a.retracted_chapter IS NULL"
        " ORDER BY a.story_from_lb", (entity_id,),
    ).fetchall()
    for r in rows:
        fld = _GRAPH_KEYS.get(r["key"])
        sf = r["story_from_lb"]
        if not fld or not r["value"] or sf is None or int(sf) != int(chapter):
            continue
        val = _clean(fld, r["value"])
        if not val:
            continue
        blk = min(nblocks - 1, round((sf - int(chapter)) * nblocks))
        out.append((fld, val, blk))
        # The evidence quote says what happened to the garment ("deep green robes that had been torn to shreds"); the value
        # alone ("deep green robes") lost it, and the cliff was drawn in intact robes.
        dmg = re.search(r"\b(?:torn|ripped|tattered|shredded)\b[\w ]{0,14}", r["evidence"] or "", re.I) if fld == "clothes" else None
        if dmg and (c := _clean("condition", dmg.group(0).strip())):
            out.append(("condition", c, blk))
    return out


def _build_epochs(store: Any, client: Any, novel_id: str, entity_id: str, chapter: float, blocks_list: list[Any]
                  ) -> tuple[list[_Epoch], str, bool]:
    """`(epochs, label, read_by_model)`; epochs cover only the windows the character is in."""
    blocks = {b.index: b for b in blocks_list}
    names = surface_names(store, novel_id, entity_id, chapter)
    label = names[0] if names else entity_id
    present = _present_blocks(store, novel_id, entity_id, chapter, blocks_list, names)
    windows = [w for w in _cut_windows(blocks_list, present) if w.present]
    graph = _graph_facts(store, entity_id, chapter, len(blocks_list))
    modelled = False
    pats = [re.compile(rf"\b{re.escape(n)}\b", re.I) for n in names if len(n) > 2]
    ent = store.get_self(entity_id)
    words = ({w for w in re.findall(r"[a-z]+", ent.canonical_label.casefold()) if w not in _STOP}
             if ent is not None and ":title:" in entity_id else set())

    others = [re.compile(rf"\b{re.escape(r['canonical_label'])}\b", re.I) for r in store.conn.execute(
        "SELECT DISTINCT e.canonical_label FROM self_entity e JOIN mention m ON m.target_id=e.id"
        " WHERE e.novel_id=? AND e.kind='SELF' AND m.chapter=? AND e.id<>?", (novel_id, chapter, entity_id))
        if len(r["canonical_label"]) > 2]

    def about(sent: str) -> bool:
        if any(p.search(sent) for p in pats) or (words and words <= set(re.findall(r"[a-z]+", sent.casefold()))):
            return True
        # "He knew the elders were discussing the youth known as Gu Yue Fang Yuan": a He-sentence that names someone else is
        # about that someone (the clan head was read as a teen from it).
        return bool(_SUBJECT.match(sent)) and not any(o.search(sent) for o in others)

    role_age = next((band for n in names for pat, band in _ROLE_AGE if pat.search(n)), "")
    epochs: list[_Epoch] = []
    for w in windows:
        read = _read_window(store, client, novel_id, entity_id, label, chapter, w, blocks)
        modelled = modelled or read is not None
        # Age comes from a cue word in a sentence about this character (its name, or a "He/She" opening in the blocks beside
        # one it is named in). A model's band is kept only when its cited block carries the same cue: at 7B it called the
        # clan head "young adult" and the 500-year-old "teen" from one stray word.
        cues: list[tuple[str, int]] = []
        for i in sorted({j for p_ in w.present for j in range(p_ - 2, p_ + 3) if w.first <= j <= w.last and j in blocks}):
            for sent in _SENT.split(blocks[i].text):
                if about(sent) and (c := age_cue(sent)):
                    cues.append((c, i))
        pick = next((c for c in cues if c[0] != "ageless-ancient"), None) or next(iter(cues), None)
        band, band_block = pick if pick else ("", None)
        if (not band and read is not None and read.age_band in AGE_BANDS and read.age_block in blocks
                and age_cue(blocks[read.age_block].text) == read.age_band):
            band, band_block = read.age_band, read.age_block
        gender = read.gender if read is not None and read.gender in ("male", "female") else ""
        fields: dict[str, tuple[str, int | None]] = {}
        if read is not None:
            shown = {j for i in w.present for j in range(i - 2, i + 3)}
            for f in read.facts:
                blk = blocks.get(f.block) if f.block is not None else None
                fname, raw = f.field, f.value
                if fname in ("hair_colour", "hair_style") and _HAIR_STATE.fullmatch((raw or "").strip().casefold()):
                    fname, raw = "condition", f"{raw.strip()} hair"  # "disheveled" is how the hair is, not which hair
                val = _clean(fname, raw)
                # A fact must cite a block the model was shown, and that block must hold its words.
                if fname not in _FIELDS or not val or blk is None or f.block not in shown or not _grounded(val, blk.text):
                    continue
                if fname == "condition" and "condition" in fields:
                    # The text states several things about the body ("torn to shreds", "covered in blood"): all of them.
                    old_v, old_b = fields["condition"]
                    if val.casefold() not in old_v.casefold():
                        fields["condition"] = (f"{old_v}, {val}", old_b)
                elif fname not in fields:
                    fields[fname] = (val, f.block)
        for fld, val, blk_i in graph:
            if w.first <= blk_i <= w.last:
                have = fields.get(fld)
                # The reader's own evidence-quoted fact outranks a window read, unless the read says the same and more
                # ("torn green robes" over "deep green robes": the tear is what makes the cliff look battle-worn).
                if have and fld == "clothes" and _stems(val) <= _stems(have[0]) | {"deep"} and have[1] is not None and abs(have[1] - blk_i) <= 1:
                    continue
                if fld == "condition" and have and val.casefold() not in have[0].casefold():
                    fields[fld] = (f"{have[0]}, {val}", have[1])
                else:
                    fields[fld] = (val, blk_i)
        new = _Epoch(w.first, w.last, band, band_block, gender, fields, w.reset_before)
        if epochs and _same_epoch(epochs[-1], new):
            _absorb(epochs[-1], new)
        else:
            epochs.append(new)
    if not epochs:
        return [], label, modelled
    # What does not change with the scene is the same person's in every epoch: a colour or an eye colour stated once is not
    # re-invented for the next epoch (RI: black hair at the cliff, chestnut after the rebirth). Hair colour is not carried
    # across an age change that greys it.
    for k in ("eyes", "hair_colour"):
        first = next((e.fields[k] for e in epochs if k in e.fields), None)
        for e in epochs:
            if first and k not in e.fields and not (k == "hair_colour" and e.age_band in _AGED_HAIR):
                e.fields[k] = first
    if role_age:
        for e in epochs:
            if not e.age_band:
                e.age_band = role_age
    return epochs, label, modelled


def _grounded_age(read: WindowRead, blocks: dict[int, Any]) -> bool:
    blk = blocks.get(read.age_block)
    if blk is None:
        return False
    cue = age_cue(blk.text)
    return bool(cue) or bool(re.search(r"\b(?:old|young|youth|elder|aged|years?)\b", blk.text, re.I))


def _same_epoch(a: _Epoch, b: _Epoch) -> bool:
    if a.age_band and b.age_band and a.age_band != b.age_band:
        return False
    ca, cb = a.fields.get("clothes"), b.fields.get("clothes")
    return not (b.reset_start and ca and cb and _stems(ca[0]) != _stems(cb[0]))


def _absorb(a: _Epoch, b: _Epoch) -> None:
    a.last = b.last
    a.age_band = a.age_band or b.age_band
    a.age_block = a.age_block if a.age_block is not None else b.age_block
    a.gender = a.gender or b.gender
    for k, v in b.fields.items():
        a.fields.setdefault(k, v)


# ---------------------------------------------------------------------------
# turning an epoch into a Look
# ---------------------------------------------------------------------------


def _gender_of(store: Any, novel_id: str, entity_id: str, chapter: float, epoch_gender: str, own_text: str) -> tuple[str | None, str]:
    """Owner/graph value first (owner corrections are final), then a grounded model reading, then pronoun counts."""
    from echotales.pipeline.persona.split import persona_at

    try:
        pid = persona_at(store, entity_id, chapter)
        row = store.conn.execute(
            "SELECT value FROM attribute WHERE target_id=? AND key='gender' AND truth_status='TRUE'"
            " AND retracted_chapter IS NULL ORDER BY id DESC LIMIT 1", (pid,),
        ).fetchone()
    except Exception:
        row = None
    if row is not None and row["value"] in ("male", "female"):
        return row["value"], "graph"
    m, f = len(_PRONOUN_M.findall(own_text)), len(_PRONOUN_F.findall(own_text))
    if epoch_gender and (m, f)[epoch_gender == "female"] >= (m, f)[epoch_gender != "female"]:
        return epoch_gender, "model, agrees with pronouns" if (m or f) else "model"
    if m >= 2 and m >= 3 * f:
        return "male", "pronouns"
    if f >= 2 and f >= 3 * m:
        return "female", "pronouns"
    return None, ""


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else "".join(parts)


def _make_look(store: Any, novel_id: str, entity_id: str, chapter: float, n: int, e: _Epoch, gender: str | None,
               all_clothes: list[str], manhua: bool) -> Look:
    slot = _slot_for(store, novel_id, entity_id)
    facts: list[LookFact] = []

    def stated(name: str) -> str:
        v = e.fields.get(name)
        if v:
            facts.append(LookFact(field=name, value=v[0], source_block=v[1]))
            return v[0]
        return ""

    def invent(name: str, value: str, reason: str) -> str:
        facts.append(LookFact(field=name, value=value, invented=True, reason=reason))
        return value

    band = e.age_band
    if band:
        facts.append(LookFact(field="age_band", value=band, source_block=e.age_block))
    else:
        band = invent("age_band", "adult", "no age cue in this stretch of the text")
    if gender:
        facts.append(LookFact(field="gender", value=gender, source_block=None, reason="owner/graph value or pronoun evidence"))

    colour = stated("hair_colour")
    style = stated("hair_style")
    state_only = style and _HAIR_STATE.fullmatch(re.sub(r"[^a-z ]", "", style.casefold()).replace("hair", "").strip() or "x")
    cond_extra = ""
    if state_only:
        # "disheveled" is how the hair is in one scene, not which hair it is (identity_lock round 3): it joins the condition.
        cond_extra, style = style, ""
    extra_hair = ""
    if style and re.search(r"sideburn|beard|mustache|moustache|temples", style, re.I):
        extra_hair, style = style, ""
    if colour and re.search(r"sideburn|beard|mustache|moustache|temples", colour, re.I):
        extra_hair, colour = colour, ""
    if not colour and not style:
        base = _AGED_HAIR.get(band)
        if base:
            hair = invent("hair", f"{base.format(c=_HAIR_COLOURS[slot[1]])}, {_HAIR_LEN_STYLE[slot[0]]}",
                          f"age band {band} and the person's own slot; the text states no hair")
        else:
            hair = invent("hair", f"{_HAIR_COLOURS[slot[1]]} hair, {_HAIR_LEN_STYLE[slot[0]]}", "the text states no hair; chosen per person from the slot bank")
    elif colour and not style:
        hair = (f"{colour} hair" if "hair" not in colour.casefold() else colour) + ", " + invent(
            "hair_style", _HAIR_LEN_STYLE[slot[0]], "colour stated, length and style not")
    else:
        if not colour:
            colour = _HAIR_COLOURS[slot[1]]
            facts.append(LookFact(field="hair_colour", value=colour, invented=True, reason="style stated, colour not"))
        hair = f"{colour} {style}" if "hair" in style.casefold() else f"{colour} hair, {style}"
    if extra_hair:
        hair += f", {extra_hair}"
    eyes = stated("eyes")
    if eyes and len(eyes.split()) > 2 and "eye" not in eyes.casefold():
        eyes = ""  # "deep pools of water" is a simile, not something an image prompt can draw
    eyes = f"{eyes} eyes" if eyes and "eye" not in eyes.casefold() else eyes
    build = stated("build")
    if build and not build.startswith(("a ", "an ")):
        build = f"a {build} build" if " " not in build else f"a {build}"
    if not build:
        build = invent("build", _YOUNG_BUILD.get(band, _BUILDS[slot[2]]), "the text states no build")
    face = stated("face")
    if not face:
        face = invent("face", _FACES[slot[3]], "the text states no face; chosen per person")
    skin = stated("skin")
    marks = stated("marks")
    clothes = stated("clothes")
    if not clothes:
        others = {s for c in all_clothes for s in _stems(c)}
        colours = [c for c in _COLOURS if not (_stems(c) & others)] or list(_COLOURS)
        colour_c = colours[slot[4] % len(colours)]
        garment = (_FEMALE_GARMENT if gender == "female" else _GARMENT)[manhua]
        clothes = invent("clothes", f"a {colour_c} {garment}",
                         "the text states no clothes here" + ("; another epoch's stated clothes are not carried" if all_clothes else ""))
    condition = stated("condition")
    if cond_extra:
        condition = f"{condition}, hair {cond_extra}".strip(", ")
    bits = [hair, eyes, build, face, skin and f"{skin} skin"]
    desc = _join([b for b in bits if b])
    desc += f", wearing {clothes}"
    if marks:
        desc += f", {marks}"
    if condition:
        desc += f", {condition}"
    label = band + (f", {condition.split(',')[0]}" if condition else "")
    return Look(
        look_id=f"{entity_id}:{chapter:g}:e{n}", entity_id=entity_id, epoch_label=label, age_band=band, gender=gender,
        description=desc, facts=facts, hair=hair, eyes=eyes, build=build, face=face, outfit=clothes,
        condition=condition, marks=marks, block_from=e.first, block_to=e.last,
    )


def looks_for_chapter(store: Any, novel_id: str, entity_id: str, chapter: float, *, client: Any = None) -> list[Look]:
    """Every epoch's look of one character in one chapter, cached once a model has read it."""
    aid = f"look_epochs:{entity_id}:{chapter:g}"
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (aid,)).fetchone()
    if row is not None:
        return [Look(**d) for d in json.loads(row["payload_json"])]
    chap = store.get_chapter(novel_id, chapter)
    if chap is None:
        return []
    epochs, _label, modelled = _build_epochs(store, client, novel_id, entity_id, chapter, chap.blocks)
    if not epochs:
        return []
    from echotales.pipeline.render.compiler import genre_direction

    manhua = genre_direction(novel_id)[2]
    blocks = {b.index: b for b in chap.blocks}
    names = surface_names(store, novel_id, entity_id, chapter)
    own = " ".join(blocks[i].text for i in _present_blocks(store, novel_id, entity_id, chapter, chap.blocks, names))
    looks: list[Look] = []
    for n, e in enumerate(epochs):
        gender, _why = _gender_of(store, novel_id, entity_id, chapter, e.gender, own)
        others = [x.fields["clothes"][0] for x in epochs if x is not e and "clothes" in x.fields]
        looks.append(_make_look(store, novel_id, entity_id, chapter, n, e, gender, others, manhua))
    # The first and last epoch stretch to the chapter's ends: a block the character is not in takes the nearest look.
    # A block the character is not in belongs to the next epoch, not the previous: epochs end at a scene end, so the scene that
    # follows (RI blocks 31-54, the hall 500 years earlier) is a new stretch of story, not the cliff's continuation.
    looks[0].block_from = 0
    for a, b in itertools.pairwise(looks):
        b.block_from = a.block_to + 1
    looks[-1].block_to = max(b.index for b in chap.blocks)
    if modelled:  # a look built without a model read is a fallback, not a result to cache
        store.record_artifact(aid, TIER, [], "", json.dumps([lk.model_dump() for lk in looks]))
        store.conn.commit()
    return looks


def look_at(store: Any, novel_id: str, entity_id: str, *, chapter: float, block: int, client: Any = None) -> Look:
    """How `entity_id` looks at `block` of `chapter`.

    A block between two epochs the character is in takes the nearer one (the earlier on a tie). An entity the chapter never
    describes gets a single invented look, flagged as such, so a caller is never handed nothing."""
    looks = looks_for_chapter(store, novel_id, entity_id, chapter, client=client)
    if not looks:
        e = _Epoch(0, 0)
        ent = store.get_self(entity_id)
        from echotales.pipeline.render.compiler import genre_direction

        gender, _ = _gender_of(store, novel_id, entity_id, chapter, "", "")
        look = _make_look(store, novel_id, entity_id, chapter, 0, e, gender, [], genre_direction(novel_id)[2])
        look.epoch_label = f"{look.age_band}, not described in chapter {chapter:g}" if ent else look.epoch_label
        return look
    for lk in looks:
        if lk.block_from <= block <= lk.block_to:
            return lk
    return min(looks, key=lambda lk: min(abs(block - lk.block_from), abs(block - lk.block_to)))


# ---------------------------------------------------------------------------
# bridge to the prompt path
# ---------------------------------------------------------------------------

#: Look age band -> the compiler's age_band vocabulary (`render/compiler.py::_identity_head`). Centuries-old cultivators are
#: drawn as mature adults, not as the white-bearded elder the word "elderly" produces.
COMPILER_BAND = {
    "child": "child", "teen": "teen", "young adult": "adult", "adult": "adult", "middle-aged": "adult",
    "elderly": "elder", "ageless-ancient": "adult",
}


def position_to_block(store: Any, novel_id: str, position: float) -> tuple[float, int] | None:
    """Invert `render/panels.py::story_position_of` (chapter + block / block count)."""
    chapter = float(int(position))
    chap = store.get_chapter(novel_id, chapter)
    if chap is None or not chap.blocks:
        return None
    return chapter, min(len(chap.blocks) - 1, round((position - chapter) * len(chap.blocks)))


def locked_from_look(look: Look, persona_id: str) -> Any:
    """The `LockedIdentity` the compiler repeats on every panel of this epoch."""
    from echotales.pipeline.persona.identity_lock import LockedIdentity

    inv = {f.field for f in look.facts if f.invented}
    src = {k: ("default" if k in inv else "text") for k in ("hair", "build", "outfit")}
    return LockedIdentity(
        persona_id=persona_id, hair=look.hair, eyes=look.eyes, build=f"{look.build}, {look.face}".strip(", "),
        outfit=look.outfit, marks=look.marks, state=look.condition, source={**src, "look": look.look_id},
    )
