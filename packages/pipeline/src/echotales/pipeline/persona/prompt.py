"""`PanelCast` -> one text-to-image prompt string.

`get_panel_cast` (`runner.py`) already resolved *what* is in frame and what
each element should look like; this module only has to say it in the order
a diffusion model reads best -- style and setting first (they set the frame
the rest is composited into), foreground subjects next, background last,
since a diffusion prompt weights earlier tokens more heavily than later
ones.

**Manga style is part of the contract, not a decoration.** The target output
is inked black-and-white panels, and a base photorealistic checkpoint will
produce photorealism no matter how the prompt is phrased -- the prompt says
what it wants, and `render/panels.py::MangaDiffusersEngine` is responsible
for being pointed at a checkpoint that can honour it.
"""

from __future__ import annotations

from echotales.pipeline.persona.runner import PanelCast

#: The style contract, appended to every panel prompt. Matches
#: `persona/reference_gen.py::REFERENCE_STYLE` deliberately: a panel that
#: does not share a style vocabulary with the reference sheet conditioning
#: it will fight that conditioning.
#: Shared by every shot type. What varies between them is framing, not
#: rendering.
#: **Rewritten against reference art the author selected, not from
#: intuition.** The previous vocabulary was "highly detailed, cinematic
#: lighting, rich colors, masterpiece, best quality" -- generic
#: AI-illustration boilerplate that pulls toward a glossy, saturated,
#: over-rendered look. The fan art this novel actually has, and what the
#: author asked for, is the opposite on every axis: Chinese ink painting,
#: a *limited* palette (most pieces are near-monochrome with a single
#: accent), large areas of negative space, visible brushwork, and hanfu
#: whose long sleeves and waist-length black hair are the composition.
#:
#: Two terms were actively working against that and are now negatives
#: instead: "rich colors" and "cinematic lighting". A checkpoint given both
#: renders a video-game key art frame, which is a perfectly good picture and
#: the wrong one.
_MANGA_BASE = (
    "guofeng illustration, chinese ink painting, xianxia, wuxia, "
    "ancient chinese fantasy, hanfu with long wide sleeves, "
    "flowing black hair, ink wash, muted limited palette, "
    "elegant brushwork, negative space, subtle gradients, "
    "solemn atmosphere, mature serious art style"
)

#: The few words that decide *what kind of picture this is*, kept short
#: enough to sit at the front of every prompt. The full style string is
#: appended at the end, where the token budget drops it first -- so a panel
#: that runs long loses the elaboration and keeps the medium.
STYLE_ANCHOR = "guofeng illustration, chinese ink painting, xianxia"

#: **Three framings, chosen per block -- not one style applied to all 89.**
#:
#: Real manga alternates: a wide establishing shot when the scene changes, a
#: full figure-in-environment shot for action, and a tight close-up over a
#: toned background when someone is talking or thinking. The first pass here
#: used one framing for every block, which is why an early version produced
#: 89 near-identical compositions, and a later version produced 89
#: environment shots -- including for blocks where a character is simply
#: speaking, where a landscape is the wrong picture and an expensive one.
#:
#: The close-up variant is deliberately the "floating bust over an ink wash"
#: look that an earlier pass produced *by accident* across the whole
#: chapter. It was never a bad image; it was the right image for the wrong
#: blocks.
#: **Framing is separated from the rest of the style string, and that
#: separation is load-bearing.** Framing decides the *composition* -- whether
#: this is a face or a landscape -- while the rest of the style decides how
#: it is rendered. Both used to live in one string appended at the very end
#: of the prompt, which meant the token budget dropped them together: a
#: close-up chosen for a line of dialogue came back as a full-body standing
#: portrait, because the words "close-up on the character's face" never
#: reached the model. Framing now travels near the front with the subject;
#: the rendering elaboration stays at the back where it is cheap to lose.
FRAMING_ESTABLISHING = "wide establishing shot, sweeping landscape, small distant figures"
FRAMING_SCENE = "medium shot, full scene, dynamic composition"
FRAMING_CLOSEUP = "close-up on the face, intense expression, shallow depth"

STYLE_ESTABLISHING = f"{_MANGA_BASE}, {FRAMING_ESTABLISHING}, detailed background, strong depth"

STYLE_SCENE = (
    f"{_MANGA_BASE}, {FRAMING_SCENE}, characters in a detailed environment, depth"
)

STYLE_CLOSEUP = (
    f"{_MANGA_BASE}, {FRAMING_CLOSEUP}, dramatic lighting, "
    "abstract toned background"
)

#: What each framing must *not* be, leading its negative prompt.
NEGATIVE_HEAD_BY_STYLE: dict[str, str] = {
    STYLE_ESTABLISHING: "plain background, empty background, portrait, bust shot",
    STYLE_SCENE: "plain background, simple background, white background, portrait, bust shot",
    STYLE_CLOSEUP: "full body, wide shot, crowd, tiny face",
}

#: Style string -> its short framing clause, for the budget-aware ordering
#: in `build_image_prompt`.
FRAMING_BY_STYLE: dict[str, str] = {
    STYLE_ESTABLISHING: FRAMING_ESTABLISHING,
    STYLE_SCENE: FRAMING_SCENE,
    STYLE_CLOSEUP: FRAMING_CLOSEUP,
}


def framing_for(style: str) -> str:
    """The short composition clause inside a full style string."""
    return FRAMING_BY_STYLE.get(style, FRAMING_SCENE)

#: Default when a caller does not pick -- the middle framing, which is the
#: one that is never badly wrong.
MANGA_STYLE = STYLE_SCENE

#: **Negatives are budgeted exactly like positives, and for a defect found
#: the same way.** Every negative prompt measured ~100 tokens against the
#: same 77-token limit, and because the shared base came first, the part
#: being discarded was the per-framing tail -- "plain background, portrait,
#: bust shot" -- which is precisely what stops a scene shot collapsing into
#: a standing portrait. The most-cut clause was the one doing the work.
#:
#: Ordered most-discriminating first, so what survives truncation is what
#: distinguishes this panel from the default picture the checkpoint wants
#: to draw.
_NEGATIVE_ANATOMY = "deformed hands, extra limbs, lowres, blurry"

#: Wrong medium. A checkpoint that drifts here is not making a subtle error.
_NEGATIVE_MEDIUM = "photorealistic, 3d render, western comic"

#: Named failure modes from the first real chapter: a cute-anime checkpoint
#: gave round friendly faces, cherry blossoms and decorative birds, none of
#: which belong in this novel.
_NEGATIVE_TONE = "chibi, cute, moe, kawaii, big round eyes"

#: The look the *positive* prompt used to ask for, now rejected: the
#: reference art is restrained and near-monochrome, and every one of these
#: pulls toward glossy saturated game key art instead.
_NEGATIVE_LOOK = "rich colors, oversaturated, glossy, plastic skin, lens flare"

#: Wrong culture. Cheap to state and it does fire -- an early panel came
#: back as a Japanese covered walkway.
_NEGATIVE_CULTURE = "cherry blossoms, japanese shrine, modern clothing, school uniform"

#: Artefacts. Last because they are the least likely and the least costly:
#: a watermark is fixable, a portrait where a battle should be is not.
_NEGATIVE_ARTEFACT = "watermark, text, speech bubble"

_NEGATIVE_TAIL = (
    _NEGATIVE_ANATOMY,
    _NEGATIVE_MEDIUM,
    _NEGATIVE_TONE,
    _NEGATIVE_LOOK,
    _NEGATIVE_CULTURE,
    _NEGATIVE_ARTEFACT,
)

def negative_for(style: str) -> str:
    """The negative prompt matching a framing, fitted to the token budget."""
    head = NEGATIVE_HEAD_BY_STYLE.get(style, NEGATIVE_HEAD_BY_STYLE[STYLE_SCENE])
    return fit_to_budget([head, *_NEGATIVE_TAIL])


def shot_style(
    span_types: list[str],
    *,
    scene_change: bool = False,
    resolved_subjects: int = 1,
    has_mob: bool = False,
) -> str:
    """Pick a framing from what the block actually contains.

    Establishing shots are reserved for scene changes -- used on every
    description block they would make a chapter feel like a travelogue.
    Dialogue and inner monologue get the close-up, which is both the right
    manga grammar and much the cheaper picture: a landscape rendered behind
    a line of speech is wasted work.

    **A close-up needs someone to close up on.** `resolved_subjects` is how
    many named people `get_panel_cast` actually placed in this block;
    default 1 preserves the old behaviour for every caller that hasn't been
    updated to pass it. At 0 -- an unresolved speaker, or a line whose
    subject the mention pipeline never linked -- a close-up has nothing to
    condition on and the checkpoint invents a face, which is how RI ch1's
    opening threat ("hand over the Cicada or I'll give you a quick death")
    rendered as a calm stranger smiling at the camera: no character data,
    no headcount tag, "intense expression" with nothing to be intense
    *about*. Routed to the scene shot instead, which at least asks for an
    environment rather than a face from nowhere.

    `has_mob` pulls the other way: a block `get_panel_cast` tagged with a
    background crowd (elders, warlords, guards) is a group moment even
    without a single named subject, and a scene shot showing several
    figures is the right picture for "a few people discussing tribe
    affairs" -- an establishing landscape undersells it as much as a
    single face oversells it.
    """
    kinds = set(span_types)
    if scene_change and "NARRATION_DESCRIPTION" in kinds:
        return STYLE_ESTABLISHING
    if kinds & {"DIALOGUE", "INNER_MONOLOGUE"}:
        if resolved_subjects <= 0:
            return STYLE_SCENE if has_mob else STYLE_ESTABLISHING
        return STYLE_CLOSEUP
    if "NARRATION_DESCRIPTION" in kinds and "NARRATION_ACTION" not in kinds:
        return STYLE_ESTABLISHING
    return STYLE_SCENE

#: Beat text is a *composition* cue, not a caption -- past this length it
#: stops steering the image and starts diluting the rest of the prompt.
#:
#: **Lowered from 220 after measuring against the token budget.** At 220
#: characters a beat is ~50 of the 75 available tokens, so it did not fit
#: alongside the subject and framing and was dropped whole -- which made
#: every panel of one character in one place the *same picture*, since the
#: beat is the only part of the prompt that distinguishes them. A shorter
#: cue that survives beats a fuller one that does not.
_MAX_BEAT_CHARS = 110


def summarise_beat(text: str, *, limit: int = _MAX_BEAT_CHARS) -> str:
    """Condense a block's narration into a single composition cue.

    Truncated on a sentence boundary where possible: half a sentence reads
    as noise to a diffusion model, and the first sentence of an action block
    is almost always the one describing what is happening.
    """
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    for stop in (". ", "! ", "? "):
        idx = cut.rfind(stop)
        if idx > limit // 3:
            return cut[: idx + 1].strip()
    return cut.rsplit(" ", 1)[0].strip()


def cast_tags(genders: list[str]) -> str:
    """Danbooru headcount tags for the figures in frame.

    Anime/manga checkpoints weight `1boy`/`2boys`/`1girl` far more heavily
    than any English phrasing, and without them they fall back to their
    training prior, which is overwhelmingly female. Measured on RI ch1
    block 2 -- a confrontation between two men -- a prompt carrying only
    their names produced a girl holding cherry blossoms.
    """
    males = sum(1 for g in genders if g == "male")
    females = sum(1 for g in genders if g == "female")

    parts: list[str] = []
    if males == 1:
        parts.append("1boy")
    elif males > 1:
        parts.append(f"{min(males, 6)}boys")
    if females == 1:
        parts.append("1girl")
    elif females > 1:
        parts.append(f"{min(females, 6)}girls")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

#: CLIP's context is 77 tokens **including** the two special tokens, and
#: Stable Diffusion silently truncates past it -- no error, no warning in
#: normal use, just a prompt whose tail never reached the model.
CLIP_TOKEN_LIMIT = 77
_USABLE_TOKENS = CLIP_TOKEN_LIMIT - 2


def count_tokens(text: str) -> int:
    """CLIP token count, or a conservative estimate without `transformers`.

    The estimate deliberately over-counts (CLIP splits on punctuation and
    sub-words, so commas and long names cost more than a word each): budget
    logic that under-counts silently reintroduces the truncation this
    module exists to prevent.
    """
    try:
        from transformers import CLIPTokenizer
    except Exception:
        words = text.replace(",", " , ").split()
        return int(len(words) * 1.3) + 2

    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = CLIPTokenizer.from_pretrained("openai/clip-vit-large-patch14")
    return len(_TOKENIZER(text)["input_ids"])


_TOKENIZER = None


def fit_to_budget(parts: list[str], limit: int = _USABLE_TOKENS) -> str:
    """Join `parts` (highest priority first) into a prompt CLIP will read.

    **Measured, not assumed: every panel of the last real chapter run
    exceeded the limit** -- median 154 tokens against a limit of 77, so
    *half of every prompt was discarded*, and because the character came
    after three blocks of scenery the discarded half was the character, the
    framing and the style. That is the whole explanation for panels that
    came back as empty courtyards for scenes about people.

    Parts are added while they fit and skipped when they do not, rather than
    the whole string being cut mid-phrase: a truncated clause ("wearing
    simple robes with wide") is worse than an absent one, because it still
    spends tokens and steers toward whatever the fragment resembles.
    """
    kept: list[str] = []
    for part in parts:
        if not part:
            continue
        candidate = ", ".join([*kept, part])
        if count_tokens(candidate) <= limit:
            kept.append(part)
    return ", ".join(kept)


#: Token budget for one character's description inside a *panel* prompt.
#:
#: The clause `reference_gen.build_reference_prompt` produces is a full
#: character sheet -- hair, eyes, skin, build, features, attire -- and is
#: right for the sheet, which has nothing else to say. In a panel it is
#: ~60 of the 75 available tokens for one person, which measured on RI ch1
#: meant the character was skipped entirely and the panel became scenery.
#: A panel needs *identity*, and identity is the first few attributes; the
#: face itself arrives through IP-Adapter conditioning, not through words.
#: Sized so the *beat* also fits alongside it -- the beat is the only part
#: of a prompt that makes two panels of one character in one place
#: different pictures, so it wins ties against further description.
_MAX_CHARACTER_TOKENS = 18


def condense_clause(clause: str, limit: int = _MAX_CHARACTER_TOKENS) -> str:
    """Trim a character clause to its most identifying attributes.

    Cuts on comma boundaries, never mid-phrase: "wearing simple robes with
    wide" spends tokens steering toward nothing. Keeps the front, which is
    where `build_reference_prompt` puts build and hair -- the two things
    that make a xianxia character recognisable at panel scale.

    Also drops any leading headcount tag, since `cast_tags` has already put
    one at the very front of the prompt and a second `1boy` is a token spent
    saying something the model has been told.
    """
    parts = [p.strip() for p in clause.split(",") if p.strip()]
    parts = [p for p in parts if p not in _HEADCOUNT_TAGS]
    ranked = sorted(enumerate(parts), key=lambda pair: (_identity_rank(pair[1]), pair[0]))

    kept: list[tuple[int, str]] = []
    for index, part in ranked:
        candidate = ", ".join(p for _i, p in sorted([*kept, (index, part)]))
        if count_tokens(candidate) - 2 > limit:
            continue
        kept.append((index, part))
    # Re-emit in the clause's own order: the ranking decides what survives,
    # not what it reads like.
    return ", ".join(part for _i, part in sorted(kept))


#: Tags `cast_tags` already emits; duplicating them inside a character
#: clause wastes budget without adding information.
_HEADCOUNT_TAGS = frozenset(
    {"1boy", "1girl", "2boys", "2girls", "solo", "male", "female", "person"}
)

#: What identifies a character at panel scale, best first.
#:
#: Ranked rather than taken in clause order, because clause order is the
#: *reference sheet's* order (build, then hair, then eyes...) and the sheet
#: has room for all of it. A panel does not: measured on Fang Yuan, a
#: positional cut kept "tall and lean, gaunt with age and injury" and
#: dropped "midnight black very long straight hair down to the waist" --
#: losing the single feature that makes him recognisable in silhouette,
#: which in this genre is most of what recognition is.
_IDENTITY_ORDER = ("hair", "eyes", "build", "tall", "slim", "wearing", "robe")


def _identity_rank(part: str) -> int:
    low = part.casefold()
    for rank, keyword in enumerate(_IDENTITY_ORDER):
        if keyword in low:
            return rank
    return len(_IDENTITY_ORDER)


def build_image_prompt(
    panel_cast: PanelCast,
    *,
    beat: str = "",
    character_appearances: dict[str, str] | None = None,
    character_genders: list[str] | None = None,
    world: str = "",
    locale: str = "",
    style: str = MANGA_STYLE,
) -> str:
    """Compose one prompt string from a resolved `PanelCast`.

    `beat` is the block's own narration, summarised -- it is what makes two
    panels with the same cast different images. `character_appearances` maps
    a character's label to their stored appearance clause
    (`persona/reference_gen.py::build_reference_prompt` builds the same
    clause for the reference sheet), so a character's look survives into
    panels even where reference conditioning is unavailable.

    Returns a style/environment-only prompt (still a valid establishing-shot
    prompt) when nobody is in frame -- `get_panel_cast` returns exactly that
    shape for a block outside every tracked scene.
    """
    appearances = character_appearances or {}
    # **Ordered by what must survive truncation, not by reading order.**
    # See `fit_to_budget`: everything past 77 CLIP tokens is silently
    # discarded, so this list is a priority ranking. Headcount and the
    # subject's own description come before scenery, because a panel of the
    # right character in a vague place is recoverable and a beautiful empty
    # courtyard is not.
    parts: list[str] = []

    # Headcount first: it is the single strongest steer on this class of
    # checkpoint, and getting it wrong turns a confrontation between two men
    # into a girl with cherry blossoms.
    if tags := cast_tags(character_genders or []):
        parts.append(tags)

    # The style *anchor* -- the few words that decide whether this is ink
    # painting or a 3D render -- comes early and short. The rest of the
    # style string is appended last, where it is the first thing dropped.
    parts.append(STYLE_ANCHOR)

    # The subject, before the setting. This is the change that matters: the
    # character used to sit behind locale, world and environment, i.e.
    # entirely inside the discarded half of the prompt.
    for character in panel_cast.foreground_characters:
        described = condense_clause(appearances.get(character.self_label, ""))
        if described:
            parts.append(f"{character.self_label}: {described}")
        elif character.attire and character.attire != panel_cast.environment:
            parts.append(f"{character.self_label} wearing {character.attire}")
        else:
            # `resolve_attire`'s last tier is the *novel's house style*, not
            # a garment, so it comes back identical to the environment
            # clause -- emitting it here produced "Fang Yuan wearing xianxia
            # web-novel illustration" on real RI ch1 output, and repeated
            # the same style string once per character on top of that. Name
            # the character and let the style clause do its job once.
            parts.append(character.self_label)

    # Composition, immediately after the subject: it is short, and losing it
    # turns a chosen close-up into a generic full-body portrait.
    parts.append(framing_for(style))

    # What is happening, then where. A beat with no place still reads; a
    # place with no beat is a landscape.
    if beat:
        parts.append(summarise_beat(beat))

    # The specific place first, the world's general vocabulary behind it:
    # a diffusion model draws "a walled stone courtyard" and draws nothing
    # recognisable from "ancient Chinese cultivation world".
    if locale:
        parts.append(locale)

    for mob in panel_cast.background_mobs:
        descriptor = f"background: {mob.description}"
        if mob.attire:
            descriptor += f" ({mob.attire})"
        parts.append(descriptor)

    # The world's generic scenery vocabulary is the *lowest* priority thing
    # in the prompt and used to be near the top. It is a list of nouns true
    # of every chapter of the novel, so it individuates nothing, and it was
    # crowding out the things that do.
    if world:
        parts.append(world)
    if panel_cast.environment and panel_cast.environment != world:
        parts.append(panel_cast.environment)

    parts.append(style)
    return fit_to_budget(parts)
