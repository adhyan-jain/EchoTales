"""A character sheet image per character per appearance interval, drawn from the locked identity and approved in the Studio.

The approved sheet's description is what gets locked: approving a sheet in the Studio must change what every later panel
of that interval says, and the Studio must show the words."""

from __future__ import annotations

from echotales.core.enums import TargetKind
from echotales.core.models import DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.persona import identity_lock as il
from echotales.pipeline.persona import identity_sheet as sheets
from echotales.pipeline.persona import refimg


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("n", "N", "x.epub", "generic")
    store.add_self(Self(id="s1", novel_id="n", canonical_label="Fang Yuan",
                        first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.conn.commit()
    return store


def _draw(tmp_path):
    seen = []

    def draw(requests, sections, model_key, *, greyscale):  # noqa: ANN001
        (request,) = requests
        seen.append((request.prompt, sections, greyscale))
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        request.out_path.write_bytes(b"\x89PNG-sheet" + str(len(seen)).encode())
        return []

    draw.seen = seen
    return draw


def test_the_sheet_is_drawn_from_the_locked_identity_and_registered_with_its_words(tmp_path) -> None:
    store = _store(tmp_path)
    draw = _draw(tmp_path)
    cand = sheets.generate_sheet(store, "n", "s1", out_dir=tmp_path / "ref", draw=draw, model_key="z-image-turbo")
    prompt = draw.seen[0][0]
    assert "Fang Yuan" in prompt and "plain" in prompt.lower(), "a plain-background reference, not a scene"
    assert cand.role == "sheet" and cand.persona_id == "s1:body1" and not cand.selected
    assert sheets.sheet_description(store, cand.id).startswith("Fang Yuan is a")
    assert sheets.sheet_description(store, cand.id) in prompt
    store.close()


def test_approving_the_sheet_locks_its_description_for_the_panels(tmp_path) -> None:
    store = _store(tmp_path)
    cand = sheets.generate_sheet(store, "n", "s1", out_dir=tmp_path / "ref", draw=_draw(tmp_path), model_key="z-image-turbo")
    before = il.approved_sheet_lock(store, "n", "s1:body1")
    assert before is None, "an unapproved sheet locks nothing"
    refimg.approve_sheet(store, "n", "s1", cand.id)
    after = il.approved_sheet_lock(store, "n", "s1:body1")
    assert after is not None and after.outfit and after.hair
    # a panel's lock now carries exactly the approved words, whatever the defaults would say
    got = il.lock_for(store, "n", "s1", "s1:body1", facts={"hair_color": "red"}, gender="male", young=False,
                      name="Fang Yuan", manhua=True)
    assert (got.hair, got.outfit) == (after.hair, after.outfit)
    store.close()


def test_regenerating_a_sheet_keeps_the_same_words_and_a_new_candidate(tmp_path) -> None:
    store = _store(tmp_path)
    draw = _draw(tmp_path)
    a = sheets.generate_sheet(store, "n", "s1", out_dir=tmp_path / "ref", draw=draw, model_key="z-image-turbo")
    b = sheets.generate_sheet(store, "n", "s1", out_dir=tmp_path / "ref", draw=draw, model_key="z-image-turbo")
    assert a.id != b.id and sheets.sheet_description(store, a.id) == sheets.sheet_description(store, b.id)
    assert len(refimg.list_sheets(store, "n", "s1", persona_id="s1:body1")) == 2
    store.close()


def test_a_sheet_per_body_for_a_character_who_changes_body(tmp_path) -> None:
    from echotales.core.interval import FuzzyInterval
    from echotales.core.models import Persona, SelfPersonaBinding

    store = _store(tmp_path)
    for i, (a, b) in enumerate(((1.0, 1.9), (1.9, None)), start=1):
        pid = f"s1:body{i}"
        store.add_persona(Persona(id=pid, novel_id="n", body_label=f"b{i}", first_attested_pos=DiscoursePosition(chapter=float(int(a)), offset=0)))
        store.add_self_persona_binding(SelfPersonaBinding(
            self_id="s1", persona_id=pid, interval=FuzzyInterval.point_known(a, b) if b else FuzzyInterval.open_ended(a, last_evidence=a),
            learned_at_pos=DiscoursePosition(chapter=1, offset=0), observer_id="READER"))
    store.conn.commit()
    made = sheets.generate_sheets(store, "n", self_ids=["s1"], out_dir=tmp_path / "ref", draw=_draw(tmp_path), model_key="z-image-turbo")
    assert sorted(c.persona_id for c in made) == ["s1:body1", "s1:body2"]
    store.close()
