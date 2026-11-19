"""Per-scene staging sheet, expression check, style-only leads (owner feedback 2026-11-19)."""

from __future__ import annotations

import re

from echotales.pipeline.persona.genre import GENRES, STYLE_LEADS, style_lead
from echotales.pipeline.render.compiler import CharacterBrief, OutputMode, PanelBrief, compile_prompt, model_profile
from echotales.pipeline.render.direction import build_prompt, system_prompt
from echotales.pipeline.render.plan import PanelPlan
from echotales.pipeline.render.staging import (
    SceneStaging,
    expression_conflicts,
    validate_staging,
)

SCENE = "Fang Yuan stood at the cliff edge. The righteous fighters climbed up the mountain path and shouted at him."
OLD = dict(name="Fang Yuan", gender="male", age_band="adult", appearance={"hair_color": "black"}, lead=True)
ARCH = re.compile(r"pavilion|paifang|eaves|archway|courtyard|tiled roof|lantern", re.I)


def test_plan_accepts_a_carried_location_source() -> None:
    assert "carried" in PanelPlan.model_fields["location_source"].annotation.__args__


def test_style_leads_carry_style_only_and_no_architecture() -> None:
    for lead in STYLE_LEADS.values():
        assert not ARCH.search(lead)
    for g in GENRES.values():
        assert not ARCH.search(g.world_setting)
    assert not ARCH.search(system_prompt(""))
    for lead in STYLE_LEADS.values():
        assert "cel" in lead.lower()  # one fixed cel-shaded anime level for every novel


def test_staging_text_is_one_verbatim_paragraph_of_set_blocking_and_light() -> None:
    s = SceneStaging(set="a bare rock cliff edge with twisted pines", blocking="Fang Yuan stands alone at the left edge; the fighters stand in rows on the right, facing him",
                     light="cold dusk")
    t = s.text()
    assert t.startswith("Set: a bare rock cliff edge") and "Blocking:" in t and "Light: cold dusk" in t


def test_validate_staging_rejects_a_ring_the_text_never_states_and_names_outside_the_cast() -> None:
    bad = SceneStaging(set="a cliff", blocking="Fang Yuan stands in the centre surrounded in a circle by fighters, and Gu Yue Fang Zheng watches",
                       light="dusk")
    ok, rejects = validate_staging(bad, scene_text=SCENE, cast=["Fang Yuan"])
    assert "ring" in " ".join(rejects) and "Gu Yue Fang Zheng" in " ".join(rejects)
    assert not re.search(r"circle|surround|ring", ok.blocking, re.I) and "facing" in ok.blocking
    assert "Gu Yue Fang Zheng" not in ok.blocking
    # the text itself says they surround him: leave it alone
    ring = SceneStaging(set="a cliff", blocking="fighters surround Fang Yuan", light="dusk")
    kept, rj = validate_staging(ring, scene_text="The fighters stood in a circle around Fang Yuan.", cast=["Fang Yuan"])
    assert kept.blocking == ring.blocking and not rj
    # "surrounded" is prose for outnumbered: on a cliff edge it is still staged as one side of the frame
    prose, rj2 = validate_staging(ring, scene_text="Enemies surrounded him all around.", cast=["Fang Yuan"])
    assert rj2 and "surround" not in prose.blocking


def test_the_director_prompt_carries_the_staging_verbatim_and_asks_only_for_camera_action_expression() -> None:
    s = SceneStaging(set="bare rock cliff", blocking="rows facing him", light="dusk")
    p = build_prompt("He laughed.", cast={"Fang Yuan": "x"}, novel_style="s", staging=s.text())
    assert s.text() in p and "do not change" in p.lower()


def test_compiled_prompt_puts_the_staging_between_the_style_lead_and_the_panel_paragraph() -> None:
    s = SceneStaging(set="bare rock cliff", blocking="Fang Yuan alone at left, fighters in rows at right facing him", light="cold dusk")
    b = PanelBrief(novel_id="", characters=[CharacterBrief(**OLD)], mode=OutputMode.COLOUR,
                   composition="Close-up of Fang Yuan, a cold mocking smile.", staging=s.text())
    out = compile_prompt(b, model_profile("z-image-turbo"))
    labels = [x.label for x in out.sections]
    assert labels[:3] == ["style", "staging", "composition"]
    assert s.text() in out.positive
    # the staging already says the light and set: they are not repeated in the setting clause
    assert "Setting:" not in out.positive


def test_a_cheerful_face_on_a_contemptuous_line_is_flagged() -> None:
    ctx = "Fang Yuan laughed coldly at the righteous fighters who had cornered him, scornful and contemptuous."
    assert expression_conflicts("laughing happily, a bright cheerful smile", ctx)
    assert not expression_conflicts("cold mocking smile, narrowed eyes, contemptuous", ctx)
    assert not expression_conflicts("a warm cheerful smile", "She smiled warmly and greeted her sister.")


def test_a_close_shot_puts_its_own_paragraph_before_the_staging() -> None:
    # Measured 2026-11-19: with the staging first, a close-up drew a second, tiny Fang Yuan standing at the cliff edge behind
    # the foreground one (2 of 2 seeds); paragraph first drew one (2 of 2).
    s = SceneStaging(set="bare rock cliff", blocking="Fang Yuan alone at left, fighters in rows at right", light="dusk")
    b = PanelBrief(novel_id="", characters=[CharacterBrief(**OLD)], mode=OutputMode.COLOUR, shot="close",
                   composition="Close-up of Fang Yuan, a cold mocking smile.", staging=s.text())
    labels = [x.label for x in compile_prompt(b, model_profile("z-image-turbo")).sections]
    assert labels[:3] == ["style", "composition", "staging"]


def test_staging_is_asked_to_keep_the_previous_scenes_set_unless_the_text_moves_the_characters() -> None:
    # RI ch1: the laugh scene says "the setting sun" and nothing else about place; a fresh staging call invented a grassy hillside
    # next to the cliff scene. The previous sheet goes in the prompt so the model carries it instead of inventing.
    from types import SimpleNamespace

    from echotales.pipeline.render.staging import STAGING_SYSTEM, direct_staging

    seen: dict = {}

    class Client:
        def complete(self, task, prompt, schema, **kw):
            seen["prompt"] = prompt
            return SimpleNamespace(value=SceneStaging(set="a bare rock cliff", blocking="Fang Yuan alone on the left", light="dusk"))

    prev = "Set: a bare rock cliff edge above cloud. Blocking: Fang Yuan alone at the left edge. Light: dusk."
    direct_staging("Looking at the setting sun, Fang Yuan lightly laughed.", cast={"Fang Yuan": ""}, novel_style="x",
                   client=Client(), previous=prev)
    assert prev in seen["prompt"]
    assert "previous" in STAGING_SYSTEM.lower() and "unless" in STAGING_SYSTEM.lower()
    seen.clear()
    direct_staging("He sat down.", cast={"Fang Yuan": ""}, novel_style="x", client=Client())
    assert "PREVIOUS" not in seen["prompt"]
