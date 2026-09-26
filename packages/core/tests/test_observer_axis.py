"""`state_of(observer=X)` must differ from `state_of(observer=READER)`.

This is `docs/design/architecture.md`'s headline acceptance test and it could not pass
until 2026-09-23 (EVOLUTION 4.80) -- not because the query was wrong, but
because nothing ever wrote an observation. Every fact this pipeline produces
is stamped `READER`, so a character scope matched nothing and a character
observer got an **empty** result. Empty is a different claim from smaller:
"the Wu clan knows less than the reader" and "we have no idea what the Wu clan
knows" are not the same sentence, and only one of them is the contribution.
"""

from __future__ import annotations

import pytest
from echotales.core.enums import (
    OBSERVER_READER,
    OBSERVER_SYSTEM,
    AliasType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import AliasBinding, DiscoursePosition, Observation, Self
from echotales.core.readset import observable_ref
from echotales.core.state import StateResolver
from echotales.core.store import Store

WITNESS = "n:self:witness"
ABSENTEE = "n:self:absentee"
TARGET = "n:self:target"


def _binding(alias: str, *, learned: int) -> AliasBinding:
    return AliasBinding(
        alias=alias,
        alias_type=AliasType.RIGID_NAME,
        target_kind=TargetKind.SELF,
        target_id=TARGET,
        interval=FuzzyInterval(from_lb=0, from_ub=0, to_lb=10**6, to_ub=10**6),
        learned_at_pos=DiscoursePosition(chapter=learned),
        observer_id=OBSERVER_READER,
    )


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    s = Store(str(tmp_path / "o.db"))
    s.add_novel("n", "N", "", "")
    for entity_id, label in ((TARGET, "Target"), (WITNESS, "Witness"), (ABSENTEE, "Absentee")):
        s.add_self(
            Self(
                id=entity_id,
                novel_id="n",
                canonical_label=label,
                first_attested_pos=DiscoursePosition(chapter=1),
            )
        )
    s.add_alias_binding("n", _binding("True Name", learned=5))
    s.add_alias_binding("n", _binding("Public Name", learned=1))
    s.conn.commit()
    yield s
    s.close()


class TestObserverScoping:
    def test_reader_sees_everything_narrated(self, store) -> None:  # type: ignore[no-untyped-def]
        result = StateResolver(store, "n").state_of(TARGET, position=100)
        assert set(result.aliases) == {"True Name", "Public Name"}

    def test_a_character_with_no_observations_sees_nothing(self, store) -> None:  # type: ignore[no-untyped-def]
        """Correct, and the exact state every shipped database was in. It is
        why this had to be measured rather than assumed to work."""
        result = StateResolver(store, "n").state_of(TARGET, position=100, observer_id=ABSENTEE)
        assert result.aliases == []

    def test_a_witness_sees_strictly_less_than_the_reader(self, store) -> None:  # type: ignore[no-untyped-def]
        """The acceptance test itself: smaller, not empty, and a subset."""
        store.add_observation(
            Observation(
                observer_id=WITNESS,
                fact_ref=observable_ref(_binding("Public Name", learned=1)),
                learned_at_pos=DiscoursePosition(chapter=1),
            )
        )
        store.conn.commit()
        resolver = StateResolver(store, "n")
        reader = set(resolver.state_of(TARGET, position=100).aliases)
        witness = set(resolver.state_of(TARGET, position=100, observer_id=WITNESS).aliases)
        assert witness == {"Public Name"}
        assert witness < reader

    def test_a_witness_does_not_know_before_they_witnessed_it(self, store) -> None:  # type: ignore[no-untyped-def]
        """Knowledge time is the observer's, not the narrator's -- the two
        diverging is the whole point of the axis."""
        store.add_observation(
            Observation(
                observer_id=WITNESS,
                fact_ref=observable_ref(_binding("True Name", learned=5)),
                learned_at_pos=DiscoursePosition(chapter=80),
            )
        )
        store.conn.commit()
        resolver = StateResolver(store, "n")
        early = resolver.state_of(
            TARGET, position=50, knowledge_pos=DiscoursePosition(chapter=50),
            observer_id=WITNESS,
        )
        late = resolver.state_of(
            TARGET, position=100, knowledge_pos=DiscoursePosition(chapter=100),
            observer_id=WITNESS,
        )
        assert early.aliases == []
        assert late.aliases == ["True Name"]

    def test_one_fact_one_identity_visibility_varies(self, store) -> None:  # type: ignore[no-untyped-def]
        """The invention-disclosure centrepiece in one assertion chain
        (scripts/eval/observer_evidence.py is the real-data twin): the SAME fact
        about the SAME Self is read by every observer -- its reference is
        derived from the fact, not a row id -- and only what is *visible*
        differs, by observer and by when they ask from."""
        fact = _binding("True Name", learned=5)
        ref = observable_ref(fact)
        store.add_observation(
            Observation(observer_id=WITNESS, fact_ref=ref,
                        learned_at_pos=DiscoursePosition(chapter=80))
        )
        store.conn.commit()
        resolver = StateResolver(store, "n")

        def ask(observer: str, known_from: int) -> tuple[str, list[str], list[str]]:
            r = resolver.state_of(TARGET, position=100, observer_id=observer,
                                  knowledge_pos=DiscoursePosition(chapter=known_from))
            return r.target_id, r.aliases, r.read_set

        reader = ask(OBSERVER_READER, 100)
        witness_after = ask(WITNESS, 100)
        witness_before = ask(WITNESS, 50)
        absentee = ask(ABSENTEE, 100)

        assert {reader[0], witness_after[0], witness_before[0], absentee[0]} == {TARGET}
        # Two fact-derived keys, neither a row id: the observation key is
        # scoped to the Self (`observable_ref`); the read-set key used for
        # cache invalidation is scoped to the novel (`alias_ref`). Both
        # observers who can see the fact record the same read-set key.
        assert ref == "alias:n:self:target:true name"
        assert "alias:n:true name" in reader[2] and "alias:n:true name" in witness_after[2]
        assert "alias:n:true name" not in absentee[2]
        assert "True Name" in reader[1]
        assert witness_after[1] == ["True Name"]
        assert witness_before[1] == []
        assert absentee[1] == []
        # Re-deriving the reference from a freshly built copy of the fact gives
        # the same key, which is what lets observations survive a re-resolve.
        assert observable_ref(_binding("True Name", learned=5)) == ref

    def test_system_still_sees_everything(self, store) -> None:  # type: ignore[no-untyped-def]
        """SYSTEM is the evaluation oracle and must not be affected."""
        result = StateResolver(store, "n").state_of(
            TARGET, position=100, observer_id=OBSERVER_SYSTEM
        )
        assert set(result.aliases) == {"True Name", "Public Name"}

    def test_the_resolver_default_observer_is_used_when_none_is_passed(self, store) -> None:  # type: ignore[no-untyped-def]
        """What makes `render --observer` work without threading the id
        through every `state_of` call site below the CLI."""
        resolver = StateResolver(store, "n", default_observer=ABSENTEE)
        assert resolver.state_of(TARGET, position=100).aliases == []
        assert resolver.state_of(
            TARGET, position=100, observer_id=OBSERVER_READER
        ).aliases


class TestObservationStore:
    def test_the_earliest_witnessing_wins(self, store) -> None:  # type: ignore[no-untyped-def]
        """Knowledge time only moves forward: re-witnessing must not push an
        observer's knowledge later than when they first learned it."""
        ref = "alias:n:self:target:true name"
        store.add_observation(
            Observation(observer_id=WITNESS, fact_ref=ref,
                        learned_at_pos=DiscoursePosition(chapter=10))
        )
        store.add_observation(
            Observation(observer_id=WITNESS, fact_ref=ref,
                        learned_at_pos=DiscoursePosition(chapter=90))
        )
        store.conn.commit()
        assert store.observations_for(WITNESS)[ref].chapter == 10

    def test_observations_are_per_observer(self, store) -> None:  # type: ignore[no-untyped-def]
        store.add_observation(
            Observation(observer_id=WITNESS, fact_ref="x",
                        learned_at_pos=DiscoursePosition(chapter=1))
        )
        store.conn.commit()
        assert store.observations_for(ABSENTEE) == {}
        assert store.observers() == [WITNESS]


class TestObservableRef:
    def test_an_alias_ref_is_stable_across_renderings(self) -> None:
        """A ref derived from row ids would reset every character's knowledge
        on every re-resolve."""
        assert observable_ref(_binding("True  NAME", learned=5)) == observable_ref(
            _binding("true name", learned=99)
        )

    def test_a_ref_ignores_when_and_how_the_fact_is_held(self) -> None:
        """Witnessing an event is not undone by a later interval refinement."""
        a = _binding("True Name", learned=5)
        b = _binding("True Name", learned=5)
        b.truth_status = TruthStatus.FALSE
        b.interval = FuzzyInterval(from_lb=3, from_ub=3, to_lb=4, to_ub=4)
        assert observable_ref(a) == observable_ref(b)
