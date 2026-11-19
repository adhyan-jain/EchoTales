"""direct_beat asks once more, naming the fault, instead of letting a rejected or happy-on-hostile paragraph through."""

from __future__ import annotations

from types import SimpleNamespace

from echotales.pipeline.render.direction import PanelDirection, direct_beat

BEAT = "Fang Yuan laughed coldly at the enemies who had cornered him, scornful and contemptuous."


class Seq:
    def __init__(self, *dirs: PanelDirection) -> None:
        self.dirs, self.prompts = list(dirs), []

    def complete(self, task, prompt, schema, **kw):
        self.prompts.append(prompt)
        return SimpleNamespace(value=self.dirs[min(len(self.prompts) - 1, len(self.dirs) - 1)].model_copy())


def run(client, **kw):
    return direct_beat(BEAT, cast={"Fang Yuan": ""}, novel_style="s", client=client, novel_id="", staging="Set: cliff.", **kw)


def test_a_paragraph_blanked_for_a_lone_figure_in_a_crowd_scene_is_retried_with_the_reason() -> None:
    bad = PanelDirection(composition="A lone figure Fang Yuan stands alone on the cliff, a cold mocking smile.")
    good = PanelDirection(composition="Fang Yuan stands on the left, a cold mocking smile; the fighters wait in rows on the right.")
    client = Seq(bad, good)
    out = run(client, crowd_mood="hostile")
    assert out is not None and out.direction.composition.startswith("Fang Yuan stands on the left")
    assert len(client.prompts) == 2 and "rejected" in client.prompts[1] and "crowd erased" in client.prompts[1]


def test_a_happy_face_on_a_hostile_line_is_retried_and_a_persistent_one_is_flagged() -> None:
    happy = PanelDirection(composition="Fang Yuan laughs happily, a bright cheerful smile.", expression="cheerful")
    cold = PanelDirection(composition="Fang Yuan gives a cold mocking smile, eyes narrowed.", expression="contemptuous")
    out = run(Seq(happy, cold))
    assert "cold mocking" in out.direction.composition
    stuck = run(Seq(happy, happy))
    assert any("positive expression" in r for r in stuck.direction.grounding_rejects)
