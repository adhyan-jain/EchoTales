"""Shot framing decided from the passage (panel quality round 3).

The failure this pins: 16 of 16 LotM panels and 9 of 13 RI cliff panels were one medium shot, and the compiled prompt never
named a shot at all. The lines below are real block text from those sheets (short quotes only)."""

from __future__ import annotations

import itertools

from echotales.pipeline.render import framing as fr

NAMES = ["Zhou Mingrui"]


def _run(lines: list[tuple[str, dict]], names=NAMES) -> list[fr.Framing]:
    state = fr.FramingState()
    return [fr.plan_framing(t, names=names, state=state, **kw) for t, kw in lines]


def test_the_chapter_opens_and_a_new_place_starts_on_a_wide_establishing_shot() -> None:
    out = _run([("Painful!", {}), ("Ouch...", {"new_place": True})])
    assert out[0].size == "wide" and out[0].focus == "establishing"
    assert out[1].focus == "establishing"


def test_a_line_about_eyes_is_an_eye_close_up() -> None:
    out = _run([("x", {}), ("At the very same moment, a pair of clear eyes quietly looked at the same lights.", {})])
    assert out[1].focus == "eyes" and out[1].size == "close"


def test_an_object_the_passage_centres_is_an_insert_even_when_the_director_listed_no_prop() -> None:
    out = _run([("x", {}), ("m", {}), ("n", {}), ("A gun? A revolver?", {"expression": "wide shocked eyes"})])
    assert out[3].focus == "prop" and out[3].subject == "revolver"


def test_a_sentence_about_the_person_is_not_an_insert() -> None:
    assert fr.prop_in("He sat down at the desk with the lamp beside him.", [], NAMES) == ""
    assert fr.prop_in("Zhou Mingrui looked at the revolver.", [], NAMES) == ""
    assert fr.prop_in("The lamp had a classical Western style. It was half the size of a head.", [], NAMES) == "lamp"


def test_a_director_listed_prop_the_text_names_is_used() -> None:
    assert fr.prop_in("She turned the key and the lock gave.", ["brass key"], ["Ada"]) == "brass key"
    assert fr.prop_in("She turned and left.", ["brass key"], ["Ada"]) == ""


def test_someone_else_speaking_to_the_lead_is_an_over_the_shoulder_shot() -> None:
    spoken = "- someone who is not in CAST (draw them among the others) says to Fang Yuan: hand it over"
    out = _run([("x", {}), ('"Hand it over!"', {"spoken": spoken})], names=["Fang Yuan"])
    assert out[1].focus == "over-shoulder" and out[1].angle == "over-the-shoulder"


def test_an_emotional_peak_is_a_close_up_and_a_threat_is_seen_from_below() -> None:
    out = _run([("x", {}), ('He sneered with contempt: "You are nothing."', {})])
    assert out[1].size == "close" and out[1].angle == "low-angle"


def test_no_size_repeats_a_third_time_and_a_quiet_run_still_moves() -> None:
    quiet = [("He thought about it for a while in the quiet.", {}) for _ in range(12)]
    out = _run([("opening", {}), *quiet])
    sizes = [o.size for o in out]
    assert all(not (sizes[i] == sizes[i + 1] == sizes[i + 2]) for i in range(len(sizes) - 2)), sizes
    assert len(set(sizes)) == 3


def test_inserts_are_not_back_to_back() -> None:
    out = _run([("x", {})] + [("The lamp had a classical Western style.", {})] * 4)
    flags = [o.focus == "prop" for o in out]
    assert not any(a and b for a, b in itertools.pairwise(flags))


def test_the_sentence_names_the_shot_and_the_insert_has_nobody_in_it() -> None:
    insert = fr.Framing("close", focus="prop", subject="revolver")
    assert "revolver" in fr.framing_sentence(insert, "Zhou Mingrui") and "nobody" in fr.framing_sentence(insert, "Zhou Mingrui")
    assert fr.framing_sentence(fr.Framing("close", focus="eyes"), "Ada").startswith("Extreme close-up on Ada's eyes")
    assert fr.framing_sentence(fr.Framing("wide", focus="establishing"), "Ada").startswith("Wide establishing")
    assert "low angle" in fr.framing_sentence(fr.Framing("medium", "low-angle"), "Ada")
