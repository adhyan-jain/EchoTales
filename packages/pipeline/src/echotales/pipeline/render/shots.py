"""Shot planning: which panels get generated motion, which are held, and where the cuts fall.

**Why this exists.** The owner wants adjacent panels turned into continuous clips, but a probe on the
8 GB laptop (EVOLUTION 4.146, decision D45) showed what a video model can and cannot do: one panel
plus a mild prompt keeps identity; first-and-last-frame works only when the end frame is a crop of
the start frame (SSIM 0.91); between two independently drawn panels it holds, garbles, then snaps.
So the planner never asks an engine for more than its declared `VideoCapability`, and the decision
is a table (`DECISION_TABLE`) rather than nested conditions, so the legal outcomes sit in one place.

Pure logic: no model, no ffmpeg, no files except `write_shots` / `load_shots`. One shot per panel:
a panel is already the unit that holds a run of story blocks over one picture, and splitting inside
it would invent a second keyframe the engine cannot draw consistently.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from echotales.core.enums import SpanType
from echotales.pipeline.render.direction import PanelDirection
from echotales.pipeline.render.director import _delivery_intensity
from echotales.pipeline.render.motion import match_tag
from echotales.pipeline.render.plan import PanelPlan
from echotales.pipeline.screenplay.schema import CameraMove, Transition
from echotales.pipeline.voice.timing import LineTiming
from pydantic import BaseModel, Field

SHOTS_SCHEMA_VERSION = 1
SHOTS_FILE = "shots.jsonl"


class ShotsSchemaError(ValueError):
    """A shots file this code cannot read."""


class _Ordered(StrEnum):
    """Members compare by declaration order, so `pair <= engine.max_pair_difference` reads as intended."""

    @property
    def rank(self) -> int:
        return list(type(self)).index(self)

    def __lt__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.rank < other.rank

    def __le__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.rank > other.rank

    def __ge__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.rank >= other.rank


class PairDifference(_Ordered):
    """How different two frames are; the widest pair an engine can join."""

    SAME_FRAME_DERIVED = "SAME_FRAME_DERIVED"
    SAME_SHOT = "SAME_SHOT"
    SAME_SCENE_SAME_CAST = "SAME_SCENE_SAME_CAST"
    ANY = "ANY"


class MotionLevel(_Ordered):
    """The strongest motion shown without identity drift (probe: a strong action prompt made wounds vanish)."""

    SUBTLE = "SUBTLE"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class ShotMode(StrEnum):
    HOLD = "HOLD"
    ANIMATE = "ANIMATE"
    INTERPOLATE = "INTERPOLATE"


# --------------------------------------------------------------------------- capability


@dataclass(frozen=True, slots=True)
class VideoCapability:
    """What a video engine can do, as plain data a later engine registry can take over."""

    engine_id: str
    tier: Literal["local", "cloud"]
    fps: int
    max_frames: int
    sizes: tuple[tuple[int, int], ...]
    supports_single_image: bool
    supports_first_last: bool
    max_pair_difference: PairDifference
    max_motion: MotionLevel
    seconds_per_clip: float
    #: (min, max): the model cannot stay loaded between clips on 8 GB, so every clip pays this.
    reload_seconds: tuple[float, float]
    #: False means the numbers are assumptions, not a run.
    measured: bool
    licence: str = ""

    @property
    def max_clip_seconds(self) -> float:
        return self.max_frames / self.fps if self.fps else 0.0

    @property
    def can_generate(self) -> bool:
        return self.max_frames > 0 and (self.supports_single_image or self.supports_first_last)


STILLS = VideoCapability(
    engine_id="stills", tier="local", fps=0, max_frames=0, sizes=(),
    supports_single_image=False, supports_first_last=False,
    max_pair_difference=PairDifference.SAME_FRAME_DERIVED, max_motion=MotionLevel.SUBTLE,
    seconds_per_clip=0.0, reload_seconds=(0.0, 0.0), measured=True, licence="n/a",
)

#: EVOLUTION 4.146 probe, 8 GB laptop, real project panels.
LOCAL_LTX = VideoCapability(
    engine_id="ltx-video-2b-distilled", tier="local", fps=24, max_frames=97, sizes=((512, 768),),
    supports_single_image=True, supports_first_last=True,
    max_pair_difference=PairDifference.SAME_FRAME_DERIVED, max_motion=MotionLevel.SUBTLE,
    seconds_per_clip=17.0, reload_seconds=(9.0, 50.0), measured=True,
    licence="LTXV Open Weights Licence (source-available; read the commercial terms before selling)",
)

# ASSUMED, NOT RUN: an anime-trained model on a rented GPU is expected to handle larger motion and
# keyframe interpolation within one scene. Every number below is a guess until D45's cloud run happens.
CLOUD_ANIME = VideoCapability(
    engine_id="cloud-anime-assumed", tier="cloud", fps=24, max_frames=121, sizes=((832, 1248),),
    supports_single_image=True, supports_first_last=True,
    max_pair_difference=PairDifference.SAME_SCENE_SAME_CAST, max_motion=MotionLevel.STRONG,
    seconds_per_clip=30.0, reload_seconds=(5.0, 20.0), measured=False,
    licence="unknown until a model is chosen",
)


@dataclass(frozen=True, slots=True)
class ShotBudget:
    max_generated_seconds: float = 120.0
    max_clips: int = 30
    base_seed: int = 0


# --------------------------------------------------------------------------- record


class DerivedEnd(BaseModel):
    """An end frame cut from the start panel; described here, rendered by the composer."""

    transform: Literal["push_in"] = "push_in"
    #: Final crop is 1/scale of the frame, centred on (cx, cy) in 0..1.
    scale: float
    cx: float = 0.5
    cy: float = 0.5


class Fallback(BaseModel):
    mode: Literal["HOLD"] = "HOLD"
    camera_move: CameraMove


class ShotSpec(BaseModel):
    schema_version: int = SHOTS_SCHEMA_VERSION
    novel_id: str
    chapter: float
    shot_index: int
    panel_id: str
    engine_id: str
    block_indexes: list[int]
    span_ids: list[str]
    #: Gapless clock (what the video path plays); the shot lasts exactly as long as its audio.
    start: float
    end: float
    duration: float
    mode: ShotMode
    #: The still's move: used by HOLD, by the held part of a generated shot, and by the fallback.
    camera_move: CameraMove
    end_panel_id: str | None = None
    end_derived: DerivedEnd | None = None
    #: Difference between this panel and the next one, whatever mode was chosen.
    pair_difference: PairDifference | None = None
    motion: MotionLevel
    motion_requested: MotionLevel
    motion_prompt: str = ""
    transition_to_next: Transition = Transition.CUT
    #: Where inside the shot (seconds from `start`) the generated clip plays, and how long. The rest
    #: is a held still: the start panel before an INTERPOLATE clip that lands on `end_panel_id`, the
    #: clip's last frame after an ANIMATE or derived clip.
    generated_start: float = 0.0
    generated_seconds: float = 0.0
    frames: int = 0
    seed: int
    fallback: Fallback
    reasons: list[str] = Field(default_factory=list)

    @property
    def hold_seconds(self) -> float:
        return self.duration - self.generated_seconds


# --------------------------------------------------------------------------- decision table


@dataclass(frozen=True, slots=True)
class ShotFacts:
    """Everything the table's conditions may look at, computed once per panel."""

    cap: VideoCapability
    duration: float
    slot_kind: str
    has_cast: bool
    next_pair: PairDifference | None
    dialogue_exchange: bool


#: A clip shorter than this is not worth ~17 s of generation plus a 9-50 s model reload.
MIN_GENERATE_SECONDS = 1.5
#: A scene change is a cut by design: nothing in the panel pair says the same place continues.
JOINABLE = PairDifference.SAME_SCENE_SAME_CAST

PREDICATES: dict[str, Callable[[ShotFacts], bool]] = {
    "engine_cannot_generate": lambda f: not f.cap.can_generate,
    "too_short": lambda f: f.duration < MIN_GENERATE_SECONDS,
    "crowd": lambda f: f.slot_kind == "crowd",
    "establishing": lambda f: f.slot_kind == "establishing",
    # A crowd is excluded by an earlier row; an empty cast has no one to move.
    "has_characters": lambda f: f.has_cast and f.slot_kind != "crowd",
    "can_single": lambda f: f.cap.supports_single_image,
    "can_first_last": lambda f: f.cap.supports_first_last,
    "next_joinable": lambda f: (
        f.cap.supports_first_last
        and f.next_pair is not None
        and f.next_pair <= f.cap.max_pair_difference
        and f.next_pair <= JOINABLE
    ),
    "dialogue_exchange": lambda f: f.dialogue_exchange,
}

EndFrame = Literal["", "panel", "derived"]


@dataclass(frozen=True, slots=True)
class Row:
    id: str
    #: All must hold; a leading "!" negates.
    when: tuple[str, ...]
    mode: ShotMode
    end: EndFrame
    reason: str


#: First matching row wins. Row order is the priority: capability and length first, then who is in
#: the picture, then the richest generation the engine allows, then the plain hold.
DECISION_TABLE: tuple[Row, ...] = (
    Row("R1_no_engine", ("engine_cannot_generate",), ShotMode.HOLD, "", "engine cannot generate: hold"),
    Row("R2_too_short", ("too_short",), ShotMode.HOLD, "", "shorter than min generate: hold"),
    Row("R3_crowd", ("crowd",), ShotMode.HOLD, "", "crowd panel: no character motion: hold"),
    Row("R4_no_characters", ("!has_characters", "!establishing"), ShotMode.HOLD, "",
        "no characters: hold"),
    Row("R5_ambient_establishing", ("establishing", "can_single"), ShotMode.ANIMATE, "",
        "establishing: ambient motion only"),
    Row("R6_interpolate_next_panel", ("has_characters", "!establishing", "next_joinable"),
        ShotMode.INTERPOLATE, "panel", "next panel joinable: interpolate"),
    Row("R7_dialogue_push_in", ("has_characters", "!establishing", "can_first_last", "dialogue_exchange"),
        ShotMode.INTERPOLATE, "derived", "dialogue exchange on one panel: push-in to derived end frame"),
    Row("R8_animate_single", ("has_characters", "!establishing", "can_single"),
        ShotMode.ANIMATE, "", "animate the one panel"),
    Row("R9_hold_default", (), ShotMode.HOLD, "", "engine has no matching capability: hold"),
)


def _holds(row: Row, facts: ShotFacts) -> bool:
    return all(
        (not PREDICATES[c[1:]](facts)) if c.startswith("!") else PREDICATES[c](facts) for c in row.when
    )


def decide(facts: ShotFacts) -> Row:
    return next(r for r in DECISION_TABLE if _holds(r, facts))


# --------------------------------------------------------------------------- rules


def pair_difference(a: PanelPlan, b: PanelPlan) -> PairDifference:
    """How differently two panels are composed.

    Two panels drawn independently are different compositions even inside one scene (probe: first-last
    between them held, garbled and snapped), so SAME_SHOT needs the same slot kind and the same
    director shot size on top of scene, cast and location. A missing direction cannot confirm a shot.
    """
    same_scene = a.scene_index == b.scene_index and a.scene_state_id == b.scene_state_id
    same_cast = {m.self_id for m in a.cast} == {m.self_id for m in b.cast}
    if not (same_scene and same_cast and a.location == b.location):
        return PairDifference.ANY
    if (
        a.slot_kind == b.slot_kind
        and a.direction is not None
        and b.direction is not None
        and a.direction.shot == b.direction.shot
    ):
        return PairDifference.SAME_SHOT
    return PairDifference.SAME_SCENE_SAME_CAST


_STRONG_TAGS = {"clash", "impact"}
_MODERATE_TAGS = {"flame", "wind"}


def requested_motion(
    direction: PanelDirection | None,
    lines: Sequence[LineTiming],
    emotions: dict[str, tuple[str, int]] | None,
) -> tuple[MotionLevel, str]:
    """The motion the beat asks for, before the engine's cap.

    strength 0-3 is the maximum of: the reader's emotion intensity (1-3) of any covered line;
    delivery-marker intensity (`director._delivery_intensity`, 0-3) of any covered line's text; and
    the director's action text via `match_tag`: clash/impact = 3, flame/wind = 2, any other tag or
    stated action = 1. Delivery markers are read from the line's own text so they override scene
    sentiment (non-negotiable 10). 3 -> STRONG, 2 -> MODERATE, else SUBTLE.
    """
    emo = max((emotions or {}).get(t.span_id, ("", 0))[1] for t in lines) if lines and emotions else 0
    deliv = max((_delivery_intensity(t.text) for t in lines), default=0)
    action = 0
    if direction is not None and direction.action.strip():
        tag = match_tag(direction.action.replace("_", " "))
        action = 3 if tag in _STRONG_TAGS else 2 if tag in _MODERATE_TAGS else 1
    strength = max(emo, deliv, action)
    level = MotionLevel.STRONG if strength >= 3 else MotionLevel.MODERATE if strength == 2 else MotionLevel.SUBTLE
    return level, f"strength={strength} (emotion={emo} delivery={deliv} action={action})"


_LEVEL_WORDS = {
    MotionLevel.SUBTLE: "subtle movement",
    MotionLevel.MODERATE: "moderate movement",
    MotionLevel.STRONG: "dynamic movement",
}


def motion_prompt(
    direction: PanelDirection | None, level: MotionLevel, *, ambient: bool, push_in: bool
) -> str:
    """Motion only: the keyframe already carries identity, and restating appearance invites drift.

    Empty without a direction: the panel's own prompt describes the picture, not the movement.
    """
    if direction is None:
        return ""
    if ambient:
        parts = [direction.setting, direction.lighting, "gentle ambient motion, no people"]
    else:
        parts = [direction.action, direction.expression, "slow steady push-in" if push_in else "",
                 _LEVEL_WORDS[level]]
    text = ", ".join(p.strip() for p in parts if p and p.strip()).replace("_", " ")
    stripped = {direction.action.strip(), direction.expression.strip(), direction.setting.strip(),
                direction.lighting.strip()} - {""}
    return text if stripped else ""


def hold_camera_move(lines: Sequence[LineTiming], lead_block: int) -> CameraMove:
    """Today's `director._pan_direction` over the shot's lines: dialogue pushes in, pure description
    pans (side alternates by block parity), anything else pulls out."""
    types = {t.span_type for t in lines}
    if SpanType.DIALOGUE.value in types:
        return CameraMove.SLOW_PUSH_IN
    if SpanType.NARRATION_DESCRIPTION.value in types:
        return CameraMove.PAN_LEFT if lead_block % 2 == 0 else CameraMove.PAN_RIGHT
    return CameraMove.PULL_OUT


#: TUNING, not measured: the probe's end frame was a crop of the start frame landing at SSIM 0.91; its
#: exact scale was not recorded. 1.10 is a visible-but-gentle push.
PUSH_IN_SCALE = 1.10


def _seed(base: int, novel: str, chapter: float, panel_id: str) -> int:
    h = hashlib.sha256(f"{base}|{novel}|{chapter:g}|{panel_id}".encode()).digest()
    return int.from_bytes(h[:4], "big") & 0x7FFFFFFF


# --------------------------------------------------------------------------- planner


def panel_runs(panels: list[PanelPlan], timing: Sequence[LineTiming]) -> list[tuple[PanelPlan, list[LineTiming]]]:
    """The voiced lines grouped into runs that share a panel, in play order. Shared by `plan_shots` and the episode
    composer so the two never disagree about which picture a line plays over.

    A real render interleaves blocks (RI ch1 v55: panel 2 holds blocks 1 and 3, panel 1 holds block 2) because an image
    is reused for a later block; the panel then simply returns to the screen as a cut-back, one run per visit. A voiced
    block no panel claims (a heading, a skipped block) rides on the previous line's panel, or on the first panel when it
    leads the chapter. A panel with no voiced line has no run: it would be a zero-length shot."""
    owner = {b: p for p in panels for b in p.block_indexes}
    runs: list[tuple[PanelPlan, list[LineTiming]]] = []
    prev = -1
    for t in timing:
        if t.block_index < prev:
            raise ValueError(f"timing is not in block order at span {t.span_id!r}")
        prev = t.block_index
        panel = owner.get(t.block_index) or (runs[-1][0] if runs else panels[0])
        if runs and runs[-1][0] is panel:
            runs[-1][1].append(t)
        else:
            runs.append((panel, [t]))
    return runs


def plan_shots(
    panels: list[PanelPlan],
    timing: list[LineTiming],
    capability: VideoCapability,
    budget: ShotBudget,
    *,
    emotions: dict[str, tuple[str, int]] | None = None,
) -> list[ShotSpec]:
    """One `ShotSpec` per panel visit (a run of lines over one panel), tiling the chapter's gapless audio exactly."""
    if not panels:
        if timing:
            raise ValueError(f"{len(timing)} voiced lines but no panels to show them over")
        return []
    panels = sorted(panels, key=lambda p: (min(p.block_indexes), p.panel_seq))
    runs = panel_runs(panels, timing)
    voiced = {t.block_index for t in timing}

    shots: list[ShotSpec] = []
    cursor = 0.0
    for i, (panel, lines) in enumerate(runs):
        nxt = runs[i + 1][0] if i + 1 < len(runs) else None
        start = cursor
        end = lines[-1].end_gapless
        cursor = end
        duration = end - start
        pair = pair_difference(panel, nxt) if nxt else None
        facts = ShotFacts(
            cap=capability, duration=duration, slot_kind=panel.slot_kind, has_cast=bool(panel.cast),
            next_pair=pair,
            dialogue_exchange=len({
                t.speaker_id or t.speaker_label for t in lines if t.span_type == SpanType.DIALOGUE.value
            }) >= 2,
        )
        row = decide(facts)
        reasons = [f"row={row.id}", row.reason]

        requested, why = requested_motion(panel.direction, lines, emotions)
        level = requested
        ambient = row.id == "R5_ambient_establishing"
        if ambient:
            level = MotionLevel.SUBTLE
            reasons.append("ambient motion only: no character motion on an establishing panel")
        elif requested > capability.max_motion:
            level = capability.max_motion
            reasons.append(f"motion capped {requested.value}->{level.value} by engine")
        reasons.append(why)

        if panel.direction is None and row.mode is not ShotMode.HOLD:
            reasons.append("no direction: no motion prompt")
        if pair is not None and row.id not in {"R6_interpolate_next_panel"}:
            if pair > JOINABLE:
                reasons.append(f"pair_difference={pair.value}: scene or cast change: cut")
            elif capability.supports_first_last and pair > capability.max_pair_difference:
                reasons.append(
                    f"pair_difference={pair.value} exceeds engine "
                    f"{capability.max_pair_difference.value}: cut"
                )

        camera = hold_camera_move(lines, panel.lead_block)
        mode = row.mode
        gen = 0.0
        frames = 0
        gen_start = 0.0
        if mode is not ShotMode.HOLD:
            gen = min(duration, capability.max_clip_seconds)
            frames = min(capability.max_frames, max(1, round(gen * capability.fps)))
            if row.end == "panel":
                gen_start = duration - gen
            if gen < duration:
                reasons.append(
                    f"generated {gen:.2f}s of {duration:.2f}s (engine max clip "
                    f"{capability.max_clip_seconds:.2f}s): hold the rest"
                )

        folded = sorted({t.block_index for t in lines} - set(panel.block_indexes))
        if folded:
            reasons.append(f"blocks without a panel carried: {folded}")
        # A block this panel owns but another visit voices belongs to that visit, not this one.
        mine = sorted({t.block_index for t in lines} | (set(panel.block_indexes) - voiced))

        shots.append(ShotSpec(
            novel_id=panel.novel_id, chapter=panel.chapter, shot_index=i, panel_id=panel.panel_id,
            engine_id=capability.engine_id,
            block_indexes=mine,
            span_ids=[t.span_id for t in lines], start=start, end=end, duration=duration,
            mode=mode, camera_move=camera,
            end_panel_id=nxt.panel_id if row.end == "panel" and nxt else None,
            end_derived=DerivedEnd(scale=PUSH_IN_SCALE) if row.end == "derived" else None,
            pair_difference=pair, motion=level, motion_requested=requested,
            motion_prompt=motion_prompt(panel.direction, level, ambient=ambient, push_in=row.end == "derived")
            if mode is not ShotMode.HOLD else "",
            generated_start=gen_start, generated_seconds=gen, frames=frames,
            seed=_seed(budget.base_seed, panel.novel_id, panel.chapter, panel.panel_id),
            fallback=Fallback(camera_move=camera), reasons=reasons,
        ))

    _apply_budget(shots, budget)
    _set_transitions(shots)
    return shots


def _apply_budget(shots: list[ShotSpec], budget: ShotBudget) -> None:
    """Spend the budget on the shots that most want motion; hold the rest.

    `director.score_blocks` does not fit: it needs `Span` objects and scene groups this planner does
    not have, and its tiers only score blocks over 6 s, so a short intense beat scores 0. Priority
    here: higher requested motion first, then longer generated time (more screen time repaid per
    reload), then earlier in the chapter, so the choice is deterministic.
    """
    cands = sorted(
        (s for s in shots if s.mode is not ShotMode.HOLD),
        key=lambda s: (-s.motion_requested.rank, -s.generated_seconds, s.shot_index),
    )
    clips = 0
    seconds = 0.0
    for s in cands:
        if clips >= budget.max_clips:
            code = "budget exhausted: clip count: hold"
        elif seconds + s.generated_seconds > budget.max_generated_seconds + 1e-9:
            code = "budget exhausted: generated seconds: hold"
        else:
            clips += 1
            seconds += s.generated_seconds
            continue
        s.mode = ShotMode.HOLD
        s.end_panel_id = None
        s.end_derived = None
        s.generated_start = s.generated_seconds = 0.0
        s.frames = 0
        s.motion_prompt = ""
        s.reasons.append(code)


def _set_transitions(shots: list[ShotSpec]) -> None:
    """CUT by default. DISSOLVE across a scene or cast change (video_plan rule 5: a crossfade at scene
    boundaries) unless a clip lands on the next panel, which must stay a cut or the join would show twice."""
    for s, nxt in itertools.pairwise(shots):
        if s.mode is ShotMode.INTERPOLATE and s.end_panel_id == nxt.panel_id:
            s.reasons.append("transition=cut: clip lands on next panel")
        elif s.pair_difference is PairDifference.ANY:
            s.transition_to_next = Transition.DISSOLVE
            s.reasons.append("transition=dissolve: scene or cast change")


# --------------------------------------------------------------------------- io and summary


def write_shots(version_dir: str | Path, shots: Sequence[ShotSpec]) -> Path:
    path = Path(version_dir) / SHOTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(s.model_dump_json() + "\n" for s in shots), encoding="utf-8")
    return path


def load_shots(version_dir: str | Path) -> list[ShotSpec]:
    path = Path(version_dir) / SHOTS_FILE
    if not path.exists():
        raise FileNotFoundError(f"no {SHOTS_FILE} in {version_dir}")
    out: list[ShotSpec] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if raw.get("schema_version") != SHOTS_SCHEMA_VERSION:
            raise ShotsSchemaError(
                f"{path} line {n}: shots schema_version {raw.get('schema_version')!r}, "
                f"this code reads {SHOTS_SCHEMA_VERSION}"
            )
        out.append(ShotSpec.model_validate(raw))
    return out


def summarise(shots: Sequence[ShotSpec], capability: VideoCapability | None = None) -> dict:
    """Counts per mode, generated seconds, and (given the engine) the wall-time estimate.

    The estimate pays a model reload per clip, because the 8 GB probe could not keep the model loaded.
    """
    modes = {m.value: sum(1 for s in shots if s.mode is m) for m in ShotMode}
    clips = modes["ANIMATE"] + modes["INTERPOLATE"]
    out: dict = {
        "shots": len(shots),
        "modes": modes,
        "clips": clips,
        "generated_seconds": round(sum(s.generated_seconds for s in shots), 3),
        "total_seconds": round(sum(s.duration for s in shots), 3),
    }
    if capability is not None:
        lo, hi = capability.reload_seconds
        out["estimate_wall_seconds"] = (
            math.floor(clips * (capability.seconds_per_clip + lo)),
            math.ceil(clips * (capability.seconds_per_clip + hi)),
        )
        out["estimate_measured"] = capability.measured
    return out
