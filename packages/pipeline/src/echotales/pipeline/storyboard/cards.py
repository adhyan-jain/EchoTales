"""Knowledge cards for the director prompt and the token budget that decides which of them survive.

Why cards and a budget: the v1 prompt gave the model a name and, at best, a one-line look per person, and the model
filled the rest from itself (RI ch1: the clan head drawn young, Bai Ning Bing absent, "clan head" read as a job title
with no weight). The graph already knows the person's look at this story time, role and what the title means. But the
local director has a 4096-token context shared with the answer (HANDOFF 4.51), so what is added has to be ranked and
the lowest-value text dropped first or the window text gets cut instead.

Only existing knowledge APIs are read (`look_for`, `dossier_at`, `glossary.entry`, the future brief); nothing here
writes a store or keeps a list of names, titles or words.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from echotales.core.store import Store
from echotales.pipeline.storyboard.inputs import ChapterInput, RosterEntry, Scene, look_for

#: Prompt tokens kept free for the answer: a window plan runs 1000-1500 tokens of JSON (measured on RI ch1), and the
#: model's context is 4096 in the default `local-low` compute.
CONTEXT_TOKENS = 4096
ANSWER_RESERVE = 1400
LOOK_WORDS_MIN = 12
TITLE_WORDS = 20


def estimate_tokens(text: str) -> int:
    """Cheap, slightly pessimistic count: this budget must never promise room the model does not have."""
    return math.ceil(len(text) / 3.2)


@dataclass(slots=True)
class Card:
    entity_id: str
    name: str
    status: str  # "present" | "referenced"
    matters_later: bool = False
    look: str = ""
    look_source: str = ""  # "dossier" when the dossier supplied the look, "bible" for the chapter look
    age: str = ""
    role: str = ""
    title_meaning: str = ""

    @property
    def rank(self) -> int:
        """Present people first, then talked-about people who matter later, then the rest."""
        return 3 if self.status == "present" else 2 if self.matters_later else 1

    def variants(self) -> list[str]:
        """Full card, then progressively poorer ones: title meaning goes first, then role, then the look is trimmed."""
        look = self.look
        short = " ".join(look.split()[:LOOK_WORDS_MIN])

        # the status tag is what tells the model who may stand in the room; a card list without it read as a cast list
        tag = "PRESENT" if self.status == "present" else "only talked about, not in the room"

        def line(look_text: str, role: bool, title: bool) -> str:
            bits = [f"  - {self.name} ({tag})"]
            tail = [x for x in (look_text, f"age {self.age}" if self.age else "") if x]
            if tail:
                bits.append(": " + "; ".join(tail))
            if role and self.role:
                bits.append(f"; role {self.role}")
            if title and self.title_meaning:
                bits.append(f"; title means: {self.title_meaning}")
            return "".join(bits)

        out = [line(look, True, True), line(look, True, False), line(look, False, False), line(short, False, False)]
        return list(dict.fromkeys(out))


def _sub_phrases(value: str) -> list[str]:
    """Every contiguous word run of `value`, longest first: the glossary is asked by set membership, not matched by a list."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", value)
    return [" ".join(words[i : i + n]) for n in range(len(words), 0, -1) for i in range(len(words) - n + 1)]


def title_meaning(store: Store, novel_id: str, role_value: str) -> str:
    from echotales.pipeline.knowledge import glossary

    for phrase in _sub_phrases(role_value):
        ent = glossary.entry(store, novel_id, phrase)
        claim = next((c for c in (ent or {}).get("claims", []) if c.get("field") == "definition"), None)
        if claim:
            return " ".join(str(claim["text"]).split()[:TITLE_WORDS])
    return ""


def _entry_for(inp: ChapterInput, eid: str) -> RosterEntry | None:
    return next((r for r in inp.roster if r.entity_id == eid), None)


def _brief_entity(brief: dict | None, eid: str) -> dict:
    return next((e for e in (brief or {}).get("entities", []) if e.get("entity_id") == eid), {})


def build_cards(store: Store, inp: ChapterInput, scene: Scene, brief: dict | None) -> list[Card]:
    """One card per roster person in the scene, present or only talked about; crowds and unknown ids get none."""
    from echotales.pipeline.knowledge.dossier import dossier_at

    cards: list[Card] = []
    for eid, status in [(i, "present") for i in scene.present_ids] + [(i, "referenced") for i in scene.referenced_ids]:
        r = _entry_for(inp, eid)
        if r is None:
            # a group or someone the model's own presence read named (`crowd:`, `extra:`, `ref:`): no knowledge to carry, but
            # the model must still be told they are in the room or it will leave the elders out of the picture
            if eid.split(":", 1)[0] in ("crowd", "extra", "ref"):
                cards.append(Card(eid, inp.labels.get(eid, eid.split(":", 1)[-1].replace("-", " ")), status))
            continue
        desc, _look_id, _ok = look_for(store, inp.novel_id, r, inp.chapter, scene.block_from)
        card = Card(eid, r.name, status, bool(_brief_entity(brief, eid).get("matters_later")), look=desc,
                    look_source="bible" if desc else "")
        try:
            d = dossier_at(store, inp.novel_id, eid, inp.chapter, whole_novel=True)
        except Exception:  # no knowledge pass has run for this novel: the card is just thinner
            d = None
        if d is not None:
            ages = d.appearance.get("apparent_age", [])
            card.age = ages[0].value if ages else ""
            roles = [f.value for f in d.roles[:1]] + [f.value for f in d.affiliations[:1]]
            card.role = "; ".join(dict.fromkeys(roles))
            card.title_meaning = title_meaning(store, inp.novel_id, d.roles[0].value) if d.roles else ""
            # an inset of someone who never stands in the room is drawn from the dossier's look, not from the name; a
            # referenced person with no bible look yet (Bai Ning Bing in RI ch1) gets it only from here
            if status == "referenced" and d.appearance:
                parts = [f"{k.replace('_', ' ')} {fs[0].value}" for k, fs in d.appearance.items() if k != "apparent_age" and fs]
                if parts and not card.look:
                    card.look, card.look_source = "; ".join(parts), "dossier"
        cards.append(card)
    cards.sort(key=lambda c: -c.rank)
    return cards


def future_brief_block(brief: dict | None, scene: Scene, inp: ChapterInput) -> str:
    """What the rest of the novel makes of this scene's people, so a beat can lean on it without inventing it."""
    ids = {*scene.present_ids, *scene.referenced_ids}
    rows: list[str] = []
    for e in (brief or {}).get("entities", []):
        if e.get("entity_id") not in ids or not e.get("matters_later"):
            continue
        row = f"  - {e['label']}: {e.get('role_summary', '')}"
        for s in e.get("setups", [])[:2]:
            row += f"\n      setup: here \"{_anchor(s.get('here', ''))}\" -> later ch{s.get('later_chapter', 0):g}: {s.get('later', '')[:110]}"
        rows.append(row)
    return "MATTERS LATER IN THE NOVEL (emphasise only; never add an event):\n" + "\n".join(rows) if rows else ""


def _anchor(text: str, n: int = 5) -> str:
    """No more than five words of source text, the repo's limit on quoted passages."""
    return " ".join(text.split()[:n])


@dataclass(slots=True)
class Part:
    text: str | list[str]  # one string, or card variants richest first
    priority: int = 0  # higher survives longer
    mandatory: bool = False
    level: int = 0
    dropped: bool = False
    name: str = ""

    def current(self) -> str:
        if self.dropped:
            return ""
        return self.text if isinstance(self.text, str) else self.text[min(self.level, len(self.text) - 1)]

    def can_shrink(self) -> bool:
        return not isinstance(self.text, str) and self.level < len(self.text) - 1


@dataclass(slots=True)
class Assembly:
    text: str
    tokens: int
    dropped: list[str] = field(default_factory=list)
    shrunk: list[str] = field(default_factory=list)


def assemble(parts: list[Part], budget_tokens: int = CONTEXT_TOKENS - ANSWER_RESERVE) -> Assembly:
    """Join `parts` in order inside `budget_tokens`. Mandatory parts always stay; the rest shrink, then drop, lowest
    priority first. Cards are shrunk across the board before any whole card goes, because losing a title meaning costs
    less than losing a person."""

    def total() -> int:
        return estimate_tokens("\n".join(p.current() for p in parts if p.current()))

    optional = sorted((p for p in parts if not p.mandatory), key=lambda p: p.priority)
    for lvl in range(1, max((len(p.text) for p in optional if not isinstance(p.text, str)), default=1)):
        for p in optional:
            if total() <= budget_tokens:
                break
            if p.can_shrink() and p.level < lvl:
                p.level = lvl
    for p in optional:
        if total() <= budget_tokens:
            break
        p.dropped = True
    text = "\n".join(p.current() for p in parts if p.current())
    return Assembly(
        text, estimate_tokens(text), [p.name for p in parts if p.dropped], [p.name for p in parts if p.level and not p.dropped]
    )
