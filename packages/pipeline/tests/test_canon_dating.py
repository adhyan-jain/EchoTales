"""B4 (CHIMERA defect backlog): wiki canon is dated to the character's first appearance when asked to be.

`wiki_canon.py` promises that imported traits are dated to the first appearance, but the import carries no date, so a
position before the character exists still received the wiki's whole-novel description. `apply_canon` now drops the
wiki tier when both `position` and `first_appearance` are given and the position precedes it; hand-authored canon is
unaffected and omitting either argument keeps the shipped behaviour. Body-blindness of the wiki stays open (no
per-body wiki traits exist). Synthetic strings only; the wiki loader is stubbed.
"""

from __future__ import annotations

import pytest

from echotales.pipeline.persona import canon as canon_mod
from echotales.pipeline.persona import wiki_canon as wiki_mod

NOVEL = "n"
LABEL = "Zorrin Vale"


@pytest.fixture(autouse=True)
def _stub_canon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wiki_mod, "load_wiki_canon", lambda novel_id: {LABEL: {"hair": "silver wiki hair"}})
    monkeypatch.setattr(canon_mod, "CANON_APPEARANCE", {NOVEL: {LABEL: {"eyes": "hand-authored amber"}}})
    monkeypatch.setattr(canon_mod, "CANON_BY_BODY", {})


def test_default_keeps_the_undated_wiki_tier() -> None:
    out = canon_mod.apply_canon(NOVEL, LABEL, {})
    assert out == {"hair": "silver wiki hair", "eyes": "hand-authored amber"}


def test_before_first_appearance_the_wiki_tier_is_dropped_but_hand_authored_canon_stays() -> None:
    out = canon_mod.apply_canon(NOVEL, LABEL, {}, position=3.0, first_appearance=10.0)
    assert out == {"eyes": "hand-authored amber"}


def test_from_first_appearance_on_the_wiki_tier_applies() -> None:
    assert canon_mod.apply_canon(NOVEL, LABEL, {}, position=10.0, first_appearance=10.0)["hair"] == "silver wiki hair"
    assert canon_mod.apply_canon(NOVEL, LABEL, {}, position=50.0, first_appearance=10.0)["hair"] == "silver wiki hair"


def test_giving_only_one_of_the_two_arguments_keeps_the_shipped_behaviour() -> None:
    assert "hair" in canon_mod.apply_canon(NOVEL, LABEL, {}, position=3.0)
    assert "hair" in canon_mod.apply_canon(NOVEL, LABEL, {}, first_appearance=10.0)
