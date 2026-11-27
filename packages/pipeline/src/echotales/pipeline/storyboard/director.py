"""The storyboard director: decides, per scene, the panel list a real manhwa adapter would draw.

Replaces "one 3:4 panel per text block" (DENSITY_BLOCKS_PER_PANEL) with the 11-rule grammar of
docs/results/MANHWA_DIRECTING_PATTERNS.md. Flow per chapter:

  load (blocks, spans, graph segments, roster, presence)  ->  one model call per window of <= 14 blocks
  ->  stitch windows into scenes (the model may find cuts the graph does not mark; RI ch1 has two unmarked)
  ->  turn the plans into `Panel`s (source text copied by tag, never retyped)  ->  audit  ->  repair  ->  audit.

The model only chooses structure; every spoken line, every name and every speaker comes from the graph, so the validators
can state exactly what an invented panel may and may not carry.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.llm.base import LLMError, LLMParseError
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.paths import DATA_ROOT, storyboard_path
from echotales.pipeline.storyboard.inputs import (
    ChapterInput,
    Line,
    RosterEntry,
    Scene,
    load_chapter,
    look_for,
    match_entry,
    presence_for,
    windows,
)
from echotales.pipeline.storyboard.plan_schema import LLetter, LPanel, LScene, LWindow
from echotales.pipeline.storyboard.prompts import (
    PROMPT_VERSION,
    SYSTEM,
    build_prompt,
    fewshot_digest,
)
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
    Storyboard,
)
from echotales.pipeline.storyboard.validators import (
    CUT_SIGNAL_PURPOSES,
    INVENTED_OK,
    SPEECH_KINDS,
    Report,
    WPanel,
    audit,
    repair,
)

#: A cut the model proposes inside a scene is trusted only when both halves are at least this long: one flagged block in
#: a noisy window would otherwise shred a scene into single-block "scenes", each demanding its own cut panel.
MIN_SPLIT_BLOCKS = 3
_CARD_STOP = {"the", "and", "later", "after", "before", "same", "time", "that", "with", "from", "this"}


@dataclass(slots=True)
class _Raw:
    idx: int
    rng: tuple[int, int]
    scene: Scene
    plan: LWindow
    cut_ok: set[str]


def set_model(model: str) -> None:
    """Point the storyboard task at another ollama model (the CLI's --model, and the model bake-off)."""
    from dataclasses import replace

    from echotales.pipeline.llm import tasks

    tasks.TASK_PROFILES[Task.STORYBOARD] = replace(tasks.TASK_PROFILES[Task.STORYBOARD], ollama_model=model)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def cache_key(inp: ChapterInput, model: str) -> str:
    h = hashlib.sha1()
    for part in (
        PROMPT_VERSION, fewshot_digest(), model, str(inp.presence_contract), str(inp.look_contract),
        json.dumps(sorted(inp.blocks.items())),
        json.dumps([(ln.id, ln.speaker_id, ln.kind) for ln in inp.lines]),
        json.dumps([(s.block_from, s.block_to, s.present_ids, s.referenced_ids) for s in inp.scenes]),
    ):
        h.update(part.encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------------------------------------------------
# model call
# ---------------------------------------------------------------------------------------------------------------------


def _fallback_plan(lines: list[Line], first: bool) -> LWindow:
    """Last resort when the model gives nothing parseable twice: every spoken line gets a dialogue panel and narration
    is carried by one caption panel per four blocks. Plain, but no spoken line is lost and the run completes."""
    panels: list[LPanel] = []
    narr: list[Line] = []

    def flush() -> None:
        if narr:
            panels.append(
                LPanel(
                    purpose=Purpose.BEAT, shape=Shape.STANDARD, shot=Shot.MEDIUM, layer=Layer.PRESENT,
                    letters=[LLetter(ref=n.id, kind=LetterKind.NARRATION) for n in narr], blocks=[n.block for n in narr],
                )
            )
            narr.clear()

    for ln in lines:
        if ln.kind == "narration":
            narr.append(ln)
            if len({n.block for n in narr}) >= 4:
                flush()
        else:
            flush()
            panels.append(
                LPanel(
                    purpose=Purpose.DIALOGUE, shape=Shape.STANDARD, shot=Shot.MEDIUM, layer=Layer.PRESENT,
                    letters=[LLetter(ref=ln.id, kind=LetterKind.THOUGHT if ln.kind == "thought" else LetterKind.SPEECH)],
                    blocks=[ln.block],
                )
            )
    flush()
    return LWindow(scenes=[LScene(from_block=lines[0].block, new_scene=False)], panels=panels)


def _call_window(client, inp: ChapterInput, scene: Scene, rng: tuple[int, int], carry: str, first: bool, report: Report) -> LWindow:
    b0, b1 = rng
    lines = [ln for ln in inp.lines if b0 <= ln.block <= b1]
    text = "\n".join(ln.text for ln in lines).lower()
    in_play = [
        r for r in inp.roster
        if r.entity_id in scene.present_ids or r.entity_id in scene.referenced_ids
        or any(ln.speaker_id == r.entity_id for ln in lines)
        or _name_in(r.name, text)
    ]
    by_id = {r.entity_id: r for r in inp.roster}
    present_names = [by_id[i].name for i in scene.present_ids if i in by_id]
    ref_names = [by_id[i].name for i in scene.referenced_ids if i in by_id]
    prompt = build_prompt(
        inp, lines, in_play, present_names, ref_names, chapter_start=first, fixed_presence=inp.presence_contract, carry=carry,
    )
    last: Exception | None = None
    for _attempt in range(2):
        try:
            res = client.complete(Task.STORYBOARD, prompt, LWindow, system=SYSTEM, novel_id=inp.novel_id, chapter=inp.chapter)
            report.llm_calls += 1
            report.latency_ms += res.latency_ms
            report.prompt_tokens += res.prompt_tokens
            report.completion_tokens += res.completion_tokens
            if res.value.panels:
                return res.value
            last = LLMParseError("model returned no panels")
        except LLMParseError as exc:
            report.llm_calls += 1
            last = exc
        except LLMError as exc:  # unavailable: do not retry into a dead backend
            last = exc
            break
    report.llm_failures += 1
    report.note("llm_failure", "fallback plan used", f"blocks {b0}-{b1}: {str(last)[:120]}")
    return _fallback_plan(lines, first)


def _name_in(name: str, text_lower: str) -> bool:
    return bool(name) and name.lower() in text_lower


def _carry(lw: LWindow, n_panels: int) -> str:
    sc = lw.scenes[-1] if lw.scenes else None
    last = lw.panels[-1] if lw.panels else None
    bits = [f"{n_panels} panels so far"]
    if sc and (sc.place or sc.story_time):
        bits.append(f"current scene: {sc.place or '?'} ({sc.story_time or 'same time'}), layer {sc.layer.value}")
    if last:
        bits.append(f"last panel: {last.purpose.value}, {last.visual[:70]}")
    return "; ".join(bits)


# ---------------------------------------------------------------------------------------------------------------------
# stitching windows into scenes
# ---------------------------------------------------------------------------------------------------------------------


def _scene_votes(raws: list[_Raw]) -> list[tuple[int, int, LScene, int]]:
    """Every LScene with the block range it covers: (from, to, lscene, window idx)."""
    out = []
    for r in raws:
        ls = sorted(r.plan.scenes, key=lambda s: s.from_block) or [LScene(from_block=r.rng[0])]
        for i, s in enumerate(ls):
            start = max(r.rng[0], s.from_block) if i else r.rng[0]
            end = (ls[i + 1].from_block - 1) if i + 1 < len(ls) else r.rng[1]
            out.append((start, max(start, min(end, r.rng[1])), s, r.idx))
    return out


def _final_scenes(inp: ChapterInput, raws: list[_Raw], report: Report) -> list[Scene]:
    votes = _scene_votes(raws)
    story = inp.block_ids
    out: list[Scene] = []
    for sc in inp.scenes:
        ids = [b for b in story if sc.block_from <= b <= sc.block_to]
        cuts: list[tuple[int, LScene]] = []
        for start, _end, ls, _w in votes:
            if ls.new_scene and start in ids and start != ids[0]:
                cuts.append((start, ls))
        cuts.sort(key=lambda c: c[0])
        accepted: list[tuple[int, LScene]] = []
        prev = ids[0]
        for b, ls in cuts:
            before = [x for x in ids if prev <= x < b]
            after = [x for x in ids if x >= b]
            if len(before) >= MIN_SPLIT_BLOCKS and len(after) >= MIN_SPLIT_BLOCKS:
                accepted.append((b, ls))
                prev = b
        bounds = [(ids[0], None), *accepted]
        for i, (b, ls) in enumerate(bounds):
            end = (bounds[i + 1][0] - 1) if i + 1 < len(bounds) else sc.block_to
            first_votes = [v for v in votes if v[0] <= b <= v[1]]
            src = ls or (first_votes[0][2] if first_votes else None)
            ns = Scene(
                b, end,
                layer=(src.layer if src else sc.layer) if sc.layer is Layer.PRESENT else sc.layer,
                story_time=(src.story_time if src else "") or sc.story_time,
                place=(src.place if src else "") or sc.place,
                cut_signal=(src.cut_signal if src else "") or sc.cut_signal,
                from_graph=sc.from_graph and i == 0,
            )
            if i > 0:
                report.note("scene_cut_found", "scene split by the director", f"block {b}: {ns.place or '?'}")
            out.append(ns)
    out.sort(key=lambda s: s.block_from)
    return out


def _presence_for_scenes(store: Store, inp: ChapterInput, scenes: list[Scene], raws: list[_Raw]) -> None:
    votes = _scene_votes(raws)
    story_text = {}
    for sc in scenes:
        story_text[id(sc)] = " ".join(inp.blocks[b] for b in inp.block_ids if sc.block_from <= b <= sc.block_to).lower()
        if inp.presence_contract:
            present, refd, _ = presence_for(store, inp.novel_id, inp.chapter, sc.block_from, sc.block_to, inp.lines, inp.roster)
            sc.present_ids = _to_ids(present, inp.roster)
            sc.referenced_ids = [i for i in _to_ids(refd, inp.roster) if i not in sc.present_ids]
            continue
        cover = [v for v in votes if v[0] <= sc.block_to and v[1] >= sc.block_from]
        pres: Counter = Counter()
        refc: Counter = Counter()
        label: dict[str, str] = {}
        for _s, _e, ls, _w in cover:
            for n in ls.present:
                eid = _entity_for(n, inp.roster, story_text[id(sc)], "extra", label)
                if eid:
                    pres[eid] += 1
            for n in ls.referenced:
                eid = _entity_for(n, inp.roster, story_text[id(sc)], "ref", label)
                if eid:
                    refc[eid] += 1
        sc.present_ids = [e for e in pres if pres[e] > refc.get(e, 0)]
        sc.referenced_ids = [e for e in set(refc) | set(pres) if e not in sc.present_ids]
        inp.labels.update(label)


def _to_ids(ids: list[str], roster: list[RosterEntry]) -> list[str]:
    out = []
    for i in ids:
        hit = next((r for r in roster if r.entity_id == i), None) or match_entry(i.rsplit(":", 1)[-1], roster)
        out.append(hit.entity_id if hit else i)
    return out


def _entity_for(name: str, roster: list[RosterEntry], scene_text: str, prefix: str, label: dict[str, str]) -> str | None:
    hit = match_entry(name, roster)
    if hit:
        return hit.entity_id
    toks = [t for t in re.findall(r"[a-z]{3,}", name.lower()) if t not in _CARD_STOP]
    # a name that appears nowhere in the scene's text is the model's invention, not a person the text mentions
    if not toks or not any(t in scene_text for t in toks):
        return None
    eid = f"{prefix}:{_slug(name)}"
    label[eid] = name
    return eid


def _segment_for(store: Store, inp: ChapterInput, sc: Scene, seg_id: str) -> Segment:
    by_id = {r.entity_id: r for r in inp.roster}
    labels = inp.labels

    def member(eid: str) -> CastMember:
        r = by_id.get(eid)
        if r is None:
            return CastMember(entity_id=eid, name=labels.get(eid, eid.split(":", 1)[-1].replace("-", " ").title()))
        _d, look_id, _ok = look_for(store, inp.novel_id, r, inp.chapter, sc.block_from)
        return CastMember(entity_id=eid, name=r.name, look_id=look_id)

    return Segment(
        segment_id=seg_id, chapter=inp.chapter, block_from=sc.block_from, block_to=sc.block_to, layer=sc.layer,
        story_time=sc.story_time, place=sc.place, cut_signal=sc.cut_signal,
        present_cast=[member(e) for e in sc.present_ids], referenced_cast=[member(e) for e in sc.referenced_ids],
    )


# ---------------------------------------------------------------------------------------------------------------------
# plans -> panels
# ---------------------------------------------------------------------------------------------------------------------

_THOUGHT_OK = {LetterKind.THOUGHT, LetterKind.MEMORY}
_NARR_OK = {LetterKind.NARRATION, LetterKind.MEMORY, LetterKind.POEM, LetterKind.THOUGHT}


def _fix_kind(ln: Line, kind: LetterKind, rep: Report) -> LetterKind:
    if ln.kind == "speech":
        ok = kind in SPEECH_KINDS or kind is LetterKind.POEM
        want = kind if ok else LetterKind.SPEECH
    elif ln.kind == "thought":
        ok = kind in _THOUGHT_OK
        want = kind if ok else LetterKind.THOUGHT
    else:
        ok = kind in _NARR_OK
        want = kind if ok else LetterKind.NARRATION
    if want is not kind:
        rep.conversion["letter_kind_fixed"] += 1
    return want


def _grounded(text: str, window_text: str, place: str, story_time: str) -> bool:
    toks = [t for t in re.findall(r"[a-z]{3,}", text.lower()) if t not in _CARD_STOP]
    if not toks:
        return False
    hay = f"{window_text} {place} {story_time}".lower()
    return any(t in hay or t.rstrip("s") in hay for t in toks)


def _resolve_cast(names: list[str], seg: Segment, inp: ChapterInput, store: Store) -> list[CastMember]:
    out: list[CastMember] = []
    pool = [*seg.present_cast, *seg.referenced_cast]
    pool_roster = [RosterEntry(m.entity_id, m.name) for m in pool]
    for n in names:
        n = n.strip()
        if not n:
            continue
        hit = match_entry(n, pool_roster)
        if hit:
            out.append(next(m for m in pool if m.entity_id == hit.entity_id))
            continue
        hit = match_entry(n, inp.roster)
        if hit:
            r = hit
            _d, look_id, _ok = look_for(store, inp.novel_id, r, inp.chapter, seg.block_from)
            out.append(CastMember(entity_id=r.entity_id, name=r.name, look_id=look_id))
            continue
        if n[0].islower() or n.lower().startswith(("a ", "an ", "the ")) or "crowd" in n.lower():
            out.append(CastMember(entity_id=f"crowd:{_slug(n)}", name=n, invented=True))
        else:
            out.append(CastMember(entity_id=f"unknown:{_slug(n)}", name=n))
    uniq: dict[str, CastMember] = {}
    for m in out:
        uniq.setdefault(m.entity_id, m)
    return list(uniq.values())


def _convert(
    store: Store, inp: ChapterInput, raws: list[_Raw], segments: list[Segment], report: Report
) -> tuple[list[WPanel], set[str]]:
    by_id = {ln.id: ln for ln in inp.lines}
    used: set[str] = set()
    cut_ok: set[str] = set()
    wps: list[WPanel] = []
    for r in raws:
        b0, b1 = r.rng
        win_text = " ".join(inp.blocks[b] for b in inp.block_ids if b0 <= b <= b1)
        for cl in r.plan.cut_lines:
            if cl.ref in by_id and cl.reason.strip():
                cut_ok.add(cl.ref)
        pending: list[tuple[LPanel, list[int], list[Letter]]] = []
        for lp in r.plan.panels:
            blocks = [b for b in lp.blocks if b0 <= b <= b1 and b in inp.blocks]
            if len(blocks) != len(lp.blocks):
                report.conversion["block_out_of_window"] += 1
            letters: list[Letter] = []
            for ll in lp.letters:
                if ll.ref:
                    ln = by_id.get(ll.ref)
                    if ln is None or not (b0 <= ln.block <= b1):
                        report.conversion["bad_line_ref"] += 1
                        continue
                    if ln.id in used:
                        report.conversion["line_used_twice"] += 1
                        continue
                    used.add(ln.id)
                    kind = _fix_kind(ln, ll.kind, report)
                    letters.append(
                        Letter(kind=kind, text=ln.text, speaker_id=ln.speaker_id if ln.kind != "narration" else None,
                               source_span_id=ln.span_id)
                    )
                    if ln.block not in blocks:
                        blocks.append(ln.block)
                else:
                    text = ll.text.strip()
                    # qwen3:8b on RI ch1 retyped the quoted lines into `text` and left `ref` empty (measured: 0 refs in a
                    # 13-block window). Retyped source text is recovered to its line, never trusted as invented speech.
                    rec = _recover_ref(text, lines_in_window(inp, b0, b1)) if ll.kind not in INVENTED_OK or len(text) > 40 else None
                    if rec is not None and rec.id not in used:
                        used.add(rec.id)
                        report.conversion["ref_recovered_from_text"] += 1
                        letters.append(
                            Letter(kind=_fix_kind(rec, ll.kind, report), text=rec.text,
                                   speaker_id=rec.speaker_id if rec.kind != "narration" else None, source_span_id=rec.span_id)
                        )
                        if rec.block not in blocks:
                            blocks.append(rec.block)
                        continue
                    if rec is not None:
                        report.conversion["line_used_twice"] += 1
                        continue
                    if ll.kind not in INVENTED_OK:
                        report.conversion["invented_speech_dropped"] += 1
                        continue
                    if not text or len(text.split()) > 6:
                        report.conversion["invented_letter_malformed"] += 1
                        continue
                    if ll.kind in (LetterKind.TIME_PLACE, LetterKind.NAME_CARD) and not _grounded(text, win_text, "", ""):
                        report.conversion["card_not_grounded"] += 1
                        continue
                    letters.append(Letter(kind=ll.kind, text=text))
            pending.append((lp, sorted(set(blocks)), letters))

        # scene for each panel: by first source block; sourceless cut panels go with the scene that follows
        scene_of: list[int | None] = []
        for _lp, blocks, _lt in pending:
            scene_of.append(_seg_index(segments, min(blocks)) if blocks else None)
        for i, si in enumerate(scene_of):
            if si is not None:
                continue
            lp = pending[i][0]
            if lp.purpose in CUT_SIGNAL_PURPOSES:
                nxt = next((scene_of[j] for j in range(i + 1, len(scene_of)) if scene_of[j] is not None), None)
                scene_of[i] = nxt if nxt is not None else (scene_of[i - 1] if i else _seg_index(segments, b0))
            else:
                scene_of[i] = scene_of[i - 1] if i and scene_of[i - 1] is not None else _seg_index(segments, b0)
        for (lp, blocks, letters), si in zip(pending, scene_of, strict=True):
            seg = segments[si if si is not None else 0]
            cast = _resolve_cast(lp.cast, seg, inp, store)
            if not cast:
                # the same model left `cast` empty while naming people in `visual`: a name in the picture text means the
                # person is in the picture
                for m in seg.present_cast:
                    if m.name and re.search(re.escape(m.name), lp.visual, re.I):
                        cast.append(m)
                if cast:
                    report.conversion["cast_from_visual"] += 1
            invented = lp.invented or (not any(lt.source_span_id for lt in letters) and not blocks)
            wps.append(
                WPanel(
                    Panel(
                        panel_id="", segment_id=seg.segment_id, layer=lp.layer, purpose=lp.purpose, shape=lp.shape,
                        shot=lp.shot, cast=cast, visual=lp.visual.strip(), letters=letters, source_blocks=blocks,
                        invented=invented, invented_reason=lp.reason.strip() if invented else "",
                    ),
                    peak=lp.peak, window=r.idx,
                )
            )
    return wps, cut_ok


def lines_in_window(inp: ChapterInput, b0: int, b1: int) -> list[Line]:
    return [ln for ln in inp.lines if b0 <= ln.block <= b1]


def _norm_text(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _recover_ref(text: str, lines: list[Line]) -> Line | None:
    """The source line a model retyped (or abbreviated), by normalised containment of its first 40 characters."""
    n = _norm_text(text)
    if len(n) < 12:
        return None
    head = n[:40]
    for ln in lines:
        ln_n = _norm_text(ln.text)
        if head in ln_n or (len(ln_n) >= 12 and ln_n[:40] in n):
            return ln
    return None


def _seg_index(segments: list[Segment], block: int) -> int:
    for i, s in enumerate(segments):
        if s.block_from <= block <= s.block_to:
            return i
    return 0


# ---------------------------------------------------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------------------------------------------------


def build_storyboard(store: Store, client, novel_id: str, chapter: float, *, say=print) -> tuple[Storyboard, Report, ChapterInput]:
    inp = load_chapter(store, novel_id, chapter)
    report = Report()
    raws: list[_Raw] = []
    carry, n_panels, first = "", 0, True
    for sc in inp.scenes:
        for rng in windows(inp, sc):
            t0 = time.perf_counter()
            plan = _call_window(client, inp, sc, rng, carry, first, report)
            say(f"  window b{rng[0]}-{rng[1]}: {len(plan.panels)} panels ({time.perf_counter() - t0:.0f}s)")
            cut_ok = {c.ref for c in plan.cut_lines if c.reason.strip()}
            raws.append(_Raw(len(raws), rng, sc, plan, cut_ok))
            n_panels += len(plan.panels)
            carry = _carry(plan, n_panels)
            first = False

    scenes = _final_scenes(inp, raws, report)
    _presence_for_scenes(store, inp, scenes, raws)
    segments = [_segment_for(store, inp, sc, f"{novel_id}:{chapter:g}:seg{i}") for i, sc in enumerate(scenes)]
    wps, cut_ok = _convert(store, inp, raws, segments, report)
    # a sub-scene's first source block may sit in a window that began earlier: sourceless cut panels already follow it

    report.before = audit(wps, segments, inp, cut_ok)
    wps = repair(wps, segments, inp, cut_ok, report)
    report.after = audit(wps, segments, inp, cut_ok)

    panels: list[Panel] = []
    for n, w in enumerate(wps):
        w.panel.panel_id = f"{novel_id}:{chapter:g}:p{n:03d}"
        panels.append(w.panel)
    model = client.model_for(Task.STORYBOARD) if hasattr(client, "model_for") else ""
    sb = Storyboard(novel_id=novel_id, chapter=chapter, model_id=model, segments=segments, panels=panels)
    return sb, report, inp


def run_chapter(
    store: Store, client, novel_id: str, chapter: float, *, force: bool = False, data_root: Path | str = DATA_ROOT, say=print
) -> tuple[Storyboard, dict, bool]:
    """Storyboard for one chapter, cached by input hash. Returns `(storyboard, meta, from_cache)`."""
    path = storyboard_path(novel_id, chapter, data_root=data_root)
    meta_path = path.with_suffix(".meta.json")
    model = client.model_for(Task.STORYBOARD) if hasattr(client, "model_for") else ""
    inp = load_chapter(store, novel_id, chapter)
    key = cache_key(inp, model)
    if not force and path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("cache_key") == key:
            return Storyboard.model_validate_json(path.read_text(encoding="utf-8")), meta, True
    sb, report, inp = build_storyboard(store, client, novel_id, chapter, say=say)
    meta = {
        "cache_key": key, "model": model, "prompt_version": PROMPT_VERSION,
        "presence_contract": inp.presence_contract, "look_contract": inp.look_contract, **report.as_dict(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sb.model_dump_json(indent=1), encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return sb, meta, False
