"""Panel quality round 6 (EVOLUTION 4.177, D66): the from-behind crowd view never fired because only the one dedicated crowd cut carried
the crowd flag, while the crowd stood in 12 of 13 RI cliff panels (staging Blocking and the director's `others`)."""

from __future__ import annotations

from types import SimpleNamespace

from echotales.pipeline.render import framing as fr

BLOCKING = ("Set: a mountaintop. Blocking: Fang Yuan stands alone facing right; the others stand packed close in a dense uneven crowd "
            "on one side of the frame, at different depths, all facing Fang Yuan. Light: sun.")


def test_the_crowd_is_found_in_the_staging_or_the_directors_others_not_only_the_crowd_cut() -> None:
    assert fr.crowd_in_scene(None, BLOCKING)
    assert fr.crowd_in_scene(SimpleNamespace(kind="crowd", count=0), "")
    assert fr.crowd_in_scene(SimpleNamespace(kind="group of sect elders", count=0), "")
    assert not fr.crowd_in_scene(None, "Set: a desk. Blocking: Klein sits alone facing left. Light: lamp.")
    assert not fr.crowd_in_scene(None, "")


def test_a_crowd_in_the_scene_turns_a_medium_panel_to_the_from_behind_view_and_cancels_over_the_shoulder() -> None:
    state = fr.FramingState()
    first = fr.plan_framing("Stop attempting to resist.", names=["Fang Yuan"], spoken='Elder says: "Stop attempting to resist."',
                            crowd_in_scene=True, state=state, opens_chapter=False)
    assert first.focus == "behind" and first.subject == "crowd"


def test_the_from_behind_crowd_view_is_never_drawn_three_times_running() -> None:
    state = fr.FramingState()
    out = [fr.plan_framing("They did not move.", names=["Fang Yuan"], crowd_in_scene=True, state=state, opens_chapter=False) for _ in range(6)]
    run = 0
    for f in out:
        run = run + 1 if (f.focus == "behind" and f.subject == "crowd") else 0
        assert run <= 2


PERSON_WORDS = r"\b(faces?|eyes|clothes|robes|persons?|people|man|men|he|his|him|characters?|proportions|subject)\b"


def test_an_insert_prompt_has_no_person_word_in_the_lead_the_frame_or_the_grade() -> None:
    """LotM r5: the lamp and pipe inserts drew one or two men (2 of 4); the genre lead said 'mature faces with natural eyes' and
    'gaslamp-era clothes', and the grade said 'the subject'."""
    from echotales.pipeline.persona.genre import style_lead
    from echotales.pipeline.render.compiler import (
        OutputMode,
        PanelBrief,
        compile_prompt,
        model_profile,
    )
    from echotales.pipeline.render.lightgrade import light_grade

    f = fr.Framing("close", focus="prop", subject="lamp")
    b = PanelBrief(
        characters=[], novel_id="lord-of-the-mysteries", mode=OutputMode.COLOUR, shot="close", frame_focus="prop", framing=fr.framing_sentence(f, "Klein", people=False),
        grade=light_grade("Light: faint crimson, a lamp at night."), staging="Set: a study lit by a wall lamp. Light: faint crimson.")
    out = compile_prompt(b, model_profile("z-image-turbo")).positive.lower()
    assert out.startswith(style_lead("lord-of-the-mysteries", people=False).lower())
    import re

    assert not re.search(PERSON_WORDS, out), re.findall(PERSON_WORDS, out)


def test_the_object_lead_keeps_the_look_and_the_place_flavour(monkeypatch) -> None:
    from echotales.pipeline.persona import genre
    from echotales.pipeline.persona.genre import style_lead

    monkeypatch.setattr(genre, "genre_of", lambda _n: "victorian_gothic")

    lead = style_lead("lord-of-the-mysteries", people=False)
    assert "webtoon" in lead and "Victorian gothic city" in lead and "clothes" not in lead and "faces" not in lead


def test_a_lone_lead_second_view_is_a_high_corner_view_not_a_view_from_behind() -> None:
    """A/B on LotM p4, 3 seeds each: 'seen from behind X at a desk' drew a second man across the desk 3 of 3, a high corner view 0 of 3."""
    f = fr.Framing("medium", focus="behind")
    alone = fr.framing_sentence(f, "Klein", alone=True)
    assert "alone" in alone and "high corner" in alone and "from directly behind" not in alone
    assert "from directly behind" in fr.framing_sentence(f, "Klein", alone=False)


def test_a_staged_day_light_is_dropped_when_the_scene_text_says_night() -> None:
    """RI rebirth r5: the scene says 'sparkling in the night' and rain, the staging said 'Light: day, rain', and the windows were drawn
    daylit. The text's night outranks the director's guess."""
    from echotales.pipeline.render.staging import SceneStaging, validate_staging

    s = SceneStaging(set="a corridor with a window", blocking="He stands facing left", light="day, rain")
    out, rejects = validate_staging(s, scene_text="Spring rain blew through the window; lights sparkled in the night.", cast=[])
    assert out.light == "" and any("night" in r for r in rejects)
    kept, none = validate_staging(s, scene_text="Spring rain blew through the window by day.", cast=[])
    assert kept.light == "day, rain" and not none
