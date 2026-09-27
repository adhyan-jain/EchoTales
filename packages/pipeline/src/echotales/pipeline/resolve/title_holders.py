"""Link title mentions to the holder the volume names, including backwards.

**The defect.** Reverend Insanity calls its clan head "the clan head" for five
chapters before anyone names him; from chapter 6 ("go against me, Gu Yue
Bo!") the text ties the title to Gu Yue Bo more than fifty times
("clan leader Gu Yue Bo", "the clan head, Gu Yue Bo", "Gu Yue clan leader,
Gu Yue Bo"). Every one of the volume's 36 "clan head / clan leader" mentions
was still unresolved on the canonical run: the resolver links a title only
through a *sole co-present* named candidate in the same chapter
(`evidence.py::relationship_deictic_resolution`), and in chapter 1 there is
no named candidate to be co-present with. The title became, in effect, a
second character -- and the audio gave "the clan head" its own voice.

**The fix, volume-first (non-negotiable #6).** Harvest every explicit
declaration that a title belongs to a named Self, per organisation; build
each holder's interval from those declarations; then link unresolved title
mentions inside that interval. The first holder's interval is extended back
to chapter 1 -- the retroactive case -- because a title with a single
declared holder and no earlier one was held by that holder from the start.

**Precision over recall (non-negotiable #9)**, so a mention is left alone
when:
- it is ordinal or historical ("the fourth generation clan head", "the
  previous clan leader", "the next clan leader") -- a different person;
- it names another organisation ("the Bai clan leader") with no declared
  holder of its own;
- it is unqualified ("the clan leader") in a passage where another
  organisation's title-holder is also present, unless the holder's own name
  or organisation is in the same or the preceding few blocks;
- it falls between one holder's last declaration and the next holder's
  first (a handover whose exact point the text does not give).
A holder needs `MIN_DECLARATIONS` independent declarations before any
mention is linked to them.

Transfer is not retraction (non-negotiable #5): a second declared holder
closes the first holder's interval; it does not undo the earlier links.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    AttributionMethod,
    EventType,
    ResolutionMethod,
    TargetKind,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import AliasBinding, DiscoursePosition, ResolutionEvent, Self
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key

log = logging.getLogger(__name__)

#: Titles held by one person at a time within an organisation. "Elder" is not
#: here: a clan has many elders at once, so it cannot name one person.
TITLE_HEADS = (
    r"clan\s+(?:head|leader|master|chief)|sect\s+(?:master|leader|head)|patriarch|matriarch|"
    r"family\s+head|village\s+(?:chief|head)|guild\s+master|tribe\s+(?:leader|chief)|headmaster"
)
_TITLE = re.compile(rf"\b(?:{TITLE_HEADS})\b", re.IGNORECASE)

#: Words that make a title refer to someone other than the current holder.
_HISTORICAL = re.compile(
    r"\b(?:generation|generations|previous|former|late|next|future|successive|every|each|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|old|older|past|"
    r"ancestral|founding|new|deputy|vice|acting)\b[\w\s’'-]{0,24}$",
    re.IGNORECASE,
)

_NAME = r"[A-Z][\w’'-]+(?:\s+[A-Z][\w’'-]+){0,3}"
_ORG = r"[A-Z][\w’'-]+(?:\s+[A-Z][\w’'-]+)?"
#: The organisation in front of a title: "Gu Yue", "Jia family", "Bai clan".
_ORG_PHRASE = rf"(?P<org>{_ORG})(?:\s+(?:clan|family|sect|tribe|village))?(?:’s|'s)?"
_NOT_ORG = {"the", "lord", "sir", "this", "that", "our", "your", "his", "her", "their", "my", "current"}

#: "clan leader Gu Yue Bo", "the clan head, Gu Yue Bo", "Gu Yue clan leader, Gu Yue Bo"
_TITLE_THEN_NAME = re.compile(
    rf"(?:(?P<org>{_ORG})(?:’s|'s)?\s+)?(?i:(?P<title>{TITLE_HEADS}))\s*,?\s+(?P<name>{_NAME})"
)
#: "Gu Yue Bo, the clan leader" / "Gu Yue Bo was the Gu Yue clan leader"
_NAME_THEN_TITLE = re.compile(
    rf"(?P<name>{_NAME})(?:\s*,\s*|\s+(?:was|is|became|remained)\s+)(?:the\s+)?(?:current\s+)?"
    rf"(?:(?P<org>{_ORG})(?:’s|'s)?\s+)?(?i:(?P<title>{TITLE_HEADS}))\b"
)
#: Inside a quote: "go against me, Gu Yue Bo!" / "I, Gu Yue Bo, ..."
_SELF_NAMING = re.compile(rf"\b(?:me|I)\s*,\s*(?P<name>{_NAME})")
_QUOTE = re.compile(r"[“\"]([^”\"]+)[”\"]")

MIN_DECLARATIONS = 2
#: Organisation-qualified mentions of a title whose holder is never named
#: ("Xiong clan leader", 8 mentions in RI) before they become one unnamed
#: identity instead of eight unresolved strings.
MIN_UNNAMED_MENTIONS = 3
#: Blocks back from an unqualified mention that may carry the holder's name.
LOCAL_WINDOW = 3


@dataclass(slots=True)
class Declaration:
    chapter: float
    block_index: int
    org: str | None
    self_id: str
    evidence: str


@dataclass(slots=True)
class Tenure:
    self_id: str
    start: float
    end: float
    declarations: int
    last_declared: float


@dataclass(slots=True)
class TitleHolderReport:
    declarations: int = 0
    holders: dict[str, list[Tenure]] = field(default_factory=dict)
    linked: int = 0
    skipped_historical: int = 0
    skipped_other_org: int = 0
    skipped_ambiguous: int = 0
    skipped_gap: int = 0
    speakers_mapped: int = 0
    unnamed_holders: int = 0
    unnamed_linked: int = 0

    def summary(self) -> str:
        def span(t: Tenure) -> str:
            end = "end" if t.end == float("inf") else f"{t.end:g}"
            return f"{t.self_id.rsplit(':', 1)[-1]} ch{t.start:g}-{end} ({t.declarations} decl.)"

        who = "; ".join(
            f"{org or '(unqualified)'}: " + ", ".join(span(t) for t in tenures)
            for org, tenures in self.holders.items()
        )
        return (
            f"title holders: {self.declarations} declarations; {who or 'none'}\n"
            f"  linked={self.linked} speakers_mapped={self.speakers_mapped} "
            f"unnamed_holders={self.unnamed_holders} (linked {self.unnamed_linked}) "
            f"skipped: historical={self.skipped_historical} other_org={self.skipped_other_org} "
            f"ambiguous={self.skipped_ambiguous} handover_gap={self.skipped_gap}"
        )


def _org_key(org: str | None) -> str | None:
    if not org:
        return None
    key = comparison_key(re.sub(r"(?:’s|'s)$", "", org.strip()))
    return None if key in {"the", "a", "his", "her", "their", "our", "your", "lord", "sir", "current", ""} else key


def _name_index(store: Store, novel_id: str) -> dict[str, str]:
    """comparison_key(name) -> Self id, only for names that denote one person."""
    owners: dict[str, set[str]] = defaultdict(set)
    for entity in store.all_selves(novel_id):
        if entity.kind.is_person and (k := comparison_key(entity.canonical_label)):
            owners[k].add(entity.id)
    for binding in store.all_aliases(novel_id):
        if (binding.alias_type is AliasType.RIGID_NAME and binding.target_kind is TargetKind.SELF
                and (k := comparison_key(binding.alias))):
            owners[k].add(binding.target_id)
    return {k: next(iter(v)) for k, v in owners.items() if len(v) == 1}


def _lookup(names: dict[str, str], raw: str) -> str | None:
    """Longest known name at the start of `raw` ("Gu Yue Bo’s hands" -> Gu Yue Bo)."""
    words = re.sub(r"(?:’s|'s)\b", "", raw).split()
    for n in range(len(words), 0, -1):
        if sid := names.get(comparison_key(" ".join(words[:n]))):
            return sid
    return None


def _historical(before: str) -> bool:
    return bool(_HISTORICAL.search(before[-40:]))


_PREPOSITION = re.compile(
    r"\b(?:beside|behind|before|after|near|to|with|from|of|for|towards|toward|at|by|than|like|"
    r"under|above|around|against|without|about|upon|into|onto)\s+(?:the\s+)?$",
    re.IGNORECASE,
)


def _is_apposition(pattern: re.Pattern[str], m: re.Match[str], text: str) -> bool:
    """Reject the four shapes that matched the patterns without being a
    declaration, each found on RI (2026-09-27 dry run):

    - a list: "the clan leader, Chi Lian or Mo Chen";
    - a possessive: "Fang Zheng is the clan leader's successor";
    - a preposition before a comma-title: "Beside the clan leader, Gu Yue Mo
      Chen said" -- the name opens a new clause;
    - a clause boundary after "NAME, the title": "abandon Fang Yuan, the clan
      leader would have no hesitation".
    """
    after = text[m.end():]
    if pattern is _TITLE_THEN_NAME:
        if re.match(r"\s*(?:,\s*[A-Z][\w’'-]+(?:\s+[A-Z][\w’'-]+)*)*\s*,?\s+(?:or|and)\b", after):
            return False
        comma = "," in text[m.end("title"): m.start("name")]
        return not (comma and _PREPOSITION.search(text[: m.start("title")]))
    if re.match(r"(?:’s|'s)\b", after):
        return False
    if "," in text[m.end("name"): m.start("title")]:
        return bool(re.match(r"\s*(?:[,.;:!?)”\"]|$)", after))
    return True


def harvest(store: Store, novel_id: str, names: dict[str, str]) -> list[Declaration]:
    out: list[Declaration] = []
    labels = {e.id: e.canonical_label for e in store.all_selves(novel_id)}
    for chapter in store.chapter_numbers(novel_id):
        ch = store.get_chapter(novel_id, chapter)
        if ch is None:
            continue
        for block in ch.blocks:
            text = block.text
            for pattern in (_TITLE_THEN_NAME, _NAME_THEN_TITLE):
                for m in pattern.finditer(text):
                    if _historical(text[: m.start("title")]) or not _is_apposition(pattern, m, text):
                        continue
                    sid = _lookup(names, m.group("name"))
                    if sid is None:
                        continue
                    org = _org_key(m.group("org"))
                    if org and org == comparison_key(labels.get(sid, "")):
                        org = None  # the "org" was the name itself
                    out.append(Declaration(chapter, block.index, org, sid, m.group(0)))
            # Self-naming inside a quote, with the speaker called by the title
            # in this block's narration: `"...against me, Gu Yue Bo!" The Gu
            # Yue clan head had gone crazy...`
            narration = _QUOTE.sub(" ", text)
            titles = [t for t in _TITLE.finditer(narration) if not _historical(narration[: t.start()])]
            if len(titles) != 1:
                continue
            for q in _QUOTE.finditer(text):
                for m in _SELF_NAMING.finditer(q.group(1)):
                    if sid := _lookup(names, m.group("name")):
                        lead = re.search(rf"(?P<org>{_ORG})(?:’s|'s)?\s*$", narration[: titles[0].start()])
                        org = _org_key(lead.group("org")) if lead else None
                        out.append(Declaration(chapter, block.index, org, sid, m.group(0)))
    return out


def tenures(decls: list[Declaration], labels: dict[str, str]) -> dict[str | None, list[Tenure]]:
    """Holder intervals per organisation (None = the title used unqualified).

    A declaration without an organisation also counts for the organisation
    the holder's own name begins with, when one is in use ("clan leader Gu
    Yue Bo" is evidence for the Gu Yue clan's title).
    """
    by_org: dict[str | None, list[Declaration]] = defaultdict(list)
    orgs = {d.org for d in decls if d.org}
    for d in decls:
        by_org[d.org].append(d)
        if d.org is None:
            name = comparison_key(labels.get(d.self_id, ""))
            for org in orgs:
                if name.startswith(org + " "):
                    by_org[org].append(d)
    out: dict[str | None, list[Tenure]] = {}
    for org, items in by_org.items():
        counts: dict[str, int] = defaultdict(int)
        for d in items:
            counts[d.self_id] += 1
        runs: list[Tenure] = []
        for d in sorted(items, key=lambda x: (x.chapter, x.block_index)):
            if counts[d.self_id] < MIN_DECLARATIONS:
                continue
            if runs and runs[-1].self_id == d.self_id:
                runs[-1].declarations += 1
                runs[-1].last_declared = d.chapter
            else:
                runs.append(Tenure(d.self_id, d.chapter, d.chapter, 1, d.chapter))
        for i, run in enumerate(runs):
            if i == 0:
                run.start = 1.0  # retroactive: held from the start of the volume
            run.end = float("inf") if i == len(runs) - 1 else run.last_declared
        if runs:
            out[org] = runs
    return out


def _holder_at(runs: list[Tenure], chapter: float) -> Tenure | None:
    for run in runs:
        if run.start <= chapter <= run.end:
            return run
    return None


def link_title_holders(store: Store, novel_id: str, *, dry_run: bool = False) -> TitleHolderReport:
    report = TitleHolderReport()
    names = _name_index(store, novel_id)
    labels = {e.id: e.canonical_label for e in store.all_selves(novel_id)}
    decls = harvest(store, novel_id, names)
    report.declarations = len(decls)
    held = tenures(decls, labels)
    report.holders = {org or "": runs for org, runs in held.items()}
    if not held:
        return report
    holder_orgs = {org for org in held if org}
    cache: dict[float, list[str]] = {}

    def block_texts(chapter: float) -> list[str]:
        if chapter not in cache:
            ch = store.get_chapter(novel_id, chapter)
            cache[chapter] = [b.text for b in ch.blocks] if ch else []
        return cache[chapter]

    def rival_orgs(text: str) -> set[str]:
        found = set()
        for m in re.finditer(rf"{_ORG_PHRASE}\s+(?:current\s+)?(?i:{TITLE_HEADS})", text):
            if m.group("org").casefold() in _NOT_ORG:
                continue
            if (org := _org_key(m.group("org"))) and org not in holder_orgs:
                found.add(org)
        return found

    def resolve(chapter: float, block_index: int, before: str, surface: str,
                contrast: bool = False, sentence_text: str = "") -> tuple[Tenure | None, str]:
        title = _TITLE.search(surface)
        if title is None:
            return None, "ambiguous"
        if _historical(before) or _historical(surface[: title.start()]):
            return None, "historical"
        own = re.match(rf"(?:the\s+)?{_ORG_PHRASE}(?:\s+current)?\s+(?i:{TITLE_HEADS})", surface)
        if own and own.group("org").casefold() in _NOT_ORG:
            own = None
        # A determiner-led mention ("the clan leader") has no organisation in
        # front of it: "As the clan leader" read "As" as a clan (RI ch181).
        led = re.match(r"(?i)(?:the|lord|sir|our|your|his|her|their)\b", surface.strip())
        tail = re.search(rf"{_ORG_PHRASE}\s*$", before) if not own and not led else None
        if tail and tail.group("org").casefold() in _NOT_ORG:
            tail = None
        org = _org_key(own.group("org")) if own else (_org_key(tail.group("org")) if tail else None)
        if org is not None:
            runs = held.get(org)
            if runs is None:
                return None, "other_org"
            hit = _holder_at(runs, chapter)
            return (hit, "") if hit else (None, "gap")
        runs = held.get(None)
        if runs is None:
            return None, "ambiguous"
        hit = _holder_at(runs, chapter)
        if hit is None:
            return None, "gap"
        texts = block_texts(chapter)
        # "hand the clan head's letter to Gu Yue's clan head": an unqualified
        # title beside the holder's own qualified one is the *other* holder.
        if contrast:
            return None, "ambiguous"
        # "Within the Gu Yue clan, only the clan leader is Rank four": the
        # sentence names the holder's organisation and no other one.
        squashed_sentence = comparison_key(sentence_text).replace(" ", "")
        if sentence_text and not rival_orgs(sentence_text) and any(
            o.replace(" ", "") in squashed_sentence for o in holder_orgs
        ):
            return hit, ""
        if rival_orgs(" ".join(texts)):
            window = " ".join(texts[max(0, block_index - LOCAL_WINDOW): block_index + 1])
            squashed = comparison_key(window).replace(" ", "")
            own_org_named = any(o.replace(" ", "") in squashed for o in holder_orgs)
            if rival_orgs(window) or (labels.get(hit.self_id, "\0") not in window and not own_org_named):
                return None, "ambiguous"
        return hit, ""

    events: list[ResolutionEvent] = []
    other_org_mentions: dict[str, list] = defaultdict(list)
    for mention in store.get_mentions(novel_id):
        if (mention.target_id is not None or mention.alias_type is not AliasType.TRANSFERABLE_TITLE
                or not _TITLE.search(mention.text)):
            continue
        texts = block_texts(mention.chapter)
        bi = mention.block_index if mention.block_index is not None else 0
        text = texts[bi] if bi < len(texts) else ""
        before = text[: mention.offset] if mention.offset is not None else ""
        # The sentence around the mention, minus the mention itself: `resolve`
        # looks for the holder's own qualified title in what remains.
        off = mention.offset or 0
        sent_start = max((m.end() for m in re.finditer(r"[.!?]\s", text[:off])), default=0)
        sent_end = next((m.start() + 1 for m in re.finditer(r"[.!?]", text[off + len(mention.text):])), len(text) - off - len(mention.text))
        sent_text = text[sent_start: off + len(mention.text) + sent_end]
        rel = off - sent_start
        masked = sent_text[:rel] + " " * len(mention.text) + sent_text[rel + len(mention.text):]
        contrast = bool(re.search(rf"{_ORG_PHRASE}\s+(?i:{TITLE_HEADS})", masked))
        tenure, why = resolve(mention.chapter, bi, before, mention.text, contrast=contrast,
                              sentence_text=masked)
        # "As the clan leader, Gu Yue Bo knew": the mention is itself a
        # declaration of the current holder, whatever else is in the passage.
        named = re.match(rf"\s*,?\s+(?P<name>{_NAME})", text[off + len(mention.text):])
        if tenure is None and why == "ambiguous" and named and not contrast:
            sid = _lookup(names, named.group("name"))
            runs = held.get(None, [])
            hit = _holder_at(runs, mention.chapter)
            if hit is not None and hit.self_id == sid:
                tenure, why = hit, ""
        if tenure is None:
            name = f"skipped_{why}"
            setattr(report, name, getattr(report, name) + 1)
            own = re.match(rf"(?:the\s+)?{_ORG_PHRASE}(?:\s+current)?\s+(?i:{TITLE_HEADS})", mention.text)
            if why == "other_org" and own and own.group("org").casefold() not in _NOT_ORG:
                other_org_mentions[_org_key(own.group("org")) or ""].append(mention)
            continue
        report.linked += 1
        if dry_run:
            continue
        mention.target_kind = TargetKind.SELF
        mention.target_id = tenure.self_id
        mention.method = ResolutionMethod.TITLE_HOLDER
        mention.confidence = 0.85
        store.add_mentions([mention])
        events.append(ResolutionEvent(
            id=uuid.uuid4().hex, seq=0, type=EventType.LINK,
            payload={"mention_id": mention.id, "target_id": tenure.self_id, "title": mention.text,
                     "tenure": [tenure.start, None if tenure.end == float("inf") else tenure.end],
                     "declarations": tenure.declarations},
            cause_pos=DiscoursePosition(chapter=int(mention.chapter)),
            method=ResolutionMethod.TITLE_HOLDER, confidence=0.85,
        ))

    # A recurring organisation-qualified title whose holder is never named
    # becomes one unnamed identity: "the Xiong clan leader" is one man
    # throughout the volume, not eight unresolved strings. Only the qualified
    # mentions are linked; a bare "the clan leader" never is.
    for org, items in other_org_mentions.items():
        if not org or len(items) < MIN_UNNAMED_MENTIONS:
            continue
        report.unnamed_holders += 1
        first = min(items, key=lambda m: (m.chapter, m.block_index or 0))
        head = _TITLE.search(first.text).group(0).lower()
        label = f"{' '.join(w.capitalize() for w in org.split())} {head}"
        sid = f"{novel_id}:self:title-{org.replace(' ', '-')}-{head.replace(' ', '-')}"
        if not dry_run and store.get_self(sid) is None:
            store.add_self(Self(id=sid, novel_id=novel_id, canonical_label=label,
                                first_attested_pos=DiscoursePosition(chapter=int(first.chapter)),
                                notes="unnamed title holder (resolve/title_holders.py)"))
            store.add_alias_binding(novel_id, AliasBinding(
                alias=label, alias_type=AliasType.TRANSFERABLE_TITLE, target_kind=TargetKind.SELF,
                target_id=sid, interval=FuzzyInterval.open_ended(first.chapter),
                learned_at_pos=DiscoursePosition(chapter=int(first.chapter)), observer_id=OBSERVER_READER,
                evidence=first.text, confidence=0.8))
        for mention in items:
            report.unnamed_linked += 1
            if dry_run:
                continue
            mention.target_kind = TargetKind.SELF
            mention.target_id = sid
            mention.method = ResolutionMethod.TITLE_HOLDER
            mention.confidence = 0.8
            store.add_mentions([mention])

    # Epithet speakers ("the clan head said"): voice them as the holder.
    for chapter in store.chapter_numbers(novel_id):
        changed = []
        for span in store.get_spans(novel_id, chapter):
            if span.attribution_method is not AttributionMethod.EPITHET_SLOT or not span.speaker_self_id:
                continue
            role = span.speaker_self_id.rsplit(":", 1)[-1].replace("-", " ").strip()
            if not _TITLE.fullmatch(role):
                continue
            # Speaker slots built before the qualifier was kept collapse "the
            # fourth generation clan head" to "clan-head": check the block's
            # own narration, and map only when a current-holder title is there.
            texts = block_texts(chapter)
            narration = _QUOTE.sub(" ", texts[span.block_index]) if span.block_index < len(texts) else ""
            titles = list(_TITLE.finditer(narration))
            if not titles or all(_historical(narration[: t.start()]) for t in titles):
                continue
            tenure, _ = resolve(chapter, span.block_index, "", f"the {role}")
            if tenure is None:
                continue
            report.speakers_mapped += 1
            span.speaker_self_id = labels[tenure.self_id]
            span.attribution_method = AttributionMethod.TITLE_HOLDER
            span.confidence = 0.8
            changed.append(span)
        if changed and not dry_run:
            store.add_spans(changed)

    if dry_run:
        return report
    last_seq = store.conn.execute("SELECT COALESCE(MAX(seq), -1) FROM resolution_event").fetchone()[0]
    for i, event in enumerate(events, start=1):
        event.seq = last_seq + i
        store.append_event(event)
    # One alias binding per holder and organisation. The reader learns the
    # name at the first declaration, so that is the knowledge position; the
    # interval (when the title is held) starts earlier.
    existing = {(b.target_id, comparison_key(b.alias)) for b in store.all_aliases(novel_id)
                if b.alias_type is AliasType.TRANSFERABLE_TITLE}
    ordered = sorted(decls, key=lambda x: (x.chapter, x.block_index))
    for org, runs in held.items():
        for run in runs:
            first = next(d for d in ordered if d.self_id == run.self_id)
            alias = f"the {org.title()} clan head" if org else "the clan head"
            if (run.self_id, comparison_key(alias)) in existing:
                continue
            store.add_alias_binding(novel_id, AliasBinding(
                alias=alias, alias_type=AliasType.TRANSFERABLE_TITLE, target_kind=TargetKind.SELF,
                target_id=run.self_id,
                interval=FuzzyInterval.open_ended(run.start, last_evidence=run.last_declared)
                if run.end == float("inf")
                else FuzzyInterval(from_lb=run.start, from_ub=run.start, to_lb=run.end, to_ub=run.end,
                                   last_evidence=run.last_declared),
                learned_at_pos=DiscoursePosition(chapter=int(first.chapter)), observer_id=OBSERVER_READER,
                evidence=first.evidence[:200], confidence=0.85,
            ))
    log.info(report.summary())
    return report
