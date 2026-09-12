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
