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

from echotales.pipeline.storyboard.inputs import ChapterInput, Line, RosterEntry
from echotales.pipeline.storyboard.plan_schema import LWindow

PROMPT_VERSION = "sb-4"
MAX_NARRATION_CHARS = 300

SYSTEM = """You are the storyboard artist adapting a web-novel chapter into a manhwa (vertical-scroll comic). You decide
the list of panels for the passage you are given, the way a professional adapter would: by drama, not by paragraph.

Answer with one JSON object: panels, cut_lines. Refer to source text only by its tag (s12), never retype it.

GRAMMAR (follow every rule):
1. HOOK. If the passage starts the chapter, the first panel is purpose cold_open: a striking image or a sound-effect
   spread, before any explanation.
2. LAYER. Set each panel's layer: present, past (flashback shown straight), memory (a character remembering),
   lore (narrated history), imagined (someone pictured or talked about), dream. One scene, one layer.
3. CUTS. When the passage opens with a cut into a new scene (it will say so), its first panel is a time_place_card, a
   transition (a graphic match) or an establishing wide panel, then a detail insert, then people.
4. PRESENCE. Only people physically in the scene go in a panel's cast. A person who is only talked about, remembered
   or planned for goes in a referenced_inset panel (layer imagined or memory), never standing in the room.
5. DENSITY. Drama decides panel count, not text length. A peak beat (a shout, a reveal, an attack, a decision) gets
   3-5 panels: the line, a face, a reaction, an insert. Quiet explanation shrinks to one caption panel or is skipped
   by simply not lettering it. Every spoken line must appear in some panel unless you list it in cut_lines with a reason.
6. CROWDS. A crowd that speaks is shown as individuals: one crowd_individual panel per speaking face (cast: a short
   description such as "a bearded elder"), carrying that crowd line. Never give a crowd member a name.
7. INSERTS. Punctuate peaks with insert panels (hand, object, blood, lantern, weather) and extreme_close panels (eyes).
8. LETTERING. letters lists source lines by tag only (ref s12), never their text. Choose each line's kind: speech, shout
   (loud, spiky), whisper, dread (menacing), thought, memory, narration, poem. Put drawn sound words in sfx (at most 3
   words each) where the text implies a sound, and a card's caption in card. SFX and cards are the ONLY text you may
   write; they must come from the passage.
9. SHAPES. Vary panel shape with the beat: wide for places and crowds, tall for heroes and falls, diagonal for
   confrontations, inset for asides and referenced people, bleed for the peak, text_only for cards, standard otherwise.
10. NEVER ADD PLOT. Invented panels (inserts, reactions, cards, establishing views) show only what the text states or
    implies. They carry no new speech and no new facts. Mark them invented true with a one-phrase reason.
11. LOOKS. A person looks the way their listed look says at this point in the story; do not describe a different age or
    clothing. Use only the names in the PEOPLE list plus crowd descriptions. Mark the climax panel of each beat peak true.

Panel visuals are plain words describing the picture: no style words, no camera jargon, nothing the text does not state."""


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
) -> str:
    parts: list[str] = []
    if n_examples is None:
        n_examples = int(os.environ.get("ECHOTALES_STORYBOARD_SHOTS", "3"))
    shots = load_fewshots()[:n_examples]
    if shots:
        parts.append("EXAMPLES (invented or public-domain text; the pattern matters, not the story):")
        for i, ex in enumerate(shots, 1):
            parts.append(f"--- example {i}\n{render_example(ex)}")
        parts.append("--- now the real passage")
    by_name = {r.name: r for r in roster_in_play}
    if fixed_presence:
        people = [(n, by_name[n].look if n in by_name else "") for n in present_names]
    else:
        people = [(r.name, r.look) for r in roster_in_play]
    parts.append("INPUT:")
    parts.append("PASSAGE STARTS THE CHAPTER." if chapter_start else "PASSAGE CONTINUES THE CHAPTER.")
    if scene_line:
        parts.append(scene_line)
    if carry:
        parts.append(f"BEFORE THIS PASSAGE: {carry}")
    parts.append(_people(people, referenced_names, fixed=fixed_presence))
    parts.append("TEXT:")
    parts.append(render_lines(lines))
    parts.append("OUTPUT:")
    return "\n".join(parts)


def schema_name() -> str:
    return LWindow.__name__
