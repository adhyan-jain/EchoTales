"""Read-set-derived cache invalidation, tested as a controlled experiment.

The claim (disclosure P6): a render artifact's cache key is derived from the
graph facts the plan consulted, so a state change invalidates exactly the
artifacts that depended on it. That has two halves, and both must hold:

  - a change to a character **in** the panel's cast changes the key;
  - a change to a character **not** in the cast leaves it alone.

The second half is what separates this from "any change busts every cache".

**A limit this test pins rather than hides.** `plan_builder.state_digest`
hashes persona ids and attributes, *not* aliases. So a reveal that only adds a
name does not invalidate a cached panel. `test_alias_change_is_not_in_the_read_set`
records that as current behaviour; if it is changed, that test should be
updated deliberately, not deleted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from echotales.core.enums import OBSERVER_READER, AliasType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    DiscoursePosition,
    Persona,
    Self,
    SelfPersonaBinding,
)
from echotales.core.store import Store
from echotales.pipeline.render.cache_key import compute_render_cache_key
from echotales.pipeline.render.contract import GenerationRequest
from echotales.pipeline.render.panels import PanelImageRequest
from echotales.pipeline.render.plan_builder import build_render_plan

NOVEL = "t"
OPEN = FuzzyInterval.open_ended(1, last_evidence=1e6)
AT1 = DiscoursePosition(chapter=1)


def _character(store: Store, sid: str, label: str) -> None:
    store.add_self(Self(id=sid, novel_id=NOVEL, canonical_label=label, first_attested_pos=AT1))
    store.add_persona(Persona(id=f"{sid}:body1", novel_id=NOVEL, body_label=label, first_attested_pos=AT1))
    store.add_self_persona_binding(
        SelfPersonaBinding(self_id=sid, persona_id=f"{sid}:body1", interval=OPEN,
                           learned_at_pos=AT1, observer_id=OBSERVER_READER)
    )


def _attr(store: Store, sid: str, key: str, value: str) -> None:
    store.add_attribute(NOVEL, Attribute(target_kind=TargetKind.SELF, target_id=sid, key=key,
                                         value=value, interval=OPEN, learned_at_pos=AT1,
                                         observer_id=OBSERVER_READER))
    store.conn.commit()


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(str(tmp_path / "t.db"))
    s.add_novel(NOVEL, "T", "x.epub", "generic")
    _character(s, "cast", "Bai Ning Bing")
    _character(s, "offstage", "Gu Yue Yao Ji")
    s.conn.commit()
    return s


def _key(store: Store) -> str:
    plan = build_render_plan(store, NOVEL, chapter=5.0, beat_id="b1", panel_seq=1,
                             cast_self_ids=["cast"], lead_self_id="cast")
    request = GenerationRequest(
        base=PanelImageRequest(prompt="a scene", out_path=Path("/tmp/x.png"), seed=0),
        backend_name="noobai", steps=30, guidance_scale=7.0,
    )
    return compute_render_cache_key(plan, request)


def test_the_key_is_stable_when_nothing_changes(store: Store) -> None:
    assert _key(store) == _key(store)


def test_a_change_to_a_cast_character_invalidates(store: Store) -> None:
    before = _key(store)
    _attr(store, "cast", "hair", "white")
    assert _key(store) != before


def test_a_change_to_an_offstage_character_does_not(store: Store) -> None:
    """The half that makes this precise invalidation rather than cache-busting."""
    before = _key(store)
    _attr(store, "offstage", "hair", "black")
    assert _key(store) == before


def test_a_new_body_for_a_cast_character_invalidates(store: Store) -> None:
    before = _key(store)
    store.add_persona(Persona(id="cast:body2", novel_id=NOVEL, body_label="new body",
                              first_attested_pos=AT1))
    store.add_self_persona_binding(
        SelfPersonaBinding(self_id="cast", persona_id="cast:body2", interval=OPEN,
                           learned_at_pos=AT1, observer_id=OBSERVER_READER)
    )
    store.conn.commit()
    assert _key(store) != before


def test_alias_change_is_not_in_the_read_set(store: Store) -> None:
    """Current behaviour, pinned: aliases are not hashed into state_digest."""
    before = _key(store)
    store.add_alias_binding(NOVEL, AliasBinding(
        alias="the White Demon", alias_type=AliasType.EPITHET, target_kind=TargetKind.SELF,
        target_id="cast", interval=OPEN, learned_at_pos=AT1, observer_id=OBSERVER_READER))
    store.conn.commit()
    assert _key(store) == before
