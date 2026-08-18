"""Faction qualification of role words (`render/factions.py`)."""

from __future__ import annotations

from echotales.pipeline.render.factions import qualify_role, scene_faction


def test_organisation_wins_over_the_settlement_of_the_same_name() -> None:
    # RI ch1 names both, two blocks apart. "Gu Yue clan elders" is what a
    # reader would say.
    text = (
        "In the middle of the Gu Yue Village was a magnificent pavilion. "
        "The Gu Yue clan head bent his waist."
    )
    assert scene_faction(text) == "Gu Yue clan"


def test_lowercase_kind_words_still_match() -> None:
    assert scene_faction("He arrived at the Bai clan hall.") .startswith("Bai")


def test_leading_article_is_dropped() -> None:
    assert not scene_faction("The Gu Yue clan gathered.").startswith("The ")


def test_no_faction_named_leaves_roles_alone() -> None:
    assert scene_faction("Rain fell on the mountain.") == ""
    assert qualify_role("elders", "") == "elders"


def test_only_roles_defined_by_belonging_are_qualified() -> None:
    assert qualify_role("elders", "Gu Yue clan") == "Gu Yue clan elders"
    assert qualify_role("disciples", "Bai clan") == "Bai clan disciples"
    # A warrior is not defined by whose he is; a clan name adds nothing.
    assert qualify_role("warriors", "Gu Yue clan") == "warriors"


def test_a_role_that_already_names_its_faction_is_left_alone() -> None:
    assert qualify_role("Gu Yue clan elders", "Gu Yue clan") == "Gu Yue clan elders"


def test_different_scenes_get_different_factions() -> None:
    # The whole point: the same word, two clans, one volume.
    gu_yue = scene_faction("The Gu Yue clan elders knelt in the hall.")
    bai = scene_faction("The Bai clan elders received him coldly.")
    assert qualify_role("elders", gu_yue) != qualify_role("elders", bai)


def test_two_clans_of_the_same_name_are_distinguished_by_region() -> None:
    """After Qing Mao mountain's clans are destroyed, RI introduces a
    different Bai clan elsewhere. Nothing in the words separates them; a
    reader disambiguates by where they are standing."""
    from echotales.pipeline.render.factions import faction_key, scene_region

    home = "The Bai clan of Qing Mao Mountain gathered in the hall."
    away = "Far away, the Bai clan of Western Border Region welcomed them."

    assert scene_faction(home) == scene_faction(away) == "Bai clan"
    assert faction_key(scene_faction(home), scene_region(home)) != faction_key(
        scene_faction(away), scene_region(away)
    )


def test_a_faction_with_no_region_keys_on_its_name_alone() -> None:
    from echotales.pipeline.render.factions import faction_key

    assert faction_key("Gu Yue clan", "") == "Gu Yue clan"
    assert faction_key("", "Qing Mao mountain") == ""
