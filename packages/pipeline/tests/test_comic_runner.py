"""The comic stages end to end on a synthetic comic: ingest -> understand -> build, plus the `comic` job."""

from __future__ import annotations

import pytest

pytest.importorskip("scipy")
pytest.importorskip("cv2")

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from echotales.core.store import Store
from echotales.pipeline.comic import runner
from echotales.pipeline.comic.ocr import TextLine
from echotales.pipeline.voice.bank import VoiceBank, parse_speaker_info

INFO = "ID  AGE  GENDER  ACCENTS  REGION\np225  23  F    English    Southern  England\np226  22  M    English    Surrey\n"


class FakeOcr:
    name = "fake"

    def read(self, image):
        return [TextLine((340, 75, 480, 95), "Hello", 0.99), TextLine((350, 98, 470, 118), "there.", 0.99)]


def _page(path: Path) -> None:
    rng = np.random.default_rng(7)
    arr = np.full((700, 600, 3), 255, dtype=np.uint8)
    arr[20:320, 20:580] = rng.integers(10, 90, size=(300, 560, 3), dtype=np.uint8)
    arr[360:680, 20:580] = rng.integers(10, 90, size=(320, 560, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    d.ellipse([300, 50, 520, 150], fill=(250, 250, 250))
    d.polygon([(340, 130), (380, 140), (300, 215)], fill=(250, 250, 250))
    img.save(path)


def test_ingest_understand_build_writes_versioned_video(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    _page(src / "page1.png")
    root = tmp_path / "comic"
    assert runner.ingest_stage(src, "pc", root=root) == 1
    monkeypatch.setattr(runner, "get_ocr", lambda name: FakeOcr())
    und = runner.understand_stage("pc", root=root)
    assert [b.text for b in und.bubbles()] == ["Hello there."]
    monkeypatch.setattr("echotales.pipeline.voice.bank.load_bank",
                        lambda kind, root_: VoiceBank(voices=parse_speaker_info(INFO)))
    store = Store(str(tmp_path / "c.db"))
    built = runner.build_stage(
        store, "pc", title="T", credit="Credit line", root=root, video_root=tmp_path / "video",
        audio_dir=tmp_path / "audio", size=(320, 180), fps=8, suffix="unit-test", note="synthetic", inpaint="cv",
    )
    assert built.version == "v1_unit-test"
    assert (built.out_dir / "episode.mp4").is_file() and (built.out_dir / "episode.srt").is_file()
    versions = (tmp_path / "video" / "ch1" / "VERSIONS.md").read_text()
    assert "v1_unit-test" in versions and "synthetic" in versions
    assert (built.out_dir / "comic.json").is_file()  # the Studio lists comic videos by this marker
    again = runner.build_stage(
        store, "pc", title="T", root=root, video_root=tmp_path / "video", audio_dir=tmp_path / "audio",
        size=(320, 180), fps=8, suffix="second", inpaint="cv",
    )
    assert again.version == "v2_second"  # a rerun never overwrites the previous version


def test_comic_job_refuses_an_unknown_source_by_name(tmp_path: Path, monkeypatch) -> None:
    import pytest

    from echotales.pipeline import jobs

    monkeypatch.setattr(runner, "comic_root", lambda novel_id, data_root=None: tmp_path / "comic")
    with pytest.raises(ValueError, match="no comic source named 'x'"):
        jobs._run_comic(Store(str(tmp_path / "c.db")), "pc", {"stage": "ingest", "source": "../../etc/x"})
    (tmp_path / "comic" / "source").mkdir(parents=True)
    src = tmp_path / "comic" / "source" / "ep"
    src.mkdir()
    _page(src / "p1.png")
    out = jobs._run_comic(Store(str(tmp_path / "c.db")), "pc", {"stage": "ingest", "source": "ep"})
    assert out == [str(tmp_path / "comic" / "pages.json")]
