"""`voice/runner.py::render_novel`, the audio orchestrator, end to end.

docs/status/STATUS.md recorded it as having zero direct test coverage: casting,
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


def _with_guessed_line(tmp_path: Path, confidence: float) -> Store:
    """Chapter 2: one line the contextual-LLM tier credited to Fang Yuan."""
    store = _store(tmp_path)
    text = '"Leave now," he said.'
    store.add_chapter(Chapter(novel_id="t", number=2.0, title="Two", source_href="b.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)]))
    store.add_spans([Span(id="g0", novel_id="t", chapter=2.0, block_index=0, start=0, end=len(text),
                          span_type=SpanType.DIALOGUE, text=text, speaker_self_id=NAMED_SURFACE,
                          attribution_method=AttributionMethod.CONTEXTUAL_LLM, confidence=confidence)])
    store.conn.commit()
    return store


def test_a_studio_voice_override_reaches_the_audio(tmp_path: Path) -> None:
    """`POST .../characters/<id>/voice` stored the choice and showed it, but casting never read it (audit M3)."""
    from echotales.core.enums import AssertedBy
    from echotales.core.interval import FuzzyInterval
    from echotales.core.models import Attribute
    from echotales.pipeline.persona.build import persona_at

    store = _store(tmp_path)
    render_novel("t", store, _bank(), out_dir=tmp_path / "before", engine=get_engine("stub"))
    default = {l["span_id"]: l for l in _manifest(tmp_path / "before")}["sp0"]["voice"]
    chosen = next(v.speaker_id for v in _bank().voices if v.speaker_id != default and v.gender == "male")

    store.add_attribute("t", Attribute(
        target_kind=TargetKind.PERSONA, target_id=persona_at(store, NAMED), key="voice_override", value=chosen,
        learned_at_pos=DiscoursePosition(chapter=0, offset=0), observer_id="reviewer", asserted_by=AssertedBy.NARRATOR,
        evidence="test", interval=FuzzyInterval.open_ended(0.0),
    ))
    store.conn.commit()
    render_novel("t", store, _bank(), out_dir=tmp_path / "after", engine=get_engine("stub"))
    assert {l["span_id"]: l for l in _manifest(tmp_path / "after")}["sp0"]["voice"] == chosen


class _CountingEngine:
    """Wraps the stub engine; optionally dies on the Nth call, the way a CUDA out-of-memory error would."""

    name = "stub"

    def __init__(self, fail_on_call: int | None = None) -> None:
        self._inner = get_engine("stub")
        self.calls = 0
        self._fail_on = fail_on_call

    def synthesize(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self._fail_on is not None and self.calls == self._fail_on:
            raise RuntimeError("CUDA out of memory")
        return self._inner.synthesize(request)


def test_a_rerun_reuses_every_unchanged_line(tmp_path: Path) -> None:
    store, out = _store(tmp_path), tmp_path / "audio"
    first = _CountingEngine()
    render_novel("t", store, _bank(), out_dir=out, engine=first)
    second = _CountingEngine()
    report = render_novel("t", store, _bank(), out_dir=out, engine=second)

    assert first.calls == 4 and second.calls == 0
    assert report.reused_lines == 4


def test_a_failure_in_a_later_chapter_keeps_the_finished_chapters(tmp_path: Path) -> None:
    store, out = _with_guessed_line(tmp_path, 0.9), tmp_path / "audio"
    try:
        render_novel("t", store, _bank(), out_dir=out, engine=_CountingEngine(fail_on_call=5))
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("the engine failure should propagate")

    assert (out / "ch1" / "chapter.wav").is_file()  # chapter 1 finished before chapter 2's line failed
    assert len(_manifest(out)) == 4

    resumed = _CountingEngine()
    render_novel("t", store, _bank(), out_dir=out, engine=resumed)
    assert resumed.calls == 1  # only the line that failed is synthesised again


def _with_unknown_and_reviewed_lines(tmp_path: Path) -> Store:
    """Chapter 2: a quoted line nobody placed, and one a reviewer put in an anonymous slot."""
    store = _store(tmp_path)
    texts = ['"Who is there?" a voice asked.', '"Stand back," she said.']
    store.add_chapter(Chapter(novel_id="t", number=2.0, title="Two", source_href="b.html",
                              blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)]))
    store.add_spans([
        Span(id="u0", novel_id="t", chapter=2.0, block_index=0, start=0, end=len(texts[0]),
             span_type=SpanType.DIALOGUE, text=texts[0], attribution_method=AttributionMethod.UNRESOLVED),
        Span(id="h0", novel_id="t", chapter=2.0, block_index=1, start=0, end=len(texts[1]),
             span_type=SpanType.DIALOGUE, text=texts[1], speaker_self_id="t:anon:2:1",
             attribution_method=AttributionMethod.HUMAN, confidence=1.0),
    ])
    store.conn.commit()
    return store


def test_an_unplaced_quoted_line_is_not_voiced_by_the_narrator(tmp_path: Path) -> None:
    """RI ch1: 14 of 29 dialogue lines were "unknown" and all fell to the narrator's voice."""
    out = tmp_path / "audio"
    report = render_novel("t", _with_unknown_and_reviewed_lines(tmp_path), _bank(), out_dir=out,
                          engine=get_engine("stub"))
    by_span = {line["span_id"]: line for line in _manifest(out)}

    narrator_voice = by_span["sp1"]["voice"]  # chapter 1's narration
    assert by_span["u0"]["speaker_label"] == "Unknown speaker"
    assert by_span["u0"]["voice"] != narrator_voice
    assert report.unattributed_lines == 1
    # a reviewer's anonymous slot keeps the slot path and its label
    assert by_span["h0"]["speaker_label"] == "Unknown Speaker 1"


def test_a_guessed_speaker_is_not_given_the_characters_own_voice(tmp_path: Path) -> None:
    """The LLM tier (confidence 0.65) was right 12 times in 28; a wrong guess in
    the character's own voice is indistinguishable from a correct line."""
    out = tmp_path / "audio"
    report = render_novel("t", _with_guessed_line(tmp_path, 0.65), _bank(), out_dir=out, synthesize=False)
    by_span = {line["span_id"]: line for line in _manifest(out)}
    assert by_span["g0"]["voice"] != by_span["sp0"]["voice"]  # sp0 is Fang Yuan, explicitly tagged
    assert by_span["g0"]["speaker_label"] == "Fang Yuan (unconfirmed)"
    assert report.unconfirmed_lines == 1


def test_a_confident_tag_and_a_zero_floor_keep_the_character_voice(tmp_path: Path) -> None:
    for confidence, floor in ((0.95, 0.7), (0.65, 0.0)):
        out = tmp_path / f"audio-{confidence}-{floor}"
        render_novel("t", _with_guessed_line(tmp_path / f"db-{confidence}-{floor}", confidence), _bank(),
                     out_dir=out, synthesize=False, min_character_confidence=floor)
        by_span = {line["span_id"]: line for line in _manifest(out)}
        assert by_span["g0"]["voice"] == by_span["sp0"]["voice"]


def test_each_chapter_gets_one_playable_track_in_reading_order(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from echotales.pipeline.voice.export import gaps_for

    out = tmp_path / "audio"
    report = render_novel("t", _store(tmp_path), _bank(), out_dir=out, engine=get_engine("stub"))
    track = out / "ch1" / "chapter.wav"
    assert report.chapter_tracks == [str(track)]
    lines = _manifest(out)
    pauses = gaps_for([SimpleNamespace(**x) for x in lines])
    expected = sum(_duration(Path(x["audio_path"])) for x in lines) + sum(pauses)
    assert abs(_duration(track) - expected) < 0.01


def test_a_dry_run_writes_no_chapter_track(tmp_path: Path) -> None:
    out = tmp_path / "audio"
    report = render_novel("t", _store(tmp_path), _bank(), out_dir=out, synthesize=False)
    assert report.chapter_tracks == []
    assert not (out / "ch1" / "chapter.wav").exists()
