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
    build_image_prompt,
    condense_clause,
    count_tokens,
    fit_to_budget,
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


class TestCondenseClause:
    def test_it_keeps_what_identifies_over_what_comes_first(self) -> None:
        """Clause order is the *reference sheet's* order, and the sheet has
        room for everything. A panel does not: a positional cut kept "tall
        and lean" and dropped the waist-length black hair, which is the one
        feature that makes this character recognisable in silhouette."""
        out = condense_clause(_APPEARANCE)
        assert "midnight black" in out
        assert "narrow eyes" in out

    def test_surviving_parts_keep_their_original_order(self) -> None:
        """Ranking decides what survives, not how it reads."""
        out = condense_clause(_APPEARANCE)
        assert out.index("hair") < out.index("eyes")

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
