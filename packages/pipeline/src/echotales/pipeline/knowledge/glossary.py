"""The world glossary, learned per novel from its own text.

No term list is written by hand. Candidates are noun phrases that recur across many chapters and are rare in other
novels (a contrast corpus supplies "rare elsewhere" without any English word list); a model then keeps the ones that are
world terms (titles, roles, institutions, practices, system terms) and drafts each entry from up to 12 usage sentences
spread over the volume. Every claim is tagged `text` (with a quote that must occur in the gathered contexts) or
`general_knowledge` (the model's prior, flagged): the owner's rule is that "elder" means what this book's text makes it
mean, and only falls back on a prior when the text is silent.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from echotales.core.store import Store
from echotales.pipeline.knowledge.common import (
    artifact_id,
    get_artifact,
    model_id_of,
    norm,
    put_artifact,
    quote_in,
)
from echotales.pipeline.llm.tasks import Task
from pydantic import BaseModel, Field

FIELDS = ("definition", "holder_age", "holder_appearance", "holder_dress", "relation", "other")
_SENT = re.compile(r"(?<=[.!?”\"])\s+")
_WORD = re.compile(r"[a-z][a-z'-]+")


class KeepItem(BaseModel):
    term: str
    category: str = ""


class KeepOut(BaseModel):
    terms: list[KeepItem] = Field(default_factory=list)


class Claim(BaseModel):
    field: str = "other"
    text: str
    source: str = "general_knowledge"
    quote: str = ""


class Related(BaseModel):
    term: str
    relation: str = ""


class TermOut(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    related: list[Related] = Field(default_factory=list)


def _story_texts(store: Store, novel_id: str, limit: int) -> list[tuple[float, str]]:
    numbers = store.chapter_numbers(novel_id)
    if len(numbers) > limit:
        step = len(numbers) / limit
        numbers = [numbers[int(i * step)] for i in range(limit)]
    out = []
    for n in numbers:
        ch = store.get_chapter(novel_id, n)
        if ch is not None:
            out.append((n, ch.story_text))
    return out


def _ngram_df(texts: Sequence[str], max_n: int = 3) -> Counter[str]:
    """Number of documents each 1-3 word sequence occurs in."""
    df: Counter[str] = Counter()
    for text in texts:
        words = _WORD.findall(text.lower())
        seen: set[str] = set()
        for n in range(1, max_n + 1):
            seen.update(" ".join(words[i:i + n]) for i in range(len(words) - n + 1))
        df.update(seen)
    return df


def contrast_df(other_dbs: Sequence[str], per_novel: int = 40) -> tuple[Counter[str], int]:
    """Document frequencies over chapters of other novels: what is ordinary English prose rather than this book's world."""
    total = Counter[str]()
    docs = 0
    for path in other_dbs:
        with Store(path) as other:
            for nov in other.list_novels():
                texts = [t for _n, t in _story_texts(other, nov["id"], per_novel)]
                total.update(_ngram_df(texts))
                docs += len(texts)
    return total, docs


def candidates(
    store: Store, novel_id: str, other_dbs: Sequence[str] = (), *, max_chapters: int = 150, top: int = 80,
) -> list[dict[str, Any]]:
    """Recurring noun phrases ranked by spread across chapters times rarity elsewhere."""
    import spacy

    nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    nlp.max_length = 3_000_000
    texts = _story_texts(store, novel_id, max_chapters)
    # Person names are excluded by their words, learned from the book's own resolved people (no list).
    name_words = {w for e in store.all_selves(novel_id) if e.kind.is_person for w in _WORD.findall(e.canonical_label.lower())}
    chapters_of: dict[str, set[float]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for (number, _text), doc in zip(texts, nlp.pipe([t for _n, t in texts], batch_size=4), strict=True):
        for chunk in doc.noun_chunks:
            toks = [t for t in chunk if t.pos_ in ("NOUN", "PROPN", "ADJ") and t.is_alpha and not t.is_stop]
            if not toks or toks[-1].pos_ not in ("NOUN", "PROPN") or len(toks) > 3:
                continue
            phrase = " ".join(t.text.lower() for t in toks)
            if all(w in name_words for w in phrase.split()) or len(phrase) < 3:
                continue
            counts[phrase] += 1
            chapters_of[phrase].add(number)
    other_df, other_docs = contrast_df(other_dbs) if other_dbs else (Counter(), 0)
    n_docs = max(len(texts), 1)
    floor = max(5, int(0.03 * n_docs))
    scored = []
    for phrase, n in counts.items():
        spread = len(chapters_of[phrase])
        if spread < floor:
            continue
        elsewhere = other_df.get(phrase, 0) / other_docs if other_docs else 0.0
        score = (spread / n_docs) / (elsewhere + 0.03) * math.log1p(n)
        scored.append({"term": phrase, "count": n, "chapters": spread, "elsewhere": round(elsewhere, 3), "score": score})
    scored.sort(key=lambda r: -r["score"])
    return scored[:top]


def contexts_for(store: Store, novel_id: str, term: str, k: int = 12) -> list[dict[str, Any]]:
    """Up to `k` sentences using the term, one per chosen chapter, evenly spread over the chapters that use it."""
    rx = re.compile(r"\b" + re.escape(term) + r"s?\b", re.IGNORECASE)
    hits: list[tuple[float, str]] = []
    for n in store.chapter_numbers(novel_id):
        ch = store.get_chapter(novel_id, n)
        if ch is None or not rx.search(ch.story_text):
            continue
        for block in ch.blocks:
            m = rx.search(block.text)
            if m:
                sent = next((s for s in _SENT.split(block.text) if rx.search(s)), block.text)
                hits.append((n, sent.strip()[:300]))
                break
    if len(hits) > k:
        step = len(hits) / k
        hits = [hits[int(i * step)] for i in range(k)]
    return [{"chapter": n, "text": t} for n, t in hits]


def _keep_prompt(batch: list[dict[str, Any]], ctx: dict[str, str]) -> str:
    lines = "\n".join(f'- "{r["term"]}" ({r["chapters"]} chapters). Example: {ctx.get(r["term"], "")}' for r in batch)
    return (
        "These phrases recur in one novel. Keep only the ones that are terms of its fictional world a reader must learn: "
        "titles, ranks, roles, institutions, factions, practices or customs, power-system or cultivation terms, special "
        "substances or beings. Drop ordinary words (body parts, times, generic objects, abstract nouns) and personal names.\n"
        f"{lines}\n\n"
        'Answer {"terms": [{"term": "<phrase exactly as listed>", "category": "title|role|institution|practice|system|item|being"}]}.'
    )


def _term_prompt(term: str, ctx: list[dict[str, Any]]) -> str:
    lines = "\n".join(f'[ch{c["chapter"]:g}] {c["text"]}' for c in ctx)
    return (
        f'Write a glossary entry for "{term}" in this novel, from these usage sentences:\n{lines}\n\n'
        f"Each claim has field (one of {', '.join(FIELDS)}), text (one short sentence), source and quote. "
        "source is \"text\" when the sentences above show it (then quote is copied EXACTLY from one sentence, at most 10 words) "
        "and \"general_knowledge\" when it is only your prior knowledge of such terms (then quote is empty). "
        "Include: definition; holder_age (typical age of people who hold or are called this, if implied); "
        "holder_appearance and holder_dress (only if implied); relation claims naming related terms. "
        'related lists other terms: {"term": ..., "relation": "above|below|part_of|opposes|requires|..."}.\n'
        "Do not state as text what the sentences do not show."
    )


def build_glossary(
    store: Store, client: Any, novel_id: str, other_dbs: Sequence[str] = (), *, keep: int = 40, say: Any = print,
) -> dict[str, Any]:
    cands = candidates(store, novel_id, other_dbs)
    say(f"glossary: {len(cands)} candidates")
    first: dict[str, str] = {}
    for r in cands:
        ctx = contexts_for(store, novel_id, r["term"], 1)
        first[r["term"]] = ctx[0]["text"][:160] if ctx else ""
    kept: dict[str, str] = {}
    for i in range(0, len(cands), 20):
        out = client.complete(Task.READER, _keep_prompt(cands[i:i + 20], first), KeepOut, novel_id=novel_id, max_tokens=900).value
        listed = {r["term"] for r in cands[i:i + 20]}
        for item in out.terms:
            if item.term.lower().strip() in listed:
                kept[item.term.lower().strip()] = item.category
    stats = {r["term"]: r for r in cands}
    terms = []
    for term in sorted(kept, key=lambda t: -stats[t]["chapters"])[:keep]:
        ctx = contexts_for(store, novel_id, term, 12)
        out = client.complete(Task.READER, _term_prompt(term, ctx), TermOut, novel_id=novel_id, max_tokens=1200).value
        claims, demoted = [], 0
        for c in out.claims:
            src = "text" if c.source == "text" else "general_knowledge"
            if src == "text" and not any(quote_in(c.quote, x["text"]) for x in ctx):
                src, demoted = "general_knowledge", demoted + 1  # a text claim whose quote is not in the sentences is a prior
            field = c.field if c.field in FIELDS else "other"
            claims.append({"field": field, "text": c.text.strip(), "source": src, "quote": c.quote.strip() if src == "text" else ""})
        terms.append({
            "term": term, "category": kept[term], "count": stats[term]["count"], "chapters": stats[term]["chapters"],
            "contexts": ctx, "claims": claims, "related": [r.model_dump() for r in out.related], "demoted_claims": demoted,
        })
        say(f"glossary: {term} ({len(claims)} claims)")
    payload = {"novel_id": novel_id, "model": model_id_of(client), "candidates": len(cands), "terms": terms}
    put_artifact(store, artifact_id("glossary", novel_id), payload)
    return payload


def load_glossary(store: Store, novel_id: str) -> dict[str, Any] | None:
    return get_artifact(store, artifact_id("glossary", novel_id))


def entry(store: Store, novel_id: str, term: str) -> dict[str, Any] | None:
    g = load_glossary(store, novel_id)
    return next((t for t in (g or {}).get("terms", []) if norm(t["term"]) == norm(term)), None)
