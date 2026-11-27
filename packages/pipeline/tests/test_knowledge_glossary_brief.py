"""Glossary claims are tagged text/general_knowledge with quotes checked; briefs say who matters later (fake LLM)."""

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
from echotales.pipeline.knowledge import build_briefs, build_glossary, glossary, load_glossary
from echotales.pipeline.knowledge.glossary import Claim, KeepItem, KeepOut, TermOut

TEXTS = {
    1.0: "The elder spoke first. Ann Lee held the jade token tight.",
    2.0: "An elder of the clan nodded gravely.",
    3.0: "Ann Lee lost the jade token in the river. The elder sighed.",
    4.0: "Ann Lee found the jade token again.",
}


class FakeClient:
    model_id = "fake:1"

    def complete(self, task, prompt, schema, **kw):  # type: ignore[no-untyped-def]
        if schema is KeepOut:
            return SimpleNamespace(value=KeepOut(terms=[KeepItem(term="elder", category="role")]))
        return SimpleNamespace(value=TermOut(claims=[
            Claim(field="definition", text="A clan senior.", source="text", quote="An elder of the clan nodded"),
            Claim(field="holder_age", text="Old.", source="text", quote="grey beards everywhere"),  # not in the text
            Claim(field="holder_dress", text="Robes.", source="general_knowledge"),
        ]))


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    for number, text in TEXTS.items():
        store.add_chapter(Chapter(novel_id="n", number=number, title="T", source_href="a",
                                  blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)]))
    store.add_self(Self(id="n:self:ann", novel_id="n", canonical_label="Ann Lee", prominence=Prominence.RECURRING,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.add_mentions([
        Mention(id=f"m{i}", novel_id="n", segment_id="s", chapter=ch, offset=0, text="Ann Lee", alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_DESCRIPTION, reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF, target_id="n:self:ann", block_index=0)
        for i, ch in enumerate((1.0, 3.0, 4.0))])
    return store


def test_glossary_demotes_text_claims_whose_quote_is_not_in_the_contexts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    store = _store()
    monkeypatch.setattr(glossary, "candidates", lambda *a, **k: [{"term": "elder", "count": 3, "chapters": 3, "elsewhere": 0.0, "score": 1.0}])
    out = build_glossary(store, FakeClient(), "n", say=lambda *_: None)
    claims = {c["field"]: c for c in out["terms"][0]["claims"]}
    assert claims["definition"]["source"] == "text"
    assert claims["holder_age"]["source"] == "general_knowledge" and claims["holder_age"]["quote"] == ""
    assert out["terms"][0]["demoted_claims"] == 1
    assert len(out["terms"][0]["contexts"]) == 3
    assert load_glossary(store, "n")["terms"][0]["term"] == "elder"


def test_brief_marks_who_matters_later() -> None:
    store = _store()
    brief = build_briefs(store, "n", [1.0], say=lambda *_: None)[0]
    ann = brief["entities"][0]
    assert ann["label"] == "Ann Lee" and ann["chapters_after"] == 2 and ann["last_chapter"] == 4.0
    assert ann["matters_later"] is False  # 2 later chapters is under the threshold of 3
