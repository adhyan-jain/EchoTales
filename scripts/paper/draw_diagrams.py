"""Draw report Figures 1-7 (the system diagrams) as SVG.

`docs/paper/FIGURES.md` listed these as HAND-DRAWN, and they were never drawn.
Every label that states a fact is read from the code or a result file at run
time -- gate names from `resolve/score.py::PREFILTER_GATES`, provenance tiers
from `eval/gold.py`, gold checks from `eval/validate_gold.py`, body intervals
from the canonical database, and counts from `data/eval/*.json` -- so a figure
cannot drift from what it depicts. Anything designed but not demonstrated on
real data is drawn dashed and says so.

Figures 5 and 6 show the observer-conditioned state path into rendering, which
the patent packet covers; they are written to the gitignored private folder,
not to docs/paper/figures/.

Usage:
    python3 scripts/paper/draw_diagrams.py [--db data/db/reverend-insanity.db]
        [--out docs/paper/figures] [--private-out docs/private/paper/figures]
"""

from __future__ import annotations

import argparse
import inspect
import json
import sqlite3
from html import escape
from pathlib import Path

INK = "#1f2933"
MUTED = "#6b7280"
LINE = "#9ca3af"
ACCENT = "#1d4ed8"
FILL = "#f3f4f6"
REAL = "#ecfdf5"
DESIGNED = "#fff7ed"
FONT = 'font-family="Helvetica, Arial, sans-serif"'


# ---- primitives --------------------------------------------------------------


def text(x: float, y: float, s: str, *, size: int = 11, anchor: str = "start",
         fill: str = INK, weight: str = "normal") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" text-anchor="{anchor}" '
            f'fill="{fill}" font-weight="{weight}">{escape(s)}</text>')


def box(x: float, y: float, w: float, h: float, title: str, lines: list[str] | tuple[str, ...] = (),
        *, fill: str = FILL, dashed: bool = False, stroke: str = LINE) -> str:
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}"{dash}/>',
           text(x + w / 2, y + 18, title, size=12, anchor="middle", weight="bold")]
    for i, line in enumerate(lines):
        out.append(text(x + w / 2, y + 36 + i * 14, line, size=10, anchor="middle", fill=MUTED))
    return "\n".join(out)


def arrow(x1: float, y1: float, x2: float, y2: float, label: str = "", *, dashed: bool = False,
          color: str = INK) -> str:
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.4" '
           f'marker-end="url(#arrow)"{dash}/>']
    if label:
        out.append(text((x1 + x2) / 2 + 4, (y1 + y2) / 2 - 5, label, size=9, fill=MUTED))
    return "\n".join(out)


def svg(width: int, height: int, title: str, caption: str, body: list[str]) -> str:
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        text(20, 28, title, size=15, weight="bold"),
        *body,
        text(20, height - 14, caption, size=10, fill=MUTED),
        "</svg>", "",
    ])


def legend(x: float, y: float) -> str:
    return "\n".join([
        f'<rect x="{x}" y="{y}" width="14" height="10" fill="{REAL}" stroke="{LINE}"/>',
        text(x + 20, y + 9, "demonstrated on real data", size=9, fill=MUTED),
        f'<rect x="{x + 170}" y="{y}" width="14" height="10" fill="{DESIGNED}" stroke="{LINE}" stroke-dasharray="4,3"/>',
        text(x + 190, y + 9, "designed / unit tests only", size=9, fill=MUTED),
    ])


# ---- facts, read not typed ---------------------------------------------------


def _gate_verdicts() -> tuple[list[str], list[str]]:
    """Which gates BLOCK and which FORCE_LINK, read from `prefilter`'s source."""
    from echotales.pipeline.resolve.score import PREFILTER_GATES, prefilter

    src = inspect.getsource(prefilter)
    block, force = [], []
    for gate in PREFILTER_GATES:
        after = src.split(f'"{gate}" not in disabled_prefilters', 1)[1]
        verdict = after.split("PrefilterVerdict.", 1)[1]
        (block if verdict.startswith("BLOCK") else force).append(gate)
    return block, force


def facts(db: Path) -> dict:
    from echotales.pipeline.eval import validate_gold
    from echotales.pipeline.eval.gold import Provenance, ReviewDepth

    block, force = _gate_verdicts()
    checks = [n.lstrip("_").replace("_", " ") for n, fn in inspect.getmembers(validate_gold, inspect.isfunction)
              if n.startswith("_") and fn.__module__ == validate_gold.__name__
              and list(inspect.signature(fn).parameters)[:1] == ["gold"]]

    ablation = json.loads(Path("data/eval/ablation/reverend-insanity.json").read_text())
    full = next(r for r in ablation["rows"] if r["condition"] == "full")
    obs = json.loads(Path("data/eval/observer_ablation.json").read_text())["total"]
    a7 = json.loads(Path("data/eval/a7_cache_ablation.json").read_text())["events"]
    controlled = ("E1_cast_appearance", "E1b_cast_attire")

    def stale(cond: str) -> int:
        return sum(a7[e]["frozen_prompt"]["conditions"][cond]["incorrect_reuse"] for e in controlled)

    bodies: list[tuple[str, float, float]] = []
    if db.is_file():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = con.execute("SELECT id FROM self_entity WHERE canonical_label='Fang Yuan' LIMIT 1").fetchone()
        if row:
            bodies = [(p.rsplit(":", 1)[-1], lo, hi) for p, lo, hi in con.execute(
                "SELECT persona_id, story_from_lb, story_to_ub FROM self_persona_binding "
                "WHERE self_id=? ORDER BY story_from_lb", (row[0],))]
    return {
        "block": block, "force": force, "checks": checks,
        "provenance": [p.value for p in Provenance], "depth": [d.value for d in ReviewDepth],
        "full": full, "threshold": ablation["link_threshold"],
        "leaks": {k: obs[k]["leak"] for k in ("FULL", "A1", "A2")}, "queries": obs["queries"],
        "stale_with": stale("A"), "stale_without": stale("B"), "bodies": bodies,
    }


# ---- figures -----------------------------------------------------------------


def fig1_architecture(f: dict) -> str:
    b = [legend(20, 44)]
    y, w, h, gap = 80, 150, 78, 28
    stages = [("Ingest", ["EPUB -> chapters,", "blocks"]),
              ("Spans", ["dialogue / narration /", "thought / system"]),
              ("Mentions", ["gazetteer + chapter NER,", "typed aliases"]),
              ("Resolve", ["incremental evidence,", "hard pre-filter gates"]),
              ("Personas", ["bodies, appearance,", "canon"])]
    for i, (t, ls) in enumerate(stages):
        x = 20 + i * (w + gap)
        b.append(box(x, y, w, h, t, ls, fill=REAL))
        if i:
            b.append(arrow(x - gap, y + h / 2, x, y + h / 2))
    gy, gw = 210, 5 * w + 4 * gap
    b.append(box(20, gy, gw, 70, "Narrative graph (SQLite)",
                 ["Self / Persona / aliases / attributes / relations / observations,",
                  "each fact with a story-time interval, a knowledge position and an observer"],
                 fill="#eff6ff", stroke=ACCENT))
    for i in range(5):
        x = 20 + i * (w + gap) + w / 2
        b.append(arrow(x, y + h, x, gy))
    oy = 330
    b.append(box(20, oy, 250, 64, "Panels -> chapter video", ["render plan per beat, image engine,", "composited 1080x1920"], fill=REAL))
    b.append(box(300, oy, 250, 64, "Audio", ["voice casting per character,", "TTS per line"], fill=REAL))
    b.append(box(580, oy, 250, 64, "Review desk (webview)", ["corrections logged, then", "applied to the graph"], fill=REAL))
    b.append(arrow(145, gy + 70, 145, oy, "state at the panel's position"))
    b.append(arrow(425, gy + 70, 425, oy, "cast + speakers"))
    b.append(arrow(705, oy, 705, gy + 70, "apply"))
    return svg(910, 440, "Figure 1. EchoTales architecture",
               "Stages run volume-first; every stage writes to the graph, and both output modalities read from it.", b)


def fig2_axes(_f: dict) -> str:
    b = [legend(20, 44)]
    ox, oy = 90, 330
    b.append(arrow(ox, oy, 700, oy))
    b.append(text(706, oy + 4, "story position (chapter + offset)", size=11))
    b.append(arrow(ox, oy, ox, 90))
    b.append(text(ox - 6, 82, "knowledge position (when a fact is learned)", size=11))
    b.append(arrow(ox, oy, ox + 170, oy - 150))
    b.append(text(ox + 176, oy - 154, "observer (READER, SYSTEM, or a character)", size=11))
    b.append(f'<rect x="{ox + 260}" y="{oy - 60}" width="240" height="14" fill="{REAL}" stroke="{ACCENT}"/>')
    b.append(text(ox + 380, oy - 66, "a fact holds over an interval of story time", size=10, anchor="middle", fill=MUTED))
    b.append(f'<circle cx="{ox + 300}" cy="{oy - 200}" r="5" fill="{ACCENT}"/>')
    b.append(text(ox + 310, oy - 196, "and is known to an observer from a knowledge position on", size=10, fill=MUTED))
    b.append(f'<rect x="{ox + 420}" y="{oy - 120}" width="220" height="30" rx="4" fill="{DESIGNED}" '
             f'stroke="{LINE}" stroke-dasharray="5,4"/>')
    b.append(text(ox + 530, oy - 101, "non-main timelines (dream, flashback)", size=10, anchor="middle", fill=MUTED))
    return svg(960, 400, "Figure 2. Three-axis temporal model",
               "Chapter order is not time: a fact carries a story interval, a knowledge position and an observer. "
               "No fact is yet written off the main timeline.", b)


def fig3_self_persona(f: dict) -> str:
    b = [legend(20, 44)]
    x0, x1, y, last = 150, 760, 90, 199.0

    def sx(ch: float) -> float:
        return x0 + (min(ch, last) - 1) / (last - 1) * (x1 - x0)

    b.append(text(20, y + 14, "Self: Fang Yuan", size=12, weight="bold"))
    b.append(f'<rect x="{x0}" y="{y}" width="{x1 - x0}" height="20" fill="#eff6ff" stroke="{ACCENT}"/>')
    b.append(text((x0 + x1) / 2, y + 14, "one continuous consciousness, chapters 1-199", size=10, anchor="middle", fill=MUTED))
    for i, (name, lo, hi) in enumerate(f["bodies"]):
        yy = y + 40 + i * 30
        left, right = sx(lo), max(sx(hi), sx(lo) + 14)  # a sub-chapter interval still needs a visible width
        b.append(text(20, yy + 13, f"Persona: {name}", size=11))
        b.append(f'<rect x="{left:.1f}" y="{yy}" width="{right - left:.1f}" height="18" fill="{REAL}" stroke="{LINE}"/>')
        end = "end of volume" if hi == float("inf") or hi >= last else f"ch {hi:.2f}"
        label = f"ch {lo:.2f} -> {end}"
        b.append(text(right + 6 if right < x1 - 100 else left + 6, yy + 13, label, size=10,
                      fill=MUTED if right < x1 - 100 else INK))
    ay = y + 40 + max(len(f["bodies"]), 1) * 30 + 10
    b.append(f'<line x1="{x0}" y1="{ay}" x2="{x1}" y2="{ay}" stroke="{LINE}"/>')
    for ch in (1, 50, 100, 150, 199):
        b.append(text(sx(ch), ay + 14, f"ch {ch}", size=9, anchor="middle", fill=MUTED))
    b.append(f'<rect x="{x0}" y="{ay + 36}" width="320" height="30" rx="4" fill="{DESIGNED}" stroke="{LINE}" stroke-dasharray="5,4"/>')
    b.append(text(x0 + 160, ay + 55, "concurrent bodies (disguise, clone, possession)", size=10, anchor="middle", fill=MUTED))
    return svg(900, ay + 110, "Figure 3. Self / Persona binding (from the canonical database)",
               "Sequential reincarnation is the only case in the corpus; concurrent bindings are in the model and unit tests only.", b)


def fig4_resolution(f: dict) -> str:
    full = f["full"]
    gate_lines = ["BLOCK:", *f["block"], "FORCE_LINK:", *f["force"]]
    gate_h = 34 + 14 * len(gate_lines)
    b = [box(20, 70, 150, 64, "New mention", ["typed alias (name,", "title, deictic, ...)"], fill=REAL),
         box(200, 70, 150, 64, "Candidates", ["retrieval over the", "entities seen so far"], fill=REAL),
         box(380, 60, 230, gate_h, "Hard pre-filter gates", gate_lines, fill=REAL),
         box(650, 70, 180, 64, "Scorer (optional)", [f"threshold {f['threshold']:.2f}",
                                                    f"{full['links_above_threshold']} links above it"],
             fill=DESIGNED, dashed=True),
         box(650, 190, 180, 64, "Decision", ["LINK / NEW / DEFER", "precision over recall"], fill=REAL),
         arrow(170, 102, 200, 102), arrow(350, 102, 380, 102), arrow(610, 102, 650, 102, "SCORE"),
         arrow(610, 170, 650, 215, "BLOCK / FORCE"), arrow(740, 134, 740, 190)]
    gz = 60 + gate_h + 30
    b.append(box(200, gz, 410, 50, "Gazetteer", ["every confirmed alias becomes an exact match for later chapters"], fill=REAL))
    b.append(arrow(650, 245, 610, gz + 20, "confirmed"))
    b.append(arrow(275, gz, 275, 134, "compounding", color=ACCENT))
    b.append(text(20, gz + 90, f"Canonical run, {full['pairs']:,} cached candidate pairs: {full['force_links']:,} force-links, "
                               f"{full['blocks']:,} blocks, {full['scored']:,} reach the scorer, "
                               f"{full['links_above_threshold']} linked by it.", size=10, fill=MUTED))
    return svg(860, gz + 130, "Figure 4. Incremental entity resolution",
               "Deterministic gates carry every link in the canonical run; the learned scorer is optional (dashed).", b)


def fig5_state_of(f: dict) -> str:
    b = [box(20, 70, 190, 70, "state_of(target,", ["story position, observer,", "knowledge position)"], fill="#eff6ff", stroke=ACCENT)]
    steps = [("Timeline filter", ["drop voided timelines"]),
             ("Observer filter", ["observed by this observer?"]),
             ("Knowledge filter", ["learned by the", "knowledge position?"]),
             ("Story-time filter", ["interval contains", "the position?"])]
    for i, (t, ls) in enumerate(steps):
        x = 240 + i * 160
        b.append(box(x, 70, 145, 70, t, ls, fill=REAL))
        b.append(arrow(210 if i == 0 else x - 15, 105, x, 105))
    b.append(box(560, 180, 240, 60, "Result", ["aliases, attributes, relations,", "bound persona(s), certainty, read set"], fill=REAL))
    b.append(arrow(800, 140, 700, 180))
    lk = f["leaks"]
    b.append(text(20, 290, f"Observer ablation on the canonical run ({f['queries']} observer queries over the recorded reveals):",
                  size=11, weight="bold"))
    b.append(text(20, 310, f"full: {lk['FULL']} leaks   |   observer collapsed to READER (A1): {lk['A1']}   |   "
                           f"knowledge time removed (A2): {lk['A2']}", size=11))
    b.append(text(20, 328, "'Leak' is defined against the system's own observation records (docs/results/ABLATIONS.md).",
                  size=10, fill=MUTED))
    return svg(900, 370, "Figure 5. state_of() query flow", "Each filter is a condition on one axis of Figure 2.", b)


def fig6_render_plan(f: dict) -> str:
    b = [legend(20, 44),
         box(20, 80, 200, 70, "Beat", ["present cast, fractional", "in-chapter position"], fill=REAL),
         box(250, 80, 220, 70, "Compiled generation state", ["state_of per cast member,", "drawn persona + appearance"],
             fill="#eff6ff", stroke=ACCENT),
         box(500, 60, 180, 50, "Panel prompt", ["persona + appearance"], fill=REAL),
         box(500, 130, 180, 50, "Render plan", ["state digest = hash(state)"], fill=REAL),
         box(710, 95, 150, 60, "Cache key", ["digest + prompt +", "engine settings"], fill=REAL),
         arrow(220, 115, 250, 115), arrow(470, 105, 500, 85), arrow(470, 125, 500, 155),
         arrow(680, 155, 710, 135), arrow(680, 85, 710, 115),
         box(250, 220, 220, 60, "Audio casting", ["whole-volume traits per character;", "reads no position or observer"],
             fill=DESIGNED, dashed=True)]
    b.append(text(20, 320, f"A7, prompt held fixed while appearance and attire change: {f['stale_with']} stale reuses "
                           f"with the digest, {f['stale_without']} without it.", size=11))
    b.append(text(20, 338, "The audio path has no state-dependent input, so it does not consume the compiled state.",
                  size=10, fill=MUTED))
    return svg(890, 380, "Figure 6. Graph state to render plan and cache key",
               "The prompt and the cache key are derived from one compiled state, so they cannot disagree.", b)


def fig7_evaluation(f: dict) -> str:
    checks = f["checks"]
    ch = 34 + 14 * len(checks)
    b = [box(20, 70, 200, 90, "Reference sets", ["provenance: " + " / ".join(f["provenance"]),
                                                "review depth:", " / ".join(f["depth"])], fill=REAL),
         box(250, 60, 220, ch, "Validation before scoring", checks, fill=REAL),
         box(500, 70, 170, 70, "Scoring", ["B3, MUC, CEAF-e,", "recall@K, ablations"], fill=REAL),
         box(700, 70, 170, 70, "Result file", ["data/eval/*.json: commit,", "database, gold, seed"], fill=REAL),
         arrow(220, 115, 250, 115), arrow(470, 105, 500, 105), arrow(670, 105, 700, 105)]
    b.append(text(20, 60 + ch + 36, "Every number is scored against an LLM-drafted SILVER set (provenance 'model'); "
                                   "no record is human gold and no agreement figure exists.", size=11))
    return svg(900, 60 + ch + 80, "Figure 7. Evaluation pipeline and provenance tiers",
               "A figure cites the result file it came from; a model-drafted record can never be reported as gold.", b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/db/reverend-insanity.db")
    ap.add_argument("--out", default="docs/paper/figures")
    ap.add_argument("--private-out", default="docs/private/paper/figures")
    args = ap.parse_args()
    f = facts(Path(args.db))
    public = {"fig01_architecture.svg": fig1_architecture, "fig02_temporal_axes.svg": fig2_axes,
              "fig03_self_persona.svg": fig3_self_persona, "fig04_resolution.svg": fig4_resolution,
              "fig07_evaluation.svg": fig7_evaluation}
    private = {"fig05_state_of.svg": fig5_state_of, "fig06_render_plan.svg": fig6_render_plan}
    for out, figs in ((Path(args.out), public), (Path(args.private_out), private)):
        out.mkdir(parents=True, exist_ok=True)
        for name, fn in figs.items():
            (out / name).write_text(fn(f))
            print(out / name)


if __name__ == "__main__":
    main()
