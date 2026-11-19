"""Chapter to pages: join a render's panel plan with the chapter's spans, compose, letter, export (roadmap M1 step 4).

**Panel-to-text mapping.** A panel row records the story blocks it is shown over (`block_indexes`), not
the spans, so the lettering for a panel is every visual span of those blocks. That is the same unit the
shot planner and the voiced timeline use; when one panel covers many blocks it simply carries many
lines, and whatever does not fit is reported in the manifest rather than dropped.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.core.store import Store
from echotales.pipeline import paths
from echotales.pipeline.pages.composer import (
    FORMATS,
    ComposerPanel,
    PageFacts,
    assign_roles,
    compose_pages,
)
from echotales.pipeline.pages.export import EXPORT_FORMATS, export_pages, split_strip
from echotales.pipeline.pages.lettering import LetterItem, LetterKind, Overflow
from echotales.pipeline.pages.render import render_page
from echotales.pipeline.render.anime import latest_panels_version
from echotales.pipeline.render.director import _delivery_intensity
from echotales.pipeline.render.plan import PanelPlan, load_panel_plan
from echotales.pipeline.spans.delivery import DeliveryPolarity, dominant_polarity, extract_delivery_markers
from echotales.pipeline.voice.delivery import strip_enclosing_quotes
from PIL import Image

#: Narration boxes per panel. A panel over many blocks would otherwise be mostly caption; the rest are
#: listed as `omitted` so a reviewer sees what the page leaves to the picture.
MAX_NARRATION_PER_PANEL = 1
_NARRATION = (SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION)


@dataclass(slots=True)
class ChapterPages:
    chapter: float
    out_dir: Path
    files: list[Path]
    page_count: int
    panels_version: str
    overflow: list[dict] = field(default_factory=list)
    manifest: Path | None = None


def parse_exports(spec: str | Sequence[str]) -> list[str]:
    items = [s.strip() for s in (spec.split(",") if isinstance(spec, str) else spec) if s.strip()]
    for item in items:
        if item not in EXPORT_FORMATS:
            raise ValueError(f"unknown export format {item!r}; expected one of {', '.join(EXPORT_FORMATS)}")
    return items or ["png"]


def _block_tag_text(spans: Sequence[Span]) -> str:
    """The narration around a line, where its speech tag ("... he shouted") lives. Dialogue spans carry
    no delivery markers of their own (`spans/classify.py`), and a marker inside quoted speech describes
    what was said, not how, so only the non-dialogue spans of the same block are read."""
    return " ".join(s.text for s in spans if s.span_type not in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE))


def _position_of(plan: PanelPlan, span: Span) -> str | None:
    if plan.direction is None or not span.speaker_self_id:
        return None
    member = next((m for m in plan.cast if m.self_id == span.speaker_self_id), None)
    if member is None:
        return None
    wanted = member.label.casefold()
    return next((c.position for c in plan.direction.characters if c.name.casefold() == wanted), None)


def panel_lettering(
    plan: PanelPlan, spans_by_block: dict[int, list[Span]]
) -> tuple[list[LetterItem], PageFacts, list[Overflow]]:
    """The panel's lettering items, the facts the role rules need, and what was left out on purpose."""
    items: list[LetterItem] = []
    omitted: list[Overflow] = []
    intensity = 0
    dialogue = 0
    narrations = 0
    for block in sorted(plan.block_indexes):
        spans = sorted(spans_by_block.get(block, []), key=lambda s: s.start)
        tag_text = _block_tag_text(spans)
        intensity = max(intensity, _delivery_intensity(tag_text))
        shouted = dominant_polarity(extract_delivery_markers(tag_text)) is DeliveryPolarity.HEIGHTENED
        # Narration next to a line of speech is almost always its speech tag ("she shouted."); a caption
        # repeating it would double what the bubble's tail and style already say.
        has_speech = any(s.span_type is SpanType.DIALOGUE for s in spans)
        for s in spans:
            if s.span_type is SpanType.DIALOGUE:
                dialogue += 1
                items.append(
                    LetterItem(s.id, LetterKind.SPEECH, strip_enclosing_quotes(s.text), _position_of(plan, s), shouted)
                )
            elif s.span_type is SpanType.INNER_MONOLOGUE:
                items.append(LetterItem(s.id, LetterKind.THOUGHT, strip_enclosing_quotes(s.text), _position_of(plan, s)))
            elif s.span_type in _NARRATION and not has_speech:
                if narrations < MAX_NARRATION_PER_PANEL:
                    narrations += 1
                    items.append(LetterItem(s.id, LetterKind.NARRATION, s.text))
                else:
                    omitted.append(Overflow(s.id, "omitted", s.text))
            # Exposition, system windows and crowd noise are not drawn (`SpanType.is_renderable_visually`).
    facts = PageFacts(plan.scene_index, plan.slot_kind, intensity, dialogue)
    return items, facts, omitted


def build_chapter_pages(
    store: Store,
    novel_id: str,
    chapter: float,
    *,
    fmt: str,
    exports: Sequence[str],
    panel_dir: str | Path | None = None,
    out_root: str | Path | None = None,
    suffix: str | None = None,
    panels_version: str | None = None,
) -> ChapterPages:
    """Page one chapter from its latest rendered panels. Writes `<out_root>/chN/vN_<suffix>/`."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown page format {fmt!r}; expected one of {', '.join(FORMATS)}")
    panel_dir = Path(panel_dir) if panel_dir is not None else Path(paths.asset_dir(novel_id, "panels"))
    out_root = Path(out_root) if out_root is not None else Path(paths.asset_dir(novel_id, "pages"))
    version_dir = (
        panel_dir / f"ch{chapter:g}" / panels_version if panels_version else latest_panels_version(panel_dir, chapter, novel_id)
    )
    plans = load_panel_plan(version_dir)
    if not plans:
        raise ValueError(f"{version_dir} has an empty panel plan; render chapter {chapter:g} again")

    spans_by_block: dict[int, list[Span]] = defaultdict(list)
    for s in store.get_spans(novel_id, chapter):
        spans_by_block[s.block_index].append(s)

    images: dict[str, Image.Image] = {}
    lettering: dict[str, list[LetterItem]] = {}
    facts: list[PageFacts] = []
    omitted: list[Overflow] = []
    for plan in plans:
        image_path = version_dir / plan.image_path
        if not image_path.is_file():
            raise FileNotFoundError(f"panel image {image_path} named by the panel plan is missing; render chapter {chapter:g} again")
        images[plan.panel_id] = Image.open(image_path).convert("RGB")
        items, f, om = panel_lettering(plan, spans_by_block)
        lettering[plan.panel_id] = items
        facts.append(f)
        omitted += om
    roles = assign_roles(facts)
    composer_panels = [
        ComposerPanel(p.panel_id, r, *images[p.panel_id].size) for p, r in zip(plans, roles, strict=True)
    ]
    layouts = compose_pages(composer_panels, fmt)

    rtl = fmt == "manga"
    rendered: list[Image.Image] = []
    overflow = [_overflow_row(o, None) for o in omitted]
    for layout in layouts:
        page, results = render_page(layout, images, lettering, rtl=rtl)
        for panel_id, res in results.items():
            overflow += [_overflow_row(o, panel_id) for o in res.overflow]
        rendered.append(page)
    if fmt == "webtoon":
        rendered = split_strip(rendered[0], layouts[0])

    base = out_root / f"ch{chapter:g}"
    out_dir = base / f"{paths.next_version(base)}_{suffix or fmt}"
    chapter_row = store.get_chapter(novel_id, chapter)
    novel_row = store.get_novel(novel_id) or {}
    files = export_pages(
        rendered, out_dir, f"{novel_id}_ch{chapter:g}", exports,
        title=chapter_row.title if chapter_row else f"Chapter {chapter:g}",
        series=novel_row.get("title", novel_id), number=f"{chapter:g}", manga=rtl,
    )
    manifest = out_dir / "pages.json"
    manifest.write_text(
        json.dumps(
            {
                "novel": novel_id, "chapter": chapter, "format": fmt, "panels_version": version_dir.name,
                "pages": len(rendered), "files": [f.name for f in files], "overflow": overflow,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Repo rule: every new version is named and gets a one-line entry at the same time it is made.
    with open(base / "VERSIONS.md", "a", encoding="utf-8") as fh:
        fh.write(
            f"\n## {out_dir.name}\n{time.strftime('%Y-%m-%d')}: {fmt} pages from panels {version_dir.name}, "
            f"{len(rendered)} pages, {len(overflow)} lettering notes; not yet reviewed by eye.\n"
        )
    return ChapterPages(chapter, out_dir, [*files, manifest], len(rendered), version_dir.name, overflow, manifest)


def _overflow_row(o: Overflow, panel_id: str | None) -> dict:
    return {"panel_id": panel_id, "span_id": o.span_id, "kind": o.kind, "lost_text": o.lost_text}


def build_pages(
    store: Store, novel_id: str, chapters: Sequence[float], *, fmt: str, exports: Sequence[str], **kw
) -> list[ChapterPages]:
    """Every chapter's panel version is resolved before any page is drawn, so a missing render fails fast."""
    panel_dir = Path(kw.get("panel_dir") or paths.asset_dir(novel_id, "panels"))
    for chapter in chapters:
        latest_panels_version(panel_dir, chapter, novel_id)
    return [build_chapter_pages(store, novel_id, c, fmt=fmt, exports=exports, **kw) for c in chapters]
