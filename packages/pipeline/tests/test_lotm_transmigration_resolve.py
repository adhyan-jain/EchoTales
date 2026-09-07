"""Defect #2 (HANDOFF "Open defects"): does LOTM's transmigration reveal
actually link "Zhou Mingrui" and "Klein Moretti" end to end through resolve?

`detect_identity_continuity` (resolve/evidence.py) and its wiring into
`score_evidence`/`score.prefilter` are already built and unit-tested in
isolation (`test_identity_continuity.py`, including
`test_the_real_lotm_transmigration_sentence`). What HANDOFF's defect #2
claims is still broken is the *resolve-pipeline* outcome: "resolve still
produces two selves, so there's no one consciousness for two personas to
hang off." This test exercises `resolve_novel` end to end to check whether
that claim still holds, given the detector and its retrieval path
(`CandidateRetriever._prominent`, kept specifically for disguise-shaped
candidates with zero surface overlap) both already exist.
"""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
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


def _mention(mid: str, text: str, *, chapter: float, group: str, offset: int = 0) -> Mention:
    return Mention(
        id=mid,
        novel_id="t",
        segment_id="s",
        chapter=chapter,
        offset=offset,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT,
        block_index=0,
        local_group_id=group,
    )


class TestTransmigrationLinksEndToEnd:
    def test_klein_moretti_links_to_zhou_mingrui_through_resolve(self) -> None:
        store = Store(":memory:")
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(_chapter(1.0, "Zhou Mingrui opened his eyes in a strange room."))
        reveal_text = (
            "Klein Moretti stared at his hands. Zhou Mingrui's memories began "
            "flooding him, and he realized he was now Klein Moretti."
        )
        store.add_chapter(_chapter(2.0, reveal_text))
        store.add_mentions(
            [
                _mention("m1", "Zhou Mingrui", chapter=1.0, group="g1"),
                _mention(
                    "m2",
                    "Klein Moretti",
                    chapter=2.0,
                    group="g2",
                    offset=reveal_text.index("Klein Moretti"),
                ),
            ]
        )
        store.conn.commit()

        resolve_novel("t", store)

        m1 = next(m for m in store.get_mentions("t", 1.0) if m.text == "Zhou Mingrui")
        m2 = next(m for m in store.get_mentions("t", 2.0) if m.text == "Klein Moretti")
        assert m1.target_id is not None
        assert m2.target_id == m1.target_id
