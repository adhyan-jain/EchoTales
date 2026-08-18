"""Temporary transformations (`persona/forms.py`)."""

from __future__ import annotations

from echotales.pipeline.persona.forms import detect_form

HUMAN = "tall and lean, midnight black hair, jet black eyes"


def test_ordinary_prose_has_no_form() -> None:
    report = detect_form("Fang Yuan stood in the courtyard, expressionless.")
    assert not report.active
    assert report.apply_to(HUMAN) == HUMAN


def test_extra_arms_are_added_to_the_human_description() -> None:
    """A partial transformation is not a new creature."""
    report = detect_form("Six zombie arms sprouted from his back.")
    assert report.overlay is not None and report.overlay.name == "many-armed"
    applied = report.apply_to(HUMAN)
    assert applied.startswith(HUMAN)
    assert "additional arms" in applied


def test_a_full_beast_replaces_the_human_description() -> None:
    report = detect_form("He transformed into a giant beast, roaring.")
    assert report.overlay is not None and report.overlay.replaces_body
    assert HUMAN not in report.apply_to(HUMAN)


def test_partial_wins_over_the_full_form_it_contains() -> None:
    report = detect_form("Caught half-transformed into a beast, he lunged.")
    assert report.overlay is not None and report.overlay.name == "partial"


def test_the_form_lifts_the_negatives_it_needs() -> None:
    """Without this a transformation cannot render at all.

    The standing negative prompt forbids extra limbs and claws, which is
    right for every ordinary panel and is exactly the content of these.
    """
    negative = "deformed hands, extra limbs, extra arms, blurry"
    report = detect_form("Six zombie arms sprouted from his back.")
    filtered = report.filtered_negative(negative)
    assert "extra arms" not in filtered
    assert "extra limbs" not in filtered
    # Everything unrelated survives.
    assert "deformed hands" in filtered and "blurry" in filtered


def test_a_panel_without_a_form_keeps_every_negative() -> None:
    negative = "deformed hands, extra limbs, blurry"
    assert detect_form("He walked on.").filtered_negative(negative) == negative


def test_reverting_needs_no_detection() -> None:
    """Prose announces a transformation loudly and reverts in silence, so
    the overlay lasts exactly as long as the text says it does."""
    during = detect_form("He transformed into a giant wolf.")
    after = detect_form("He straightened his robes and walked away.")
    assert during.active and not after.active
    assert after.apply_to(HUMAN) == HUMAN
