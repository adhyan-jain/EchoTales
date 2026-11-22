"""Motion-comic planning and a real ffmpeg render on a synthetic comic with the stub voice engine."""

from __future__ import annotations

import pytest

pytest.importorskip("scipy")
pytest.importorskip("cv2")

import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from echotales.core.store import Store
from echotales.pipeline.comic.build import camera_window, plan_shots, build_episode
from echotales.pipeline.comic.bubbles import Bubble
from echotales.pipeline.comic.ingest import PageImage
from echotales.pipeline.comic.to_graph import comic_to_store
from echotales.pipeline.comic.understand import ComicUnderstanding, PageUnderstanding, PanelUnderstanding
from echotales.pipeline.voice.bank import VoiceBank, parse_speaker_info
from echotales.pipeline.voice.engine import get_engine
from echotales.pipeline.voice.runner import render_novel
from echotales.pipeline.voice.timing import build_timing

INFO = "ID  AGE  GENDER  ACCENTS  REGION\np225  23  F    English    Southern  England\np226  22  M    English    Surrey\n"


def _bubble(i: int, panel: int, text: str, kind: str = "speech", speaker: str | None = "Character A") -> Bubble:
    return Bubble(id=f"p001b{i:02d}", panel_index=panel, text=text, kind=kind, text_box=(10, 10, 60, 30),
                  box=(5, 5, 70, 40), speaker=speaker, order=i)


def _und() -> ComicUnderstanding:
    panels = [
        PanelUnderstanding(0, (10, 10, 390, 190), [_bubble(1, 0, "Hello there, little cat.")]),
        PanelUnderstanding(1, (10, 210, 390, 390), []),
        PanelUnderstanding(2, (10, 410, 390, 590), [_bubble(2, 2, "Meanwhile.", "narration", None), _bubble(3, 2, "Oh no!")]),
    ]
    return ComicUnderstanding([PageUnderstanding(0, "p1.png", (400, 600), panels, mask_file="")])


def _page() -> Image.Image:
    rng = np.random.default_rng(3)
    return Image.fromarray(rng.integers(0, 255, size=(600, 400, 3), dtype=np.uint8))


def test_plan_shots_times_panels_from_voice_and_holds_silent_ones() -> None:
    from types import SimpleNamespace as T
    timings = [T(block_index=0, duration=2.0), T(block_index=1, duration=1.0), T(block_index=2, duration=1.5)]
    shots = plan_shots(_und(), timings, lead=0.3, tail=0.4, hold=2.0)
    assert [s.panel_index for s in shots] == [0, 1, 2]
    assert shots[0].duration == pytest.approx(0.3 + 2.0 + 0.4)
    assert shots[1].duration == 2.0 and shots[1].lines == []
    assert shots[2].duration == pytest.approx(0.3 + 1.0 + 1.5 + 0.4)
    assert shots[2].lines[0].offset == pytest.approx(0.3) and shots[2].lines[1].offset == pytest.approx(1.3)


def test_camera_window_covers_the_frame_aspect_and_stays_inside_the_panel() -> None:
    for panel in [(0, 0, 1000, 400), (0, 0, 400, 1000), (0, 0, 640, 360)]:
        for zoom, pan in [(1.0, -1.0), (1.12, 0.0), (1.06, 1.0)]:
            x0, y0, x1, y1 = camera_window(panel, 16 / 9, zoom, pan)
            assert abs((x1 - x0) / (y1 - y0) - 16 / 9) < 0.01
            assert panel[0] - 0.5 <= x0 and x1 <= panel[2] + 0.5 and panel[1] - 0.5 <= y0 and y1 <= panel[3] + 0.5


def test_camera_window_never_leaves_a_full_page_panel_by_float_noise() -> None:
    # A page-wide strip at x0 = 0 panned right: the window's left edge came out as -1.4e-14 and PIL's
    # resize(box=...) raised "box offset can't be negative" (LotNB ch100 webtoon build).
    page = Image.new("RGB", (720, 1006), (200, 200, 200))
    for panel in [(0, 0, 720, 33), (0, 133, 720, 279), (0, 20, 720, 145)]:
        for pan in np.linspace(-1.0, 1.0, 11):
            win = camera_window(panel, 1280 / 720, 1.06, float(pan))
            assert win[0] >= panel[0] and win[1] >= panel[1] and win[2] <= panel[2] and win[3] <= panel[3]
            page.resize((320, 180), Image.Resampling.BICUBIC, box=win)


def test_failed_encode_leaves_no_episode_mp4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import echotales.pipeline.comic.build as build_mod

    und = _und()
    store = Store(str(tmp_path / "c.db"))
    comic_to_store(store, und, "pc", "Pepper and Carrot", trust_speakers=True)
    audio = tmp_path / "audio"
    render_novel("pc", store, VoiceBank(voices=parse_speaker_info(INFO)), out_dir=audio, engine=get_engine("stub"))
    timings = build_timing(audio, 1.0, write=True)

    def boom(*_a, **_k):
        raise ValueError("synthetic frame failure")
        yield  # pragma: no cover

    monkeypatch.setattr(build_mod, "_shot_frames", boom)
    with pytest.raises(ValueError, match="synthetic"):
        build_episode(und, [PageImage(0, "p1.png", _page())], timings, tmp_path / "out",
                      title="T", credit="c", size=(320, 180), fps=8)
    assert not list((tmp_path / "out").glob("*.mp4"))


def test_build_episode_renders_a_video_with_credit_and_subtitles(tmp_path: Path) -> None:
    und = _und()
    store = Store(str(tmp_path / "c.db"))
    comic_to_store(store, und, "pc", "Pepper and Carrot", trust_speakers=True)
    audio = tmp_path / "audio"
    render_novel("pc", store, VoiceBank(voices=parse_speaker_info(INFO)), out_dir=audio, engine=get_engine("stub"))
    timings = build_timing(audio, 1.0, write=True)
    result = build_episode(
        und, [PageImage(0, "p1.png", _page())], timings, tmp_path / "out",
        title="Test Episode", credit="Test comic by Someone, CC BY 4.0", size=(320, 180), fps=8,
    )
    assert result.video.is_file() and result.srt.is_file()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags=comment",
                            "-of", "default=nw=1", str(result.video)], capture_output=True, text=True).stdout
    duration = float(next(x for x in probe.splitlines() if x.startswith("duration=")).split("=")[1])
    assert abs(duration - result.duration) < 0.5
    assert "CC BY 4.0" in probe
    assert "Hello there" in result.srt.read_text()


class _FakeDepth:
    name = "fake"

    def depth(self, image):
        d = np.zeros((image.height, image.width), dtype=np.float32)
        d[:, image.width // 2:] = 1.0
        return d


def test_depth_parallax_changes_the_frames_but_not_the_timeline(tmp_path: Path) -> None:
    und = _und()
    store = Store(str(tmp_path / "c.db"))
    comic_to_store(store, und, "pc", "T", trust_speakers=True)
    audio = tmp_path / "audio"
    render_novel("pc", store, VoiceBank(voices=parse_speaker_info(INFO)), out_dir=audio, engine=get_engine("stub"))
    timings = build_timing(audio, 1.0, write=True)
    kw = dict(title="T", credit="c", size=(160, 90), fps=8)
    flat = build_episode(und, [PageImage(0, "p.png", _page())], timings, tmp_path / "a", **kw)
    deep = build_episode(und, [PageImage(0, "p.png", _page())], timings, tmp_path / "b", depth=_FakeDepth(), **kw)
    assert deep.duration == flat.duration and deep.video.is_file()
    assert deep.video.read_bytes() != flat.video.read_bytes()


def test_shot_frames_keep_every_shot_on_its_audio_start() -> None:
    """60 shots of 2.31 s: per-shot rounding ended ~1 s early against audio placed in seconds (EVOLUTION 4.183)."""
    from echotales.pipeline.comic.build import Shot, shot_frame_counts

    shots = [Shot(0, i, (0, 0, 1, 1), 2.31) for i in range(60)]
    counts = shot_frame_counts(shots, 24)
    assert abs(sum(counts) - round(60 * 2.31 * 24)) <= 1
    assert all(n >= 1 for n in counts)
