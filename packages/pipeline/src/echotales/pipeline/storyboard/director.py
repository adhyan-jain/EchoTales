"""The storyboard director: decides, per scene, the panel list a real manhwa adapter would draw.

Replaces "one 3:4 panel per text block" (DENSITY_BLOCKS_PER_PANEL) with the 11-rule grammar of
docs/results/MANHWA_DIRECTING_PATTERNS.md. Flow per chapter:

  load (blocks, spans, graph segments, roster, presence)
  ->  scene pass: one model call over the whole chapter marks place/time changes the graph does not (RI ch1 has two
      unmarked cuts); a window-level "new scene" flag was tried first and fired at every window start (measured: 4 false
      cuts, the real one at block 80 missed)
  ->  presence pass: one call per scene says who is in the room and who is only talked about, reading the raw text with
      no speaker labels (the reader's wrong labels on RI ch1 blocks 61/62/71 put Fang Yuan in the ritual otherwise)
  ->  one panel-plan call per window of <= 14 blocks, bisected on a bad answer
  ->  turn the plans into `Panel`s (source text copied by tag, never retyped)  ->  audit  ->  repair  ->  audit.

The model only chooses structure; every spoken line, every name and every speaker comes from the graph, so the validators
can state exactly what an invented panel may and may not carry.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.llm.base import LLMError, LLMParseError
from echotales.pipeline.llm.tasks import Task
from echotales.pipeline.paths import DATA_ROOT, storyboard_path
from echotales.pipeline.storyboard import prompts as sbp
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
from echotales.pipeline.storyboard.plan_schema import (
    LLetter,
    LPanel,
    LPresence,
    LSceneList,
    LWindow,
)
from echotales.pipeline.storyboard.prompts import PROMPT_VERSION, fewshot_digest
from echotales.pipeline.storyboard.stage_scenes import scenes_from_analysis
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
    SPEECH_KINDS,
    Report,
    WPanel,
    audit,
    repair,
)

#: A cut the model proposes inside a scene is trusted only when both halves are at least this long: one flagged block in
#: a noisy window would otherwise shred a scene into single-block "scenes", each demanding its own cut panel.
MIN_SPLIT_BLOCKS = 6
_SFX_OK = re.compile(r"^[A-Za-z!?'\- ]{1,24}$")  # qwen3 once wrote `LETTERS [{...` into an sfx slot
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
    from echotales.pipeline.llm import tasks

    tasks.TASK_PROFILES[Task.STORYBOARD] = replace(tasks.TASK_PROFILES[Task.STORYBOARD], ollama_model=model)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def cache_key(inp: ChapterInput, model: str, stage: list[Scene] | None = None) -> str:
    h = hashlib.sha1()
    for part in (
        PROMPT_VERSION, fewshot_digest(), model, str(inp.presence_contract), str(inp.look_contract),
        json.dumps(sorted(inp.blocks.items())),
        json.dumps([(ln.id, ln.speaker_id, ln.kind) for ln in inp.lines]),
        json.dumps([(s.block_from, s.block_to, s.present_ids, s.referenced_ids) for s in inp.scenes]),
        # a rerun of the segment stage moves scene cuts without touching the text, so it must miss the cache
        json.dumps([(s.block_from, s.block_to, s.layer.value, s.story_time, s.cut_signal) for s in stage or []]),
    ):
        h.update(part.encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------------------------------------------------
# model call
# ---------------------------------------------------------------------------------------------------------------------


def _fallback_plan(lines: list[Line]) -> LWindow:
    """Last resort when the model gives nothing parseable for a few blocks: every spoken line gets a dialogue panel and
    narration is carried by one caption panel per four blocks. Plain, but no spoken line is lost and the run completes."""
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
    return LWindow(panels=panels)


def _ask(client, inp: ChapterInput, prompt: str, schema, system: str, report: Report):  # type: ignore[no-untyped-def]
    res = client.complete(Task.STORYBOARD, prompt, schema, system=system, novel_id=inp.novel_id, chapter=inp.chapter)
    report.llm_calls += 1
    report.latency_ms += res.latency_ms
    report.prompt_tokens += res.prompt_tokens
    report.completion_tokens += res.completion_tokens
    return res.value


def _plan_range(
    client, inp: ChapterInput, sc: Scene, rng: tuple[int, int], carry: str, first: bool, opens_cut: bool, report: Report
) -> LWindow:
    """One window's panel plan. On an unparseable answer the window is bisected and each half re-planned: qwen3:8b on RI
    ch1 blocks 31-44 ran to its token cap inside one string twice (186 s, no plan), where a half-size window answers."""
    b0, b1 = rng
    lines = [ln for ln in inp.lines if b0 <= ln.block <= b1]
    # a reader label naming someone the scene only talks about is a reader error (RI ch1 blocks 61/62/71 label the clan
    # head's lines "Fang Yuan"); showing it makes the model cast that person in the room
    away = set(sc.referenced_ids) - set(sc.present_ids)
    lines = [replace(ln, speaker_name="") if ln.speaker_id in away else ln for ln in lines]
    text = "\n".join(ln.text for ln in lines).lower()
    in_play = [
        r for r in inp.roster
        if r.entity_id in sc.present_ids or r.entity_id in sc.referenced_ids
        or any(ln.speaker_id == r.entity_id for ln in lines) or _name_in(r.name, text)
    ]
    by_id = {r.entity_id: r for r in inp.roster}
    present_names = [by_id[i].name if i in by_id else inp.labels.get(i, i.split(":", 1)[-1]) for i in sc.present_ids]
    ref_names = [by_id[i].name if i in by_id else inp.labels.get(i, i.split(":", 1)[-1]) for i in sc.referenced_ids]
    scene_line = f"THIS SCENE: {sc.place or 'place not stated'}; {sc.story_time or 'time not stated'}; layer {sc.layer.value}."
    if opens_cut:
        scene_line += (
            " THE PASSAGE OPENS WITH A CUT into this scene: begin with a time_place_card, a transition or an establishing panel."
        )
    prompt = sbp.build_prompt(
        inp, lines, in_play, present_names, ref_names, chapter_start=first, fixed_presence=True, carry=carry, scene_line=scene_line,
    )
    try:
        plan = _ask(client, inp, prompt, LWindow, sbp.SYSTEM, report)
        if plan.panels:
            return plan
        err: Exception = LLMParseError("model returned no panels")
    except LLMParseError as exc:
        report.llm_calls += 1
        err = exc
    except LLMError as exc:  # unavailable: do not retry into a dead backend
        report.llm_failures += 1
        report.note("llm_failure", "fallback plan used", f"blocks {b0}-{b1}: {str(exc)[:120]}")
        return _fallback_plan(lines)
    story = [b for b in inp.block_ids if b0 <= b <= b1]
    if len(story) >= 6:
        mid = story[len(story) // 2]
        report.note("llm_bisect", "window re-planned in halves", f"blocks {b0}-{b1}: {str(err)[:80]}")
        left = _plan_range(client, inp, sc, (b0, story[story.index(mid) - 1]), carry, first, opens_cut, report)
        right = _plan_range(client, inp, sc, (mid, b1), _carry(left, 0), False, False, report)
        return LWindow(panels=[*left.panels, *right.panels], cut_lines=[*left.cut_lines, *right.cut_lines])
    report.llm_failures += 1
    report.note("llm_failure", "fallback plan used", f"blocks {b0}-{b1}: {str(err)[:120]}")
    return _fallback_plan(lines)


def _name_in(name: str, text_lower: str) -> bool:
    return bool(name) and name.lower() in text_lower


def _carry(lw: LWindow, n_panels: int) -> str:
    last = lw.panels[-1] if lw.panels else None
    bits = [f"{n_panels} panels so far"] if n_panels else []
    if last:
        bits.append(f"last panel: {last.purpose.value}, {last.visual[:70]}")
    return "; ".join(bits)


# ---------------------------------------------------------------------------------------------------------------------
# scene pass and presence pass
# ---------------------------------------------------------------------------------------------------------------------


def _detect_scenes(client, inp: ChapterInput, report: Report) -> list[Scene]:
    """Final scenes: the graph's and the separator splits, plus the cuts one whole-chapter model read finds."""
    base = inp.scenes
    marks = []
    try:
        marks = _ask(client, inp, sbp.build_scene_prompt(inp), LSceneList, sbp.SCENE_SYSTEM, report).scenes
    except LLMError as exc:
        report.llm_calls += 1
        report.llm_failures += 1
        report.note("llm_failure", "scene pass failed; graph scenes only", str(exc)[:120])
    story = inp.block_ids
    pos = {b: i for i, b in enumerate(story)}
    forced = {sc.block_from for sc in base}
    cand = sorted(forced | {m.from_block for m in marks if m.from_block in pos})
    keep: list[int] = []
    for b in cand:
        if not keep:
            keep.append(b)
            continue
        far_prev = pos[b] - pos[keep[-1]] >= MIN_SPLIT_BLOCKS
        far_end = len(story) - pos[b] >= MIN_SPLIT_BLOCKS
        later_forced = [f for f in forced if f > b and pos[f] - pos[b] < MIN_SPLIT_BLOCKS]
        if b in forced:
            if not far_prev and keep[-1] not in forced:
                keep.pop()
            keep.append(b)
        elif far_prev and far_end and not later_forced and _differs(marks, keep[-1], b):
            keep.append(b)
    out: list[Scene] = []
    for i, b in enumerate(keep):
        end = (story[pos[keep[i + 1]] - 1]) if i + 1 < len(keep) else story[-1]
        graph = next((sc for sc in base if sc.block_from <= b <= sc.block_to), base[0])
        mark = next((m for m in marks if m.from_block == b), None) or next(
            (m for m in sorted(marks, key=lambda m: m.from_block, reverse=True) if m.from_block <= b), None
        )
        sc = Scene(
            b, end,
            layer=graph.layer if graph.layer is not Layer.PRESENT else (mark.layer if mark else Layer.PRESENT),
            story_time=(mark.story_time if mark else "") or graph.story_time,
            place=(mark.place if mark else "") or graph.place,
            cut_signal=(next((m.cut_signal for m in marks if m.from_block == b), "")) or graph.cut_signal,
            from_graph=b in forced,
        )
        if b not in forced:
            report.note("scene_cut_found", "scene split by the director's scene pass", f"block {b}: {sc.place or '?'}")
        out.append(sc)
    return out


def _mark_at(marks, b: int):  # type: ignore[no-untyped-def]
    return next((m for m in sorted(marks, key=lambda m: m.from_block, reverse=True) if m.from_block <= b), None)


def _differs(marks, prev: int, b: int) -> bool:  # type: ignore[no-untyped-def]
    """A scene the model marked counts only if its place or story time differs from the scene before it. qwen3:8b on RI
    ch1 marked 15 starts (one per ~5 blocks) with the same place string; real cuts change where or when."""
    m, pm = _mark_at(marks, b), _mark_at(marks, prev)
    if m is None or pm is None:
        return True
    norm = lambda t: re.sub(r"\b(the|a|an)\b|[^a-z0-9 ]", "", t.lower()).split()  # noqa: E731
    return set(norm(m.place)) != set(norm(pm.place)) or set(norm(m.story_time)) != set(norm(pm.story_time)) or m.layer is not pm.layer


def _scene_presence(store: Store, client, inp: ChapterInput, sc: Scene, report: Report) -> None:
    """Who is in this scene and who is only talked about: the contract when it exists, else one model read of the raw text."""
    if inp.presence_contract:
        present, refd, _ = presence_for(store, inp.novel_id, inp.chapter, sc.block_from, sc.block_to, inp.lines, inp.roster)
        sc.present_ids = _to_ids(present, inp.roster)
        sc.referenced_ids = [i for i in _to_ids(refd, inp.roster) if i not in sc.present_ids]
        return
    text = " ".join(inp.blocks[b] for b in inp.block_ids if sc.block_from <= b <= sc.block_to).lower()
    try:
        res = _ask(client, inp, sbp.build_presence_prompt(inp, sc), LPresence, sbp.PRESENCE_SYSTEM, report)
    except LLMError as exc:
        report.llm_calls += 1
        report.llm_failures += 1
        report.note("llm_failure", "presence pass failed; fallback presence kept", f"{sc.block_from}-{sc.block_to}: {str(exc)[:100]}")
        return
    present: list[str] = []
    refd: list[str] = []
    for n in res.present:
        eid = _entity_for(n, inp.roster, text, "extra", inp.labels)
        if eid and eid not in present:
            present.append(eid)
    for n in res.referenced:
        eid = _entity_for(n, inp.roster, text, "ref", inp.labels)
        if eid and eid not in present and eid not in refd and not eid.startswith("crowd:"):
            refd.append(eid)
    sc.present_ids, sc.referenced_ids = present, refd


def _to_ids(ids: list[str], roster: list[RosterEntry]) -> list[str]:
    out = []
    for i in ids:
        hit = next((r for r in roster if r.entity_id == i), None) or match_entry(i.rsplit(":", 1)[-1], roster)
        out.append(hit.entity_id if hit else i)
    return out


def _entity_for(name: str, roster: list[RosterEntry], scene_text: str, prefix: str, label: dict[str, str]) -> str | None:
    name = name.strip()
    hit = match_entry(name, roster)
    if hit:
        return hit.entity_id
    toks = [t for t in re.findall(r"[a-z]{3,}", name.lower()) if t not in _CARD_STOP]
    # a name that appears nowhere in the scene's text is the model's invention, not a person the text mentions
    if not name or not toks or not any(t.rstrip("s") in scene_text for t in toks):
        return None
    group = name[0].islower()  # "elders", "besiegers": a crowd, never a named person
    if group:
        name = _clean_group(name)
        if not name:
            return None
    eid = f"{'crowd' if group else prefix}:{_slug(name)}"
    label[eid] = name
    return eid


_GROUP_LEAD = re.compile(r"^(the|a|an|some|many|several|over \d+|\d+)\s+|^(group|number|crowd|members?|rest) of\s+")


def _clean_group(name: str) -> str:
    """"the group of warlords" -> "warlords"; "major factions of justice" -> "major factions". The model's raw group labels
    went straight into drawn cast names on RI ch1 ("a the group of warlord"), so a group keeps only its plural head."""
    n = name.strip().lower()
    for _ in range(3):
        n = _GROUP_LEAD.sub("", n)
    n = n.split(" of ")[0].strip()
    return n if n and len(n.split()) <= 3 else ""


def _segment_for(store: Store, inp: ChapterInput, sc: Scene, seg_id: str) -> Segment:
    by_id = {r.entity_id: r for r in inp.roster}
    labels = inp.labels

    def member(eid: str) -> CastMember:
        r = by_id.get(eid)
        if r is None:
            return CastMember(
                entity_id=eid, name=labels.get(eid, eid.split(":", 1)[-1].replace("-", " ").title()),
                invented=eid.startswith("crowd:"),
            )
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


def _resolve_cast(names: list[str], seg: Segment, inp: ChapterInput, store: Store, *, crowd_ok: bool = False) -> list[CastMember]:
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
            stems = {t.rstrip("s") for t in re.findall(r"[a-z]{3,}", n.lower()) if t not in _CARD_STOP}
            grp = next(
                (m for m in seg.present_cast if m.entity_id.startswith("crowd:")
                 and stems & {t.rstrip("s") for t in re.findall(r"[a-z]{3,}", m.name.lower())}), None,
            )
            if grp is not None:
                out.append(grp)
            elif crowd_ok:
                out.append(CastMember(entity_id=f"crowd:{_slug(n)}", name=n, invented=True))
            else:
                # "a slight breeze", "tall buildings": scenery the model listed as people; flagged and removed by repair
                out.append(CastMember(entity_id=f"unknown:{_slug(n)}", name=n))
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
                    report.conversion["letter_without_ref"] += 1
            for raw in lp.sfx:
                word = raw.strip()
                if word and len(word.split()) <= 3 and _SFX_OK.match(word):
                    letters.append(Letter(kind=LetterKind.SFX, text=word.upper()))
                elif word:
                    report.conversion["sfx_malformed"] += 1
            card = lp.card.strip()
            if card:
                if len(card.split()) > 6:
                    report.conversion["card_malformed"] += 1
                elif not _grounded(card, win_text, "", ""):
                    report.conversion["card_not_grounded"] += 1
                else:
                    kind = LetterKind.TIME_PLACE if lp.purpose in (Purpose.TIME_PLACE_CARD, Purpose.TRANSITION) else LetterKind.NAME_CARD
                    letters.append(Letter(kind=kind, text=card))
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
            cast = _resolve_cast(lp.cast, seg, inp, store, crowd_ok=lp.purpose is Purpose.CROWD_INDIVIDUAL)
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


def _seg_index(segments: list[Segment], block: int) -> int:
    for i, s in enumerate(segments):
        if s.block_from <= block <= s.block_to:
            return i
    return 0


# ---------------------------------------------------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------------------------------------------------


def _stage_scenes(store: Store, inp: ChapterInput, analysis) -> list[Scene] | None:  # type: ignore[no-untyped-def]
    """Scenes from the segment stage when it has run for this chapter (an explicit analysis wins over the stored one)."""
    if analysis is None:
        try:
            from echotales.pipeline.segment.scenes import load_scene_cuts

            analysis = load_scene_cuts(store, inp.novel_id, inp.chapter)
        except Exception:  # the stage is optional; the v1 scene pass is the fallback
            analysis = None
    if analysis is None or not getattr(analysis, "cuts", None) and not getattr(analysis, "prior_loop_segments", None):
        return None
    return scenes_from_analysis(inp, analysis)


def build_storyboard(
    store: Store, client, novel_id: str, chapter: float, *, say=print, analysis=None
) -> tuple[Storyboard, Report, ChapterInput]:
    inp = load_chapter(store, novel_id, chapter)
    report = Report()
    scenes = _stage_scenes(store, inp, analysis)
    report.scenes_from_stage = scenes is not None
    if scenes is None:
        scenes = _detect_scenes(client, inp, report)
    for sc in scenes:
        _scene_presence(store, client, inp, sc, report)
    say(f"  {len(scenes)} scenes: " + ", ".join(f"b{sc.block_from}-{sc.block_to}" for sc in scenes))
    raws: list[_Raw] = []
    carry, n_panels = "", 0
    for si, sc in enumerate(scenes):
        for wi, rng in enumerate(windows(inp, sc)):
            t0 = time.perf_counter()
            plan = _plan_range(client, inp, sc, rng, carry, not raws, si > 0 and wi == 0, report)
            say(f"  window b{rng[0]}-{rng[1]}: {len(plan.panels)} panels ({time.perf_counter() - t0:.0f}s)")
            raws.append(_Raw(len(raws), rng, sc, plan, {c.ref for c in plan.cut_lines if c.reason.strip()}))
            n_panels += len(plan.panels)
            carry = _carry(plan, n_panels)

    segments = [_segment_for(store, inp, sc, f"{novel_id}:{chapter:g}:seg{i}") for i, sc in enumerate(scenes)]
    wps, cut_ok = _convert(store, inp, raws, segments, report)

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
    key = cache_key(inp, model, _stage_scenes(store, inp, None))
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
