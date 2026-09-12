import pytest
from echotales.core.enums import BlockType
from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline.eval.baseline_a import (
    MentionOut,
    SectionResult,
    _locate,
    materialize_mentions,
)


def test_baseline_a_locate_substring():
    text = "Zhou Mingrui opened his eyes in a strange room. Klein Moretti looked around."
    offset = _locate(text, "Klein Moretti", "looked around", set())
    assert offset is not None
    assert text[offset:].startswith("Klein Moretti")


def test_baseline_a_materialize_mentions():
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="1.html",
            blocks=[
                Block(
                    index=0,
                    block_type=BlockType.PROSE,
                    text="Zhou Mingrui opened his eyes in a strange room.",
                )
            ],
        )
    )

    section = SectionResult(
        section="ch1-1",
        chapters=(1, 1),
        entities=[{"id": "e1", "name": "Zhou Mingrui"}],
        mentions=[
            {
                "chapter": 1.0,
                "surface": "Zhou Mingrui",
                "context": "opened his eyes",
                "entity_id": "e1",
            }
        ],
        prompt_tokens=100,
        output_tokens=50,
        wall_seconds=1.0,
    )

    inserted = materialize_mentions(store, "t", [section])
    assert inserted == 1

    mentions = store.get_mentions("t", 1.0)
    assert len(mentions) == 1
    assert mentions[0].text == "Zhou Mingrui"
    assert mentions[0].target_id == "baseline_e1"
