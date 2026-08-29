"""The 77-token wall, and what has to survive it.

**Measured before this existed: every panel of the last real chapter run
exceeded CLIP's limit** -- median 154 tokens against 77, so half of every
prompt was discarded silently. Because the character sat behind three blocks
of scenery, the discarded half was the character, the framing and the style,
and the panels came back as empty courtyards for scenes about people.

These pin the ordering, not just the length: a prompt that fits but leads
with scenery is the same bug wearing a smaller number.
"""

from __future__ import annotations

from echotales.pipeline.persona.prompt import (
    STYLE_ANCHOR,
    STYLE_CLOSEUP,
    STYLE_ESTABLISHING,
    STYLE_SCENE,
    build_image_prompt,
    condense_clause,
    count_tokens,
    fit_to_budget,
    negative_for,
)
from echotales.pipeline.persona.runner import CharacterCast, PanelCast

_APPEARANCE = (
    "1boy, solo, male, tall and lean, gaunt with age and injury, "
    "midnight black very long straight hair down to the waist, "
    "jet black cold and narrow eyes, pale, aged, hollow-cheeked, "
    "cold expressionless stare, utterly ruthless demeanour, "
    "wearing simple robes with wide sleeves"
)

_WORLD = (
    "ancient Chinese cultivation world, stone courtyards, timber halls with "
    "upturned tiled roofs, bamboo groves, terraced mountain villages, mist "
    "over jagged peaks, stone steps, paper lanterns"
)


def _cast(*labels: str) -> PanelCast:
    return PanelCast(
        foreground_characters=[CharacterCast(self_label=n, attire="") for n in labels]
    )


class TestBudget:
    def test_parts_that_do_not_fit_are_dropped_whole(self) -> None:
        """A truncated clause is worse than an absent one: it still spends
        tokens and steers toward whatever the fragment resembles."""
        long_tail = "an extremely long trailing clause " * 20
        out = fit_to_budget(["1boy", "ink painting", long_tail, "a courtyard"])
        assert "1boy" in out
        assert "extremely long trailing" not in out

    def test_the_result_fits_clip(self) -> None:
        out = fit_to_budget(["1boy", _APPEARANCE, _WORLD, "a walled courtyard"])
        assert count_tokens(out) <= 77

    def test_an_empty_part_list_is_an_empty_prompt(self) -> None:
        assert fit_to_budget([]) == ""
        assert fit_to_budget(["", ""]) == ""


class TestDirective:
    """Hand-authored staging (`render/beat_canon.py`) and the priority fight
    it lost twice before landing in the right slot -- first to `beat`'s
    truncation cap, then to the character's own generic appearance clause."""

    _DIRECTIVE = (
        "standing in a pool of blood, bloody footprints leading to him, "
        "robes soaked and torn, face calm and expressionless. Both palms "
        "raised before his chest, holding a small glowing luminous "
        "cicada, gazing at it plainly."
    )

    def test_a_long_directive_survives_alongside_a_character(self) -> None:
        """Measured regression: appearance ("Fang Yuan: midnight black
        hair, cold narrow eyes") is shorter than the directive, so a
        greedy budget fit that tried appearance first kept it and dropped
        the entire directive silently."""
        prompt = build_image_prompt(
            _cast("Fang Yuan"),
            directive=self._DIRECTIVE,
            character_appearances={"Fang Yuan": _APPEARANCE},
            character_genders=["male"],
        )
        assert "pool of blood" in prompt
        assert "cicada" in prompt
        assert count_tokens(prompt) <= 77

    def test_directive_outranks_the_beat(self) -> None:
        prompt = build_image_prompt(
            _cast("Fang Yuan"),
            beat="A very long stretch of ordinary narration text " * 5,
            directive=self._DIRECTIVE,
            character_appearances={"Fang Yuan": _APPEARANCE},
            character_genders=["male"],
        )
        assert "cicada" in prompt

    def test_no_directive_is_a_no_op(self) -> None:
        """Every panel without a canon entry must build exactly as before
        this existed."""
        with_empty = build_image_prompt(
            _cast("Fang Yuan"), directive="",
            character_appearances={"Fang Yuan": _APPEARANCE},
            character_genders=["male"],
        )
        without_arg = build_image_prompt(
            _cast("Fang Yuan"),
            character_appearances={"Fang Yuan": _APPEARANCE},
            character_genders=["male"],
        )
        assert with_empty == without_arg


class TestOrdering:
    def test_a_real_panel_prompt_fits(self) -> None:
        prompt = build_image_prompt(
            _cast("Fang Yuan"),
            beat="He stood silent as a sculpture, surrounded on every side.",
            character_appearances={"Fang Yuan": _APPEARANCE},
            character_genders=["male"],
            world=_WORLD,
            locale="a walled stone courtyard, flagstones, low roofs beyond",
        )
        assert count_tokens(prompt) <= 77

    def test_the_subject_survives_and_the_scenery_dump_does_not(self) -> None:
        """The whole point. Generic world vocabulary is true of every chapter
        so it individuates nothing, and it was crowding out the one thing
        that does."""
        prompt = build_image_prompt(
            _cast("Fang Yuan"),
            beat="He turned slowly.",
            character_appearances={"Fang Yuan": _APPEARANCE},
            character_genders=["male"],
            world=_WORLD,
            locale="a walled stone courtyard",
        )
        assert "Fang Yuan" in prompt
        assert "midnight black" in prompt
        assert "paper lanterns" not in prompt

    def test_headcount_and_style_anchor_lead(self) -> None:
        """Headcount is the strongest steer on this checkpoint class, and the
        anchor is what decides ink painting versus 3D render."""
        prompt = build_image_prompt(
            _cast("Fang Yuan"),
            beat="He turned.",
            character_appearances={"Fang Yuan": _APPEARANCE},
            character_genders=["male"],
        )
        assert prompt.startswith("1boy")
        assert prompt.index(STYLE_ANCHOR) < prompt.index("Fang Yuan")

    def test_two_characters_both_survive(self) -> None:
        prompt = build_image_prompt(
            _cast("Fang Yuan", "Bai Ning Bing"),
            beat="They faced each other.",
            character_appearances={
                "Fang Yuan": _APPEARANCE,
                "Bai Ning Bing": _APPEARANCE,
            },
            character_genders=["male", "male"],
            world=_WORLD,
        )
        assert "Fang Yuan" in prompt and "Bai Ning Bing" in prompt
        assert count_tokens(prompt) <= 77


class TestNegativePrompts:
    """The same truncation bug, one prompt over. Every negative measured
    ~100 tokens against the same 77-token limit, and because the shared
    base came first, what was silently dropped was the per-framing tail --
    "plain background, portrait, bust shot" -- which is exactly what stops
    a scene shot collapsing into a portrait."""

    def test_every_framing_fits(self) -> None:
        for style in (STYLE_ESTABLISHING, STYLE_SCENE, STYLE_CLOSEUP):
            assert count_tokens(negative_for(style)) <= 77

    def test_the_discriminating_clause_survives(self) -> None:
        """The per-framing head must not be the part that gets cut."""
        assert "portrait" in negative_for(STYLE_SCENE)
        assert "tiny face" in negative_for(STYLE_CLOSEUP)

    def test_framings_reject_different_things(self) -> None:
        """A close-up wants the plain background a scene shot must reject --
        one shared negative cannot serve both."""
        assert negative_for(STYLE_CLOSEUP) != negative_for(STYLE_SCENE)


class TestCondenseClause:
    def test_it_keeps_what_identifies_over_what_comes_first(self) -> None:
        """Clause order is the *reference sheet's* order, and the sheet has
        room for everything. A panel does not: hair and robe colour are the
        two most identifying features (hair is silhouette, robe is the
        character's visual signature in xianxia); eyes survive when they fit."""
        out = condense_clause(_APPEARANCE)
        assert "midnight black" in out
        assert "wearing" in out  # robe colour must always survive

    def test_surviving_parts_keep_their_original_order(self) -> None:
        """Ranking decides what survives, not how it reads."""
        out = condense_clause(_APPEARANCE)
        assert out.index("hair") < out.index("wearing")

    def test_it_drops_duplicated_headcount_tags(self) -> None:
        """`cast_tags` already put `1boy` at the very front of the prompt; a
        second one is a token spent saying something already said."""
        out = condense_clause(_APPEARANCE)
        assert "1boy" not in out
        assert "solo" not in out

    def test_it_never_cuts_mid_phrase(self) -> None:
        out = condense_clause(_APPEARANCE)
        for part in out.split(","):
            assert part.strip() in _APPEARANCE

    def test_a_short_clause_is_untouched(self) -> None:
        assert condense_clause("tall and lean, black hair") == "tall and lean, black hair"

    def test_an_empty_clause_stays_empty(self) -> None:
        assert condense_clause("") == ""


def test_all_male_cast_gets_male_focus_and_a_feminine_negative() -> None:
    from echotales.pipeline.persona.prompt import cast_tags, gender_negative

    assert "male focus" in cast_tags(["male"])
    assert "1girl" in gender_negative(["male", "male"])


def test_mixed_cast_is_left_alone() -> None:
    from echotales.pipeline.persona.prompt import cast_tags, gender_negative

    # Masculinising a panel that has a woman in it is the opposite failure.
    assert "male focus" not in cast_tags(["male", "female"])
    assert gender_negative(["male", "female"]) == ""
    assert gender_negative([]) == ""


def test_unresolved_cast_falls_back_to_the_beats_own_pronouns() -> None:
    """RI ch1 blocks 0/36: an unnamed mob/role cast leaves `genders` empty,
    and an empty tag list used to mean no steer at all -- confirmed on a
    real render (noobai bake-off) to still default female even with
    `gender_negative`'s negative-only exclusion applied. `cast_tags` now
    asks positively, from the same pronoun signal `gender_negative` trusts.
    """
    from echotales.pipeline.persona.prompt import cast_tags

    tags = cast_tags([], beat="He stood before the elders, his eyes cold.")
    assert "1boy" in tags
    assert "male focus" in tags

    tags = cast_tags([], beat="She walked past the elders, her sleeves trailing.")
    assert "1girl" in tags

    # No pronoun signal at all, or a genuinely mixed one: stay silent
    # rather than guess -- an empty tag is recoverable, a confidently wrong
    # one is not.
    assert cast_tags([], beat="The mountain path wound upward through mist.") == ""
    assert cast_tags([], beat="He grabbed her arm as she turned to face him.") == ""
    assert cast_tags([]) == ""

    # A resolved cast still wins outright -- the fallback only fires when
    # there is nothing else to go on.
    assert cast_tags(["female"], beat="He shouted from the courtyard.") == "1girl, solo"


def test_unresolved_figure_with_no_gender_signal_gets_a_silhouette_not_a_guess() -> None:
    """RI ch1: 7+ panels with an unresolved figure (director wrote "a
    figure" per SYSTEM rule 5) and zero gendered pronouns in the beat
    still rendered a detailed feminine face on a real render -- rule 6's
    "render as a silhouette" instruction was never backed by an actual
    tag. Fires only when the director's own text says a figure is there;
    a pure-environment beat with nobody in frame must stay silent, or
    this would hallucinate a person into a landscape shot.
    """
    from echotales.pipeline.persona.prompt import cast_tags

    tags = cast_tags([], beat="a figure, solo, stone_courtyard the elders murmured among themselves")
    assert "silhouette" in tags
    assert "1boy" not in tags
    assert "1girl" not in tags

    # No "a figure" marker at all -- a pure landscape/environment beat --
    # must stay silent, exactly as before this fix.
    assert cast_tags([], beat="The mountain path wound upward through mist.") == ""

    # A resolved gender or a beat's own pronoun still wins outright; the
    # silhouette fallback is the last resort, not a default.
    assert "silhouette" not in cast_tags(["male"], beat="a figure stood there")
    assert "silhouette" not in cast_tags(
        [], beat="a figure, solo -- he stood before the elders"
    )


def test_solo_is_asserted_as_its_own_leading_tag() -> None:
    """RI ch1 blocks 46/48/51-53/63: the director's own `layout` already
    said "a figure, solo" and the checkpoint still rendered two people --
    "solo" sat as one word inside a long tier-3 clause instead of being a
    leading Danbooru tag the way `1boy`/`crowd` already are. `cast_tags`
    now emits it whenever the resolved (or pronoun-inferred) headcount is
    exactly one, so it gets the same front-of-prompt priority.
    """
    from echotales.pipeline.persona.prompt import cast_tags

    assert cast_tags(["male"]) == "1boy, solo, male focus"
    assert cast_tags(["female"]) == "1girl, solo"
    # Two or more people: never assert solo, whatever the mix.
    assert "solo" not in cast_tags(["male", "male"])
    assert "solo" not in cast_tags(["male", "female"])
    # Empty-cast pronoun fallback also implies exactly one figure.
    assert "solo" in cast_tags([], beat="He stood before the elders, his eyes cold.")
    assert "solo" in cast_tags([], beat="She walked past the elders, her sleeves trailing.")


def test_style_base_carries_no_hair() -> None:
    from echotales.pipeline.persona.prompt import STYLE_SCENE

    # Hair belongs to whoever has it, not to every panel including empty ones.
    assert "flowing black hair" not in STYLE_SCENE


def test_negative_prompt_with_gender_clause_fits_clip() -> None:
    """Gender negative must not be truncated when stacked on the style base.

    Regression guard: `negative_for(STYLE_SCENE)` alone is ~69 tokens.
    Appending `_NEGATIVE_FEMININE` (~14 tokens) pushed the total to ~83,
    past CLIP's 75-token limit. CLIP silently drops from the right, so the
    gender clause — the last thing appended and the most important guard
    against feminisation — was the first thing to disappear at inference time.
    The fix re-fits with gender terms at the front of the priority list so
    they always survive truncation.
    """
    from echotales.pipeline.persona.prompt import (
        STYLE_SCENE,
        CLIP_TOKEN_LIMIT,
        _NEGATIVE_FEMININE,
        count_tokens,
        fit_to_budget,
        negative_for,
    )

    gender_neg = _NEGATIVE_FEMININE
    base_neg = negative_for(STYLE_SCENE)

    # Old assembly (gender last) exceeds the limit.
    old_assembled = base_neg + ", " + gender_neg
    assert count_tokens(old_assembled) > CLIP_TOKEN_LIMIT, (
        "pre-condition: old assembly must exceed the CLIP limit for this test to be meaningful"
    )

    # New assembly: gender terms at the front of the priority list.
    parts = (
        [p.strip() for p in gender_neg.split(",") if p.strip()]
        + [p.strip() for p in base_neg.split(",") if p.strip()]
    )
    result = fit_to_budget(parts)

    assert count_tokens(result) <= CLIP_TOKEN_LIMIT
    # Gender terms must survive.
    assert "1girl" in result
    assert "female" in result
