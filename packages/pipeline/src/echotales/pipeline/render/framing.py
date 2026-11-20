"""Camera framing per panel: a wide establishing shot where a place starts, close-ups on emotional beats and body-part lines,
an insert of a prop the text centres, over-the-shoulder views in an exchange, and never the same size three times running.

Why this exists (panel quality round 3, EVOLUTION 4.171). Measured on the M1 sheets: gemma2:9b emitted `shot: "medium"` for 16
of 16 LotM panels and 9 of 13 RI cliff panels, and the compiled Z-Image prompt never contained the shot at all
(`_compile_composed` read `b.shot` only to reorder two sections), so even a director that varied it would have drawn the same
medium shot. Both ends are fixed: this module decides the framing from the passage, deterministically (a 9B model told "vary the
shot" does not), and the compiler writes it as the first sentence after the style lead.

Pure logic: no model, no store. English signal words only for what a picture can show (body parts, objects, emotion words);
nothing about any one book."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Size = Literal["wide", "medium", "close"]
#: What the picture is about, finer than `size`: "" (the person), "eyes", "hands", "prop", "over-shoulder", "establishing".
Focus = Literal["", "eyes", "hands", "prop", "over-shoulder", "establishing"]


@dataclass(frozen=True, slots=True)
class Framing:
    size: Size
    angle: str = "eye-level"
    focus: Focus = ""
    #: The prop an insert is about, or the other person of an over-the-shoulder shot; "" otherwise.
    subject: str = ""
    reason: str = ""


@dataclass(slots=True)
class FramingState:
    """What the planner remembers between panels of one chapter."""

    recent: list[Framing] = field(default_factory=list)
    inserts_since: int = 99


_EYES = re.compile(r"\b(eyes?|pupils?|irises|iris|gaze[sd]?|eyeballs?|eyelids?)\b", re.I)
_HANDS = re.compile(r"\b(hands?|fingers?|fists?|palms?|knuckles)\b", re.I)

#: Concrete things a picture can centre. Broad on purpose (weapons, light sources, documents, vessels, adornments, tools): a prop
#: the director never listed (LotM b23 "A gun? A revolver?" came back with props []) is still found.
_OBJECTS = ["revolver", "pistol", "gun", "rifle", "musket", "sword", "blade", "dagger", "knife", "spear", "bow", "arrow", "axe", "staff", "wand", "sabre", "saber", "cannon", "bullet", "lamp", "lantern", "candle", "candlestick", "torch", "chandelier", "notebook", "book", "diary", "journal", "letter", "scroll", "map", "newspaper", "paper", "envelope", "contract", "ring", "necklace", "pendant", "amulet", "talisman", "bracelet", "crown", "mirror", "key", "lock", "box", "chest", "cup", "teacup", "goblet", "bottle", "vial", "flask", "jar", "pot", "bowl", "plate", "pen", "quill", "inkwell", "clock", "watch", "coin", "bag", "purse", "basket", "umbrella", "cane", "fan", "flute", "violin", "piano", "drum", "bell", "banner", "flag", "cloak", "mask", "pill", "medicine", "herb", "stone", "gem", "jewel", "orb", "cicada", "insect", "pipe", "portrait", "painting", "statue", "throne", "cage", "chain", "rope", "whip", "hammer", "shield", "armor", "armour", "helmet", "crystal", "feather", "flower", "rose"]
_OBJECT_RE = re.compile(r"\b(" + "|".join(sorted(set(_OBJECTS), key=len, reverse=True)) + r")s?\b", re.I)

_PERSON_WORDS = re.compile(r"\b(he|she|him|her|his|hers|they|them|their|i|me|my|we|us|our|you|your|himself|herself)\b", re.I)

_PLACE = re.compile(
    r"\b(room|hall|cliff|mountain|peak|valley|courtyard|forest|village|city|town|street|palace|temple|cave|garden|house|"
    r"chamber|corridor|bridge|river|lake|sea|shore|field|road|market|tavern|inn|church|tower|castle|sky|cabinet|wall)\b", re.I)

#: Emotion words that earn a close-up. Not a sentiment model: a flag that a face is the picture.
_PEAK = re.compile(
    r"(\?!|!\?|\b(?:shock\w*|stun\w*|startl\w*|astonish\w*|horrif\w*|terrif\w*|scream\w*|shout\w*|roar\w*|furious|rage|"
    r"anger|angry|glar\w*|sneer\w*|mock\w*|scorn\w*|contempt\w*|smirk\w*|laugh\w*|cried|cry|weep\w*|sob\w*|tears|trembl\w*|"
    r"gasp\w*|gaped|pain\w*|agon\w*|ache|ouch|fear\w*|afraid|frighten\w*|disbelief|incredul\w*)\b)", re.I)
_PEAK_EXPRESSION = re.compile(
    r"\b(shock\w*|stun\w*|wide|furious|fury|glare|glaring|sneer\w*|mock\w*|contempt\w*|smirk\w*|scorn\w*|laugh\w*|"
    r"tears|cry\w*|terrif\w*|fear\w*|afraid|pain\w*|agony|rage|anger\w*|disbelief|horror|screaming|clenched)\b", re.I)

_HIGH = re.compile(r"\b(knelt|kneel\w*|collaps\w*|fell|fallen|crouch\w*|cower\w*|beg\w*|crawl\w*|sank|slump\w*|defeat\w*|helpless)\b", re.I)
_LOW = re.compile(r"\b(towering|loom\w*|looked down|looking down|overlook\w*|domineering|contempt\w*|disdain\w*|sneer\w*|"
                  r"mock\w*|menac\w*|threat\w*|rose above)\b", re.I)

#: Lines of `speech.spoken_lines`: "- <speaker> says [to X]: ...".
_SAYS = re.compile(r"^- (?P<who>.+?) says(?: to (?P<to>[^:]+))?:", re.M)


_QUOTED = re.compile(r'"[^"]*"|\u201c[^\u201d]*\u201d')


def _unquoted(text: str) -> str:
    """The narration only: a body part named inside a spoken line ("Hand it over!") is not what the picture is about."""
    return _QUOTED.sub(" ", text)


def _first_sentence(text: str) -> str:
    """The first sentence, plus the second when the first is a fragment of four words or fewer ("A gun? A revolver?")."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    if not parts or not parts[0]:
        return ""
    return " ".join(parts[:2]) if len(parts[0].split()) <= 4 and len(parts) > 1 else parts[0]


def prop_in(text: str, director_props: list[str], names: list[str]) -> str:
    """The object the passage centres, '' when it centres none.

    A director-listed prop whose last word the passage names wins. Otherwise an object word in the passage's first sentence,
    when that sentence has no person in it (no name, no pronoun): "The lamp had a classical Western style." and "A gun? A
    revolver?" centre an object; "He sat at the desk." centres him."""
    low = text.lower()
    for p in director_props:
        words = [w for w in re.findall(r"[a-z]+", p.lower()) if len(w) > 2]
        if words and re.search(rf"\b{re.escape(words[-1])}", low):
            return p.strip()
    first = _first_sentence(text)
    if not first or _PERSON_WORDS.search(first) or any(n and n.lower() in first.lower() for n in names):
        return ""
    found = [m.group(1).lower() for m in _OBJECT_RE.finditer(first)]
    if not found:
        return ""
    # "A gun? A revolver?": the later, more specific word is the thing drawn.
    return found[-1] if found[0] == "gun" else found[0]


def _other_speaker(spoken: str, lead: str) -> str:
    """The name of someone other than the lead who speaks in this beat, '' when none does."""
    for m in _SAYS.finditer(spoken or ""):
        who = m.group("who").strip()
        if who.lower().startswith("someone"):
            return "the speaker"
        if lead and who.lower() != lead.lower():
            return who
    return ""


def _angle(text: str, expression: str) -> str:
    blob = f"{text} {expression}"
    if _HIGH.search(blob):
        return "high-angle"
    if _LOW.search(blob):
        return "low-angle"
    return "eye-level"


def plan_framing(
    beat_text: str,
    *,
    expression: str = "",
    director_props: list[str] | None = None,
    names: list[str] | None = None,
    spoken: str = "",
    crowd: bool = False,
    new_place: bool = False,
    state: FramingState | None = None,
) -> Framing:
    """Choose this panel's framing from its passage, then keep the sequence varied.

    Priority: a place starting (wide) > a body-part line (eyes / hands close-up) > an object the passage centres (insert, at most
    one in three) > an exchange with someone else speaking (over the shoulder) > an emotional peak (close) > a place described with
    nobody in it (wide) > the sequence's own rotation. Whatever was chosen, a size is never used a third time running."""
    state = state if state is not None else FramingState()
    names = names or []
    lead = names[0] if names else ""
    text = " ".join(beat_text.split())
    recent = state.recent
    last = recent[-1] if recent else None
    short = len(text.split()) <= 45
    narration = _unquoted(text)

    chosen: Framing | None = None
    if new_place or last is None:
        chosen = Framing("wide", focus="establishing", reason="a place starts" if new_place else "the chapter opens")
    elif short and _EYES.search(narration) and not crowd:
        chosen = Framing("close", focus="eyes", reason="the line is about eyes")
    elif short and _HANDS.search(narration) and not crowd and not _EYES.search(narration):
        chosen = Framing("close", focus="hands", reason="the line is about hands")
    elif state.inserts_since >= 2 and (obj := prop_in(text, director_props or [], names)):
        chosen = Framing("close", focus="prop", subject=obj, reason=f"the text centres the {obj}")
    elif (other := _other_speaker(spoken, lead)) and not crowd and last.focus != "over-shoulder":
        chosen = Framing("medium", focus="over-shoulder", subject=other, reason="someone else speaks to the lead")
    elif _PEAK.search(text) or _PEAK_EXPRESSION.search(expression):
        chosen = Framing("close", reason="emotional peak")
    elif not _PERSON_WORDS.search(text) and not any(n.lower() in text.lower() for n in names) and _PLACE.search(text):
        chosen = Framing("wide", reason="a place described with nobody in it")

    if chosen is None:
        # Nothing in the text asks for a size: rotate so a run of quiet panels still moves (medium, wide, close, medium ...).
        order: list[Size] = ["medium", "wide", "close"]
        chosen = Framing(order[(order.index(last.size) + 1) % 3] if last else "medium", reason="rotation")

    if len(recent) >= 2 and recent[-1].size == recent[-2].size == chosen.size and chosen.focus == "":
        instead: Size = "close" if chosen.size == "medium" else "medium"
        chosen = Framing(instead, reason=f"{chosen.reason}; varied after two {chosen.size}")
    angle = "over-the-shoulder" if chosen.focus == "over-shoulder" else _angle(text, expression)
    chosen = Framing(chosen.size, angle, chosen.focus, chosen.subject, chosen.reason)
    state.recent.append(chosen)
    state.inserts_since = 0 if chosen.focus == "prop" else state.inserts_since + 1
    return chosen


_ANGLE_TEXT = {
    "low-angle": ", seen from a low angle looking up",
    "high-angle": ", seen from a high angle looking down",
    "dutch-angle": ", with a tilted dutch angle",
    "birds-eye": ", seen from directly above",
}


def framing_sentence(f: Framing, lead: str, *, people: bool = True) -> str:
    """One plain sentence naming the shot, written for a language-model text encoder (Z-Image has no CFG: what comes first and
    plainly is what holds)."""
    who = lead or "the character"
    angle = _ANGLE_TEXT.get(f.angle, "")
    if f.focus == "prop":
        return f"Insert shot: a close view of the {f.subject} alone, filling the frame, nobody in the picture{angle}."
    if f.focus == "eyes":
        return f"Extreme close-up on {who}'s eyes and brow, the eyes filling the frame, the rest of the face cropped{angle}."
    if f.focus == "hands":
        return f"Close-up on {who}'s hands and what they hold, filling the frame, the face out of the picture{angle}."
    if f.focus == "over-shoulder":
        other = f.subject if f.subject and f.subject != "the speaker" else "the other person"
        return (f"Over-the-shoulder shot: the back of {other}'s head and shoulder at the edge of the frame in the foreground, "
                f"{who}'s face turned toward the viewer beyond it.")
    if f.focus == "establishing" or f.size == "wide":
        return (f"Wide establishing shot from far back{angle}: the whole place fills the frame and "
                f"{'any people are small in it' if people else 'it is empty of people'}.")
    if f.size == "close":
        return f"Close-up portrait of {who}, head and shoulders filling the frame, the face large and clearly drawn{angle}."
    return f"Medium shot of {who} from the waist up{angle}."


def staging_set(staging: str) -> str:
    """The Set clause of a staging sheet, lower-cased, '' when there is none: what "the place" is for deciding that a place started."""
    m = re.search(r"\bSet:\s*(.*?)(?=\s+(?:Blocking|Light):|\Z)", staging or "", re.S)
    return " ".join(m.group(1).lower().split()) if m else ""


def apply_framing(direction: object, f: Framing, lead: str) -> object:
    """The director's `PanelDirection` with this framing written into it (`shot`, `camera_angle`, `frame`, `frame_focus`).
    A copy: the cached direction stays what the model said, so a change of rule re-frames without re-asking."""
    return direction.model_copy(update={  # type: ignore[attr-defined]
        "shot": f.size, "camera_angle": f.angle if f.angle != "over-the-shoulder" else "eye-level",
        "frame": framing_sentence(f, lead, people=f.focus != "prop"), "frame_focus": f.focus,
    })
