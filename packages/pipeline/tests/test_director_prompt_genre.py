"""The director's system prompt follows the novel's genre and asks for every Director v2 field."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from echotales.pipeline.persona import genre
from echotales.pipeline.render.direction import (
    CharacterDirection,
    PanelDirection,
    _validate_direction,
    build_prompt,
    direct_beat,
    system_prompt,
)


class _Capture:
    """Stands in for ModelClient: records the system and user prompt, replies with a fixed PanelDirection."""

    def __init__(self, reply: PanelDirection | None = None) -> None:
        self.reply = reply or PanelDirection()
        self.system = ""
        self.prompt = ""

    def complete(self, task, prompt, model, *, system="", novel_id=""):  # noqa: ANN001
        self.system, self.prompt = system, prompt
        return SimpleNamespace(value=self.reply)


@pytest.fixture
def projects():
    genre._PROJECT_GENRE["pp-test"] = "contemporary"
    genre._PROJECT_GENRE["xx-test"] = "xianxia"
    yield
    genre._PROJECT_GENRE.pop("pp-test", None)
    genre._PROJECT_GENRE.pop("xx-test", None)


def test_a_non_xianxia_novel_gets_no_xianxia_guidance(projects) -> None:
    client = _Capture()
    direct_beat("Elizabeth crossed the drawing room.", cast={"Elizabeth Bennet": "dark hair"},
                novel_style="Regency England", client=client, novel_id="pp-test")
    text = (client.system + client.prompt).lower()
    for banned in ("xianxia", "hanfu", "ancient china", "danbooru", "noobai", "illustrious"):
        assert banned not in text


def test_a_xianxia_novel_keeps_its_guidance(projects) -> None:
    client = _Capture()
    direct_beat("Fang Yuan stood.", cast={"Fang Yuan": "black hair"}, novel_style="x", client=client, novel_id="xx-test")
    assert "xianxia" in client.system.lower() and "hanfu" in client.system.lower()


def test_the_prompt_asks_for_every_v2_field() -> None:
    prompt = build_prompt("Elizabeth smiled.", cast={"Elizabeth Bennet": "x"}, novel_style="x")
    for key in ("characters", "others", "camera_angle", "location_detail", "props"):
        assert f"  {key}" in prompt
    for sub in ("position", "pose", "expression", "condition", "relation_to_lead"):
        assert sub in prompt
    assert "Return only JSON" in prompt


def test_v2_fields_in_a_json_reply_parse_into_the_direction() -> None:
    raw = (
        '{"shot": "wide", "camera_angle": "low-angle", "location_detail": "drawing room with a piano",'
        ' "props": ["letter"], "characters": [{"name": "Elizabeth Bennet", "position": "left", "pose": "sitting",'
        ' "expression": "calm", "condition": ""}], "others": {"kind": "guests", "count": 4, "relation_to_lead": "watching"}}'
    )
    d = PanelDirection.model_validate_json(raw)
    assert d.camera_angle == "low-angle" and d.props == ["letter"] and d.location_detail.startswith("drawing")
    assert d.characters[0].name == "Elizabeth Bennet" and d.characters[0].pose == "sitting"
    assert d.others is not None and d.others.count == 4


def test_the_tag_instruction_is_gone_but_the_genre_neutral_rules_stay(projects) -> None:
    text = system_prompt("pp-test").lower()
    assert "cast" in text and "one place per shot" in text and "independent of physical condition" in text
    assert "plain" in text


def test_a_director_character_outside_the_cast_is_dropped() -> None:
    d = PanelDirection(characters=[CharacterDirection(name="Elizabeth Bennet"), CharacterDirection(name="Lady Zed")])
    out = _validate_direction(d, beat_text="Elizabeth sat.", cast={"Elizabeth Bennet": "x"})
    assert [c.name for c in out.characters] == ["Elizabeth Bennet"]


def test_the_legacy_tag_prompt_turns_the_directors_plain_phrases_into_tags() -> None:
    # The NoobAI path was tuned on underscore tags; the director now writes plain phrases, so the conversion lives
    # where the tag prompt is assembled and a cast name keeps its spacing.
    from echotales.pipeline.render.direction import Direction

    d = PanelDirection(action="hands clasped, standing alone", layout="Fang Yuan, alone", setting="stone courtyard",
                       lighting="soft dusk", mood="tense", expression="calm")
    parts = Direction(direction=d, cast={"Fang Yuan": "black hair"}, novel_style="x", novel_id="reverend-insanity").to_image_prompt_parts()
    joined = ", ".join(parts)
    assert "hands_clasped" in joined and "standing_alone" in joined and "stone_courtyard" in joined and "soft_dusk" in joined
    assert "Fang Yuan" in joined and "Fang_Yuan" not in joined
