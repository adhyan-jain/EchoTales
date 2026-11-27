"""Deterministic rule checks and repairs for a storyboard (no model calls).

A small local model breaks the grammar often enough that the director cannot trust a plan as written, and cannot ask
the model again for every slip on an 8 GB card. So every rule is a pure check (`audit`) plus a pure repair (`repair`),
and both are counted: the "before repair" and "after repair" violation counts in docs/results/STORYBOARD_DIRECTOR.md are
`audit` run on the model's plan and on the repaired plan. Each repair appends to a log so a reviewer can see exactly what
the validators changed and why; a repair that invents a panel marks it invented with its reason.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from echotales.pipeline.storyboard.inputs import ChapterInput
from echotales.pipeline.storyboard.schema import (
    CastMember,
    Layer,
    Letter,
    LetterKind,
    Panel,
    Purpose,
    Segment,
    Shape,
    Shot,
)

SPEECH_KINDS = {LetterKind.SPEECH, LetterKind.SHOUT, LetterKind.WHISPER, LetterKind.DREAD}
#: Letters a model may write itself. Anything else without a source line would be invented speech or narration.
INVENTED_OK = {LetterKind.SFX, LetterKind.TIME_PLACE, LetterKind.NAME_CARD}
CUT_SIGNAL_PURPOSES = {Purpose.TIME_PLACE_CARD, Purpose.TRANSITION, Purpose.ESTABLISHING}
PEAK_RELIEF = {Purpose.INSERT, Purpose.EXTREME_CLOSE, Purpose.REACTION}
_NO_HOST = {Purpose.CROWD_INDIVIDUAL, Purpose.REFERENCED_INSET, Purpose.TIME_PLACE_CARD, Purpose.TITLE_CARD, Purpose.NAME_CARD, Purpose.COLD_OPEN}
#: Panels per story block outside this band are reported, not repaired: the reference RI ch1 is ~1 panel per block, and a
#: chapter far below it is flat while far above it is a slideshow of single lines.
DENSITY_BAND = (0.45, 1.6)
MIN_SHAPES = 4
MIN_PANELS_FOR_VARIETY = 14
_STOP = {"the", "and", "of", "a", "an", "in", "on", "at", "to", "for", "later", "after", "before", "same", "time"}

#: Shape a purpose implies when the model left it `standard`: grammar rule 9, applied deterministically.
SHAPE_FOR_PURPOSE = {
    Purpose.TIME_PLACE_CARD: Shape.TEXT_ONLY,
    Purpose.TITLE_CARD: Shape.TEXT_ONLY,
    Purpose.NAME_CARD: Shape.TEXT_ONLY,
    Purpose.ESTABLISHING: Shape.WIDE,
    Purpose.TRANSITION: Shape.WIDE,
    Purpose.MONTAGE: Shape.WIDE,
    Purpose.HERO: Shape.TALL,
    Purpose.INSERT: Shape.INSET,
    Purpose.REFERENCED_INSET: Shape.INSET,
    Purpose.COLD_OPEN: Shape.BLEED,
}


@dataclass(slots=True)
class WPanel:
    """A panel plus the planning facts the contract has no field for."""

    panel: Panel
    peak: bool = False
    window: int = 0


@dataclass(slots=True)
class Report:
    before: Counter = field(default_factory=Counter)
    after: Counter = field(default_factory=Counter)
    log: list[dict] = field(default_factory=list)
    conversion: Counter = field(default_factory=Counter)  # slips fixed while turning the plan into panels (bad refs ...)
    llm_calls: int = 0
    llm_failures: int = 0
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def note(self, rule: str, action: str, detail: str = "") -> None:
        self.log.append({"rule": rule, "action": action, "detail": detail})

    def as_dict(self) -> dict:
        return {
            "before": dict(self.before),
            "after": dict(self.after),
            "conversion": dict(self.conversion),
            "repairs": dict(Counter(e["rule"] for e in self.log)),
            "llm_calls": self.llm_calls,
            "llm_failures": self.llm_failures,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "log": self.log,
        }


def _ids(members: list[CastMember]) -> set[str]:
    return {m.entity_id for m in members}


def _is_crowd(m: CastMember) -> bool:
    return m.entity_id.startswith("crowd:") or m.invented


def segment_of(segments: list[Segment], block: int) -> Segment:
    for sg in segments:
        if sg.block_from <= block <= sg.block_to:
            return sg
    return segments[0]


def _panel_segment(p: Panel, segments: list[Segment]) -> Segment:
    return next((s for s in segments if s.segment_id == p.segment_id), segments[0])


def _content_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]{3,}", text.lower()) if t not in _STOP}


# ---------------------------------------------------------------------------------------------------------------------
# audit: pure checks, one count per violation
# ---------------------------------------------------------------------------------------------------------------------


def audit(
    wps: list[WPanel],
    segments: list[Segment],
    inp: ChapterInput,
    cut_ok: set[str],
) -> Counter:
    """Count violations by rule. `cut_ok` is the set of line tags the model cut with a stated reason."""
    c: Counter = Counter()
    panels = [w.panel for w in wps]

    lettered = {lt.source_span_id for p in panels for lt in p.letters if lt.source_span_id}
    for ln in inp.lines:
        if ln.kind in ("speech", "thought") and ln.span_id not in lettered and ln.id not in cut_ok:
            c["speech_lost"] += 1

    roster_names = {r.entity_id: r.name for r in inp.roster}
    for w in wps:
        p = w.panel
        seg = _panel_segment(p, segments)
        present, refd = _ids(seg.present_cast), _ids(seg.referenced_cast)
        for m in p.cast:
            if _is_crowd(m):
                continue
            if m.entity_id in refd and m.entity_id not in present:
                if p.purpose is not Purpose.REFERENCED_INSET:
                    c["referenced_in_room"] += 1
            elif m.entity_id not in present:
                c["name_not_in_cast"] += 1
        if p.purpose is Purpose.REFERENCED_INSET and p.layer is not Layer.IMAGINED:
            c["inset_layer"] += 1
        if p.invented and not p.invented_reason:
            c["invented_no_reason"] += 1
        for lt in p.letters:
            if lt.source_span_id is None and lt.kind not in INVENTED_OK:
                c["invented_speech"] += 1
            if lt.speaker_id and lt.speaker_id in refd and lt.speaker_id not in present:
                c["speaker_not_present"] += 1
        if p.purpose is Purpose.CROWD_INDIVIDUAL and (
            any(lt.speaker_id for lt in p.letters) or any(not _is_crowd(m) for m in p.cast)
        ):
            c["crowd_named"] += 1
        # a referenced person's name in the picture text while they are not in the panel's cast
        if p.purpose is not Purpose.REFERENCED_INSET:
            for eid in refd - present:
                nm = roster_names.get(eid) or next((m.name for m in seg.referenced_cast if m.entity_id == eid), "")
                if nm and re.search(re.escape(nm), p.visual, re.I) and eid not in _ids(p.cast):
                    c["visual_names_absent"] += 1

    # scene cuts
    for si, seg in enumerate(segments):
        if si == 0:
            continue
        first = next((w.panel for w in wps if w.panel.segment_id == seg.segment_id), None)
        if first is None or first.purpose not in CUT_SIGNAL_PURPOSES:
            c["cut_unsignalled"] += 1
    if wps and wps[0].panel.purpose is not Purpose.COLD_OPEN:
        c["no_cold_open"] += 1
    for i, w in enumerate(wps):
        if w.peak or any(lt.kind is LetterKind.SHOUT for lt in w.panel.letters):
            near = [x.panel for x in wps[max(0, i - 2) : i + 3]]
            if not any(q.purpose in PEAK_RELIEF for q in near if q is not w.panel):
                c["peak_no_relief"] += 1
    if len(panels) >= MIN_PANELS_FOR_VARIETY and len({p.shape for p in panels}) < MIN_SHAPES:
        c["shape_variety"] += 1
    blocks = max(1, len(inp.blocks))
    ratio = len(panels) / blocks
    if panels and not (DENSITY_BAND[0] <= ratio <= DENSITY_BAND[1]):
        c["density_out_of_band"] += 1
    return c


# ---------------------------------------------------------------------------------------------------------------------
# repair
# ---------------------------------------------------------------------------------------------------------------------


def _new_panel(seg: Segment, purpose: Purpose, **kw) -> Panel:
    return Panel(panel_id="", segment_id=seg.segment_id, layer=kw.pop("layer", seg.layer), purpose=purpose, **kw)


def repair(
    wps: list[WPanel],
    segments: list[Segment],
    inp: ChapterInput,
    cut_ok: set[str],
    report: Report,
) -> list[WPanel]:
    """Fix what can be fixed without asking the model again. Returns the new panel list (inserts happen)."""
    roster_names = {r.entity_id: r.name for r in inp.roster}

    # --- cast: unknown names out, referenced people out of the room --------------------------------------------------
    for w in wps:
        p = w.panel
        seg = _panel_segment(p, segments)
        present, refd = _ids(seg.present_cast), _ids(seg.referenced_cast)
        keep: list[CastMember] = []
        for m in p.cast:
            if _is_crowd(m) or m.entity_id in present:
                keep.append(m)
            elif m.entity_id in refd:
                if p.purpose is Purpose.REFERENCED_INSET:
                    keep.append(m)
                else:
                    report.note("referenced_in_room", "removed from cast", f"{m.name} in {p.purpose.value} {p.source_blocks}")
                    p.visual = re.sub(re.escape(m.name), "the person being discussed", p.visual, flags=re.I)
            else:
                report.note("name_not_in_cast", "removed from cast", f"{m.name} in {p.purpose.value} {p.source_blocks}")
        removed = len(p.cast) - len(keep)
        p.cast = keep
        if removed and not keep and p.purpose in (Purpose.DIALOGUE, Purpose.BEAT, Purpose.REACTION, Purpose.HERO):
            # the panel was only ever about the absent person: show them apart rather than leave a face with no owner
            only = [m for m in seg.referenced_cast if m.name.lower() in p.visual.lower()]
            if only and not any(lt.speaker_id for lt in p.letters):
                p.purpose, p.layer, p.shape = Purpose.REFERENCED_INSET, Layer.IMAGINED, Shape.INSET
                p.cast = [only[0]]
                p.invented, p.invented_reason = True, "person only talked about, shown apart from the room"
                report.note("referenced_in_room", "converted to referenced_inset", only[0].name)
        if p.purpose is Purpose.REFERENCED_INSET and p.layer is not Layer.IMAGINED:
            report.note("inset_layer", "layer set to imagined", p.panel_id)
            p.layer = Layer.IMAGINED
        for eid in refd - present:
            nm = roster_names.get(eid) or next((m.name for m in seg.referenced_cast if m.entity_id == eid), "")
            if nm and p.purpose is not Purpose.REFERENCED_INSET and re.search(re.escape(nm), p.visual, re.I):
                p.visual = re.sub(re.escape(nm), "the person being discussed", p.visual, flags=re.I)
                report.note("visual_names_absent", "name replaced in picture text", nm)
        if p.invented and not p.invented_reason:
            p.invented_reason = "texture panel (reason not given by the model)"
            report.note("invented_no_reason", "default reason added", p.purpose.value)

    # --- crowd individuals carry only crowd lines ----------------------------------------------------------------------
    for w in wps:
        p = w.panel
        if p.purpose is Purpose.CROWD_INDIVIDUAL and (
            any(lt.speaker_id for lt in p.letters) or any(not _is_crowd(m) for m in p.cast)
        ):
            p.purpose = Purpose.DIALOGUE
            p.invented = False
            report.note("crowd_named", "purpose set to dialogue", str(p.source_blocks))

    # --- lost speech: restore beside its block ---------------------------------------------------------------------------
    lettered = {lt.source_span_id for w in wps for lt in w.panel.letters if lt.source_span_id}
    for ln in inp.lines:
        if ln.kind not in ("speech", "thought") or ln.span_id in lettered or ln.id in cut_ok:
            continue
        # beside its own block when a plain dialogue/beat panel already draws it; never on a crowd face, an inset or a
        # card (a repaired line landed on a crowd_individual panel and made it look like a named speaker)
        host = next(
            (w for w in wps if ln.block in w.panel.source_blocks and w.panel.purpose not in _NO_HOST), None
        )
        kind = LetterKind.THOUGHT if ln.kind == "thought" else LetterKind.SPEECH
        lt = Letter(kind=kind, text=ln.text, speaker_id=ln.speaker_id, source_span_id=ln.span_id)
        if host is not None:
            host.panel.letters.append(lt)
            report.note("speech_lost", "line added to the panel drawing its block", f"{ln.id} b{ln.block}")
        else:
            seg = segment_of(segments, ln.block)
            speaker = next((m for m in seg.present_cast if m.entity_id == ln.speaker_id), None)
            np_ = _new_panel(seg, Purpose.DIALOGUE, letters=[lt], source_blocks=[ln.block], cast=[speaker] if speaker else [])
            at = 0
            for i, w in enumerate(wps):
                if w.panel.source_blocks and min(w.panel.source_blocks) <= ln.block:
                    at = i + 1
            wps.insert(at, WPanel(np_))
            report.note("speech_lost", "dialogue panel created", f"{ln.id} b{ln.block}")

    # --- speakers who are not in the scene ----------------------------------------------------------------------------
    for w in wps:
        seg = _panel_segment(w.panel, segments)
        present, refd = _ids(seg.present_cast), _ids(seg.referenced_cast)
        for lt in w.panel.letters:
            if lt.speaker_id and lt.speaker_id in refd and lt.speaker_id not in present:
                report.note(
                    "speaker_not_present", "speaker cleared",
                    f"{roster_names.get(lt.speaker_id, lt.speaker_id)} is only talked about here; the reader attributed the line to them",
                )
                lt.speaker_id = None

    # --- scene cuts -----------------------------------------------------------------------------------------------------
    out: list[WPanel] = []
    seen_seg: set[str] = set()
    for w in wps:
        sid = w.panel.segment_id
        if sid not in seen_seg:
            seen_seg.add(sid)
            seg = next(s for s in segments if s.segment_id == sid)
            idx = segments.index(seg)
            if idx > 0 and w.panel.purpose not in CUT_SIGNAL_PURPOSES:
                if seg.place:
                    cp = _new_panel(
                        seg, Purpose.TIME_PLACE_CARD, shape=Shape.TEXT_ONLY, shot=Shot.WIDE,
                        letters=[Letter(kind=LetterKind.TIME_PLACE, text=seg.place.upper()[:40])],
                        source_blocks=[seg.block_from], invented=True, invented_reason="scene cut had no signal; place card added",
                    )
                else:
                    cp = _new_panel(
                        seg, Purpose.ESTABLISHING, shape=Shape.WIDE, shot=Shot.EXTREME_WIDE,
                        visual="Wide view of the new scene's setting", source_blocks=[seg.block_from],
                        invented=True, invented_reason="scene cut had no signal; establishing view added",
                    )
                out.append(WPanel(cp, window=w.window))
                seg.cut_signal = seg.cut_signal or ("card" if seg.place else "establishing")
                report.note("cut_unsignalled", "cut panel inserted", f"{seg.segment_id} at b{seg.block_from}")
        out.append(w)
    wps = out

    # --- cold open ------------------------------------------------------------------------------------------------------
    if wps and wps[0].panel.purpose is not Purpose.COLD_OPEN:
        first = wps[0].panel
        seg = _panel_segment(first, segments)
        # the hook is the chapter's first striking image: reuse the first picture the model already drew rather than
        # invent one, so the repair adds a repeat of an existing image and no new fact
        src = next((w.panel for w in wps if w.panel.visual), first)
        cp = _new_panel(
            seg, Purpose.COLD_OPEN, shape=Shape.BLEED, shot=Shot.EXTREME_WIDE,
            visual=src.visual, cast=list(src.cast), source_blocks=list(src.source_blocks[:1]),
            invented=True, invented_reason="hook before exposition: chapter opened without one",
        )
        wps.insert(0, WPanel(cp))
        report.note("no_cold_open", "cold open inserted", src.visual[:60])

    # --- peaks need relief -----------------------------------------------------------------------------------------------
    i = 0
    while i < len(wps):
        w = wps[i]
        if w.peak or any(lt.kind is LetterKind.SHOUT for lt in w.panel.letters):
            near = [x.panel for x in wps[max(0, i - 2) : i + 3]]
            if not any(q.purpose in PEAK_RELIEF for q in near if q is not w.panel):
                seg = _panel_segment(w.panel, segments)
                present = [m for m in seg.present_cast]
                speakers = {lt.speaker_id for lt in w.panel.letters if lt.speaker_id}
                other = next((m for m in present if m.entity_id not in speakers), present[0] if present else None)
                if other is not None and not w.panel.cast and not present:
                    other = None
                if other is not None:
                    rp = _new_panel(
                        seg, Purpose.REACTION, shape=Shape.INSET, shot=Shot.CLOSE, cast=[other],
                        visual=f"{other.name}'s face as the moment lands", source_blocks=list(w.panel.source_blocks[-1:]),
                        invented=True, invented_reason="reaction shot at a peak beat; no new fact",
                    )
                else:
                    rp = _new_panel(
                        seg, Purpose.EXTREME_CLOSE, shape=Shape.INSET, shot=Shot.EXTREME_CLOSE,
                        visual="Extreme close-up of eyes at the peak", source_blocks=list(w.panel.source_blocks[-1:]),
                        invented=True, invented_reason="extreme close-up at a peak beat; no new fact",
                    )
                wps.insert(i + 1, WPanel(rp, window=w.window))
                report.note("peak_no_relief", "reaction/ECU inserted", str(w.panel.source_blocks))
                i += 1
        i += 1

    # --- shapes from purpose -----------------------------------------------------------------------------------------------
    changed = 0
    for w in wps:
        p = w.panel
        target = SHAPE_FOR_PURPOSE.get(p.purpose)
        if p.shape is Shape.STANDARD:
            if target is not None:
                p.shape, changed = target, changed + 1
            elif w.peak:
                p.shape, changed = Shape.BLEED, changed + 1
    if changed:
        report.note("shape_variety", "shape set from purpose", f"{changed} panels")
    return wps
