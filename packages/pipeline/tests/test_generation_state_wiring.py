"""`GenerationState` as the single source for the image path.

The chain under test, in both directions:

    state change -> GenerationState changes -> the prompt's persona/appearance
    changes -> the cache key changes (dependent artifact invalidates)

    unrelated change -> GenerationState.digest() unchanged -> same key
    (unaffected artifact stays reusable)

`test_readset_invalidation.py` pins the key-level behaviour; this file pins the
new guarantees: the prompt and the key are derived from ONE compiled state at
the panel's own in-chapter position (they used to come from two `state_of()`
calls at two positions), the digest hashes only what the image path consumes,
and the state serialises deterministically.

Audio and reels are deliberately not tested here: neither has a state-dependent
input to consume (see the note in `voice/runner.py`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    Attribute,
    DiscoursePosition,
    Persona,
    Relation,
    Self,
    SelfPersonaBinding,
)
from echotales.core.state import GenerationState
from echotales.core.store import Store
from echotales.pipeline.render.cache_key import compute_render_cache_key
from echotales.pipeline.render.contract import GenerationRequest
from echotales.pipeline.render.panels import PanelImageRequest, character_looks
from echotales.pipeline.render.plan_builder import build_render_plan, compile_render_state

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


def _persona_attr(store: Store, persona_id: str, key: str, value: str, *, from_chapter: int = 1) -> None:
    store.add_attribute(NOVEL, Attribute(
        target_kind=TargetKind.PERSONA, target_id=persona_id, key=key, value=value,
        interval=FuzzyInterval.open_ended(from_chapter, last_evidence=1e6),
        learned_at_pos=DiscoursePosition(chapter=from_chapter), observer_id=OBSERVER_READER))
    store.conn.commit()


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(str(tmp_path / "t.db"))
    s.add_novel(NOVEL, "T", "x.epub", "generic")
    _character(s, "cast", "Bai Ning Bing")
    _character(s, "other", "Gu Yue Yao Ji")
    _character(s, "offstage", "Ren Zu")
    _persona_attr(s, "cast:body1", "hair_color", "black")
    return s


def _state(store: Store, ids=("cast",), position: float = 5.0) -> GenerationState:
    return compile_render_state(store, NOVEL, list(ids), position=position)


def _key(store: Store, *, position: float = 5.0, prompt: str = "a scene") -> str:
    plan = build_render_plan(store, NOVEL, chapter=5.0, beat_id="b1", panel_seq=1,
                             cast_self_ids=["cast"], lead_self_id="cast", position=position)
    request = GenerationRequest(
        base=PanelImageRequest(prompt=prompt, out_path=Path("/tmp/x.png"), seed=0),
        backend_name="noobai", steps=30, guidance_scale=7.0,
    )
    return compute_render_cache_key(plan, request)


def _looks(store: Store, state: GenerationState | None, position: float = 5.0):
    return character_looks(store, "cast", novel_id="", chapter=position, gen_state=state)


# ---- state change -> state -> generation input -> key -----------------------


def test_an_appearance_change_flows_from_state_to_prompt_to_key(store: Store) -> None:
    before_state, before_key = _state(store), _key(store)
    assert "silver" not in _looks(store, before_state)[1]

    _persona_attr(store, "cast:body1", "hair_color", "silver", from_chapter=2)

    after_state = _state(store)
    assert after_state.digest() != before_state.digest()  # the state changed
    assert dict(after_state.target("cast").persona_attributes[0][1])["hair_color"] == "silver"
    assert "silver" in _looks(store, after_state)[1]  # the generation input changed
    assert _key(store) != before_key  # the dependent artifact invalidates


def test_the_prompt_reads_the_compiled_state_not_the_store(store: Store) -> None:
    """Handing `character_looks` a state is what makes the state the source:
    a state compiled before an edit keeps producing the pre-edit prompt."""
    stale = _state(store)
    _persona_attr(store, "cast:body1", "hair_color", "silver", from_chapter=2)
    assert "silver" not in _looks(store, stale)[1]
    assert "silver" in _looks(store, None)[1]  # no state -> the direct path, unchanged


def test_with_and_without_a_state_the_prompt_inputs_are_identical(store: Store) -> None:
    """Existing behaviour is unchanged when no new constraint applies."""
    _persona_attr(store, "cast:body1", "eye_color", "amber")
    assert _looks(store, _state(store)) == _looks(store, None)


# ---- unrelated change -> nothing invalidates --------------------------------


def _unchanged_after(store: Store, mutate) -> None:
    state, key, clause = _state(store), _key(store), _looks(store, _state(store))[1]
    mutate()
    assert _state(store).digest() == state.digest()
    assert _key(store) == key
    assert _looks(store, _state(store))[1] == clause


def test_a_new_relationship_does_not_invalidate(store: Store) -> None:
    """Relationships are not an input to the image prompt, so they are in the
    state's audit lists but not in the dependency set that is hashed."""
    def mutate() -> None:
        store.add_relation(NOVEL, Relation(
            src_self="cast", dst_self="other", type="rival", interval=OPEN,
            learned_at_pos=AT1, observer_id=OBSERVER_READER))
        store.conn.commit()
    _unchanged_after(store, mutate)


def test_an_attribute_revealed_after_the_panel_does_not_invalidate(store: Store) -> None:
    """A scar the text discloses at chapter 100 is not part of a chapter 5 panel."""
    _unchanged_after(
        store,
        lambda: _persona_attr(store, "cast:body1", "distinguishing_features", "a scar", from_chapter=100),
    )


def test_a_standing_fact_revealed_after_the_panel_does_not_invalidate(store: Store) -> None:
    _unchanged_after(store, lambda: _persona_attr(store, "cast:body1", "gender", "female", from_chapter=100))


def test_a_drawn_fact_outside_the_appearance_keys_still_invalidates(store: Store) -> None:
    """The prompt reads more than appearance (gender for the count tags, attire
    under an older key). Hashing only appearance keys let A7's attire change
    through with an unchanged key: 23 stale reuses in the 2026-09-27 re-run."""
    before = _key(store)
    _persona_attr(store, "cast:body1", "attire", "silver armour")
    assert _key(store) != before
    _persona_attr(store, "cast:body1", "gender", "female")
    assert _key(store) != before


def test_changing_only_the_observer_does_not_change_the_digest(store: Store) -> None:
    """Two observers who see the same drawn state must share a key; the
    observer id itself must not bust the cache (A7 E4: 30 extra renders)."""
    from echotales.core.enums import OBSERVER_SYSTEM

    reader = compile_render_state(store, NOVEL, ["cast"], position=5.0)
    system = compile_render_state(store, NOVEL, ["cast"], position=5.0, observer_id=OBSERVER_SYSTEM)
    assert reader.observer_id != system.observer_id
    assert reader.target("cast") == system.target("cast")
    assert reader.digest() == system.digest()


def test_an_appearance_change_on_an_undrawn_character_does_not_invalidate(store: Store) -> None:
    _unchanged_after(store, lambda: _persona_attr(store, "offstage:body1", "hair_color", "red"))


def test_a_character_outside_the_cast_does_not_change_the_state(store: Store) -> None:
    before = _state(store, ["cast"]).digest()
    _persona_attr(store, "other:body1", "hair_color", "white")
    assert _state(store, ["cast"]).digest() == before
    assert _state(store, ["cast", "other"]).digest() != before


# ---- one state, one position ------------------------------------------------


def test_the_plan_and_the_prompt_agree_on_a_mid_chapter_body_change(store: Store) -> None:
    """A rebirth partway through chapter 5: the prompt is built at the fractional
    in-chapter position, so the plan (and its cache key) must resolve there too.
    Before, the plan resolved at the chapter start and hashed the old body into
    the key of a panel drawn from the new one."""
    store.add_persona(Persona(id="cast:body2", novel_id=NOVEL, body_label="reborn", first_attested_pos=AT1))
    store.add_self_persona_binding(SelfPersonaBinding(
        self_id="cast", persona_id="cast:body2", interval=FuzzyInterval.open_ended(5.5, last_evidence=1e6),
        learned_at_pos=DiscoursePosition(chapter=5), observer_id=OBSERVER_READER))
    store.conn.commit()

    late = _state(store, position=5.8)
    assert _state(store, position=5.2).persona_for("cast") == "cast:body1"
    # Concurrent bindings are legitimate and the first bound persona is the drawn one;
    # the point is that the plan reads the same state the prompt does.
    plan = build_render_plan(store, NOVEL, chapter=5.0, beat_id="b", panel_seq=1, cast_self_ids=["cast"],
                             position=5.8, gen_state=late)
    assert plan.characters[0].persona_id == late.persona_for("cast")
    assert plan.state_digest == late.digest()
    assert late.digest() != _state(store, position=5.2).digest()
    assert _key(store, position=5.2) != _key(store, position=5.8)


def test_the_default_position_is_still_the_chapter_start(store: Store) -> None:
    plan = build_render_plan(store, NOVEL, chapter=5.0, beat_id="b", panel_seq=1, cast_self_ids=["cast"])
    assert plan.state_digest == _state(store, position=5.0).digest()


def test_a_state_that_does_not_cover_the_cast_is_recompiled(store: Store) -> None:
    plan = build_render_plan(store, NOVEL, chapter=5.0, beat_id="b", panel_seq=1,
                             cast_self_ids=["cast", "other"], gen_state=_state(store, ["cast"]))
    assert {c.self_id for c in plan.characters} == {"cast", "other"}
    assert plan.state_digest == _state(store, ["cast", "other"]).digest()


# ---- determinism and serialisation ------------------------------------------


def test_the_state_is_deterministic_and_order_independent(store: Store) -> None:
    a, b = _state(store, ["cast", "other"]), _state(store, ["other", "cast"])
    assert a == b
    assert a.digest() == b.digest()
    assert a.to_json() == b.to_json()


def test_the_state_round_trips_through_json(store: Store) -> None:
    import json

    state = _state(store, ["cast", "other"])
    restored = GenerationState.from_dict(json.loads(state.to_json()))
    assert restored == state
    assert restored.digest() == state.digest()
    assert restored.persona_for("cast") == "cast:body1"


def test_the_read_set_lists_exactly_what_was_consumed(store: Store) -> None:
    refs = set(_state(store).read_set)
    assert {"self:cast", "persona:cast:body1", "attr:cast:body1:hair_color:black"} <= refs
    assert not any(r.startswith("alias:") for r in refs)  # not consulted by the image path
    assert not any("other" in r or "offstage" in r for r in refs)
