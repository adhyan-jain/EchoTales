"""Look-by-epoch (`persona/looks.py`).

Failures this pins (RI ch1 render v57): the Gu Yue clan head, Fang Zhi and Fang Yuan were drawn from one sentence ("a man
with long black hair tied up in a topknot with a hairpin ... an adult face"), and Fang Yuan wore the cliff's torn robes in the
hall 500 years earlier and after the rebirth ("his own young and soft, pale palms", block 83)."""

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
    "The head of the clan prayed in the hall. The head of the clan had a middle-aged appearance and wore white ceremonial robes.",
    "The elders discussed the youth known as Fang Yuan, a boy of great talent.",
    "Fang Yuan gazed at the lights, then at his own young and soft, pale palms.",
]
CALLS: list[str] = []


class FakeClient:
    """Answers per character the way a careful model would, and counts calls."""

    def complete(self, task, prompt, schema, *, system="", novel_id="", chapter=None):  # type: ignore[no-untyped-def]
        CALLS.append(prompt)
        name = prompt.split("\n")[0]
        facts = []
        if "Fang Yuan" in name and "[0]" in prompt:
            facts = [{"field": "clothes", "value": "deep green robes", "block": 0},
                     {"field": "condition", "value": "torn to shreds", "block": 0},
                     {"field": "condition", "value": "covered in blood", "block": 0},
                     {"field": "hair_colour", "value": "disheveled", "block": 0},
                     # not in the text at all: must be dropped by the grounding check
                     {"field": "eyes", "value": "violet", "block": 1}]
        value = schema(present=True, facts=facts)
        return SimpleNamespace(value=value)


def _store(tmp_path):  # type: ignore[no-untyped-def]
    s = Store(str(tmp_path / "t.db"))
    s.add_novel(N, "T", "x.epub", "generic")
    s.add_chapter(Chapter(novel_id=N, number=1.0, title="c", source_href="a", blocks=[
        {"index": i, "block_type": "PROSE", "text": t} for i, t in enumerate(BLOCKS)]))
    for sid, label in (("fy", "Fang Yuan"), ("hd", "Gu Clan Head")):
        s.add_self(Self(id=f"{N}:self:{sid}", novel_id=N, canonical_label=label,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0), prominence=Prominence.INCIDENTAL))
    return s


def test_one_person_gets_a_different_look_before_and_after_the_rebirth(tmp_path) -> None:
    s = _store(tmp_path)
    cliff = lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0, client=FakeClient())
    reborn = lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=5, client=FakeClient())
    assert cliff.look_id != reborn.look_id
    assert cliff.age_band == "ageless-ancient" and reborn.age_band == "teen"
    assert "deep green robes" in cliff.description and "torn to shreds" in cliff.description
    assert "covered in blood" in cliff.condition and "disheveled hair" in cliff.condition
    # the cliff's clothes and wounds do not follow him into the reborn epoch
    assert "green" not in reborn.outfit and not reborn.condition
    assert reborn.fact("clothes").invented and reborn.fact("clothes").reason  # type: ignore[union-attr]
    s.close()


def test_a_value_the_cited_block_does_not_hold_is_dropped(tmp_path) -> None:
    s = _store(tmp_path)
    cliff = lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0, client=FakeClient())
    assert "violet" not in cliff.description
    assert cliff.fact("eyes") is None
    s.close()


def test_stated_age_cues_are_read_without_a_model(tmp_path) -> None:
    s = _store(tmp_path)
    head = lk.look_at(s, N, f"{N}:self:hd", chapter=1.0, block=3)
    assert lk.age_cue("his own young and soft, pale palms") == "teen"
    assert lk.age_cue("had lived over 500 years of his life") == "ageless-ancient"
    assert lk.age_cue('"500 years of experience, it really feels like a dream"') == ""
    assert head.look_id.startswith(f"{N}:self:hd")
    s.close()


def test_the_model_is_asked_once_per_window_and_a_second_look_reads_the_cache(tmp_path) -> None:
    s = _store(tmp_path)
    CALLS.clear()
    lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0, client=FakeClient())
    first = len(CALLS)
    lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=5, client=None)  # the image pass has no client
    assert first >= 1 and len(CALLS) == first
    s.close()


def test_a_look_built_without_any_model_read_is_not_cached(tmp_path) -> None:
    s = _store(tmp_path)
    lk.look_at(s, N, f"{N}:self:fy", chapter=1.0, block=0)
    assert s.conn.execute("SELECT COUNT(*) FROM derived_artifact WHERE id LIKE 'look_epochs:%'").fetchone()[0] == 0
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


def test_a_state_word_is_not_a_hair_colour() -> None:
    assert lk._clean("hair_colour", "disheveled") == ""
    assert lk._clean("build", "deathly pale") == ""
    assert lk._clean("condition", "kneeling on the floor") == ""
    assert lk._clean("condition", "torn to shreds") == "torn to shreds"
