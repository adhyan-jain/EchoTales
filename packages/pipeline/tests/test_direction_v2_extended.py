"""Extended unit tests for Director v2 schema, shot variety rules, and conservation auditing."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline import flow
from echotales.pipeline.render.direction import (
    CharacterDirection,
    DirectionConservationAudit,
    OthersDirection,
    PanelDirection,
    check_direction_conservation,
    enforce_shot_variety,
)


def test_shot_variety_empty_or_single_direction() -> None:
    assert enforce_shot_variety([]) == []

    single = [PanelDirection(shot="medium", characters=[CharacterDirection(name="Fang Yuan")])]
    varied = enforce_shot_variety(single)
    assert len(varied) == 1
    assert varied[0].shot == "medium"
    assert varied[0].characters[0].name == "Fang Yuan"


def test_shot_variety_preserves_different_subjects() -> None:
    # Consecutive medium shots on DIFFERENT characters should not be forced to change shot size
    directions = [
        PanelDirection(shot="medium", characters=[CharacterDirection(name="Fang Yuan")]),
        PanelDirection(shot="medium", characters=[CharacterDirection(name="Gu Yue Bo")]),
    ]
    varied = enforce_shot_variety(directions)
    assert varied[0].shot == "medium"
    assert varied[1].shot == "medium"
    assert varied[0].characters[0].name == "Fang Yuan"
    assert varied[1].characters[0].name == "Gu Yue Bo"


def test_shot_variety_cycles_camera_angles_on_same_subject() -> None:
    # Consecutive panels with duplicate angles should cycle to avoid consecutive identical angles
    directions = [
        PanelDirection(shot="wide", camera_angle="eye-level", characters=[CharacterDirection(name="Fang Yuan")]),
        PanelDirection(shot="medium", camera_angle="eye-level", characters=[CharacterDirection(name="Fang Yuan")]),
        PanelDirection(shot="close", camera_angle="low-angle", characters=[CharacterDirection(name="Fang Yuan")]),
    ]
    varied = enforce_shot_variety(directions)
    # The shots were already varied (wide -> medium -> close)
    # Panel 1 collides with panel 0's eye-level -> cycles to low-angle
    # Panel 2 collides with panel 1's low-angle -> cycles to high-angle
    assert varied[0].camera_angle == "eye-level"
    assert varied[1].camera_angle == "low-angle"
    assert varied[2].camera_angle == "high-angle"


def test_shot_variety_switches_medium_to_close_when_expression_or_props_present() -> None:
    directions = [
        PanelDirection(shot="medium", characters=[CharacterDirection(name="Fang Yuan")]),
        PanelDirection(
            shot="medium",
            characters=[CharacterDirection(name="Fang Yuan")],
            expression="sneering",
            props=["ancient dagger"],
        ),
    ]
    varied = enforce_shot_variety(directions)
    assert varied[0].shot == "medium"
    assert varied[1].shot == "close"


def test_direction_conservation_dropped_places_and_props() -> None:
    beat = "Fang Yuan stood in the courtyard holding a sharp blade. Across the stone bridge sat a heavy carriage."
    # Direction only captures the courtyard and the blade, omitting the bridge and carriage
    direction = PanelDirection(
        shot="medium",
        characters=[CharacterDirection(name="Fang Yuan")],
        setting="stone_courtyard",
        props=["blade"],
    )
    cast_names = {"Fang Yuan"}

    audit = check_direction_conservation(beat, direction, cast_names)
    assert "courtyard" in audit.captured_places
    assert "blade" in audit.captured_props
    assert "Fang Yuan" in audit.captured_people
    assert "bridge" in audit.dropped_places
    assert "carriage" in audit.dropped_props


def test_flow_director_conservation_reports_dropped_items_as_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from echotales.core.enums import BlockType
    from echotales.pipeline import paths

    store = Store(str(tmp_path / "test_flow.db"))
    store.add_novel("test", "Test Novel", "test.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="test",
            number=1.0,
            title="Ch1",
            source_href="1.html",
            blocks=[
                Block(
                    index=0,
                    block_type=BlockType.PROSE,
                    text="Fang Yuan carried a lantern into the cave. A golden sword lay by the altar.",
                )
            ],
        )
    )
    store.conn.commit()

    panel_dir = tmp_path / "panels"
    panel_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "asset_dir", lambda novel_id, kind: panel_dir if kind == "panels" else tmp_path / kind)

    # Write panel_plan omitting the altar and lantern
    plan_file = panel_dir / "panel_plan.jsonl"
    plan_file.write_text(
        json.dumps(
            {
                "novel_id": "test",
                "chapter": 1.0,
                "panel_seq": 1,
                "block_indexes": [0],
                "cast": [{"self_id": "s1", "label": "Fang Yuan"}],
                "direction": {
                    "shot": "medium",
                    "characters": [{"name": "Fang Yuan", "position": "center"}],
                    "setting": "cave",
                    "props": ["sword"],
                },
            }
        ) + "\n",
        encoding="utf-8",
    )

    chk = flow._find(flow.Stage.DIRECTOR, "director.conservation")
    res = chk.fn(store, "test", None)
    assert res.status is flow.Status.PASS
    assert res.count_out < res.count_in
    assert len(res.warnings) > 0
    # Lantern or altar should be reported in warnings
    assert any("dropped" in w for w in res.warnings)
