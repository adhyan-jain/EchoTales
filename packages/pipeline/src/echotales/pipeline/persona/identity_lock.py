"""One locked identity per character per appearance interval: the wording every panel of that interval repeats.

Why (Opus review of the 2026-11-20 round-2 sheets): RI's Fang Yuan changed robe (dark, white, teal) and hair (topknot,
loose) inside one 13-panel scene because the identity sentence carried only hair colour and eyes, so the image model
chose the clothes and the hair style fresh on every panel; the text's "deep green robes torn to shreds" never reached the
prompt; and LotM's lead was brown-haired in 16 of 16 panels where block 36 says "Black hair, brown eyes", because the
graph held no hair fact for him and a genre default (brown) filled the gap. Z-Image Turbo has no CFG, so what is not in
the prompt, early, is the model's choice.

What an interval is: a persona (body) epoch, within which the appearance facts valid at the panel's position
(`reference_gen.appearance_of`, position-scoped so a later reveal never leaks) give hair, eyes, build and marks; then a
scene overlay for what the text of THIS scene states about clothes and condition (torn robes, blood). Whatever neither
states is chosen ONCE from a small genre table by a stable hash of the self id and stored (`derived_artifact`, empty
read set like `long_series` baselines), so a later change to this table cannot re-roll a character already drawn.
An approved reference sheet outranks all of it: the description that was approved is the one locked.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

TIER = "IDENTITY"

#: (length, how it is worn) per genre flavour and gender. A character with no stated hair gets ONE of these for good.
_HAIR_DEFAULTS: dict[tuple[bool, str], tuple[tuple[str, str], ...]] = {
    (True, "male"): (("long", "tied up in a topknot with a hairpin"), ("long", "tied up in a topknot with a hairpin"),
                     ("long", "worn loose over the shoulders")),
    (True, "female"): (("long", "pinned up with a hairpin"), ("long", "worn loose down the back"),
                       ("shoulder-length", "tied back with a ribbon")),
    (False, "male"): (("short", "neatly combed"), ("short", "swept back"), ("medium-length", "combed to one side")),
    (False, "female"): (("long", "pinned up at the back"), ("shoulder-length", "worn loose"),
                        ("long", "braided over one shoulder")),
}
_COLOURS = ("dark navy", "charcoal grey", "deep brown", "black", "dark green", "deep maroon")
_GARMENT = {
    (True, "male"): "hanfu robe with wide sleeves and a plain sash",
    (True, "female"): "layered hanfu dress with a plain sash",
    (False, "male"): "frock coat and waistcoat over a white shirt",
    (False, "female"): "long dress with a high collar",
}
_BUILD = {"male": ("a lean build", "a lean build", "an average build"), "female": ("a slender build",)}


def _pick(seed: str, options: tuple[Any, ...], salt: str) -> Any:
    return options[int(hashlib.md5(f"{salt}:{seed}".encode()).hexdigest(), 16) % len(options)]


def choose_defaults(self_id: str, gender: str, manhua: bool) -> dict[str, str]:
    """What a character gets where no fact states it. Deterministic in the self id, so two runs agree even before the
    choice is stored."""
    g = gender if gender in ("male", "female") else "male"
    length, style = _pick(self_id, _HAIR_DEFAULTS[(manhua, g)], "hair")
    return {
        "hair_length": length, "hair_style": style, "outfit_colour": _pick(self_id, _COLOURS, "colour"),
        "garment": _GARMENT[(manhua, g)], "build": _pick(self_id, _BUILD[g], "build"),
    }


def stored_defaults(store: object, persona_id: str, self_id: str, gender: str, manhua: bool) -> dict[str, str]:
    """The persona's defaults, chosen and stored on first use and read back every time after."""
    aid = f"identity_default:{persona_id}"
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (aid,)).fetchone()  # type: ignore[attr-defined]
    if row is not None:
        stored: dict[str, str] = json.loads(row["payload_json"])
        return stored
    chosen = choose_defaults(self_id, gender, manhua)
    store.record_artifact(aid, TIER, [], "", json.dumps(chosen))  # type: ignore[attr-defined]
    store.conn.commit()  # type: ignore[attr-defined]
    return chosen


@dataclass(frozen=True, slots=True)
class LockedIdentity:
    """The fixed description of one character in one interval. `state` is the only scene-dependent part."""

    persona_id: str
    hair: str
    eyes: str
    build: str
    outfit: str
    marks: str = ""
    #: What the scene's own text says about this body: "robes torn to shreds, hair disheveled, blood on the face".
    state: str = ""
    #: field -> "text" | "default" | "sheet" | "scene": where each part came from, for `audit` and the Studio.
    source: dict[str, str] = field(default_factory=dict)

    def description(self) -> str:
        """The part after the name and age: hair, eyes, build, clothes, then the stated state."""
        feats = [x for x in (self.hair, self.eyes, self.build, self.marks) if x]
        text = ", ".join(feats[:-1]) + " and " + feats[-1] if len(feats) > 1 else "".join(feats)
        if self.outfit:
            text += f", wearing {self.outfit}"
        if self.state:
            text += f", {self.state}"
        return text

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> LockedIdentity:
        d = json.loads(raw)
        return cls(**{k: d.get(k, "" if k != "source" else {}) for k in cls.__dataclass_fields__})


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("_", " ")).strip().strip(",.")


def build_lock(
    persona_id: str, facts: dict[str, str], defaults: dict[str, str], *, young: bool = False, gender: str = "male",
    scene_outfit: str = "", scene_hair: str = "", scene_state: str = "", sheet: LockedIdentity | None = None,
    genre: dict[str, str] | None = None,
) -> LockedIdentity:
    """Merge, in this order of authority: an approved sheet, this scene's text (clothes, hair, state), the position-scoped
    graph facts, the stored defaults. Pure: the same inputs give the same words, which is the whole point."""
    src: dict[str, str] = {}
    genre = genre or {}
    colour = _plain(facts.get("hair_color", "")) or _plain(genre.get("hair_color", ""))
    style = _plain(facts.get("hair_style", ""))
    if sheet is not None:
        hair, src["hair"] = sheet.hair, "sheet"
    elif scene_hair:
        hair, src["hair"] = _plain(scene_hair), "scene"
        if "hair" not in hair.casefold():  # a bare colour or style ("Black") must still read as hair after "with"
            hair = f"{hair.casefold()} hair"
    elif style:
        # A stated style is often a whole phrase ("very long straight hair down to the waist"): never "... waist hair".
        hair = f"{colour} {style}".strip()
        hair = hair if "hair" in style.casefold() else f"{hair} hair"
        src["hair"] = "text"
    else:
        # Colour stated or not, the length and style are the character's own fixed pick, so they cannot re-roll per panel.
        hair = f"{defaults['hair_length']} {colour or 'black'} hair {defaults['hair_style']}"
        src["hair"] = "default" if not facts.get("hair_color") else "text+default"
    eye = _plain(facts.get("eye_color", "")) or _plain(genre.get("eye_color", ""))
    eyes = sheet.eyes if sheet is not None else (f"{eye} eyes" if eye else "")
    src["eyes"] = "sheet" if sheet is not None else ("text" if facts.get("eye_color") else "default" if eye else "absent")
    stated_build = _plain(facts.get("height_build", ""))
    if sheet is not None:
        build, src["build"] = sheet.build, "sheet"
    elif stated_build:
        # "lean", "tall and thin" or a full phrase: always something that reads after "with".
        build = stated_build if stated_build.startswith(("a ", "an ")) else (
            f"a {stated_build} build" if " " not in stated_build else f"a {stated_build}")
        src["build"] = "text"
    else:
        build = "a slim boyish build" if young else defaults["build"]
        src["build"] = "default"
    outfit_fact = _plain(facts.get("typical_attire", ""))
    if scene_outfit:
        outfit, src["outfit"] = _plain(scene_outfit), "scene"
    elif sheet is not None:
        outfit, src["outfit"] = sheet.outfit, "sheet"
    elif outfit_fact:
        outfit, src["outfit"] = outfit_fact, "text"
    else:
        outfit, src["outfit"] = f"a {defaults['outfit_colour']} {defaults['garment']}", "default"
    marks = sheet.marks if sheet is not None else _plain(facts.get("distinguishing_features", ""))
    return LockedIdentity(
        persona_id=persona_id, hair=hair, eyes=eyes, build=build, outfit=outfit, marks=marks,
        state=_plain(scene_state), source=src,
    )


# ---------------------------------------------------------------------------
# what a scene's own text says about a character's clothes and condition
# ---------------------------------------------------------------------------


class CharacterLook(BaseModel):
    outfit: str = Field(default="")
    hair: str = Field(default="")
    condition: str = Field(default="")


LOOK_SYSTEM = (
    "You read ONE scene of a novel and report only what its text states about how ONE named character looks in this scene. "
    "outfit: the garment and its colour exactly as stated (\"deep green robes\"); empty if the scene does not say. "
    "hair: the hair's colour, length or style if stated, never its condition; empty if not stated. "
    "condition: damage or state of the body or clothes the text states (\"robes torn to shreds, hair disheveled, "
    "blood on the face\"); empty if none. Never guess from the genre, never add what the text does not say. "
    "Return JSON with keys outfit, hair, condition."
)


@dataclass(slots=True)
class SceneContext:
    """One scene's text and key, and the client that may read it. `client=None` (the image pass) only reads what the
    director pass stored."""

    key: str
    text: str
    client: object | None = None
    novel_id: str = ""


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", text.casefold())}


def grounded_look(look: CharacterLook, scene_text: str) -> CharacterLook:
    """Keep a field only when at least one of its content words is in the scene text: a small model fills these from the
    genre when the text is silent (a white robe on a scene that names none)."""
    have = _stems(scene_text)
    keep = {k: v for k, v in look.model_dump().items() if v.strip() and _stems(v) & have}
    return CharacterLook(**keep)


#: Characters of scene text one look call reads. A scene can be a whole chapter (LotM ch1 is one 40-block scene), and the
#: first call read only its first 2,600 characters: "a linen shirt" at block 36 was never seen and the lock fell to a genre
#: default (EVOLUTION 4.171).
LOOK_WINDOW = 2600
LOOK_MAX_WINDOWS = 8


def _look_windows(text: str) -> list[str]:
    """The scene text cut at sentence ends into windows of at most `LOOK_WINDOW` characters (a sentence longer than that is
    cut where it stands), at most `LOOK_MAX_WINDOWS` of them."""
    out: list[str] = []
    cur = ""
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(sent) > LOOK_WINDOW:
            if cur:
                out.append(cur)
                cur = ""
            out.append(sent[:LOOK_WINDOW])
            sent = sent[LOOK_WINDOW:]
        if cur and len(cur) + 1 + len(sent) > LOOK_WINDOW:
            out.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out[:LOOK_MAX_WINDOWS]


def _ask_look(store: object, ctx: SceneContext, persona_id: str, name: str, window: str, aid: str) -> CharacterLook | None:
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (aid,)).fetchone()  # type: ignore[attr-defined]
    if row is not None:
        return CharacterLook(**json.loads(row["payload_json"]))
    if ctx.client is None:
        return None
    from echotales.pipeline.llm.tasks import Task

    prompt = f"Character: {name}\nScene text:\n{window}\n\nReturn only JSON with keys outfit, hair, condition."
    try:
        result = ctx.client.complete(Task.PANEL_DIRECTION, prompt, CharacterLook, system=LOOK_SYSTEM, novel_id=ctx.novel_id)  # type: ignore[attr-defined]
    except Exception as exc:
        log.warning("scene look for %s failed: %s", name, exc)
        return None
    if not isinstance(result.value, CharacterLook):  # a client that answers every task with one canned object
        return None
    look = grounded_look(result.value, window)
    store.record_artifact(aid, TIER, [], "", json.dumps(look.model_dump()))  # type: ignore[attr-defined]
    store.conn.commit()  # type: ignore[attr-defined]
    return look


def scene_look(store: object, ctx: SceneContext | None, persona_id: str, name: str) -> CharacterLook | None:
    """This character's stated look in this scene: stored, else asked once per window of the scene text and stored. None when
    there is nothing to read (no scene, no stored answer, no client).

    Clothes and hair are the first window that states them (one scene, one outfit, as the lock is chosen once); the condition
    is the first window's only, because a wound stated at the end of a scene must not be drawn on its first panel."""
    if ctx is None or not ctx.text.strip():
        return None
    base = f"identity_look:{persona_id}:{ctx.key}"
    looks: list[CharacterLook] = []
    for n, window in enumerate(_look_windows(ctx.text)):
        got = _ask_look(store, ctx, persona_id, name, window, base if n == 0 else f"{base}#w{n}")
        if got is None:
            if n == 0:
                return None
            continue
        looks.append(got)
    if not looks:
        return None
    return CharacterLook(
        outfit=next((x.outfit for x in looks if x.outfit), ""),
        hair=next((x.hair for x in looks if x.hair), ""),
        condition=looks[0].condition,
    )


def resolve_look(store: object, ctx: SceneContext | None, persona_id: str, name: str) -> CharacterLook | None:
    """This scene's look, completed from the neighbouring scenes of the same chapter and body.

    One body in one continuous stretch of story is one outfit: RI ch1's first two scenes (the shouted ultimatum) state no
    clothes and the third says deep green robes torn to shreds, so scenes 0 and 1 were drawn in a default charcoal robe
    while scene 2 was green. Clothes and hair a scene does not state are taken from the nearest scene that states them
    (the previous one first, else the next); a wound or tearing is a state that begins where it is stated, so it is only
    carried forward."""
    own = scene_look(store, ctx, persona_id, name)
    if ctx is None or own is None:
        return own
    chapter, _, first = ctx.key.partition(":")
    if not re.fullmatch(r"\d+", first):
        return own
    here = int(first)
    prefix = f"identity_look:{persona_id}:{chapter}:"
    others: list[tuple[int, CharacterLook]] = []
    for row in store.conn.execute("SELECT id, payload_json FROM derived_artifact WHERE id LIKE ?", (prefix + "%",)):  # type: ignore[attr-defined]
        tail = row["id"][len(prefix):]
        if re.fullmatch(r"\d+", tail) and int(tail) != here:
            others.append((int(tail), CharacterLook(**json.loads(row["payload_json"]))))
    before = sorted((o for o in others if o[0] < here), key=lambda o: -o[0])
    after = sorted((o for o in others if o[0] > here), key=lambda o: o[0])

    def pick(field_name: str, pools: list[list[tuple[int, CharacterLook]]]) -> str:
        for pool in pools:
            for _b, look in pool:
                if getattr(look, field_name):
                    return str(getattr(look, field_name))
        return ""

    return CharacterLook(
        outfit=own.outfit or pick("outfit", [before, after]),
        hair=own.hair or pick("hair", [before, after]),
        condition=own.condition or pick("condition", [before]),
    )


def approved_sheet_lock(store: object, novel_id: str, persona_id: str) -> LockedIdentity | None:
    """The identity an approved reference sheet of this persona was generated from (`identity_sheet:<candidate id>`)."""
    row = store.conn.execute(  # type: ignore[attr-defined]
        "SELECT id FROM ref_image_candidate WHERE novel_id=? AND persona_id=? AND selected=1 AND role='sheet'"
        " ORDER BY found_at DESC", (novel_id, persona_id),
    ).fetchone()
    if row is None:
        return None
    art = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (f"identity_sheet:{row['id']}",)).fetchone()  # type: ignore[attr-defined]
    return LockedIdentity.from_json(art["payload_json"]) if art is not None else None


def lock_for(
    store: object, novel_id: str, self_id: str, persona_id: str, *, facts: dict[str, str], gender: str, young: bool,
    name: str, manhua: bool, scene: SceneContext | None = None, genre: dict[str, str] | None = None,
) -> LockedIdentity:
    """The locked identity of this character at this panel's position, in this scene."""
    defaults = stored_defaults(store, persona_id, self_id, gender, manhua)
    look = resolve_look(store, scene, persona_id, name)
    return build_lock(
        persona_id, facts, defaults, young=young, gender=gender,
        scene_outfit=look.outfit if look else "", scene_hair=look.hair if look else "",
        scene_state=look.condition if look else "", sheet=approved_sheet_lock(store, novel_id, persona_id), genre=genre,
    )
