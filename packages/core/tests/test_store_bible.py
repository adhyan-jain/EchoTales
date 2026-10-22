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


def test_location_plates_persona_versions_and_relationships(store: Store) -> None:
    from echotales.core.models import LocationPlate, PersonaVersion, Relation, VoiceProfile

    # 1. LocationPlate CRUD
    plate = LocationPlate(
        id="plate:221b",
        novel_id="showcase",
        location_id="loc:study",
        title="221B Baker St Study",
        source_url="file:///tmp/study.png",
        angle="establishing",
        time_of_day="day",
        is_approved=True,
    )
    store.add_location_plate(plate)
    plates = store.list_location_plates("showcase", "loc:study")
    assert len(plates) == 1
    assert plates[0].id == "plate:221b"
    assert plates[0].is_approved is True

    # 2. PersonaVersion CRUD
    pv = PersonaVersion(
        id="pv:holmes:1",
        novel_id="showcase",
        self_id="char:holmes",
        persona_id="persona:holmes:dressing_gown",
        chapter_introduced=1.0,
        shift_reason="outfit_change",
    )
    store.add_persona_version(pv)
    pvs = store.list_persona_versions("showcase", "char:holmes")
    assert len(pvs) == 1
    assert pvs[0].persona_id == "persona:holmes:dressing_gown"

    # 3. VoiceProfile CRUD
    vp = VoiceProfile(
        id="vp:holmes",
        novel_id="showcase",
        self_id="char:holmes",
        speaker_id="p225",
        gender="male",
        pitch=1.05,
    )
    store.add_voice_profile(vp)
    fetched_vp = store.get_voice_profile("showcase", "char:holmes")
    assert fetched_vp is not None
    assert fetched_vp.speaker_id == "p225"

    # 4. Relation in StoryBibleSnapshot
    store.add_self(Self(id="char:holmes", novel_id="showcase", canonical_label="Holmes", first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.add_self(Self(id="char:watson", novel_id="showcase", canonical_label="Watson", first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.add_relation("showcase", Relation(
        src_self="char:holmes",
        dst_self="char:watson",
        type="colleague",
        learned_at_pos=DiscoursePosition(chapter=1, offset=0),
        observer_id="narrator",
        asserted_by=AssertedBy.NARRATOR,
        evidence="my dear Watson",
        interval=FuzzyInterval.open_ended(1.0),
    ))

    snapshot = store.bible_at("showcase", 1.0)
    assert "char:holmes" in snapshot.relationships
    assert snapshot.relationships["char:holmes"]["char:watson"] == "colleague"


def test_bible_reads_looks_stored_on_the_body1_persona_when_no_binding_exists() -> None:
    """The reader writes looks to `<self>:body1` (persona_at's answer); bible_at asked for `<self>:default` and found none."""
    from echotales.core.enums import AssertedBy, TargetKind
    from echotales.core.interval import FuzzyInterval
    from echotales.core.models import Attribute, DiscoursePosition, Self

    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    store.add_self(Self(id="n:self:a", novel_id="n", canonical_label="Alice",
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    for chapter, key, value in ((3, "hair_color", "black"), (9, "eye_color", "brown")):
        store.add_attribute("n", Attribute(
            target_kind=TargetKind.PERSONA, target_id="n:self:a:body1", key=key, value=value,
            interval=FuzzyInterval.open_ended(chapter, last_evidence=chapter),
            learned_at_pos=DiscoursePosition(chapter=chapter, offset=0), observer_id="reader",
            asserted_by=AssertedBy.INFERENCE))
    assert store.bible_at("n", 5).characters["n:self:a"].attributes == {"hair_color": "black"}  # no look-ahead
    assert store.bible_at("n", 9).characters["n:self:a"].attributes == {"hair_color": "black", "eye_color": "brown"}
