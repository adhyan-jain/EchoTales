"""Panel image generation: `PanelCast` -> one cached image per block.

Same shape as `voice/engine.py` (`Protocol`, stub, lazy-loaded real backend)
and for the same reason: naming a capability rather than a vendor means
swapping SDXL for another local model later is a config change, not a
rewrite. SDXL is the default because it is the one image backend that is
genuinely free to run locally -- no API key, no per-render cost -- which
matters for a dev phase with no generation budget.

**Cached by `(chapter, block_index)`, generated at most once.** A 199-chapter
novel has thousands of blocks; re-generating an already-rendered panel on
every run would make iteration on `director.py`/`compose.py` prohibitively
slow even before cost is a factor. `render_panels` skips any block whose
output file already exists.

**Only story-bearing blocks get a panel.** A heading or translator's note has
nothing to draw -- mirrors `BlockType.is_story_content`, the same filter
identity processing already applies upstream.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from echotales.core.enums import ReferenceMode, SpanType
from echotales.core.models import Chapter, Mention, Span
from echotales.core.store import Store
from echotales.pipeline.persona.prompt import NEGATIVE_PROMPT, build_image_prompt
from echotales.pipeline.persona.runner import get_panel_cast
from echotales.pipeline.render._png import write_solid_png

log = logging.getLogger(__name__)


@dataclass(slots=True)
class PanelImageRequest:
    """One panel to render."""

    prompt: str
    out_path: Path
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    seed: int = 0
    #: Reference sheets for the characters in frame
    #: (`persona/reference_gen.py`), used as IP-Adapter conditioning so the
    #: same character keeps the same face between panels. Empty means
    #: prompt-only generation, which every engine must still support --
    #: incidental characters never get a sheet.
    reference_images: list[Path] = field(default_factory=list)
    #: IP-Adapter scale. 0.6-0.7 is the working range: strong enough to
    #: carry identity, loose enough to let the prompt choose the pose. At
    #: 1.0 every panel reproduces the reference sheet's neutral front view.
    reference_weight: float = 0.65


class PanelImageEngine(Protocol):
    """What the pipeline needs from an image backend."""

    name: str

    def generate(self, request: PanelImageRequest) -> Path:
        """Render one panel to `request.out_path` and return it."""
        ...


@dataclass(slots=True)
class StubImageEngine:
    """Writes a real, small solid-colour PNG -- no Pillow, no GPU.

    Deliberately not a no-op, mirroring `voice/engine.py::StubEngine`'s
    reasoning: downstream code (`director.py`, `compose.py`) opens these
    files and reads their dimensions, so a stub that wrote nothing would
    leave that path untested. The colour is derived from the prompt so two
    different panels are visibly distinguishable in a stub-rendered run.
    """

    name: str = "stub"

    def generate(self, request: PanelImageRequest) -> Path:
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        colour = (
            hash(request.prompt) % 200 + 30,
            (hash(request.prompt) // 200) % 200 + 30,
            (hash(request.prompt) // 40000) % 200 + 30,
        )
        write_solid_png(request.out_path, request.width, request.height, colour)
        return request.out_path


@dataclass(slots=True)
class SDXLEngine:
    """Stable Diffusion XL, loaded lazily.

    Import and model load happen on first use, never at construction --
    same discipline as `voice/engine.py::ChatterboxEngine` -- so merely
    selecting this backend does not pull several GB of weights onto the GPU
    during an unrelated pipeline stage.
    """

    name: str = "sdxl"
    model_id: str = "stabilityai/stable-diffusion-xl-base-1.0"
    device: str = "cuda"
    steps: int = 30
    guidance_scale: float = 7.0
    _pipe: object | None = None

    def _ensure_pipe(self) -> object:
        if self._pipe is None:
            import torch  # type: ignore[import-not-found]
            from diffusers import StableDiffusionXLPipeline  # type: ignore[import-not-found]

            self._pipe = StableDiffusionXLPipeline.from_pretrained(
                self.model_id, torch_dtype=torch.float16
            ).to(self.device)
        return self._pipe

    def generate(self, request: PanelImageRequest) -> Path:
        import torch  # type: ignore[import-not-found]

        pipe = self._ensure_pipe()
        generator = torch.Generator(device=self.device).manual_seed(request.seed)
        image = pipe(  # type: ignore[operator]
            prompt=request.prompt,
            negative_prompt=request.negative_prompt or None,
            width=request.width,
            height=request.height,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance_scale,
            generator=generator,
        ).images[0]
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(request.out_path)
        return request.out_path


@dataclass(slots=True)
class MangaDiffusersEngine:
    """Manga-style panels with IP-Adapter reference conditioning.

    **The checkpoint carries the style, not the prompt.** SDXL base and
    SD1.5 base both produce photorealistic or semi-realistic output however
    hard a prompt argues otherwise, so the default here is an anime/manga
    finetune. If output comes back photorealistic, the checkpoint is wrong
    and swapping it is the fix -- rewording the prompt is not.

    **IP-Adapter is what makes a character survive between panels.** Each
    present character's reference sheet (`persona/reference_gen.py`) is fed
    as image conditioning at `reference_weight`. When no sheet exists -- an
    incidental character, or a run before `generate_references` -- the call
    degrades to prompt-only rather than failing: a panel with a
    less-consistent face is worth having, a crashed render is not. Every
    such degradation is logged, because silently losing conditioning looks
    identical to having it.

    Multi-character panels are capped at `max_references`: IP-Adapter
    blends the images it is given, and past two the blend stops resembling
    any of them. The rest of the cast stays in the prompt as background
    figures, which is the same principal/background split
    `plans.md` Phase 10 specifies for 3+ character panels.
    """

    name: str = "manga"
    #: An anime/manga finetune, not a photorealistic base -- see the class
    #: docstring. Overridable so a locally-downloaded checkpoint can be
    #: pointed at without a code change.
    model_id: str = "Meina/MeinaMix_V11"
    ip_adapter_repo: str = "h94/IP-Adapter"
    ip_adapter_weight: str = "ip-adapter_sd15.bin"
    device: str = "cuda"
    steps: int = 28
    guidance_scale: float = 7.0
    max_references: int = 2
    #: Convert the result to greyscale after generation.
    #:
    #: The prompt asks for monochrome and the negative prompt rejects
    #: colour, and the checkpoint produces colour anyway -- it is an anime
    #: *colour* model, and that is what it knows. Measured on the first real
    #: generation: green robes, brown eyes, full saturation, against a
    #: negative prompt containing "color, colored". Rather than fight the
    #: checkpoint with prompt wording that demonstrably does not work, the
    #: conversion is done deterministically here, where it cannot fail. The
    #: checkpoint still earns its place: it supplies the anatomy, the
    #: linework and the xianxia costume vocabulary that a photorealistic
    #: base cannot.
    monochrome: bool = True
    _pipe: object | None = None
    _ip_loaded: bool = False

    def _ensure_pipe(self, want_ip: bool) -> object:
        if self._pipe is None:
            import torch  # type: ignore[import-not-found]
            from diffusers import StableDiffusionPipeline  # type: ignore[import-not-found]

            self._pipe = StableDiffusionPipeline.from_pretrained(
                self.model_id, torch_dtype=torch.float16, safety_checker=None
            ).to(self.device)

        if want_ip and not self._ip_loaded:
            try:
                self._pipe.load_ip_adapter(  # type: ignore[attr-defined]
                    self.ip_adapter_repo,
                    subfolder="models",
                    weight_name=self.ip_adapter_weight,
                )
                self._ip_loaded = True
            except Exception as exc:  # noqa: BLE001 - degrade, do not crash
                log.warning(
                    "IP-Adapter unavailable (%s); panels will be prompt-only "
                    "and character identity will drift between panels",
                    exc,
                )
        return self._pipe

    def generate(self, request: PanelImageRequest) -> Path:
        import torch  # type: ignore[import-not-found]
        from diffusers.utils import load_image  # type: ignore[import-not-found]

        refs = [p for p in request.reference_images if Path(p).exists()][
            : self.max_references
        ]
        if request.reference_images and not refs:
            log.warning(
                "no reference sheet found on disk for %s; prompt-only fallback",
                request.out_path.name,
            )

        pipe = self._ensure_pipe(want_ip=bool(refs))
        kwargs: dict[str, object] = {}

        if self._ip_loaded:
            # **Once the adapter is loaded it can never be skipped.** Loading
            # it rewrites the UNet's attention processors, and they read
            # `added_cond_kwargs["image_embeds"]` unconditionally -- a call
            # without `ip_adapter_image` passes None straight into
            # `process_encoder_hidden_states` and raises. Panels alternate
            # between having a reference and not (most blocks name nobody
            # with a sheet), so this is the common path, not an edge case:
            # the real run crashed on the first unconditioned panel after
            # the first conditioned one.
            #
            # Rather than unload and reload per panel -- seconds of GPU
            # churn on every block -- an unconditioned panel passes a blank
            # image at scale 0.0, which is arithmetically the same as no
            # conditioning at all.
            if refs:
                pipe.set_ip_adapter_scale(request.reference_weight)  # type: ignore[attr-defined]
                kwargs["ip_adapter_image"] = [load_image(str(p)) for p in refs]
            else:
                from PIL import Image

                pipe.set_ip_adapter_scale(0.0)  # type: ignore[attr-defined]
                kwargs["ip_adapter_image"] = [
                    Image.new("RGB", (224, 224), (255, 255, 255))
                ]

        generator = torch.Generator(device=self.device).manual_seed(request.seed)
        image = pipe(  # type: ignore[operator]
            prompt=request.prompt,
            negative_prompt=request.negative_prompt or None,
            width=request.width,
            height=request.height,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance_scale,
            generator=generator,
            **kwargs,
        ).images[0]

        if self.monochrome:
            # "L" then back to "RGB": the downstream ffmpeg segments and the
            # IP-Adapter both expect three channels, and a single-channel
            # PNG would force a conversion somewhere less visible.
            image = image.convert("L").convert("RGB")

        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(request.out_path)
        return request.out_path


def get_engine(name: str = "stub", **kwargs: object) -> PanelImageEngine:
    """Construct a backend by name.

    Unknown names raise rather than silently falling back to the stub --
    same reasoning as `voice/engine.py::get_engine`: a typo that quietly
    produced placeholder panels would look like a successful render until
    someone opened the images.
    """
    if name == "stub":
        return StubImageEngine(**kwargs)  # type: ignore[arg-type]
    if name == "sdxl":
        return SDXLEngine(**kwargs)  # type: ignore[arg-type]
    if name == "manga":
        return MangaDiffusersEngine(**kwargs)  # type: ignore[arg-type]
    raise ValueError(
        f"unknown image engine {name!r}; expected 'stub', 'sdxl' or 'manga'"
    )


@dataclass(slots=True)
class PanelImage:
    """One rendered panel, and the prompt that produced it."""

    chapter: float
    block_index: int
    prompt: str
    image_path: str
    #: Entity labels whose reference sheet conditioned this panel. Empty
    #: means prompt-only -- recorded per panel so a drifting face can be
    #: traced to a missing sheet rather than guessed at.
    conditioned_on: list[str] = field(default_factory=list)


def beat_text(spans: list[Span], block_index: int, fallback: str) -> str:
    """The composition cue for one block: what the panel should *depict*.

    Narration only. A dialogue block's text is the line being spoken, and a
    spoken line is a terrible thing to hand a diffusion model -- measured on
    RI ch1, where using raw block text made the prompt for block 0
    "Fang Yuan, quietly hand over the Spring Autumn Cicada and I'll give you
    a quick death!", which describes nothing visible. The words are carried
    by the audio track; the picture needs the stage direction.

    Falls back to the raw block when it has no narration at all (a pure
    dialogue exchange), since some cue beats none -- and the cast and style
    clauses still carry that panel.
    """
    narration = [
        s.text.strip()
        for s in spans
        if s.block_index == block_index
        and s.span_type
        in (
            SpanType.NARRATION_ACTION,
            SpanType.NARRATION_DESCRIPTION,
        )
        and s.text.strip()
    ]
    return " ".join(narration) if narration else fallback


def present_entity_ids(mentions: list[Mention], block_index: int) -> list[str]:
    """Resolved entity ids physically present in one block.

    `spans/scene.py`'s `active_selves` cannot be used for this: it comes
    from `anaphora/local.py::present_cast`, which returns mention *surface
    text* ("he", "his uncle"), not entity ids -- fine for counting who is in
    a scene, useless for looking up a persona's reference sheet. Reading the
    mentions directly is both correct and no more expensive.

    Ordered by first appearance in the block so the character the prose
    introduces first is the one that survives `max_references` capping.
    """
    out: list[str] = []
    for mention in mentions:
        if mention.block_index != block_index:
            continue
        if mention.reference_mode is not ReferenceMode.PRESENT:
            continue
        if mention.target_id and mention.target_id not in out:
            out.append(mention.target_id)
    return out


def character_looks(
    store: Store, entity_id: str, *, novel_id: str = ""
) -> tuple[str, str, Path | None, str] | None:
    """`(label, appearance clause, reference sheet, gender)` for one entity.

    Returns None for a non-person entity -- §10 item 5's typing again: a
    location resolves like a name but has no face to draw. The clause and
    the sheet are independent: a character can have extracted appearance but
    no generated sheet yet (references not run), which is exactly the
    prompt-only fallback path.
    """
    entity = store.get_self(entity_id)
    if entity is None or not entity.kind.is_person:
        return None

    from echotales.pipeline.persona.reference_gen import (
        _demographics,
        appearance_of,
        build_reference_prompt,
        reference_path_for,
    )

    persona_id = f"{entity_id}:body1"
    appearance = appearance_of(store, persona_id)
    gender, _age = _demographics(
        store, persona_id, novel_id=novel_id, entity_id=entity_id
    )
    clause = ""
    if appearance:
        # Reuse the reference sheet's own phrasing so the panel prompt and
        # the image conditioning it are describing the same person in the
        # same words; strip the style suffix, which the panel adds itself.
        clause = build_reference_prompt(
            entity.canonical_label, appearance
        ).split(", manga style")[0]
    return (
        entity.canonical_label,
        clause,
        reference_path_for(store, persona_id),
        gender,
    )


@dataclass(slots=True)
class PanelReport:
    novel_id: str
    panels: int = 0
    chapters: int = 0
    skipped_cached: int = 0
    skipped_non_story: int = 0
    #: Panels generated this run with at least one reference sheet vs none.
    #: Cached panels count toward neither -- they were not generated now.
    conditioned_panels: int = 0
    prompt_only_panels: int = 0
    engine: str = "stub"

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.panels:,} panels over {self.chapters} chapters "
            f"({self.engine})\n"
            f"  reused from cache: {self.skipped_cached:,}\n"
            f"  generated with reference conditioning: {self.conditioned_panels:,}; "
            f"prompt-only: {self.prompt_only_panels:,}\n"
            f"  skipped (non-story block): {self.skipped_non_story:,}"
        )


def render_panels(
    novel_id: str,
    store: Store,
    *,
    out_dir: str | Path = "data/panels",
    engine: PanelImageEngine | None = None,
    chapters: list[float] | None = None,
    seed: int = 0,
    width: int = 1024,
    height: int = 1024,
) -> PanelReport:
    """Render one cached panel image per story-bearing block.

    `engine=None` uses the stub, matching `voice/runner.py::render_novel`'s
    default -- a manifest without a GPU is how a run gets reviewed before
    spending render time on it.
    """
    engine = engine or get_engine("stub")
    out_dir = Path(out_dir) / novel_id
    report = PanelReport(novel_id=novel_id, engine=engine.name)

    manifest: list[PanelImage] = []
    wanted = chapters if chapters is not None else store.chapter_numbers(novel_id)

    for chapter_number in wanted:
        chapter: Chapter | None = store.get_chapter(novel_id, chapter_number)
        if chapter is None:
            continue
        report.chapters += 1

        mentions = store.get_mentions(novel_id, chapter_number)
        segments = store.get_segments(novel_id, chapter_number)
        spans = store.get_spans(novel_id, chapter_number)

        for block in chapter.blocks:
            if not block.block_type.is_story_content or not block.text.strip():
                report.skipped_non_story += 1
                continue

            chapter_dir = out_dir / f"ch{chapter_number:g}"
            image_path = chapter_dir / f"block{block.index:04d}.png"

            cast = get_panel_cast(
                novel_id,
                chapter,
                block.index,
                mentions=mentions,
                segments=segments,
                spans=spans,
            )

            # Reference sheets for whoever is actually in this block, so the
            # same character keeps the same face across panels.
            references: list[Path] = []
            conditioned: list[str] = []
            appearances: dict[str, str] = {}
            genders: list[str] = []
            for entity_id in present_entity_ids(mentions, block.index):
                looks = character_looks(store, entity_id, novel_id=novel_id)
                if looks is None:
                    continue
                label, clause, sheet, gender = looks
                genders.append(gender)
                if clause:
                    appearances[label] = clause
                if sheet is not None:
                    references.append(sheet)
                    conditioned.append(label)

            prompt = build_image_prompt(
                cast,
                beat=beat_text(spans, block.index, block.text),
                character_appearances=appearances,
                character_genders=genders,
            )

            if image_path.exists():
                report.skipped_cached += 1
            else:
                engine.generate(
                    PanelImageRequest(
                        prompt=prompt,
                        out_path=image_path,
                        negative_prompt=NEGATIVE_PROMPT,
                        width=width,
                        height=height,
                        seed=seed,
                        reference_images=references,
                    )
                )
                if conditioned:
                    report.conditioned_panels += 1
                else:
                    report.prompt_only_panels += 1

            manifest.append(
                PanelImage(
                    chapter=chapter_number,
                    block_index=block.index,
                    prompt=prompt,
                    image_path=str(image_path),
                    conditioned_on=conditioned,
                )
            )
            report.panels += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.jsonl").write_text(
        "\n".join(json.dumps(asdict(p)) for p in manifest) + "\n",
        encoding="utf-8",
    )
    return report
