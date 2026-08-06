"""Tests for the store and ``state_of``.

Organised around the case table in plans.md §3 -- the set of situations a flat
entity table cannot represent. Each class below is one row of that table, plus
the temporal and epistemic behaviours the query has to get right.
"""

from __future__ import annotations

import pytest
from echotales.core.enums import (
    OBSERVER_READER,
    OBSERVER_SYSTEM,
    AliasType,
    AssertedBy,
    Canonicity,
    EventType,
    NarrativeLayer,
    Prominence,
    SegmentType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import Certainty, FuzzyInterval
from echotales.core.models import (
    MAIN_TIMELINE,
    AliasBinding,
    Attribute,
    DiscoursePosition,
    NarrativeSegment,
    Persona,
    Relation,
    ResolutionEvent,
    Self,
    SelfPersonaBinding,
)
from echotales.core.state import StateResolver
from echotales.core.store import Store

NOVEL = "test-novel"
WU_CLAN = "WU_CLAN"


@pytest.fixture
def store() -> Store:
    s = Store(":memory:")
    s.add_novel(NOVEL, "Test Novel", "data/raw/test.epub", "test")
    return s


def make_self(store: Store, sid: str, label: str, chapter: int = 1) -> Self:
    entity = Self(
        id=sid,
        novel_id=NOVEL,
        canonical_label=label,
        first_attested_pos=DiscoursePosition(chapter=chapter),
    )
    store.add_self(entity)
    return entity


def make_persona(store: Store, pid: str, label: str, chapter: int = 1) -> Persona:
    p = Persona(
        id=pid,
        novel_id=NOVEL,
        body_label=label,
        first_attested_pos=DiscoursePosition(chapter=chapter),
    )
    store.add_persona(p)
    return p


def bind_alias(
    store: Store,
    alias: str,
    target_id: str,
    *,
    kind: TargetKind = TargetKind.SELF,
    alias_type: AliasType = AliasType.RIGID_NAME,
    interval: FuzzyInterval | None = None,
    learned_at: int = 1,
    observer: str = OBSERVER_READER,
    truth: TruthStatus = TruthStatus.TRUE,
    asserted_by: AssertedBy = AssertedBy.NARRATOR,
) -> int:
    return store.add_alias_binding(
        NOVEL,
        AliasBinding(
            alias=alias,
            alias_type=alias_type,
            target_kind=kind,
            target_id=target_id,
            interval=interval or FuzzyInterval.open_ended(learned_at, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=learned_at),
            observer_id=observer,
            truth_status=truth,
            asserted_by=asserted_by,
        ),
    )


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------


class TestGenericDescriptorsNeverEnterTheGraph:
    """Non-negotiable #4, enforced at construction rather than by convention."""

    def test_constructing_a_generic_descriptor_binding_raises(self) -> None:
        with pytest.raises(ValueError, match="never be persisted"):
            AliasBinding(
                alias="the innkeeper",
                alias_type=AliasType.GENERIC_DESCRIPTOR,
                target_kind=TargetKind.SELF,
                target_id="s1",
                interval=FuzzyInterval.unbounded(),
                learned_at_pos=DiscoursePosition(chapter=1),
                observer_id=OBSERVER_READER,
            )

    def test_every_other_alias_type_is_constructible(self) -> None:
        for at in AliasType:
            if at is AliasType.GENERIC_DESCRIPTOR:
                continue
            AliasBinding(
                alias="x",
                alias_type=at,
                target_kind=TargetKind.SELF,
                target_id="s1",
                interval=FuzzyInterval.unbounded(),
                learned_at_pos=DiscoursePosition(chapter=1),
                observer_id=OBSERVER_READER,
            )


# ---------------------------------------------------------------------------
# plans.md §3 case table
# ---------------------------------------------------------------------------


class TestOrdinaryCharacter:
    """One self, one persona, binding open-ended."""

    def test_aliases_and_persona_resolve(self, store: Store) -> None:
        make_self(store, "s_li", "Li Wei")
        make_persona(store, "p_li", "Li Wei's body")
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_li",
                persona_id="p_li",
                interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=1),
                observer_id=OBSERVER_READER,
            )
        )
        bind_alias(store, "Li Wei", "s_li")
        store.conn.commit()

        res = StateResolver(store, NOVEL).state_of("s_li", position=50)
        assert res.aliases == ["Li Wei"]
        assert res.persona_ids == ["p_li"]


class TestReincarnation:
    """One self, two personas, sequential bindings.

    The point of the split: querying at chapter 10 must return the old body,
    at chapter 300 the new one -- while relationships and memory stay attached
    to the single continuous self.
    """

    @pytest.fixture
    def resolver(self, store: Store) -> StateResolver:
        make_self(store, "s_soul", "The Traveller")
        make_persona(store, "p_old", "original body")
        make_persona(store, "p_new", "reborn body", chapter=100)
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_soul",
                persona_id="p_old",
                interval=FuzzyInterval.point_known(1, 100),
                learned_at_pos=DiscoursePosition(chapter=1),
                observer_id=OBSERVER_READER,
            )
        )
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_soul",
                persona_id="p_new",
                interval=FuzzyInterval.open_ended(100, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=100),
                observer_id=OBSERVER_READER,
            )
        )
        store.conn.commit()
        return StateResolver(store, NOVEL)

    def test_early_position_returns_the_original_body(self, resolver: StateResolver) -> None:
        assert resolver.state_of("s_soul", position=50).persona_ids == ["p_old"]

    def test_late_position_returns_the_reborn_body(self, resolver: StateResolver) -> None:
        assert resolver.state_of("s_soul", position=300).persona_ids == ["p_new"]

    def test_bodies_never_coexist(self, resolver: StateResolver) -> None:
        for pos in (50, 300):
            assert len(resolver.state_of("s_soul", position=pos).persona_ids) == 1


class TestBodySwap:
    """Two selves, two personas, bindings crossed at the swap point."""

    def test_each_self_gets_the_other_body_after_the_swap(self, store: Store) -> None:
        make_self(store, "s_a", "A")
        make_self(store, "s_b", "B")
        make_persona(store, "p_a", "body A")
        make_persona(store, "p_b", "body B")
        swap = 200.0
        for sid, before, after in (("s_a", "p_a", "p_b"), ("s_b", "p_b", "p_a")):
            store.add_self_persona_binding(
                SelfPersonaBinding(
                    self_id=sid,
                    persona_id=before,
                    interval=FuzzyInterval.point_known(1, swap),
                    learned_at_pos=DiscoursePosition(chapter=1),
                    observer_id=OBSERVER_READER,
                )
            )
            store.add_self_persona_binding(
                SelfPersonaBinding(
                    self_id=sid,
                    persona_id=after,
                    interval=FuzzyInterval.open_ended(swap, last_evidence=1e6),
                    learned_at_pos=DiscoursePosition(chapter=int(swap)),
                    observer_id=OBSERVER_READER,
                )
            )
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        assert r.state_of("s_a", position=100).persona_ids == ["p_a"]
        assert r.state_of("s_b", position=100).persona_ids == ["p_b"]
        assert r.state_of("s_a", position=300).persona_ids == ["p_b"]
        assert r.state_of("s_b", position=300).persona_ids == ["p_a"]


class TestCloneOrSoulAvatar:
    """One self, concurrent persona bindings.

    Concurrency here is legitimate, which is why the co-presence penalty in the
    resolver applies between personas and never between selves.
    """

    def test_both_bodies_are_active_simultaneously(self, store: Store) -> None:
        make_self(store, "s_main", "Cultivator")
        make_persona(store, "p_body", "true body")
        make_persona(store, "p_avatar", "soul avatar", chapter=80)
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_main",
                persona_id="p_body",
                interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=1),
                observer_id=OBSERVER_READER,
            )
        )
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_main",
                persona_id="p_avatar",
                interval=FuzzyInterval.open_ended(80, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=80),
                observer_id=OBSERVER_READER,
            )
        )
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        assert r.state_of("s_main", position=50).persona_ids == ["p_body"]
        assert set(r.state_of("s_main", position=150).persona_ids) == {"p_body", "p_avatar"}
        assert set(r.concurrent_personas("s_main", MAIN_TIMELINE, 150)) == {"p_body", "p_avatar"}


class TestPossession:
    """Two selves contesting one persona over overlapping intervals."""

    def test_one_body_is_claimed_by_two_selves(self, store: Store) -> None:
        make_self(store, "s_host", "Host")
        make_self(store, "s_spirit", "Spirit")
        make_persona(store, "p_host", "host body")
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_host",
                persona_id="p_host",
                interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=1),
                observer_id=OBSERVER_READER,
            )
        )
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_spirit",
                persona_id="p_host",
                interval=FuzzyInterval.point_known(120, 180),
                learned_at_pos=DiscoursePosition(chapter=120),
                observer_id=OBSERVER_READER,
            )
        )
        store.conn.commit()

        contenders = store.get_self_persona_bindings(persona_id="p_host")
        assert {b.self_id for b in contenders} == {"s_host", "s_spirit"}
        r = StateResolver(store, NOVEL)
        assert r.state_of("s_spirit", position=150).persona_ids == ["p_host"]
        assert r.state_of("s_spirit", position=300).persona_ids == []


class TestSustainedDisguise:
    """One self, several simultaneous personas with different audience scopes.

    This is the headline case. The same query, differing only in observer, must
    return different alias sets -- the reader knows the disguise, the deceived
    faction does not, and neither view may leak into the other.
    """

    @pytest.fixture
    def resolver(self, store: Store) -> StateResolver:
        make_self(store, "s_fy", "Fang Yuan")
        make_persona(store, "p_true", "true body")
        make_persona(store, "p_disguise", "assumed body", chapter=60)
        for pid, start in (("p_true", 1), ("p_disguise", 60)):
            store.add_self_persona_binding(
                SelfPersonaBinding(
                    self_id="s_fy",
                    persona_id=pid,
                    interval=FuzzyInterval.open_ended(start, last_evidence=1e6),
                    learned_at_pos=DiscoursePosition(chapter=start),
                    observer_id=OBSERVER_READER,
                )
            )

        # What the reader is told.
        bind_alias(store, "Fang Yuan", "s_fy", learned_at=1)
        bind_alias(
            store,
            "Wu Yi Hai",
            "s_fy",
            learned_at=60,
            truth=TruthStatus.FABRICATED,
        )
        # What the deceived faction believes: for them the identity is simply true.
        bind_alias(store, "Wu Yi Hai", "s_fy", learned_at=60, observer=WU_CLAN)
        store.conn.commit()
        return StateResolver(store, NOVEL)

    def test_reader_sees_both_the_real_name_and_the_disguise(
        self, resolver: StateResolver
    ) -> None:
        aliases = resolver.state_of("s_fy", position=100, observer_id=OBSERVER_READER).aliases
        assert set(aliases) == {"Fang Yuan", "Wu Yi Hai"}

    def test_deceived_faction_sees_only_the_disguise(self, resolver: StateResolver) -> None:
        aliases = resolver.state_of("s_fy", position=100, observer_id=WU_CLAN).aliases
        assert aliases == ["Wu Yi Hai"]

    def test_the_two_views_differ(self, resolver: StateResolver) -> None:
        """The acceptance test named in the plan."""
        reader = resolver.state_of("s_fy", position=100, observer_id=OBSERVER_READER)
        clan = resolver.state_of("s_fy", position=100, observer_id=WU_CLAN)
        assert set(reader.aliases) != set(clan.aliases)

    def test_disguise_is_invisible_before_it_is_adopted(self, resolver: StateResolver) -> None:
        early = resolver.state_of("s_fy", position=30, observer_id=OBSERVER_READER)
        assert early.aliases == ["Fang Yuan"]

    def test_fabricated_identity_is_not_marked_false(self, resolver: StateResolver) -> None:
        """FABRICATED means invented wholesale, not 'a lie to be filtered out'.

        Filtering it as FALSE would hide the disguise from the reader view,
        which is precisely backwards.
        """
        bindings = [
            b for b in store_aliases(resolver) if b.alias == "Wu Yi Hai" and b.observer_id == "READER"
        ]
        assert bindings and bindings[0].truth_status is TruthStatus.FABRICATED


def store_aliases(resolver: StateResolver) -> list[AliasBinding]:
    return resolver.store.get_aliases_for(TargetKind.SELF, "s_fy")


class TestDreamRealmPersona:
    """A temporary identity scoped to a dream timeline only.

    Dream-realm entities must not merge with main-timeline ones: the
    protagonist living as someone else's son inside a dream is a dream persona,
    not a main-timeline identity.
    """

    def test_dream_persona_does_not_appear_on_the_main_timeline(self, store: Store) -> None:
        dream = "DREAM_TU_SHI_CHENG"
        make_self(store, "s_fy", "Fang Yuan")
        make_persona(store, "p_true", "true body")
        make_persona(store, "p_dream", "dream persona", chapter=90)
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_fy",
                persona_id="p_true",
                interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=1),
                observer_id=OBSERVER_READER,
            )
        )
        store.add_self_persona_binding(
            SelfPersonaBinding(
                self_id="s_fy",
                persona_id="p_dream",
                timeline_id=dream,
                interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=90),
                observer_id=OBSERVER_READER,
            )
        )
        store.add_segments(
            [
                NarrativeSegment(
                    id="seg_dream",
                    novel_id=NOVEL,
                    chapter_from=90,
                    offset_from=0,
                    chapter_to=92,
                    offset_to=0,
                    timeline_id=dream,
                    story_seq_from=1,
                    story_seq_to=50,
                    segment_type=SegmentType.DREAM_OTHER,
                    narrative_layer=NarrativeLayer.DREAM_OTHER,
                )
            ]
        )
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        assert r.state_of("s_fy", position=95).persona_ids == ["p_true"]
        assert r.state_of("s_fy", timeline_id=dream, position=10).persona_ids == ["p_dream"]

    def test_cross_timeline_facts_are_excluded_not_compared(self, store: Store) -> None:
        """Timelines form a partial order; comparing them would invent an ordering."""
        make_self(store, "s_x", "X")
        bind_alias(store, "Dream Name", "s_x", learned_at=1)
        store.conn.commit()
        r = StateResolver(store, NOVEL)
        assert r.state_of("s_x", timeline_id="DREAM_OTHER", position=50).aliases == []


# ---------------------------------------------------------------------------
# Temporal and epistemic behaviour
# ---------------------------------------------------------------------------


class TestTransferableTitle:
    """A title changing hands -- close the interval, do not retract."""

    def test_each_position_returns_the_holder_of_that_era(self, store: Store) -> None:
        make_self(store, "s_old", "Old Master")
        make_self(store, "s_new", "New Master", chapter=150)
        bind_alias(
            store,
            "Sect Master",
            "s_old",
            alias_type=AliasType.TRANSFERABLE_TITLE,
            interval=FuzzyInterval.point_known(1, 150),
        )
        bind_alias(
            store,
            "Sect Master",
            "s_new",
            alias_type=AliasType.TRANSFERABLE_TITLE,
            interval=FuzzyInterval.open_ended(150, last_evidence=1e6),
            learned_at=150,
        )
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        early = r.resolve_alias("Sect Master", position=50)
        late = r.resolve_alias("Sect Master", position=300)
        assert [t[1] for t in early] == ["s_old"]
        assert [t[1] for t in late] == ["s_new"]

    def test_an_alias_may_have_several_simultaneous_holders(self, store: Store) -> None:
        """Alias->target is one-to-many; the temporal index filters, it does not resolve."""
        make_self(store, "s_1", "Elder One")
        make_self(store, "s_2", "Elder Two")
        for sid in ("s_1", "s_2"):
            bind_alias(store, "Elder", sid, alias_type=AliasType.TRANSFERABLE_TITLE)
        store.conn.commit()

        holders = StateResolver(store, NOVEL).resolve_alias("Elder", position=50)
        assert len(holders) == 2


class TestRetractionVersusIntervalEnd:
    """Non-negotiable #5. These are different questions and must behave differently."""

    def test_closing_an_interval_hides_the_fact_only_afterwards(self, store: Store) -> None:
        make_self(store, "s_a", "A")
        bid = bind_alias(
            store,
            "Sect Master",
            "s_a",
            alias_type=AliasType.TRANSFERABLE_TITLE,
        )
        store.close_alias_interval(bid, 150, None)
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        assert r.state_of("s_a", position=100).aliases == ["Sect Master"]
        assert r.state_of("s_a", position=200).aliases == []

    def test_retraction_erases_the_fact_only_after_the_reveal(self, store: Store) -> None:
        """A reader standing before the reveal still holds the mistaken belief."""
        make_self(store, "s_impostor", "Impostor")
        bid = bind_alias(store, "True Heir", "s_impostor", learned_at=10)
        store.retract_alias(bid, DiscoursePosition(chapter=200))
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        before = r.state_of(
            "s_impostor", position=100, knowledge_pos=DiscoursePosition(chapter=100)
        )
        after = r.state_of(
            "s_impostor", position=300, knowledge_pos=DiscoursePosition(chapter=300)
        )
        assert before.aliases == ["True Heir"]
        assert after.aliases == []

    def test_retraction_leaves_the_interval_intact(self, store: Store) -> None:
        """The claim did span that time; only its truth changed."""
        make_self(store, "s_i", "Impostor")
        bid = bind_alias(store, "True Heir", "s_i", learned_at=10)
        before = store.get_aliases_for(TargetKind.SELF, "s_i")[0].interval
        store.retract_alias(bid, DiscoursePosition(chapter=200))
        store.conn.commit()
        after = store.get_aliases_for(TargetKind.SELF, "s_i")[0]
        assert after.interval == before
        assert after.retracted_at == DiscoursePosition(chapter=200)

    def test_system_observer_sees_retracted_facts(self, store: Store) -> None:
        """The oracle view, needed for evaluation and debugging."""
        make_self(store, "s_i", "Impostor")
        bid = bind_alias(store, "True Heir", "s_i", learned_at=10)
        store.retract_alias(bid, DiscoursePosition(chapter=200))
        store.conn.commit()
        r = StateResolver(store, NOVEL)
        assert r.state_of("s_i", position=300, observer_id=OBSERVER_SYSTEM).aliases == ["True Heir"]


class TestKnowledgeTime:
    def test_a_fact_is_invisible_before_the_reader_learns_it(self, store: Store) -> None:
        make_self(store, "s_x", "X")
        bind_alias(
            store,
            "Frost Emperor",
            "s_x",
            alias_type=AliasType.EPITHET,
            interval=FuzzyInterval.since_before(200),
            learned_at=200,
        )
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        assert r.state_of("s_x", position=50, knowledge_pos=DiscoursePosition(chapter=50)).aliases == []

    def test_a_reveal_applies_retroactively_in_story_time(self, store: Store) -> None:
        """Chapter 200 discloses a fact that was true from chapter 1.

        Reading at chapter 300 about events at chapter 50, the reader now knows
        the binding held then. This is why first-attestation is a soft prior
        rather than a hard constraint (plans.md §4.4) -- a hard constraint would
        forbid the very binding the reveal establishes.
        """
        make_self(store, "s_x", "X")
        bind_alias(
            store,
            "Frost Emperor",
            "s_x",
            alias_type=AliasType.EPITHET,
            interval=FuzzyInterval.since_before(200),
            learned_at=200,
        )
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        res = r.state_of("s_x", position=50, knowledge_pos=DiscoursePosition(chapter=300))
        assert res.aliases == ["Frost Emperor"]


class TestVoidedSpans:
    def test_facts_on_a_voided_timeline_are_excluded(self, store: Store) -> None:
        illusion = "ILLUSION_ARC"
        make_self(store, "s_x", "X")
        store.add_segments(
            [
                NarrativeSegment(
                    id="seg_ill",
                    novel_id=NOVEL,
                    chapter_from=100,
                    offset_from=0,
                    chapter_to=120,
                    offset_to=0,
                    timeline_id=illusion,
                    story_seq_from=1,
                    story_seq_to=20,
                    segment_type=SegmentType.ILLUSION,
                    canonicity=Canonicity.VOIDED,
                )
            ]
        )
        store.add_alias_binding(
            NOVEL,
            AliasBinding(
                alias="Illusory Title",
                alias_type=AliasType.EPITHET,
                target_kind=TargetKind.SELF,
                target_id="s_x",
                timeline_id=illusion,
                interval=FuzzyInterval.open_ended(1, last_evidence=100),
                learned_at_pos=DiscoursePosition(chapter=100),
                observer_id=OBSERVER_READER,
            ),
        )
        store.conn.commit()

        r = StateResolver(store, NOVEL)
        assert r.state_of("s_x", timeline_id=illusion, position=10).aliases == []


class TestAttributeRouting:
    def test_later_evidence_supersedes_earlier_on_the_same_key(self, store: Store) -> None:
        make_persona(store, "p_x", "body")
        for value, learned in (("black", 3), ("white", 150)):
            store.add_attribute(
                NOVEL,
                Attribute(
                    target_kind=TargetKind.PERSONA,
                    target_id="p_x",
                    key="hair_colour",
                    value=value,
                    interval=FuzzyInterval.open_ended(learned, last_evidence=1e6),
                    learned_at_pos=DiscoursePosition(chapter=learned),
                    observer_id=OBSERVER_READER,
                ),
            )
        store.conn.commit()
        r = StateResolver(store, NOVEL)

        early = r.state_of(
            "p_x",
            target_kind=TargetKind.PERSONA,
            position=50,
            knowledge_pos=DiscoursePosition(chapter=50),
        )
        late = r.state_of(
            "p_x",
            target_kind=TargetKind.PERSONA,
            position=300,
            knowledge_pos=DiscoursePosition(chapter=300),
        )
        assert early.attributes["hair_colour"] == "black"
        assert late.attributes["hair_colour"] == "white"


class TestRelations:
    def test_relations_resolve_between_selves(self, store: Store) -> None:
        make_self(store, "s_master", "Master")
        make_self(store, "s_disciple", "Disciple")
        store.add_relation(
            NOVEL,
            Relation(
                src_self="s_disciple",
                dst_self="s_master",
                type="MASTER_OF",
                interval=FuzzyInterval.open_ended(5, last_evidence=1e6),
                learned_at_pos=DiscoursePosition(chapter=5),
                observer_id=OBSERVER_READER,
            ),
        )
        store.conn.commit()
        res = StateResolver(store, NOVEL).state_of("s_disciple", position=100)
        assert ("MASTER_OF", "s_master") in res.relationships


class TestCertaintyPropagation:
    def test_a_plausible_fact_weakens_the_overall_result(self, store: Store) -> None:
        make_self(store, "s_x", "X")
        bind_alias(store, "Old Title", "s_x", interval=FuzzyInterval.open_ended(1))
        store.conn.commit()
        res = StateResolver(store, NOVEL).state_of("s_x", position=5000)
        assert res.certainty == Certainty.PLAUSIBLE.value

    def test_plausible_facts_can_be_filtered_out(self, store: Store) -> None:
        make_self(store, "s_x", "X")
        bind_alias(store, "Old Title", "s_x", interval=FuzzyInterval.open_ended(1))
        store.conn.commit()
        res = StateResolver(store, NOVEL).state_of(
            "s_x", position=5000, include_plausible=False
        )
        assert res.aliases == []


# ---------------------------------------------------------------------------
# Store mechanics
# ---------------------------------------------------------------------------


class TestEventLog:
    def test_events_replay_in_sequence_order(self, store: Store) -> None:
        for i, et in enumerate([EventType.NEW_ENTITY, EventType.LINK, EventType.REBIND], start=1):
            store.append_event(
                ResolutionEvent(
                    id=f"e{i}",
                    seq=i,
                    type=et,
                    payload={"n": i},
                    cause_pos=DiscoursePosition(chapter=i * 10),
                )
            )
        store.conn.commit()
        assert [e.seq for e in store.iter_events()] == [1, 2, 3]

    def test_replay_can_be_truncated_to_a_position(self, store: Store) -> None:
        """The replay debugger: what did the graph believe at chapter 15?"""
        for i, et in enumerate([EventType.NEW_ENTITY, EventType.LINK, EventType.REBIND], start=1):
            store.append_event(
                ResolutionEvent(
                    id=f"e{i}",
                    seq=i,
                    type=et,
                    payload={},
                    cause_pos=DiscoursePosition(chapter=i * 10),
                )
            )
        store.conn.commit()
        seen = list(store.iter_events(up_to=DiscoursePosition(chapter=15)))
        assert [e.seq for e in seen] == [1]

    def test_next_seq_advances(self, store: Store) -> None:
        assert store.next_seq() == 1
        store.append_event(
            ResolutionEvent(
                id="e1",
                seq=store.next_seq(),
                type=EventType.NEW_ENTITY,
                payload={},
                cause_pos=DiscoursePosition(chapter=1),
            )
        )
        store.conn.commit()
        assert store.next_seq() == 2

    def test_duplicate_sequence_numbers_are_rejected(self, store: Store) -> None:
        import sqlite3

        for eid in ("a", "b"):
            if eid == "b":
                with pytest.raises(sqlite3.IntegrityError):
                    store.append_event(
                        ResolutionEvent(
                            id=eid,
                            seq=1,
                            type=EventType.LINK,
                            payload={},
                            cause_pos=DiscoursePosition(chapter=1),
                        )
                    )
            else:
                store.append_event(
                    ResolutionEvent(
                        id=eid,
                        seq=1,
                        type=EventType.NEW_ENTITY,
                        payload={},
                        cause_pos=DiscoursePosition(chapter=1),
                    )
                )


class TestInvalidation:
    def test_only_artifacts_touching_changed_facts_are_invalidated(self, store: Store) -> None:
        store.record_artifact("a1", "GRAPH", ["self:s_1", "self:s_2"], "h1", "{}")
        store.record_artifact("a2", "GRAPH", ["self:s_9"], "h2", "{}")
        store.conn.commit()
        assert store.invalidate_by_facts(["self:s_1"]) == 1

    def test_no_changes_invalidates_nothing(self, store: Store) -> None:
        store.record_artifact("a1", "GRAPH", ["self:s_1"], "h1", "{}")
        store.conn.commit()
        assert store.invalidate_by_facts([]) == 0


class TestReadSet:
    def test_state_of_reports_the_facts_it_consulted(self, store: Store) -> None:
        make_self(store, "s_x", "X")
        bind_alias(store, "X", "s_x")
        store.conn.commit()
        res = StateResolver(store, NOVEL).state_of("s_x", position=50)
        assert "self:s_x" in res.read_set
        assert any(r.startswith("alias:") for r in res.read_set)


class TestDiscoursePosition:
    def test_ordering_is_total(self) -> None:
        a = DiscoursePosition(chapter=1, offset=5)
        b = DiscoursePosition(chapter=1, offset=9)
        c = DiscoursePosition(chapter=2, offset=0)
        assert a < b < c
        assert c > a

    def test_sortable_round_trip(self) -> None:
        p = DiscoursePosition(chapter=199, offset=1234)
        assert DiscoursePosition.from_sortable(p.as_sortable()) == p


class TestProminence:
    def test_mention_counts_drive_tiering(self, store: Store) -> None:
        from echotales.core.enums import ReferenceMode, SpanType
        from echotales.core.models import Mention

        make_self(store, "s_main", "Main")
        store.add_mentions(
            [
                Mention(
                    id=f"m{i}",
                    novel_id=NOVEL,
                    segment_id="seg1",
                    chapter=1,
                    offset=i,
                    text="Main",
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION_ACTION,
                    reference_mode=ReferenceMode.PRESENT,
                    target_kind=TargetKind.SELF,
                    target_id="s_main",
                )
                for i in range(5)
            ]
        )
        store.conn.commit()
        assert store.mention_counts(NOVEL) == {"s_main": 5}
        store.set_prominence("s_main", Prominence.PRINCIPAL)
        entity = store.get_self("s_main")
        assert entity is not None and entity.prominence is Prominence.PRINCIPAL


class TestEscalationAccounting:
    def test_escalation_stats_are_recorded_per_stage(self, store: Store) -> None:
        store.log_llm_call(stage="resolve", tier="local", model="qwen", escalated=False)
        store.log_llm_call(
            stage="resolve", tier="api", model="claude", escalated=True, escalation_reason="DEFER"
        )
        store.conn.commit()
        stats = {(r["stage"], r["tier"]): r for r in store.escalation_stats()}
        assert stats[("resolve", "api")]["escalations"] == 1
