"""`voice/runner.py::render_novel`, the audio orchestrator, end to end.

docs/STATUS.md recorded it as having zero direct test coverage: casting,
delivery and the engine each had unit tests, but nothing ran the whole path --
cast, script, synthesise, write the manifest -- so a break in the wiring would
have passed CI. This runs it against the stub engine, which writes real WAV
files (silent, with a duration derived from the text), a small in-memory novel
and a five-voice bank. It checks behaviour a listener would notice:
who is voiced how, that an unnamed speaker keeps one voice, and that a re-run
recasts nobody.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

from echotales.core.enums import (
    AliasType,
    AttributionMethod,
    BlockType,
    ReferenceMode,
    SpanType,
    TargetKind,
)
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.persona import build_personas
from echotales.pipeline.voice.bank import VoiceBank, parse_speaker_info
from echotales.pipeline.voice.engine import get_engine
from echotales.pipeline.voice.runner import render_novel

SPEAKER_INFO = """ID  AGE  GENDER  ACCENTS  REGION
p225  23  F    English    Southern  England
p226  22  M    English    Surrey
p227  38  M    English    Cumbria
p228  64  F    English    Southern  England
p229  11  M    Scottish   Fife
"""

NAMED = "t:self1"
#: `Span.speaker_self_id` holds the attribution's surface label, not a Self id;
#: `voice/runner.py::speaker_index` joins it to the entity through resolved mentions.
NAMED_SURFACE = "Fang Yuan"
SLOT = "t:anon:1:s2:1"


def _bank() -> VoiceBank:
    return VoiceBank(voices=parse_speaker_info(SPEAKER_INFO))


def _store(tmp_path: Path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    texts = [
        '"Stop right there," Fang Yuan said.',
        "He walked north along the river.",
        '"Who goes there?" a guard shouted.',
        '"Halt!" the same guard shouted again.',
    ]
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="One",
            source_href="a.html",
            blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)],
        )
    )
    store.add_self(
        Self(
            id=NAMED,
            novel_id="t",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
            kind=TargetKind.SELF,
        )
    )
    store.add_mentions(
        [
            Mention(
                id="m1", novel_id="t", segment_id="s", chapter=1.0, offset=25, block_index=0,
                text="Fang Yuan", alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF, target_id=NAMED,
            )
        ]
    )
    specs = [
        (SpanType.DIALOGUE, NAMED_SURFACE, AttributionMethod.EXPLICIT),
        (SpanType.NARRATION_ACTION, None, AttributionMethod.UNRESOLVED),
        (SpanType.DIALOGUE, SLOT, AttributionMethod.ANONYMOUS_SLOT),
        (SpanType.DIALOGUE, SLOT, AttributionMethod.ANONYMOUS_SLOT),
    ]
    store.add_spans(
        [
            Span(
                id=f"sp{i}", novel_id="t", chapter=1.0, block_index=i, start=0, end=len(texts[i]),
                span_type=kind, text=texts[i], speaker_self_id=speaker, attribution_method=method,
            )
            for i, (kind, speaker, method) in enumerate(specs)
        ]
    )
    store.conn.commit()
    # Casting reads stored persona traits, so run the persona stage exactly as
    # the pipeline does rather than hand-writing bindings.
    build_personas("t", store)
    store.conn.commit()
    return store


def _manifest(out: Path) -> list[dict]:
    return [json.loads(x) for x in (out / "manifest.jsonl").read_text().splitlines() if x.strip()]


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as fh:
        return fh.getnframes() / fh.getframerate()


def test_every_span_gets_a_line_and_a_real_audio_file(tmp_path: Path) -> None:
    out = tmp_path / "audio"
    report = render_novel("t", _store(tmp_path), _bank(), out_dir=out, engine=get_engine("stub"))

    lines = _manifest(out)
    assert report.lines == len(lines) == 4
    assert report.chapters == 1
    for line in lines:
        wav = Path(line["audio_path"])
        assert wav.is_file(), f"no audio written for {line['span_id']}"
        assert _duration(wav) > 0.25  # the stub's floor; a zero-length file would be a broken path
    assert (out / "casting.txt").read_text().strip()


def test_named_narrator_and_anonymous_lines_are_voiced_as_what_they_are(tmp_path: Path) -> None:
    out = tmp_path / "audio"
    report = render_novel("t", _store(tmp_path), _bank(), out_dir=out, engine=get_engine("stub"))
    by_span = {line["span_id"]: line for line in _manifest(out)}

    assert by_span["sp0"]["speaker_label"] == "Fang Yuan"
    assert by_span["sp1"]["speaker_id"] != NAMED  # narration is the narrator's, not the character's
    assert report.character_lines == 1
    assert report.anonymous_lines == 2
    assert report.narrator_lines == 1


def test_an_unnamed_speaker_keeps_one_voice_across_lines(tmp_path: Path) -> None:
    """The slot exists so two unnamed speakers stay distinguishable: the same
    slot must not be re-rolled per line."""
    out = tmp_path / "audio"
    render_novel("t", _store(tmp_path), _bank(), out_dir=out, engine=get_engine("stub"))
    by_span = {line["span_id"]: line for line in _manifest(out)}
    assert by_span["sp2"]["voice"] == by_span["sp3"]["voice"]
    assert by_span["sp2"]["voice"] != by_span["sp0"]["voice"]  # and it is not the named character's voice


def test_a_rerun_with_the_same_seed_recasts_nobody(tmp_path: Path) -> None:
    store = _store(tmp_path)
    voices = []
    for name in ("first", "second"):
        out = tmp_path / name
        render_novel("t", store, _bank(), out_dir=out, engine=get_engine("stub"), seed=11)
        voices.append([(line["span_id"], line["voice"]) for line in _manifest(out)])
    assert voices[0] == voices[1]


def test_casting_can_be_reviewed_without_synthesising(tmp_path: Path) -> None:
    """`synthesize=False` is how casting is reviewed before spending GPU time."""
    out = tmp_path / "audio"
    report = render_novel("t", _store(tmp_path), _bank(), out_dir=out, synthesize=False)
    assert report.lines == 4
    assert len(_manifest(out)) == 4
    assert not list(out.rglob("*.wav"))


def test_a_chapter_filter_renders_only_those_chapters(tmp_path: Path) -> None:
    out = tmp_path / "audio"
    report = render_novel("t", _store(tmp_path), _bank(), out_dir=out, engine=get_engine("stub"), chapters=[2.0])
    assert report.chapters == 1
    assert report.lines == 0
    assert not list(out.rglob("*.wav"))
