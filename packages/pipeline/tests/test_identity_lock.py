"""Locked identity: one wording per character per appearance interval, early in every Z-Image prompt.

Failures this pins (Opus review of the 2026-11-20 round-2 sheets): RI's lead changed robe colour and hair style inside one
13-panel scene; the scene text's "deep green robes ... torn to shreds" never reached the prompt; LotM's lead got a genre
default (brown hair) because the graph had no hair fact, in 16 of 16 panels."""

from __future__ import annotations

import json

from echotales.core.store import Store
from echotales.pipeline.persona import identity_lock as il
from echotales.pipeline.render.compiler import (
    CharacterBrief,
    OutputMode,
    PanelBrief,
    compile_prompt,
    identity_sentence,
    model_profile,
)

FACTS = {"hair_color": "black", "eye_color": "dark brown"}


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    return store


def _lock(store, **over):
    args = dict(novel_id="t", self_id="t:self:1", persona_id="t:self:1:body1", facts=FACTS, gender="male", young=False,
                name="Fang Yuan", manhua=True)
    args.update(over)
    return il.lock_for(store, **args)


def test_a_fact_free_character_gets_one_outfit_and_hair_style_for_good(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    first = _lock(store)
    # The table is changed after the first panel: the stored choice must still win, never a re-roll.
    monkeypatch.setattr(il, "_COLOURS", ("white",))
    monkeypatch.setitem(il._HAIR_DEFAULTS, (True, "male"), (("short", "cropped"),))
    second = _lock(store)
    assert first.outfit == second.outfit and first.hair == second.hair
    assert first.source["outfit"] == "default" and "black hair" in first.hair
    store.close()


def test_defaults_are_a_pure_function_of_the_self_id() -> None:
    assert il.choose_defaults("a", "male", True) == il.choose_defaults("a", "male", True)
    colours = {il.choose_defaults(f"self{i}", "male", True)["outfit_colour"] for i in range(30)}
    assert len(colours) > 1, "different characters are not all dressed alike"


def test_text_facts_beat_defaults_and_say_where_they_came_from() -> None:
    d = il.choose_defaults("s", "male", True)
    lock = il.build_lock("p", {**FACTS, "hair_style": "long hair loose to the waist", "typical_attire": "grey robes",
                               "height_build": "lean"}, d)
    assert lock.hair == "black long hair loose to the waist" or "loose to the waist" in lock.hair
    assert lock.outfit == "grey robes" and lock.build == "a lean build"
    assert lock.source["outfit"] == "text" and lock.source["hair"] == "text"
    assert lock.eyes == "dark brown eyes"


def test_the_scene_text_changes_outfit_and_adds_the_stated_state_only_for_that_scene() -> None:
    d = il.choose_defaults("s", "male", True)
    base = il.build_lock("p", {**FACTS, "typical_attire": "black robes"}, d)
    scene = il.build_lock("p", {**FACTS, "typical_attire": "black robes"}, d, scene_outfit="deep green robes",
                          scene_state="robes torn to shreds, hair disheveled, blood on the face")
    assert "deep green robes" in scene.description() and "torn to shreds" in scene.description()
    assert "green" not in base.description() and base.state == ""
    assert scene.hair == base.hair, "hair style stays the interval's own"


def test_an_approved_sheet_decides_the_locked_wording() -> None:
    d = il.choose_defaults("s", "male", True)
    sheet = il.LockedIdentity("p", hair="short white hair", eyes="amber eyes", build="a broad build", outfit="a red cloak")
    lock = il.build_lock("p", FACTS, d, sheet=sheet, scene_state="soaked by rain")
    assert (lock.hair, lock.eyes, lock.build, lock.outfit) == ("short white hair", "amber eyes", "a broad build", "a red cloak")
    assert lock.state == "soaked by rain" and lock.source["hair"] == "sheet"


def test_the_sheet_is_read_back_from_the_store_when_approved(tmp_path) -> None:
    store = _store(tmp_path)
    store.conn.execute(
        "INSERT INTO ref_image_candidate(id, novel_id, self_id, character_label, source_url, thumbnail_url, title,"
        " source_page, query, backend, found_at, user_uploaded, selected, persona_id, role)"
        " VALUES ('p:sheet:abc','t','t:self:1','Fang Yuan','file:///x.png','','','','','generated-sheet',1,0,1,"
        "'t:self:1:body1','sheet')")
    sheet = il.LockedIdentity("t:self:1:body1", hair="short white hair", eyes="amber eyes", build="a broad build",
                              outfit="a red cloak")
    store.record_artifact("identity_sheet:p:sheet:abc", il.TIER, [], "", sheet.to_json())
    store.conn.commit()
    assert _lock(store).outfit == "a red cloak"
    store.close()


class _Client:
    """Answers the look task like a model: returns what it was given, and counts calls."""

    def __init__(self, look: il.CharacterLook) -> None:
        self.look, self.calls = look, 0

    def complete(self, task, prompt, schema, **kw):
        self.calls += 1
        return type("R", (), {"value": self.look})()


SCENE = "Fang Yuan was in deep green robes that had been torn to shreds. His hair was disheveled. Blood ran down his face."


def test_a_scene_look_is_asked_once_stored_and_read_without_a_client(tmp_path) -> None:
    store = _store(tmp_path)
    client = _Client(il.CharacterLook(outfit="deep green robes", condition="robes torn to shreds, hair disheveled"))
    ctx = il.SceneContext("1:0", SCENE, client, "t")
    first = _lock(store, scene=ctx)
    again = _lock(store, scene=ctx)
    image_pass = _lock(store, scene=il.SceneContext("1:0", SCENE, None, "t"))
    assert client.calls == 1
    assert first.outfit == again.outfit == image_pass.outfit == "deep green robes"
    assert "torn to shreds" in image_pass.state
    store.close()


def _put_look(store, persona, key, **look) -> None:
    store.record_artifact(f"identity_look:{persona}:{key}", il.TIER, [], "", json.dumps(
        {"outfit": "", "hair": "", "condition": "", **look}))
    store.conn.commit()


def test_clothes_stated_in_a_later_scene_dress_the_earlier_ones_and_wounds_only_carry_forward(tmp_path) -> None:
    # RI ch1: scenes at blocks 0 and 1 (the shouted ultimatum) state no clothes; the scene at block 5 says deep green robes
    # torn to shreds; the scene at block 27 states nothing. One body in one continuous hour is one outfit, so scene 0 is
    # not drawn in a default charcoal robe while scene 5 is green; the tearing is a state that begins where it is stated.
    store = _store(tmp_path)
    p = "t:self:1:body1"
    _put_look(store, p, "1:0")
    _put_look(store, p, "1:5", outfit="deep green robes", condition="robes torn to shreds, blood on the body")
    _put_look(store, p, "1:27")
    for key, outfit, state in (("1:0", "deep green robes", ""), ("1:5", "deep green robes", "torn to shreds"),
                               ("1:27", "deep green robes", "torn to shreds")):
        lock = _lock(store, scene=il.SceneContext(key, SCENE, None, "t"))
        assert lock.outfit == outfit, key
        assert (state in lock.state) if state else lock.state == "", key
    store.close()


def test_another_chapter_or_another_body_does_not_lend_its_clothes(tmp_path) -> None:
    store = _store(tmp_path)
    _put_look(store, "t:self:1:body1", "2:0", outfit="a white nightgown")
    _put_look(store, "t:self:1:body2", "1:3", outfit="a red cloak")
    _put_look(store, "t:self:1:body1", "1:0")
    lock = _lock(store, scene=il.SceneContext("1:0", SCENE, None, "t"))
    assert "nightgown" not in lock.outfit and "cloak" not in lock.outfit and lock.source["outfit"] == "default"
    store.close()


def test_a_look_the_text_does_not_support_is_dropped(tmp_path) -> None:
    store = _store(tmp_path)
    client = _Client(il.CharacterLook(outfit="a white silk gown", condition="blood on the face"))
    lock = _lock(store, scene=il.SceneContext("1:9", SCENE, client, "t"))
    assert "gown" not in lock.description() and "blood" in lock.state
    store.close()


def test_no_client_and_nothing_stored_leaves_the_base_identity(tmp_path) -> None:
    store = _store(tmp_path)
    assert _lock(store, scene=il.SceneContext("1:0", SCENE, None, "t")).state == ""
    store.close()


# --- the compiler: the lock is the identity sentence, and it comes early -------------------------------------------------


def _brief(locked) -> PanelBrief:
    c = CharacterBrief(name="Fang Yuan", gender="male", age_band="adult", appearance=FACTS, lead=True, locked=locked)
    return PanelBrief(novel_id="", characters=[c], mode=OutputMode.COLOUR,
                      composition="A wide shot on a cliff. Fang Yuan stands alone, his face calm.",
                      staging="Set: a bare rock cliff. Blocking: Fang Yuan stands alone. Light: dusk.")


def test_the_locked_sentence_replaces_the_graph_only_sentence() -> None:
    lock = il.build_lock("p", FACTS, il.choose_defaults("s", "male", True), scene_outfit="deep green robes",
                         scene_state="robes torn to shreds")
    c = CharacterBrief(name="Fang Yuan", gender="male", age_band="adult", appearance=FACTS, locked=lock)
    s = identity_sentence(c)
    assert s.startswith("Fang Yuan is a man with ") and "black" in s and "hair" in s
    assert "deep green robes" in s and "torn to shreds" in s and "dark brown eyes" in s
    assert identity_sentence(CharacterBrief(name="Fang Yuan", gender="male", age_band="adult", appearance=FACTS)) != s


def test_the_identity_sentence_comes_straight_after_the_style_lead_before_staging_and_composition() -> None:
    lock = il.build_lock("p", FACTS, il.choose_defaults("s", "male", True))
    out = compile_prompt(_brief(lock), model_profile("z-image-turbo"))
    labels = [s.label for s in out.sections]
    assert labels[:2] == ["style", "character:Fang Yuan"]
    assert labels.index("character:Fang Yuan") < labels.index("staging") < labels.index("composition")


def _graph_store(tmp_path, with_hair: bool):
    from echotales.core.enums import AssertedBy, TruthStatus
    from echotales.core.interval import FuzzyInterval
    from echotales.core.models import Attribute, DiscoursePosition, Persona, Self

    store = Store(str(tmp_path / "g.db"))
    store.add_novel("lord-of-the-mysteries", "L", "x.epub", "generic")
    store.add_self(Self(id="s1", novel_id="lord-of-the-mysteries", canonical_label="Zhou Mingrui",
                        first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind="SELF"))
    store.add_persona(Persona(id="s1:body1", novel_id="lord-of-the-mysteries", body_label="b",
                              first_attested_pos=DiscoursePosition(chapter=1.0, offset=0)))
    if with_hair:
        for key, value in (("hair_color", "black"), ("eye_color", "brown")):
            store.add_attribute("lord-of-the-mysteries", Attribute(
                target_kind="PERSONA", target_id="s1:body1", key=key, value=value,
                interval=FuzzyInterval.open_ended(1.0, last_evidence=1.0), learned_at_pos=DiscoursePosition(chapter=1, offset=0),
                observer_id="READER", asserted_by=AssertedBy.NARRATOR, truth_status=TruthStatus.TRUE))
    store.conn.commit()
    return store


def test_a_graph_fact_beats_the_genre_default_and_the_default_is_the_fallback(tmp_path, monkeypatch) -> None:
    # LotM: the text says "Black hair, brown eyes"; the genre default is brown hair and grey eyes.
    from echotales.pipeline.persona import genre
    from echotales.pipeline.render.compiler import character_brief

    monkeypatch.setitem(genre._PROJECT_GENRE, "lord-of-the-mysteries", "victorian_gothic")

    (tmp_path / "a").mkdir()
    stated = character_brief(_graph_store(tmp_path / "a", True), "lord-of-the-mysteries", "s1", 1.5)
    assert "black" in stated.locked.hair and stated.locked.eyes == "brown eyes"
    assert stated.locked.source["hair"] == "text+default" and stated.locked.source["eyes"] == "text"
    (tmp_path / "b").mkdir()
    silent = character_brief(_graph_store(tmp_path / "b", False), "lord-of-the-mysteries", "s1", 1.5)
    assert "brown" in silent.locked.hair and silent.locked.source["hair"] == "default"


def test_a_character_without_a_lock_is_early_too() -> None:
    out = compile_prompt(_brief(None), model_profile("z-image-turbo"))
    assert [s.label for s in out.sections][:2] == ["style", "character:Fang Yuan"]
