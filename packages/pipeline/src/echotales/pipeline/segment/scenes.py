"""Scene cuts for a chapter: induced conventions, then implicit cuts, then story order.

This is the orchestration the segment runner calls behind `SceneCutConfig`. It
splits MAIN segments only. A rule-detected dream or flashback keeps its bounds
(the rules are the higher-precision signal, see `runner._merge_llm_proposals`),
and a scene cut inside one of them is not asked about.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from typing import Any

from echotales.core.enums import Canonicity, SegmentType
from echotales.core.models import Chapter, Mention, NarrativeSegment
from echotales.core.store import Store
from echotales.pipeline.segment.cuts import SEGMENT_FOR_CUT, CutType, SceneCut, TimeRelation
from echotales.pipeline.segment.discontinuity import Boundary, TopicModel, score_chapter
from echotales.pipeline.segment.implicit import propose_implicit_cuts, resolve_story_order
from echotales.pipeline.segment.induce import ConventionSet, find_induced_cuts

_ARTIFACT_PREFIX = "scene_cuts"


@dataclass(slots=True)
class SceneCutConfig:
    """Turns the per-novel scene-cut pass on. Off by default so existing behaviour is unchanged."""

    enabled: bool = False
    #: Chapters from the start of the volume the conventions are learned on.
    learn_chapters: int = 10
    conventions_dir: str = "data/lexicons"
    #: Small local model for the implicit-cut and story-order passes. None means conventions only.
    llm: Any | None = None
    max_implicit_per_chapter: int = 4


@dataclass(slots=True)
class SceneAnalysis:
    chapter: float
    cuts: list[SceneCut] = field(default_factory=list)
    #: Indices (reading order, from 0) of segments the story order pass called a prior loop.
    prior_loop_segments: set[int] = field(default_factory=set)
    boundaries: list[Boundary] = field(default_factory=list)


def analyse_chapter_scenes(
    chapter: Chapter,
    conventions: ConventionSet | None,
    *,
    mentions: list[Mention] | None = None,
    llm: Any | None = None,
    nlp: Any | None = None,
    topic: TopicModel | None = None,
    max_implicit: int = 4,
) -> SceneAnalysis:
    boundaries = score_chapter(chapter, mentions, nlp=nlp, topic=topic)
    cuts: list[SceneCut] = []
    score_at = {b.position: b.score for b in boundaries}
    weak: set[int] = set()
    if conventions is not None:
        for c in find_induced_cuts(chapter, conventions, nlp=nlp):
            c.score = round(score_at.get(c.block, 0.0), 3)
            if c.source.startswith("induced-strong"):
                cuts.append(c)
            else:
                weak.add(c.block)
    prior: set[int] = set()
    if llm is not None and conventions is not None:
        taken = {c.block for c in cuts}
        cuts += propose_implicit_cuts(
            chapter,
            boundaries,
            taken,
            llm,
            threshold=conventions.candidate_threshold,
            priority=weak,
            max_cuts=max_implicit,
        )
        cuts.sort(key=lambda c: c.block)
        prior = resolve_story_order(chapter, cuts, llm, nlp=nlp)
    return SceneAnalysis(chapter=chapter.number, cuts=cuts, prior_loop_segments=prior, boundaries=boundaries)


def apply_cuts_to_segments(
    chapter: Chapter, segments: list[NarrativeSegment], analysis: SceneAnalysis
) -> list[NarrativeSegment]:
    """Split MAIN segments at scene cuts; keep every other segment as it is."""
    if not analysis.cuts and not analysis.prior_loop_segments:
        return segments
    ranges_start = [0] + [c.block for c in analysis.cuts]
    cut_at = {c.block: c for c in analysis.cuts}
    out: list[NarrativeSegment] = []
    ordinal = 0
    for seg in segments:
        if seg.segment_type is not SegmentType.MAIN:
            out.append(seg)
            continue
        inner = [b for b in ranges_start if seg.offset_from < b <= seg.offset_to]
        edges = [seg.offset_from, *inner, seg.offset_to + 1]
        for lo, nxt in pairwise(edges):
            hi = nxt - 1
            cut = cut_at.get(lo)
            seg_idx = ranges_start.index(lo) if lo in ranges_start else 0
            is_prior = seg_idx in analysis.prior_loop_segments
            cut_type = CutType.PRIOR_LOOP if is_prior else (cut.cut_type if cut else CutType.NEW_SCENE)
            stype, layer = SEGMENT_FOR_CUT[cut_type]
            if lo == seg.offset_from and hi == seg.offset_to and stype is SegmentType.MAIN:
                out.append(seg)
                continue
            if stype is SegmentType.MAIN:
                out.append(
                    seg.model_copy(update={"id": f"{seg.novel_id}:{seg.chapter_from:g}:main{lo}", "offset_from": lo, "offset_to": hi})
                )
            else:
                ordinal += 1
                out.append(
                    NarrativeSegment(
                        id=f"{seg.novel_id}:{seg.chapter_from:g}:scene{lo}",
                        novel_id=seg.novel_id,
                        chapter_from=seg.chapter_from,
                        offset_from=lo,
                        chapter_to=seg.chapter_to,
                        offset_to=hi,
                        timeline_id=f"{stype.value}_CH{seg.chapter_from:g}_S{ordinal}",
                        story_seq_from=0.0,
                        story_seq_to=float(hi - lo),
                        segment_type=stype,
                        narrative_layer=layer,
                        canonicity=Canonicity.CANONICAL,
                        confidence=cut.confidence if cut else 0.5,
                    )
                )
    return sorted(out, key=lambda s: s.offset_from)


def save_scene_cuts(store: Store, novel_id: str, analysis: SceneAnalysis) -> None:
    """Persist cut labels (type, time relation, evidence) that NarrativeSegment has no column for."""
    payload = {
        "cuts": [asdict(c) for c in analysis.cuts],
        "prior_loop_segments": sorted(analysis.prior_loop_segments),
    }
    store.conn.execute(
        "INSERT OR REPLACE INTO derived_artifact (id, tier, read_set_json, read_set_hash, payload_json, invalidated)"
        " VALUES (?, 'scene_cuts', '[]', '', ?, 0)",
        (f"{_ARTIFACT_PREFIX}:{novel_id}:{analysis.chapter:g}", json.dumps(payload, default=str)),
    )


def load_scene_cuts(store: Store, novel_id: str, chapter: float) -> SceneAnalysis | None:
    row = store.conn.execute(
        "SELECT payload_json FROM derived_artifact WHERE id=?", (f"{_ARTIFACT_PREFIX}:{novel_id}:{chapter:g}",)
    ).fetchone()
    if not row:
        return None
    raw = json.loads(row[0])
    cuts = [
        SceneCut(
            **{
                **c,
                "cut_type": CutType(c["cut_type"]),
                "time_relation": TimeRelation(c["time_relation"]),
            }
        )
        for c in raw["cuts"]
    ]
    return SceneAnalysis(chapter=chapter, cuts=cuts, prior_loop_segments=set(raw["prior_loop_segments"]))
