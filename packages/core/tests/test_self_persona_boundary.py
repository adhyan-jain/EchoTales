"""Core Pipeline Hardening #10: a direct, named property test of
non-negotiable #3 (Self is not Persona) -- a `Self`'s continuity-of-
consciousness facts and each of its bodies' `Persona`-scoped facts must
never merge, even across a reincarnation/body-swap boundary on the *same*
Self. Previously this invariant only held as an implicit side effect of the
reincarnation `persona_ids` tests in `test_state.py`; nothing asserted it
for `Attribute` rows directly.
"""

from __future__ import annotations

from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    Attribute,
    DiscoursePosition,
    Persona,
    Self,
    SelfPersonaBinding,
)
from echotales.core.state import StateResolver
from echotales.core.store import Store

NOVEL = "boundary-test"


def _store() -> Store:
    s = Store(":memory:")
    s.add_novel(NOVEL, "Test Novel", "data/raw/test.epub", "test")
    return s


def _write_attribute(
    store: Store, *, target_kind: TargetKind, target_id: str, key: str, value: str, chapter: int
) -> None:
    store.add_attribute(
        NOVEL,
        Attribute(
            target_kind=target_kind,
            target_id=target_id,
            key=key,
            value=value,
            interval=FuzzyInterval.open_ended(chapter, last_evidence=1e6),
            learned_at_pos=DiscoursePosition(chapter=chapter),
            observer_id=OBSERVER_READER,
        ),
    )


def _reincarnation_store() -> tuple[Store, StateResolver]:
    """One Self ("The Traveller"), two Personas bound sequentially at the
    same swap point `TestReincarnation` in test_state.py uses (chapter 100),
    each body given its own, distinct hair_color attribute."""
    store = _store()
    store.add_self(
        Self(
            id="s_soul",
            novel_id=NOVEL,
            canonical_label="The Traveller",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_persona(
        Persona(
            id="p_old",
            novel_id=NOVEL,
            body_label="original body",
            first_attested_pos=DiscoursePosition(chapter=1),
        )
    )
    store.add_persona(
        Persona(
            id="p_new",
            novel_id=NOVEL,
            body_label="reborn body",
            first_attested_pos=DiscoursePosition(chapter=100),
        )
    )
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
    # Body-scoped facts: each persona's own hair colour, never the other's.
    _write_attribute(
        store, target_kind=TargetKind.PERSONA, target_id="p_old",
        key="hair_color", value="black", chapter=1,
    )
    _write_attribute(
        store, target_kind=TargetKind.PERSONA, target_id="p_new",
        key="hair_color", value="silver", chapter=100,
    )
    # A Self-scoped fact (a role/title), which belongs to neither body.
    _write_attribute(
        store, target_kind=TargetKind.SELF, target_id="s_soul",
        key="role", value="wandering scholar", chapter=1,
    )
    store.conn.commit()
    return store, StateResolver(store, NOVEL)


class TestPersonaAttributesNeverCrossBodies:
    def test_old_body_never_reports_new_bodys_attribute(self) -> None:
        _, resolver = _reincarnation_store()
        result = resolver.state_of("p_old", target_kind=TargetKind.PERSONA, position=50)
        assert result.attributes.get("hair_color") == "black"

    def test_new_body_never_reports_old_bodys_attribute(self) -> None:
        _, resolver = _reincarnation_store()
        result = resolver.state_of("p_new", target_kind=TargetKind.PERSONA, position=300)
        assert result.attributes.get("hair_color") == "silver"

    def test_old_bodys_query_has_no_trace_of_new_bodys_value_at_any_position(self) -> None:
        """The direct leak check: query p_old at a position *after* the
        swap (where p_new is the story-current body) -- p_old's own
        attribute row must still read back as p_old's, never p_new's,
        because a Persona's attributes are keyed by persona_id, not by
        "whichever body is current for this Self right now"."""
        _, resolver = _reincarnation_store()
        result = resolver.state_of("p_old", target_kind=TargetKind.PERSONA, position=300)
        assert result.attributes.get("hair_color") == "black"
        assert result.attributes.get("hair_color") != "silver"


class TestSelfAttributesNeverAbsorbPersonaAttributes:
    """The other direction of the same boundary: a Self-level fact and its
    bodies' Persona-level facts occupy disjoint namespaces even though they
    share one continuity of consciousness."""

    def test_self_level_query_never_returns_either_bodys_hair_color(self) -> None:
        _, resolver = _reincarnation_store()
        result = resolver.state_of("s_soul", position=300)
        assert "hair_color" not in result.attributes
        assert result.attributes.get("role") == "wandering scholar"

    def test_persona_level_query_never_returns_the_selfs_role(self) -> None:
        _, resolver = _reincarnation_store()
        for persona_id, position in (("p_old", 50), ("p_new", 300)):
            result = resolver.state_of(
                persona_id, target_kind=TargetKind.PERSONA, position=position
            )
            assert "role" not in result.attributes
