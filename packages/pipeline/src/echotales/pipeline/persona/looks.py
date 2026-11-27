"""Look-by-epoch: how one character looks at one story time, read from the text and never from a name or a word list.

Why (RI ch1 render v57, `data/novels/RI/panels/ch1/v57_round8/manifest.jsonl`): every named person got the same sentence
("a man with long black hair tied up in a topknot with a hairpin ... an adult face"), because `identity_lock` fills every gap
from a three-entry genre table and carries one lock per body, and a body only splits when two chapters state a change. So the
Gu Yue clan head, Fang Zhi and Fang Yuan were one face, and Fang Yuan wore the cliff's torn robes in the hall 500 years
earlier and after the rebirth, where block 83 says "his own young and soft, pale palms".

v1 of this module (docs/results/LOOK_BY_EPOCH.md, v1 column) decided age, build, condition, reset points and gender with
hand-written English word lists and regexes (one of them contained the phrase "young and soft", copied from RI block 83).
Owner 2026-11-27: "we cant simply do regex since it'll be different from author to author". v2 decides nothing with a
vocabulary. What replaces it:

1. Whole-novel facts first. The store's `state_of` attributes (appearance rows with an evidence quote) at this story time,
   from any chapter; a fact counts only when its evidence quote is found verbatim in the chapter it came from.
2. Per-scene model reads. The model returns each value with a verbatim quote and the block id. A value is kept only when
   (a) the quote is in that block after normalising case and whitespace, (b) the value shares its content words with the quote
   or a second model check says the quote states it, and (c) the quote is about THIS character: judged by the mention table
   (nearest preceding person mention in the block), else by a model that must choose the person from the people the store
   names in those blocks (so "a pair of clear eyes" in block 79, revealed as Fang Yuan in block 80, is not the clan head's).
3. Epoch boundaries from one chapter-level model question ("does the text state that a character's body changes?") whose
   quotes are verified, cut at scene windows: the scene-cut module's segments when its results exist, else break-shaped blocks.
4. Gaps filled from a per-novel slot bank (distinct people), the garment taken from one cached model read of the novel's
   setting, every invented value flagged with a reason.

Gender is the stored/owner value, else the repo's existing persona/gender path (`persona/gender.py`); no new pronoun rules.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
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
#: Bumped when a prompt or a check changes, so a stale cached read is never trusted.
READ_VERSION = "v2"

#: The closed set of age bands the compiler understands (`COMPILER_BAND`). A label set, not a cue vocabulary.
AGE_BANDS = ("child", "teen", "young adult", "adult", "middle-aged", "elderly", "ageless-ancient")
_FIELDS = ("hair_colour", "hair_style", "eyes", "build", "face", "skin", "clothes", "condition", "marks")

#: Reader/graph attribute keys -> this module's fields. `current_condition` is deliberately a key like the others; whether a
#: fact is transient is the store's own `TRANSIENT_KEYS`, not decided here.
_GRAPH_KEYS = {
    "hair_color": "hair_colour", "hair_style": "hair_style", "eye_color": "eyes", "height_build": "build",
    "skin_tone": "skin", "typical_attire": "clothes", "current_condition": "condition",
    "distinguishing_features": "marks",
}

#: Longest value (in words) each field may carry into an image prompt. A 7B model reading RI ch1 returned whole clauses
#: ("like deep pools of water in a well, so deep that ...") as an eye colour. A length cap, not a vocabulary.
_MAX_WORDS = {"hair_colour": 3, "hair_style": 7, "eyes": 4, "build": 5, "face": 7, "skin": 4, "clothes": 9,
              "condition": 11, "marks": 9}
#: Characters of text one read covers; a scene window is split into chunks of this size so one call sees one story time.
WINDOW_CHARS = 3600
CHAPTER_CHUNK_CHARS = 6500
_BREAK = re.compile(r"^[\W_]*$|^\s*(?:\*\s*){2,}$")  # a character-class shape (only punctuation), not a word list
_STOP = {"of", "the", "a", "an", "and"}


class LookFact(BaseModel):
    field: str
    value: str
    source_block: int | None = None
    invented: bool = False
    reason: str = ""
    #: The verbatim words (from the block) that state the value; empty for an invented value.
    quote: str = ""
    #: How the quote was tied to this character: "graph" (mention table), "model" (choice among the named people),
    #: "dossier" (a `state_of` attribute of this person), "".
    attribution: str = ""


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
# quotes
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    """Case, whitespace and punctuation folded, so a model's straight quotes match the text's curly ones."""
    return " ".join(re.findall(r"\w+", (text or "").casefold()))


def find_quote(block_text: str, quote: str) -> int | None:
    """Raw character offset of `quote` in `block_text` after normalising case, whitespace and punctuation, else None.

    A quote shorter than two words is not evidence (a single word is found in almost any block)."""
    nq = _norm(quote)
    if len(nq.split()) < 2:
        return None
    pieces = [(m.start(), m.group(0).casefold()) for m in re.finditer(r"\w+", block_text)]
    words = [w for _o, w in pieces]
    q = nq.split()
    for i in range(len(words) - len(q) + 1):
        if words[i:i + len(q)] == q:
            return pieces[i][0]
    return None


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{3,}", text.casefold())}


def _grounded(value: str, quote: str) -> bool:
    """Most of the value's content words are in the quote (a model fills fields from the genre when the text is silent)."""
    mine = _stems(value)
    if not mine:
        return False
    need = len(mine) if len(mine) <= 2 else -(-len(mine) * 2 // 3)
    return len(mine & _stems(quote)) >= need


def _clean(field_name: str, value: str) -> str:
    v = re.sub(r"\s+", " ", value or "").strip().strip(".,;")
    if not v or len(v.split()) > _MAX_WORDS.get(field_name, 9) or re.search(r"[;:]", v):
        return ""
    return v


# ---------------------------------------------------------------------------
# what the text says: schemas and prompts
# ---------------------------------------------------------------------------


class _ReadFact(BaseModel):
    field: str = ""
    value: str = ""
    block: int | None = None
    quote: str = ""


class WindowRead(BaseModel):
    """A model's reading of some blocks for one character. Everything here is re-checked before it is used."""

    present: bool = False
    age_band: str = ""
    age_block: int | None = None
    age_quote: str = ""
    facts: list[_ReadFact] = Field(default_factory=list)


class _Verdict(BaseModel):
    id: int = 0
    refers_to: str = ""
    states_value: bool = False


class Verdicts(BaseModel):
    items: list[_Verdict] = Field(default_factory=list)


class _Event(BaseModel):
    character: str = ""
    block: int | None = None
    quote: str = ""
    what: str = ""
    #: Which parts the change touches: any of age, body, clothes, hair, condition, everything.
    affects: list[str] = Field(default_factory=list)


class BodyChanges(BaseModel):
    events: list[_Event] = Field(default_factory=list)


class Setting(BaseModel):
    setting: str = ""
    male_garment: str = ""
    female_garment: str = ""
    #: Garment colours that are natural in this setting (invented clothes pick from these).
    colours: list[str] = Field(default_factory=list)


READ_SYSTEM = (
    "You read numbered blocks of a novel and report ONLY what the text states about how ONE named character looks. "
    "Return JSON: present (true if this character is in or described in these blocks), age_band, age_block, age_quote, and "
    "facts. age_band is one of child, teen, young adult, adult, middle-aged, elderly, ageless-ancient and only when the "
    "text states or plainly implies this character's age or age group (a number, a word for the person, a stated life "
    "span); otherwise empty. facts is a list of {field, value, block, quote} where field is one of hair_colour, hair_style, "
    "eyes, build, face, skin, clothes, condition, marks. quote is a SHORT passage (3 to 12 words) copied exactly from the "
    "block that states the value, and block is that block's number. clothes: the garment and colour as stated. build: "
    "body shape only. eyes: colour or shape in at most four words. condition: damage or state of the body or clothes "
    "(torn, bloodied, dishevelled). Keep every value to a short phrase taken from the quote. Only report things said about "
    "THIS character, never about someone next to them, and never guess from the genre or add what the text does not say."
)

VERIFY_SYSTEM = (
    "You check claims about how a novel's characters look. For each numbered claim you get a quote from the blocks. Return "
    "JSON {items: [{id, refers_to, states_value}]}. refers_to: the name, copied from the list of people, of the person the "
    "quote describes; a description with no name belongs to the person the story is about at that point, and a description "
    "whose owner is named in the next sentence or block belongs to that person; write unknown if you cannot tell. "
    "states_value: true only if the quote itself states that the value is that character's property of that kind."
)

EVENT_SYSTEM = (
    "You read numbered blocks of a novel. Does the text state that any character's body changes in these blocks? Cover age, "
    "rebirth or regression, transformation, injury, disguise, and clothing change. Return JSON {events: [...]}; for each "
    "one give character (the name used in the text), block (the block number), quote (a SHORT passage copied exactly from "
    "that block), what (what changed), and affects (any of: age, body, clothes, hair, condition, everything). Report only "
    "changes the text states; a state that simply holds (torn clothes that are described) is not a change. Return an empty "
    "list when there are none."
)

SETTING_SYSTEM = (
    "From the opening of a novel, name its setting in a few words (for example: xianxia sect robes; Victorian England "
    "day dress; modern Seoul streetwear) and give, for that setting, the everyday garment of an ordinary man and of an "
    "ordinary woman as a short drawable phrase without colour, plus up to six colours natural to it. Return JSON "
    "{setting, male_garment, female_garment, colours}."
)


# ---------------------------------------------------------------------------
# chapter evidence: names, presence, scene windows
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Window:
    first: int
    last: int
    present: list[int]


def surface_names(store: Any, novel_id: str, entity_id: str, chapter: float) -> list[str]:
    """Every string that names this entity in this chapter: label, aliases, and the unresolved title mentions that share a
    content word with the label (the clan head is `head of gu` in the graph and "Gu Yue clan head", "the clan head" in the
    prose, and those mentions carry no target id). All of it comes from the graph's own strings."""
    from echotales.core.enums import TargetKind

    ent = store.get_self(entity_id)
    names: list[str] = [ent.canonical_label] if ent is not None and ent.canonical_label else []
    with contextlib.suppress(Exception):  # an entity kind with no alias table row
        names += [a.alias for a in store.get_aliases_for(TargetKind.SELF, entity_id)]
    label_words = {w for n in names[:1] for w in re.findall(r"[a-z]+", n.casefold()) if w not in _STOP}
    if ent is not None and ":title:" in entity_id and label_words:
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
    # A title entity ("head of gu") is written in the prose as "the head of the Gu Yue clan": all its label words in one block.
    words = ({w for w in re.findall(r"[a-z]+", ent.canonical_label.casefold()) if w not in _STOP}
             if ent is not None and ":title:" in entity_id else set())
    for b in blocks:
        if any(p.search(b.text) for p in pats) or (words and words <= set(re.findall(r"[a-z]+", b.text.casefold()))):
            hits.add(b.index)
    for r in store.conn.execute(
        "SELECT block_index FROM mention WHERE novel_id=? AND chapter=? AND target_id=?", (novel_id, chapter, entity_id)
    ):
        hits.add(int(r["block_index"]))
    return sorted(hits)


def scene_cut_blocks(store: Any, novel_id: str, chapter: float, blocks: list[Any]) -> tuple[set[int], str]:
    """Blocks a scene starts at, and where they came from.

    The scene-cut module's saved analysis when it exists (it is optional: `echotales.pipeline.segment.scenes` lives on a
    branch that may not be merged); otherwise blocks that are only punctuation end a scene (RI ch1 blocks 4 and 30 are
    "……" and block 86 is "* * *", and the cliff / hall cut sits at 31)."""
    try:
        load_scene_cuts = importlib.import_module("echotales.pipeline.segment.scenes").load_scene_cuts
    except (ImportError, AttributeError):
        load_scene_cuts = None
    if load_scene_cuts is not None:
        with contextlib.suppress(Exception):
            analysis = load_scene_cuts(store, novel_id, chapter)
            if analysis is not None:
                return {int(c.block) for c in analysis.cuts}, "scene-cut module"
    order = [b.index for b in blocks]
    cuts: set[int] = set()
    for pos, b in enumerate(blocks):
        if _BREAK.match(b.text.strip() or ".") and pos + 1 < len(order):
            cuts.add(order[pos + 1])
    return cuts, "break-shaped blocks"


def _windows(blocks: list[Any], cuts: set[int], present: list[int]) -> list[_Window]:
    pset = set(present)
    out: list[_Window] = []
    cur: list[int] = []
    for b in blocks:
        if cur and b.index in cuts:
            out.append(_Window(cur[0], cur[-1], [i for i in cur if i in pset]))
            cur = []
        cur.append(b.index)
    if cur:
        out.append(_Window(cur[0], cur[-1], [i for i in cur if i in pset]))
    return out


def _chunks(near: list[int], blocks: dict[int, Any]) -> list[list[int]]:
    """Split the blocks one read shows into chunks of at most WINDOW_CHARS (a block is never cut)."""
    out: list[list[int]] = []
    cur: list[int] = []
    size = 0
    for i in near:
        n = len(blocks[i].text)
        if cur and size + n > WINDOW_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# attribution through the graph
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Ctx:
    store: Any
    client: Any
    novel_id: str
    entity_id: str
    chapter: float
    label: str
    names: list[str]
    blocks: dict[int, Any]
    #: block -> [(offset, target_id)] of mentions of PEOPLE, from the mention table, in reading order.
    mentions: dict[int, list[tuple[int, str]]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


def _load_mentions(store: Any, novel_id: str, chapter: float) -> tuple[dict[int, list[tuple[int, str]]], dict[str, str]]:
    by_block: dict[int, list[tuple[int, str]]] = {}
    labels: dict[str, str] = {}
    people: dict[str, bool] = {}
    for r in store.conn.execute(
        "SELECT block_index, offset, target_id FROM mention WHERE novel_id=? AND chapter=? AND target_id IS NOT NULL"
        " ORDER BY block_index, offset", (novel_id, chapter),
    ):
        tid = r["target_id"]
        if tid not in people:
            ent = store.get_self(tid)
            people[tid] = ent is not None and ent.kind.is_person
            if people[tid]:
                labels[tid] = ent.canonical_label
        if people[tid]:
            by_block.setdefault(int(r["block_index"]), []).append((int(r["offset"]), tid))
    return by_block, labels


def graph_attribution(ctx: _Ctx, block: int, offset: int) -> bool | None:
    """Does the person the mention table puts at `offset` of `block` equal this character?

    True/False when a person mention precedes the quote in its block (the nearest one is its subject: the structural form of
    coreference the table stores). None when the table says nothing there (no person mention before the quote), which sends
    the question to the model. Precision over recall: a different person named just before the quote refutes it."""
    prev = [tid for off, tid in ctx.mentions.get(block, []) if off <= offset]
    if not prev:
        return None
    return prev[-1] == ctx.entity_id


def _name_match(answer: str, names: list[str]) -> bool:
    a = {w for w in re.findall(r"\w+", answer.casefold()) if w not in _STOP}
    if not a:
        return False
    for n in names:
        t = {w for w in re.findall(r"\w+", n.casefold()) if w not in _STOP}
        if t and (a <= t or t <= a):
            return True
    return False


# ---------------------------------------------------------------------------
# reads, verified
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Fact:
    field: str
    value: str
    block: int
    quote: str
    attribution: str


@dataclass(slots=True)
class _Verified:
    facts: list[_Fact] = field(default_factory=list)
    age: tuple[str, int, str, str] | None = None  # band, block, quote, attribution


def _cached(store: Any, aid: str) -> Any | None:
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (aid,)).fetchone()
    return json.loads(row["payload_json"]) if row is not None else None


def _save(store: Any, aid: str, payload: Any) -> None:
    store.record_artifact(aid, TIER, [], "", json.dumps(payload))
    store.conn.commit()


def _ask(ctx_client: Any, prompt: str, schema: Any, system: str, novel_id: str, chapter: float) -> Any | None:
    from echotales.pipeline.llm.tasks import Task

    try:
        res = ctx_client.complete(Task.READER, prompt, schema, system=system, novel_id=novel_id, chapter=chapter)
    except Exception as exc:
        log.warning("look call failed (%s): %s", schema.__name__, exc)
        return None
    return res.value if isinstance(res.value, schema) else None


def _read_chunk(ctx: _Ctx, chunk: list[int]) -> _Verified | None:
    text = "\n".join(f"[{i}] {ctx.blocks[i].text}" for i in chunk)
    key = hashlib.md5(f"{READ_VERSION}|{ctx.label}|{text}".encode()).hexdigest()[:12]
    aid = f"look_read2:{ctx.entity_id}:{ctx.chapter:g}:{chunk[0]}-{chunk[-1]}:{key}"
    hit = _cached(ctx.store, aid)
    if hit is not None:
        return _Verified(
            facts=[_Fact(**f) for f in hit["facts"]], age=tuple(hit["age"]) if hit["age"] else None,  # type: ignore[arg-type]
        )
    if ctx.client is None:
        return None
    read = _ask(ctx.client, f"Character: {ctx.label}\nBlocks:\n{text}\n\nReturn only the JSON object.", WindowRead,
                READ_SYSTEM, ctx.novel_id, ctx.chapter)
    if read is None:
        return None
    claims: list[tuple[str, str, int, str, int]] = []  # field, value, block, quote, offset
    for f in read.facts:
        val = _clean(f.field, f.value)
        if f.field not in _FIELDS or not val or f.block not in chunk:
            continue
        off = find_quote(ctx.blocks[f.block].text, f.quote)
        if off is not None:
            claims.append((f.field, val, f.block, f.quote.strip(), off))
    if read.age_band in AGE_BANDS and read.age_block in chunk:
        off = find_quote(ctx.blocks[read.age_block].text, read.age_quote)
        if off is not None:
            claims.append(("age_band", read.age_band, read.age_block, read.age_quote.strip(), off))
    out = _Verified()
    if claims:
        verdicts = _verify(ctx, chunk, claims)
        for n, (fld, val, blk, quote, off) in enumerate(claims, 1):
            v = verdicts.get(n)
            if v is None or not v.states_value or (fld != "age_band" and not _grounded(val, quote)):
                continue
            graph = graph_attribution(ctx, blk, off)
            if graph is None:
                if not _name_match(v.refers_to, ctx.names):
                    continue
                how = "model"
            elif graph:
                how = "graph"
            else:
                continue
            if fld == "age_band":
                out.age = out.age or (val, blk, quote, how)
            else:
                out.facts.append(_Fact(fld, val, blk, quote, how))
    _save(ctx.store, aid, {"facts": [vars_of(f) for f in out.facts], "age": list(out.age) if out.age else None})
    return out


def vars_of(f: _Fact) -> dict[str, Any]:
    return {"field": f.field, "value": f.value, "block": f.block, "quote": f.quote, "attribution": f.attribution}


def _verify(ctx: _Ctx, chunk: list[int], claims: list[tuple[str, str, int, str, int]]) -> dict[int, _Verdict]:
    """One model call for the whole read: who each quote is about, and whether it states the value as that kind of fact."""
    shown = sorted({j for c in claims for j in (c[2] - 1, c[2], c[2] + 1) if j in ctx.blocks})
    people: list[str] = [ctx.label]
    for j in shown:
        for _off, tid in ctx.mentions.get(j, []):
            lab = ctx.labels.get(tid, "")
            if lab and lab not in people:
                people.append(lab)
    text = "\n".join(f"[{i}] {ctx.blocks[i].text}" for i in shown)
    lines = "\n".join(f'{n}. block {b}, {fld} = "{val}", quote: "{q}"' for n, (fld, val, b, q, _o) in enumerate(claims, 1))
    prompt = (f"People: {'; '.join(people)}; unknown\nBlocks:\n{text}\n\nClaims about {ctx.label}:\n{lines}\n\n"
              "Return only the JSON object.")
    res = _ask(ctx.client, prompt, Verdicts, VERIFY_SYSTEM, ctx.novel_id, ctx.chapter)
    return {v.id: v for v in res.items} if res is not None else {}


# ---------------------------------------------------------------------------
# body changes (epoch boundaries), the novel's setting, and the store's own facts
# ---------------------------------------------------------------------------


def body_change_events(store: Any, client: Any, novel_id: str, chapter: float, blocks_list: list[Any]) -> list[_Event]:
    """Verified statements that some character's body changes in this chapter: the quote must be in the block it cites."""
    blocks = {b.index: b for b in blocks_list}
    chunks: list[list[int]] = []
    cur: list[int] = []
    size = 0
    for b in blocks_list:
        if cur and size + len(b.text) > CHAPTER_CHUNK_CHARS:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(b.index)
        size += len(b.text)
    if cur:
        chunks.append(cur)
    out: list[_Event] = []
    for ch in chunks:
        text = "\n".join(f"[{i}] {blocks[i].text}" for i in ch)
        key = hashlib.md5(f"{READ_VERSION}|{text}".encode()).hexdigest()[:12]
        aid = f"look_events2:{novel_id}:{chapter:g}:{ch[0]}-{ch[-1]}:{key}"
        hit = _cached(store, aid)
        if hit is None:
            if client is None:
                continue
            res = _ask(client, f"Blocks:\n{text}\n\nReturn only the JSON object.", BodyChanges, EVENT_SYSTEM, novel_id, chapter)
            if res is None:
                continue
            hit = [e.model_dump() for e in res.events if e.block in ch and find_quote(blocks[e.block].text, e.quote) is not None]
            _save(store, aid, hit)
        out += [_Event(**e) for e in hit]
    return out


def novel_setting(store: Any, client: Any, novel_id: str) -> Setting | None:
    """One cached model read per novel of its setting and ordinary garments (never chosen from a genre flag)."""
    aid = f"look_setting:{novel_id}"
    hit = _cached(store, aid)
    if hit is not None:
        return Setting(**hit)
    if client is None:
        return None
    first = next((c for c in (store.get_chapter(novel_id, float(n)) for n in (1, 2, 3)) if c is not None), None)
    if first is None:
        return None
    sample = " ".join(b.text for b in first.blocks)[:3500]
    res = _ask(client, f"Opening of the novel:\n{sample}\n\nReturn only the JSON object.", Setting, SETTING_SYSTEM, novel_id,
               float(first.number))
    if res is None or not res.male_garment or not res.female_garment:
        return None
    _save(store, aid, res.model_dump())
    return res


def dossier_facts(store: Any, novel_id: str, entity_id: str, position: float, chapter: float, first: int, last: int,
                  nblocks: int) -> list[tuple[str, str, int | None, str]]:
    """The store's own quote-verified appearance facts for this person at this story time, from any ingested chapter.

    Read through `StateResolver.state_of` (story time `position`, the end of the novel as the knowledge point: how someone
    looked at that story time is a fact whenever it was learned, as for Bai Ning Bing who is only mentioned in RI ch1 and
    appears in person later). `(field, value, block_or_None, quote)`. A fact is kept only when its evidence quote is found
    verbatim in the chapter it was learned in. From the chapter being drawn, only evidence inside this epoch's blocks counts
    (the cliff's torn robes are not the reborn youth's), and the transient condition key never crosses chapters."""
    from echotales.core.enums import TargetKind
    from echotales.core.models import DiscoursePosition
    from echotales.core.state import StateResolver
    from echotales.pipeline.persona.split import persona_at
    from echotales.pipeline.resolve.appearance_extract import TRANSIENT_KEYS

    out: list[tuple[str, str, int | None, str]] = []
    try:
        pid = persona_at(store, entity_id, position)
        far = DiscoursePosition(chapter=10**6)
        have = StateResolver(store, novel_id).state_of(
            pid, target_kind=TargetKind.PERSONA, position=position, knowledge_pos=far).attributes
    except Exception as exc:
        log.debug("no dossier for %s: %s", entity_id, exc)
        return out
    rows = store.get_attributes(TargetKind.PERSONA, pid)
    for key, fld in _GRAPH_KEYS.items():
        value = have.get(key)
        if not value:
            continue
        cand = [a for a in rows if a.key == key and a.value == value and (a.evidence or "").strip()]
        if not cand:
            continue
        a = max(cand, key=lambda r: (r.interval.from_lb, r.learned_at_pos))
        src_chapter = float(a.learned_at_pos.chapter)
        if key in TRANSIENT_KEYS and src_chapter != chapter:
            continue
        chap = chapter if src_chapter == chapter else src_chapter
        ch = store.get_chapter(novel_id, chap)
        if ch is None:
            continue
        where = next((b.index for b in ch.blocks if find_quote(b.text, a.evidence) is not None), None)
        if where is None:
            continue
        if chap == chapter and not (first <= where <= last):
            continue
        val = _clean(fld, value)
        if val:
            out.append((fld, val, where if chap == chapter else None, a.evidence.strip()[:160]))
    return out


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
#: Invented hair and build keyed by the closed AGE_BANDS set; every use is flagged invented.
_AGED_HAIR = {"middle-aged": "{c} hair graying at the temples", "elderly": "white hair",
              "ageless-ancient": "{c} hair with a few silver strands"}
_YOUNG_BUILD = {"child": "a small child's frame", "teen": "a slim boyish build"}


def _bank() -> list[tuple[int, ...]]:
    combos = list(itertools.product(range(len(_HAIR_LEN_STYLE)), range(len(_HAIR_COLOURS)), range(len(_BUILDS)),
                                    range(len(_FACES)), range(len(_COLOURS))))
    random.Random(20261127).shuffle(combos)  # a fixed shuffle: the bank order never changes
    return combos


def _slot_for(store: Any, novel_id: str, entity_id: str) -> tuple[int, ...]:
    """The invented tuple of this entity: allocated once per novel, stored, and at least three of five dimensions away from
    every earlier allocation, so two people in one scene never share their invented hair, build and face."""
    aid = f"look_slots:{novel_id}"
    table: dict[str, list[int]] = _cached(store, aid) or {}
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
    _save(store, aid, table)
    return chosen


# ---------------------------------------------------------------------------
# epochs
# ---------------------------------------------------------------------------

#: field -> the body-change groups (the closed vocabulary EVENT_SYSTEM asks for) that stop it carrying into the next epoch.
_CARRY_BREAKS = {
    "hair_colour": {"age", "body", "hair"}, "hair_style": {"age", "body", "hair"}, "build": {"age", "body"},
    "face": {"age", "body"}, "skin": {"age", "body"}, "marks": {"age", "body"}, "eyes": set(), "clothes": {"clothes"},
}
_StatedField = tuple[str, int | None, str, str]  # value, block, quote, attribution


@dataclass(slots=True)
class _Epoch:
    first: int
    last: int
    age: tuple[str, int | None, str, str] | None = None
    fields: dict[str, _StatedField] = field(default_factory=dict)
    #: Groups of the body-change event that opened this epoch (empty for the first epoch).
    affects: set[str] = field(default_factory=set)


def _my_event(ctx: _Ctx, e: _Event) -> bool:
    if e.block not in ctx.blocks:
        return False
    if _name_match(e.character, ctx.names):
        return True
    off = find_quote(ctx.blocks[e.block].text, e.quote)
    return off is not None and graph_attribution(ctx, e.block, off) is True


def _merge_read(fields: dict[str, _StatedField], read: _Verified) -> None:
    for f in sorted(read.facts, key=lambda x: x.block):
        if f.field == "condition" and "condition" in fields:
            old = fields["condition"]
            if f.value.casefold() not in old[0].casefold():
                fields["condition"] = (f"{old[0]}, {f.value}", old[1], old[2], old[3])
        elif f.field not in fields:
            fields[f.field] = (f.value, f.block, f.quote, f.attribution)


def _build_epochs(store: Any, client: Any, novel_id: str, entity_id: str, chapter: float, blocks_list: list[Any]
                  ) -> tuple[list[_Epoch], str, bool, str]:
    """`(epochs, label, modelled, window_source)`; epochs cover only the scene windows the character is in."""
    blocks = {b.index: b for b in blocks_list}
    names = surface_names(store, novel_id, entity_id, chapter)
    label = names[0] if names else entity_id
    present = _present_blocks(store, novel_id, entity_id, chapter, blocks_list, names)
    cuts, source = scene_cut_blocks(store, novel_id, chapter, blocks_list)
    all_wins = _windows(blocks_list, cuts, present)
    wins = [w for w in all_wins if w.present]
    if not wins:
        return [], label, False, source
    mentions, labels = _load_mentions(store, novel_id, chapter)
    ctx = _Ctx(store, client, novel_id, entity_id, chapter, label, names, blocks, mentions, labels)
    mine = [e for e in body_change_events(store, client, novel_id, chapter, blocks_list) if _my_event(ctx, e)]
    cut_at: dict[int, set[str]] = {}
    for e in mine:
        w = next((x for x in all_wins if e.block is not None and x.first <= e.block <= x.last), None)
        if w is not None and w in wins:
            cut_at.setdefault(w.first, set()).update(a.casefold() for a in e.affects)
    modelled = False
    epochs: list[_Epoch] = []
    for w in wins:
        near = sorted({j for i in w.present for j in range(i - 2, i + 3) if w.first <= j <= w.last and j in blocks})
        fields: dict[str, _StatedField] = {}
        age: tuple[str, int | None, str, str] | None = None
        for chunk in _chunks(near, blocks):
            read = _read_chunk(ctx, chunk)
            modelled = modelled or read is not None
            if read is not None:
                _merge_read(fields, read)
                if read.age is not None and age is None:
                    age = read.age
        if epochs and w.first not in cut_at:
            ep = epochs[-1]
            ep.last = w.last
            for k, v in fields.items():
                if k not in ep.fields:
                    ep.fields[k] = v
            ep.age = ep.age or age
        else:
            epochs.append(_Epoch(w.first, w.last, age, fields, cut_at.get(w.first, set())))
    for ep in epochs:
        pos = chapter + ep.first / max(len(blocks_list), 1)
        for fld, val, blk, quote in dossier_facts(store, novel_id, entity_id, pos, chapter, ep.first, ep.last, len(blocks_list)):
            ep.fields[fld] = (val, blk, quote, "dossier")
    for prev, ep in itertools.pairwise(epochs):
        everything = not ep.affects or "everything" in ep.affects
        for k, v in prev.fields.items():
            if k not in ep.fields and k != "condition" and not everything and not (_CARRY_BREAKS.get(k, set()) & ep.affects):
                ep.fields[k] = v
        if ep.age is None and not everything and "age" not in ep.affects:
            ep.age = prev.age
    return epochs, label, modelled, source


# ---------------------------------------------------------------------------
# turning an epoch into a Look
# ---------------------------------------------------------------------------


def _gender_of(store: Any, novel_id: str, entity_id: str) -> tuple[str | None, str]:
    """The stored or owner value, else the repo's persona/gender path (own-pronoun votes, then the first-name prior).

    No pronoun counting here: v1's counts were a second, weaker copy of `persona/gender.py`."""
    from echotales.pipeline.persona.gender import _current_gender, gender_lean_basis

    with contextlib.suppress(Exception):
        value, _human = _current_gender(store, entity_id)
        if value in ("male", "female"):
            return value, "graph"
        side, basis = gender_lean_basis(store, novel_id, {entity_id}).get(entity_id, (None, ""))
        if side in ("male", "female"):
            return side, basis
    return None, ""


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else "".join(parts)


def _make_look(store: Any, novel_id: str, entity_id: str, chapter: float, n: int, e: _Epoch, gender: str | None,
               all_clothes: list[str], setting: Setting | None) -> Look:
    slot = _slot_for(store, novel_id, entity_id)
    facts: list[LookFact] = []

    def stated(name: str) -> str:
        v = e.fields.get(name)
        if v:
            facts.append(LookFact(field=name, value=v[0], source_block=v[1], quote=v[2], attribution=v[3]))
            return v[0]
        return ""

    def invent(name: str, value: str, reason: str) -> str:
        facts.append(LookFact(field=name, value=value, invented=True, reason=reason))
        return value

    if e.age is not None:
        band = e.age[0]
        facts.append(LookFact(field="age_band", value=band, source_block=e.age[1], quote=e.age[2], attribution=e.age[3]))
    else:
        band = invent("age_band", "adult", "no quote in this stretch of the text supports an age")
    if gender:
        facts.append(LookFact(field="gender", value=gender, reason="stored/owner value or the persona gender path"))

    colour = stated("hair_colour")
    style = stated("hair_style")
    if not colour and not style:
        base = _AGED_HAIR.get(band)
        if base:
            hair = invent("hair", f"{base.format(c=_HAIR_COLOURS[slot[1]])}, {_HAIR_LEN_STYLE[slot[0]]}",
                          f"age band {band} and the person's own slot; the text states no hair")
        else:
            hair = invent("hair", f"{_HAIR_COLOURS[slot[1]]} hair, {_HAIR_LEN_STYLE[slot[0]]}",
                          "the text states no hair; chosen per person from the slot bank")
    elif colour and not style:
        hair = (f"{colour} hair" if "hair" not in colour.casefold() else colour) + ", " + invent(
            "hair_style", _HAIR_LEN_STYLE[slot[0]], "colour stated, length and style not")
    else:
        if not colour:
            colour = _HAIR_COLOURS[slot[1]]
            facts.append(LookFact(field="hair_colour", value=colour, invented=True, reason="style stated, colour not"))
        hair = f"{colour} {style}" if "hair" in style.casefold() else f"{colour} hair, {style}"
    eyes = stated("eyes")
    eyes = f"{eyes} eyes" if eyes and "eye" not in eyes.casefold() else eyes
    build = stated("build")
    if build and not build.startswith(("a ", "an ")):
        build = f"a {build} build" if " " not in build else f"a {build}"
    if not build:
        build = invent("build", _YOUNG_BUILD.get(band, _BUILDS[slot[2]]), "the text states no build")
    face = stated("face") or invent("face", _FACES[slot[3]], "the text states no face; chosen per person")
    skin = stated("skin")
    marks = stated("marks")
    clothes = stated("clothes")
    if not clothes:
        pool = setting.colours if setting and setting.colours else list(_COLOURS)
        others = {s for c in all_clothes for s in _stems(c)}
        free = [c for c in pool if not (_stems(c) & others)] or pool
        garment = ((setting.female_garment if gender == "female" else setting.male_garment) if setting
                   else "plain everyday clothes")
        why = ("the text states no clothes here" + ("; another epoch's stated clothes are not carried" if all_clothes else "")
               + (f"; garment from the novel's setting read ({setting.setting})" if setting else "; no setting read yet"))
        clothes = invent("clothes", f"a {free[slot[4] % len(free)]} {garment}", why)
    condition = stated("condition")
    bits = [hair, eyes, build, face, skin and f"{skin} skin"]
    desc = _join([b for b in bits if b]) + f", wearing {clothes}"
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
    aid = f"look_epochs2:{entity_id}:{chapter:g}"
    hit = _cached(store, aid)
    if hit is not None:
        return [Look(**d) for d in hit]
    chap = store.get_chapter(novel_id, chapter)
    if chap is None:
        return []
    epochs, _label, modelled, _src = _build_epochs(store, client, novel_id, entity_id, chapter, chap.blocks)
    if not epochs:
        return []
    setting = novel_setting(store, client, novel_id)
    gender, _why = _gender_of(store, novel_id, entity_id)
    looks: list[Look] = []
    for n, e in enumerate(epochs):
        others = [x.fields["clothes"][0] for x in epochs if x is not e and "clothes" in x.fields]
        looks.append(_make_look(store, novel_id, entity_id, chapter, n, e, gender, others, setting))
    # The first and last epoch stretch to the chapter's ends; an epoch begins at the scene window its change was stated in
    # (RI blocks 31-86, the hall 500 years earlier, are a new stretch of story, not the cliff's continuation).
    looks[0].block_from = 0
    for a, b in itertools.pairwise(looks):
        a.block_to = b.block_from - 1
    looks[-1].block_to = max(b.index for b in chap.blocks)
    if modelled and setting is not None:  # a look built without a model read is a fallback, not a result to cache
        _save(store, aid, [lk.model_dump() for lk in looks])
    return looks


def look_at(store: Any, novel_id: str, entity_id: str, *, chapter: float, block: int, client: Any = None) -> Look:
    """How `entity_id` looks at `block` of `chapter`.

    A block between two epochs the character is in takes the nearer one (the earlier on a tie). An entity the chapter never
    describes gets a single invented look, flagged as such, so a caller is never handed nothing."""
    looks = looks_for_chapter(store, novel_id, entity_id, chapter, client=client)
    if not looks:
        ent = store.get_self(entity_id)
        gender, _ = _gender_of(store, novel_id, entity_id)
        setting = novel_setting(store, client, novel_id)
        look = _make_look(store, novel_id, entity_id, chapter, 0, _Epoch(0, 0), gender, [], setting)
        look.epoch_label = f"{look.age_band}, not described in chapter {chapter:g}" if ent else look.epoch_label
        return look
    for lk in looks:
        if lk.block_from <= block <= lk.block_to:
            return lk
    return min(looks, key=lambda lk: min(abs(block - lk.block_from), abs(block - lk.block_to)))




# ---------------------------------------------------------------------------
# bridge to the prompt path
# ---------------------------------------------------------------------------

#: Look age band -> the compiler's age_band vocabulary (`render/compiler.py::_identity_head`).
COMPILER_BAND = {
    "child": "child", "teen": "teen", "young adult": "adult", "adult": "adult", "middle-aged": "middle-aged",
    "elderly": "elder", "ageless-ancient": "elder",
}
# v1 mapped middle-aged and ageless-ancient to "adult", the one band `_identity_head` leaves unwritten, so the clan head's stated
# middle age and the cliff Fang Yuan's centuries never reached the prompt; the owner calls the 500-year-old of RI block 29 old.


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
