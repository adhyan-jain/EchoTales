"""Prompt assembly for the storyboard director.

The rule text is the 11-rule grammar of docs/results/MANHWA_DIRECTING_PATTERNS.md section 3, restated as instructions a
small model can follow. Each rule is one imperative with the failure it prevents, because the same small models ignored
a long abstract style brief in the render director (HANDOFF 4.51/4.52) but kept short, concrete prohibitions.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from echotales.pipeline.storyboard.cards import Card, Part, assemble
from echotales.pipeline.storyboard.inputs import ChapterInput, Line, RosterEntry
from echotales.pipeline.storyboard.plan_schema import LWindow

PROMPT_VERSION = "sb-5"
MAX_NARRATION_CHARS = 300

SYSTEM = """You are the storyboard artist adapting a web-novel chapter into a manhwa (vertical-scroll comic). Plan the
panels for the passage by drama, not by paragraph. You know the whole novel (the cards and the MATTERS LATER list), so
direct with it: add tension and curiosity, but never a plot fact the text does not state.
Answer with one JSON object: panels, cut_lines. Refer to source text only by its tag (s12), never retype it.

RULES
1. HOOK. If the passage starts the chapter, panel 1 is purpose cold_open and is NOT a hero: sound effects (sfx), a black
   text-only card, or a striking insert/extreme_close. The person comes after.
2. FIXED. The scene's layer, place, time and PRESENT list are given; do not change them. A panel may use another layer
   only for a dream, memory, lore or imagined picture inside the scene.
3. CUTS. A passage that opens with a cut starts with a time_place_card, a transition or an establishing panel. If the
   cut is a MATCH (a simultaneous scene elsewhere), start with a transition panel, cut_signal "match", echoing the shape
   of the last picture of the scene before.
4. PRESENCE. Only PRESENT people go in cast. A person only talked about is never in the room: if the CARDS say they
   matter later, show them once as a referenced_inset (layer imagined, shape inset, shot medium_close, no letters, look
   from their card, invented true).
5. WITHHELD. If the text hides who someone is until a later line (see NEXT), draw only the clue: extreme_close, empty
   cast, withheld true. The reveal is the next panel that names them.
6. DENSITY. A peak (shout, reveal, attack, decision) gets 3-5 panels: line, face, reaction, insert. Quiet explanation
   shrinks to one caption. Every spoken line appears in some panel or is listed in cut_lines with a reason.
7. CROWDS. A crowd that speaks is individuals: one crowd_individual panel per speaking face, never named.
8. LETTERING. letters = line tags with a kind: speech, shout, whisper, dread, thought, memory, narration, poem (verse),
   screen (text on a phone, window or system display). Put sound words in sfx (max 3 words) and a card caption in card.
9. EMOTION. Give every panel an emotion (one or two words) that the text supports.
10. SHAPES. wide for places and crowds, tall for heroes and falls, diagonal for clashes, inset for asides, bleed for the
    peak, text_only for cards.
11. FORESHADOW. At most one or two panels per passage may set beat "foreshadow" or "curiosity": only an insert or
    framing that emphasises text already there because MATTERS LATER says it pays off. Never show the later event.
12. EVIDENCE. Every invented panel is invented true and its reason starts with text:, dossier: or brief: followed by the
    tag or item it comes from. No reason, no panel. Invented panels carry no speech.
13. LOOKS. Use only names from the CARDS; use each person's look and age as given.
Visuals are plain words: no style words, no camera jargon, nothing the text does not state."""


@lru_cache(maxsize=1)
def load_fewshots(path: str | None = None) -> list[dict]:
    p = Path(path) if path else _default_fewshot_path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _default_fewshot_path() -> Path:
    from echotales.pipeline.paths import GOLD_DIR

    return GOLD_DIR / "adaptation" / "storyboard_fewshot.jsonl"


def fewshot_digest() -> str:
    import hashlib

    return hashlib.sha1(json.dumps(load_fewshots(), sort_keys=True).encode()).hexdigest()[:10]


def render_lines(lines: list[Line]) -> str:
    out: list[str] = []
    for ln in lines:
        text = ln.text
        if ln.kind == "narration" and len(text) > MAX_NARRATION_CHARS:
            text = text[:MAX_NARRATION_CHARS].rstrip() + " ..."
        if ln.kind == "narration":
            out.append(f"[b{ln.block}] {ln.id} NARRATION: {text}")
        else:
            who = ln.speaker_name or "unknown speaker"
            out.append(f"[b{ln.block}] {ln.id} {ln.kind.upper()} ({who}): {text}")
    return "\n".join(out)


def _people(present: list[tuple[str, str]], referenced: list[str], fixed: bool) -> str:
    lines: list[str] = []
    head = "PRESENT in this scene (fixed)" if fixed else "PEOPLE named in this passage (decide who is physically there)"
    lines.append(head + ":")
    for name, look in present:
        lines.append(f"  - {name}" + (f": {look}" if look else ""))
    if not present:
        lines.append("  - (nobody listed; crowd and unnamed people may still appear)")
    if fixed or referenced:
        lines.append("ONLY TALKED ABOUT / not present: " + (", ".join(referenced) if referenced else "(none)"))
    return "\n".join(lines)


SCENE_SYSTEM = """You split one novel chapter into scenes. A scene is one place at one time with one set of people.
Answer with JSON: scenes, a list of {from_block, place, story_time, layer, cut_signal}, in order, the first at the first block.
Start a NEW scene only when something changes: a new place is named or reached, time jumps (hours later, that night, years
ago), the story moves to different people somewhere else (often with no marker: "at the same moment", a new character
introduced in a new setting), or a memory or dream begins. A chapter is usually 2 to 6 scenes. Do not start a scene at
every paragraph, and do not start one where the same people continue in the same place.
place is the specific spot where the action is (the temple hall, a third-floor window), not just the town or mountain.
story_time says when (that night, 500 years earlier); give each scene its own value, same as before only if nothing changed.
layer is present, past (flashback shown straight), memory, lore (narrated history), imagined or dream.
cut_signal is how the cut INTO the scene is best shown: card (a place or time caption), match (a graphic match between two
similar images) or establishing (a wide view of the new place); leave it empty for the first scene."""

PRESENCE_SYSTEM = """You read one scene of a novel and say who is physically IN the scene and who is only talked about.
Answer with JSON: present, referenced.
present: every person (or group such as "elders", "besiegers", "servants") whose body is in the place of the scene.
referenced: people who are only named, discussed, remembered, thought about or planned for, and are not in the room.
A person who is spoken about by those present is referenced, not present, even if they are the topic of the whole scene.
Scenery, weather, objects and places are not people: if nobody is in the scene yet, answer with empty lists.
A person whose name appears only inside other people's speech or thoughts, or who is described by report, is referenced.
The person whose own thoughts or memories the scene shows is present.
Use names as the text gives them. Name a group of people in lower case ("elders"). Do not invent people the text does not mention."""


def build_scene_prompt(inp: ChapterInput) -> str:
    rows = []
    for b in inp.block_ids:
        t = inp.blocks[b].strip().replace("\n", " ")
        rows.append(f"[b{b}] {t[:110]}{' ...' if len(t) > 110 else ''}")
    return "CHAPTER BLOCKS (each line is the start of one block):\n" + "\n".join(rows) + "\nOUTPUT:"


def build_presence_prompt(inp: ChapterInput, sc) -> str:  # type: ignore[no-untyped-def]
    rows = []
    for b in inp.block_ids:
        if sc.block_from <= b <= sc.block_to:
            t = inp.blocks[b].strip().replace("\n", " ")
            rows.append(t[:220] + (" ..." if len(t) > 220 else ""))
    return (
        f"SCENE: {sc.place or 'place not stated'}; {sc.story_time or 'time not stated'}.\n"
        "SCENE TEXT:\n" + "\n".join(rows) + "\nOUTPUT:"
    )


def render_example(ex: dict) -> str:
    inp = [
        "PASSAGE STARTS THE CHAPTER." if ex.get("chapter_start") else "PASSAGE CONTINUES THE CHAPTER.",
        _people([(n, lk) for n, lk in ex["present"]], ex["referenced"], fixed=True),
        "TEXT:",
        render_lines([Line(x["id"], x["block"], x["kind"], x["text"], None, x.get("speaker", "")) for x in ex["lines"]]),
    ]
    return "INPUT:\n" + "\n".join(inp) + "\nOUTPUT:\n" + json.dumps({k: v for k, v in ex["output"].items() if k != "scenes"}, ensure_ascii=False, separators=(",", ":"))


def build_prompt(
    inp: ChapterInput,
    lines: list[Line],
    roster_in_play: list[RosterEntry],
    present_names: list[str],
    referenced_names: list[str],
    *,
    chapter_start: bool,
    fixed_presence: bool,
    carry: str,
    scene_line: str = "",
    n_examples: int | None = None,
    cards: list[Card] | None = None,
    brief_block: str = "",
    lookahead: str = "",
    budget_tokens: int | None = None,
) -> str:
    """The window prompt as budgeted parts. With `cards` the people section is the card list (v2); without, the v1 lines.

    Priority when the budget is short (cards.assemble): few-shots go first, then lookahead and the future brief, then the
    poorer fields of low-ranked cards, then whole low-ranked cards. Rules, fixed scene line and the text never drop."""
    if n_examples is None:
        n_examples = int(os.environ.get("ECHOTALES_STORYBOARD_SHOTS", "3"))
    parts: list[Part] = []
    shots = load_fewshots()[:n_examples]
    if shots:
        ex = ["EXAMPLES (invented or public-domain text; the pattern matters, not the story):"]
        for i, e in enumerate(shots, 1):
            ex.append(f"--- example {i}\n{render_example(e)}")
        ex.append("--- now the real passage")
        parts.append(Part("\n".join(ex), priority=0, name="examples"))
    head = ["INPUT:", "PASSAGE STARTS THE CHAPTER." if chapter_start else "PASSAGE CONTINUES THE CHAPTER."]
    if scene_line:
        head.append(scene_line)
    if carry:
        head.append(f"BEFORE THIS PASSAGE: {carry}")
    parts.append(Part("\n".join(head), mandatory=True, name="head"))
    if cards is not None:
        parts.append(Part("CARDS (present people are in the room; talked-about people are not):", mandatory=True, name="cards-head"))
        for c in cards:
            parts.append(Part(c.variants(), priority=10 + c.rank, name=f"card:{c.name}"))
        if not cards:
            parts.append(Part("  - (nobody listed; crowd and unnamed people may still appear)", mandatory=True, name="cards-none"))
        else:
            parts.append(Part("ONLY TALKED ABOUT = status referenced; PRESENT = " + ", ".join(c.name for c in cards if c.status == "present"),
                              mandatory=True, name="cards-key"))
    else:
        by_name = {r.name: r for r in roster_in_play}
        people = [(n, by_name[n].look if n in by_name else "") for n in present_names] if fixed_presence else [(r.name, r.look) for r in roster_in_play]
        parts.append(Part(_people(people, referenced_names, fixed=fixed_presence), mandatory=True, name="people"))
    if brief_block:
        parts.append(Part(brief_block, priority=5, name="brief"))
    parts.append(Part("TEXT:\n" + render_lines(lines), mandatory=True, name="text"))
    if lookahead:
        parts.append(Part("NEXT (not part of this passage; do not draw it, use it to know what is coming):\n" + lookahead, priority=4, name="lookahead"))
    parts.append(Part("OUTPUT:", mandatory=True, name="output"))
    asm = assemble(parts, budget_tokens if budget_tokens is not None else 10**9)
    last_assembly.update(dropped=asm.dropped, shrunk=asm.shrunk, tokens=asm.tokens)
    return asm.text


#: What the last `build_prompt` call had to drop or shrink; read by the director to report budget pressure per run.
last_assembly: dict = {"dropped": [], "shrunk": [], "tokens": 0}


def schema_name() -> str:
    return LWindow.__name__
