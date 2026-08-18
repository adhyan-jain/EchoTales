"""Novel-specific word senses derived from the graph (`world/lexicon.py`)."""

from __future__ import annotations

from echotales.pipeline.world.lexicon import WorldLexicon, _ANY_USE_RE, _EPITHET_PATTERNS


def _epithets(text: str) -> list[str]:
    return [w for p in _EPITHET_PATTERNS for w in p.findall(text)]


def test_vocative_and_address_forms_are_epithets() -> None:
    assert _epithets("“Fang Yuan you damn demon, just because you wanted...") == ["demon"]
    assert _epithets("“Wicked demon, what are you laughing about?”") == ["demon"]
    assert "demon" in _epithets("He knew that this demon would not stop.")


def test_plain_description_is_not_an_epithet() -> None:
    # The novel's real creatures must not be glossed away.
    assert _epithets("A wolf howled somewhere on the mountain.") == []
    assert _epithets("The worm crawled into the aperture.") == []
    # ...but they still count toward the denominator.
    assert _ANY_USE_RE.findall("A wolf howled") == ["wolf"]


def test_capitalised_proper_names_are_left_alone() -> None:
    # "Demon Suppression Tower" is a place, not name-calling.
    assert _ANY_USE_RE.findall("They fled to the Demon Suppression Tower.") == []


def test_director_note_names_the_person() -> None:
    lex = WorldLexicon("reverend-insanity", {"demon": ["Fang Yuan"]})
    note = lex.director_note()
    assert "'demon' means Fang Yuan, a human being" in note
    assert "Draw them as human" in note


def test_negative_terms_suppress_the_costume() -> None:
    lex = WorldLexicon("reverend-insanity", {"demon": ["Fang Yuan"]})
    negatives = lex.negative_terms()
    for term in ("demon horns", "red eyes", "fangs"):
        assert term in negatives


def test_an_empty_lexicon_contributes_nothing() -> None:
    lex = WorldLexicon("some-novel")
    assert lex.director_note() == ""
    assert lex.negative_terms() == ""
