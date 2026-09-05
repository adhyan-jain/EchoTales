"""Section 5.1/5.2/5.3 of the 2026-09-05 root-cause remediation pass.

Non-negotiable #4 (bare role titles never become mentions) was correct for
preventing false surface-similarity matches, but Section 1.2's recall@k gate
measured the cost: recall@10 on TRANSFERABLE_TITLE/RELATIONAL_DEICTIC is 0%
against real hard-case gold, and HANDOFF names the concrete failure -- the
clan leader in RI ch1 blocks 68-78, who appears alone, speaking, and
currently produces an empty cast.

The fix lets these alias types become mentions, but they resolve only
through relationship constraints (here: "who is the sole entity already
established as physically present"), never through surface similarity, and
never found a new entity on their own. These tests exercise that mechanism
end to end through the real `resolve_novel`, not a unit test of one function
in isolation -- `test_clan_prefix_resolve.py` and
`test_lotm_transmigration_resolve.py` set the precedent for this file's
shape.
"""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, Decision, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.resolve import resolve_novel


def _chapter(number: float, text: str) -> Chapter:
    return Chapter(
        novel_id="t",
        number=number,
        title="T",
        source_href=f"{number}.html",
        blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
    )


def _mention(
    mid: str,
    text: str,
    *,
    chapter: float,
    group: str,
    offset: int = 0,
    alias_type: AliasType = AliasType.RIGID_NAME,
    reference_mode: ReferenceMode = ReferenceMode.PRESENT,
) -> Mention:
    return Mention(
        id=mid,
        novel_id="t",
        segment_id="s",
        chapter=chapter,
        offset=offset,
        text=text,
        alias_type=alias_type,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=reference_mode,
        block_index=0,
        local_group_id=group,
    )


class TestSoleCoPresentTitleResolution:
    def test_title_links_to_the_only_other_present_named_entity(self) -> None:
        """The clan-leader-alone case: one named entity present, one bare
        title referring to nobody else -- the title must resolve to that
        entity, not sit unresolved with an empty cast."""
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(
            _chapter(1.0, "Gu Yue Tie stood before the hall. The clan head spoke sternly.")
        )
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Tie", chapter=1.0, group="g1", offset=0),
                _mention(
                    "m2",
                    "the clan head",
                    chapter=1.0,
                    group="g2",
                    offset=30,
                    alias_type=AliasType.TRANSFERABLE_TITLE,
                ),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)

        named = next(m for m in store.get_mentions("t", 1.0) if m.text == "Gu Yue Tie")
        title = next(m for m in store.get_mentions("t", 1.0) if m.text == "the clan head")
        assert named.target_id is not None
        assert title.target_id == named.target_id

    def test_title_never_founds_a_new_entity_alone(self) -> None:
        """No other named, present entity anywhere in the chapter -- the
        title must defer, never mint its own entity keyed to a role."""
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(_chapter(1.0, "The clan head spoke sternly to no one in particular."))
        store.add_mentions(
            [
                _mention(
                    "m1",
                    "the clan head",
                    chapter=1.0,
                    group="g1",
                    alias_type=AliasType.TRANSFERABLE_TITLE,
                ),
            ]
        )
        store.conn.commit()

        report = resolve_novel("t", store)

        title = next(m for m in store.get_mentions("t", 1.0) if m.text == "the clan head")
        assert title.target_id is None
        assert report.deictic_only == 1

    def test_two_rival_present_entities_defer_rather_than_guess(self) -> None:
        """Section 5.3's six-Wang guard: two named, present candidates that
        the title could plausibly denote must never be force-linked to
        either one -- ambiguity defers, it does not pick a side."""
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(
            _chapter(
                1.0,
                "Gu Yue Tie and Gu Yue Chen entered the hall. The clan head spoke sternly.",
            )
        )
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Tie", chapter=1.0, group="g1", offset=0),
                _mention("m2", "Gu Yue Chen", chapter=1.0, group="g2", offset=15),
                _mention(
                    "m3",
                    "the clan head",
                    chapter=1.0,
                    group="g3",
                    offset=45,
                    alias_type=AliasType.TRANSFERABLE_TITLE,
                ),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)

        tie = next(m for m in store.get_mentions("t", 1.0) if m.text == "Gu Yue Tie")
        chen = next(m for m in store.get_mentions("t", 1.0) if m.text == "Gu Yue Chen")
        title = next(m for m in store.get_mentions("t", 1.0) if m.text == "the clan head")
        assert tie.target_id is not None and chen.target_id is not None
        assert tie.target_id != chen.target_id
        assert title.target_id is None, "must defer, not guess between two rival candidates"

    def test_relational_deictic_also_uses_sole_co_present(self) -> None:
        """The same mechanism must cover RELATIONAL_DEICTIC, not just
        TRANSFERABLE_TITLE -- both were named in Section 5.1."""
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(_chapter(1.0, "Fang Yuan entered. This one bowed low."))
        store.add_mentions(
            [
                _mention("m1", "Fang Yuan", chapter=1.0, group="g1", offset=0),
                _mention(
                    "m2",
                    "this one",
                    chapter=1.0,
                    group="g2",
                    offset=13,
                    alias_type=AliasType.RELATIONAL_DEICTIC,
                ),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)

        named = next(m for m in store.get_mentions("t", 1.0) if m.text == "Fang Yuan")
        deictic = next(m for m in store.get_mentions("t", 1.0) if m.text == "this one")
        assert named.target_id is not None
        assert deictic.target_id == named.target_id
