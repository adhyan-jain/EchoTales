"""Look-by-epoch v2 (`persona/looks.py`), with a fake model.

Failures this pins (RI ch1 render v57): the clan head, Fang Zhi and Fang Yuan were drawn from one sentence, Fang Yuan wore the
cliff's torn robes after the rebirth ("his own young and soft, pale palms", block 83), and v1 handed the clan head Fang Yuan's
"a pair of clear eyes" (block 79, the owner is revealed in block 80). No test here depends on a word list in the module:
every decision is driven by the fake model's quoted answers and the store."""

from __future__ import annotations

from types import SimpleNamespace

from echotales.core.enums import Prominence
from echotales.core.models import Chapter, DiscoursePosition, Self
from echotales.core.store import Store
from echotales.pipeline.persona import looks as lk

N = "t"
BLOCKS = [
    "Fang Yuan was in deep green robes that had been torn to shreds. His hair was disheveled and his body was covered in blood.",
    "He had lived over 500 years of his life and he laughed at the enemies around him.",
    "……",
    "The head of the Gu clan prayed in the hall. The head of the Gu clan had a middle-aged appearance and wore white ceremonial robes.",
    "The elders discussed the youth known as Fang Yuan, a boy of great talent.",
    "The head of the Gu clan sighed at the window of the garret.",
    "At the very same moment, a pair of clear eyes quietly looked at the same lights.",
    "Fang Yuan gazed at the lights, then at his own young and soft, pale palms.",
]
CALLS: list[str] = []


class FakeClient:
    """Answers the way a careful model would: quotes copied from the blocks, who a description belongs to chosen by name."""

    def complete(self, task, prompt, schema, *, system="", novel_id="", chapter=None):  # type: ignore[no-untyped-def]
        CALLS.append(schema.__name__)
        if schema is lk.Setting:
            return SimpleNamespace(value=schema(setting="xianxia sect robes", male_garment="robe with wide sleeves",
                                                 female_garment="layered robe dress", colours=["moss green", "slate blue"]))
        if schema is lk.BodyChanges:
            return SimpleNamespace(value=schema(events=[
                {"character": "Fang Yuan", "block": 7, "quote": "his own young and soft, pale palms",
                 "what": "reborn as a youth", "affects": ["everything"]}]))
        if schema is lk.Verdicts:
            owner = "Fang Yuan" if "clear eyes" in prompt and "Claims about Fang Yuan" in prompt else None
            claims = [ln for ln in prompt.split("Claims about")[1].split("\n")[1:] if ln[:1].isdigit()]
            items = []
            for ln in claims:
                n = int(ln.split(".")[0])
                who = "Fang Yuan" if "Fang Yuan" in prompt.split("Claims about")[1].split("\n")[0] else "Head of Gu"
                if "clear eyes" in ln:
                    who = "Fang Yuan"  # block 80 reveals it
                items.append({"id": n, "refers_to": who if owner or who else "unknown", "states_value": True})
            return SimpleNamespace(value=schema(items=items))
        name = prompt.split("\n")[0]
        facts, age = [], {}
        if "Fang Yuan" in name and "[0]" in prompt:
            facts = [
                {"field": "clothes", "value": "deep green robes", "block": 0, "quote": "deep green robes that had been torn"},
                {"field": "condition", "value": "torn to shreds", "block": 0, "quote": "torn to shreds"},
                {"field": "condition", "value": "covered in blood", "block": 0, "quote": "his body was covered in blood"},
                # the value is not in its quote: dropped
                {"field": "eyes", "value": "violet", "block": 1, "quote": "he laughed at the enemies"},
                # the quote is not in the cited block: dropped
                {"field": "hair_colour", "value": "silver", "block": 0, "quote": "silver hair all over"},
            ]
            age = {"age_band": "ageless-ancient", "age_block": 1, "age_quote": "lived over 500 years of his life"}
        if "Fang Yuan" in name and "[7]" in prompt:
            age = {"age_band": "teen", "age_block": 7, "age_quote": "his own young and soft, pale palms"}
            facts = [{"field": "skin", "value": "pale", "block": 7, "quote": "young and soft, pale palms"}]
        if "Head of Gu" in name:
            facts = [
                {"field": "clothes", "value": "white ceremonial robes", "block": 3, "quote": "wore white ceremonial robes"},
                {"field": "eyes", "value": "clear", "block": 6, "quote": "a pair of clear eyes quietly looked"},
            ]
            age = {"age_band": "middle-aged", "age_block": 3, "age_quote": "had a middle-aged appearance"}
        return SimpleNamespace(value=schema(present=True, facts=facts, **age))


def _store(tmp_path):  # type: ignore[no-untyped-def]
    s = Store(str(tmp_path / "t.db"))
    s.add_novel(N, "T", "x.epub", "generic")
    s.add_chapter(Chapter(novel_id=N, number=1.0, title="c", source_href="a", blocks=[
        {"index": i, "block_type": "PROSE", "text": t} for i, t in enumerate(BLOCKS)]))
    for sid, label in (("self:fy", "Fang Yuan"), ("title:hd", "Head of Gu")):
        s.add_self(Self(id=f"{N}:{sid}", novel_id=N, canonical_label=label,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0), prominence=Prominence.INCIDENTAL))
    return s


def test_one_person_gets_a_different_look_before_and_after_the_rebirth(tmp_path) -> None:
    s = _store(tmp_path)
    cliff = lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0, client=FakeClient())
    reborn = lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=7, client=FakeClient())
    assert cliff.look_id != reborn.look_id
    assert cliff.age_band == "ageless-ancient" and reborn.age_band == "teen"
    assert "deep green robes" in cliff.description and "torn to shreds" in cliff.condition
    assert "covered in blood" in cliff.condition
    # the cliff's clothes and wounds do not follow him into the reborn epoch
    assert "green robes" not in reborn.outfit and not reborn.condition
    assert reborn.fact("clothes").invented and reborn.fact("clothes").reason  # type: ignore[union-attr]
    assert "robe with wide sleeves" in reborn.outfit  # garment from the novel's setting read, not a genre flag
    assert reborn.fact("age_band").quote == "his own young and soft, pale palms"  # type: ignore[union-attr]
    s.close()


def test_a_value_its_quote_does_not_support_or_a_quote_not_in_the_block_is_dropped(tmp_path) -> None:
    s = _store(tmp_path)
    cliff = lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0, client=FakeClient())
    assert "violet" not in cliff.description and cliff.fact("eyes") is None
    assert cliff.fact("hair_colour") is None and cliff.fact("hair").invented  # type: ignore[union-attr]
    s.close()


def test_a_description_whose_owner_is_named_in_the_next_block_is_not_the_clan_heads(tmp_path) -> None:
    """RI blocks 79-80: 'a pair of clear eyes' is Fang Yuan's, revealed one block later. v1 gave it to the clan head."""
    s = _store(tmp_path)
    head = lk.look_at(s, N, f"{N}:title:hd", chapter=1.0, block=3, client=FakeClient())
    assert head.fact("eyes") is None and "clear" not in head.description
    assert head.age_band == "middle-aged" and "white ceremonial robes" in head.outfit
    s.close()


def test_the_mention_table_decides_attribution_before_any_model(tmp_path) -> None:
    s = _store(tmp_path)
    ctx = lk._Ctx(s, None, N, f"{N}:title:hd", 1.0, "Head of Gu", ["Gu Clan Head"], {},
                  mentions={4: [(0, f"{N}:self:fy")], 5: [(0, f"{N}:title:hd"), (40, f"{N}:self:fy")]})
    assert lk.graph_attribution(ctx, 4, 30) is False   # the nearest person before the quote is someone else
    assert lk.graph_attribution(ctx, 5, 20) is True
    assert lk.graph_attribution(ctx, 5, 60) is False
    assert lk.graph_attribution(ctx, 3, 10) is None    # no mention in that block: ask the model
    s.close()


def test_quotes_match_after_normalising_case_space_and_punctuation() -> None:
    text = "His hair was “disheveled”,  and his body\nwas covered in blood."
    assert lk.find_quote(text, "DISHEVELED and his body was covered") is not None
    assert lk.find_quote(text, "covered in violet") is None
    assert lk.find_quote(text, "blood") is None  # one word is not a quote


def test_the_model_is_asked_once_and_a_second_look_reads_the_cache(tmp_path) -> None:
    s = _store(tmp_path)
    CALLS.clear()
    lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0, client=FakeClient())
    first = len(CALLS)
    lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=7, client=None)  # the image pass has no client
    assert first >= 1 and len(CALLS) == first
    s.close()


def test_a_look_built_without_any_model_read_is_not_cached_and_flags_everything(tmp_path) -> None:
    s = _store(tmp_path)
    look = lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0)
    assert s.conn.execute("SELECT COUNT(*) FROM derived_artifact WHERE id LIKE 'look_epochs2:%'").fetchone()[0] == 0
    assert look.fact("age_band").invented  # type: ignore[union-attr]
    assert all(f.invented for f in look.facts if f.field in ("clothes", "build", "face"))
    s.close()


def test_scene_cut_module_results_are_used_when_present(tmp_path, monkeypatch) -> None:
    s = _store(tmp_path)
    fake = SimpleNamespace(load_scene_cuts=lambda store, nid, ch: SimpleNamespace(cuts=[SimpleNamespace(block=4)]))
    monkeypatch.setattr(lk.importlib, "import_module", lambda name: fake)
    cuts, src = lk.scene_cut_blocks(s, N, 1.0, [])
    assert cuts == {4} and src == "scene-cut module"
    monkeypatch.undo()
    cuts, src = lk.scene_cut_blocks(s, N, 1.0, s.get_chapter(N, 1.0).blocks)
    assert cuts == {3} and src == "break-shaped blocks"
    s.close()


def test_people_with_no_evidence_never_share_their_invented_look(tmp_path) -> None:
    s = Store(str(tmp_path / "u.db"))
    s.add_novel(N, "T", "x.epub", "generic")
    ids = [f"{N}:self:{i}" for i in range(12)]
    for i in ids:
        s.add_self(Self(id=i, novel_id=N, canonical_label=f"Person {i[-2:]}",
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0), prominence=Prominence.INCIDENTAL))
    slots = [lk._slot_for(s, N, i) for i in ids]
    for a in range(len(slots)):
        for b in range(a + 1, len(slots)):
            assert sum(x != y for x, y in zip(slots[a], slots[b], strict=True)) >= 3
    assert lk._slot_for(s, N, ids[0]) == slots[0]  # stable once stored
    s.close()


def test_position_inverts_the_story_position(tmp_path) -> None:
    s = _store(tmp_path)
    assert lk.position_to_block(s, N, 1 + 4 / len(BLOCKS)) == (1.0, 4)
    assert lk.position_to_block(s, N, 9.5) is None
    s.close()
