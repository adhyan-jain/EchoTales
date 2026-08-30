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

import re

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
    # "flowing black hair" used to sit here. It is in the reference art, but
    # as a *global* style term it applied to every panel including ones with
    # no person in them, and on a Danbooru-trained checkpoint long flowing
    # hair is one of the strongest feminine cues there is -- reviewed panels
    # of a male protagonist came back as women in white robes with
    # waist-length hair. Hair belongs to the character clause, where it is
    # attached to a character who actually has it.
    "ink wash, muted limited palette, "
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
#: **Anatomy is where these checkpoints fail under zoom.** A panel that
#: reads well at thumbnail size comes apart at 100%: fused or six-fingered
#: hands, an eye at the wrong height, hair that changes colour partway down
#: its own length. Listed specifically rather than as "bad anatomy",
#: because these checkpoints are tag-trained and respond to the named
#: failure far more than to the category.
_NEGATIVE_ANATOMY = (
    "deformed hands, mutated hands, fused fingers, extra fingers, "
    "missing fingers, malformed fingers, extra limbs, extra arms, "
    "asymmetric eyes, misaligned eyes, cross-eyed, deformed face, "
    "melted features, disconnected limbs, two-tone hair, "
    "inconsistent hair colour, lowres, blurry, jpeg artifacts"
)

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

#: Incoherent geography. The checkpoint fills a wide frame by stacking
#: several unrelated landscapes -- a reviewed panel had the subject standing
#: over what read as three different mountain ranges at once, with no single
#: ground plane under him. Nothing in the negative opposed that, and the
#: positive prompt cannot fix it: naming one place does not stop the model
#: adding more behind it.
_NEGATIVE_GEOGRAPHY = (
    "multiple horizons, stacked landscapes, disjointed background, "
    "floating in air, no ground, collage"
)

#: Wrong body and wrong demeanour. The protagonist is repeatedly described as
#: lean with cold, abyss-black eyes, and the checkpoint's prior for a robed
#: martial figure is a broad-shouldered, bright-eyed heroic one -- reviewed
#: panels read as "an energetic righteous warrior", which is the opposite of
#: the character. Positive wording did not hold this on its own.
_NEGATIVE_PHYSIQUE = (
    "muscular, buff, bulky, broad shoulders, bodybuilder, heroic pose, "
    "righteous, cheerful, smiling, bright eyes, "
    # The SDXL anime checkpoints reach for a demon-boy costume whenever a
    # character is described as a demon -- a close-up of Fang Yuan's dying
    # thoughts came back as a grinning red-eyed youth with fangs and a
    # forehead gem. He is canonically jet-black eyed and expressionless;
    # "demon" in this novel is a moral word, not a species.
    "red eyes, glowing eyes, fangs, horns, forehead gem, face markings"
)

#: Safety and baseline quality. Illustrious (and SDXL anime finetunes
#: generally) are Danbooru-tag trained: without explicit quality/safety tags
#: they drift toward their training prior, which includes NSFW. A test render
#: returned a partially undressed figure among grotesque faces -- neither
#: asked for nor acceptable, and not something a positive prompt prevents.
_NEGATIVE_SAFETY = (
    "nsfw, nude, topless, exposed chest, suggestive, "
    "worst quality, low quality, jpeg artifacts, bad hands, bad face, "
    "grotesque, uncanny, distorted face"
)

_NEGATIVE_TAIL = (
    _NEGATIVE_SAFETY,
    _NEGATIVE_PHYSIQUE,
    _NEGATIVE_GEOGRAPHY,
    _NEGATIVE_ANATOMY,
    _NEGATIVE_MEDIUM,
    _NEGATIVE_TONE,
    _NEGATIVE_LOOK,
    _NEGATIVE_CULTURE,
    _NEGATIVE_ARTEFACT,
)

#: **The negative prompt is fitted to the same 77 tokens as the positive
#: one, so its ordering is a real choice, not a stylistic one.** Measured:
#: with the single order above, an establishing shot's negative ended at
#: "...cheerful, smiling, bright eyes" and every geography term was dropped
#: -- on precisely the framing whose reviewed failure was three mountain
#: ranges stacked behind the subject with no ground plane. Physique matters
#: where a body fills the frame and geography where a landscape does, so
#: which one survives truncation has to follow the framing.
#: Key art instead of a scene. An anime checkpoint's strongest prior for
#: "several named characters, one image" is a promotional poster, and it
#: fires hard: a reviewed establishing shot came back as a cast lineup of
#: twenty unrelated characters staring at the camera under a title banner in
#: fake Chinese type, with two chibi mascots in the corner. Every element of
#: that is a genre convention of the *format*, not of the scene, so it has
#: to be refused as a format.
_NEGATIVE_POSTER = (
    "poster, cover art, title text, watermark, character lineup, "
    "looking at viewer, chibi"
)

#: **A wide shot cannot afford the full safety block.** The negative prompt
#: is fitted to 77 tokens like the positive one, and at 13 words the long
#: form left nothing for the two failures a wide shot actually exhibits
#: (poster layout, incoherent geography) -- both were being truncated off.
#: This states the same refusals in a third of the tokens; the long form
#: still applies to close-ups, where a body fills the frame and the extra
#: precision earns its place.
_NEGATIVE_SAFETY_SHORT = "nsfw, nude, worst quality, bad anatomy, distorted face"

_NEGATIVE_TAIL_WIDE = (
    _NEGATIVE_SAFETY_SHORT,
    _NEGATIVE_POSTER,
    _NEGATIVE_GEOGRAPHY,
    _NEGATIVE_PHYSIQUE,
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
    tail = _NEGATIVE_TAIL if style == STYLE_CLOSEUP else _NEGATIVE_TAIL_WIDE
    return fit_to_budget([head, *tail])


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

#: A hand-authored `directive` (`render/beat_canon.py`) gets more room than
#: scraped prose. It exists precisely because raw extraction cannot recover
#: the moment, so it is already the *dense* version -- there is no fuller
#: source text to fall back to if it gets cut, the way a beat's second
#: sentence is at least recoverable from the audio's caption track. Still
#: capped, so one long directive cannot swallow the entire token budget on
#: its own.
_MAX_DIRECTIVE_CHARS = 240


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


def cast_tags(genders: list[str], *, beat: str = "") -> str:
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
    # **`solo` needs the same front-of-prompt treatment `1boy`/`crowd`
    # already got, not a mid-clause mention.** Measured on RI ch1: the
    # director's own `layout` field correctly said "a figure, solo" (or
    # equivalent) on 5+ panels, and the checkpoint still rendered two
    # people anyway -- because that "solo" sat as one word inside a
    # 70+-token tier-3 clause, not asserted as its own leading Danbooru
    # tag the way `1boy`/`male focus` are. Fires only for an actual
    # single-person headcount; a crowd panel never reaches this function
    # (`is_crowd_cut` branches before it), so there is no case here where
    # "solo" could contradict a real multi-person cast.
    if males + females == 1:
        parts.append("solo")
    # **`1boy` alone does not hold.** It fixes the headcount and not the
    # rendering: with `1boy` present and nothing else, reviewed panels still
    # came back as a slim figure with a feminine face, waist-length hair and
    # a white gown. `male focus` is the Danbooru tag that actually moves the
    # face and build, and it only makes sense when nobody in frame is
    # female -- adding it to a mixed-cast panel would masculinise the women.
    if males and not females:
        parts.append("male focus")

    # **The unresolved-cast case still needs a *positive* push, not just
    # `gender_negative`'s negative one.** `genders` is empty whenever
    # nobody in frame resolved to a persona -- an unnamed "warlords and
    # warrior women" mob, a director-named character whose block window
    # never actually carried a resolved mention. A negative-only clause was
    # measured insufficient on its own: RI ch1 blocks 0 and 36, both
    # unresolved-cast beats whose prose plainly reads male ("he"/"his"
    # throughout), still rendered feminine-presenting subjects even with
    # `gender_negative`'s exclusion applied (`data/diag/noobai/panels/ch1/
    # v1/p001_b0000.png`, `p016_b0036.png`) -- excluding a look is not the
    # same as asking for one, and this checkpoint needs to be asked. Uses
    # the beat's own pronouns, same signal `gender_negative` already
    # trusts for the same case.
    if not parts and beat:
        has_male = bool(_MALE_PRONOUN_RE.search(beat))
        has_female = bool(_FEMALE_PRONOUN_RE.search(beat))
        if has_male and not has_female:
            parts = ["1boy", "male focus", "solo"]
        elif has_female and not has_male:
            parts = ["1girl", "solo"]

    # **The genuinely signal-free case still needs a mechanical answer,
    # not just an LLM instruction.** SYSTEM rule 6 already tells the
    # director "if gender is unstated, render as a silhouette, back-
    # turned figure, or environmental element" -- but that is compliance-
    # only, with no tag-level backstop the way the pronoun fallback above
    # gives `gender_negative`. Measured on a real chapter-1 render: 7+
    # panels with neither a resolved gender nor a beat pronoun (clan
    # elders discussing news, a narrator's aside) still rendered a
    # detailed, clearly feminine face, because nothing here was asking
    # for anything else -- an empty tag string means "checkpoint's own
    # prior decides," and that prior is female. Assert the *composition*
    # rule 6 already wants, as a positive tag this checkpoint actually
    # weights, instead of guessing a gender that genuinely isn't stated
    # (guessing wrong is the "confidently wrong" failure the pronoun
    # fallback above was built to avoid; "faceless" isn't a guess).
    # **Only when the director actually meant to draw someone.** `beat`
    # here is beat prose plus the director's own action+layout text (see
    # the call site), and `direction.py`'s SYSTEM rule 5 tells the
    # director to write the literal words "a figure" in `layout` exactly
    # when CAST is empty but the passage still places someone in frame --
    # as opposed to a pure-environment beat with nobody there at all,
    # where asserting a silhouette would be a *new* hallucination (a
    # person injected into a landscape shot). "a figure" in the combined
    # text is that same signal, already computed by the caller; checking
    # for it here is what keeps this fallback from also firing on
    # `cast_tags([], beat="The mountain path wound upward through mist.")`
    # -- correctly still silent, since nothing places a figure there --
    # while still catching the actually-measured failures (clan elders
    # discussing news, a narrator's aside: `layout="a figure, solo"`,
    # zero pronouns, rendered a detailed feminine face on a real chapter-
    # 1 run). Also excludes the *mixed*-pronoun case ("he grabbed her
    # arm"): that is two people in frame, a headcount problem, not one
    # unresolved figure's gender -- asserting a lone silhouette there
    # would be its own wrong guess.
    if (
        not parts
        and beat
        and "a figure" in beat.lower()
        and not (_MALE_PRONOUN_RE.search(beat) and _FEMALE_PRONOUN_RE.search(beat))
    ):
        parts = ["silhouette", "back_turned", "faceless", "solo"]

    return ", ".join(parts)


#: What to refuse when the cast is entirely male. Paired with `male focus`
#: above and for the same measured reason: on these checkpoints the pull
#: toward a female subject is strong enough that it has to be opposed from
#: both directions at once.
_NEGATIVE_FEMININE = (
    "1girl, 2girls, multiple girls, female, woman, girl, girls, "
    "feminine face, breasts, lipstick, makeup, female focus"
)


#: Pronouns, for the case where nothing in frame resolved to a known
#: character. Deliberately whole-word: "his" must not match "history".
_MALE_PRONOUN_RE = re.compile(r"\b(?:he|him|his|himself)\b", re.I)
_FEMALE_PRONOUN_RE = re.compile(r"\b(?:she|her|hers|herself)\b", re.I)


def gender_negative(genders: list[str], *, beat: str = "") -> str:
    """The extra negative clause a male-only panel needs, if any.

    **The unresolved case is the one that was failing.** `genders` is empty
    whenever nobody in frame resolved to a persona -- an unnamed cultivator,
    a scene the cast pass could not place anyone in -- and an empty list
    used to mean "say nothing", which on these checkpoints means "draw a
    woman". The beat's own pronouns settle it: prose that says "he" four
    times and never "she" is about a man, whatever resolution managed.
    """
    if any(g == "female" for g in genders):
        return ""
    if any(g == "male" for g in genders):
        return _NEGATIVE_FEMININE
    if beat and _MALE_PRONOUN_RE.search(beat) and not _FEMALE_PRONOUN_RE.search(beat):
        return _NEGATIVE_FEMININE
    return ""


def genre_mismatch_negative(novel_id: str, beat: str) -> str:
    """Suppress this novel's genre-typical-but-textually-absent props.

    RI's director hallucinated `"blades, talismans, swords"` into a
    beat's `key_objects` where the passage said nothing about weapons at
    all -- measured on ch1 blocks 0-3 (pure dialogue, no props named),
    the checkpoint's own xianxia-genre prior filling the gap the way it
    fills an unstated gender. `WORLD_CONTEXT`'s citation trail is the
    positive-side fix (tell the director what *is* actually here);
    this is the negative-side backstop for whatever still slips through.

    Gated on the beat's own text so a scene that genuinely names one of
    these (rare, but the novel runs 199 chapters) is not silently
    overridden -- same principle as `gender_negative` trusting the
    beat's own pronouns over a blanket rule. Word-boundary matching on
    both sides: "blade" must not fire on the beat text just because it
    contains "moonblade", RI's real ranged-attack technique.
    """
    from echotales.pipeline.persona.attire import GENRE_MISMATCH_PROPS

    props = GENRE_MISMATCH_PROPS.get(novel_id, ())
    if not props:
        return ""
    if any(re.search(rf"\b{re.escape(p)}\b", beat, re.I) for p in props):
        return ""
    return ", ".join(props)


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
    # fit_to_budget calls this on candidates that may exceed the 77-token
    # limit as part of the check loop. The transformers tokenizer warns on
    # any input over model_max_length, which fires on every rejected
    # candidate and pollutes the run log. Suppress here since over-budget
    # is expected and handled by the caller.
    import logging as _logging
    _logging.getLogger("transformers.tokenization_utils_base").setLevel(_logging.ERROR)
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
# Raised from 18 to 20: the priority reorder puts "wearing white robes" (3
# tokens) right after hair (~12 tokens). At 18 the total with eyes pushed to
# 19 and eyes was dropped. At 20, hair (12) + robe (3) + eyes (4) = 19 ≤ 20.
# 2-character scenes use 40 tokens total (20+20), still within the 77-token
# CLIP budget when style, cast, beat and framing are accounted for (~26 more).
_MAX_CHARACTER_TOKENS = 20


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


#: Colour words `compress_identity_tags` recognises inside a hair phrase.
_HAIR_COLORS = frozenset(
    {"black", "white", "silver", "grey", "gray", "brown", "red", "blonde",
     "blond", "golden", "blue", "green", "purple", "pink", "auburn"}
)

#: Filler that carries no visual information -- dropped before tagging.
_TAG_FILLER = frozenset(
    {"and", "with", "a", "an", "the", "that", "had", "been", "very", "down",
     "to", "waist", "of"}
)


def compress_identity_tags(clause: str) -> str:
    """Convert a condensed identity/condition clause from prose to tags.

    `condense_clause` already picks *which* attributes survive; this
    controls how many *words* each one costs. Measured on Fang Yuan: his
    condensed clause ran ~40 tokens of narrative prose ("midnight black
    very long straight hair down to the waist, cold and narrow eyes") with
    real redundancy the tag-vs-narrative experiment already proved
    unnecessary -- the checkpoint reads "long_black_hair, cold_eyes" as the
    same identity for a fraction of the tokens, which is what actually
    freed room for tier 2 (action, mood, key_objects) to survive alongside
    tier 1 instead of being silently squeezed out.

    Hair and eyes get dedicated handling because their phrasing is
    predictable ("<descriptors> hair" / "<descriptors> eyes") and losing
    the wrong word matters most for them -- hair colour is "the single
    feature that makes [a character] recognisable in silhouette" per
    `condense_clause`'s own docstring. Everything else (build, attire,
    distinguishing features, already-tagged condition words like `blood`
    or `wounded`) just has filler words stripped and gets snake_cased,
    capped to its two most specific words -- a plain word like `blood`
    passes through unchanged.
    """
    parts = [p.strip() for p in clause.split(",") if p.strip()]
    tags: list[str] = []
    for part in parts:
        words = [w for w in part.lower().split() if w not in _TAG_FILLER]
        if not words:
            continue
        if words[-1] == "hair":
            color = next((w for w in words if w in _HAIR_COLORS), None)
            length = "long" if any(w in ("long", "floor") for w in words) else (
                "short" if "short" in words else ""
            )
            tags.append("_".join(x for x in (length, color, "hair") if x))
        elif words[-1] == "eyes":
            descriptors = [w for w in words[:-1] if w != "eyes"][:2]
            tags.append("_".join([*descriptors, "eyes"]))
        else:
            tags.append("_".join(words[:2]))
    return ", ".join(t for t in tags if t)


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
# "wearing" and "robe" promoted to rank 2: robe colour is the single most
# visible difference between characters in xianxia (Fang Yuan's white vs
# Shen Cui's green), and the budget cut it every time by ranking it below
# hair+eyes which together already used 16 of the 18-token limit.
_IDENTITY_ORDER = ("hair", "wearing", "robe", "eyes", "build", "tall", "slim")


def _identity_rank(part: str) -> int:
    low = part.casefold()
    for rank, keyword in enumerate(_IDENTITY_ORDER):
        if keyword in low:
            return rank
    return len(_IDENTITY_ORDER)


#: **The cheapest fix for hands is to not show them.** Hanfu has long
#: draping sleeves that cover the hands in ordinary standing poses, which
#: is both period-correct and the single most reliable way to avoid the
#: failure these checkpoints are worst at. Applied only where it costs
#: nothing -- a beat that puts something *in* a character's hands (a sword,
#: a Gu, a raised palm) must not hide them.
_SLEEVE_CLAUSE = "hands concealed in long draping sleeves"

#: Words that mean the hands are the point of the shot.
_HANDS_MATTER = (
    "hand", "palm", "finger", "grip", "grasp", "hold", "sword", "blade",
    "weapon", "raise", "reach", "point", "clench", "fist", "throw", "seal",
)


def hands_clause(beat: str) -> str:
    """`_SLEEVE_CLAUSE` when nothing in the beat needs visible hands."""
    blob = (beat or "").casefold()
    if any(term in blob for term in _HANDS_MATTER):
        return ""
    return _SLEEVE_CLAUSE


def build_image_prompt(
    panel_cast: PanelCast,
    *,
    beat: str = "",
    directive: str = "",
    character_appearances: dict[str, str] | None = None,
    character_genders: list[str] | None = None,
    world: str = "",
    locale: str = "",
    style: str = MANGA_STYLE,
    limit: int = _USABLE_TOKENS,
) -> str:
    """Compose one prompt string from a resolved `PanelCast`.

    `beat` is the block's own narration, summarised -- it is what makes two
    panels with the same cast different images. `character_appearances` maps
    a character's label to their stored appearance clause
    (`persona/reference_gen.py::build_reference_prompt` builds the same
    clause for the reference sheet), so a character's look survives into
    panels even where reference conditioning is unavailable.

    `directive` is hand-authored staging (`render/beat_canon.py`), kept
    **separate from `beat`** rather than prepended to it, and that
    separation is load-bearing: `beat` is capped to `_MAX_BEAT_CHARS` and
    truncated on a sentence boundary meant for raw prose, and a directive
    concatenated in front of the beat lost its second sentence to that same
    cap the first time this was tried -- "surrounded by an armed faction,
    some flying overhead" fell off, leaving only "a mountain stronghold at
    dusk." `directive` gets its own priority slot, ahead of *both* the beat
    and the character's generic appearance clause -- the second ordering
    also had to be measured in, not assumed: "Fang Yuan: midnight black
    hair, cold narrow eyes" is shorter and unremarkable next to the
    staging, so a first attempt that put appearance first let it win the
    greedy budget fit and silently dropped the entire directive.

    Returns a style/environment-only prompt (still a valid establishing-shot
    prompt) when nobody is in frame -- `get_panel_cast` returns exactly that
    shape for a block outside every tracked scene.

    `limit` defaults to the full 75-token budget, but the caller must lower
    it by the target image engine's own `quality_prefix` cost when one
    exists. That prefix is prepended ahead of everything built here, at the
    engine layer, after this function has already returned a "complete"
    fitted string -- without reserving room for it up front, the engine
    silently re-truncates this carefully prioritised prompt from a second,
    uncoordinated budget fit that has no knowledge of what this function
    decided mattered most. Measured: two RI ch1 panels differing only in
    their trailing mood tag rendered byte-identical images, because
    `quality_prefix` alone (47 tokens for NoobAI) pushed both prompts' only
    point of difference past the second fit's cutoff.
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
    if tags := cast_tags(character_genders or [], beat=beat):
        parts.append(tags)

    # The style *anchor* -- the few words that decide whether this is ink
    # painting or a 3D render -- comes early and short. The rest of the
    # style string is appended last, where it is the first thing dropped.
    parts.append(STYLE_ANCHOR)

    # Hand-authored staging outranks the block's own prose *and* the
    # generic appearance clause -- it exists specifically for panels where
    # neither the prose nor a standing description is the picture a reader
    # wants (Section this module's docstring), so it goes ahead of both. Tried
    # after the character loop first and lost the budget fight every time:
    # "Fang Yuan: midnight black hair, cold narrow eyes" is unremarkable
    # and generic next to "standing in a pool of blood... holding a
    # glowing cicada", but being *shorter* let it win the greedy fit, and
    # the entire directive was silently dropped. Own truncation budget, so
    # one long directive cannot swallow the rest of the prompt either.
    if directive:
        parts.append(summarise_beat(directive, limit=_MAX_DIRECTIVE_CHARS))

    # **What is happening, ahead of what the subject permanently looks
    # like.** Appearance is a standing fact and repeats on every panel of
    # that character; the beat is the only part of the prompt that makes
    # *this* panel a different picture from the last one. Behind the
    # appearance clause it kept losing the greedy budget fit -- Fang Yuan's
    # clause runs about twenty tokens of hair and eyes, and panels came out
    # as a correct-looking man doing nothing identifiable, or as locale
    # scenery with no beat in them at all. Identity is also the one thing
    # reference conditioning can carry without any tokens, which the beat
    # cannot.
    if beat:
        parts.append(summarise_beat(beat))

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

    # Late in the priority order: worth having, never worth displacing the
    # beat or the subject.
    if sleeves := hands_clause(beat):
        parts.append(sleeves)

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
    return fit_to_budget(parts, limit=limit)
