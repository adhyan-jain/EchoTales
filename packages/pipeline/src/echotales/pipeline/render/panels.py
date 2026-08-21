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
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Protocol

from echotales.core.enums import ReferenceMode, SpanType
from echotales.core.models import Chapter, Mention, Span
from echotales.core.store import Store
from echotales.pipeline.persona.attire import scene_locale, world_setting
from echotales.pipeline.persona.prompt import (
    cast_tags,
    fit_to_budget,
    STYLE_CLOSEUP,
    STYLE_ESTABLISHING,
    STYLE_SCENE,
    build_image_prompt,
    gender_negative,
    negative_for,
)
from echotales.pipeline.persona.forms import detect_form
from echotales.pipeline.persona.runner import get_panel_cast
from echotales.pipeline.render._png import write_solid_png
from echotales.pipeline.render.beat_canon import beat_canon_for
from echotales.pipeline.render.direction import direct_beat, sanitize_prompt
from echotales.pipeline.render.scene_refs import (
    curated_character_reference,
    match_scene_references,
)
from echotales.pipeline.render.factions import qualify_role, scene_faction
from echotales.pipeline.render.scenes import group_scenes
from echotales.pipeline.spans.scene import detect_mobs
from echotales.pipeline.render.palette import Palette, PaletteSpec, apply_palette
from echotales.pipeline.world.context import story_context
from echotales.pipeline.world.lexicon import build_lexicon

log = logging.getLogger(__name__)

#: How many consecutive story blocks one panel may cover.
#:
#: The audio reads every block; the picture changes only when a new panel
#: starts, so this number *is* how long a viewer looks at one image while
#: the narration moves on. Four is roughly a paragraph of story -- close
#: enough that the image still describes what is being read. Measured
#: before this existed: single panels covered 12 and 16 blocks of RI ch1.
_MAX_BLOCKS_PER_PANEL = 4

#: Slot ids are `chunk * _SLOTS_PER_CHUNK + base`, where base is
#: 0=establishing, 1=close-up, 2=scene, 3=crowd cut.
_SLOTS_PER_CHUNK = 4


def _cached_snapshot(model_id: str) -> str | None:
    """The local snapshot directory for a hub model, if one is usable.

    **`local_files_only=True` is not the fallback it looks like.** It routes
    through the hub's snapshot-completeness check, which fails when the repo
    carries files this pipeline never needs -- Animagine ships a
    single-file `.safetensors` variant and a README alongside the diffusers
    folder layout, and their absence raises `IncompleteSnapshotError` even
    though every weight required to build the pipeline is present. Passing
    the directory path instead skips hub resolution entirely, which is what
    "use what is on disk" actually means.
    """
    org, _, name = model_id.partition("/")
    root = (
        Path.home()
        / ".cache/huggingface/hub"
        / f"models--{org}--{name}".replace("/", "--")
        / "snapshots"
    )
    if not root.is_dir():
        return None
    for snapshot in sorted(root.iterdir(), reverse=True):
        if (snapshot / "model_index.json").exists():
            return str(snapshot)
    return None


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
            )
            # This 8 GB card OOMs inside vae.decode with the pipeline fully
            # resident on GPU (`.to(self.device)`), even with vae/attention
            # slicing enabled -- slicing only helps a batch >1, and every
            # call here is batch=1, so it did nothing (confirmed: still
            # OOM'd at ~7.5/7.65 GiB, same crash site, after adding it).
            # `enable_model_cpu_offload` keeps only the submodule actually
            # running on GPU at any moment and shuttles the rest to CPU --
            # slower per image, but this is the option that actually fits
            # the card. Do not call `.to(self.device)` first: offload
            # manages device placement itself.
            self._pipe.enable_vae_slicing()
            self._pipe.enable_model_cpu_offload()
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
    #: **GuoFeng3, a Chinese antique-style checkpoint -- not a general anime
    #: one.** The first real chapter was generated with MeinaMix, a cute
    #: anime finetune, and the result read as soft manhwa: round friendly
    #: faces, cherry blossoms, decorative birds, none of it xianxia. That is
    #: the checkpoint's training distribution asserting itself, and no
    #: prompt wording overrides it -- the same lesson as the colour output.
    #: GuoFeng3 is trained on Chinese antique/xianxia character art and
    #: ships male antique characters and scene elements specifically, which
    #: is exactly this corpus. Still SD1.5-based, so the SD1.5 IP-Adapter
    #: keeps working unchanged.
    model_id: str = "xiaolxl/GuoFeng3"
    ip_adapter_repo: str = "h94/IP-Adapter"
    ip_adapter_weight: str = "ip-adapter_sd15.bin"
    device: str = "cuda"
    # Fewer panels means each one can afford more steps. At ~14 panels a
    # chapter instead of 89, 40 steps costs less total GPU time than 28 did.
    steps: int = 40
    guidance_scale: float = 7.5
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
    #: **Colour, not ink.** Monochrome was the original brief, and it is
    #: the right look *only* at a quality level this checkpoint does not
    #: reach -- flat greyscale hides nothing and makes weak linework read as
    #: unfinished. Colour gives the same output something to stand on, and
    #: xianxia is a genre with a strong palette (jade, cinnabar, ink-black
    #: hair, blood). Left switchable rather than deleted: a better
    #: checkpoint or a manga-specific LoRA would make the ink look viable
    #: again.
    monochrome: bool = False
    #: Colour restraint, applied after generation where it cannot fail --
    #: see `render/palette.py`. `monochrome=True` is kept as a shorthand for
    #: `Palette.INK` so existing callers and configs keep working.
    palette: str = "colour"
    #: Hue preserved under the `accent` palette, in degrees. Cinnabar red
    #: (0) is xianxia's signature; jade green (140) and gold (45) are the
    #: other two the genre reaches for.
    accent_hue: float = 0.0
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
            except Exception as exc:
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
                # **Nested, and that nesting is the API contract, not a
                # style choice.** diffusers reads the outer list as "one
                # entry per loaded IP-Adapter" and the inner list as the
                # images for that adapter. A flat list of two images against
                # one adapter raises `must have same length as the number of
                # IP Adapters` -- which is exactly what killed a full
                # chapter run 54 panels in, on the first panel that had both
                # a curated composition reference and a character sheet.
                kwargs["ip_adapter_image"] = [[load_image(str(p)) for p in refs]]
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

        # A near-uniform panel is a failed generation, not a stylistic
        # choice: it reads as a dropped frame mid-chapter. Retried once with
        # a shifted seed rather than accepted or crashed on. A *deliberate*
        # black frame is a transition and belongs to `director.py`, which
        # would insert it knowingly -- this guard only catches the accident.
        if _is_flat(image):
            log.warning(
                "flat panel for %s; retrying once with a shifted seed",
                request.out_path.name,
            )
            generator = torch.Generator(device=self.device).manual_seed(
                request.seed + 9973
            )
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

        treatment = Palette.INK if self.monochrome else Palette(self.palette)
        image = apply_palette(
            image, PaletteSpec(palette=treatment, accent_hue=self.accent_hue)
        )

        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(request.out_path)
        return request.out_path


@dataclass(slots=True)
class IllustriousEngine:
    """Illustrious XL -- an SDXL anime finetune, for scenes SD1.5 cannot hold.

    `MangaDiffusersEngine`'s GuoFeng3 is SD1.5-based, and nine rounds of
    prompt work established a hard ceiling on it: it renders a hero, and it
    renders a crowd, but never both, and pulling a crowd closer than
    landscape distance collapses into gore or poster collage. Multi-subject
    composition is the specific thing SDXL improves over SD1.5, which makes
    the checkpoint -- not the prompt -- the next thing to change.

    Loaded with `enable_model_cpu_offload` for the same reason `SDXLEngine`
    is: this card OOMs in `vae.decode` with an SDXL pipeline fully resident,
    and slicing does nothing at batch=1.

    No IP-Adapter here yet. SD1.5 and SDXL take different adapter weights,
    and wiring the SDXL one is only worth doing once the checkpoint has
    earned its place on output quality -- so this engine is prompt-only, and
    `render_panels` degrades to prompt-only for it exactly as it already
    does for a character with no sheet.
    """

    name: str = "illustrious"
    model_id: str = "OnomaAIResearch/Illustrious-xl-early-release-v0"
    device: str = "cuda"
    steps: int = 30
    guidance_scale: float = 6.0
    #: **Danbooru quality tags are not decoration on this checkpoint.**
    #: Illustrious is trained with them and drifts hard toward its raw
    #: training prior without them: a first render came back as grotesque
    #: uncanny faces and a partially undressed figure. GuoFeng3 needs no such
    #: preamble, which is why this is engine-level rather than in the shared
    #: prompt builder.
    #: **Genre has to lead on every prompt, not just the crowd cut.**
    #: GuoFeng3 carries ancient-China style in its weights; this checkpoint
    #: is a general anime model and reverts to that prior the moment the
    #: prompt lets it -- test renders came back with cat ears, modern
    #: clothing and a European cathedral. Anchoring per-panel in the shared
    #: prompt builder would spend tokens GuoFeng3 does not need, so it lives
    #: here, on the engine that needs it.
    quality_prefix: str = (
        "masterpiece, best quality, very aesthetic, absurdres, "
        "ancient china, xianxia, wuxia, hanfu, chinese clothes, "
        "manhwa style, webtoon art"
    )
    #: SDXL takes different adapter weights than SD1.5 -- the SD1.5 file
    #: `MangaDiffusersEngine` loads will not load here at all.
    ip_adapter_repo: str = "h94/IP-Adapter"
    ip_adapter_subfolder: str = "sdxl_models"
    #: The ViT-H variant, not the default `ip-adapter_sdxl.bin`. They are
    #: equivalent in quality, but the plain one wants the ViT-bigG image
    #: encoder (3.7 GB) while this one reuses the ViT-H encoder already on
    #: disk for `MangaDiffusersEngine` -- which, on this connection, is the
    #: difference between a 700 MB download and a 4.4 GB one.
    ip_adapter_weight: str = "ip-adapter_sdxl_vit-h.safetensors"
    #: Where that shared encoder lives *in its own repo*. It cannot be
    #: reached as `../models/image_encoder` from `sdxl_models`: `huggingface_
    #: _hub` rejects any path containing `..` outright, so the encoder is
    #: loaded by hand and handed to the pipeline instead.
    ip_adapter_image_encoder: str = "models/image_encoder"
    max_references: int = 2
    _pipe: object | None = None
    _ip_loaded: bool = False

    def _ensure_pipe(self, want_ip: bool = False) -> object:
        if self._pipe is None:
            import torch  # type: ignore[import-not-found]
            from diffusers import StableDiffusionXLPipeline  # type: ignore[import-not-found]

            # **A flaky network must not kill a multi-hour render.** The
            # weights are fully cached, but a transient "Connection reset by
            # peer" while fetching metadata makes diffusers fall through to
            # "model is not cached locally" and raise -- it took down a
            # ch1+ch2 run twice. Retry pinned to the local cache.
            try:
                pipe = StableDiffusionXLPipeline.from_pretrained(
                    self.model_id, torch_dtype=torch.float16, use_safetensors=True
                )
            except OSError as exc:
                log.warning("hub unreachable (%s); loading from local cache", exc)
                pipe = StableDiffusionXLPipeline.from_pretrained(
                    _cached_snapshot(self.model_id) or self.model_id,
                    torch_dtype=torch.float16,
                    use_safetensors=True,
                )
            # **The adapter has to be attached before offloading, not after.**
            # `enable_model_cpu_offload` installs hooks on the modules present
            # at the time it runs; an image encoder assigned afterwards has no
            # hook, stays on CPU, and the first conditioned panel dies on a
            # device mismatch. So the decision to condition is made here, at
            # first load, from the first panel that asks for it.
            if want_ip:
                self._load_ip_adapter(pipe, torch)
            pipe.enable_vae_slicing()
            pipe.enable_model_cpu_offload()
            self._pipe = pipe
        elif want_ip and not self._ip_loaded:
            import torch  # type: ignore[import-not-found]

            self._load_ip_adapter(self._pipe, torch)
        return self._pipe

    def _load_ip_adapter(self, pipe: object, torch: object) -> None:
        try:
            from transformers import CLIPVisionModelWithProjection  # type: ignore[import-not-found]

            pipe.image_encoder = CLIPVisionModelWithProjection.from_pretrained(  # type: ignore[attr-defined]
                self.ip_adapter_repo,
                subfolder=self.ip_adapter_image_encoder,
                torch_dtype=torch.float16,  # type: ignore[attr-defined]
            ).to(self.device)
            pipe.load_ip_adapter(  # type: ignore[attr-defined]
                self.ip_adapter_repo,
                subfolder=self.ip_adapter_subfolder,
                weight_name=self.ip_adapter_weight,
                # None means "use the encoder already on the pipeline".
                image_encoder_folder=None,
            )
            self._ip_loaded = True
        except Exception as exc:
            log.warning(
                "SDXL IP-Adapter unavailable (%s); panels will be "
                "prompt-only and curated references will not apply",
                exc,
            )

    def generate(self, request: PanelImageRequest) -> Path:
        import torch  # type: ignore[import-not-found]
        from diffusers.utils import load_image  # type: ignore[import-not-found]

        refs = [p for p in request.reference_images if Path(p).exists()][
            : self.max_references
        ]
        pipe = self._ensure_pipe(want_ip=bool(refs))
        kwargs: dict[str, object] = {}
        if self._ip_loaded:
            # Same "never skip once loaded" constraint as
            # `MangaDiffusersEngine` -- loading rewrites the UNet's attention
            # processors, and a call without an image raises rather than
            # falling back. A blank image at scale 0.0 is the no-op.
            if refs:
                pipe.set_ip_adapter_scale(request.reference_weight)  # type: ignore[attr-defined]
                # **Nested, and that nesting is the API contract, not a
                # style choice.** diffusers reads the outer list as "one
                # entry per loaded IP-Adapter" and the inner list as the
                # images for that adapter. A flat list of two images against
                # one adapter raises `must have same length as the number of
                # IP Adapters` -- which is exactly what killed a full
                # chapter run 54 panels in, on the first panel that had both
                # a curated composition reference and a character sheet.
                kwargs["ip_adapter_image"] = [[load_image(str(p)) for p in refs]]
            else:
                from PIL import Image

                pipe.set_ip_adapter_scale(0.0)  # type: ignore[attr-defined]
                kwargs["ip_adapter_image"] = [
                    Image.new("RGB", (224, 224), (255, 255, 255))
                ]

        generator = torch.Generator(device="cpu").manual_seed(request.seed)
        image = pipe(  # type: ignore[operator]
            # **The prefix has to be prepended here, not in the shared prompt
            # builder.** GuoFeng3 needs none of it and every token spent on it
            # would come out of the 77-token CLIP budget that `fit_to_budget`
            # is already rationing for scene content.
            #
            # But the caller already spent that budget down to the limit, so
            # a naive `f"{prefix}, {prompt}"` overflows and CLIP silently
            # drops the *end* -- which is where the locale and the style
            # elaboration live. Measured on the crowd cut: "a narrow mountain
            # path, pine and mist, cliffs falling away" was cut off entirely.
            # Re-fitting drops whole low-priority clauses instead, which is
            # the same trade `fit_to_budget` exists to make.
            prompt=fit_to_budget(
                [self.quality_prefix, *request.prompt.split(", ")]
            ),
            negative_prompt=(
                (request.negative_prompt or "")
                # This family's anime prior specifically: without these it
                # puts cat ears, kemonomimi and modern dress in a xianxia
                # scene, and once put a European cathedral behind it.
                + ", animal ears, cat ears, kemonomimi, fantasy armor, "
                "modern clothing, school uniform, elf"
            ),
            width=request.width,
            height=request.height,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance_scale,
            generator=generator,
            **kwargs,
        ).images[0]
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(request.out_path)
        return request.out_path


@dataclass(slots=True)
class RefinedEngine:
    """One checkpoint composes the frame, a second repaints it.

    The measured split between the two backends is clean: SDXL checkpoints
    place several people in a frame and SD1.5 cannot, while GuoFeng3 carries
    ancient-China style in its weights that no amount of prompt tokens buys
    on a general anime checkpoint. Neither is fixable by prompting, so this
    runs both -- `base` for layout, then GuoFeng3 img2img over its output at
    a denoise strength low enough to keep that layout.

    **This is not compositing.** Nothing is pasted; the refiner repaints
    every pixel of the frame and inherits only where the shapes are. The
    earlier attempt to cut a hero out of one render and drop it into another
    is what produced seams, and this shares none of that mechanism.

    `strength` is the whole dial. Below ~0.25 the restyle barely lands;
    above ~0.5 SD1.5 starts re-deciding the composition and the crowd
    collapses the same way it does when it generates one from scratch.
    """

    name: str = "refined"
    #: Which SDXL backend lays the frame out. Named rather than injected so
    #: `--image-engine refined` stays a one-flag choice on the CLI.
    base_engine: str = "noobai"
    refiner_model_id: str = "xiaolxl/GuoFeng3"
    device: str = "cuda"
    strength: float = 0.35
    steps: int = 30
    guidance_scale: float = 7.0
    #: Keep the intermediate next to the final panel. It costs one file per
    #: panel and it is the only way to tell "the base composed badly" apart
    #: from "the refiner destroyed a good composition" after the fact.
    keep_base: bool = True
    _base: object | None = None
    _pipe: object | None = None

    def _ensure_base(self) -> PanelImageEngine:
        if self._base is None:
            self._base = get_engine(self.base_engine)
        return self._base  # type: ignore[return-value]

    def _ensure_pipe(self) -> object:
        if self._pipe is None:
            import torch  # type: ignore[import-not-found]
            from diffusers import StableDiffusionImg2ImgPipeline  # type: ignore[import-not-found]

            try:
                self._pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                    self.refiner_model_id, torch_dtype=torch.float16, safety_checker=None
                )
            except OSError as exc:  # same transient-network case as the base
                log.warning("hub unreachable (%s); loading from local cache", exc)
                self._pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                    _cached_snapshot(self.refiner_model_id) or self.refiner_model_id,
                    torch_dtype=torch.float16,
                    safety_checker=None,
                )
            # Both checkpoints are resident across a panel, so neither one
            # gets to sit on the card -- offload, unlike `MangaDiffusersEngine`
            # which is alone on the GPU and can afford `.to(device)`.
            self._pipe.enable_vae_slicing()
            self._pipe.enable_model_cpu_offload()
        return self._pipe

    def generate(self, request: PanelImageRequest) -> Path:
        import torch  # type: ignore[import-not-found]
        from diffusers.utils import load_image  # type: ignore[import-not-found]

        base_path = request.out_path.with_name(
            request.out_path.stem + ".base" + request.out_path.suffix
        )
        base_request = replace(request, out_path=base_path)
        self._ensure_base().generate(base_request)

        pipe = self._ensure_pipe()
        generator = torch.Generator(device="cpu").manual_seed(request.seed)
        image = pipe(  # type: ignore[operator]
            prompt=request.prompt,
            negative_prompt=request.negative_prompt or None,
            image=load_image(str(base_path)),
            strength=self.strength,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance_scale,
            generator=generator,
        ).images[0]

        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(request.out_path)
        if not self.keep_base:
            base_path.unlink(missing_ok=True)
        return request.out_path



@dataclass(slots=True)
class NoobAIEngine(IllustriousEngine):
    """NoobAI-XL v1.1 -- an Illustrious continuation trained far longer.

    NoobAI diverges from Illustrious's tag vocabulary: it was trained on
    Danbooru aesthetic *score* tags (score_9 / score_8_up / …) rather than
    the older masterpiece/best-quality taxonomy. Feeding it the Illustrious
    prefix puts unknown tags at the front of its attention budget and pulls
    it back toward its raw aesthetic prior instead of the intended content.

    Steps raised from 30→35 and guidance_scale from 6.0→7.0 for this
    checkpoint: NoobAI's longer training lets it use more steps productively,
    and the higher CFG is needed to hold character-specific prompt terms
    (gender, clothing, hair) against its very strong default composition bias.
    """

    name: str = "noobai"
    model_id: str = "Laxhar/noobai-XL-1.1"
    steps: int = 35
    guidance_scale: float = 7.0
    quality_prefix: str = (
        "score_9, score_8_up, score_7_up, masterpiece, best quality, "
        "ancient china, xianxia, wuxia, hanfu, chinese clothes, "
        "manhwa style, webtoon art"
    )


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
    if name == "illustrious":
        return IllustriousEngine(**kwargs)  # type: ignore[arg-type]
    if name == "refined":
        return RefinedEngine(**kwargs)  # type: ignore[arg-type]
    if name == "noobai":
        return NoobAIEngine(**kwargs)  # type: ignore[arg-type]
    if name == "manga":
        return MangaDiffusersEngine(**kwargs)  # type: ignore[arg-type]
    if name == "gemini":
        from echotales.pipeline.render.gemini import GeminiImageEngine

        return GeminiImageEngine(**kwargs)  # type: ignore[arg-type,return-value]
    if name == "openrouter":
        from echotales.pipeline.render.openrouter import OpenRouterImageEngine

        return OpenRouterImageEngine(**kwargs)  # type: ignore[arg-type,return-value]
    raise ValueError(
        f"unknown image engine {name!r}; expected 'stub', 'sdxl', 'manga', "
        "'illustrious', 'noobai', 'refined', 'gemini' or 'openrouter'"
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
    #: Logged for debugging -- the negative prompt sent to the engine.
    #: Without this, "why did a female figure appear?" cannot be answered
    #: after the fact: the positive prompt and the image are both visible,
    #: but the negative that was (or was not) applied is not.
    negative_prompt: str = ""


def _is_flat(image: object, *, threshold: float = 6.0) -> bool:
    """Whether an image is a near-uniform block of one colour.

    Measured as the mean absolute deviation from the image's own mean
    brightness -- cheap, and it does not care *which* colour, so it catches
    a blank white panel and a blank grey one alike. The threshold is set low
    enough that a legitimately sparse panel (a figure against open sky)
    survives; only genuinely featureless output trips it.
    """
    try:
        from PIL import ImageStat

        stat = ImageStat.Stat(image.convert("L"))  # type: ignore[attr-defined]
        return float(stat.stddev[0]) < threshold
    except Exception:
        return False


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


def present_beat_entities(mentions: list[Mention], blocks: list[int]) -> list[str]:
    """Resolved entities present anywhere in a beat.

    A beat spans several blocks, and the character the moment is about is
    frequently named in one of them rather than all -- looking only at the
    lead block loses the cast for most beats.
    """
    wanted = set(blocks)
    out: list[str] = []
    for mention in mentions:
        if mention.block_index not in wanted:
            continue
        if mention.reference_mode is not ReferenceMode.PRESENT:
            continue
        if mention.target_id and mention.target_id not in out:
            out.append(mention.target_id)
    return out


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
    store: Store,
    entity_id: str,
    *,
    novel_id: str = "",
    chapter: float | None = None,
    crowd: bool = False,
) -> tuple[str, str, Path | None, str] | None:
    """`(label, appearance clause, reference sheet, gender)` for one entity.

    `chapter` selects which *body* to draw, and **must be the fractional
    story position** `persona/split.py::write_epochs` uses for its own body
    boundaries (`chapter + block_index / n_blocks_in_chapter`), not a bare
    chapter number. A body change can land mid-chapter -- RI's Fang Yuan is
    reborn partway through chapter 1 itself -- and a bare integer chapter
    number is indistinguishable from "the very start of the chapter" to
    `persona_at`'s interval lookup, so every panel in that chapter resolved
    to the pre-rebirth body regardless of which half of the chapter it was
    actually depicting. `render_panels` computes this the same way
    `split.py` does; see its call site. None means "their latest body",
    which is the right answer for a cast list and the wrong one for a
    panel -- so panel rendering always passes a real position.

    Returns None for a non-person entity -- §10 item 5's typing again: a
    location resolves like a name but has no face to draw. The clause and
    the sheet are independent: a character can have extracted appearance but
    no generated sheet yet (references not run), which is exactly the
    prompt-only fallback path.
    """
    entity = store.get_self(entity_id)
    if entity is None or not entity.kind.is_person:
        return None

    from echotales.pipeline.persona.attire import resolve_appearance
    from echotales.pipeline.persona.canon import apply_canon
    from echotales.pipeline.persona.reference_gen import (
        _demographics,
        appearance_of,
        build_reference_prompt,
        reference_path_for,
    )
    from echotales.pipeline.persona.split import persona_at

    persona_id = persona_at(store, entity_id, chapter)
    appearance = appearance_of(store, persona_id)
    # Canon, then genre defaults -- the same chain `reference_gen` applies.
    # Without it here the panels were running on raw extraction only: Fang
    # Yuan has no extracted hair colour, so the image model invented one and
    # gave the canonically black-haired protagonist white hair.
    if novel_id:
        appearance = apply_canon(
            novel_id, entity.canonical_label, appearance, persona_id
        )
        appearance = resolve_appearance(novel_id, appearance)
    gender, _age = _demographics(
        store, persona_id, novel_id=novel_id, entity_id=entity_id
    )
    clause = ""
    if appearance:
        # Reuse the reference sheet's own phrasing so the panel prompt and
        # the image conditioning it are describing the same person in the
        # same words; strip the style suffix, which the panel adds itself.
        # Pass the resolved gender and omit the style suffix outright --
        # splitting on a style substring silently stopped working the
        # moment the style text changed, and the omitted gender made the
        # protagonist render as "androgynous person" despite a clean
        # 120/131 male-pronoun verdict.
        # **`detailed=False` for panels, and it is the difference between a
        # panel that shows the scene and one that shows a portrait.** CLIP
        # truncates at 77 tokens, this clause leads the prompt, and the full
        # version spends ~50 of them on one face -- so the scene, the mob and
        # the locale, all of which come *after* it, were silently cut off the
        # end of every panel prompt that had a resolved character in it.
        # Measured on RI ch1: block 0 (long clause) rendered a lone figure on
        # a blank grey background while its prompt asked for a mountain
        # stronghold and encroaching warlords; block 1, whose speaker never
        # resolved and so carried no clause at all, rendered the full misty
        # peaks-and-timber-halls scene from the same run. The short form keeps
        # the identity cues that actually survive at panel scale (hair,
        # attire, gender); the face is carried by the IP-Adapter reference
        # sheet, which is what that conditioning is for.
        clause = build_reference_prompt(
            entity.canonical_label,
            appearance,
            gender=gender,
            age_band=_age,
            with_style=False,
            solo=False,
            detailed=False,
            crowd=crowd,
        )
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
    #: Blocks whose final prompt was byte-identical to one already generated
    #: this run, and were copied from that file instead of paying for a
    #: second diffusion pass. See `render_panels`'s note on why this is
    #: exact-match only, not similarity-based.
    deduped_panels: int = 0
    engine: str = "stub"

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.panels:,} panels over {self.chapters} chapters "
            f"({self.engine})\n"
            f"  reused from cache: {self.skipped_cached:,}; "
            f"deduped against another block this run: {self.deduped_panels:,}\n"
            f"  generated with reference conditioning: {self.conditioned_panels:,}; "
            f"prompt-only: {self.prompt_only_panels:,}\n"
            f"  skipped (non-story block): {self.skipped_non_story:,}"
        )


def _speaker_label(span: Span, store: Store) -> str:
    """Who says this line, in words a director can use.

    An anonymous slot is deliberately rendered as "someone" rather than as
    its slot id: the id is a voice-casting handle, and putting
    `ri:anon:1:s0:2` in a prompt would have the image model draw the
    string.
    """
    speaker = span.speaker_self_id or ""
    if not speaker or ":anon:" in speaker:
        return "Someone"
    entity = store.get_self(speaker)
    return entity.canonical_label if entity is not None else "Someone"


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
    client: object | None = None,
    max_panels: int = 14,
    block_range: tuple[int, int] | None = None,
    prompt_cache_path: str | Path | None = None,
    #: Version directory for this run, placed *inside* the chapter so a
    #: multi-chapter run keeps each chapter's history browsable and no
    #: run ever overwrites a previous one.
    version: str | None = None,
) -> PanelReport:
    """Render one cached panel image per story-bearing block.

    `engine=None` uses the stub, matching `voice/runner.py::render_novel`'s
    default -- a manifest without a GPU is how a run gets reviewed before
    spending render time on it.

    **`prompt_cache_path`, when given, decouples direction from image
    generation.** Every beat's final prompt (LLM-directed or mechanically
    assembled) is written to this JSON file keyed by `"{chapter:g}:
    {block_index}"`; on a later call with the same path, a beat whose key is
    already cached skips the director call (and the mechanical fallback)
    entirely and reuses the cached prompt. This is what lets a "direction
    first" run (`client` set, a cheap/no-GPU image engine such as `stub`)
    populate the cache with every beat's LLM-authored prompt using a
    gateway/API backend that doesn't touch the local GPU, followed by a
    separate "image" run (`client=None`, the real local diffusion engine)
    that generates every image from the cache with zero further LLM calls
    -- avoiding the VRAM conflict a resident ollama model and a local
    diffusion pipeline have in the same process (`EVOLUTION.md` section 9).
    Config: `render_direction_first` in `config.json`/`Settings`;
    `commands.py::cmd_render` is what actually runs the two passes.

    **`block_range` restricts every requested chapter to `[lo, hi]`
    inclusive, for testing.** Panel generation costs 40-70s/image on this
    hardware and its cost is set by `max_panels`, not by chapter length --
    a short chapter is exactly as expensive to render as a long one, since
    both get merged down to the same panel count. `max_panels` alone already
    controls that count; `block_range` is for the different, real need of
    iterating on a *specific* portion of a chapter (the opening, a
    confrontation) rather than a sample scattered across the whole thing,
    without having to first classify where one "scene" starts and ends --
    a block range is cheap to pick by eye and good enough for tuning.

    **Deduplicates on the exact prompt string, across the whole run.** Two
    blocks with identical cast, environment, framing and (after truncation)
    beat text produce a byte-identical prompt -- and with one fixed `seed`
    per run, a byte-identical prompt is a byte-identical image, so a second
    diffusion pass for it is pure GPU time spent to reproduce a file already
    on disk. Deliberately exact-match only, not similarity-based: two
    *different* prompts might describe a similar-looking panel, but judging
    "similar enough to reuse" is a real editorial call this function has no
    basis to make silently, and a wrong merge would show the wrong picture
    under a caption that doesn't match it. `image_path.exists()` (below)
    already covers the cross-run case; this covers the within-run one.
    """
    import hashlib
    import shutil

    engine = engine or get_engine("stub")
    # No novel level here: `paths.novel_root` already scopes the output
    # root to this novel (`data/RI/panels`), so repeating the id below it
    # only buried the chapters one directory deeper.
    out_dir = Path(out_dir)
    report = PanelReport(novel_id=novel_id, engine=engine.name)
    generated_by_digest: dict[str, Path] = {}

    prompt_cache: dict[str, str] = {}
    cache_path = Path(prompt_cache_path) if prompt_cache_path is not None else None
    if cache_path is not None and cache_path.exists():
        try:
            prompt_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prompt_cache = {}

    manifest: list[PanelImage] = []
    wanted = chapters if chapters is not None else store.chapter_numbers(novel_id)

    # **Built from the whole volume, not from the chapters being rendered.**
    # A word's sense is a property of the book; deriving "demon means a man
    # here" from a two-chapter slice would give a thinner answer for the
    # same panels. Reveals stay contained because the lexicon only ever
    # says what a *word* denotes -- never who anyone turns out to be.
    _lexicon = build_lexicon(store, novel_id)
    _lexicon_note = _lexicon.director_note()
    _lexicon_negatives = (
        f", {_lexicon.negative_terms()}" if _lexicon.negative_terms() else ""
    )
    if _lexicon.people_called:
        log.info(
            "world lexicon: %s",
            ", ".join(
                f"{w}={labels[0]}" for w, labels in sorted(_lexicon.people_called.items())
            ),
        )

    for chapter_number in wanted:
        chapter: Chapter | None = store.get_chapter(novel_id, chapter_number)
        if chapter is None:
            continue
        report.chapters += 1
        # Panel number within the chapter, in play order. Reset per chapter
        # so a filename is meaningful without knowing the whole run.
        _panel_seq = 0

        mentions = store.get_mentions(novel_id, chapter_number)
        segments = store.get_segments(novel_id, chapter_number)
        spans = store.get_spans(novel_id, chapter_number)

        if block_range is not None:
            lo, hi = block_range
            chapter = chapter.model_copy(
                update={"blocks": [b for b in chapter.blocks if lo <= b.index <= hi]}
            )
            mentions = [m for m in mentions if lo <= m.block_index <= hi]
            spans = [s for s in spans if lo <= s.block_index <= hi]

        # One (or a few) unique images per *scene*, not per block or per
        # beat. See `render/scenes.py`: a scene is a contiguous stretch
        # sharing cast, place and timeline, and its length in blocks sets
        # a hard image budget (1/2/3) rather than one image per drawable
        # moment -- a 15-block conversation in one courtyard needs 1-3
        # pictures held across it with Ken Burns, not 15 near-duplicates.
        by_index = {b.index: b for b in chapter.blocks}
        scenes = group_scenes(novel_id, chapter, mentions, segments, spans)
        by_block_spans: dict[int, list[Span]] = {}
        for span in spans:
            by_block_spans.setdefault(span.block_index, []).append(span)

        for scene in scenes:
            story_scene_blocks = [
                b for b in scene.blocks
                if (blk := by_index.get(b)) is not None
                and blk.text.strip()
                # A scene-break block ("......") has nothing to depict, and
                # the director invents a whole scene when handed one --
                # RI ch1 block 4 is a bare ellipsis and became "Fang Yuan
                # stands at the edge of a stone courtyard, gazing up at
                # mist-covered peaks", none of which is in the novel.
                and any(ch.isalnum() for ch in blk.text)
                and blk.block_type.is_story_content
            ]
            if not story_scene_blocks:
                report.skipped_non_story += len(scene.blocks)
                continue

            budget = scene.image_budget
            # Which slot (0=establishing, 1=close-up, 2=wide/secondary)
            # each block in this scene draws its picture from. Budget 1:
            # everything shares the one image. Budget 2: narration blocks
            # get the establishing image, dialogue-bearing blocks get the
            # close-up -- the spec's own "alternate on dialogue exchanges"
            # rule. Budget 3: non-dialogue still anchors on establishing;
            # dialogue blocks alternate between close-up and wide/
            # secondary by position, so a scene with several speakers
            # doesn't hold on only one of them for its entire length.
            slot_for_block: dict[int, int] = {}
            for i, b in enumerate(story_scene_blocks):
                has_dialogue = any(
                    s.span_type in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE)
                    for s in by_block_spans.get(b, [])
                )
                if budget == 1:
                    base = 0
                elif budget == 2:
                    base = 1 if has_dialogue else 0
                else:
                    base = 0 if not has_dialogue else (1 if i % 2 == 0 else 2)
                # **A scene is not a shot, and this is where relevance was
                # being lost.** Slots were assigned by content type only, so
                # a scene of any length produced at most three images, each
                # anchored to the first block that claimed its slot.
                # Measured on RI ch1: 22 panels for 92 blocks, with two
                # panels covering 12 and 16 consecutive blocks -- sixteen
                # blocks of narration read aloud over one picture of the
                # scene's opening moment. The picture was not wrong about
                # the scene; it was answering a question the audio had
                # stopped asking twelve blocks earlier.
                #
                # Chunking keeps everything scene grouping bought (one
                # locale, one cast, continuity) and restores beat-level
                # granularity: each run of blocks gets its own slot, hence
                # its own director call, drawn from its own prose.
                chunk = i // _MAX_BLOCKS_PER_PANEL
                slot_for_block[b] = chunk * _SLOTS_PER_CHUNK + base

            # Only slots a block actually maps to get generated -- an
            # all-narration long scene never needs its close-up/wide
            # slots just because the budget allows them.
            needed_slots = sorted(set(slot_for_block.values()))
            slot_lead: dict[int, int] = {}
            for b in story_scene_blocks:
                slot_lead.setdefault(slot_for_block[b], b)

            # **One locale per scene, resolved from the whole scene's text.**
            # `scene_locale` rotates through the novel's locales by block
            # index when no cue matches -- a deliberate choice from when
            # panels were generated per block, and actively wrong now that
            # they are generated per scene: consecutive slots of one
            # continuous scene came back as a cave, then a courtyard, then a
            # bamboo grove, by sheer block-index arithmetic. Measured on RI
            # ch1's opening siege, which rendered as five unrelated places.
            # Resolving once from the joined scene text also stops a single
            # stray word deciding the whole location -- block 18's *poem*
            # ("night is like...") flipped that panel to a moonlit forest
            # while its own prose said "looking at the setting sun".
            _scene_narration = " ".join(
                sp.text.strip()
                for sp in spans
                if sp.block_index in set(story_scene_blocks)
                and sp.span_type
                in (SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION)
                and sp.text.strip()
            )
            _scene_text = " ".join(
                by_index[b].text for b in story_scene_blocks if b in by_index
            )
            scene_locale_text = scene_locale(
                novel_id, _scene_text, block_index=scene.blocks[0]
            )

            # **The crowd gets its own cut, not a corner of the hero's
            # panel.** Four rounds of prompt work could not put a crowd in
            # frame beside a named character on this checkpoint -- and the
            # same checkpoint renders a dense crowd readily when the prompt
            # names nobody. So a scene with a mob earns one extra panel that
            # is *only* the mob: no character clause, no reference sheet,
            # nothing for the model to collapse onto a single figure. This
            # is also what the source medium does with this beat -- cut to
            # the faces reacting, then back -- so it is the honest structure
            # rather than a workaround for a model limit, though it is both.
            # Whose people these are. A role word without a faction is a
            # continuity hazard in a novel that runs "the elders" past four
            # clans in one volume -- see `render/factions.py`.
            _scene_faction = scene_faction(_scene_text)
            _scene_mobs = detect_mobs(_scene_text, scene.blocks[0])
            _crowd_slot = None
            if _scene_mobs and len(story_scene_blocks) > 1:
                _crowd_slot = 3
                # It belongs on a line somebody in the crowd speaks, which
                # is the moment a reader would be looking at them.
                _dialogue_blocks = [
                    b
                    for b in story_scene_blocks
                    if any(
                        sp.span_type in (SpanType.DIALOGUE,)
                        for sp in by_block_spans.get(b, [])
                    )
                ]
                if _dialogue_blocks:
                    # In the chunk that block belongs to, so the crowd cut
                    # lands next to the lines it illustrates rather than at
                    # the top of a scene it may be far into.
                    _crowd_block = _dialogue_blocks[0]
                    _crowd_chunk = (
                        story_scene_blocks.index(_crowd_block) // _MAX_BLOCKS_PER_PANEL
                    )
                    _crowd_slot = _crowd_chunk * _SLOTS_PER_CHUNK + 3
                    slot_for_block[_crowd_block] = _crowd_slot
                    slot_lead[_crowd_slot] = _crowd_block
                    needed_slots = sorted(set(slot_for_block.values()))
                else:
                    _crowd_slot = None

            slot_images: dict[int, PanelImage] = {}
            for slot in needed_slots:
                lead = slot_lead[slot]
                block = by_index[lead]
                is_crowd_cut = slot == _crowd_slot
                style = (STYLE_ESTABLISHING, STYLE_CLOSEUP, STYLE_SCENE, STYLE_SCENE)[
                    slot % _SLOTS_PER_CHUNK
                ]
                closeup = style is STYLE_CLOSEUP

                # **What this panel's own blocks say, not the scene's.**
                # `cast.background_mobs` is resolved over the whole scene,
                # which was harmless when a scene produced one image and is
                # wrong now that it produces several: RI ch1's opening scene
                # mentions a besieging crowd in its first blocks, so *every*
                # chunk of it -- including a dying man's private last
                # thoughts -- inherited "many people present", lost its
                # character sheet as a crowd wide, and picked up the
                # one-vs-many composition reference. That is the "random
                # crowds": the same crowd, asserted everywhere.
                _chunk_blocks = sorted(
                    b
                    for b, sl in slot_for_block.items()
                    if sl // _SLOTS_PER_CHUNK == slot // _SLOTS_PER_CHUNK
                )
                _chunk_text = " ".join(
                    by_index[b].text for b in _chunk_blocks if b in by_index
                )
                _chunk_mobs = detect_mobs(_chunk_text, lead)
                # A transformation is a property of this passage, not of the
                # character -- see `persona/forms.py` on why it is an
                # overlay and why reverting needs no detection.
                _form = detect_form(_chunk_text)

                chapter_dir = out_dir / f"ch{chapter_number:g}"
                if version:
                    chapter_dir = chapter_dir / version
                # **The crowd cut needs its own file.** `slot_lead` is
                # built before the crowd slot is assigned, so the crowd's
                # lead block is usually already some other slot's lead too --
                # both then resolve to the same block{n}.png, the normal
                # panel writes it first, and the crowd panel is silently
                # dropped by the `image_path.exists()` cache check. Cost
                # three rounds of "the crowd cut fires but never appears".
                # **Numbered in the order they play, block kept for tracing.**
                # Naming by lead block alone put `block0047.png` after
                # `block0048.png` in a directory listing and gave three
                # panels of one scene numbers 21, 26 and 47 -- readable only
                # if you already knew how slots were assigned. `p003_b0026`
                # sorts as it plays and still says which block it came from.
                _panel_seq += 1
                stem = f"p{_panel_seq:03d}_b{lead:04d}"
                image_path = chapter_dir / (
                    f"{stem}_crowd.png" if is_crowd_cut else f"{stem}.png"
                )

                cast = get_panel_cast(
                    novel_id,
                    chapter,
                    lead,
                    mentions=mentions,
                    segments=segments,
                    spans=spans,
                    store=store,
                    # **Scoped to this panel's own blocks.** Scene-wide was
                    # right when a scene produced one image and is a
                    # hallucination source now that it produces several: the
                    # protagonist is present somewhere in almost every
                    # scene, so a chunk of clan elders gossiping about a
                    # third party was handed Fang Yuan as cast and the
                    # director wrote "Fang Yuan stands in a stone courtyard,
                    # his gaze distant as he contemplates the future of the
                    # Bai clan" for a passage he does not appear in.
                    block_window=(min(_chunk_blocks), max(_chunk_blocks)),
                )

                references: list[Path] = []
                conditioned: list[str] = []
                appearances: dict[str, str] = {}
                genders: list[str] = []
                # Same fractional-position convention as
                # `persona/split.py::write_epochs`'s own boundaries --
                # required, not cosmetic: see `character_looks`'s
                # docstring for the mid-chapter body-selection bug this
                # fixes.
                story_position = chapter_number + lead / max(len(chapter.blocks), 1)
                _chunk_blocks_set = set(_chunk_blocks)
                for entity_id in present_beat_entities(mentions, _chunk_blocks):
                    looks = character_looks(
                        store,
                        entity_id,
                        novel_id=novel_id,
                        chapter=story_position,
                        crowd=bool(_chunk_mobs),
                    )
                    if looks is None:
                        continue
                    label, clause, sheet, gender = looks
                    genders.append(gender)
                    if clause or _form.active:
                        appearances[label] = _form.apply_to(clause)
                    # A hand-picked portrait beats the generated sheet when
                    # one exists: the sheets are themselves diffusion output
                    # and inherit the same drift they are supposed to
                    # prevent (Fang Yuan kept coming back bulked and
                    # bright-eyed), while the curated image is ground truth.
                    sheet = (
                        curated_character_reference(label, chapter=story_position)
                        or sheet
                    )
                    if sheet is not None:
                        references.append(sheet)
                        conditioned.append(label)

                if not appearances:
                    # The PRESENT-only pass produced no cast. This happens on
                    # dialogue/prologue blocks where the subject is physically
                    # present but their mention was classified as
                    # DIALOGUE_REFERENCE rather than PRESENT (e.g. someone
                    # shouting "Fang Yuan, stop resisting!" in block 0). The
                    # director correctly names them in action/layout, but
                    # without an appearance clause the model invents an
                    # unconstrained figure -- confirmed as the titan effect in
                    # RI ch1 block 0. Fall back to any entity mentioned in
                    # these blocks (any reference mode) so the director still
                    # gets the canonical look to constrain the output.
                    _fallback_ids = {
                        m.target_id
                        for m in mentions
                        if m.block_index in _chunk_blocks_set and m.target_id
                    }
                    for entity_id in _fallback_ids:
                        if any(
                            m.target_id == entity_id and m.block_index in _chunk_blocks_set
                            for m in mentions
                            if m.reference_mode is ReferenceMode.PRESENT
                        ):
                            continue  # already handled above
                        looks = character_looks(
                            store,
                            entity_id,
                            novel_id=novel_id,
                            chapter=story_position,
                            crowd=bool(_chunk_mobs),
                        )
                        if looks is None:
                            continue
                        label, clause, sheet, gender = looks
                        genders.append(gender)
                        if clause or _form.active:
                            appearances[label] = _form.apply_to(clause)
                        sheet = (
                            curated_character_reference(label, chapter=story_position)
                            or sheet
                        )
                        if sheet is not None:
                            references.append(sheet)
                            conditioned.append(label)

                # The slot's own representative block's prose, not the
                # whole scene's -- what makes the establishing/close-up/
                # wide images of one scene distinct pictures rather than
                # the same prompt three times.
                # **Fall back to the scene's narration, never to the
                # spoken line.** `beat_text` already prefers narration, but
                # its fallback was the raw block, so a pure-dialogue block
                # handed the director an insult to illustrate: RI ch1 block
                # 1 is "Old bastard Fang, stop attempting to resist", and
                # the director duly wrote "Old bastard Fang stands
                # resolute", inventing a character out of a slur. Panels are
                # scene-grouped now, so the scene almost always has real
                # narration somewhere -- which describes the same moment and
                # is actually visual.
                # **The chunk's own narration, falling back to the scene's.**
                # Now that a slot covers a handful of blocks rather than a
                # whole scene, the scene-wide fallback would hand the
                # director prose from a different part of the scene than the
                # one this panel plays under -- the exact mismatch chunking
                # exists to remove.
                _chunk_narration = " ".join(
                    sp.text.strip()
                    for sp in spans
                    if sp.block_index in set(_chunk_blocks)
                    and sp.span_type
                    in (SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION)
                    and sp.text.strip()
                )
                # **An all-dialogue chunk has to be drawn from its dialogue.**
                # Falling back to the scene's narration here was reaching
                # into a different moment for the picture -- which is the
                # very mismatch chunking removes -- and measurably so: every
                # panel scoring 0.00 in the relevance audit was a chunk of
                # pure dialogue. Handing the director the lines themselves,
                # with who says them, lets its "draw the speaker saying it
                # in their surroundings" rule apply to real material.
                if not _chunk_narration:
                    # Kept short on purpose. `fit_to_budget` rations 77 CLIP
                    # tokens by priority, and a verbatim exchange is long
                    # enough to be dropped whole -- which is what happened:
                    # the panel for the elders' gossip came out as locale
                    # scenery with no beat in it at all. One speaker, a few
                    # words, is what survives the budget and is also all a
                    # picture of someone talking can show.
                    _lines = [
                        (_speaker_label(sp, store), " ".join(sp.text.split()[:10]))
                        for sp in spans
                        if sp.block_index in set(_chunk_blocks)
                        and sp.span_type is SpanType.DIALOGUE
                        and sp.text.strip()
                    ]
                    _chunk_dialogue = (
                        f"{_lines[0][0]} speaking: {_lines[0][1]}" if _lines else ""
                    )
                else:
                    _chunk_dialogue = ""

                beat_prose = beat_text(
                    spans,
                    lead,
                    _chunk_narration or _chunk_dialogue or _scene_narration or block.text
                )

                canon = beat_canon_for(novel_id, chapter_number, lead)
                directive = canon.staging if canon is not None else ""
                if canon is not None and canon.style_override == "establishing":
                    style = STYLE_ESTABLISHING
                elif canon is not None and canon.style_override == "scene":
                    style = STYLE_SCENE

                # **Keyed by the beat, not just the block.** The key was
                # `chapter:block`, which silently outlived every change to
                # how beats are chosen: after scenes were chunked, a render
                # kept serving prompts written for the old whole-scene
                # beats, and two rounds of "the fix changed nothing" were
                # actually the cache answering. The beat digest makes a
                # changed beat a different entry, so stale prompts fall out
                # of use on their own while genuinely identical work is
                # still reused across the two phases.
                _beat_digest = hashlib.sha256(
                    f"{beat_prose}|{directive}".encode("utf-8")
                ).hexdigest()[:12]
                cache_key = (
                    f"{chapter_number:g}:{lead}:{_beat_digest}"
                    + (":crowd" if is_crowd_cut else "")
                )
                cached_prompt = prompt_cache.get(cache_key)
                directed = None  # may be set in the else branch below; None on cache hit

                if cached_prompt is not None:
                    # A direction pass already ran (`prompt_cache_path`) and
                    # settled this slot's prompt -- reuse it verbatim rather
                    # than re-calling the director or falling back to the
                    # mechanical assembler, which is the whole point of the
                    # two-phase split (this function's own docstring).
                    prompt = cached_prompt
                else:
                    # **Ask a model what this panel should show**, and only
                    # fall back to mechanical assembly when there is no
                    # client or the call fails. An assembled prompt is
                    # grammatical and about nothing: it cannot know what is
                    # happening in the beat, which is why panels came back
                    # unrelated to the story around them.
                    if client is not None:
                        brief = story_context(
                            novel_id, store, chapter_number, scene.blocks
                        ).to_brief()
                        # What this novel's own words denote. The graph is
                        # the only thing that knows "demon" is a man here,
                        # and the director is the cheapest place to say so.
                        if _lexicon_note:
                            brief = f"{brief}\n{_lexicon_note}".strip()
                        directed_prose = (
                            f"{directive} {beat_prose}".strip() if directive else beat_prose
                        )
                        # State the crowd to the director explicitly -- but
                        # only on the slot that actually needs to know.
                        # **Real bug, found by generating and looking at
                        # one panel repeatedly (4.45): this injection had no
                        # `is_crowd_cut` gate at all, so a scene with a mob
                        # got "many people present ... surrounding him"
                        # stapled onto *every* slot's prompt in the chunk --
                        # including the main/establishing slot, whose job is
                        # a solo shot of the named subject and whose own
                        # dedicated crowd cut (`_crowd_slot`, just below)
                        # already exists specifically to carry the crowd.
                        # Result: the crowd got asserted twice, and the
                        # solo-capable slot never had a chance to be solo --
                        # confirmed directly: three checkpoint/prompt fixes
                        # failed on this exact scene, and the *only* thing
                        # that worked in testing was a prompt with no crowd
                        # mention in it at all.
                        if _chunk_mobs and (is_crowd_cut or _crowd_slot is None):
                            roles = ", ".join(
                                qualify_role(role, _scene_faction)
                                for role in sorted({m.role for m in _chunk_mobs})
                            )
                            directed_prose = (
                                f"{directed_prose} "
                                f"(many people present: {roles}, surrounding him)"
                            ).strip()
                        elif _chunk_mobs and not is_crowd_cut:
                            # A dedicated crowd cut exists elsewhere in this
                            # scene -- tell the director explicitly to leave
                            # the crowd to it, rather than leaving the
                            # omission implicit and hoping the model infers
                            # the same division of labour the pipeline
                            # already decided on.
                            directed_prose = (
                                f"{directed_prose} "
                                "(draw only the named subject alone here -- "
                                "the surrounding crowd is a separate panel)"
                            ).strip()
                        directed = direct_beat(
                            directed_prose,
                            context_brief=brief,
                            cast={k: v for k, v in appearances.items() if v},
                            novel_style=world_setting(novel_id),
                            client=client,
                            novel_id=novel_id,
                        )

                    if directed is not None:
                        prompt = directed.to_image_prompt(
                            scene_locale=scene_locale_text,
                        )
                        # **Assert the crowd as a count tag, in front.**
                        # Removing "1boy" stopped the prompt insisting on
                        # exactly one man, but nothing replaced it, and prose
                        # like "surrounded by enemies on the ground and in
                        # the air" sitting mid-prompt does not survive
                        # against a named subject -- three rounds of real
                        # generation produced a lone figure every time while
                        # saying exactly that. Danbooru count tags are the
                        # vocabulary this checkpoint actually weights (the
                        # same reason "1boy" and "solo" were able to override
                        # everything), so the crowd has to be stated in that
                        # vocabulary and placed where truncation cannot reach
                        # it.
                        # Only the crowd *cut* asserts a crowd. Prefixing
                        # every wide panel in a mob scene with "crowd,
                        # multiple people, 6+boys" turned the hero's own
                        # panel into a wall of faces on a checkpoint that
                        # actually honours the tag -- the count tag is a
                        # blunt instrument and belongs only on the panel
                        # whose subject *is* the crowd.
                        if is_crowd_cut:
                            prompt = f"crowd, multiple people, 6+boys, {prompt}"
                        elif tags := cast_tags(
                            genders,
                            # **Combine beat prose with the director's own
                            # action+layout text.** When a block is pure
                            # dialogue the beat prose has no narration and
                            # therefore no he/him/his pronouns (e.g. block 0
                            # RI ch1: an enemy shouts at Fang Yuan in second
                            # person, so beat_prose never mentions "he").
                            # The director's output often does: "enemies ring
                            # *him* on all sides." Including those fields
                            # catches the pronoun even when the original prose
                            # doesn't carry it.
                            beat=(
                                f"{beat_prose} "
                                f"{directed.direction.action or ''} "
                                f"{directed.direction.layout or ''}"
                            ),
                        ):
                            # **The director path never carried the headcount
                            # tags, and that is the whole "everyone is a
                            # woman" bug.** `build_image_prompt` puts
                            # `1boy, male focus` at the very front for the
                            # measured reason that these checkpoints weight
                            # Danbooru count tags far above any English
                            # phrasing -- and `Direction.to_image_prompt`
                            # composes its own string from action, cast,
                            # setting and mood, with no tags anywhere. So
                            # every panel a real director wrote fell back to
                            # the checkpoint's training prior, which is
                            # overwhelmingly female, no matter how plainly
                            # the prose said "he". The negative clause alone
                            # could not hold the line on its own.
                            #
                            # `cast_tags` now also covers the *unresolved*
                            # cast case (`beat=` param): a beat whose cast
                            # never resolved to a named persona -- an
                            # unnamed mob role, a director-named character
                            # whose block window carried no matching mention
                            # -- used to leave `genders` empty and fall
                            # through with no tag at all. Confirmed still
                            # failing after the fix above, on a *different*
                            # checkpoint (noobai): RI ch1 blocks 0 and 36
                            # both rendered feminine-presenting subjects
                            # despite `gender_negative`'s exclusion already
                            # applying, because a negative clause opposes a
                            # look without asking for one. `cast_tags` falls
                            # back to the same beat-pronoun signal
                            # `gender_negative` already trusts, so both the
                            # positive and negative clauses now agree.
                            prompt = f"{tags}, {prompt}"
                    else:
                        prompt = build_image_prompt(
                            cast,
                            beat=beat_prose,
                            directive=directive,
                            character_appearances=appearances,
                            character_genders=genders,
                            world="" if closeup else world_setting(novel_id),
                            locale=(
                                ""
                                if closeup
                                else scene_locale_text
                            ),
                            style=style,
                        )
                    prompt = sanitize_prompt(prompt)
                    prompt_cache[cache_key] = prompt

                if is_crowd_cut:
                    # No character clause and no reference sheet: those are
                    # exactly the two things that collapse this panel back
                    # into a single figure. Danbooru count tags lead, since
                    # that is the vocabulary this checkpoint weights most.
                    _roles = ", ".join(
                        qualify_role(role, _scene_faction)
                        for role in sorted({m.role for m in (_chunk_mobs or _scene_mobs)})
                    )
                    # Framing leads. The first crowd panel that rendered put
                    # the crowd as tiny figures at the foot of a mountain --
                    # a landscape with people in it, not a reaction shot --
                    # because the locale outweighed everything. The point of
                    # this cut is the faces, so the shot has to be stated
                    # first and the locale demoted to a backdrop.
                    # **Distant-crowd-in-a-landscape is this checkpoint's
                    # ceiling, and it is worth taking.** Two attempts to pull
                    # the framing in for legible faces both collapsed: a
                    # "medium shot ... angry mob, shouting, bloodied" returned
                    # screaming muscular berserkers over a field of corpses,
                    # and a calmer "group standing together, front view"
                    # returned a garish poster collage with text artefacts.
                    # The locale-led version below is the one that produced a
                    # real crowd (people with banners on the mountain path
                    # under mist), so it stays until a checkpoint that can
                    # hold a crowd at closer range replaces it.
                    prompt = fit_to_budget(
                        [
                            # **Genre anchor first, and repeated.** GuoFeng3
                            # carries ancient-China style in the checkpoint
                            # itself, so a bare "xianxia cultivators" was
                            # enough; a general anime checkpoint carries no
                            # such prior and rendered this crowd as a
                            # European cathedral interior in modern cloaks.
                            # The setting has to be asserted, not assumed.
                            # **Scale the figures up, keep the vocabulary
                            # calm.** v16's crowd was real but tiny -- people
                            # at the foot of a mountain, a landscape with
                            # figures in it. The two attempts to pull in
                            # closer failed on *wording* ("angry mob",
                            # "shouting", "bloodied" -> gore and collage),
                            # not on framing, so this asks for large
                            # foreground figures while keeping the calm
                            # standoff language, and demotes the locale to
                            # the back of the prompt so it stops dictating
                            # the shot.
                            "ancient china, xianxia, wuxia, hanfu robes",
                            "crowd of chinese cultivators, multiple people, 6+boys",
                            "large figures in the foreground, seen from behind",
                            f"{_roles} standing close together, facing away",
                            "manhwa illustration, dramatic lighting, highly detailed",
                            scene_locale_text,
                        ]
                    )
                    references = []
                    conditioned = []

                digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                neg_prompt = ""  # set in the generation branch; "" on cache hit
                if image_path.exists():
                    report.skipped_cached += 1
                elif digest in generated_by_digest:
                    image_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(generated_by_digest[digest], image_path)
                    report.deduped_panels += 1
                else:
                    # 0.65 (the default) is right for a close-up -- a face
                    # is exactly what the reference sheet is meant to
                    # anchor there. It is wrong for a wide/establishing
                    # shot that needs a crowd, an environment, or an
                    # action pose the reference's neutral front-facing
                    # portrait never shows: confirmed directly on RI ch1's
                    # opening panel, whose prompt correctly described
                    # "warlords with drawn swords" and a mountain
                    # stronghold, but which rendered as a clean solo
                    # portrait regardless -- the reference *image*, not
                    # just its "solo" text tag (already fixed separately),
                    # was pulling the whole composition toward its own
                    # plain-background single-figure framing. Any panel
                    # with a background mob needs the most room for the
                    # prompt to actually draw the scene.
                    # **A wide shot of a crowd gets no reference sheet at
                    # all.** The sheet is a solo figure on a plain
                    # background, and IP-Adapter reproduces composition as
                    # well as face -- so on exactly the panels that need
                    # other people in frame it was overriding them. Verified
                    # both ways on RI ch1's opening siege: with the sheet
                    # attached the panel renders one man alone however
                    # explicitly the prompt asks for warlords, and a
                    # standalone generation at the same weight *without* a
                    # sheet produced the crowd and the environment. What the
                    # sheet buys is face consistency, which is worth almost
                    # nothing at wide-shot scale where faces are a few
                    # pixels -- so this trades a benefit we cannot see for a
                    # failure we can.
                    if _chunk_mobs and not closeup:
                        references = []
                        conditioned = []

                    # ...but a *curated* image is the exact opposite of a
                    # solo sheet: it was picked because it already shows the
                    # composition this panel needs (one figure against a
                    # crowd, a clan hall that reads as a clan hall). So the
                    # panels that just gave up their generated sheets are
                    # the ones most worth conditioning on a hand-picked one.
                    curated = match_scene_references(
                        _chunk_text,
                        has_mob=bool(_chunk_mobs),
                        closeup=closeup,
                    )
                    if curated:
                        references = curated + references[:1]
                        conditioned = conditioned or ["curated"]

                    if closeup:
                        weight = 0.65
                    elif curated:
                        # 0.3 exists because a *sheet* on a wide shot
                        # reproduces its own solo framing and erases the
                        # crowd. A curated composition reference has the
                        # opposite problem -- at 0.3 its layout barely
                        # registers -- and copying its layout is the entire
                        # reason it is attached.
                        weight = 0.5
                    elif _chunk_mobs:
                        weight = 0.3
                    else:
                        weight = 0.45
                    # **Gender clause has the highest priority and must
                    # survive truncation.** `negative_for(style)` alone
                    # uses ~69 tokens; the gender clause adds ~14 more,
                    # pushing the total to ~83 against CLIP's 75-token
                    # limit. CLIP silently truncates from the right -- so
                    # appending `gender_neg` LAST meant it was the first
                    # thing dropped. Verified: the assembled string
                    # `negative_for(STYLE_SCENE) + _NEGATIVE_FEMININE`
                    # measured at 98 tokens, 23 over budget, meaning the
                    # entire gender clause was discarded on every
                    # male-cast panel, removing the one guard against
                    # feminisation at inference time.
                    #
                    # Fix: re-fit the full assembled negative as a
                    # comma-split part list with gender terms at the
                    # front. `fit_to_budget` adds parts in priority
                    # order -- earlier = higher priority -- so gender
                    # terms fill the first slots and style terms use
                    # whatever space remains. Crowd terms get lowest
                    # priority (least critical to prevent feminisation).
                    # Same pronoun-coverage fix as `cast_tags` above:
                    # dialogue-only beats have no he/him/his in
                    # `beat_prose`, so also scan the director's own
                    # action/layout text where those pronouns appear.
                    gender_neg = gender_negative(
                        genders,
                        beat=(
                            f"{beat_prose} "
                            f"{directed.direction.action or '' if directed is not None else ''} "
                            f"{directed.direction.layout or '' if directed is not None else ''}"
                        ),
                    )
                    _base_neg = _form.filtered_negative(
                        negative_for(style) + _lexicon_negatives
                    )
                    _crowd_gore_neg = (
                        "gore, blood splatter, muscular, bare chest, screaming, western comic, corpses, fire"
                        if is_crowd_cut
                        else ""
                    )
                    # Crowd cuts need explicit female suppression beyond gender_neg:
                    # the model's prior for xianxia group scenes includes a female
                    # cultivator student even when gender_neg has "1girl, female,
                    # woman". Placed BEFORE base_neg so it survives budget trimming.
                    _crowd_female_neg = (
                        "girl, girls, female, woman, women, bishoujo"
                        if is_crowd_cut
                        else ""
                    )
                    # When the positive prompt calls for white robes, suppress the
                    # NoobAI xianxia checkpoint's strong teal/cyan prior. Placed
                    # FIRST so it survives budget trimming ahead of gender terms
                    # and the base negative tail.
                    _color_neg = (
                        "teal clothing, cyan robe, blue-green robe, turquoise outfit"
                        if "white robe" in prompt.lower()
                        else ""
                    )
                    _neg_parts = (
                        ([p.strip() for p in _color_neg.split(",") if p.strip()] if _color_neg else [])
                        + ([p.strip() for p in gender_neg.split(",") if p.strip()] if gender_neg else [])
                        + ([p.strip() for p in _crowd_female_neg.split(",") if p.strip()] if _crowd_female_neg else [])
                        + [p.strip() for p in _base_neg.split(",") if p.strip()]
                        + ([p.strip() for p in _crowd_gore_neg.split(",") if p.strip()] if _crowd_gore_neg else [])
                    )
                    neg_prompt = fit_to_budget(_neg_parts)
                    # Reference conditioning removed: IP-Adapter reference
                    # sheets caused color/composition contamination and cannot
                    # generalise across novels. Appearance is constrained by
                    # prompt text (appearance clause + style anchor) instead.
                    engine.generate(
                        PanelImageRequest(
                            prompt=prompt,
                            out_path=image_path,
                            negative_prompt=neg_prompt,
                            width=width,
                            height=height,
                            seed=seed,
                            reference_images=[],
                            reference_weight=0.0,
                        )
                    )
                    generated_by_digest[digest] = image_path
                    if conditioned:
                        report.conditioned_panels += 1
                    else:
                        report.prompt_only_panels += 1

                slot_images[slot] = PanelImage(
                    chapter=chapter_number,
                    block_index=lead,
                    prompt=prompt,
                    image_path=str(image_path),
                    conditioned_on=conditioned,
                    negative_prompt=neg_prompt,
                )
                report.panels += 1

            # One manifest row per block, all blocks sharing a slot
            # pointing at the same (already generated) image -- this is
            # what gives `render/timeline.py` its per-block shot mapping
            # while keeping the actual generation count down to the
            # scene's budget, not the scene's block count.
            for b in story_scene_blocks:
                image = slot_images[slot_for_block[b]]
                manifest.append(
                    PanelImage(
                        chapter=chapter_number,
                        block_index=b,
                        prompt=image.prompt,
                        image_path=image.image_path,
                        conditioned_on=image.conditioned_on,
                        negative_prompt=image.negative_prompt,
                    )
                )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.jsonl").write_text(
        "\n".join(json.dumps(asdict(p)) for p in manifest) + "\n",
        encoding="utf-8",
    )
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(prompt_cache, indent=2), encoding="utf-8")
    return report
