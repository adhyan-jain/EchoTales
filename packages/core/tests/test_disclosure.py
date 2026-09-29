"""Tests for the Minimal Disclosure Compiler (`core/disclosure.py`).

Each class mirrors an existing `state_of`/observer-axis test scenario from
`test_state.py`/`test_observer_axis.py`, verifying `compile_minimal_disclosure`
preserves (never widens) what `state_of` already established, while
narrowing further per a `TaskSpec`. `TestGreedySetCoverProperty` and
`TestMinimalDisclosureReadSet` are the two classes with no state_of analog --
they test properties unique to this module.
"""

from __future__ import annotations

import pytest
from echotales.core.disclosure import TaskSpec, compile_minimal_disclosure
from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    AssertedBy,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    DiscoursePosition,
    Observation,
    Persona,
    Self,
    SelfPersonaBinding,
)
from echotales.core.readset import entity_ref, observable_ref
from echotales.core.state import compile_generation_state
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
        id=sid, novel_id=NOVEL, canonical_label=label,
        first_attested_pos=DiscoursePosition(chapter=chapter),
    )
    store.add_self(entity)
    return entity


def make_persona(store: Store, pid: str, label: str, chapter: int = 1) -> Persona:
    p = Persona(
        id=pid, novel_id=NOVEL, body_label=label,
        first_attested_pos=DiscoursePosition(chapter=chapter),
    )
    store.add_persona(p)
    return p


def bind_alias(
    store: Store,
    alias: str,
    target_id: str,
    *,
    alias_type: AliasType = AliasType.RIGID_NAME,
    interval: FuzzyInterval | None = None,
    learned_at: int = 1,
    observer: str = OBSERVER_READER,
    truth: TruthStatus = TruthStatus.TRUE,
) -> int:
    return store.add_alias_binding(
        NOVEL,
        AliasBinding(
            alias=alias,
            alias_type=alias_type,
            target_kind=TargetKind.SELF,
            target_id=target_id,
            interval=interval or FuzzyInterval.open_ended(learned_at, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=learned_at),
            observer_id=observer,
            truth_status=truth,
            asserted_by=AssertedBy.NARRATOR,
        ),
    )


def add_attr(
    store: Store,
    target_id: str,
    key: str,
    value: str,
    *,
    learned_at: int = 1,
    retracted_at: DiscoursePosition | None = None,
    kind: TargetKind = TargetKind.SELF,
) -> None:
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=kind,
            target_id=target_id,
            key=key,
            value=value,
            interval=FuzzyInterval.open_ended(learned_at, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=learned_at),
            observer_id=OBSERVER_READER,
            retracted_at=retracted_at,
        ),
    )


def bind_persona(
    store: Store, self_id: str, persona_id: str, *, start: int = 1, end: int | None = None
) -> None:
    interval = (
        FuzzyInterval.point_known(start, end)
        if end is not None
        else FuzzyInterval.open_ended(start, last_evidence=1e6)
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id=self_id,
            persona_id=persona_id,
            interval=interval,
            learned_at_pos=DiscoursePosition(chapter=start),
            observer_id=OBSERVER_READER,
        )
    )


# ---------------------------------------------------------------------------
# Mirrors TestSustainedDisguise (test_state.py:318-392)
# ---------------------------------------------------------------------------


class TestDisguiseUnderMinimalDisclosure:
    @pytest.fixture
    def store_with_disguise(self, store: Store) -> Store:
        make_self(store, "s_fy", "Fang Yuan")
        bind_alias(store, "Fang Yuan", "s_fy", learned_at=1)
        bind_alias(store, "Wu Yi Hai", "s_fy", learned_at=60, truth=TruthStatus.FABRICATED)
        bind_alias(store, "Wu Yi Hai", "s_fy", learned_at=60, observer=WU_CLAN)
        store.conn.commit()
        return store

    def test_deceived_faction_never_sees_the_real_name_after_minimization(
        self, store_with_disguise: Store
    ) -> None:
        result = compile_minimal_disclosure(
            store_with_disguise, NOVEL, ["s_fy"], TaskSpec(task_id="name_only"),
            position=100, observer_id=WU_CLAN,
        )
        assert "alias:Fang Yuan" not in result.state.allowed_facts
        # The forbidden set is exactly what a leakage validator checks
        # generated text against.
        assert "Fang Yuan" in result.state.forbidden_facts

    def test_a_single_target_keeps_only_one_name_when_no_ambiguity_exists(
        self, store_with_disguise: Store
    ) -> None:
        """The reader's candidate set has two valid aliases for one target
        (the real name and the disguise); with only one target in the batch
        there is nothing to disambiguate, so minimization keeps exactly one --
        the concrete demonstration that this is coverage-driven selection,
        not "keep everything the observer can see" (`compile_generation_state`
        keeps both) and not top-k-by-priority (which would also keep both,
        up to its cap)."""
        candidate = compile_generation_state(
            store_with_disguise, NOVEL, ["s_fy"], position=100, observer_id=OBSERVER_READER
        )
        assert len([f for f in candidate.allowed_facts if f.startswith("alias:")]) == 2

        result = compile_minimal_disclosure(
            store_with_disguise, NOVEL, ["s_fy"], TaskSpec(task_id="name_only"),
            position=100, observer_id=OBSERVER_READER,
        )
        selected_aliases = [f for f in result.state.allowed_facts if f.startswith("alias:")]
        assert len(selected_aliases) == 1


# ---------------------------------------------------------------------------
# Mirrors TestRetractionVersusIntervalEnd (test_state.py:502-548)
# ---------------------------------------------------------------------------


class TestRetractedFactsUnderMinimalDisclosure:
    def test_a_retracted_fact_is_still_selected_before_the_reveal_if_required(
        self, store: Store
    ) -> None:
        make_self(store, "s_impostor", "Impostor")
        add_attr(
            store, "s_impostor", "status", "secretly the heir",
            learned_at=10, retracted_at=DiscoursePosition(chapter=200),
        )
        store.conn.commit()
        task = TaskSpec(task_id="status_check", required_keys={TargetKind.SELF: frozenset({"status"})})

        result = compile_minimal_disclosure(
            store, NOVEL, ["s_impostor"], task,
            position=100, observer_id=OBSERVER_READER, knowledge_pos=DiscoursePosition(chapter=100),
        )
        assert "attr:status=secretly the heir" in result.state.allowed_facts
        assert result.unsatisfied_keys == ()

    def test_a_retracted_fact_is_not_selected_after_the_reveal_even_if_required(
        self, store: Store
    ) -> None:
        make_self(store, "s_impostor", "Impostor")
        add_attr(
            store, "s_impostor", "status", "secretly the heir",
            learned_at=10, retracted_at=DiscoursePosition(chapter=200),
        )
        store.conn.commit()
        task = TaskSpec(task_id="status_check", required_keys={TargetKind.SELF: frozenset({"status"})})

        result = compile_minimal_disclosure(
            store, NOVEL, ["s_impostor"], task,
            position=300, observer_id=OBSERVER_READER, knowledge_pos=DiscoursePosition(chapter=300),
        )
        assert "attr:status=secretly the heir" not in result.state.allowed_facts
        assert result.unsatisfied_keys == ("s_impostor:status",)


# ---------------------------------------------------------------------------
# Mirrors TestObserverScoping (test_observer_axis.py:65-171)
# ---------------------------------------------------------------------------


class TestWitnessVsNonWitnessMinimization:
    @pytest.fixture
    def witness_store(self, store: Store) -> Store:
        make_self(store, "s_target", "Target")
        bind_alias(store, "True Name", "s_target", learned_at=5)
        bind_alias(store, "Public Name", "s_target", learned_at=1)
        store.conn.commit()
        return store

    def test_a_non_witness_has_a_narrower_selected_set_than_a_witness(
        self, witness_store: Store
    ) -> None:
        fact = AliasBinding(
            alias="Public Name", alias_type=AliasType.RIGID_NAME, target_kind=TargetKind.SELF,
            target_id="s_target", interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
        )
        witness_store.add_observation(
            Observation(
                observer_id="WITNESS", fact_ref=observable_ref(fact),
                learned_at_pos=DiscoursePosition(chapter=1),
            )
        )
        witness_store.conn.commit()
        task = TaskSpec(task_id="name_only")

        witness = compile_minimal_disclosure(
            witness_store, NOVEL, ["s_target"], task, position=100, observer_id="WITNESS",
        )
        absentee = compile_minimal_disclosure(
            witness_store, NOVEL, ["s_target"], task, position=100, observer_id="ABSENTEE",
        )
        assert set(absentee.state.allowed_facts) < set(witness.state.allowed_facts)

    def test_a_non_witness_never_gains_facts_a_witness_lacks_via_minimization(
        self, witness_store: Store
    ) -> None:
        """MDC only ever shrinks a candidate set further -- it must never
        produce a *different* selection for a strictly less-informed observer."""
        task = TaskSpec(task_id="name_only")
        absentee = compile_minimal_disclosure(
            witness_store, NOVEL, ["s_target"], task, position=100, observer_id="ABSENTEE",
        )
        assert absentee.state.allowed_facts == ()


# ---------------------------------------------------------------------------
# Mirrors TestTransferableTitle (test_state.py:461-500)
# ---------------------------------------------------------------------------


class TestAmbiguousTitleDisambiguation:
    def test_a_shared_title_is_retained_only_when_two_cast_members_collide(
        self, store: Store
    ) -> None:
        make_self(store, "s_1", "Elder One")
        make_self(store, "s_2", "Elder Two")
        bind_alias(store, "Elder", "s_1", alias_type=AliasType.TRANSFERABLE_TITLE, learned_at=1)
        bind_alias(store, "Chen", "s_1", learned_at=1)
        bind_alias(store, "Elder", "s_2", alias_type=AliasType.TRANSFERABLE_TITLE, learned_at=1)
        bind_alias(store, "Li", "s_2", learned_at=1)
        store.conn.commit()

        result = compile_minimal_disclosure(
            store, NOVEL, ["s_1", "s_2"], TaskSpec(task_id="cast_names"), position=100,
        )
        names = {a for a in result.state.allowed_facts if a.startswith("alias:")}
        # Both targets' disambiguating name survives, breaking the "Elder"/"Elder" tie.
        assert "alias:Chen" in names
        assert "alias:Li" in names

    def test_an_unambiguous_alias_within_the_cast_is_still_dropped_if_not_required_for_naming(
        self, store: Store
    ) -> None:
        make_self(store, "s_1", "Fang Yuan")
        make_self(store, "s_2", "Some Other")
        bind_alias(store, "Fang Yuan", "s_1", learned_at=1)
        bind_alias(store, "Gu Master", "s_1", learned_at=1)  # unique, never needed to disambiguate
        bind_alias(store, "Some Other", "s_2", learned_at=1)
        store.conn.commit()

        result = compile_minimal_disclosure(
            store, NOVEL, ["s_1", "s_2"], TaskSpec(task_id="cast_names"), position=100,
        )
        assert "alias:Gu Master" not in result.state.allowed_facts
        assert "alias:Fang Yuan" in result.state.allowed_facts


# ---------------------------------------------------------------------------
# Mirrors TestReincarnation / TestBodySwap (test_state.py:165-247)
# ---------------------------------------------------------------------------


class TestDependencyClosureAcrossBodyChanges:
    def test_a_selected_persona_attribute_pulls_in_its_binding_fact(self, store: Store) -> None:
        make_self(store, "s_fy", "Fang Yuan")
        make_persona(store, "p_body", "current body")
        bind_persona(store, "s_fy", "p_body", start=1)
        bind_alias(store, "Fang Yuan", "s_fy", learned_at=1)
        add_attr(store, "p_body", "hair_colour", "black", kind=TargetKind.PERSONA, learned_at=1)
        store.conn.commit()

        result = compile_minimal_disclosure(
            store, NOVEL, ["s_fy"], TaskSpec(task_id="render"),
            position=50, persona_reader=lambda pid: {"hair_colour": "black"},
        )
        assert entity_ref(TargetKind.PERSONA, "p_body") in result.state.read_set

    def test_a_forbidden_pre_rebirth_body_never_leaks_via_a_shared_dependency_edge(
        self, store: Store
    ) -> None:
        make_self(store, "s_fy", "Fang Yuan")
        make_persona(store, "p_old", "pre-rebirth body")
        make_persona(store, "p_new", "post-rebirth body", chapter=2)
        bind_persona(store, "s_fy", "p_old", start=1, end=2)
        bind_persona(store, "s_fy", "p_new", start=2)
        bind_alias(store, "Fang Yuan", "s_fy", learned_at=1)
        add_attr(store, "p_old", "hair_colour", "grey", kind=TargetKind.PERSONA, learned_at=1)
        store.conn.commit()

        result = compile_minimal_disclosure(
            store, NOVEL, ["s_fy"], TaskSpec(task_id="render"),
            position=50, persona_reader=lambda pid: {},
        )
        assert "attr:hair_colour=grey" not in result.state.allowed_facts


# ---------------------------------------------------------------------------
# MDC-specific: no state_of analog
# ---------------------------------------------------------------------------


class TestGreedySetCoverProperty:
    def test_selecting_two_required_keys_never_pulls_in_a_third_unrequired_attribute(
        self, store: Store
    ) -> None:
        make_self(store, "s_x", "X")
        add_attr(store, "s_x", "role", "hunter", learned_at=1)
        add_attr(store, "s_x", "faction", "Gu Yue clan", learned_at=1)
        add_attr(store, "s_x", "personality", "cautious", learned_at=1)
        store.conn.commit()
        task = TaskSpec(
            task_id="two_keys",
            required_keys={TargetKind.SELF: frozenset({"role", "faction"})},
        )

        result = compile_minimal_disclosure(store, NOVEL, ["s_x"], task, position=50)
        attr_facts = {f for f in result.state.allowed_facts if f.startswith("attr:")}
        assert attr_facts == {"attr:role=hunter", "attr:faction=Gu Yue clan"}

    def test_unsatisfied_required_keys_are_reported_not_silently_dropped(
        self, store: Store
    ) -> None:
        make_self(store, "s_x", "X")
        add_attr(store, "s_x", "role", "hunter", learned_at=1)
        store.conn.commit()
        task = TaskSpec(
            task_id="missing_key",
            required_keys={TargetKind.SELF: frozenset({"role", "cultivation_rank"})},
        )

        result = compile_minimal_disclosure(store, NOVEL, ["s_x"], task, position=50)
        assert result.unsatisfied_keys == ("s_x:cultivation_rank",)


class TestMinimalDisclosureReadSet:
    def test_the_disclosure_read_set_is_a_subset_of_the_candidate_read_set(
        self, store: Store
    ) -> None:
        make_self(store, "s_x", "X")
        make_persona(store, "p_x", "body")
        bind_persona(store, "s_x", "p_x", start=1)
        bind_alias(store, "X", "s_x", learned_at=1)
        add_attr(store, "s_x", "role", "hunter", learned_at=1)
        add_attr(store, "s_x", "faction", "Gu Yue clan", learned_at=1)
        store.conn.commit()

        candidate = compile_generation_state(store, NOVEL, ["s_x"], position=50)
        result = compile_minimal_disclosure(
            store, NOVEL, ["s_x"],
            TaskSpec(task_id="role_only", required_keys={TargetKind.SELF: frozenset({"role"})}),
            position=50,
        )
        assert set(result.state.read_set) <= set(candidate.read_set)
        assert set(result.state.allowed_facts) <= set(candidate.allowed_facts)
        # And in this case strictly smaller: faction was observer-valid but not required.
        assert set(result.state.allowed_facts) < set(candidate.allowed_facts)
