"""Regression form of the E3 probe (docs/research/ENGINEERING_PROBES.md).

Invariants that HOLD are plain assertions. Invariants the architecture documents claim and the code does not satisfy are
`xfail(strict=True)`: when someone fixes the code the test flips to XPASS and fails loudly, which is the signal to move the
claim from "open" to "closed" in the docs. Synthetic in-memory stores only; no database file, no novel text.

    env -u OPENAI_API_KEY python3 -m pytest scripts/chimera/test_eng_probe_e3_state_of.py -o addopts='' -p no:cacheprovider
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eng_probe_e3_state_of_invariants as E3  # noqa: E402


def test_prefix_truncation_leaves_state_of_unchanged() -> None:
    r = E3.metamorphic(60, 1)
    assert r["I1_prefix_truncation"]["violations"] == 0


@pytest.mark.parametrize("kind", ["alias", "attribute", "relation"])
def test_retraction_is_believed_before_and_hidden_after(kind: str) -> None:
    r = E3.check_retraction_vs_interval_end()[kind]
    assert r["retracted_visible_at_ch9"] and r["retracted_hidden_at_ch10"] and r["retracted_hidden_at_ch30"]
    assert r["closed_visible_story5_know30"] and r["closed_hidden_story12_know30"]


@pytest.mark.parametrize("kind", ["alias", "attribute", "relation"])
def test_false_facts_hidden_in_world_visible_to_system(kind: str) -> None:
    r = E3.check_false_hidden_in_world()[kind]
    assert r["hidden_from_reader"] and r["visible_to_system"]


@pytest.mark.xfail(strict=True, reason="E3/I4: the persona branch of state_of reads neither truth_status nor a retraction")
def test_false_persona_binding_hidden_from_reader() -> None:
    assert E3.check_false_hidden_in_world()["persona"]["hidden_from_reader"]


@pytest.mark.xfail(strict=True, reason="E3/I3: SelfPersonaBinding has no retracted_at, so retraction is not representable")
def test_persona_binding_retraction_representable() -> None:
    assert E3.check_retraction_vs_interval_end()["persona"]["retraction_representable"]


@pytest.mark.xfail(strict=True, reason="E3/I5: retracted_at is one global discourse position; a character never told stops believing")
def test_character_not_told_of_retraction_keeps_believing() -> None:
    assert E3.check_retraction_is_observer_global()["c_still_believes_at_ch30_when_never_told"]


@pytest.mark.xfail(strict=True, reason="E3/I6: off the MAIN timeline the default knowledge_pos is chapter 10**6 (omniscient reader)")
def test_reader_default_knowledge_is_not_omniscient_off_main_timeline() -> None:
    assert not E3.check_reader_knowledge_off_main_timeline()["dream_fact_learned_ch30_visible_to_reader_with_default_args"]


@pytest.mark.xfail(strict=True, reason="E3/I7: _voided_timelines is timeline-level; a VOIDED segment on MAIN_TIMELINE hides every MAIN fact")
def test_voided_main_segment_only_hides_its_own_facts() -> None:
    assert E3.check_canonicity()["voided_main_segment_ch5_6__fact_outside_segment_still_visible"]


@pytest.mark.xfail(strict=True, reason="E3/I8: equal learned_at_pos ties are broken by row iteration order")
def test_attribute_winner_does_not_depend_on_insertion_order() -> None:
    assert not E3.check_tie_order_dependence()["same_chapter_same_offset"]["order_dependent"]


def test_fact_learned_inside_a_chapter_is_invisible_until_the_next_position() -> None:
    """Documents the start-of-chapter reading of position (E4b): not a bug by itself, an inconsistency across writers."""
    r = E3.check_chapter_lag()
    assert not r["visible_at_p5"] and not r["visible_at_p5_9"] and r["visible_at_p6"]
    assert r["visible_with_explicit_end_of_chapter_knowledge"]
