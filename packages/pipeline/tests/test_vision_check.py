"""Vision check: a local VLM answers person count, hair colour, outfit colour and presence; the best passing candidate is kept."""

from __future__ import annotations

import json
from pathlib import Path

from echotales.pipeline.keyframes import qa
from echotales.pipeline.persona.identity_lock import LockedIdentity
from echotales.pipeline.render.compiler import CharacterBrief, CrowdBrief, OutputMode, PanelBrief


def test_colour_families_read_the_first_colour_run_and_fold_dark_shades() -> None:
    f = qa.colour_family
    assert f("dark navy") == "dark" and f("black") == "dark" and f("charcoal grey") == "grey"
    assert f("deep green robes") == "green" and f("dark brown") == "brown" and f("teal") == "teal"
    assert f("a long robe") == "" and f("") == ""
    assert f("blonde") == f("golden blond") == "blond"
    # the lead garment is named first: a white shirt under a green coat is a green outfit
    assert f("a dark green frock coat and waistcoat over a white shirt") == "green"
    assert f("a white robe with a black sash") == "white"


EXPECT = qa.PanelExpectation(people=1, hair_colour="black", outfit_colour="deep green", lead="Fang Yuan")


def ans(**kw) -> qa.VisionAnswer:
    base = dict(people=1, lead_visible=True, hair_colour="black", outfit_colour="green")
    base.update(kw)
    return qa.VisionAnswer(**base)


def test_a_matching_answer_passes_and_each_mismatch_is_named() -> None:
    assert qa.judge(ans(), EXPECT).passed
    assert qa.judge(ans(people=2), EXPECT).failed == ["people"]
    assert qa.judge(ans(hair_colour="brown"), EXPECT).failed == ["hair"]
    assert qa.judge(ans(outfit_colour="white"), EXPECT).failed == ["outfit"]
    assert qa.judge(ans(lead_visible=False), EXPECT).failed == ["presence"]


def test_a_dark_outfit_read_as_blue_passes_but_green_for_teal_does_not() -> None:
    dark = qa.PanelExpectation(outfit_colour="dark navy")
    assert qa.judge(ans(outfit_colour="blue"), dark).passed
    green = qa.PanelExpectation(outfit_colour="deep green")
    assert qa.judge(ans(outfit_colour="teal"), green).failed == ["outfit"]


def test_a_crowd_panel_needs_at_least_the_named_people_and_colours_may_be_skipped() -> None:
    crowd = qa.PanelExpectation(people=1, people_at_least=True, hair_colour="", outfit_colour="", lead="Fang Yuan")
    assert qa.judge(ans(people=14, hair_colour="grey", outfit_colour="red"), crowd).passed
    assert qa.judge(ans(people=0), crowd).failed == ["people", "presence"] or "people" in qa.judge(ans(people=0), crowd).failed


def test_a_scenery_panel_expects_nobody() -> None:
    scenery = qa.PanelExpectation(people=0)
    assert qa.judge(qa.VisionAnswer(people=0, lead_visible=False), scenery).passed
    assert qa.judge(qa.VisionAnswer(people=1, lead_visible=True), scenery).failed == ["people"]


class FakeVLM:
    def __init__(self, answers: list[qa.VisionAnswer]) -> None:
        self.answers, self.seen = list(answers), []

    def look(self, path):  # noqa: ANN001
        self.seen.append(path)
        return self.answers.pop(0)


def test_the_first_passing_candidate_is_kept_and_the_rescue_is_counted(tmp_path) -> None:
    paths = [tmp_path / f"c{i}.png" for i in range(3)]
    vlm = FakeVLM([ans(hair_colour="brown"), ans(), ans()])
    sel = qa.select_candidate(paths, EXPECT, vlm)
    assert sel.chosen == 1 and sel.passed and sel.first_passed is False
    assert len(vlm.seen) == 2, "stops at the first passing candidate"


def test_when_none_pass_the_one_with_fewest_failures_is_kept(tmp_path) -> None:
    paths = [tmp_path / f"c{i}.png" for i in range(2)]
    sel = qa.select_candidate(paths, EXPECT, FakeVLM([ans(people=3, hair_colour="red"), ans(people=2)]))
    assert sel.chosen == 1 and not sel.passed


def test_a_vlm_that_cannot_answer_does_not_veto_the_candidate(tmp_path) -> None:
    class Broken:
        def look(self, path):  # noqa: ANN001
            return None

    sel = qa.select_candidate([tmp_path / "a.png", tmp_path / "b.png"], EXPECT, Broken())
    assert sel.chosen == 0 and sel.unchecked


def test_installed_model_choice_prefers_the_ranked_list_and_says_so_when_none(monkeypatch) -> None:
    assert qa.pick_vision_model(["gemma2:9b", "granite3.2-vision:2b"], "") == "granite3.2-vision:2b"
    assert qa.pick_vision_model(["gemma2:9b"], "") is None
    assert qa.pick_vision_model(["gemma2:9b", "llava:7b"], "llava:7b") == "llava:7b"
    assert qa.pick_vision_model(["gemma2:9b"], "llava:7b") is None
    assert "ollama pull" in qa.NO_VLM_MESSAGE


def _brief(mode=OutputMode.COLOUR, crowd=None, chars=1) -> PanelBrief:
    lock = LockedIdentity("p", hair="long black hair tied up in a topknot", eyes="dark brown eyes", build="a lean build",
                          outfit="deep green robes")
    cs = [CharacterBrief(name=f"N{i}", gender="male", locked=lock, lead=i == 0) for i in range(chars)]
    return PanelBrief(novel_id="", characters=cs, crowd=crowd, mode=mode)


def test_expectation_comes_from_the_locked_identity() -> None:
    e = qa.expectation_from_brief(_brief())
    assert (e.people, e.people_at_least, e.hair_colour, e.outfit_colour, e.lead) == (1, False, "dark", "green", "N0")
    assert qa.expectation_from_brief(_brief(chars=2)).people == 2
    crowd = qa.expectation_from_brief(_brief(crowd=CrowdBrief(description="fighters")))
    assert crowd.people_at_least and crowd.people == 1
    manga = qa.expectation_from_brief(_brief(mode=OutputMode.MANGA))
    assert manga.hair_colour == "" and manga.outfit_colour == "", "no colours to check in black and white"
    assert qa.expectation_from_brief(PanelBrief(novel_id="", characters=[])).people == 0


def test_the_report_counts_checked_passed_rescued_and_extra_images(tmp_path) -> None:
    rows = [
        {"panel": "a", "candidates": 2, "chosen": 0, "passed": True, "first_passed": True, "unchecked": False, "failed": []},
        {"panel": "b", "candidates": 2, "chosen": 1, "passed": True, "first_passed": False, "unchecked": False, "failed": ["hair"]},
        {"panel": "c", "candidates": 2, "chosen": 0, "passed": False, "first_passed": False, "unchecked": False, "failed": ["people"]},
        {"panel": "d", "candidates": 2, "chosen": 0, "passed": False, "first_passed": False, "unchecked": True, "failed": []},
    ]
    r = qa.summarise(rows)
    assert r["panels_checked"] == 3 and r["unchecked"] == 1
    assert r["first_pass_rate"] == round(1 / 3, 3) and r["final_pass_rate"] == round(2 / 3, 3)
    assert r["rescued"] == 1 and r["extra_images"] == 4
    p = tmp_path / "vision_check.jsonl"
    qa.write_rows(p, rows)
    assert [json.loads(x)["panel"] for x in p.read_text().splitlines()] == list("abcd")
    assert isinstance(p, Path)
