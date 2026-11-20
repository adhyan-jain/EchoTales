"""The director's paragraph invents a second person and a sky (panel quality round 3, defects 4 and 6).

Measured on the M1 sheets: gemma2:9b opened 6 of 13 RI cliff paragraphs with "A lone figure stands on the mountaintop ..." beside
the named lead, and the image showed a silhouetted figure on a distant cliff top in 9 of 13 panels; the rebirth paragraphs lit
the room with "the soft glow of moonlight" while the staging sheet said rain, and the picture had a full moon in heavy rain."""

from __future__ import annotations

from echotales.pipeline.render.direction import (
    PanelDirection,
    _validate_composition,
    scrub_unstated,
)


def test_an_unstated_lone_figure_beside_a_named_lead_becomes_the_lead() -> None:
    text = "A lone figure stands on a windswept mountaintop as the sun dips below the horizon. Fang Yuan gazes out."
    out, rejects = scrub_unstated(text, allowed="Fang Yuan was in deep green robes.", lead="Fang Yuan")
    assert "lone figure" not in out and out.startswith("Fang Yuan stands on a windswept mountaintop")
    assert any(r.startswith("figure:") for r in rejects)


def test_a_figure_the_passage_states_is_kept() -> None:
    text = "A hooded figure waits at the gate. Ada watches."
    out, rejects = scrub_unstated(text, allowed="A hooded figure waited at the gate. Ada watched.", lead="Ada")
    assert "hooded figure" in out and not rejects


def test_a_silhouette_clause_the_text_never_states_is_dropped_but_the_sentence_survives() -> None:
    text = "Fang stands at the cliff edge, his silhouette outlined against the fiery sky. He stares ahead, his expression unreadable."
    out, rejects = scrub_unstated(text, allowed="Fang Yuan stood at the cliff edge. The sky burned.", lead="Fang Yuan")
    assert "silhouette" not in out and "Fang stands at the cliff edge" in out and "expression unreadable" in out
    assert rejects


def test_a_moon_the_text_and_staging_never_state_is_removed_from_a_rainy_night() -> None:
    text = "Fang Yuan stands alone in a room lit by the soft glow of moonlight filtering through a window. He appears lost in thought."
    out, rejects = scrub_unstated(text, allowed="Set: a window, rain falling outside. Light: night. At the very same moment", lead="Fang Yuan")
    assert "moon" not in out.lower() and "lost in thought" in out and "Fang Yuan stands alone in a room" in out
    assert "sky:moon" in rejects


def test_a_sky_the_staging_states_is_kept_in_any_wording() -> None:
    text = "The setting sun casts long shadows. Fang Yuan stares out."
    out, rejects = scrub_unstated(text, allowed="Light: sunset.", lead="Fang Yuan")
    assert out == text and not rejects


def test_rain_is_kept_when_the_passage_says_it_and_the_moon_beside_it_is_not() -> None:
    text = "Rain falls on the mountain under a pale moon. Fang Yuan stands in it."
    out, rejects = scrub_unstated(text, allowed="The spring rain quietly rained down on the mountain.", lead="Fang Yuan")
    assert "Rain falls" in out and "moon" not in out and "Fang Yuan stands in it." in out
    assert rejects == ["sky:moon"]


def test_validate_composition_applies_it_with_the_staging_as_allowed_text() -> None:
    d = PanelDirection(
        composition="A lone figure stands by a window. The moonlight casts long shadows across the room. Fang Yuan gazes out.",
        staging="Set: a window, rain falling outside. Blocking: Fang Yuan stands by the window. Light: night.",
    )
    out = _validate_composition(d, beat_text="He looked quietly.", cast={"Fang Yuan": ""}, novel_id="", store=None, crowd_mood=None)
    assert "lone figure" not in out.composition and "moon" not in out.composition.lower()
    assert "Fang Yuan gazes out" in out.composition
    assert any(r == "sky:moon" for r in out.grounding_rejects)


def test_a_cut_clause_never_leaves_a_dangling_fragment() -> None:
    text = "The mountaintop is bathed in the pale light of the moon. Fang Yuan stands alone against it."
    out, rejects = scrub_unstated(text, allowed="Light: night.", lead="Fang Yuan")
    assert out == "Fang Yuan stands alone against it." and "sky:moon" in rejects


def _fabricated(text: str, cast=None):
    d = PanelDirection(composition=text)
    return _validate_composition(d, beat_text="He stood at the window.", cast=cast or {"Fang Yuan": ""}, novel_id="", store=None, crowd_mood=None)


def test_an_invented_item_name_is_never_turned_into_the_lead() -> None:
    """Round 3, RI rebirth: 'He holds a vial of Spring Water' became 'a vial of Fang Yuan' and 'holds his Spring Sword' became
    'holds his Fang Yuan'."""
    out = _fabricated("Fang Yuan stands by the window. He holds a vial of Spring Water, gazing out.")
    assert "vial of Fang Yuan" not in out.composition and "Spring Water" not in out.composition
    assert "holds a vial" in out.composition
    out = _fabricated("Fang Yuan stands by the window. He holds his Spring Sword in one hand.")
    assert "holds his Fang Yuan" not in out.composition and "Spring Sword" not in out.composition
    assert "a small object in one hand" in out.composition


def test_an_invented_person_name_in_a_one_person_cast_still_becomes_the_lead() -> None:
    out = _fabricated("Zhou Yuan sits at his desk, frowning.", cast={"Zhou Mingrui": ""})
    assert out.composition.startswith("Zhou Mingrui sits")
