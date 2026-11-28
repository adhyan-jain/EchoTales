"""Art-drama bake-off (round 2: arms A, B2 = the fixed drama compiler, B2_fx, plus the round-1 B column; C and D are not rerun).

Round 1 was arms A/B/C/D over the 13 hand-built RI ch1 panels, same seeds, plus the FX layer on and off.

Run the whole thing under the GPU lock (owner rule; image models and ollama never share the 8 GB card):

    flock /tmp/echotales-gpu.lock python scripts/eval/art_drama_bakeoff.py --phase all

Arms (docs/results/ART_DRAMA.md):
  A  Z-Image Turbo, production compiler, neutral framing
  B  Z-Image Turbo, drama compiler (`render/drama.py`)
  C  NoobAI XL txt2img, tag prompt from the same Panel (comparison only; never the default, D58)
  D  arm B's picture as the init for a NoobAI img2img pass with arm C's tags, strength 0.35 / 0.45 / 0.55
`<arm>_fx` is the same picture with the drama FX layer (`pages/drama_fx.py`) on. Each model runs in its own subprocess, so Z-Image
and NoobAI are never resident together. The reference slices are copyrighted: they are read from data/scratch (gitignored) and the
sheets are written to data/scratch, so nothing here is ever committed.

Phases: prompts (CPU), zimage (A, B), noobai (C), i2i (D), fx (CPU), sheets (CPU), all."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/pipeline/tests"))
OUT = ROOT / "data/scratch/art_drama_v2"
#: Round 1 (v1 compiler) images, kept as a comparison column. The worktree has no gitignored data, so it is the v1 worktree's.
OLD = Path.home() / "Desktop/EchoTales/.claude/worktrees/art-drama/data/scratch/art_drama"
REF_DIR = ROOT / "data/scratch/reference/ri_manhua/ch01"
if not REF_DIR.exists():  # a worktree has no gitignored data; the primary checkout holds the reference slices
    REF_DIR = Path.home() / "Desktop/EchoTales/data/scratch/reference/ri_manhua/ch01"

#: One reference slice per panel, chosen by hand from the 179 slices (contact sheets viewed 2026-11-28).
REFERENCE = {
    "p01_hero": "018", "p02_accuser": "013", "p03_overhead": "033", "p04_laugh": "080", "p05_detonation": "087",
    "p06_village": "095", "p07_clanhead": "101", "p08_elders": "103", "p09_elder": "152", "p10_bainingbing": "128",
    "p11_garret": "161", "p12_eyes": "043", "p13_young": "168",
}
STRENGTHS = (0.35, 0.45, 0.55)
SIZE = (832, 1216)
ARMS = ["A", "B", "C", "D35", "D45", "D55"]
SHEET_COLS = ["ref", "A", "B_v1", "B2", "B2_fx"]  # B_v1 = round 1 drama compiler, read from OLD


def seed_of(i: int) -> int:
    return 4200 + i


def _panels():
    from _art_bakeoff_panels import bakeoff_panels

    return bakeoff_panels()


def _prompts():
    from echotales.pipeline.render.drama import compile_drama, compile_neutral, compile_noobai_tags

    rows = {}
    for bp in _panels():
        a, b = compile_neutral(bp.brief, bp.panel), compile_drama(bp.brief, bp.panel)
        pos, neg, secs = compile_noobai_tags(bp.panel, identity_tags=bp.identity_tags, scene_tags=bp.scene_tags, crowd=bp.crowd,
                                             gender_tag=bp.gender_tag)
        rows[bp.panel_id] = {
            "A": {"positive": a.positive, "sections": a.section_texts()},
            "B2": {"positive": b.positive, "sections": b.section_texts()},
            "C": {"positive": pos, "negative": neg, "sections": secs},
        }
    return rows


def phase_prompts() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _prompts()
    (OUT / "prompts.json").write_text(json.dumps(rows, indent=1))
    for pid, r in rows.items():
        print(f"== {pid}\n  A[{len(r['A']['positive'].split())}w]: {r['A']['positive'][:160]}...\n  B[{len(r['B2']['positive'].split())}w] sections="
              f"{[s[0] for s in r['B2']['sections']]}\n  C: {r['C']['positive'][:160]}...")


def _save(b64: str, path: Path) -> None:
    import base64

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(b64))


def phase_zimage() -> None:
    from echotales.pipeline.workers_contract import ImageWorkerRequest
    from echotales.pipeline.workers_zimage import LocalZImageWorker

    rows = json.loads((OUT / "prompts.json").read_text())
    w = LocalZImageWorker()
    stats = {}
    only = os.environ.get("ART_ONLY", "").split(",") if os.environ.get("ART_ONLY") else None  # re-render just these panels (and B2)
    for arm in ("B2",) if only else ("A", "B2"):
        pids = [p for p in rows if only is None or p in only]
        reqs = [ImageWorkerRequest(prompt=rows[p][arm]["positive"], width=SIZE[0], height=SIZE[1], seed=seed_of(list(rows).index(p))) for p in pids]
        t = time.time()
        n0 = len(w.stats)
        resp = w.generate_many(reqs, [rows[p][arm]["sections"] for p in pids])
        for p, r in zip(pids, resp, strict=True):
            _save(r.image_b64, OUT / arm / f"{p}.png")
        stats[arm] = {"wall_s": round(time.time() - t, 1), "per_image": w.stats[n0:]}
    w.close()
    (OUT / "stats_zimage.json").write_text(json.dumps(stats, indent=1, default=str))


def phase_noobai() -> None:
    from echotales.pipeline.workers_contract import ImageWorkerRequest
    from echotales.pipeline.workers_local import LocalNoobAIWorker

    rows = json.loads((OUT / "prompts.json").read_text())
    w = LocalNoobAIWorker()
    pids = list(rows)
    reqs = [ImageWorkerRequest(prompt=rows[p]["C"]["positive"], negative_prompt=rows[p]["C"]["negative"], width=SIZE[0], height=SIZE[1],
                               seed=seed_of(i)) for i, p in enumerate(pids)]
    t = time.time()
    resp = w.generate_many(reqs, [rows[p]["C"]["sections"] for p in pids])
    for p, r in zip(pids, resp, strict=True):
        _save(r.image_b64, OUT / "C" / f"{p}.png")
    w.close()
    (OUT / "stats_noobai.json").write_text(json.dumps({"wall_s": round(time.time() - t, 1), "per_image": w.stats}, indent=1, default=str))


def phase_i2i() -> None:
    rows = json.loads((OUT / "prompts.json").read_text())
    jobs = []
    for i, p in enumerate(rows):
        for s in STRENGTHS:
            jobs.append({"init": str(OUT / "B2" / f"{p}.png"), "out": str(OUT / f"D{int(s * 100)}" / f"{p}.png"), "prompt": rows[p]["C"]["positive"],
                         "negative": rows[p]["C"]["negative"], "strength": s, "seed": seed_of(i)})
    spec = OUT / "i2i_jobs.json"
    spec.write_text(json.dumps({"jobs": jobs, "stats": str(OUT / "stats_i2i.json")}))
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'packages/core/src'}:{ROOT / 'packages/pipeline/src'}"}
    worker = ROOT / "packages/pipeline/src/echotales/pipeline/render/_noobai_i2i_worker.py"
    t = time.time()
    subprocess.run([sys.executable, str(worker), str(spec)], check=True, env=env)
    print(f"i2i wall {time.time() - t:.0f}s")


def phase_fx() -> None:
    from echotales.pipeline.pages.drama_fx import apply_panel_fx
    from PIL import Image

    for bp in _panels():
        for arm in ("A", "B2"):
            src = OUT / arm / f"{bp.panel_id}.png"
            if src.exists():
                dst = OUT / f"{arm}_fx" / f"{bp.panel_id}.png"
                dst.parent.mkdir(parents=True, exist_ok=True)
                apply_panel_fx(Image.open(src), bp.panel, seed=7).save(dst)


def phase_sheets() -> None:
    from PIL import Image, ImageDraw, ImageFile, ImageOps

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    th = 420
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    panels = _panels()
    for bp in panels:
        tiles = []
        for col in SHEET_COLS:
            if col == "ref":
                f = REF_DIR / f"{REFERENCE[bp.panel_id]}.jpg"
                im = Image.open(f).convert("RGB") if f.exists() else Image.new("RGB", (300, th), "grey")
                label = f"ref {REFERENCE[bp.panel_id]}"
            else:
                f = (OLD / "B" if col == "B_v1" else OUT / col) / f"{bp.panel_id}.png"
                im = Image.open(f).convert("RGB") if f.exists() else Image.new("RGB", (300, th), (40, 40, 40))
                label = col
            im = ImageOps.contain(im, (int(th * 0.8), th))
            tiles.append((label, im))
        sheet_w = sum(t[1].width for t in tiles) + 6 * len(tiles)
        sheet = Image.new("RGB", (sheet_w, th + 44), "white")
        d = ImageDraw.Draw(sheet)
        d.text((4, 2), f"{bp.panel_id}  {bp.panel.purpose.value}/{bp.panel.shot.value}/{bp.panel.layer.value}  {bp.note}", fill="black")
        x = 0
        for label, im in tiles:
            sheet.paste(im, (x, 40))
            d.text((x + 4, 24), label, fill="red")
            x += im.width + 6
        sheet.save(OUT / "sheets" / f"{bp.panel_id}.png")
    print("sheets in", OUT / "sheets")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=["prompts", "zimage", "noobai", "i2i", "fx", "sheets", "all"])
    a = ap.parse_args()
    if a.phase == "all":
        for ph in ("prompts", "zimage", "fx", "sheets"):  # v2 is Z-Image only: C is comparison-only and D is dropped
            subprocess.run([sys.executable, __file__, "--phase", ph], check=True)  # one process per model: nothing shares the card
        return 0
    {"prompts": phase_prompts, "zimage": phase_zimage, "noobai": phase_noobai, "i2i": phase_i2i, "fx": phase_fx, "sheets": phase_sheets}[a.phase]()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages/core/src"))
    sys.path.insert(0, str(ROOT / "packages/pipeline/src"))
    raise SystemExit(main())
