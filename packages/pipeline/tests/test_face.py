"""Per-line emotion (panel quality round 3, defect 7): a neutral director face is upgraded from the passage's own words, a stated
calm is never overridden, and every emotion is written as the parts of a face."""

from __future__ import annotations

from pathlib import Path

from echotales.pipeline.render import face


def test_the_example_phrase_the_director_copies_is_neutral() -> None:
    for text in ("calm unreadable stare", "calm", "", "Calm", "blank"):
        assert face.is_neutral(text)
    assert not face.is_neutral("cold mocking smile, narrowed eyes")


def test_a_neutral_face_is_upgraded_from_the_lines_emotion_words() -> None:
    assert face.infer_expression("calm unreadable stare", "Painful!") == "painful grimace"
    assert face.infer_expression("calm unreadable stare", "Ouch...") == "painful grimace"
    assert face.infer_expression("calm", "Hehe, I can end up getting some spare time") == "laughing"
    assert face.infer_expression("", "Looking at the setting sun, Fang Yuan lightly laughed.") == "faint smile"


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


def test_a_neutral_face_takes_the_scenes_mood_and_the_earliest_mood_word_wins() -> None:
    # RI ch1 (v56): 34 of 45 director faces were the example phrase; the mood fallback knew only sad, tense and happy, so a
    # "pensive" or "reverent" scene fell through to a flat stare and the nine "tense" ones all read the same "tense, wary".
    quiet = "The room was quiet."
    assert face.infer_expression("calm unreadable stare", quiet, mood="pensive, foreboding") == "thoughtful, eyes lowered"
    assert face.infer_expression("calm unreadable stare", quiet, mood="reverent, solemn") == "solemn, eyes lowered"
    assert face.infer_expression("calm unreadable stare", quiet, mood="triumphant, menacing") == "cold mocking smile"
    assert face.infer_expression("calm unreadable stare", quiet, mood="tense, contemplative") == "tense, wary"
    assert face.infer_expression("calm unreadable stare", quiet, mood="contemplative, tense") == "thoughtful, eyes lowered"
    assert not face.is_neutral(face.infer_expression("calm unreadable stare", quiet, mood="pensive"))


def test_the_directors_vocabulary_offers_no_stock_face_phrase_to_copy() -> None:
    # The model copies the last example of a list when the line is thin (4.171: the neutral phrase on 34 of 45 RI panels). The
    # first round-8 fix replaced it with "thin bitter smile, eyes lowered" and gemma2:9b wrote exactly that for most of Mr.
    # Bennet's panels in the P&P rerun, so the prompt now names no phrase at all.
    from echotales.pipeline.render import direction

    src = Path(direction.__file__).read_text(encoding="utf-8")
    assert "calm unreadable stare" not in src and "thin bitter smile" not in src and "cold mocking smile, narrowed eyes" not in src
