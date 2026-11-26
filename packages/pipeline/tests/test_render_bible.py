from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    Attribute,
    DiscoursePosition,
    Persona,
    Self,
    SelfPersonaBinding,
    TargetKind,
)
from echotales.core.store import Store
from echotales.pipeline.render.bible import build_volume_bible


def test_build_volume_bible():
    store = Store(":memory:")
    pos = DiscoursePosition(chapter=1, offset=0)

    # 1. Add self
    store.add_self(Self(id="fang_yuan", novel_id="test-novel", canonical_label="Fang Yuan", first_attested_pos=pos))

    # 2. Add two personas
    store.add_persona(Persona(id="fang_yuan:old", novel_id="test-novel", body_label="Elder Body", first_attested_pos=pos))
    store.add_persona(Persona(id="fang_yuan:youth", novel_id="test-novel", body_label="Youth Body", first_attested_pos=pos))

    # 3. Add bindings
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="fang_yuan",
            persona_id="fang_yuan:old",
            interval=FuzzyInterval.point_known(1.0, 1.5),
            learned_at_pos=pos,
            observer_id="READER",
        )
    )
    store.add_self_persona_binding(
        SelfPersonaBinding(
            self_id="fang_yuan",
            persona_id="fang_yuan:youth",
            interval=FuzzyInterval.point_known(1.5, 20.0),
            learned_at_pos=pos,
            observer_id="READER",
        )
    )

    # 4. Add attributes
    store.add_attribute(
        "test-novel",
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="fang_yuan:old",
            key="hair",
            value="long white hair",
            interval=FuzzyInterval.point_known(1.0, 1.5),
            learned_at_pos=pos,
            observer_id="READER",
        ),
    )
    store.add_attribute(
        "test-novel",
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id="fang_yuan:youth",
            key="hair",
            value="short black hair",
            interval=FuzzyInterval.point_known(1.5, 20.0),
            learned_at_pos=pos,
            observer_id="READER",
        ),
    )

    # Build bible
    bible = build_volume_bible(store, "test-novel")
    assert "fang_yuan" in bible.epochs_by_self
    assert len(bible.epochs_by_self["fang_yuan"]) == 2

    # Query look at chapter 1 vs chapter 2
    look_cliff = bible.get_look_at("fang_yuan", DiscoursePosition(chapter=1, offset=10))
    assert look_cliff is not None
    assert look_cliff.persona_id == "fang_yuan:old"
    assert look_cliff.hair_desc == "long white hair"

    look_academy = bible.get_look_at("fang_yuan", DiscoursePosition(chapter=2, offset=10))
    assert look_academy is not None
    assert look_academy.persona_id == "fang_yuan:youth"
    assert look_academy.hair_desc == "short black hair"
