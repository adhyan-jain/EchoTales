from echotales.pipeline.voice.delivery import strip_enclosing_quotes


def test_mismatched_curly_double_quotes_are_stripped():
    # Reverend Insanity ch1 closes a line with an opening mark; the bubble and the TTS both showed it.
    assert strip_enclosing_quotes("\u201cYou have committed heinous sins!\u201c") == "You have committed heinous sins!"
    assert strip_enclosing_quotes("\u201dBackwards marks\u201d") == "Backwards marks"


def test_apostrophe_led_word_is_kept():
    assert strip_enclosing_quotes("'Tis late, he said.") == "'Tis late, he said."
