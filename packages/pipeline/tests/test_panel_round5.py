"""Panel quality round 5 (EVOLUTION 4.173, D64): systemic gaps left after round 4, each pinned with the real line or prompt that
showed it. Short quotes only; no novel text beyond a clause."""

from __future__ import annotations

from echotales.pipeline.persona.genre import style_lead
from echotales.pipeline.render import face
from echotales.pipeline.render import framing as fr
from echotales.pipeline.render.compiler import (
    CharacterBrief,
    OutputMode,
    PanelBrief,
    compile_prompt,
    model_profile,
    trim_staging,
)
from echotales.pipeline.render.direction import (
    PanelDirection,
    _validate_composition,
    drop_place_conflicts,
    scrub_unstated,
)

NAMES = ["Zhou Mingrui"]
QUIET = "He thought about it for a while in the quiet."


def _key(f: fr.Framing) -> tuple[str, str]:
    return (f.size, f.focus)


def test_a_long_quiet_run_never_repeats_a_framing_more_than_twice() -> None:
    """LotM r4: one location, 16 panels, chest-up medium or close (a close shot the model drew as a medium) in 12 of them."""
    state = fr.FramingState()
    lines = ["He sat at the desk.", "Why would I suddenly have such a headache?", "I need to wake up! Now!", "Ouch...", "Pa!",
             "He had grown up reading web novels.", "This... What is this?", "Hey, putting it that way, it does not seem bad."]
    out = [fr.plan_framing(t, names=NAMES, state=state, opens_chapter=False) for t in lines * 3]
    keys = [_key(f) for f in out]
    assert all(not (keys[i] == keys[i + 1] == keys[i + 2]) for i in range(len(keys) - 2)), keys
    assert len({k for k in keys}) >= 4


def test_a_soft_pick_that_repeats_the_last_two_is_replaced_by_a_different_view() -> None:
    state = fr.FramingState()
    out = [fr.plan_framing('He sneered with contempt: "No."', names=NAMES, state=state, opens_chapter=False) for _ in range(6)]
    keys = [_key(f) for f in out]
    assert all(keys[i] != keys[i + 1] or keys[i] != keys[i + 2] for i in range(len(keys) - 2)), keys


def test_the_behind_and_top_down_views_say_so_and_show_no_face() -> None:
    behind = fr.framing_sentence(fr.Framing("medium", focus="behind"), "Klein")
    top = fr.framing_sentence(fr.Framing("medium", "birds-eye", focus="topdown"), "Klein")
    assert "directly behind" in behind and "face" in behind.lower()
    assert "directly above" in top


def test_a_behind_view_drops_the_face_sentence_and_the_front_facing_paragraph() -> None:
    b = PanelBrief(
        novel_id="", characters=[CharacterBrief(name="Klein", gender="male", age_band="adult", appearance={"hair": "black"})],
        mode=OutputMode.COLOUR, composition="Klein sits facing the viewer, a smile on his lips.", shot="medium",
        frame_focus="behind", framing="From behind.", face="a smile",
        staging="Set: a study; a desk. Blocking: Klein sits at the desk. Light: lamp.")
    out = compile_prompt(b, model_profile("z-image-turbo"))
    assert "face:" not in out.positive and "facing the viewer" not in out.positive


def test_an_insert_keeps_only_the_set_clauses_that_name_its_prop() -> None:
    """LotM r4 p7: 'insert of the lamp, nobody in the picture' still drew the man, because the Set clause kept 'a desk in front of
    him' and the notebook and books."""
    staging = ("Set: a study lit by a lamp with a classical Western style, on the right wall; a burly wood desk in front of him; "
               "an opened notebook on the desk. Light: faint crimson red.")
    out = trim_staging(staging, "prop", "close", subject="lamp")
    assert "lamp" in out and "in front of him" not in out and "notebook" not in out


def test_a_close_up_keeps_the_place_but_not_the_furniture_list() -> None:
    staging = ("Set: a study lit by a lamp, on the right wall; a burly wood desk in front of him; an opened notebook on the desk. "
               "Blocking: he sits. Light: faint crimson red.")
    out = trim_staging(staging, "", "close")
    assert "a study lit by a lamp" in out and "notebook" not in out and "Light: faint crimson red" in out


def test_the_xianxia_lead_has_no_ink_wash_wording_and_neither_has_the_fallback_sentence() -> None:
    """RI r4 cliff p5, p6, p8, p9: the director's paragraph was blanked, the panel fell to the old sentence ('ink-wash mountains,
    mist, painterly, muted') and came out as a white-ground ink-wash painting."""
    from echotales.pipeline.render.compiler import _style_sentence

    brief = PanelBrief(novel_id="", characters=[], manhua=True)
    for text in (_style_sentence(brief), style_lead("reverend-insanity")):
        assert "ink-wash" not in text.lower() and "ink wash" not in text.lower()


def test_a_blanked_paragraph_still_compiles_in_the_composed_form_with_the_webtoon_lead() -> None:
    from echotales.pipeline.render.compiler import CrowdBrief

    b = PanelBrief(
        novel_id="reverend-insanity", mode=OutputMode.COLOUR, shot="wide", composition="",
        characters=[CharacterBrief(name="Fang Yuan", gender="male", age_band="adult", appearance={"hair": "long black"})],
        crowd=CrowdBrief(description="sect fighters", size="many", stance="surrounding"),
        framing="Wide establishing shot.", frame_focus="establishing", staging="Set: a mountaintop. Light: dusk.")
    out = compile_prompt(b, model_profile("z-image-turbo"))
    assert out.positive.startswith(style_lead("reverend-insanity")) and "donghua" not in out.positive
    assert "facing Fang Yuan" in out.positive and "far side" in out.positive


def test_hands_are_stated_empty_when_the_text_names_no_weapon_or_held_thing() -> None:
    b = PanelBrief(
        novel_id="", mode=OutputMode.COLOUR, shot="medium", composition="Fang Yuan stands on the rock.", staging="Set: a rock.",
        characters=[CharacterBrief(name="Fang Yuan", gender="male", age_band="adult", appearance={"clothing": "green robes"})], empty_hands=True)
    assert "hands hang empty" in compile_prompt(b, model_profile("z-image-turbo")).positive
    b.empty_hands = False
    assert "hands hang empty" not in compile_prompt(b, model_profile("z-image-turbo")).positive


def test_a_weapon_the_passage_never_names_is_cut_from_the_paragraph() -> None:
    text = "Fang stands on the cliff with his sword drawn, staring out. The wind whips his hair."
    out, rejects = scrub_unstated(text, allowed="Fang Yuan stood on the cliff.", lead="Fang Yuan")
    assert "sword" not in out and "wind whips" in out and "weapon:sword" in rejects


def test_a_weapon_the_passage_names_is_kept() -> None:
    text = "Zhou Mingrui holds the revolver in his hand."
    out, rejects = scrub_unstated(text, allowed="He caressed the revolver's cold metal.", lead="")
    assert "revolver" in out and not rejects


def test_director_props_naming_an_unstated_weapon_are_dropped() -> None:
    d = PanelDirection(composition="Fang Yuan stands.", props=["sword", "a scroll"], key_objects=["Spring Breeze Sword"])
    out = _validate_composition(d, beat_text="Fang Yuan stood.", cast={"Fang Yuan": ""}, novel_id="", store=None, crowd_mood=None)
    assert out.props == ["a scroll"] and out.key_objects == []


def test_a_paragraph_place_the_staging_does_not_have_is_cut_not_just_flagged() -> None:
    """LotM/RI r4: 'a dark damp cave' written against a staged mountaintop; the retry failed and the paragraph was only flagged."""
    text = "Fang Yuan stands in a dark damp cave, wind in his hair. His eyes are cold."
    out = drop_place_conflicts(text, ["cave"])
    assert "cave" not in out and "eyes are cold" in out


def test_a_calm_default_gives_way_to_an_emotion_the_line_implies() -> None:
    assert face.infer_expression("calm unreadable stare", "Looking at the setting sun, Fang Yuan lightly laughed.") == "faint smile"
    assert face.infer_expression("calm unreadable stare", "Pa!") == "startled flinch"
    assert face.infer_expression("calm unreadable stare", "I failed in the end.") == "quiet bitter smile"


def test_the_directors_own_mood_decides_when_the_line_carries_no_cue() -> None:
    assert face.infer_expression("calm unreadable stare", "He looked at the lamp.", mood="somber, contemplative") == "sorrowful, downcast"
    assert face.infer_expression("calm unreadable stare", "He looked at the lamp.", mood="tense, expectant") == "tense, wary"
    assert face.infer_expression("calm unreadable stare", "He looked at the lamp.", mood="") == "calm unreadable stare"


def test_a_stated_calm_still_beats_the_mood() -> None:
    assert face.infer_expression("calm", "His expression did not change.", mood="somber") == "calm"


def test_the_paragraphs_own_calm_but_unreadable_clause_is_dropped_when_a_face_is_drawn() -> None:
    para = "Zhou sits at the desk. He appears lost in thought, his expression calm but unreadable. The lamp glows."
    out = face.drop_calm_clause(para)
    assert "unreadable" not in out and "lamp glows" in out and "sits at the desk" in out


def test_a_young_locked_body_states_a_boyish_build_not_only_a_youthful_face() -> None:
    """RI r4 rebirth p8-p9: 'a 15-year-old boy ... a smooth youthful face' still drew a tall grown man; the locked path carried no
    build, the unlocked path did."""
    from echotales.pipeline.render.compiler import identity_sentence

    class Lock:
        def description(self) -> str:
            return "long black hair, a grey hanfu"

    c = CharacterBrief(name="Fang Yuan", gender="male", age_band="youth", age_years=15, locked=Lock())
    out = identity_sentence(c)
    assert "15-year-old boy" in out and "slim boyish build" in out and "shorter" in out


def test_a_crowd_panel_is_seen_from_behind_the_lead_with_the_crowd_facing_him() -> None:
    """RI r5 cliff: with the crowd on the lead's side of the frame and both facing the viewer, 6 of 13 panels read as the lead
    standing among his own people. A medium or wide crowd panel is staged from behind him, the crowd across a gap facing him."""
    state = fr.FramingState()
    out = [fr.plan_framing("They did not move; everyone was wary of Fang Yuan.", names=["Fang Yuan"], crowd=True, state=state,
                           opens_chapter=False) for _ in range(4)]
    crowd_views = [f for f in out if f.focus == "behind" and f.subject == "crowd"]
    assert crowd_views
    text = fr.framing_sentence(crowd_views[0], "Fang Yuan")
    assert "side view" in text and "profile" in text and "turned toward him" in text and "gap" in text
    assert not any(f.focus == "behind" and f.subject == "crowd" for f in [fr.plan_framing("x", names=["A"], crowd=False,
                                                                                     state=fr.FramingState(), opens_chapter=False)])
