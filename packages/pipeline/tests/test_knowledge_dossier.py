"""Knowledge-base dossier: verified quotes only, presence gating, changes close earlier intervals (fake LLM)."""

from __future__ import annotations

from types import SimpleNamespace

from echotales.core.enums import (
    AliasType,
    BlockType,
    Prominence,
    ReferenceMode,
    SpanType,
    TargetKind,
)
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.knowledge import build_dossiers, dossier_at
from echotales.pipeline.knowledge.dossier import CharOut, FactOut, WindowOut, YesNo

TEXTS = {
    1.0: ["Ann Lee spoke softly. Mo Bai was far away.", "The black-haired Ann Lee wore a white robe.",
          "Mo Bai, they said, was gifted."],
    2.0: ["Ann Lee had cut her hair; now her hair was snow white."],
}


class FakeClient:
    model_id = "fake:1"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, task, prompt, schema, **kw):  # type: ignore[no-untyped-def]
        self.calls += 1
        if schema is YesNo:
            return SimpleNamespace(value=YesNo(answer=False), model="fake:1")
        if "snow white" in prompt:
            out = WindowOut(characters=[CharOut(name="Ann Lee", in_person=True, facts=[
                FactOut(attribute="hair_color", value="white", block=0, quote="her hair was snow white")])])
        else:
            out = WindowOut(characters=[
                CharOut(name="Ann Lee", in_person=True, facts=[
                    FactOut(attribute="hair_color", value="black", block=1, quote="The black-haired Ann Lee"),
                    FactOut(attribute="typical_attire", value="white robe", block=1, quote="wore a white robe"),
                    FactOut(attribute="eye_color", value="green", block=1, quote="emerald eyes glittered")]),
                CharOut(name="Mo Bai", in_person=False, facts=[
                    FactOut(attribute="hair_color", value="red", block=2, quote="Mo Bai, they said, was gifted"),
                    FactOut(attribute="role", value="genius", block=2, quote="Mo Bai, they said, was gifted")]),
            ])
        return SimpleNamespace(value=out, model="fake:1")


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    for number, blocks in TEXTS.items():
        store.add_chapter(Chapter(novel_id="n", number=number, title="T", source_href="a",
                                  blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(blocks)]))
    for sid, name in (("n:self:ann", "Ann Lee"), ("n:self:mo", "Mo Bai")):
        store.add_self(Self(id=sid, novel_id="n", canonical_label=name, prominence=Prominence.RECURRING,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    rows = []
    for ch, blk, text, sid in ((1.0, 0, "Ann Lee", "n:self:ann"), (1.0, 1, "Ann Lee", "n:self:ann"),
                               (1.0, 2, "Mo Bai", "n:self:mo"), (1.0, 0, "Mo Bai", "n:self:mo"),
                               (2.0, 0, "Ann Lee", "n:self:ann")):
        rows.append(Mention(id=f"m{len(rows)}", novel_id="n", segment_id="s", chapter=ch, offset=0, text=text,
                            alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_DESCRIPTION,
                            reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=sid, block_index=blk))
    store.add_mentions(rows)
    return store


def test_checked_facts_become_a_chain_and_absent_looks_are_dropped() -> None:
    store, client = _store(), FakeClient()
    report = build_dossiers(store, client, "n", say=lambda *_: None)
    assert report.rejected_quote == 1  # the invented "emerald eyes" quote is not in the text
    assert report.rejected_not_present == 1  # Mo Bai's hair, said of an absent person
    d1 = dossier_at(store, "n", "n:self:ann", 1.0)
    assert d1.appearance["hair_color"][0].value == "black"
    assert d1.appearance["hair_color"][0].quote == "The black-haired Ann Lee"
    d2 = dossier_at(store, "n", "n:self:ann", 2.5)
    assert [f.value for f in d2.appearance["hair_color"]] == ["white"]
    assert dossier_at(store, "n", "n:self:mo", 1.0).roles[0].value == "genius"
    assert dossier_at(store, "n", "n:self:ann", 1.0).first_in_person == 1.0


def test_resume_skips_done_chapters_and_extrapolates_later_looks() -> None:
    store, client = _store(), FakeClient()
    build_dossiers(store, client, "n", [2.0], say=lambda *_: None)
    calls = client.calls
    again = build_dossiers(store, client, "n", [2.0], say=lambda *_: None)
    assert again.skipped == 1 and client.calls == calls
    early = dossier_at(store, "n", "n:self:ann", 1.0)
    assert early.appearance["hair_color"][0].extrapolated is False  # innate: reaches back to the body start
