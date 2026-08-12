"""A small, reused library of short motion clips (xyz.md Step 4, video revision).

The reel that motivated this design (see the conversation, not reproducible
here) makes a single point worth being explicit about: it did **not**
generate a new clip for every cut. It generated 2-3 clips for the whole
episode and reused them constantly, cutting between them and the manhwa's
own still panels in time with the audio. That reuse is the entire reason the
technique is affordable -- a fresh clip per cut would be a fresh generation
per cut, and `director.py` would have no cost budget to work with.

So this module is deliberately small and tag-keyed rather than one-clip-
per-scene: `MOTION_TAGS` is a fixed, short vocabulary (a handful of generic
action/mood beats, plus one idle loop per voice archetype bucket from
`persona/traits.py::TraitProfile.archetype`), each generated **at most
once** and cached under its tag. `director.py` matches a block's content
against this same tag vocabulary via `match_tag` and, on a hit, cuts to the
cached clip instead of panning the still panel.

**Clips are stored as PNG frame sequences, not an encoded video.** Nothing
in this project's dependency set can write a video container, and adding one
just for intermediate storage would be pure overhead -- `compose.py` already
needs `ffmpeg` on the machine for the final mux, so frame directories that
`ffmpeg`'s `image2` demuxer reads directly are the lightest thing that could
work, mirroring the "no dependency the final consumer doesn't already need"
call `render/panels.py`'s PNG writer makes.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from echotales.pipeline.render._png import write_solid_png
from echotales.pipeline.spans.delivery import DeliveryPolarity, dominant_polarity, extract_delivery_markers

#: Fixed vocabulary of reusable motion beats, independent of any one
#: character or scene. Kept short deliberately -- see the module docstring.
GENERIC_TAGS: tuple[str, ...] = (
    "clash",
    "wind",
    "flame",
    "impact",
)

#: Keyword -> generic tag. Whole-word matched against a block's span text,
#: same style as `traits.py::_AGE_HONORIFICS`. Longest key wins on overlap
#: by virtue of `match_tag` checking `GENERIC_KEYWORDS` before polarity.
GENERIC_KEYWORDS: dict[str, str] = {
    "sword": "clash", "blade": "clash", "clashed": "clash", "clang": "clash",
    "parried": "clash", "strike": "clash",
    "wind": "wind", "gust": "wind", "breeze": "wind", "robe fluttered": "wind",
    "flame": "flame", "fire": "flame", "burned": "flame", "blazing": "flame",
    "explosion": "impact", "shattered": "impact", "collided": "impact",
    "slammed": "impact", "crashed": "impact",
}

#: Delivery polarity -> generic tag, the fallback when no keyword hits but
#: the line is clearly heightened. Reuses `spans/delivery.py` rather than a
#: second emotion vocabulary -- one signal, two consumers (voice delivery,
#: motion-clip choice).
POLARITY_TAGS: dict[DeliveryPolarity, str] = {
    DeliveryPolarity.HEIGHTENED: "impact",
}


def match_tag(text: str) -> str | None:
    """The motion-clip tag this block's text cues, if any.

    Keyword match first (concrete, high precision), delivery polarity second
    (broader, lower precision) -- mirrors the tiered-confidence pattern the
    speaker-attribution ladder uses elsewhere in this pipeline.
    """
    blob = text.casefold()
    for term in sorted(GENERIC_KEYWORDS, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", blob):
            return GENERIC_KEYWORDS[term]

    markers = extract_delivery_markers(text)
    polarity = dominant_polarity(markers)
    if polarity is not None and polarity in POLARITY_TAGS:
        return POLARITY_TAGS[polarity]
    return None


@dataclass(slots=True)
class MotionClipRequest:
    """One clip to render."""

    tag: str
    prompt: str
    out_dir: Path
    seed_image: Path | None = None
    num_frames: int = 24
    fps: int = 12
    width: int = 1024
    height: int = 576


class MotionClipEngine(Protocol):
    """What the pipeline needs from an image-to-video backend."""

    name: str

    def generate(self, request: MotionClipRequest) -> Path:
        """Render `request.num_frames` PNGs into `request.out_dir` and
        return that directory."""
        ...


@dataclass(slots=True)
class StubMotionEngine:
    """Writes a real short frame sequence -- a solid colour that shifts hue
    frame to frame, so a stub-rendered clip is visibly *moving* when played
    back, not just a still repeated.

    Mirrors `render/panels.py::StubImageEngine`'s reasoning: `director.py`
    and `compose.py` open these files and read the frame count, so a stub
    that wrote nothing would leave that path untested.
    """

    name: str = "stub"

    def generate(self, request: MotionClipRequest) -> Path:
        request.out_dir.mkdir(parents=True, exist_ok=True)
        base = hash(request.tag)
        for i in range(request.num_frames):
            shift = i * 6
            colour = (
                (base % 200 + 30 + shift) % 256,
                ((base // 200) % 200 + 30 + shift) % 256,
                ((base // 40000) % 200 + 30 + shift) % 256,
            )
            write_solid_png(
                request.out_dir / f"frame{i:04d}.png",
                request.width,
                request.height,
                colour,
            )
        return request.out_dir


@dataclass(slots=True)
class SVDEngine:
    """Stable Video Diffusion img2vid, loaded lazily.

    Same lazy-load discipline as `voice/engine.py::ChatterboxEngine` and
    `render/panels.py::SDXLEngine`: importing `torch`/`diffusers` and
    pulling the (multi-GB) weights only happens on first real use.
    Conditioned on a still frame (`request.seed_image`, typically one of
    `panels.py`'s already-rendered panels) rather than generating from text,
    because SVD is an image-to-video model, not a text-to-video one -- this
    is also what keeps a clip visually anchored to this novel's style
    instead of drifting to a generic one.
    """

    name: str = "svd"
    model_id: str = "stabilityai/stable-video-diffusion-img2vid"
    device: str = "cuda"
    _pipe: object | None = None

    def _ensure_pipe(self) -> object:
        if self._pipe is None:
            import torch  # type: ignore[import-not-found]
            from diffusers import StableVideoDiffusionPipeline  # type: ignore[import-not-found]

            self._pipe = StableVideoDiffusionPipeline.from_pretrained(
                self.model_id, torch_dtype=torch.float16
            ).to(self.device)
        return self._pipe

    def generate(self, request: MotionClipRequest) -> Path:
        from diffusers.utils import load_image  # type: ignore[import-not-found]

        if request.seed_image is None:
            raise ValueError("SVDEngine requires request.seed_image")

        pipe = self._ensure_pipe()
        image = load_image(str(request.seed_image)).resize((request.width, request.height))
        frames = pipe(  # type: ignore[operator]
            image, num_frames=request.num_frames
        ).frames[0]

        request.out_dir.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(frames):
            frame.save(request.out_dir / f"frame{i:04d}.png")
        return request.out_dir


def get_engine(name: str = "stub", **kwargs: object) -> MotionClipEngine:
    if name == "stub":
        return StubMotionEngine(**kwargs)  # type: ignore[arg-type]
    if name == "svd":
        return SVDEngine(**kwargs)  # type: ignore[arg-type]
    raise ValueError(f"unknown motion engine {name!r}; expected 'stub' or 'svd'")


@dataclass(slots=True)
class MotionClip:
    tag: str
    frames_dir: str
    num_frames: int
    fps: int


@dataclass(slots=True)
class MotionLibraryReport:
    novel_id: str
    clips: int = 0
    skipped_cached: int = 0
    engine: str = "stub"

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.clips} motion clips ({self.engine}); "
            f"{self.skipped_cached} reused from cache"
        )


def build_motion_library(
    novel_id: str,
    *,
    out_dir: str | Path = "data/motion",
    engine: MotionClipEngine | None = None,
    seed_images: dict[str, Path] | None = None,
    tags: tuple[str, ...] = GENERIC_TAGS,
    num_frames: int = 24,
    fps: int = 12,
) -> MotionLibraryReport:
    """Generate the fixed clip set once, caching every tag by name.

    `seed_images` maps a tag to a representative still (usually one of
    `panels.py`'s outputs) to condition a real img2vid engine on; the stub
    engine ignores it entirely. A tag with no seed image and a real engine
    is skipped rather than guessed at -- an unconditioned clip would not
    look like this novel.
    """
    engine = engine or get_engine("stub")
    out_dir = Path(out_dir) / novel_id
    report = MotionLibraryReport(novel_id=novel_id, engine=engine.name)
    seed_images = seed_images or {}

    manifest: dict[str, MotionClip] = {}
    for tag in tags:
        frames_dir = out_dir / tag
        marker = frames_dir / "clip.json"

        if marker.exists():
            report.skipped_cached += 1
            manifest[tag] = MotionClip(**json.loads(marker.read_text(encoding="utf-8")))
            continue

        if engine.name != "stub" and tag not in seed_images:
            continue

        engine.generate(
            MotionClipRequest(
                tag=tag,
                prompt=f"{tag}, motion loop, manhwa illustration style",
                out_dir=frames_dir,
                seed_image=seed_images.get(tag),
                num_frames=num_frames,
                fps=fps,
            )
        )
        clip = MotionClip(tag=tag, frames_dir=str(frames_dir), num_frames=num_frames, fps=fps)
        marker.write_text(json.dumps(asdict(clip)), encoding="utf-8")
        manifest[tag] = clip
        report.clips += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps({tag: asdict(clip) for tag, clip in manifest.items()}, indent=2),
        encoding="utf-8",
    )
    return report


def load_motion_library(novel_id: str, out_dir: str | Path = "data/motion") -> dict[str, MotionClip]:
    """Reload a previously built library, keyed by tag."""
    manifest_path = Path(out_dir) / novel_id / "manifest.json"
    if not manifest_path.exists():
        return {}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {tag: MotionClip(**data) for tag, data in raw.items()}
