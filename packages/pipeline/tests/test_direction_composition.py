"""The director's composed paragraph: grounding validators, thin-context marking, prompt contents."""

from __future__ import annotations

from echotales.core.enums import BlockType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.render.direction import PanelDirection, _validate_direction, build_prompt, system_prompt

PASSAGE = "Fang Yuan stood on the cliff. The elders of the righteous sects surrounded him. He held the Spring Autumn Cicada."
CAST = {"Fang Yuan": "black hair"}


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="a",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=PASSAGE)]))
    for sid, name, ch in (("t:1", "Fang Yuan", 1.0), ("t:2", "Bai Ning Bing", 108.0)):
        store.add_self(Self(id=sid, novel_id="t", canonical_label=name,
                            first_attested_pos=DiscoursePosition(chapter=ch, offset=0), kind=TargetKind.SELF))
    store.conn.commit()
    return store


def validate(d: PanelDirection, tmp_path, crowd_mood=None) -> PanelDirection:
    return _validate_direction(d, beat_text=PASSAGE, cast=CAST, novel_id="t", store=_store(tmp_path), crowd_mood=crowd_mood)


def test_defaults_mark_a_panel_as_text_grounded_with_no_paragraph() -> None:
    d = PanelDirection()
    assert d.composition == "" and d.visual_source == "text"


def test_a_grounded_paragraph_survives_with_text_named_objects_and_groups() -> None:
    para = ("A wide shot on a cliff at dusk. Fang Yuan stands in the centre, calm, holding the Spring Autumn Cicada, "
            "ringed by the elders of the righteous sects.")
    d = validate(PanelDirection(composition=para, visual_source="text"), tmp_path=_tmp())
    assert d.composition == para and d.grounding_rejects == []


def test_a_known_character_outside_the_cast_is_stripped_from_the_paragraph(tmp_path) -> None:
    d = validate(PanelDirection(composition="Fang Yuan faces Bai Ning Bing across the rock."), tmp_path)
    assert "Bai Ning Bing" not in d.composition and "a figure" in d.composition
    assert d.grounding_rejects


def test_an_invented_name_is_stripped_but_a_capitalised_sentence_start_is_not_a_name(tmp_path) -> None:
    d = validate(PanelDirection(composition="Dusk falls. Fang Yuan watches Lady Zed draw her sword."), tmp_path)
    assert "Lady Zed" not in d.composition and d.composition.startswith("Dusk falls.")


def test_an_invented_group_blanks_the_paragraph(tmp_path) -> None:
    d = validate(PanelDirection(composition="Fang Yuan stands among cheering onlookers and guards."), tmp_path)
    assert d.composition == "" and d.grounding_rejects


def test_a_paragraph_that_empties_a_confirmed_crowd_is_blanked(tmp_path) -> None:
    d = validate(PanelDirection(composition="Fang Yuan stands alone on the cliff."), tmp_path, crowd_mood="hostile")
    assert d.composition == ""


def test_visual_source_other_than_text_or_inferred_becomes_text() -> None:
    d = _validate_direction(PanelDirection(composition="", visual_source="guess"), beat_text=PASSAGE, cast=CAST)
    assert d.visual_source == "text"


def test_the_request_asks_for_the_paragraph_and_shows_probe_style_examples_as_structure_only() -> None:
    text = build_prompt(PASSAGE, cast=CAST, novel_style="x", recent_shots=["wide", "wide"])
    assert "  composition   " in text and "visual_source" in text
    assert "wide, wide" in text  # the shot-run limit needs the previous shots
    sys = system_prompt("")
    assert "structure only" in sys.lower() and "empty rock" in sys


def _tmp():
    import tempfile
    from pathlib import Path

    return Path(tempfile.mkdtemp())
