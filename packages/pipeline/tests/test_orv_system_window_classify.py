import pytest
from echotales.core.enums import BlockType
from echotales.pipeline.ingest.classify import classify_block, is_system_window


def test_orv_bracketed_constellation_system_window():
    text = "[The constellation 'Demon-like Judge of Fire' is watching you.]"
    assert is_system_window(text)
    classified = classify_block(text)
    assert classified.block_type is BlockType.SYSTEM_WINDOW


def test_orv_bracketed_skill_activation_system_window():
    text = "[Exclusive skill 'Omniscient Reader's Viewpoint' Lv.1 has been activated.]"
    assert is_system_window(text)
    classified = classify_block(text)
    assert classified.block_type is BlockType.SYSTEM_WINDOW


def test_orv_bracketed_scenario_system_window():
    text = "[Main Scenario #1 – Proof of Value has begun.]"
    assert is_system_window(text)
    classified = classify_block(text)
    assert classified.block_type is BlockType.SYSTEM_WINDOW


def test_ordinary_bracketed_text_is_not_system_window():
    text = "[He walked towards the door slowly.]"
    assert not is_system_window(text)
    classified = classify_block(text)
    assert classified.block_type is BlockType.PROSE


@pytest.mark.parametrize(
    "text",
    [
        "[He wondered about the probability of finding coins in that channel of the cave.]",
        "[She always thought her grandmother's stories were just a fable, nothing more.]",
    ],
)
def test_bracketed_prose_with_common_words_is_not_system_window(text):
    """Regression: the keyword-only branch of is_system_window must not fire on
    ordinary bracketed prose just because it contains a word that also appears
    in system-notification jargon (e.g. "probability", "coins", "channel",
    "fable" are ordinary English, not LitRPG-specific -- see classify.py's
    _SYSTEM_KEYWORDS). LOTM and ORV both use full-paragraph brackets for
    internal monologue, structurally identical to a system notification per
    _looks_bracketed, so a false positive here silently diverts story prose
    out of identity processing."""
    assert not is_system_window(text)
    classified = classify_block(text)
    assert classified.block_type is BlockType.PROSE


def test_long_bracketed_paragraph_with_system_keyword_is_not_system_window():
    text = (
        "[He kept thinking about the strange dokkaebi mask he had seen in the "
        "market that morning, wondering if it was some kind of tourist "
        "giveaway or just a trinket, and whether it was even worth asking "
        "the vendor about its origin before the sun went down.]"
    )
    assert not is_system_window(text)
    classified = classify_block(text)
    assert classified.block_type is BlockType.PROSE
