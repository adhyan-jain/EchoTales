"""Per-line emotion (panel quality round 3, defect 7): a neutral director face is upgraded from the passage's own words, a stated
calm is never overridden, and every emotion is written as the parts of a face."""

from __future__ import annotations

from echotales.pipeline.render import face


def test_the_example_phrase_the_director_copies_is_neutral() -> None:
    for text in ("calm unreadable stare", "calm", "", "Calm", "blank"):
        assert face.is_neutral(text)
    assert not face.is_neutral("cold mocking smile, narrowed eyes")


def test_a_neutral_face_is_upgraded_from_the_lines_emotion_words() -> None:
    assert face.infer_expression("calm unreadable stare", "Painful!") == "painful grimace"
    assert face.infer_expression("calm unreadable stare", "Ouch...") == "painful grimace"
    assert face.infer_expression("calm", "Hehe, I can end up getting some spare time") == "laughing"
    assert face.infer_expression("", "Looking at the setting sun, Fang Yuan lightly laughed.") == "cold mocking smile"


def test_a_stated_calm_is_never_overridden() -> None:
    passage = "His expression did not change, it was calm, though the pain was great."
    assert face.infer_expression("calm unreadable stare", passage) == "calm unreadable stare"


def test_a_passage_with_no_emotion_keeps_the_directors_face() -> None:
    assert face.infer_expression("calm unreadable stare", "The room was quiet.") == "calm unreadable stare"
    assert face.infer_expression("cold mocking smile", "The room was quiet.") == "cold mocking smile"


def test_a_weak_director_frown_gives_way_to_a_stronger_cue_in_the_text() -> None:
    assert face.infer_expression("frowning", "Painful!") == "painful grimace"
    assert face.infer_expression("frowning", "He was thinking.") == "frowning"


def test_each_family_is_written_as_facial_parts() -> None:
    mock = face.drawn_face("cold mocking smile, narrowed eyes")
    assert "corner of the mouth" in mock and "narrowed" in mock and "chin raised" in mock
    assert "eyes wide open" in face.drawn_face("wide shocked eyes") and "eyebrows raised" in face.drawn_face("wide shocked eyes")
    assert "teeth" in face.drawn_face("furious glare, clenched teeth")
    assert face.drawn_face("calm unreadable stare").startswith("calm and still")
    assert face.drawn_face("wry half-smile") == "wry half-smile"
