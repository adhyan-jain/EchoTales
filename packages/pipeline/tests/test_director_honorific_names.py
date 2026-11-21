"""Honorific punctuation and spacing must not change who a name is (P&P e2e 2026-11-22).

The director wrote "Mr Bennet" for the cast member "Mr. Bennet"; every cast check compared the raw strings, so the character
was dropped as "outside CAST", stripped as "out-of-scene" and replaced in the paragraph by "a figure".
"""

from __future__ import annotations

import pytest

from echotales.core.enums import BlockType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.render.compiler import _match_director_characters
from echotales.pipeline.render.direction import CharacterDirection, PanelDirection, _validate_direction, name_key

PASSAGE = "Mr. Bennet replied that he had not. Mrs. Bennet was in the room."
CAST = {"Mr. Bennet": "black hair", "Mrs. Bennet": "grey hair"}


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="a",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=PASSAGE)]))
    for sid, name in (("t:1", "Mr. Bennet"), ("t:2", "Mrs. Bennet")):
        store.add_self(Self(id=sid, novel_id="t", canonical_label=name,
                            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.conn.commit()
    return store


@pytest.mark.parametrize(
    ("a", "b"),
    [("Mr Bennet", "Mr. Bennet"), ("MR. BENNET", "Mr. Bennet"), ("Mrs  Bennet", "Mrs. Bennet"), ("Mr. Bennet's", "Mr Bennet")],
)
def test_name_key_ignores_honorific_full_stops_spacing_and_case(a: str, b: str) -> None:
    assert name_key(a) == name_key(b)


def test_name_key_keeps_different_people_apart() -> None:
    assert name_key("Mr. Bennet") != name_key("Mrs. Bennet")


def test_a_director_character_without_the_full_stop_is_not_dropped_as_outside_cast(tmp_path) -> None:
    d = PanelDirection(characters=[CharacterDirection(name="Mr Bennet"), CharacterDirection(name="Mrs Bennet")])
    out = _validate_direction(d, beat_text=PASSAGE, cast=CAST, novel_id="t", store=_store(tmp_path))
    assert [c.name for c in out.characters] == ["Mr Bennet", "Mrs Bennet"]


def test_the_name_without_a_full_stop_is_not_stripped_from_the_action_as_out_of_scene(tmp_path) -> None:
    d = PanelDirection(action="Mr Bennet sits in a drawing room.", layout="Mr Bennet on the left")
    out = _validate_direction(d, beat_text=PASSAGE, cast=CAST, novel_id="t", store=_store(tmp_path))
    assert "Mr Bennet" in out.action and "a figure" not in out.action
    assert "Mr Bennet" in out.layout


def test_the_name_without_a_full_stop_is_not_replaced_in_the_composed_paragraph(tmp_path) -> None:
    d = PanelDirection(composition="Mr Bennet sits in an armchair while Mrs Bennet stands at the door.")
    out = _validate_direction(d, beat_text=PASSAGE, cast=CAST, novel_id="t", store=_store(tmp_path))
    assert out.composition.startswith("Mr Bennet sits") and "a figure" not in out.composition


def test_a_real_outsider_is_still_dropped(tmp_path) -> None:
    d = PanelDirection(characters=[CharacterDirection(name="Mr Darcy")])
    assert _validate_direction(d, beat_text=PASSAGE, cast=CAST, novel_id="t", store=_store(tmp_path)).characters == []


def test_the_compiler_pairs_a_director_name_without_the_full_stop_with_the_cast_member(tmp_path) -> None:
    store = _store(tmp_path)
    pairs = _match_director_characters(store, ["t:1", "t:2"], [CharacterDirection(name="Mrs Bennet"), CharacterDirection(name="Mr Bennet")])
    assert [(cd.name, sid) for cd, sid in pairs] == [("Mrs Bennet", "t:2"), ("Mr Bennet", "t:1")]
