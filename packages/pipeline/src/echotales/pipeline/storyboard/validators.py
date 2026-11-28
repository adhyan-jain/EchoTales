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
from itertools import pairwise

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
#: One panel can carry about this many source blocks before it is a text slab, not a beat: qwen3:8b put 14 blocks and 11
#: speech lines of the RI ch1 elders' corridor talk in one dialogue panel (measured).
MAX_BLOCKS_PER_PANEL = 4
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
    scenes_from_stage: bool = False  # the segment stage's cuts were used instead of the director's own scene pass

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
            "scenes_from_stage": self.scenes_from_stage,
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
        if p.purpose is Purpose.TIME_PLACE_CARD and not any(lt.kind is LetterKind.TIME_PLACE for lt in p.letters):
            c["card_empty"] += 1
        for lt in p.letters:
            if lt.source_span_id is None and lt.kind not in INVENTED_OK:
                c["invented_speech"] += 1
            if lt.speaker_id and lt.speaker_id in refd and lt.speaker_id not in present:
                c["speaker_not_present"] += 1
        if p.purpose is Purpose.CROWD_INDIVIDUAL and (
            any(lt.speaker_id for lt in p.letters) or any(not _is_crowd(m) for m in p.cast)
        ):
            c["crowd_named"] += 1
        speech_n = sum(1 for lt in p.letters if lt.source_span_id and lt.kind in SPEECH_KINDS | {LetterKind.THOUGHT})
        if len(p.source_blocks) >= MAX_BLOCKS_PER_PANEL or speech_n >= 3 or len(p.letters) >= 6:
            c["panel_overstuffed"] += 1
        if (
            p.purpose is not Purpose.CROWD_INDIVIDUAL
            and any(m.entity_id.startswith("crowd:") for m in seg.present_cast)
            and any(lt.source_span_id and lt.kind in SPEECH_KINDS and not lt.speaker_id for lt in p.letters)
        ):
            c["crowd_line_not_individualised"] += 1
        # a referenced person's name in the picture text while they are not in the panel's cast
        if p.purpose is not Purpose.REFERENCED_INSET:
            for eid in refd - present:
                nm = roster_names.get(eid) or next((m.name for m in seg.referenced_cast if m.entity_id == eid), "")
                if nm and re.search(re.escape(nm), p.visual, re.I) and eid not in _ids(p.cast):
                    c["visual_names_absent"] += 1

    # the same picture text twice in a row cannot be told apart by the image model; reported, not repairable here
    for a, b in pairwise(panels):
        if a.visual and a.visual == b.visual:
            c["visual_repeat"] += 1
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

    # --- a card with no caption is a blank panel: caption it from the scene's place, else make it an establishing view ---
    for w in wps:
        p = w.panel
        if p.purpose is Purpose.TIME_PLACE_CARD and not any(lt.kind is LetterKind.TIME_PLACE for lt in p.letters):
            seg = _panel_segment(p, segments)
            cap = " ".join(seg.place.upper().split()[:6])
            if cap:
                p.letters.append(Letter(kind=LetterKind.TIME_PLACE, text=cap))
                report.note("card_empty", "caption taken from the scene place", cap)
            else:
                p.purpose, p.shape = Purpose.ESTABLISHING, Shape.WIDE
                report.note("card_empty", "made an establishing panel", p.panel_id)

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

    # --- overstuffed panels are split by speaker turn; unattributed lines in a crowd scene get their own face ---------------
    out_split: list[WPanel] = []
    line_block = {ln.span_id: ln.block for ln in inp.lines}
    crowd_count: dict[str, int] = {}
    for w in wps:
        seg = _panel_segment(w.panel, segments)
        parts = _split_panel(w, seg, line_block, report)
        for part in parts:
            _individualise_crowd(part, seg, crowd_count, report)
        out_split.extend(parts)
    wps = out_split

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
        lead = seg.present_cast[0] if seg.present_cast and not seg.present_cast[0].entity_id.startswith("crowd:") else None
        src = next((w.panel for w in wps if w.panel.visual), first)
        where = f" in {seg.place}" if seg.place else ""
        cp = _new_panel(
            seg, Purpose.COLD_OPEN, shape=Shape.BLEED, shot=Shot.EXTREME_WIDE,
            visual=f"{lead.name}{where}, alone in a striking wide frame" if lead else src.visual,
            cast=[lead] if lead else list(src.cast), source_blocks=list(src.source_blocks[:1]),
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


_ORDINAL = ["", "another ", "a third ", "a fourth ", "a fifth ", "a sixth ", "a seventh ", "an eighth ", "a ninth ", "a tenth "]


def _singular(name: str) -> str:
    n = name.strip().lower()
    n = n[:-1] if n.endswith("s") and len(n) > 3 else n
    return n


def _split_panel(w: WPanel, seg: Segment, line_block: dict, report: Report) -> list[WPanel]:
    p = w.panel
    lets = p.letters
    speechish = SPEECH_KINDS | {LetterKind.THOUGHT}
    speech_n = sum(1 for lt in lets if lt.source_span_id and lt.kind in speechish)
    if not (len(p.source_blocks) >= MAX_BLOCKS_PER_PANEL or speech_n >= 3 or len(lets) >= 6):
        return [w]
    groups: list[list[Letter]] = []
    cur: list[Letter] = []
    narr = 0
    for lt in lets:
        if lt.kind in speechish and lt.source_span_id:
            if cur:
                groups.append(cur)
            groups.append([lt])
            cur, narr = [], 0
        elif lt.kind is LetterKind.SFX:
            (cur if cur else groups[-1] if groups else cur).append(lt)
        else:
            if narr >= 2:
                groups.append(cur)
                cur, narr = [], 0
            cur.append(lt)
            narr += 1
    if cur:
        groups.append(cur)
    if len(groups) <= 1:
        return [w]
    out: list[WPanel] = []
    for gi, g in enumerate(groups):
        blocks = sorted({line_block[lt.source_span_id] for lt in g if lt.source_span_id in line_block}) or list(p.source_blocks[:1])
        spoken = next((lt for lt in g if lt.kind in speechish and lt.source_span_id), None)
        if gi == 0:
            np_ = p.model_copy(update={"letters": g, "source_blocks": blocks})
        else:
            who = next((m for m in seg.present_cast if spoken and m.entity_id == spoken.speaker_id), None)
            np_ = Panel(
                panel_id="", segment_id=p.segment_id, layer=p.layer,
                purpose=Purpose.DIALOGUE if spoken else Purpose.BEAT, shape=Shape.STANDARD,
                shot=Shot.MEDIUM_CLOSE if spoken else p.shot, cast=[who] if who else list(p.cast),
                visual=f"{who.name} speaks" if who else p.visual, letters=g, source_blocks=blocks,
                invented=False, invented_reason="",
            )
        out.append(WPanel(np_, peak=w.peak and gi == 0, window=w.window))
    report.note("panel_overstuffed", "panel split by speaker turn", f"blocks {p.source_blocks[:3]}... into {len(out)} panels")
    return out


def _individualise_crowd(w: WPanel, seg: Segment, count: dict[str, int], report: Report) -> None:
    """An unattributed spoken line in a scene with a crowd gets one distinct invented face (grammar rule 6)."""
    p = w.panel
    crowd = next((m for m in seg.present_cast if m.entity_id.startswith("crowd:")), None)
    if crowd is None or p.purpose is Purpose.CROWD_INDIVIDUAL:
        return
    lines = [lt for lt in p.letters if lt.source_span_id and lt.kind in SPEECH_KINDS]
    if len(lines) != 1 or lines[0].speaker_id or len(p.letters) > 2:
        return
    base = _singular(crowd.name)
    k = count.get(crowd.entity_id, 0)
    count[crowd.entity_id] = k + 1
    art = "an" if base[:1] in "aeiou" else "a"
    name = f"{art} {base}" if k == 0 else f"{_ORDINAL[k]}{base}" if k < len(_ORDINAL) else f"{base} number {k + 1}"
    p.purpose, p.shape, p.shot = Purpose.CROWD_INDIVIDUAL, Shape.STANDARD, Shot.CLOSE
    p.cast = [CastMember(entity_id=f"{crowd.entity_id}-{k + 1}", name=name, invented=True)]
    p.visual = f"{name} calls out"
    p.invented, p.invented_reason = True, "one face from the crowd carrying an existing unattributed line"
    report.note("crowd_line_not_individualised", "crowd individual made", f"{name} b{p.source_blocks}")


# ---------------------------------------------------------------------------------------------------------------------
# director v2 rules (sb-5). Kept apart from `audit`/`repair` so the v1 counts in STORYBOARD_DIRECTOR.md stay comparable:
# the v2 director runs v1 first and these after, and `Report.before/after` carry both sets of counters.
# ---------------------------------------------------------------------------------------------------------------------

EVIDENCE_PREFIXES = ("text:", "dossier:", "brief:")
FORESHADOW_BEATS = {"foreshadow", "curiosity"}
#: Layers a panel may take inside a scene of another layer: a picture within the scene (a dream, a memory), never a
#: relabelling of the scene itself. v1 plans on RI ch1 drew the prior-loop cliff on `present` and the reborn timeline on
#: `past`.
SUB_LAYERS = {Layer.DREAM, Layer.MEMORY, Layer.LORE, Layer.IMAGINED}
#: A cold open that is not a hero shot: sound effects, a card on black, or a close detail (RI v1 opened on the hero).
COLD_OPEN_SHOTS = {Shot.INSERT, Shot.EXTREME_CLOSE}
BALLOON_KINDS = SPEECH_KINDS | {LetterKind.THOUGHT, LetterKind.MEMORY, LetterKind.NARRATION}
MIN_SHARED_FORESHADOW_TOKENS = 2
#: Seconds per word and floor/ceiling for a panel's hold; derived from lettering so a long exchange is not flashed past.
READ_SECONDS_PER_WORD = 0.34
HOLD_FLOOR_S = 1.6
HOLD_CEIL_S = 9.0


def panel_duration(p: Panel) -> float:
    words = sum(len(lt.text.split()) for lt in p.letters if lt.kind is not LetterKind.SFX)
    return round(min(HOLD_CEIL_S, max(HOLD_FLOOR_S, 1.0 + words * READ_SECONDS_PER_WORD)), 2)


def _cold_open_ok(p: Panel) -> bool:
    return p.purpose is Purpose.COLD_OPEN and (
        any(lt.kind is LetterKind.SFX for lt in p.letters) or p.shape is Shape.TEXT_ONLY or p.shot in COLD_OPEN_SHOTS
    )


def _person_cast(p: Panel) -> list[CastMember]:
    return [m for m in p.cast if not _is_crowd(m)]


def _later_only_tokens(brief: dict | None, chapter_text: str) -> list[set[str]]:
    """Content words of each brief setup's later sentence that the chapter never uses: a panel built from them depicts
    the later event instead of emphasising this chapter's text."""
    have = _content_tokens(chapter_text)
    out = []
    for e in (brief or {}).get("entities", []):
        for s in e.get("setups", []):
            toks = _content_tokens(s.get("later", "")) - have
            if toks:
                out.append(toks)
    return out


def audit_v2(wps: list[WPanel], segments: list[Segment], inp: ChapterInput, cards: dict[str, list], brief: dict | None) -> Counter:
    """Violations of the director v2 rules. `cards` maps segment id to its knowledge cards."""
    c: Counter = Counter()
    panels = [w.panel for w in wps]
    chapter_text = " ".join(inp.blocks.values())
    later_sets = _later_only_tokens(brief, chapter_text)
    for p in panels:
        seg = _panel_segment(p, segments)
        present = _ids(seg.present_cast)
        for m in p.cast:
            if not _is_crowd(m) and m.entity_id not in present and not (
                p.purpose is Purpose.REFERENCED_INSET and p.layer is Layer.IMAGINED
            ):
                c["cast_outside_present"] += 1
        if p.layer is not seg.layer and p.layer not in SUB_LAYERS:
            c["layer_mismatch"] += 1
        if p.withheld:
            if _person_cast(p):
                c["withheld_has_cast"] += 1
            if p.shot is not Shot.EXTREME_CLOSE:
                c["withheld_not_ecu"] += 1
        if p.invented and not p.invented_reason.lower().startswith(EVIDENCE_PREFIXES):
            c["invented_no_evidence"] += 1
        if not p.emotion:
            c["emotion_missing"] += 1
        if p.beat in FORESHADOW_BEATS:
            if not p.source_blocks:
                c["foreshadow_unanchored"] += 1
            vis = _content_tokens(p.visual)
            if any(len(vis & toks) >= MIN_SHARED_FORESHADOW_TOKENS for toks in later_sets):
                c["foreshadow_depicts_later"] += 1
        if p.purpose is Purpose.REFERENCED_INSET:
            if any(lt.kind in BALLOON_KINDS for lt in p.letters):
                c["inset_has_balloon"] += 1
            for m in p.cast:
                card = next((k for k in cards.get(seg.segment_id, []) if k.entity_id == m.entity_id), None)
                if card is not None and card.look and m.look_source != "dossier" and card.look_source == "dossier":
                    c["inset_look_not_dossier"] += 1
    for i, w in enumerate(wps):
        if w.panel.withheld and not any(
            _person_cast(x.panel) and x.panel.source_blocks and max(x.panel.source_blocks) >= max(w.panel.source_blocks or [0])
            for x in wps[i + 1 :]
        ):
            c["withheld_no_reveal"] += 1
    if panels and not _cold_open_ok(panels[0]):
        c["cold_open_hero"] += 1
    for si, seg in enumerate(segments):
        first = next((w.panel for w in wps if w.panel.segment_id == seg.segment_id), None)
        if si and seg.cut_signal == "match" and not (first and first.purpose is Purpose.TRANSITION and first.cut_signal == "match"):
            c["parallel_cut_unmatched"] += 1
        for card in cards.get(seg.segment_id, []):
            if card.status == "referenced" and card.matters_later and not any(
                p.purpose is Purpose.REFERENCED_INSET and p.segment_id == seg.segment_id and any(m.entity_id == card.entity_id for m in p.cast)
                for p in panels
            ):
                c["inset_missing"] += 1
    if any(e.get("setups") for e in (brief or {}).get("entities", []) if e.get("matters_later")) and not any(
        p.beat in FORESHADOW_BEATS for p in panels
    ):
        c["no_foreshadow"] += 1
    return c


def repair_v2(
    wps: list[WPanel], segments: list[Segment], inp: ChapterInput, cards: dict[str, list], brief: dict | None, report: Report
) -> list[WPanel]:
    """Fix what a pure rule can fix after v1's repair: layers, withheld panels, the cold open, match cuts, missing insets,
    citations. Emotion, a missing reveal and a missing foreshadow are reported only: no rule can supply them honestly."""
    chapter_text = " ".join(inp.blocks.values())
    later_sets = _later_only_tokens(brief, chapter_text)
    for w in wps:
        p = w.panel
        seg = _panel_segment(p, segments)
        if p.layer is not seg.layer and p.layer not in SUB_LAYERS:
            report.note("layer_mismatch", "panel layer set to its scene's", f"{p.layer.value}->{seg.layer.value} {p.source_blocks[:1]}")
            p.layer = seg.layer
        if p.withheld:
            if _person_cast(p):
                report.note("withheld_has_cast", "cast removed from withheld panel", ", ".join(m.name for m in p.cast))
                p.cast = [m for m in p.cast if _is_crowd(m)]
            if p.shot is not Shot.EXTREME_CLOSE:
                report.note("withheld_not_ecu", "shot set to extreme_close", p.shot.value)
                p.shot = Shot.EXTREME_CLOSE
        if p.beat in FORESHADOW_BEATS:
            vis = _content_tokens(p.visual)
            if not p.source_blocks or any(len(vis & toks) >= MIN_SHARED_FORESHADOW_TOKENS for toks in later_sets):
                report.note("foreshadow_depicts_later", "beat cleared", f"{p.visual[:50]}")
                p.beat = ""
        if p.purpose is Purpose.REFERENCED_INSET:
            for m in p.cast:
                card = next((k for k in cards.get(seg.segment_id, []) if k.entity_id == m.entity_id), None)
                if card is not None and card.look and m.look_source != "dossier" and card.look_source == "dossier":
                    m.look, m.look_source = card.look, "dossier"
                    report.note("inset_look_not_dossier", "dossier look attached", m.name)
        if p.invented and not p.invented_reason.lower().startswith(EVIDENCE_PREFIXES):
            cite = f"text:b{p.source_blocks[0] if p.source_blocks else seg.block_from}"
            report.note("invented_no_evidence", "citation added", f"{cite}: {p.invented_reason[:40]}")
            p.invented_reason = f"{cite} {p.invented_reason}".strip()

    # --- cold open: a v1 hero hook is replaced, not kept beside the new one -----------------------------------------------
    if wps and not _cold_open_ok(wps[0].panel):
        first = wps[0].panel
        seg = _panel_segment(first, segments)
        v1_hook = first.purpose is Purpose.COLD_OPEN and first.invented_reason.startswith("hook before exposition")
        if first.purpose is Purpose.COLD_OPEN and not v1_hook:
            first.shot, first.shape, first.cast = Shot.EXTREME_CLOSE, Shape.BLEED, []
            report.note("cold_open_hero", "cold open reshaped to a close detail", first.visual[:50])
        else:
            if v1_hook:
                wps.pop(0)
            cp = _new_panel(
                seg, Purpose.COLD_OPEN, shape=Shape.TEXT_ONLY, shot=Shot.INSERT, visual="black frame, held in silence",
                invented=True, invented_reason=f"text:b{seg.block_from} the chapter opens before anyone is shown",
                source_blocks=[seg.block_from], emotion="dread",
            )
            wps.insert(0, WPanel(cp))
            report.note("cold_open_hero", "black cold open inserted", f"b{seg.block_from}")

    # --- parallel cut: a simultaneous scene is entered by a graphic match -----------------------------------------------
    for si, seg in enumerate(segments):
        if not si or seg.cut_signal != "match":
            continue
        idx = next((i for i, w in enumerate(wps) if w.panel.segment_id == seg.segment_id), None)
        if idx is None:
            continue
        first = wps[idx].panel
        if first.purpose is Purpose.TRANSITION and first.cut_signal == "match":
            continue
        if first.purpose in CUT_SIGNAL_PURPOSES and first.invented:
            first.purpose, first.shape, first.cut_signal = Purpose.TRANSITION, Shape.WIDE, "match"
            report.note("parallel_cut_unmatched", "cut panel made a match transition", seg.segment_id)
        else:
            tp = _new_panel(
                seg, Purpose.TRANSITION, shape=Shape.WIDE, shot=Shot.WIDE, cut_signal="match",
                visual="the new scene framed like the last picture of the scene before, same composition",
                invented=True, invented_reason=f"text:b{seg.block_from} simultaneous scene entered by a match cut",
                source_blocks=[seg.block_from],
            )
            wps.insert(idx, WPanel(tp))
            report.note("parallel_cut_unmatched", "match transition inserted", seg.segment_id)

    # --- referenced people the novel makes matter get one silent inset ---------------------------------------------------
    for seg in segments:
        for card in cards.get(seg.segment_id, []):
            if card.status != "referenced" or not card.matters_later or not card.look:
                continue
            if any(w.panel.purpose is Purpose.REFERENCED_INSET and w.panel.segment_id == seg.segment_id
                   and any(m.entity_id == card.entity_id for m in w.panel.cast) for w in wps):
                continue
            name_toks = {t for t in re.findall(r"[a-z]{3,}", card.name.lower())}
            at = [i for i, w in enumerate(wps) if w.panel.segment_id == seg.segment_id]
            if not at:
                continue
            hit = next(
                (i for i in at if name_toks & {t for lt in wps[i].panel.letters for t in re.findall(r"[a-z]{3,}", lt.text.lower())}),
                at[-1],
            )
            blocks = wps[hit].panel.source_blocks[:1] or [seg.block_from]
            src = next((m for m in seg.referenced_cast if m.entity_id == card.entity_id), None)
            member = (src.model_copy() if src else CastMember(entity_id=card.entity_id, name=card.name))
            member.look, member.look_source = card.look, card.look_source or "bible"
            ip = _new_panel(
                seg, Purpose.REFERENCED_INSET, layer=Layer.IMAGINED, shape=Shape.INSET, shot=Shot.MEDIUM_CLOSE, cast=[member],
                visual=f"{card.name}: {card.look}", invented=True, source_blocks=blocks,
                invented_reason=f"dossier:{card.name} is only talked about here and matters later", emotion="curiosity",
            )
            wps.insert(hit + 1, WPanel(ip))
            report.note("inset_missing", "silent inset inserted", card.name)

    for w in wps:
        w.panel.duration_s = panel_duration(w.panel)
    return wps
