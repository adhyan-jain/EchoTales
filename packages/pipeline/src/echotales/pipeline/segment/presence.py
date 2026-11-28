"""Who is physically in a scene, as opposed to merely talked about.

Why this exists (docs/results/MANHWA_DIRECTING_PATTERNS.md, grammar rule 4 and
the RI ch1 scorecard): v57 drew Fang Yuan in the clan-head's ritual because his
name is all over blocks 31-79. The elders are discussing him; he is not in the
room. The reader's mention roles cannot separate the two: RI block 58 carries a
PRESENT mention of "Gu Yue Fang Yuan" in narration about an absent boy. Only a
reader of the scene can, so the decision is a small-model classification per
(entity, segment), batched into one call and cached, with the one hard signal
the pipeline already has, a speaker attribution, short-circuiting it.

`present_cast` is a contract other stages depend on; keep its signature.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from echotales.core.enums import SpanType
from echotales.core.models import Mention
from echotales.core.store import Store
from echotales.pipeline.llm import LLMRequest
from pydantic import BaseModel, Field

#: Entity kinds that can stand in a room. Items, places and organisations are
#: never "present" in the sense a panel needs (an organisation's members are).
_NOT_PEOPLE_LABELS = {"item", "location", "organization", "category"}

_CACHE_PREFIX = "presence"


@lru_cache(maxsize=1)
def _parser() -> Any | None:
    """spaCy with the dependency parser, or None when the model is absent (callers keep the older heuristic)."""
    try:
        import spacy

        return spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    except Exception:
        return None


def _is_subject_at(text: str, offset: int, length: int = 1) -> bool | None:
    """Whether the name at `offset` is the grammatical subject of its clause; None when no parser is available.

    RI ch1 block 58: "the elders were discussing about the youth known as Gu Yue Fang Yuan" is narration, and the
    reader tagged Fang Yuan PRESENT there, but he is the object of the elders' talk. A person on stage acts, so
    a narration mention counts toward presence only when the name is a subject; objects, possessives and
    appositives ("Fang Zhi's bloodline") are references. This is a syntactic test, not a word list.
    """
    nlp = _parser()
    if nlp is None:
        return None
    doc = nlp(text)
    span = [t for t in doc if t.idx < offset + max(length, 1) and t.idx + len(t.text) > offset]
    if not span:
        return None
    inside = {t.i for t in span}
    # The mention's own syntactic head: the token whose head lies outside the mention ("the clan head" -> head).
    root = next((t for t in span if t.head.i not in inside or t.head is t), span[-1])
    if root.dep_ not in ("nsubj", "nsubjpass"):
        return False
    # A subject inside a complement clause ("it so happens that X was the best") is the content of someone's
    # statement or thought, not an action on stage.
    verb = root.head
    return verb.dep_ not in ("ccomp", "csubj", "csubjpass")
#: The segment text sent to the model is clipped so the prompt fits an 8k context on an 8 GB card.
_MAX_SEGMENT_CHARS = 7000


@dataclass(slots=True)
class Candidate:
    entity_id: str  # a SELF id, or "unresolved:<surface>" for a name the resolver has not bound
    label: str
    blocks: list[int] = field(default_factory=list)
    speaks: bool = False
    #: Blocks where a speaker attribution names this entity, and blocks where the reader marked the same entity
    #: as talked about; `speaks` is only trusted for a speaker block that is not also a talked-about block.
    speaker_blocks: set[int] = field(default_factory=set)
    reference_blocks: set[int] = field(default_factory=set)
    narration_present_mentions: int = 0
    #: Narration mentions where the name is the clause subject; None-parser runs count every narration mention.
    acting_mentions: int = 0
    talked_about_mentions: int = 0
    snippets: list[str] = field(default_factory=list)


class Verdict(BaseModel):
    candidate: int = Field(description="the candidate number")
    present: bool = Field(description="true only if physically in the scene's place during these blocks")
    quote: str = Field(default="", description="exact words from the scene showing this person acting or speaking there")


class PresenceResponse(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


_SYSTEM = (
    "You read one scene of a novel and decide who is physically there. A person is PRESENT if they speak in the "
    "scene, act in it, or are described as being in the place. A person is NOT present if they are only talked "
    "about, remembered, imagined, quoted, or named in someone's thoughts, even when the narration is about them. "
    "A person overheard from another room or place is not present."
)


def _norm_surface(text: str) -> str:
    t = re.sub(r"^(?:the|a|an)\s+", "", text.strip().lower())
    return re.sub(r"\s+", " ", t)


def _is_person_mention(m: Mention, person_ids: dict[str, bool]) -> bool:
    label = (m.entity_label or "").lower()
    if label in _NOT_PEOPLE_LABELS:
        return False
    return not (m.target_id and not person_ids.get(m.target_id, True))


def collect_candidates(
    store: Store, novel_id: str, chapter: float, block_from: int, block_to: int
) -> tuple[list[Candidate], dict[int, str]]:
    """People mentioned or speaking in the block range, with the evidence the reader already produced."""
    chapter_obj = store.get_chapter(novel_id, chapter)
    texts = {b.index: b.text for b in chapter_obj.blocks} if chapter_obj else {}
    labels = {s.id: s.canonical_label for s in store.all_selves(novel_id)}
    kinds = {s.id: s.kind.is_person for s in store.all_selves(novel_id)}
    by_id: dict[str, Candidate] = {}

    def cand(eid: str, label: str) -> Candidate:
        return by_id.setdefault(eid, Candidate(entity_id=eid, label=label))

    for m in store.get_mentions(novel_id, chapter):
        if not (block_from <= m.block_index <= block_to) or not _is_person_mention(m, kinds):
            continue
        if m.target_id:
            c = cand(m.target_id, labels.get(m.target_id, m.text))
        else:
            surface = _norm_surface(m.text)
            if not surface or len(surface) < 3:
                continue
            c = cand(f"unresolved:{surface}", m.text)
        c.blocks.append(m.block_index)
        # DIALOGUE_REFERENCE and INNER_THOUGHT_REFERENCE are, by definition, someone else's words or thoughts.
        if m.reference_mode.value in ("DIALOGUE_REFERENCE", "INNER_THOUGHT_REFERENCE"):
            c.talked_about_mentions += 1
            c.reference_blocks.add(m.block_index)
        elif m.span_type in (SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION):
            c.narration_present_mentions += 1
            acts = _is_subject_at(texts.get(m.block_index, ""), m.offset, len(m.text))
            if acts is None or acts:
                c.acting_mentions += 1
        text = texts.get(m.block_index, "")
        if len(c.snippets) < 2 and text:
            s = max(0, m.offset - 60)
            c.snippets.append(" ".join(text[s : m.offset + 100].split()))
    for sp in store.get_spans(novel_id, chapter):
        if not (block_from <= sp.block_index <= block_to and sp.speaker_self_id and sp.span_type == SpanType.DIALOGUE):
            continue
        # Speaker ids that are neither a known entity nor a numbered anonymous slot are bare labels the
        # attribution pass emitted ("Audrey", "Audrey's" in LotM ch8); they would double-count the real id.
        if sp.speaker_self_id in labels or ":anon:" in sp.speaker_self_id:
            cand(sp.speaker_self_id, labels.get(sp.speaker_self_id, "unnamed speaker")).speaker_blocks.add(
                sp.block_index
            )
    for c in by_id.values():
        # RI ch1 block 55: an elder says "Fang Zhi's side has appeared a young genius" and the attribution pass
        # named Fang Zhi as the speaker, so he was marked present in the clan head's ritual (31-79) though he
        # is only talked about. The reader's own DIALOGUE_REFERENCE mention of the same entity in the same
        # block contradicts that attribution, so it no longer short-circuits the scene reading.
        c.speaks = bool(c.speaker_blocks - c.reference_blocks)
    return list(by_id.values()), texts


def _digest(candidates: list[Candidate], text: str, quoted: bool = False) -> str:
    key = json.dumps([[c.entity_id, c.speaks] for c in candidates], sort_keys=True) + text + ("|q1" if quoted else "")
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _cache_get(store: Store, art_id: str) -> dict[str, bool] | None:
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (art_id,)).fetchone()
    return json.loads(row[0]) if row else None


def _cache_put(store: Store, art_id: str, payload: dict[str, bool]) -> None:
    # Empty read set: identity merges must not invalidate a decision about a scene's text.
    store.conn.execute(
        "INSERT OR REPLACE INTO derived_artifact (id, tier, read_set_json, read_set_hash, payload_json, invalidated)"
        " VALUES (?, 'presence', '[]', '', ?, 0)",
        (art_id, json.dumps(payload)),
    )
    store.conn.commit()


def _heuristic(c: Candidate) -> bool:
    """Reader-signal fallback: speaking, or named in narration and never quoted as talked-about."""
    if c.speaks:
        return True
    return c.acting_mentions * 2 > c.narration_present_mentions and c.acting_mentions > 0 and c.talked_about_mentions == 0


def present_cast(
    store: Store,
    novel_id: str,
    chapter: float,
    block_from: int,
    block_to: int,
    *,
    llm: Any | None = None,
    require_quote: bool = False,
) -> tuple[list[str], list[str]]:
    """(physically present entity ids, referenced-only entity ids) for blocks `block_from..block_to`.

    Without `llm` the answer comes from reader signals alone (speaker
    attributions and mention roles), which over-counts people named in
    narration. With `llm` the non-speakers are classified by reading the
    scene; the verdict is cached per (scene text, candidates).

    `require_quote` (segment v3): a model "present" counts only with a quote that exists in the scene, in a block
    that mentions the person or whose words name them. RI ch1 31-78 listed Fang Yuan as present on a bare yes
    although the elders only discuss him; a quote that must show him acting or speaking cannot be invented
    from nothing, and a failed check puts the person in the referenced list.
    """
    candidates, texts = collect_candidates(store, novel_id, chapter, block_from, block_to)
    if not candidates:
        return [], []
    verdict: dict[str, bool] = {c.entity_id: _heuristic(c) for c in candidates}
    to_ask = [c for c in candidates if not c.speaks]
    if llm is not None and to_ask:
        scene = "\n".join(f"[{i}] {texts[i]}" for i in range(block_from, block_to + 1) if i in texts)[:_MAX_SEGMENT_CHARS]
        art_id = f"{_CACHE_PREFIX}:{novel_id}:{chapter:g}:{block_from}-{block_to}:{_digest(to_ask, scene, require_quote)}"
        cached = _cache_get(store, art_id)
        if cached is None:
            cached = _classify(llm, scene, to_ask, texts if require_quote else None, block_from, block_to)
            if cached:
                _cache_put(store, art_id, cached)
        for c in to_ask:
            if c.entity_id in cached:
                verdict[c.entity_id] = cached[c.entity_id]
    present = [c.entity_id for c in candidates if verdict[c.entity_id]]
    referenced = [c.entity_id for c in candidates if not verdict[c.entity_id]]
    return present, referenced


def _quote_checks(c: Candidate, quote: str, texts: dict[int, str], lo: int, hi: int) -> bool:
    """The quote is a real stretch of one of the scene's blocks and that block is about this person."""
    from echotales.pipeline.segment.storytime import quote_in

    name_tokens = {t for t in re.findall(r"[a-z]+", c.label.lower()) if len(t) > 2}
    for i in range(lo, hi + 1):
        if i in texts and quote_in(texts[i], quote):
            return i in c.blocks or bool(name_tokens & set(re.findall(r"[a-z]+", quote.lower())))
    return False


def _classify(
    llm: Any,
    scene: str,
    to_ask: list[Candidate],
    texts: dict[int, str] | None = None,
    lo: int = 0,
    hi: int = 0,
) -> dict[str, bool]:
    lines = []
    for i, c in enumerate(to_ask, start=1):
        sn = " | ".join(c.snippets)
        lines.append(f"{i}. {c.label}" + (f"  (e.g. {sn})" if sn else ""))
    prompt = (
        f"SCENE (block numbers in brackets):\n{scene}\n\nCANDIDATES:\n" + "\n".join(lines)
        + "\n\nFor each candidate number, is that person physically present in this scene?"
        + (" If yes, copy in `quote` the exact words from the scene that show them acting or speaking there." if texts is not None else "")
    )
    try:
        res = llm.complete(
            LLMRequest(stage="scene_presence", prompt=prompt, system=_SYSTEM, max_tokens=400), PresenceResponse
        )
    except Exception:
        return {}
    out: dict[str, bool] = {}
    for v in res.value.verdicts:
        if 1 <= v.candidate <= len(to_ask):
            c = to_ask[v.candidate - 1]
            out[c.entity_id] = v.present and (texts is None or _quote_checks(c, v.quote, texts, lo, hi))
    return out
