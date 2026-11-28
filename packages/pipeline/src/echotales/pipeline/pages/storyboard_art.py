"""Draw a `Storyboard`'s pictures with the drama compiler (`render/drama.py`, arm B2) instead of leaving them to the caller.

Why: `render_storyboard_webtoon` only lays out pictures somebody else made, and the only compiler that beat the production prompts
in the art-drama bake-off (docs/results/ART_DRAMA.md: relevant like arm A, dramatic like the NoobAI panels) was never wired to the
storyboard. This turns each panel's own schema fields (purpose, shot, shape, layer, cast and the look the director copied from the
bible) into the `PanelBrief` that `compile_drama` reads, so a real render gets the cinematic prompt without a hand-built brief.

Nothing here knows a novel: the only novel facts are the `looks` the caller supplies (cast looks come from the bible, never from
the storyboard) and the panel's own `visual` text."""

from __future__ import annotations

import base64
import io
import json
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from echotales.pipeline.persona.prompt import count_tokens
from echotales.pipeline.render.compiler import (
    CharacterBrief,
    CompiledPrompt,
    OutputMode,
    PanelBrief,
)
from echotales.pipeline.render.drama import compile_drama
from echotales.pipeline.render.lightgrade import light_grade
from echotales.pipeline.storyboard.schema import Panel, Segment, Shape, Shot, Storyboard

#: look_id or entity_id -> the person as the bible says they look at that story time.
Looks = Mapping[str, CharacterBrief]

_SHOT_WORD = {Shot.EXTREME_WIDE: "wide", Shot.WIDE: "wide", Shot.OVERHEAD: "wide", Shot.LOW_ANGLE: "wide", Shot.MEDIUM: "medium",
              Shot.MEDIUM_CLOSE: "medium", Shot.CLOSE: "close", Shot.EXTREME_CLOSE: "close", Shot.INSERT: "close"}
#: Z-Image's text window (`workers_zimage.MAX_TOKENS`). The CLIP 77-token rule does not bind this model (the style lead alone is 85
#: CLIP tokens); CLIP counts over-count Qwen's, so staying under it is conservative. Sections are dropped lowest priority first.
Z_IMAGE_TOKEN_BUDGET = 500
#: Never dropped: the lead, the camera, the drama and the identity sentences are what the bake-off showed carrying the picture.
_KEEP = ("style", "framing", "grade", "drama")
#: Pixel budget of the verified 832x1216 bake-off render (8 GB card), per panel shape.
_SIZE = {Shape.TALL: (832, 1216), Shape.BLEED: (832, 1216), Shape.WIDE: (1216, 832), Shape.INSET: (832, 832)}
_DEFAULT_SIZE = (960, 1040)


def _character(member, looks: Looks) -> CharacterBrief:
    base = looks.get(member.look_id or "") or looks.get(member.entity_id)
    if base is None:
        # No look in the bible: the name only, never a guessed face. The compiler still writes a gender noun ("person").
        return CharacterBrief(name=member.name, lead=True)
    return replace(base, name=base.name or member.name)


def panel_brief(panel: Panel, segment: Segment | None, looks: Looks, novel_id: str, mode: OutputMode = OutputMode.COLOUR) -> PanelBrief:
    """The brief `compile_drama` reads. The drama table keys on the panel's enums; this only supplies the facts they sit on."""
    chars = [_character(m, looks) for m in panel.cast]
    if chars:
        chars[0] = replace(chars[0], lead=True)
    free = not chars
    mood = segment.palette if segment else ""
    # An eyes-only extreme close withholds identity: "eyes" makes the compiler keep only the paragraph's eye sentences, so the
    # director's longer description can't add a face or a name the panel deliberately leaves out (bake-off p12).
    focus = "eyes" if free and panel.shot is Shot.EXTREME_CLOSE else "prop" if free and panel.shot is Shot.INSERT else ""
    return PanelBrief(
        novel_id=novel_id, characters=chars, location="" if focus == "eyes" else segment.place if segment else "", shot=_SHOT_WORD[panel.shot], mood=mood,
        mode=mode, composition=panel.visual, frame_focus=focus, grade=light_grade(panel.visual, mood=mood),
        empty_hands=False, manhua=False,
    )


def fit_sections(comp: CompiledPrompt, limit: int = Z_IMAGE_TOKEN_BUDGET) -> CompiledPrompt:
    """Drop the lowest-priority sections (from the end: setting, composition, staging) until the prompt fits the text window.
    Identity sentences go only after every scene section is gone."""
    sections = list(comp.sections)

    def total() -> int:
        return count_tokens(" ".join(s.text for s in sections))

    for droppable in (lambda s: s.label not in _KEEP and not s.label.startswith("character:"),
                      lambda s: s.label.startswith("character:")):
        while total() > limit:
            idx = [i for i, s in enumerate(sections) if droppable(s)]
            if not idx:
                break
            sections.pop(idx[-1])
    comp.sections = sections
    comp.positive = " ".join(s.text for s in sections)
    return comp


def compile_panel(panel: Panel, storyboard: Storyboard, looks: Looks, mode: OutputMode = OutputMode.COLOUR) -> CompiledPrompt | None:
    """The B2 prompt for one panel, or None for a card (`Shape.TEXT_ONLY` carries only letters, no picture)."""
    if panel.shape is Shape.TEXT_ONLY:
        return None
    seg = next((s for s in storyboard.segments if s.segment_id == panel.segment_id), None)
    brief = panel_brief(panel, seg, looks, storyboard.novel_id, mode)
    return fit_sections(compile_drama(brief, panel))


@dataclass
class DrawnStoryboard:
    images: dict[str, Path]
    prompts: dict[str, list[tuple[str, str]]]


class StubZImageWorker:
    """Deterministic offline worker with the `generate_many` shape of `LocalZImageWorker`: a solid PNG per prompt, no model."""

    def generate_many(self, requests, sections_list, *, greyscale: bool = False):
        from echotales.pipeline.workers_contract import ImageWorkerResponse
        from PIL import Image

        out = []
        for r in requests:
            c = zlib.crc32(r.prompt.encode())
            buf = io.BytesIO()
            Image.new("RGB", (r.width, r.height), (c % 200 + 30, (c >> 8) % 200 + 30, (c >> 16) % 200 + 30)).save(buf, "PNG")
            out.append(ImageWorkerResponse(image_b64=base64.b64encode(buf.getvalue()).decode(), seed=r.seed))
        return out


def draw_storyboard(
    storyboard: Storyboard, out_dir: Path, looks: Looks | None = None, *, model_key: str = "z-image-turbo", mode: OutputMode = OutputMode.COLOUR,
) -> DrawnStoryboard:
    """Compile every picture panel with B2 and render them in one batch (one model load), `<panel_id>.png` under `out_dir`.

    The worker is whatever `render/compiled_route.worker_for(model_key)` holds, so a test or the CLI's stub engine installs one with
    `set_worker`; nothing is routed to NoobAI here (licence, D58)."""
    from echotales.pipeline.render.compiled_route import generate_compiled_batch
    from echotales.pipeline.render.panels import PanelImageRequest

    out_dir = Path(out_dir)
    reqs: list[PanelImageRequest] = []
    secs: list[list[tuple[str, str]]] = []
    prompts: dict[str, list[tuple[str, str]]] = {}
    for p in storyboard.panels:
        comp = compile_panel(p, storyboard, looks or {}, mode)
        if comp is None:
            continue
        w, h = _SIZE.get(p.shape, _DEFAULT_SIZE)
        reqs.append(PanelImageRequest(prompt=comp.positive, out_path=out_dir / f"{p.panel_id}.png", width=w, height=h,
                                      seed=zlib.crc32(p.panel_id.encode()) % 2**31))
        secs.append([(s.label, s.text) for s in comp.sections])
        prompts[p.panel_id] = secs[-1]
    failed = generate_compiled_batch(reqs, secs, model_key, greyscale=mode is OutputMode.MANGA)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompts.json").write_text(json.dumps(prompts, indent=1))
    bad = {r.out_path for r in failed}
    return DrawnStoryboard({q.out_path.stem: q.out_path for q in reqs if q.out_path not in bad}, prompts)
