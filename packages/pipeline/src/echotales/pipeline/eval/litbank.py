"""LitBank coreference as an external, human-annotated check (EVOLUTION 4.91).

Every accuracy number in this project was scored against an LLM-drafted silver
set. LitBank (Bamman, Lewke & Mansoor, LREC 2020; CC BY 4.0) is the nearest
public, human-annotated literary coreference corpus: about 2,000 words from
each of 100 English novels. This module turns one LitBank document into an
EchoTales single-chapter "novel", runs the ordinary pipeline stages over it,
and scores the result against the human key.

Format facts this relies on, read from the corpus itself:
  - `coref/brat/<doc>_brat.txt` is the tokenised text (tokens separated by
    whitespace, one sentence per line); `.ann` lines give mention spans and a
    type such as PROP_PER, NOM_PER, PRON_PER over that text.
  - `coref/conll/<doc>_brat.conll` lists the same tokens in order, with the
    cluster brackets in the last column: "(3", "3)", "(0)", "(2|(5".
  So token i of the conll file is the i-th whitespace-delimited token of the
  .txt, which is how cluster spans get character offsets.

Two ways of scoring are reported, because they answer different questions:
  key-restricted  the house scorer's convention (`coref_score.score_all`):
                  system mentions that do not match a key mention are ignored.
                  Comparable to every other number in this repository.
  standard        every system person mention is scored; a spurious one costs
                  precision, as in the CoNLL-2012 scorer. Only this mode is
                  anywhere near comparable to published LitBank results, and
                  even it differs in mention detection (see EXTERNAL_BENCHMARK).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import MetricScore, b_cubed, ceafe, conll_f1, muc

Span = tuple[str, int, int]  # (doc, start, end)


@dataclass(frozen=True, slots=True)
class KeyMention:
    start: int
    end: int
    surface: str
    cluster: str
    mention_type: str  # PROP / NOM / PRON / "" when the .ann has no exact match
    entity_type: str   # PER / LOC / ... / ""


def _token_offsets(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]


def parse_document(txt_path: Path, conll_path: Path, ann_path: Path) -> tuple[str, list[KeyMention]]:
    """Key mentions with character offsets into the .txt, clusters from conll."""
    text = txt_path.read_text(encoding="utf-8")
    offsets = _token_offsets(text)
    conll_tokens: list[tuple[str, str]] = []
    for line in conll_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        conll_tokens.append((cols[3], cols[-1].strip()))
    if len(conll_tokens) != len(offsets):
        raise ValueError(f"{conll_path.name}: {len(conll_tokens)} conll tokens vs {len(offsets)} in text")

    types: dict[tuple[int, int], tuple[str, str]] = {}
    for line in ann_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("T"):
            continue
        _tid, body, _surface = line.split("\t", 2)
        label, start_s, end_s = body.split(" ")[:3]
        # The coref .ann carries two kinds of T-line over the same spans: a
        # typed one ("PROP_PER") and a cluster-name one ("Jarndyce_1-72").
        # Only the typed kind is a mention type; letting the other through
        # overwrote the type of most spans on the first attempt.
        typed = re.fullmatch(r"(PROP|NOM|PRON)_([A-Z]+)", label)
        if typed:
            types[(int(start_s), int(end_s))] = (typed.group(1), typed.group(2))

    open_spans: dict[str, list[int]] = {}
    mentions: list[KeyMention] = []
    for i, ((token, tag), (start, end, surface)) in enumerate(zip(conll_tokens, offsets, strict=True)):
        if token != surface:
            raise ValueError(f"{conll_path.name}: token {i} {token!r} != text {surface!r}")
        if tag in ("", "_", "-"):
            continue
        for part in tag.split("|"):
            m = re.fullmatch(r"(\()?(\d+)(\))?", part)
            if not m:
                continue
            opening, cid, closing = m.groups()
            if opening and closing:
                span_start = start
            elif opening:
                open_spans.setdefault(cid, []).append(start)
                continue
            else:
                span_start = open_spans[cid].pop()
            mtype, etype = types.get((span_start, end), ("", ""))
            mentions.append(KeyMention(span_start, end, text[span_start:end], cid, mtype, etype))
    return text, mentions


def person_clusters(mentions: Iterable[KeyMention]) -> set[str]:
    """Clusters whose typed mentions are mostly PER -- LitBank also annotates
    LOC/FAC/GPE/ORG/VEH, which EchoTales does not claim to resolve as characters."""
    votes: dict[str, list[str]] = {}
    for m in mentions:
        if m.entity_type:
            votes.setdefault(m.cluster, []).append(m.entity_type)
    return {c for c, v in votes.items() if v.count("PER") * 2 > len(v)}


def ingest_document(store: Store, novel_id: str, text: str) -> None:
    """One chapter, one PROSE block, so `Chapter.story_text` == the .txt exactly."""
    store.add_novel(novel_id, novel_id, "litbank", "generic")
    store.add_chapter(Chapter(
        novel_id=novel_id, number=1.0, title="LitBank excerpt", source_href="litbank",
        blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
    ))
    store.conn.commit()


def system_mentions(store: Store, novel_id: str, *, persons_only: bool = True) -> list[tuple[int, int, str]]:
    """(start, end, cluster) for every system mention; unlinked ones are singletons."""
    out = []
    for m in store.get_mentions(novel_id):
        if persons_only and m.entity_label not in (None, "", "character", "person"):
            continue
        cluster = m.target_id or f"__single__{m.id}"
        out.append((m.offset, m.offset + len(m.text), cluster))
    return out


def score(docs: dict[str, tuple[list[KeyMention], list[tuple[int, int, str]]]], *,
          prop_only: bool, key_restricted: bool) -> dict[str, float]:
    """Pool every document (keys prefixed by doc) and score MUC/B3/CEAF-e/CoNLL."""
    gold: dict[Span, str] = {}
    system: dict[Span, str] = {}
    for doc, (key, sys_mentions) in docs.items():
        people = person_clusters(key)
        for m in key:
            if m.cluster in people and (not prop_only or m.mention_type == "PROP"):
                gold[(doc, m.start, m.end)] = f"{doc}:{m.cluster}"
        for start, end, cluster in sys_mentions:
            span = (doc, start, end)
            if key_restricted and span not in gold:
                continue
            system[span] = f"{doc}:{cluster}"
    # CEAF-e's optimal matching is cubic in the number of clusters; pooled over
    # 100 documents it did not finish. Clusters never match across documents
    # (keys are doc-prefixed), so matching per document and pooling the
    # numerators and denominators gives the same micro-average.
    num = p_den = r_den = 0.0
    for doc in docs:
        g_doc = {k: v for k, v in gold.items() if k[0] == doc}
        s_doc = {k: v for k, v in system.items() if k[0] == doc}
        c = ceafe(g_doc, s_doc)
        n_sys, n_gold = len(set(s_doc.values())), len(set(g_doc.values()))
        num += c.recall * n_gold if n_gold else c.precision * n_sys
        p_den += n_sys
        r_den += n_gold
    pooled_ceafe = MetricScore("CEAFe", num / p_den if p_den else 0.0, num / r_den if r_den else 0.0)
    scores: list[MetricScore] = [muc(gold, system), b_cubed(gold, system), pooled_ceafe]
    out: dict[str, float] = {f"{s.name}_{k}": round(v * 100, 2) for s in scores
                             for k, v in (("P", s.precision), ("R", s.recall), ("F1", s.f1))}
    out["CoNLL_F1"] = round(conll_f1(*scores) * 100, 2)
    out["gold_mentions"] = len(gold)
    out["system_mentions"] = len(system)
    out["exact_span_matches"] = len(set(gold) & set(system))
    return out
