"""A fact the text states after a mid-chapter rebirth belongs to the new body, from its own block."""

from __future__ import annotations

from echotales.core.enums import BlockType, Prominence, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Block, Chapter, DiscoursePosition, Persona, Self, SelfPersonaBinding
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.reader import facts_pass as fp


def test_a_fact_stated_after_a_mid_chapter_rebirth_binds_to_the_new_body_from_its_own_block() -> None:
    """RI ch1: block 83 ("his young and soft, pale palms") follows the rebirth at 1 + 82/92, but facts were bound with
    `persona_at(chapter + 0.5)` and a chapter-granular `story_from`, so the 500-year-old on the cliff (block 6) read
    "young and soft" in the 2026-11-16 render (EVOLUTION 4.164)."""
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    texts = [
        "Fang Yuan stood on the cliff, covered in blood.",
        "He was reborn.",
        "Fang Yuan looked at his young and soft palms.",
        "The rain fell.",
    ]
    blocks = [Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)]
    store.add_chapter(Chapter(novel_id="n", number=1.0, title="T", source_href="a", blocks=blocks))
    store.add_self(Self(id="n:self:fy", novel_id="n", canonical_label="Fang Yuan", prominence=Prominence.RECURRING,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    for pid, label in (("n:self:fy:body1", "old"), ("n:self:fy:body2", "young")):
        store.add_persona(Persona(id=pid, novel_id="n", body_label=label, first_attested_pos=DiscoursePosition(chapter=1)))
    for pid, iv in (("n:self:fy:body1", FuzzyInterval.point_known(1.0, 1.5)),
                    ("n:self:fy:body2", FuzzyInterval.open_ended(1.5))):
        store.add_self_persona_binding(SelfPersonaBinding(
            self_id="n:self:fy", persona_id=pid, interval=iv, learned_at_pos=DiscoursePosition(chapter=1),
            observer_id="READER"))
    stub = StubProvider()
    stub.register_response("reader", {"appearance": [
        {"character": "Fang Yuan", "attribute": "current_condition", "value": "young and soft palms",
         "quote": "his young and soft palms"},
    ], "identities": [], "ages": []})
    chapter = store.get_chapter("n", 1.0)
    fp.read_chapter_facts(store, ModelClient(provider_override=stub), chapter)
    old = [a for a in store.get_attributes(TargetKind.PERSONA, "n:self:fy:body1") if a.key == "current_condition"]
    young = [a for a in store.get_attributes(TargetKind.PERSONA, "n:self:fy:body2") if a.key == "current_condition"]
    assert not old
    assert young and young[0].interval.from_lb == 1.5  # block 2 of 4, not "chapter 1"
