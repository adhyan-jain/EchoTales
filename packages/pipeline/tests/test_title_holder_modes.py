"""B13 and A7 (CHIMERA defect backlog): the title-holder pass's two new switches. Synthetic strings only.

B13: the closed-tenure interval no longer passes a keyword FuzzyInterval silently dropped, and with
`fuzzy_handover=True` the handover is bounded by the next holder's first declaration (the gap reads PLAUSIBLE,
not EXCLUDED); defaults keep the shipped crisp end.
A7: with `causal=True` the first holder's tenure starts at the first declaration, so a bare title mentioned before
the reader is told who holds it is not linked backward; the default keeps the documented volume-first behaviour.
"""

from __future__ import annotations

import inspect

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Block, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.resolve import resolve_novel
from echotales.pipeline.resolve.title_holders import Declaration, link_title_holders, tenures

N = "t"


def _world() -> Store:
    s = Store(":memory:")
    s.add_novel(N, "T", "x.epub", "generic")
    texts = {
        1.0: "Everyone watched the clan head closely. Zorrin Vale waited at the gate.",
        2.0: "Clan head Zorrin Vale rose from the dais. Zorrin Vale spoke. Clan head Zorrin Vale rose again.",
        3.0: "Clan head Zorrin Vale rose from the dais.",
        4.0: "Clan head Mavel Orsk took the seat. Clan head Mavel Orsk spoke. Clan head Mavel Orsk rose.",
    }
    for n, t in texts.items():
        s.add_chapter(Chapter(novel_id=N, number=n, title="T", source_href=f"{n}.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=t)]))
    ms = []
    k = 0
    for n, t in texts.items():
        for name, atype in (("Zorrin Vale", AliasType.RIGID_NAME), ("Mavel Orsk", AliasType.RIGID_NAME),
                            ("the clan head", AliasType.TRANSFERABLE_TITLE)):
            pos = 0
            while (i := t.find(name, pos)) != -1:
                k += 1
                ms.append(Mention(id=f"m{k}", novel_id=N, segment_id="s", chapter=n, offset=i, text=name,
                                  alias_type=atype, span_type=SpanType.NARRATION_ACTION,
                                  reference_mode=ReferenceMode.PRESENT, block_index=0, local_group_id=f"g{k}"))
                pos = i + len(name)
    s.add_mentions(ms)
    s.conn.commit()
    resolve_novel(N, s)
    return s


def _reset_title_links(s: Store) -> None:
    for m in s.get_mentions(N):
        if m.alias_type is AliasType.TRANSFERABLE_TITLE:
            m.target_id, m.target_kind, m.method = None, None, None
            s.add_mentions([m])
    s.conn.execute("DELETE FROM alias_binding WHERE novel_id=? AND alias_type='TRANSFERABLE_TITLE'", (N,))
    s.conn.commit()


def test_tenure_start_default_is_chapter_one_and_causal_is_the_first_declaration() -> None:
    d = [Declaration(2.0, 0, None, "a", "x"), Declaration(3.0, 0, None, "a", "x"), Declaration(4.0, 0, None, "b", "y"),
         Declaration(4.0, 1, None, "b", "y")]
    labels = {"a": "A", "b": "B"}
    assert tenures(d, labels)[None][0].start == 1.0
    assert tenures(d, labels, causal=True)[None][0].start == 2.0


def test_closed_tenure_call_no_longer_passes_a_field_the_model_lacks() -> None:
    assert "last_evidence" not in FuzzyInterval.model_fields
    # the old closed-interval call ended `last_evidence=run.last_declared),`; the open_ended call has no comma
    assert "last_evidence=run.last_declared)," not in inspect.getsource(link_title_holders)


def test_title_before_the_first_declaration_is_linked_by_default_but_not_in_causal_mode() -> None:
    s = _world()
    assert [m for m in s.get_mentions(N, 1.0) if m.text == "the clan head"][0].target_id is not None
    _reset_title_links(s)
    link_title_holders(s, N, causal=True)
    assert [m for m in s.get_mentions(N, 1.0) if m.text == "the clan head"][0].target_id is None


def test_fuzzy_handover_bounds_the_closed_tenure_by_the_next_declaration() -> None:
    s = _world()
    crisp = [b for b in s.all_aliases(N) if b.alias_type is AliasType.TRANSFERABLE_TITLE
             and b.interval.to_ub != float("inf")]
    assert crisp and all(b.interval.to_lb == b.interval.to_ub for b in crisp)      # default: crisp end
    _reset_title_links(s)
    link_title_holders(s, N, fuzzy_handover=True)
    fuzzy = [b for b in s.all_aliases(N) if b.alias_type is AliasType.TRANSFERABLE_TITLE
             and b.interval.to_ub != float("inf")]
    assert fuzzy and all(b.interval.to_ub > b.interval.to_lb for b in fuzzy)        # bounded by the next holder
