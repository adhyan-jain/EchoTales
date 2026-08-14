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
from echotales.pipeline.persona.attire import scene_locale, world_setting
from echotales.pipeline.persona.prompt import (
    STYLE_CLOSEUP,
    build_image_prompt,
    negative_for,
    shot_style,
)
from echotales.pipeline.persona.runner import get_panel_cast
from echotales.pipeline.render._png import write_solid_png
from echotales.pipeline.render.beats import segment_beats
from echotales.pipeline.render.direction import direct_beat
from echotales.pipeline.render.palette import Palette, PaletteSpec, apply_palette
from echotales.pipeline.world.context import story_context

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
    if name == "gemini":
        from echotales.pipeline.render.gemini import GeminiImageEngine

        return GeminiImageEngine(**kwargs)  # type: ignore[arg-type,return-value]
    if name == "openrouter":
        from echotales.pipeline.render.openrouter import OpenRouterImageEngine

        return OpenRouterImageEngine(**kwargs)  # type: ignore[arg-type,return-value]
    raise ValueError(
        f"unknown image engine {name!r}; expected 'stub', 'sdxl', 'manga', "
        "'gemini' or 'openrouter'"
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
) -> tuple[str, str, Path | None, str] | None:
    """`(label, appearance clause, reference sheet, gender)` for one entity.

    `chapter` selects which *body* to draw. A character who was reborn or
    transmigrated has more than one persona, each with its own appearance and
    its own reference sheet, and drawing chapter 40's panel from chapter 1's
    body is the exact error the self/persona split exists to prevent. None
    means "their latest body", which is the right answer for a cast list and
    the wrong one for a panel -- so panel rendering always passes it.

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
        clause = build_reference_prompt(
            entity.canonical_label,
            appearance,
            gender=gender,
            age_band=_age,
            with_style=False,
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
    client: object | None = None,
    max_panels: int = 14,
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

        # One panel per *beat*, not per block. See `render/beats.py`: a
        # paragraph is not a panel, and drawing every paragraph produced 89
        # near-duplicate images per chapter, mostly scenery.
        by_index_text = {b.index: b.text for b in chapter.blocks}
        beats = segment_beats(spans, segments, max_panels=max_panels)
        if not beats:
            # No spans for this chapter (not span-classified yet, or a
            # fixture): fall back to one beat per story block so the stage
            # still produces something rather than silently nothing.
            from echotales.pipeline.render.beats import Beat

            story = [
                b.index
                for b in chapter.blocks
                if b.block_type.is_story_content and b.text.strip()
            ][:max_panels]
            beats = [
                Beat(index=i, blocks=[bi], text=by_index_text.get(bi, ""))
                for i, bi in enumerate(story)
            ]
        lead_blocks = {b.lead_block: b for b in beats}
        by_index = {b.index: b for b in chapter.blocks}

        for lead, beat in sorted(lead_blocks.items()):
            block = by_index.get(lead)
            if block is None or not block.text.strip():
                continue
            if not block.block_type.is_story_content:
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
            for entity_id in present_beat_entities(mentions, beat.blocks):
                looks = character_looks(
                    store, entity_id, novel_id=novel_id, chapter=chapter_number
                )
                if looks is None:
                    continue
                label, clause, sheet, gender = looks
                genders.append(gender)
                if clause:
                    appearances[label] = clause
                if sheet is not None:
                    references.append(sheet)
                    conditioned.append(label)

            beat_prose = beat.text or beat_text(spans, block.index, block.text)
            # Framing from everything the beat contains, not one style for
            # the whole chapter. See `prompt.py::shot_style`.
            style = shot_style(
                [s.span_type.value for s in spans if s.block_index in set(beat.blocks)]
            )
            closeup = style is STYLE_CLOSEUP

            # **Ask a model what this panel should show**, and only fall back
            # to mechanical assembly when there is no client or the call
            # fails. An assembled prompt is grammatical and about nothing:
            # it cannot know what is happening in the beat, which is why
            # panels came back unrelated to the story around them.
            directed = None
            if client is not None:
                brief = story_context(
                    novel_id, store, chapter_number, beat.blocks
                ).to_brief()
                directed = direct_beat(
                    beat_prose,
                    context_brief=brief,
                    cast={k: v for k, v in appearances.items() if v},
                    novel_style=world_setting(novel_id),
                    client=client,
                    novel_id=novel_id,
                )

            if directed is not None:
                prompt = directed.to_image_prompt()
            else:
                prompt = build_image_prompt(
                    cast,
                    beat=beat_prose,
                    character_appearances=appearances,
                    character_genders=genders,
                    # A close-up's background is deliberately abstract tone,
                    # so feeding it a courtyard only fights the framing.
                    world="" if closeup else world_setting(novel_id),
                    locale=(
                        ""
                        if closeup
                        else scene_locale(
                            novel_id, beat_prose, block_index=block.index
                        )
                    ),
                    style=style,
                )

            if image_path.exists():
                report.skipped_cached += 1
            else:
                engine.generate(
                    PanelImageRequest(
                        prompt=prompt,
                        out_path=image_path,
                        negative_prompt=negative_for(style),
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
