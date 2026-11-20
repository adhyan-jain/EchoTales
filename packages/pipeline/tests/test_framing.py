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


def test_a_list_of_looks_that_names_eyes_is_a_portrait_not_an_eye_crop() -> None:
    out = _run([("x", {}), ("Black hair, brown eyes, a linen shirt, thinly built, average-looking features.", {})])
    assert out[1].focus != "eyes"


def test_began_and_begin_are_not_a_person_begging_from_below() -> None:
    out = _run([("x", {}), ("It began to rain and the street began to empty.", {})])
    assert out[1].angle == "eye-level"


def test_an_object_the_passage_centres_is_an_insert_even_when_the_director_listed_no_prop() -> None:
    out = _run([("x", {}), ("m", {}), ("n", {}), ("A gun? A revolver?", {"expression": "wide shocked eyes"})])
    assert out[3].focus == "prop" and out[3].subject == "revolver"


def test_a_sentence_about_the_person_is_not_an_insert() -> None:
    assert fr.prop_in("He sat down at the desk with the lamp beside him.", [], NAMES) == ""
    assert fr.prop_in("Zhou Mingrui looked at the revolver.", [], NAMES) == ""
    assert fr.prop_in("The lamp had a classical Western style. It was half the size of a head.", [], NAMES) == "lamp"


def test_a_director_listed_prop_the_text_names_is_used() -> None:
    assert fr.prop_in("The key turned and the lock gave.", ["brass key"], ["Ada"]) == "brass key"
    assert fr.prop_in("She turned the key and the lock gave.", ["brass key"], ["Ada"]) == ""
    assert fr.prop_in("Hey, putting it that way, I can read my books at leisure.", ["books"], ["Ada"]) == ""


def test_someone_else_speaking_to_the_lead_is_an_over_the_shoulder_shot() -> None:
    spoken = "- someone who is not in CAST (draw them among the others) says to Fang Yuan: hand it over"
    out = _run([("x", {}), ('"Hand it over!"', {"spoken": spoken})], names=["Fang Yuan"])
    assert out[1].focus == "over-shoulder" and out[1].angle == "over-the-shoulder"


def test_over_the_shoulder_needs_someone_else_in_the_scene() -> None:
    spoken = "- someone who is not in CAST (draw them among the others) says to Zhou Mingrui: hello"
    out = _run([("x", {}), ('"Hello."', {"spoken": spoken, "others_present": False})])
    assert out[1].focus != "over-shoulder"


def test_a_weapon_insert_may_follow_another_insert_but_a_lamp_may_not() -> None:
    out = _run([("x", {}), ("The lamp had a classical Western style.", {}), ("A gun? A revolver?", {})])
    assert [o.focus for o in out[1:]] == ["prop", "prop"] and out[2].subject == "revolver"
    out = _run([("x", {}), ("The lamp had a classical Western style.", {}), ("The candle burned low.", {})])
    assert out[2].focus != "prop"


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
    assert "natural realistic proportions" in fr.framing_sentence(fr.Framing("close"), "Ada")
    assert fr.framing_sentence(fr.Framing("close", focus="eyes"), "Ada").startswith("Extreme close-up on Ada's eyes")
    assert fr.framing_sentence(fr.Framing("wide", focus="establishing"), "Ada").startswith("Wide establishing")
    assert "low angle" in fr.framing_sentence(fr.Framing("medium", "low-angle"), "Ada")


def test_a_close_up_keeps_the_face_sentences_and_drops_the_scene_they_sat_in() -> None:
    para = ("Fang stands amidst the carnage. The battlefield is a gruesome sight, littered with corpses. "
            "His face shows a cold mocking smile with narrowed eyes.")
    assert fr.crop_composition(para, "") == "His face shows a cold mocking smile with narrowed eyes."
    assert fr.crop_composition(para, "eyes") == "His face shows a cold mocking smile with narrowed eyes."
    assert fr.crop_composition("The room is quiet. Dust drifts.", "") == "The room is quiet."
    assert fr.crop_composition("The room is quiet.", "eyes") == ""
