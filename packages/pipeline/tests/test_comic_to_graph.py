"""A comic in the store: chapters, spans in reading order, speakers as entities, and the voice stage accepts it."""

from __future__ import annotations

import pytest

pytest.importorskip("scipy")

import json
from pathlib import Path

from echotales.core.enums import AttributionMethod, BlockType, SpanType
from echotales.core.store import Store
from echotales.pipeline.comic.bubbles import Bubble
from echotales.pipeline.comic.to_graph import comic_to_store, story_bubbles
from echotales.pipeline.comic.understand import ComicUnderstanding, PageUnderstanding, PanelUnderstanding
from echotales.pipeline.voice.bank import VoiceBank, parse_speaker_info
from echotales.pipeline.voice.engine import get_engine
from echotales.pipeline.voice.runner import render_novel

INFO = """ID  AGE  GENDER  ACCENTS  REGION
p225  23  F    English    Southern  England
p226  22  M    English    Surrey
p227  38  M    English    Cumbria
p228  64  F    English    Southern  England
"""


def _b(i: int, text: str, kind: str, speaker: str | None) -> Bubble:
    return Bubble(id=f"p001b{i:02d}", panel_index=0, text=text, kind=kind, text_box=(0, 0, 9, 9), box=(0, 0, 9, 9),
                  speaker=speaker, order=i)


def _und() -> ComicUnderstanding:
    bubbles = [
        _b(1, "Meanwhile, in the kitchen.", "narration", None),
        _b(2, "...and the last touch.", "speech", "Character A"),
        _b(3, "SHSH", "sfx", None),
        _b(4, "Don't even think about it.", "speech", "Character B"),
        _b(5, "Hmm.", "speech", None),
    ]
    page = PageUnderstanding(0, "p1.png", (100, 100), [PanelUnderstanding(0, (0, 0, 100, 100), bubbles)])
    return ComicUnderstanding([page], ocr_engine="fake", speakers=["Character A", "Character B"])


def test_story_bubbles_drop_sound_effects_and_keep_order() -> None:
    assert [b.text for b in story_bubbles(_und())] == [
        "Meanwhile, in the kitchen.", "...and the last touch.", "Don't even think about it.", "Hmm."]


def test_store_round_trip(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "c.db"))
    report = comic_to_store(store, _und(), "pc", "Pepper and Carrot", chapter=1.0, chapter_title="Potion of Flight")
    assert store.get_novel("pc")["content_type"] == "comic"
    chapter = store.get_chapter("pc", 1.0)
    assert chapter.title == "Potion of Flight"
    assert [b.block_type for b in chapter.blocks] == [BlockType.PROSE, BlockType.DIALOGUE, BlockType.DIALOGUE, BlockType.DIALOGUE]
    spans = store.get_spans("pc", 1.0)
    assert [s.span_type for s in spans] == [SpanType.NARRATION_DESCRIPTION, SpanType.DIALOGUE, SpanType.DIALOGUE, SpanType.DIALOGUE]
    assert [s.speaker_self_id for s in spans] == [None, "Character A", "Character B", None]
    assert spans[1].attribution_method is AttributionMethod.PROXIMAL
    assert spans[3].attribution_method is AttributionMethod.UNRESOLVED
    assert {s.canonical_label for s in store.all_selves("pc")} == {"Character A", "Character B"}
    assert report.spans == 4 and report.sfx_skipped == 1 and report.unattributed == 1


def _voice(tmp_path: Path, trust: bool):
    store = Store(str(tmp_path / "c.db"))
    comic_to_store(store, _und(), "pc", "Pepper and Carrot", chapter=1.0, trust_speakers=trust)
    out = tmp_path / "audio"
    report = render_novel("pc", store, VoiceBank(voices=parse_speaker_info(INFO)), out_dir=out, engine=get_engine("stub"))
    lines = [json.loads(x) for x in (out / "manifest.jsonl").read_text().splitlines() if x.strip()]
    return report, lines


def test_voice_stage_accepts_the_comic_and_guesses_are_stand_ins(tmp_path: Path) -> None:
    report, lines = _voice(tmp_path, trust=False)
    assert report.lines == len(lines) == 4
    assert all(Path(ln["audio_path"]).is_file() for ln in lines)
    assert report.character_lines == 0 and report.unconfirmed_lines == 2


def test_trusted_speakers_get_their_character_voice(tmp_path: Path) -> None:
    report, lines = _voice(tmp_path, trust=True)
    assert report.character_lines == 2 and report.unconfirmed_lines == 0
    assert len(lines) == 4
