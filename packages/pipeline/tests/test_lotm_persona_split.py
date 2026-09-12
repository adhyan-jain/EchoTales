from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, Mention, Span
from echotales.core.store import Store
from echotales.pipeline.persona.build import build_personas
from echotales.pipeline.persona.split import bodies_of, is_split
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


def test_lotm_transmigration_emits_multiple_persona_bodies():
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(_chapter(1.0, "Zhou Mingrui opened his eyes in a strange room."))
    reveal_text = (
        "Klein Moretti stared at his hands. Zhou Mingrui's memories began "
        "flooding him, and he realized he was now Klein Moretti."
    )
    store.add_chapter(_chapter(2.0, reveal_text))
    store.add_chapter(_chapter(3.0, "Klein Moretti walked down the street in his new body."))
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
            _mention("m3", "Klein Moretti", chapter=3.0, group="g3"),
        ]
    )

    store.add_spans(
        [
            Span(
                id="sp1",
                novel_id="t",
                chapter=1.0,
                block_index=0,
                start=0,
                end=46,
                span_type=SpanType.NARRATION_ACTION,
                text="Zhou Mingrui opened his eyes in a strange room.",
            ),
            Span(
                id="sp2",
                novel_id="t",
                chapter=2.0,
                block_index=0,
                start=0,
                end=len(reveal_text),
                span_type=SpanType.NARRATION_ACTION,
                text=reveal_text,
            ),
            Span(
                id="sp3",
                novel_id="t",
                chapter=3.0,
                block_index=0,
                start=0,
                end=54,
                span_type=SpanType.NARRATION_ACTION,
                text="Klein Moretti walked down the street in his new body.",
            ),
        ]
    )
    store.conn.commit()

    resolve_novel("t", store)
    m1 = next(m for m in store.get_mentions("t", 1.0) if m.text == "Zhou Mingrui")
    self_id = m1.target_id

    # Build personas
    build_personas("t", store)

    assert is_split(store, self_id)
    bodies = bodies_of(store, self_id)
    assert len(bodies) >= 2
    assert "body1" in bodies[0][0]
    assert "body2" in bodies[1][0]
