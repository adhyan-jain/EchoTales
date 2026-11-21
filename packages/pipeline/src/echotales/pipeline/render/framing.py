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
Focus = Literal["", "eyes", "hands", "prop", "over-shoulder", "establishing", "behind", "topdown", "reverse", "overview", "low", "down", "profile"]


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
    #: How many panels took a crowd view, so the crowd scene walks `_CROWD_VIEWS` instead of repeating one picture.
    crowd_n: int = 0


_EYES = re.compile(r"\b(eyes?|pupils?|irises|iris|gaze[sd]?|eyeballs?|eyelids?)\b", re.I)
_HANDS = re.compile(r"\b(hands?|fingers?|fists?|palms?|knuckles)\b", re.I)

#: Concrete things a picture can centre. Broad on purpose (weapons, light sources, documents, vessels, adornments, tools): a prop
#: the director never listed (LotM b23 "A gun? A revolver?" came back with props []) is still found.
_OBJECTS = ["revolver", "pistol", "gun", "rifle", "musket", "sword", "blade", "dagger", "knife", "spear", "bow", "arrow", "axe", "staff", "wand", "sabre", "saber", "cannon", "bullet", "lamp", "lantern", "candle", "candlestick", "torch", "chandelier", "notebook", "book", "diary", "journal", "letter", "scroll", "map", "newspaper", "paper", "envelope", "contract", "ring", "necklace", "pendant", "amulet", "talisman", "bracelet", "crown", "mirror", "key", "lock", "box", "chest", "cup", "teacup", "goblet", "bottle", "vial", "flask", "jar", "pot", "bowl", "plate", "pen", "quill", "inkwell", "clock", "watch", "coin", "bag", "purse", "basket", "umbrella", "cane", "fan", "flute", "violin", "piano", "drum", "bell", "banner", "flag", "cloak", "mask", "pill", "medicine", "herb", "stone", "gem", "jewel", "orb", "cicada", "insect", "pipe", "portrait", "painting", "statue", "throne", "cage", "chain", "rope", "whip", "hammer", "shield", "armor", "armour", "helmet", "crystal", "feather", "flower", "rose"]
_OBJECT_RE = re.compile(r"\b(" + "|".join(sorted(set(_OBJECTS), key=len, reverse=True)) + r")s?\b", re.I)

#: A list of looks ("Black hair, brown eyes, a linen shirt, thinly built") names eyes without being about them: a portrait, not a crop.
_LOOKS_LIST = re.compile(r"\b(hair|build|built|robes?|shirt|coat|dress|tall|height|features|skin|clothes|complexion)\b", re.I)

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

_HIGH = re.compile(r"\b(knelt|kneel\w*|collaps\w*|fell|fallen|crouch\w*|cower\w*|begs|begged|begging|crawl\w*|sank|slump\w*|defeat\w*|helpless)\b", re.I)
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

    Only the passage's first sentence counts (two when the first is a fragment), and only when it has no person in it (no name, no
    pronoun): "The lamp had a classical Western style." and "A gun? A revolver?" centre an object; "He sat at the desk." and
    "Hey, putting it that way, I can read my books" centre a person (a first render drew an insert of 'books' for the latter). A
    director-listed prop whose last word that sentence names is preferred to the object lexicon."""
    first = _first_sentence(text)
    if not first or _PERSON_WORDS.search(first) or any(n and n.lower() in first.lower() for n in names):
        return ""
    low = first.lower()
    for p in director_props:
        words = [w for w in re.findall(r"[a-z]+", p.lower()) if len(w) > 2]
        if words and re.search(rf"\b{re.escape(words[-1])}", low):
            return p.strip()
    found = [m.group(1).lower() for m in _OBJECT_RE.finditer(first)]
    if not found:
        return ""
    # "A gun? A revolver?": the later, more specific word is the thing drawn.
    return found[-1] if found[0] == "gun" else found[0]


#: A weapon the passage centres is a story beat and may follow another insert at once; other objects keep a panel between.
_WEAPONS = {"revolver", "pistol", "gun", "rifle", "musket", "sword", "dagger", "knife", "blade", "spear", "axe", "cannon", "sabre", "saber"}


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


#: The views a quiet run rotates through, in the order a viewer reads them as different pictures: person, over their shoulder from
#: behind, face, place, from above, eyes.
#: Round 7 (EVOLUTION 4.182): the lone lead's "behind" view and the plain medium read as one chest-up man at the desk (LotM r6), so the
#: run also takes a high over-the-shoulder look down at the desk ("down") and a profile at the window ("profile").
_CYCLE: list[tuple[str, str]] = [("medium", ""), ("close", ""), ("medium", "behind"), ("wide", ""), ("medium", "down"), ("medium", "profile"),
                                 ("close", "eyes"), ("medium", "topdown")]

#: The views a crowd scene walks, each a different picture of the same confrontation (RI cliff r6: 5 of 13 panels were the one side
#: view). Side view, reverse on the crowd with the lead out of frame, a high wide with him a lone figure, a low angle on him alone
#: against the sky, a face close-up. The first is the round-6 side view.
_CROWD_VIEWS: list[tuple[str, str]] = [("medium", "behind"), ("medium", "reverse"), ("wide", "overview"), ("medium", "low"), ("close", "")]
_CROWD_REPLACES = ("", "behind", "over-shoulder", "topdown", "down", "profile")


def _key(f: Framing) -> tuple[str, str]:
    return (f.size, f.focus)


def plan_framing(
    beat_text: str,
    *,
    expression: str = "",
    director_props: list[str] | None = None,
    names: list[str] | None = None,
    spoken: str = "",
    crowd: bool = False,
    crowd_in_scene: bool = False,
    others_present: bool = True,
    new_place: bool = False,
    opens_chapter: bool | None = None,
    state: FramingState | None = None,
) -> Framing:
    """Choose this panel's framing from its passage, then keep the sequence varied.

    Priority: a place starting (wide) > a body-part line (eyes / hands close-up) > an object the passage centres (insert, never two in a row
    unless a weapon) > an exchange with someone else speaking (over the shoulder) > an emotional peak (close) > a place described with
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
    # `opens_chapter` is for a render of a block range that starts mid-chapter (b79 "a pair of clear eyes" was drawn as an
    # establishing shot only because it was the first panel of the slice); None means "the first panel I am given".
    if opens_chapter is None:
        opens_chapter = last is None
    if new_place or opens_chapter:
        chosen = Framing("wide", focus="establishing", reason="a place starts" if new_place else "the chapter opens")
    elif short and _EYES.search(narration) and not crowd and not _LOOKS_LIST.search(_first_sentence(narration)):
        chosen = Framing("close", focus="eyes", reason="the line is about eyes")
    elif short and _HANDS.search(narration) and not crowd and not _EYES.search(narration):
        chosen = Framing("close", focus="hands", reason="the line is about hands")
    elif (obj := prop_in(text, director_props or [], names)) and (state.inserts_since >= 1 or obj in _WEAPONS):
        chosen = Framing("close", focus="prop", subject=obj, reason=f"the text centres the {obj}")
    elif others_present and (other := _other_speaker(spoken, lead)) and not crowd and not crowd_in_scene and not (last and last.focus == "over-shoulder"):
        chosen = Framing("medium", focus="over-shoulder", subject=other, reason="someone else speaks to the lead")
    elif _PEAK.search(text) or _PEAK_EXPRESSION.search(expression):
        chosen = Framing("close", reason="emotional peak")
    elif not _PERSON_WORDS.search(text) and not any(n.lower() in text.lower() for n in names) and _PLACE.search(text):
        chosen = Framing("wide", reason="a place described with nobody in it")

    soft = chosen is None or chosen.reason in ("emotional peak", "a place described with nobody in it")
    if chosen is None:
        chosen = Framing("medium", reason="rotation")
    if soft:
        # Round 5 (EVOLUTION 4.173): LotM r4 alternated medium and close over one desk, and the model drew both as the same chest-up
        # man, so a size is not a different picture. A text-driven pick (a peak, a place, nothing) that repeats the last view is
        # moved to the next view in `_CYCLE` that neither of the last two used.
        used = {_key(f) for f in recent[-2:]}
        # Round 7: a plain "rotation" pick always walks on (a 3-view loop of medium, behind, close otherwise: the last two used
        # always excluded only the view that had just been left, so the run never reached the other cycle entries).
        if (_key(chosen) in used or chosen.reason == "rotation") and last is not None:
            start = _CYCLE.index(_key(last)) + 1 if _key(last) in _CYCLE else 0
            for i in range(len(_CYCLE)):
                size, focus = _CYCLE[(start + i) % len(_CYCLE)]
                if (size, focus) not in used:
                    chosen = Framing(size, focus=focus, reason=f"{chosen.reason}; a different view after {last.size} {last.focus}".strip())  # type: ignore[arg-type]
                    break
    if (crowd or crowd_in_scene) and chosen.size in ("medium", "wide") and chosen.focus in _CROWD_REPLACES:
        # The crowd and the lead both facing the viewer read as the lead among his own people (RI cliff r5, 6 of 13 panels): from
        # behind the lead, with the crowd across a gap facing him, they read as opposed. Round 6: only the one dedicated crowd cut
        # carried `crowd`, so this never fired (12 of 13 cliff panels had a crowd in the staging); `crowd_in_scene` is the flag
        # for a crowd that is merely in the picture. Round 7: the one side view then filled 5 of 13 panels, so the crowd scene walks
        # `_CROWD_VIEWS`, never the view the last panel had.
        for i in range(len(_CROWD_VIEWS)):
            size, focus = _CROWD_VIEWS[(state.crowd_n + i) % len(_CROWD_VIEWS)]
            if (size, focus) != (_key(last) if last else None):
                state.crowd_n += i + 1
                chosen = Framing(size, focus=focus, subject="crowd" if focus else "", reason=f"{chosen.reason}; crowd view {focus or 'face'}")  # type: ignore[arg-type]
                break
    angle = _FIXED_ANGLE.get(chosen.focus) or _angle(text, expression)
    chosen = Framing(chosen.size, angle, chosen.focus, chosen.subject, chosen.reason)
    state.recent.append(chosen)
    state.inserts_since = 0 if chosen.focus == "prop" else state.inserts_since + 1
    return chosen


_FIXED_ANGLE = {"topdown": "birds-eye", "over-shoulder": "over-the-shoulder", "overview": "high-angle", "low": "low-angle", "down": "high-angle"}

_ANGLE_TEXT = {
    "low-angle": ", seen from a low angle looking up",
    "high-angle": ", seen from a high angle looking down",
    "dutch-angle": ", with a tilted dutch angle",
    "birds-eye": ", seen from directly above",
}


def framing_sentence(f: Framing, lead: str, *, people: bool = True, alone: bool = False) -> str:
    """One plain sentence naming the shot, written for a language-model text encoder (Z-Image has no CFG: what comes first and
    plainly is what holds)."""
    who = lead or "the character"
    angle = _ANGLE_TEXT.get(f.angle, "")
    if f.focus == "prop":
        # Round 5: with only "nobody in the picture" the lamp insert drew two men and the pipe insert a couple (2 of 2 LotM inserts);
        # the object is stated as the whole subject, a still life, never as a person's belonging. Round 6: even "empty of people" is a
        # person word the model draws from, so the sentence names no person at all.
        return (f"Still-life insert shot: a close view of the {f.subject} alone, an object study with the {f.subject} filling the "
                f"frame and the room only a blurred backdrop{angle}.")
    if f.focus == "eyes":
        return f"Extreme close-up on {who}'s eyes and brow, the eyes filling the frame, the rest of the face cropped{angle}."
    if f.focus == "hands":
        return f"Close-up on {who}'s hands and what they hold, filling the frame, the face out of the picture{angle}."
    if f.focus == "reverse":
        # Round 7 A/B (cliff p7, seeds 1 and 2, `out_r7_ab/ab_cliff.png`): the lead is not named so he is not drawn. With a blurred
        # shoulder in the wording the crowd faced the camera but stood calm (2 of 2); "pointing at someone just beyond the lens"
        # drew an accusing crowd (2 of 2) and no hero in the crowd.
        return ("Reverse shot at ground level from where he stands: a dense crowd of different people at close and middle distance "
                "fills the frame, their angry faces turned toward the camera, all of them glaring and pointing at someone just "
                "beyond the lens.")
    if f.focus == "overview":
        # Drew him mid-sized (not small) on bare rock with the crowd a thin ring far behind: lone, and no follower reading (2 of 2).
        return (f"High wide establishing shot looking down from far above: {who} is one small lone figure standing on bare rock, "
                "and the crowd is a loose ring of tiny people at a distance from him on the ground, the whole place visible and "
                "the figures small in it.")
    if f.focus == "low":
        # "head and shoulders ... no other person" drew him seated on the rock (2 of 2); this wording drew him standing, wind in
        # the hair, nobody else (2 of 2).
        return (f"Low angle looking up at {who} from the ground, one man alone against the open sky, upper body and face seen from "
                "below, wind in his hair.")
    if f.focus == "down" and alone:
        # Round 7 A/B: drew the man in three-quarter back view bent over the desk, one person (3 of 3), unlike round 6's "from behind".
        return (f"High over-the-shoulder view looking down: {who} sits alone, head bent over what lies on the desk in front of him, "
                "only the back of his head and shoulders at the bottom of the frame and the desk and its objects below, the rest of "
                "the room empty and quiet.")
    if f.focus == "down":
        f = Framing(f.size, f.angle, "topdown", f.subject, f.reason)
    if f.focus == "profile":
        # Round 7 A/B (LotM p4, 3 seeds, `out_r7_ab/ab_lone.png`): a lone man at a window in profile drew no second person (6 of 6);
        # standing at a tall window looking out drew a clearly different picture from the seated desk views (3 of 3), "sits at
        # the window" drew the desk view again.
        return (f"Side view of {who} alone in profile, standing at a tall window and looking out at the street, the window and the "
                "light outside filling the frame.")
    if f.focus == "behind" and f.subject == "crowd":
        # Round 6 A/B (RI cliff p3, 2 seeds each, `out_r6_ab_crowd`): "seen from behind X, the crowd across a gap facing him" drew a
        # second, front-facing X in the middle with the crowd standing around him facing the viewer (2 of 2: the camera behind him
        # IS the crowd's facing direction, so the crowd faces the viewer and he is not the one they face); "over his shoulder, the
        # crowd all glaring at him" drew him facing the viewer with the crowd behind (2 of 2). A side view with him in profile, a gap
        # of bare ground and the crowd turned toward him drew the opposed arrangement 2 of 2 (as did a profile-left, crowd-right
        # variant). The focus name "behind" is kept for the staging/compiler rules (no paragraph, no face, no Blocking).
        return (f"Wide side view with the camera at the side: {who} stands alone on the left of the frame in profile, facing right, "
                "and across a wide gap of bare ground the crowd stands on the right as a dense uneven mass of different people at "
                f"different depths, every one of them turned toward him and glaring at him{angle}.")
    if f.focus == "behind" and alone:
        # Round 6 A/B (LotM p4, 3 seeds each, `out_r6_ab_lone`): "seen from behind X at a desk" drew a second man facing the viewer
        # across the desk in 3 of 3 (also with "sits alone", 2 of 3 with "exactly one human figure"); a high corner view of the same
        # lone man drew 0 of 3. A lone lead's second-view is therefore a corner view, not a view from behind.
        return (f"Seen from a high corner of the room looking down: {who} is alone in the room, small in the frame, the furniture and "
                f"objects of the room around him, the rest of the room empty and quiet{angle}.")
    if f.focus == "behind":
        return (f"Seen from directly behind {who}: the back of his head and shoulders large in the lower foreground, he is the only "
                f"person in the picture and looks away from the viewer into the room ahead, his face hidden{angle}.")
    if f.focus == "topdown":
        return (f"High top-down view looking straight down from directly above: {who} small in the frame, the top of his head and "
                "shoulders, the table or ground around him filling the picture.")
    if f.focus == "over-shoulder":
        other = f.subject if f.subject and f.subject != "the speaker" else "one of the people around him"
        return (f"Over-the-shoulder shot: the back of the head and shoulder of {other} at the edge of the frame in the foreground, "
                f"{who} large in the middle of the frame, his face turned toward the viewer beyond it.")
    if f.focus == "establishing" or f.size == "wide":
        return (f"Wide establishing shot from far back{angle}: the whole place fills the frame and "
                f"{'any people are small in it' if people else 'it is empty of people'}.")
    if f.size == "close":
        # "the face large" and "filling the frame" drew a chibi (huge head on a small full body) in 3 of 3 RI close-ups whose
        # paragraph still described the whole scene; the crop is stated as a crop with natural proportions (round 3).
        return (f"Close-up shot cropped at the chest, natural realistic proportions: only {who}'s head, neck and shoulders are in "
                f"the picture and the place is a soft background{angle}.")
    return f"Medium shot of {who} from the waist up{angle}."


def crowd_in_scene(others: object, staging: str) -> bool:
    """True when the director's `others` is a crowd or group, or the staging sheet blocks a crowd: the crowd is in the picture even
    when this is not the dedicated crowd cut (RI cliff r5: 12 of 13 panels, one carried the crowd flag)."""
    kind = str(getattr(others, "kind", "") or "").lower()
    return bool(re.search(r"\b(crowd|group|mob|army|onlookers|elders|soldiers|villagers)\b", kind)) or bool(
        re.search(r"\bBlocking:.*\b(crowd|mob|army|onlookers)\b", staging or "", re.I | re.S))


def staging_set(staging: str) -> str:
    """The Set clause of a staging sheet, lower-cased, '' when there is none: what "the place" is for deciding that a place started."""
    m = re.search(r"\bSet:\s*(.*?)(?=\s+(?:Blocking|Light):|\Z)", staging or "", re.S)
    return " ".join(m.group(1).lower().split()) if m else ""


def apply_framing(direction: object, f: Framing, lead: str, *, alone: bool = False) -> object:
    """The director's `PanelDirection` with this framing written into it (`shot`, `camera_angle`, `frame`, `frame_focus`).
    A copy: the cached direction stays what the model said, so a change of rule re-frames without re-asking."""
    return direction.model_copy(update={  # type: ignore[attr-defined]
        "shot": f.size, "camera_angle": f.angle if f.angle != "over-the-shoulder" else "eye-level",
        "frame": framing_sentence(f, lead, people=f.focus != "prop", alone=alone), "frame_focus": f.focus,
        "frame_subject": f.subject if f.focus == "prop" else "",
    })


_FACE_SENTENCE = re.compile(
    r"\b(face|eyes?|gaze|stares?|stared|looks?|looking|expression|smile[sd]?|smirk\w*|sneer\w*|brows?|lips?|mouth|teeth|jaw|cheeks?|"
    r"tears?|blood|wounds?|hair|chin|glare\w*|grin\w*|laugh\w*|frown\w*)\b", re.I)


def crop_composition(text: str, focus: str) -> str:
    """The director's paragraph cut to what a close-up can show: the sentences about the face and the body's state, else the first
    sentence. A close-up whose paragraph still said "stands amidst the carnage, the battlefield littered with corpses" drew a huge
    head on a small full body (a chibi, 3 of 3 RI close-ups in the first round-3 render); an eye crop keeps only eye and gaze
    sentences, or nothing."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    if focus == "eyes":
        return " ".join(s for s in sentences if re.search(r"\b(eyes?|gaze|stares?|stared|glare\w*|brows?)\b", s, re.I))
    keep = [s for s in sentences if _FACE_SENTENCE.search(s)]
    return " ".join(keep or sentences[:1])
