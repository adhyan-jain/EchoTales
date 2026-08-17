"""Hand-picked reference images, matched to a scene by what it contains.

`persona/reference_gen.py` generates a sheet per *character*, which fixes
identity drift and nothing else. It has no answer for the two failures that
survived ten rounds of prompt work: a composition the model cannot be talked
into (one figure facing an army, read as scale rather than as a brawl), and a
locale it renders generically (an ancestral hall that comes out as a moonlit
courtyard). Both are things a picture states in one shot and a 77-token CLIP
prompt cannot state at all.

So this module is the second, hand-curated half of the reference story: a
small fixed set of images collected for *this* novel, sitting in
`data/scene-references/`, selected per panel by keyword and by what the panel
already knows about itself (is there a mob? is it a close-up?) and handed to
the same IP-Adapter slot the character sheets use.

**Composition references are only useful on shots that have a composition
problem.** A close-up of one face does not need to be told where to put
people, and conditioning it on a wide army shot actively fights the character
sheet for that face -- so `match_scene_references` returns nothing for those
by design, the same way `render_panels` already drops sheets on a crowd wide.

Missing files are not an error. The set is curated by hand and grows as
scenes come up; a slug with no file behind it is simply not matched, and the
panel falls back to prompt-only exactly as it does for a character with no
sheet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Where the curated images live. Novel-scoped output lives under
#: `data/RI/` (see `pipeline/paths.py`), but these are *inputs* -- collected
#: by hand, not generated, and never versioned per run -- so they sit in
#: their own top-level directory rather than in a novel's output tree.
SCENE_REFERENCE_DIR = Path("data/scene-references")


@dataclass(frozen=True, slots=True)
class SceneReference:
    """One curated image and the scenes it speaks to."""

    slug: str
    #: Stem-matched against the scene's prose, lowercased. Stems rather than
    #: whole words for the same reason `render/motion.py` uses them: "sects"
    #: and "sect's" are the same cue.
    keywords: tuple[str, ...] = ()
    #: Require a crowd/mob in the panel. The one-vs-many images are actively
    #: wrong on a two-person scene -- they would invent an army.
    requires_mob: bool = False
    #: Skip on close-ups. See the module docstring.
    wide_only: bool = True


#: The curated set, in priority order -- the first match wins, so the most
#: specific compositions are listed before the general locales.
SCENE_REFERENCES: tuple[SceneReference, ...] = (
    SceneReference(
        "one-vs-many-01",
        keywords=("surround", "besieg", "outnumber", "army", "horde", "encircl"),
        requires_mob=True,
    ),
    SceneReference("one-vs-many-02", keywords=("crowd", "mob", "elders", "disciples"), requires_mob=True),
    SceneReference("river-of-time-01", keywords=("river of time", "time flow", "reincarnat")),
    SceneReference("ancestral-hall-destroyed-01", keywords=("hall lay in ruins", "ruined hall", "wrecked")),
    SceneReference("ancestral-hall-exterior-01", keywords=("ancestral hall", "clan hall", "ancestral")),
    SceneReference("twins-duel-01", keywords=("fang zheng",)),
    SceneReference("bai-ning-bing-01", keywords=("bai ning bing",)),
    SceneReference("mountain-sect-01", keywords=("mountain", "peak", "cliff", "summit")),
    SceneReference("mountain-sect-02", keywords=("sect", "pavilion", "courtyard")),
    SceneReference("mountain-sect-03", keywords=("village", "valley", "gate")),
)

#: Character slug -> curated portrait, consulted *before* the generated
#: sheet. These were collected precisely because the generated Fang Yuan
#: sheets read as a bulked, righteous warrior rather than a lean man with
#: eyes "deep and black like an abyss", and a picture settles that argument
#: in a way a prompt clause has repeatedly failed to.
CHARACTER_REFERENCES: dict[str, tuple[str, ...]] = {
    "fang yuan": ("fang-yuan-ref-01", "fang-yuan-cicada-01"),
    "fang zheng": ("twins-duel-01",),
    "bai ning bing": ("bai-ning-bing-01",),
}

#: Curated portraits that only apply at a point in the story. Fang Yuan is
#: an eighty-year-old demon in a fifteen-year-old's body for most of arc one,
#: and the youth image is wrong the moment he is not.
YOUTH_REFERENCES: dict[str, str] = {"fang yuan": "fang-yuan-young-01"}

#: Story position (chapter, fractional -- same convention as
#: `character_looks`) below which `YOUTH_REFERENCES` wins.
YOUTH_UNTIL_CHAPTER: float = 60.0

_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def _resolve(slug: str, root: Path) -> Path | None:
    for suffix in _SUFFIXES:
        candidate = root / f"{slug}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _mentions(text: str, keyword: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(keyword)}\w*", text) is not None


def match_scene_references(
    text: str,
    *,
    has_mob: bool = False,
    closeup: bool = False,
    limit: int = 1,
    root: Path | str = SCENE_REFERENCE_DIR,
) -> list[Path]:
    """Curated composition/locale references for this panel, best first.

    `limit` defaults to 1: IP-Adapter averages its conditioning images, so a
    second composition reference does not add detail, it blurs the first one
    into it -- the same reason `MangaDiffusersEngine.max_references` is 2 and
    not 5.
    """
    root = Path(root)
    if closeup:
        return []

    blob = text.casefold()
    out: list[Path] = []
    for ref in SCENE_REFERENCES:
        if ref.requires_mob and not has_mob:
            continue
        if not any(_mentions(blob, kw) for kw in ref.keywords):
            continue
        path = _resolve(ref.slug, root)
        if path is not None and path not in out:
            out.append(path)
        if len(out) >= limit:
            break
    return out


def curated_character_reference(
    label: str,
    *,
    chapter: float = 0.0,
    root: Path | str = SCENE_REFERENCE_DIR,
) -> Path | None:
    """A hand-picked portrait for this character, if one exists.

    Returns None -- rather than raising or warning -- for every character
    without one, which is nearly all of them; the caller falls back to the
    generated sheet.
    """
    root = Path(root)
    key = label.casefold().strip()

    if chapter and chapter < YOUTH_UNTIL_CHAPTER:
        youth = YOUTH_REFERENCES.get(key)
        if youth is not None:
            path = _resolve(youth, root)
            if path is not None:
                return path

    for slug in CHARACTER_REFERENCES.get(key, ()):
        path = _resolve(slug, root)
        if path is not None:
            return path
    return None
