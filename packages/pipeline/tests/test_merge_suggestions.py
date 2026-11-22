"""Likely-same-person pairs reach the review queue as suggestions (P&P e2e 2026-11-22, defect 11).

After a real run the queue had 0 items although Lizzy and Elizabeth were separate entities and so were Miss Bennet and
Jane; the reviewer had to find them by reading the cast list. These become `merge_suggestion` items: never an automatic
merge (non-negotiable 9, precision over recall), only a bounded list for a person to decide. Synthetic names, the
same shapes as the book.
"""

from __future__ import annotations

from echotales.core.enums import AliasType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.resolve import merge_suggest

NOVEL = "t"


def _store(people: dict[str, str], appearances: list[tuple[str, float, int]]) -> Store:
    """`people` maps entity id -> label; `appearances` lists (entity id, chapter, block) mentions."""
    store = Store(":memory:")
    store.add_novel(NOVEL, "T", "x.epub", "generic")
    for i, (sid, label) in enumerate(people.items()):
        store.add_self(
            Self(id=sid, novel_id=NOVEL, canonical_label=label, kind=TargetKind.SELF,
                 first_attested_pos=DiscoursePosition(chapter=1, offset=i))
        )
    store.add_mentions(
        [
            Mention(
                id=f"m{i}", novel_id=NOVEL, segment_id="s", chapter=ch, offset=0, block_index=block,
                text=people[sid], alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=sid,
            )
            for i, (sid, ch, block) in enumerate(appearances)
        ]
    )
    store.conn.commit()
    return store


def _items(store: Store):
    return [i for i in store.list_review_items(NOVEL) if i.kind == merge_suggestion_kind()]


def merge_suggestion_kind() -> str:
    return merge_suggest.KIND


def _pairs(store: Store) -> set[frozenset[str]]:
    out = set()
    for item in _items(store):
        group = item.candidates[0]
        for c in item.candidates[1:]:
            out.add(frozenset({group["from_id"], c["target_id"]}))
    return out


def test_a_diminutive_of_a_given_name_is_suggested() -> None:
    store = _store(
        {"t:eliz": "Elizabeth", "t:lizzy": "Lizzy"},
        [("t:eliz", 3, 0), ("t:eliz", 3, 1), ("t:lizzy", 2, 4), ("t:lizzy", 3, 7)],
    )
    merge_suggest.sync(store, NOVEL)
    assert _pairs(store) == {frozenset({"t:eliz", "t:lizzy"})}


def test_nothing_is_merged_by_the_suggestion() -> None:
    store = _store({"t:eliz": "Elizabeth", "t:lizzy": "Lizzy"}, [("t:eliz", 3, 0), ("t:lizzy", 2, 4)])
    merge_suggest.sync(store, NOVEL)
    assert {m.target_id for m in store.get_mentions(NOVEL)} == {"t:eliz", "t:lizzy"}
    assert {e.id for e in store.all_selves(NOVEL)} == {"t:eliz", "t:lizzy"}
    assert store.merged_into(NOVEL) == {}


def test_two_names_in_one_paragraph_are_two_people() -> None:
    """"Elizabeth smiled at Lizzy": the author is telling them apart."""
    store = _store({"t:eliz": "Elizabeth", "t:lizzy": "Lizzy"}, [("t:eliz", 3, 5), ("t:lizzy", 3, 5)])
    merge_suggest.sync(store, NOVEL)
    assert _items(store) == []


def test_unrelated_given_names_are_not_suggested() -> None:
    store = _store(
        {"t:a": "Anna", "t:b": "Maria", "t:c": "Mary", "t:d": "Jane"},
        [("t:a", 1, 0), ("t:b", 1, 1), ("t:c", 2, 0), ("t:d", 2, 1)],
    )
    merge_suggest.sync(store, NOVEL)
    # Maria and Mary are different people in the book this was taken from; a suggestion is allowed, a merge is not
    assert frozenset({"t:a", "t:b"}) not in _pairs(store)
    assert frozenset({"t:a", "t:d"}) not in _pairs(store)


def test_different_surnames_block_a_diminutive_match() -> None:
    store = _store({"t:a": "Elizabeth Bennet", "t:b": "Lizzy Lucas"}, [("t:a", 1, 0), ("t:b", 2, 0)])
    merge_suggest.sync(store, NOVEL)
    assert _items(store) == []


def test_title_and_surname_suggests_the_family_members_who_share_the_surname() -> None:
    store = _store(
        {"t:mr": "Mr. Bennet", "t:mrs": "Mrs. Bennet", "t:miss": "Miss Bennet", "t:jane": "Jane", "t:eliz": "Elizabeth",
         "t:bing": "Bingley"},
        [("t:mr", 1, 0), ("t:mrs", 1, 1), ("t:jane", 1, 2), ("t:jane", 3, 1), ("t:eliz", 1, 3), ("t:eliz", 3, 2),
         ("t:miss", 3, 6), ("t:bing", 3, 8)],
    )
    merge_suggest.sync(store, NOVEL)
    pairs = _pairs(store)
    assert frozenset({"t:miss", "t:jane"}) in pairs
    assert frozenset({"t:miss", "t:eliz"}) in pairs
    # the parents and the unrelated man are never candidates for "Miss Bennet"
    assert not any({"t:mr", "t:mrs", "t:bing"} & set(p) and "t:miss" in p for p in pairs)


def test_a_title_with_no_known_family_member_suggests_nothing() -> None:
    store = _store({"t:miss": "Miss Kay", "t:jane": "Jane"}, [("t:miss", 1, 0), ("t:jane", 1, 1)])
    merge_suggest.sync(store, NOVEL)
    assert _items(store) == []


def test_a_reviewer_decision_survives_a_rerun_and_a_merged_pair_closes() -> None:
    store = _store({"t:eliz": "Elizabeth", "t:lizzy": "Lizzy"}, [("t:eliz", 3, 0), ("t:lizzy", 2, 4)])
    merge_suggest.sync(store, NOVEL)
    (item,) = _items(store)
    store.resolve_review_item(item.id, "human:dismiss")
    merge_suggest.sync(store, NOVEL)
    (again,) = _items(store)
    assert again.resolved and again.resolution == "human:dismiss"
    assert len(_items(store)) == 1


def test_a_pair_that_was_merged_afterwards_is_closed_automatically() -> None:
    from echotales.core.enums import EventType
    from echotales.core.models import ResolutionEvent

    store = _store({"t:eliz": "Elizabeth", "t:lizzy": "Lizzy"}, [("t:eliz", 3, 0), ("t:lizzy", 2, 4)])
    merge_suggest.sync(store, NOVEL)
    store.append_event(
        ResolutionEvent(
            id="e1", seq=store.next_seq(), type=EventType.MERGE, payload={"from_id": "t:lizzy", "into_id": "t:eliz"},
            cause_pos=DiscoursePosition(chapter=0, offset=0),
        )
    )
    store.conn.commit()
    merge_suggest.sync(store, NOVEL)
    (item,) = _items(store)
    assert item.resolved and item.resolution.startswith("auto:")


def test_sync_twice_does_not_duplicate() -> None:
    store = _store({"t:eliz": "Elizabeth", "t:lizzy": "Lizzy"}, [("t:eliz", 3, 0), ("t:lizzy", 2, 4)])
    merge_suggest.sync(store, NOVEL)
    merge_suggest.sync(store, NOVEL)
    assert len(_items(store)) == 1
