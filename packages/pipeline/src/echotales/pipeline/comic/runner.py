"""The comic stages as functions: `ingest`, `understand`, `build`. The CLI and the `comic` job both call these.

Working files for one comic live in `data/novels/<CODE>/comic/` (`pages/`, `masks/`, `understanding.json`); the
voiced audio goes where every other novel's does, and the video under `video/ch<N>/v<K>_<suffix>/` with a line in
that folder's `VERSIONS.md`, per the repository's versioned-output rule.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline import paths
from echotales.pipeline.comic.build import BuildResult, build_episode
from echotales.pipeline.comic.ingest import PageImage, load_pages
from echotales.pipeline.comic.inpaint import get_inpainter
from echotales.pipeline.comic.ocr import get_ocr
from echotales.pipeline.comic.to_graph import ComicGraphReport, comic_to_store
from echotales.pipeline.comic.understand import ComicUnderstanding, understand_pages
from PIL import Image

DEFAULT_CREDIT = "Made with EchoTales"


def comic_root(novel_id: str, data_root: Path | str = paths.DATA_ROOT) -> Path:
    return paths.asset_dir(novel_id, "comic", data_root=data_root)


def ingest_stage(input_path: Path | str, novel_id: str, *, webtoon: bool = False, root: Path | None = None) -> int:
    """Normalise the input to numbered PNG pages under `<root>/pages/`. Returns the page count."""
    root = root or comic_root(novel_id)
    pages = load_pages(input_path, webtoon=webtoon)
    out = root / "pages"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("p*.png"):
        old.unlink()
    for p in pages:
        p.image.save(out / f"p{p.index + 1:03d}.png")
    (root / "pages.json").write_text(
        json.dumps({"source": str(input_path), "webtoon": webtoon, "pages": [p.name for p in pages]}, indent=1),
        encoding="utf-8",
    )
    return len(pages)


def saved_pages(root: Path) -> list[PageImage]:
    meta = json.loads((root / "pages.json").read_text(encoding="utf-8"))
    files = sorted((root / "pages").glob("p*.png"))
    if not files:
        raise FileNotFoundError(f"no ingested pages in {root / 'pages'}; run `echotales comic ingest` first")
    return [PageImage(i, meta["pages"][i], Image.open(f).convert("RGB")) for i, f in enumerate(files)]


def understand_stage(
    novel_id: str, *, ocr: str = "rapidocr", rtl: bool = False, root: Path | None = None
) -> ComicUnderstanding:
    root = root or comic_root(novel_id)
    return understand_pages(saved_pages(root), get_ocr(ocr), rtl=rtl, out_dir=root)


@dataclass(slots=True)
class ComicBuild:
    graph: ComicGraphReport
    video: BuildResult
    version: str
    out_dir: Path


def build_stage(
    store: Store,
    novel_id: str,
    *,
    title: str,
    chapter: float = 1.0,
    chapter_title: str | None = None,
    credit: str = DEFAULT_CREDIT,
    engine: str = "stub",
    bank_kind: str | None = None,
    bank_root: str | Path = "data/voice",
    inpaint: str = "auto",
    depth: bool = False,
    suffix: str = "motion-comic",
    note: str = "",
    trust_speakers: bool = False,
    size: tuple[int, int] = (1280, 720),
    fps: int = 24,
    root: Path | None = None,
    video_root: Path | None = None,
    audio_dir: Path | None = None,
) -> ComicBuild:
    """Graph, voice, timing and video for one comic. Needs `ingest` and `understand` to have run."""
    from echotales.pipeline.voice import get_engine as get_voice_engine
    from echotales.pipeline.voice import render_novel
    from echotales.pipeline.voice.bank import DEFAULT_BANK_KIND, load_bank
    from echotales.pipeline.voice.timing import build_timing

    root = root or comic_root(novel_id)
    und = ComicUnderstanding.load(root / "understanding.json")
    graph = comic_to_store(store, und, novel_id, title, chapter=chapter, chapter_title=chapter_title,
                           source=str(root), trust_speakers=trust_speakers)
    audio_dir = audio_dir or paths.asset_dir(novel_id, "audio")
    bank = load_bank(bank_kind or DEFAULT_BANK_KIND, bank_root)
    render_novel(novel_id, store, bank, out_dir=audio_dir, engine=get_voice_engine(engine), chapters=[chapter])
    timings = build_timing(audio_dir, chapter, write=True)

    base = (video_root or paths.asset_dir(novel_id, "video")) / f"ch{chapter:g}"
    version = f"{paths.next_version(base)}_{suffix}"
    out_dir = base / version
    inpainter = get_inpainter(inpaint) if inpaint != "none" else None
    video = build_episode(
        und, saved_pages(root), timings, out_dir, title=title, credit=credit,
        inpainter=inpainter, masks_dir=root, size=size, fps=fps,
        depth=_depth() if depth else None,
    )
    # Marks this folder as a motion comic for the Studio's comic panel, which lists only these videos.
    (out_dir / "comic.json").write_text(json.dumps({"shots": video.shots, "duration": video.duration}), encoding="utf-8")
    _append_version(base, version, engine, inpainter.name if inpainter else "none", video, note, depth)
    return ComicBuild(graph, video, version, out_dir)


def _depth():
    from echotales.pipeline.comic.parallax import DepthAnythingSmall

    return DepthAnythingSmall()


def _append_version(base: Path, version: str, engine: str, inpaint: str, video: BuildResult, note: str,
                    depth: bool = False) -> None:
    index = base / "VERSIONS.md"
    if not index.exists():
        index.write_text("# Video versions\n\nOne line per version: what was tried and an honest verdict.\n\n", encoding="utf-8")
    verdict = note or "unreviewed"
    line = (
        f"## {version} ({datetime.date.today().isoformat()})\n"
        f"- motion comic, {video.shots} panel shots, {video.duration:.1f}s; voice engine `{engine}`, inpainting `{inpaint}`{', depth parallax' if depth else ''}. "
        f"Verdict: {verdict}\n\n"
    )
    with index.open("a", encoding="utf-8") as fh:
        fh.write(line)
