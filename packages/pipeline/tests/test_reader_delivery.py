"""Line emotions: the reader's delivery pass, how they set synthesis, and the paced, chaptered audiobook export."""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from echotales.core.enums import BlockType, SpanType
from echotales.core.models import Block, Chapter, Span
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.reader.delivery_pass import read_chapter_delivery
from echotales.pipeline.spans.delivery import DeliveryPolarity
from echotales.pipeline.voice.bank import BankVoice
from echotales.pipeline.voice.delivery import settings_for
from echotales.pipeline.voice.export import (
    PARAGRAPH_GAP_S,
    SAME_SPEAKER_GAP_S,
    SCENE_GAP_S,
    SPEAKER_CHANGE_GAP_S,
    chapter_metadata,
    export_m4b,
    gaps_for,
)

TEXT0 = "“Hand it over or die!” the man roared."
TEXT1 = "The corridor fell silent. Somewhere water dripped."
TEXT2 = "“Fine.” She shrugged."


def _world() -> tuple[Store, Chapter]:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    chapter = Chapter(
        novel_id="n", number=1.0, title="T", source_href="a",
        blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate((TEXT0, TEXT1, TEXT2))],
    )
    store.add_chapter(chapter)
    store.add_spans([
        Span(id="n:1:0:0", novel_id="n", chapter=1.0, block_index=0, start=0, end=24, span_type=SpanType.DIALOGUE,
             text="“Hand it over or die!”"),
        Span(id="n:1:1:0", novel_id="n", chapter=1.0, block_index=1, start=0, end=len(TEXT1),
             span_type=SpanType.NARRATION_DESCRIPTION, text=TEXT1),
        Span(id="n:1:2:0", novel_id="n", chapter=1.0, block_index=2, start=0, end=7, span_type=SpanType.DIALOGUE,
             text="“Fine.”"),
    ])
    return store, chapter


def _run(response: dict) -> tuple[Store, object]:  # type: ignore[type-arg]
    store, chapter = _world()
    stub = StubProvider()
    stub.register_response("reader", response)
    return store, read_chapter_delivery(store, ModelClient(provider_override=stub), chapter)


def test_each_quoted_line_gets_its_emotion_and_narration_the_passage_mood() -> None:
    store, report = _run({
        "mood": "afraid", "mood_intensity": 2,
        "lines": [{"tag": "0.0", "emotion": "angry", "intensity": 3}, {"tag": "2.0", "emotion": "calm", "intensity": 1}],
    })
    assert store.span_emotions("n", 1.0) == {
        "n:1:0:0": ("anger", 3), "n:1:2:0": ("serenity", 1), "n:1:1:0": ("fear", 2),
    }
    assert report.lines == 2 and report.narration == 1  # type: ignore[attr-defined]


def test_an_off_list_label_is_neutral_and_intensity_is_clamped() -> None:
    store, report = _run({"lines": [{"tag": "0.0", "emotion": "furious-ish", "intensity": 9},
                                    {"tag": "2.0", "emotion": "Surprised", "intensity": 0}]})
    emotions = store.span_emotions("n", 1.0)
    assert emotions["n:1:0:0"] == ("neutral", 3)
    assert emotions["n:1:2:0"] == ("amazement", 1)
    assert report.unknown_labels == 1  # type: ignore[attr-defined]


def test_a_delivery_marker_still_overrides_the_emotion() -> None:
    # Non-negotiable 10: "he said expressionlessly" stays flat however angry the passage reads.
    flat = settings_for(span_type=SpanType.DIALOGUE, polarity=DeliveryPolarity.FLAT, emotion="anger", intensity=3)
    assert flat.emotion == "neutral" and flat.exaggeration < 0.5


def test_the_emotion_picks_the_recording_and_the_intensity_the_dial() -> None:
    mild = settings_for(span_type=SpanType.DIALOGUE, emotion="anger", intensity=1)
    strong = settings_for(span_type=SpanType.DIALOGUE, emotion="anger", intensity=3)
    sad = settings_for(span_type=SpanType.DIALOGUE, emotion="sadness", intensity=3)
    assert strong.emotion == "anger" and strong.exaggeration > mild.exaggeration and strong.cfg_weight < mild.cfg_weight
    assert sad.exaggeration < strong.exaggeration  # a quiet state is not pushed to a shout


def test_narration_takes_only_a_clear_mood_and_never_a_reading_style() -> None:
    slight = settings_for(span_type=SpanType.NARRATION_DESCRIPTION, emotion="fear", intensity=1)
    clear = settings_for(span_type=SpanType.NARRATION_DESCRIPTION, emotion="fear", intensity=3)
    styled = settings_for(span_type=SpanType.NARRATION_DESCRIPTION, emotion="loud", intensity=3)
    performed = settings_for(span_type=SpanType.DIALOGUE, emotion="fear", intensity=3)
    assert slight.emotion == "neutral" and clear.emotion == "fear" and styled.emotion == "neutral"
    assert clear.exaggeration < performed.exaggeration


def test_an_ears_label_degrades_to_the_nearest_cremad_recording() -> None:
    voice = BankVoice("1001", "male", 40, reference_clip=Path("neutral.wav"),
                      emotion_clips={"angry": Path("ang.wav"), "happy": Path("hap.wav"), "fear": Path("fea.wav")})
    assert voice.clip_for("anger") == Path("ang.wav")
    assert voice.clip_for("pride") == Path("hap.wav")  # pride -> contentment -> happy
    assert voice.clip_for("pain") == Path("fea.wav")  # pain -> distress -> fear
    assert voice.clip_for("amazement") == Path("neutral.wav")


def test_pauses_follow_the_structure_of_the_text() -> None:
    lines = [SimpleNamespace(block_index=b, voice=v, span_type="x") for b, v in
             ((0, "a"), (0, "a"), (1, "b"), (2, "b"), (5, "b"))]
    assert gaps_for(lines) == [SAME_SPEAKER_GAP_S, SPEAKER_CHANGE_GAP_S, PARAGRAPH_GAP_S, SCENE_GAP_S]


def test_chapter_markers_are_contiguous_milliseconds() -> None:
    meta = chapter_metadata(["One", "Two"], [1.5, 2.25], title="Book", author="A")
    assert "START=0\nEND=1500\ntitle=One" in meta and "START=1500\nEND=3750\ntitle=Two" in meta


def _tone(path: Path, seconds: float) -> Path:
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(24000)
        fh.writeframes(b"\x10\x00\xf0\xff" * int(24000 * seconds / 2))
    return path


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="needs ffmpeg")
def test_the_m4b_has_one_chapter_per_track(tmp_path: Path) -> None:
    tracks = [_tone(tmp_path / "1.wav", 1.0), _tone(tmp_path / "2.wav", 1.5)]
    book = export_m4b(tracks, tmp_path / "book.m4b", titles=["Chapter 1", "Chapter 2"], title="Book")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "csv=p=0", str(book)],
                           capture_output=True, text=True, check=True).stdout.strip().splitlines()
    assert len(probe) == 2 and probe[1].endswith("Chapter 2")
