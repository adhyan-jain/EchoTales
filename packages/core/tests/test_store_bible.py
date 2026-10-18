"""Unit tests for Store.bible_at bitemporal snapshots and Studio review items."""

from __future__ import annotations

import pytest

from echotales.core.enums import AliasType, AssertedBy, Prominence, TargetKind, TruthStatus
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    DiscoursePosition,
    Persona,
    ReviewItem,
    Self,
    SelfPersonaBinding,
)
from echotales.core.store import Store


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def test_store_bible_at_no_future_leakage(store: Store) -> None:
    # Novel and two characters introduced at different chapters
    store.add_self(
        Self(
            id="char:sherlock",
            novel_id="hound",
            canonical_label="Sherlock Holmes",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
            prominence=Prominence.PRINCIPAL,
        )
    )
    store.add_self(
        Self(
            id="char:mortimer",
            novel_id="hound",
            canonical_label="Dr. James Mortimer",
            first_attested_pos=DiscoursePosition(chapter=2, offset=10),
            prominence=Prominence.RECURRING,
        )
    )

    # Chapter 1 snapshot: only Sherlock should exist
    snap1 = store.bible_at("hound", 1.0)
    assert "char:sherlock" in snap1.characters
    assert "char:mortimer" not in snap1.characters
    assert snap1.resolve_alias("Sherlock Holmes") == "char:sherlock"
    assert snap1.resolve_alias("Dr. James Mortimer") is None

    # Chapter 2 snapshot: both characters should exist
    snap2 = store.bible_at("hound", 2.0)
    assert "char:sherlock" in snap2.characters
    assert "char:mortimer" in snap2.characters
    assert snap2.resolve_alias("Dr. James Mortimer") == "char:mortimer"


def test_store_bible_at_persona_shift(store: Store) -> None:
    store.add_self(
        Self(
            id="char:jekyll",
            novel_id="jekyll_hyde",
            canonical_label="Dr. Henry Jekyll",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
            prominence=Prominence.PRINCIPAL,
        )
    )
    store.add_persona(
        Persona(
            id="body:jekyll_normal",
            novel_id="jekyll_hyde",
            body_label="Tall handsome Victorian gentleman",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
        )
    )
    store.add_persona(
        Persona(
            id="body:hyde_grotesque",
            novel_id="jekyll_hyde",
            body_label="Short dwarfish grotesque figure",
            first_attested_pos=DiscoursePosition(chapter=2, offset=5),
        )
    )

    # Body 1 binding at chapter 1
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="char:jekyll",
            persona_id="body:jekyll_normal",
            timeline_id="MAIN",
            interval=FuzzyInterval.point_known(1.0, 1.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id="reader",
            truth_status=TruthStatus.TRUE,
        )
    )

    snap1 = store.bible_at("jekyll_hyde", 1.0)
    assert snap1.characters["char:jekyll"].active_persona_id == "body:jekyll_normal"

    # Body 2 shift at chapter 2
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="char:jekyll",
            persona_id="body:hyde_grotesque",
            timeline_id="MAIN",
            interval=FuzzyInterval.point_known(2.0, 2.0),
            learned_at_pos=DiscoursePosition(chapter=2, offset=5),
            observer_id="reader",
            truth_status=TruthStatus.TRUE,
        )
    )

    snap2 = store.bible_at("jekyll_hyde", 2.0)
    assert snap2.characters["char:jekyll"].active_persona_id == "body:hyde_grotesque"


def test_store_bible_at_retracted_facts(store: Store) -> None:
    store.add_self(
        Self(
            id="char:klein",
            novel_id="lotm",
            canonical_label="Klein Moretti",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
            prominence=Prominence.PRINCIPAL,
        )
    )

    # Alias learned at ch1
    alias_id = store.add_alias_binding(
        "lotm",
        AliasBinding(
            alias="Ordinary History Graduate",
            alias_type=AliasType.EPITHET,
            target_kind=TargetKind.SELF,
            target_id="char:klein",
            timeline_id="MAIN",
            interval=FuzzyInterval.point_known(1.0, 1.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id="reader",
            asserted_by=AssertedBy.NARRATOR,
            truth_status=TruthStatus.TRUE,
        ),
    )

    # Attribute learned at ch1
    attr_id = store.add_attribute(
        "lotm",
        Attribute(
            target_kind=TargetKind.SELF,
            target_id="char:klein",
            key="profession",
            value="Civil Servant Candidate",
            timeline_id="MAIN",
            interval=FuzzyInterval.point_known(1.0, 1.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id="reader",
            asserted_by=AssertedBy.NARRATOR,
            truth_status=TruthStatus.TRUE,
        ),
    )

    # In ch1: alias and attribute exist
    snap1 = store.bible_at("lotm", 1.0)
    assert "Ordinary History Graduate" in snap1.characters["char:klein"].aliases
    assert snap1.characters["char:klein"].attributes["profession"] == "Civil Servant Candidate"

    # Retract both at ch3 (e.g. Klein becomes Beyonder / Nighthawk)
    store.retract_alias(alias_id, at=DiscoursePosition(chapter=3, offset=0))
    store.retract_attribute(attr_id, at=DiscoursePosition(chapter=3, offset=0))

    # At ch2: still visible (retraction happened at ch3)
    snap2 = store.bible_at("lotm", 2.0)
    assert "Ordinary History Graduate" in snap2.characters["char:klein"].aliases
    assert snap2.characters["char:klein"].attributes["profession"] == "Civil Servant Candidate"

    # At ch3: excluded
    snap3 = store.bible_at("lotm", 3.0)
    assert "Ordinary History Graduate" not in snap3.characters["char:klein"].aliases
    assert "profession" not in snap3.characters["char:klein"].attributes


def test_store_bible_at_locations(store: Store) -> None:
    store.add_self(
        Self(
            id="loc:baker_st",
            novel_id="hound",
            canonical_label="221B Baker Street",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
            prominence=Prominence.INCIDENTAL,
            notes="Victorian sitting room, fireplace, gas lamps, violin",
            kind=TargetKind.LOCATION,
        )
    )
    store.add_attribute(
        "hound",
        Attribute(
            target_kind=TargetKind.LOCATION,
            target_id="loc:baker_st",
            key="master_plate_path",
            value="assets/plates/baker_st.png",
            timeline_id="MAIN",
            interval=FuzzyInterval.point_known(1.0, 1.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id="reader",
            asserted_by=AssertedBy.NARRATOR,
            truth_status=TruthStatus.TRUE,
        ),
    )
    store.add_attribute(
        "hound",
        Attribute(
            target_kind=TargetKind.LOCATION,
            target_id="loc:baker_st",
            key="ambience_sound",
            value="crackling_hearth_distant_hansom_cabs",
            timeline_id="MAIN",
            interval=FuzzyInterval.point_known(1.0, 1.0),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id="reader",
            asserted_by=AssertedBy.NARRATOR,
            truth_status=TruthStatus.TRUE,
        ),
    )

    snap = store.bible_at("hound", 1.0)
    assert "loc:baker_st" in snap.locations
    loc = snap.locations["loc:baker_st"]
    assert loc.canonical_name == "221B Baker Street"
    assert loc.master_plate_path == "assets/plates/baker_st.png"
    assert loc.ambience_sound == "crackling_hearth_distant_hansom_cabs"


def test_store_review_item_lifecycle(store: Store) -> None:
    item = ReviewItem(
        id="rev:1001",
        novel_id="lotm",
        chapter=1.0,
        kind="ambiguous_entity_merge",
        message="Ambiguous alias candidate for Zhou Mingrui vs Klein Moretti",
        candidates=[{"self_id": "char:zhou", "score": 0.82}],
        created_at=100.0,
    )
    store.add_review_item(item)

    fetched = store.get_review_item("rev:1001")
    assert fetched is not None
    assert fetched.resolved is False
    assert fetched.candidates == [{"self_id": "char:zhou", "score": 0.82}]

    unresolved = store.list_review_items("lotm", resolved=False)
    assert len(unresolved) == 1
    assert unresolved[0].id == "rev:1001"

    store.resolve_review_item("rev:1001", resolution="MERGE_AS_ALIAS")

    resolved_items = store.list_review_items("lotm", resolved=True)
    assert len(resolved_items) == 1
    assert resolved_items[0].resolution == "MERGE_AS_ALIAS"
    assert resolved_items[0].resolved is True
