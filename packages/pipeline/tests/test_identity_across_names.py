"""One character, several names: the three ways the resolver split people.

Each case is a real failure measured on 2026-09-27:
- RI: "the clan head" in chapter 1 is Gu Yue Bo, named from chapter 6; all 36
  clan-head/leader mentions in the volume were unresolved.
- LOTM: "Klein Moretti" then "Klein" split in two, because name containment
  assumed family-name-first order (Dunn, Audrey and Alger split the same way).
- LOTM: the transmigrated protagonist, Zhou Mingrui, and the body's name,
  Klein Moretti, were separate people.
Each test also pins the precision guard that keeps the fix from merging
people who really are different.
"""

from __future__ import annotations

from pathlib import Path

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import name_containment
from echotales.pipeline.resolve.title_holders import link_title_holders
from echotales.pipeline.resolve.transmigration import merge_transmigrations

N = "t"


def _store(tmp_path: Path, chapters: list[list[str]], people: list[str]) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel(N, "T", "x.epub", "generic")
    for i, blocks in enumerate(chapters, start=1):
        store.add_chapter(Chapter(novel_id=N, number=float(i), title=str(i), source_href=f"{i}.html",
                                  blocks=[Block(index=j, block_type=BlockType.PROSE, text=t)
                                          for j, t in enumerate(blocks)]))
    for p in people:
        store.add_self(Self(id=f"{N}:{p}", novel_id=N, canonical_label=p,
                            first_attested_pos=DiscoursePosition(chapter=1)))
    store.conn.commit()
    return store


def _mention(store: Store, chapter: int, block: int, surface: str, *, target: str | None = None,
             alias_type: AliasType = AliasType.TRANSFERABLE_TITLE) -> str:
    text = store.get_chapter(N, float(chapter)).blocks[block].text
    mid = f"m{chapter}-{block}-{text.index(surface)}"
    store.add_mentions([Mention(
        id=mid, novel_id=N, segment_id="s", chapter=float(chapter), offset=text.index(surface),
        block_index=block, text=surface, alias_type=alias_type, span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF if target else None,
        target_id=f"{N}:{target}" if target else None)])
    store.conn.commit()
    return mid


def _target(store: Store, mid: str) -> str | None:
    return next(m.target_id for m in store.get_mentions(N) if m.id == mid)


# ---- name order ------------------------------------------------------------


def test_a_western_given_name_links_to_the_full_name() -> None:
    assert name_containment("Klein", "Klein Moretti", ambiguous_tokens=frozenset(), given_name_first=True) > 0.8
    assert name_containment("Klein", "Klein Moretti", ambiguous_tokens=frozenset()) == 0.0  # the old order


def test_a_bare_surname_still_merges_no_one() -> None:
    """"Moretti" is the family (Melissa, Benson, Klein), never one person."""
    assert name_containment("Moretti", "Klein Moretti", ambiguous_tokens=frozenset(), given_name_first=True) == 0.0


def test_family_first_order_is_unchanged() -> None:
    assert name_containment("Mo Bei", "Gu Yue Mo Bei", ambiguous_tokens=frozenset()) > 0.8
    assert name_containment("Gu Yue", "Gu Yue Mo Bei", ambiguous_tokens=frozenset()) == 0.0


# ---- title holders -----------------------------------------------------------

CLAN = [
    ["The clan head looked out of the window."],
    ['"Whoever objects goes against me, Gu Yue Bo!" The Gu Yue clan head roared.'],
    ["Clan leader Gu Yue Bo nodded slowly."],
    ["The fourth generation clan head was a hero of the village."],
    ["The Xiong clan leader laughed.", "Xiong clan leader stepped forward.", "Xiong clan leader left."],
    ["It was the clan leader, Gu Yue Bo, who spoke first."],
]


def test_a_title_used_before_the_name_is_given_links_to_the_holder(tmp_path: Path) -> None:
    store = _store(tmp_path, CLAN, ["Gu Yue Bo"])
    early = _mention(store, 1, 0, "The clan head")
    report = link_title_holders(store, N)
    assert _target(store, early) == f"{N}:Gu Yue Bo"
    assert report.linked >= 1


def test_a_historical_holder_is_not_the_current_one(tmp_path: Path) -> None:
    store = _store(tmp_path, CLAN, ["Gu Yue Bo"])
    ancestor = _mention(store, 4, 0, "clan head")
    link_title_holders(store, N)
    assert _target(store, ancestor) is None


def test_another_clans_head_gets_one_identity_of_its_own(tmp_path: Path) -> None:
    store = _store(tmp_path, CLAN, ["Gu Yue Bo"])
    xiong = [_mention(store, 5, i, "Xiong clan leader") for i in range(3)]
    link_title_holders(store, N)
    targets = {_target(store, m) for m in xiong}
    assert len(targets) == 1 and None not in targets
    assert f"{N}:Gu Yue Bo" not in targets


def test_a_title_with_one_declaration_is_not_enough(tmp_path: Path) -> None:
    store = _store(tmp_path, [CLAN[0], CLAN[2]], ["Gu Yue Bo"])  # a single declaration
    early = _mention(store, 1, 0, "The clan head")
    link_title_holders(store, N)
    assert _target(store, early) is None


# ---- transmigration ----------------------------------------------------------

TRANSMIGRATION = [
    ["Could I have transmigrated? Zhou Mingrui thought, staring at the mirror.",
     "Zhou Mingrui had a rough idea how Klein had died."],
    ["Before his transmigration, Zhou Mingrui had been an office worker.",
     "Zhou Mingrui sorted through Klein's memories of the university."],
    ['"Klein, buy bread," Melissa said.', "Klein Moretti walked to the market."],
]


def test_the_transmigrator_and_the_bodys_name_are_one_person(tmp_path: Path) -> None:
    store = _store(tmp_path, TRANSMIGRATION, ["Zhou Mingrui", "Klein", "Klein Moretti", "Melissa"])
    klein = _mention(store, 3, 0, "Klein", target="Klein", alias_type=AliasType.RIGID_NAME)
    full = _mention(store, 3, 1, "Klein Moretti", target="Klein Moretti", alias_type=AliasType.RIGID_NAME)
    melissa = _mention(store, 3, 0, "Melissa", target="Melissa", alias_type=AliasType.RIGID_NAME)
    report = merge_transmigrations(store, N)
    assert _target(store, klein) == _target(store, full) == f"{N}:Zhou Mingrui"
    assert _target(store, melissa) == f"{N}:Melissa"  # a family member is never absorbed
    assert report.merges


def test_remembering_someone_is_not_transmigration(tmp_path: Path) -> None:
    """Possession evidence alone ("Klein's memories") without any
    transmigration cue must not merge: mourning is not becoming."""
    chapters = [["Zhou Mingrui thought about Klein's memories of home.",
                 "Zhou Mingrui wondered how Klein had died."]]
    store = _store(tmp_path, chapters, ["Zhou Mingrui", "Klein"])
    klein = _mention(store, 1, 0, "Klein", target="Klein", alias_type=AliasType.RIGID_NAME)
    assert not merge_transmigrations(store, N).merges
    assert _target(store, klein) == f"{N}:Klein"
