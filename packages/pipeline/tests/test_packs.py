"""Adaptation packs: what a pack carries, that it never carries the book, and that it applies only to the same text.

Built on the three-chapter book of `test_reader_cast.py`. The planted sentence is that book's own chapter-3 text.
"""

from __future__ import annotations

import json
import zipfile

import pytest
from echotales.core.enums import OBSERVER_READER, AliasType, BlockType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    Block,
    Chapter,
    DiscoursePosition,
    Self,
    VoiceProfile,
)
from echotales.core.store import Store
from echotales.pipeline import packs
from echotales.pipeline.corrections import Correction, CorrectionLog, CorrectionType
from test_reader_cast import TEXT, _book

PLANTED = "Arthur Vane removed his mask. He smiled at Mira, and he told Corin his name."


def _source(tmp_path) -> Store:
    store = _book(tmp_path, 3, "src")
    store.add_attribute("t", Attribute(
        target_kind=TargetKind.SELF, target_id="t:mira", key="typical_attire", value="a green travelling cloak",
        interval=FuzzyInterval.open_ended(1.0), learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER,
        evidence=TEXT[1]))
    store.add_voice_profile(VoiceProfile(id="v1", novel_id="t", self_id="t:mira", speaker_id="p225", pitch=1.1))
    store.add_alias_binding("t", AliasBinding(
        alias="the quiet one", alias_type=AliasType.EPITHET, target_kind=TargetKind.SELF, target_id="t:mira",
        interval=FuzzyInterval.open_ended(1.0), learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER))
    store.conn.commit()
    return store


def _plan(root, chapter: int, panels: list[dict]) -> None:
    d = root / "novels" / "t" / "panels" / f"ch{chapter}" / "v1_test"
    d.mkdir(parents=True)
    (d / "panel_plan.jsonl").write_text("".join(json.dumps(p) + "\n" for p in panels), encoding="utf-8")


def _panel(prompt: str = "a masked figure bows in a candlelit hall") -> dict:
    return {"panel_id": "t:1:1", "panel_seq": 1, "scene_index": 0, "slot_kind": "establishing", "lead_block": 0,
            "block_indexes": [0], "cast": [{"self_id": "t:mira", "persona_id": "x", "label": "Mira"}],
            "location": "a hall", "direction": {"shot": "wide"}, "prompt": prompt, "negative_prompt": "blurry",
            "engine": "stub"}


def _corrections(tmp_path) -> CorrectionLog:
    log = CorrectionLog(tmp_path / "corr.jsonl")
    log.add(Correction(novel_id="t", type=CorrectionType.MERGE_ENTITIES, payload={"from_id": "t:corin", "into_id": "t:mira"}))
    log.add(Correction(novel_id="t", type=CorrectionType.FLAG, payload={"note": "look again"}))
    return log


# --- leak check ---------------------------------------------------------------


def test_a_pack_with_a_sentence_of_the_book_is_rejected(tmp_path) -> None:
    store = _source(tmp_path)
    store.add_attribute("t", Attribute(
        target_kind=TargetKind.SELF, target_id="t:guest", key="distinguishing_features",
        value=f"described as: {PLANTED}", interval=FuzzyInterval.open_ended(3.0),
        learned_at_pos=DiscoursePosition(chapter=3), observer_id=OBSERVER_READER))
    store.conn.commit()
    out = tmp_path / "x.etpack"
    with pytest.raises(packs.PackLeakError) as exc:
        packs.export_pack(store, "t", out, data_root=tmp_path)
    assert "appearance[" in str(exc.value) and "arthur vane removed his mask he smiled" in str(exc.value)
    assert not out.exists()


def test_a_leak_in_a_panel_prompt_is_rejected_too(tmp_path) -> None:
    _plan(tmp_path, 3, [_panel(prompt="Illustration: " + PLANTED)])
    with pytest.raises(packs.PackLeakError):
        packs.export_pack(_source(tmp_path), "t", tmp_path / "x.etpack", data_root=tmp_path)


def test_seven_shared_words_are_allowed_eight_are_not(tmp_path) -> None:
    store = _source(tmp_path)
    seven = "Arthur Vane removed his mask. He smiled"  # 7 words
    assert len(packs._words(seven)) == 7 and packs.LEAK_NGRAM_WORDS == 8
    packs.check_no_book_text(store, "t", {"v": seven})
    with pytest.raises(packs.PackLeakError):
        packs.check_no_book_text(store, "t", {"v": seven + " at"})


def test_graph_evidence_quotations_never_enter_the_pack(tmp_path) -> None:
    store = _source(tmp_path)  # its attribute carries `evidence=TEXT[1]`, a whole book sentence
    out = packs.export_pack(store, "t", tmp_path / "x.etpack", data_root=tmp_path)
    with zipfile.ZipFile(out) as z:
        assert TEXT[1] not in b"".join(z.read(n) for n in z.namelist()).decode()


# --- export -------------------------------------------------------------------


def test_export_holds_every_kind_keyed_to_chapter_hashes(tmp_path) -> None:
    _plan(tmp_path, 1, [_panel()])
    out = packs.export_pack(_source(tmp_path), "t", tmp_path / "x.etpack", corrections=_corrections(tmp_path), data_root=tmp_path)
    assert out.suffix == ".etpack"
    pack = packs.read_pack(out)
    assert pack["manifest"]["format"] == "etpack" and set(pack["manifest"]["chapters"]) == {"1", "2", "3"}
    assert {c["label"] for c in pack["cast"]} == {"Arthur Vane", "Mira", "Corin"}
    # The persona build's own gender and age facts travel too; the planted attire is among them.
    assert "a green travelling cloak" in [a["value"] for a in pack["appearance"]]
    assert pack["voices"][0]["profile"]["speaker_id"] == "p225"
    assert pack["direction"][0]["panels"][0]["prompt"].startswith("a masked figure")
    assert [c["type"] for c in pack["corrections"]] == ["merge_entities"]  # the flag is a note, not a decision
    for kind in ("cast", "appearance", "voices", "direction", "corrections"):
        assert all(len(i["hash"]) == 64 for i in pack[kind]), kind
    assert "engine" not in pack["direction"][0]["panels"][0]


# --- import -------------------------------------------------------------------


def test_import_applies_what_matches_into_a_fresh_copy_of_the_book(tmp_path) -> None:
    _plan(tmp_path, 1, [_panel()])
    out = packs.export_pack(_source(tmp_path), "t", tmp_path / "x.etpack", corrections=_corrections(tmp_path), data_root=tmp_path)
    target = _book(tmp_path, 3, "dst")
    log = CorrectionLog(tmp_path / "dst.jsonl")
    report = packs.import_pack(target, "t", out, corrections_log=log, data_root=tmp_path / "dst-data")

    assert report.skipped == []
    assert report.applied["appearance"] == 1 and report.applied["voices"] == 1 and report.applied["corrections"] == 1
    assert [a.value for a in target.get_attributes(TargetKind.SELF, "t:mira")] == ["a green travelling cloak"]
    assert target.get_voice_profile("t", "t:mira").speaker_id == "p225"
    assert "the quiet one" in {a.alias for a in target.get_aliases_for(TargetKind.SELF, "t:mira")}
    assert [c.type for c in log] == [CorrectionType.MERGE_ENTITIES]
    plan = tmp_path / "dst-data" / "novels" / "t" / "packs" / "x" / "direction" / "ch1.jsonl"
    assert json.loads(plan.read_text().splitlines()[0])["prompt"].startswith("a masked figure")
    assert report.direction_dir == str(plan.parent)


def test_importing_twice_adds_nothing_the_second_time(tmp_path) -> None:
    out = packs.export_pack(_source(tmp_path), "t", tmp_path / "x.etpack", corrections=_corrections(tmp_path), data_root=tmp_path)
    target = _book(tmp_path, 3, "dst")
    log = CorrectionLog(tmp_path / "dst.jsonl")
    packs.import_pack(target, "t", out, corrections_log=log, data_root=tmp_path / "d")
    again = packs.import_pack(target, "t", out, corrections_log=log, data_root=tmp_path / "d")
    assert again.applied.get("appearance", 0) == 0 and again.applied.get("corrections", 0) == 0
    assert len(target.get_attributes(TargetKind.SELF, "t:mira")) == 1 and len(log) == 1


def test_items_for_a_chapter_whose_text_differs_are_reported_not_applied(tmp_path) -> None:
    store = _source(tmp_path)
    store.add_attribute("t", Attribute(
        target_kind=TargetKind.SELF, target_id="t:mira", key="hair_color", value="auburn",
        interval=FuzzyInterval.open_ended(2.0), learned_at_pos=DiscoursePosition(chapter=2), observer_id=OBSERVER_READER))
    store.conn.commit()
    out = packs.export_pack(store, "t", tmp_path / "x.etpack", data_root=tmp_path)

    target = _book(tmp_path, 3, "dst")
    target.conn.execute("DELETE FROM chapter WHERE novel_id='t' AND number=2")
    target.add_chapter(Chapter(novel_id="t", number=2.0, title="T", source_href="2.html",
                               blocks=[Block(index=0, block_type=BlockType.PROSE, text="A different translation of chapter two.")]))
    target.conn.commit()
    report = packs.import_pack(target, "t", out, data_root=tmp_path / "d")

    assert report.applied["appearance"] == 1  # chapter 1's cloak
    assert [(s["kind"], s["chapter"]) for s in report.skipped if s["kind"] == "appearance"] == [("appearance", 2.0)]
    assert [a.key for a in target.get_attributes(TargetKind.SELF, "t:mira")] == ["typical_attire"]


def test_a_character_is_matched_by_label_when_the_ids_differ(tmp_path) -> None:
    out = packs.export_pack(_source(tmp_path), "t", tmp_path / "x.etpack", data_root=tmp_path)
    other = Store(":memory:")
    other.add_novel("t", "T", "x.epub", "generic")
    for n in (1, 2, 3):
        other.add_chapter(_book(tmp_path, 3, f"tmp{n}").get_chapter("t", float(n)))
    other.add_self(Self(id="t:self:zz", novel_id="t", canonical_label="mira",
                        first_attested_pos=DiscoursePosition(chapter=1), kind=TargetKind.SELF))
    other.conn.commit()
    report = packs.import_pack(other, "t", out, data_root=tmp_path / "d")
    assert [a.value for a in other.get_attributes(TargetKind.SELF, "t:self:zz")] == ["a green travelling cloak"]
    unmatched = {s["what"] for s in report.skipped if s["kind"] == "cast"}
    assert "Corin" in unmatched and "Mira" not in unmatched


def test_a_correction_naming_an_absent_character_is_skipped(tmp_path) -> None:
    out = packs.export_pack(_source(tmp_path), "t", tmp_path / "x.etpack", corrections=_corrections(tmp_path), data_root=tmp_path)
    target = _book(tmp_path, 2, "short")  # chapter 3 and Corin are absent here
    log = CorrectionLog(tmp_path / "short.jsonl")
    report = packs.import_pack(target, "t", out, corrections_log=log, data_root=tmp_path / "d")
    assert len(log) == 0 and any(s["kind"] == "corrections" for s in report.skipped)


def test_a_file_that_is_not_a_pack_is_refused(tmp_path) -> None:
    bad = tmp_path / "bad.etpack"
    bad.write_bytes(b"not a zip")
    with pytest.raises(packs.PackError):
        packs.import_pack(_book(tmp_path, 1, "x"), "t", bad, data_root=tmp_path)
