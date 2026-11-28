"""Art bake-off v3: B2 (Z-Image drama) against C2 NoobAI, C2 Illustrious and B2 + a NoobAI img2img style pass (arm D), each also
with a character LoRA once one exists, on the same 13 panels with the same seeds (4200 + panel index), 832x1216.

Owner decision 2026-11-28: every local method may be used to get a real manhwa or anime look; the art model is chosen only by
side-by-side quality against the real manhwa. This script runs the arms and builds the sheets; it does not judge them.

Arms (docs/results/ART_V3.md):
  B2             Z-Image Turbo, drama compiler (`render/drama.py`)
  C2_noobai      NoobAI-XL 1.1 txt2img, tags from `render/drama_tags.py::compile_c2`
  C2_illustrious Illustrious-XL v0.1 txt2img, same tags, masterpiece-family quality words
  D              arm B2's picture as the init of a NoobAI img2img pass with the C2 tags (strength `--strength`, default 0.45)
  <arm>_lora     C2_noobai / C2_illustrious / D with a character LoRA (`--lora fang_yuan=<safetensors>`), only the panels whose
                 cast has a LoRA; the trigger word leads the identity tags. B2 has no LoRA arm: the LoRA is SDXL-only.

Every model runs in its own subprocess under `flock /tmp/echotales-gpu.lock`; nothing here loads a model in this process. Images go to
`data/scratch/art_v3/<arm>/<panel_id>.png` (gitignored; the reference slices are copyrighted), with `prompts.json`, `stats_<arm>.json`
and `sheets/`.

    python scripts/eval/art_bakeoff_v3.py --phase prompts
    python scripts/eval/art_bakeoff_v3.py --phase run --arms B2,C2_noobai,C2_illustrious,D
    python scripts/eval/art_bakeoff_v3.py --phase sheets
    python scripts/eval/art_bakeoff_v3.py --phase all --stub          # no GPU: solid-colour stand-ins, to check the plumbing"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import zlib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "packages/pipeline/src"), str(ROOT / "packages/pipeline/tests"),
                str(ROOT / "scripts/art")]
LOCK = "/tmp/echotales-gpu.lock"
SIZE = (832, 1216)
WORKER = ROOT / "packages/pipeline/src/echotales/pipeline/render/_sdxl_art_worker.py"
CHECKPOINT = {"noobai": "Laxhar/noobai-XL-1.1", "illustrious": "OnomaAIResearch/Illustrious-xl-early-release-v0"}
#: arm -> (engine, checkpoint key). Order is the run order: Z-Image first, because arm D needs its pictures.
ARMS: dict[str, tuple[str, str]] = {
    "B2": ("zimage", ""), "C2_noobai": ("sdxl", "noobai"), "C2_illustrious": ("sdxl", "illustrious"), "D": ("sdxl_i2i", "noobai"),
}
SHEET_COLS = ["ref", "B2", "C2_noobai", "C2_illustrious", "D"]
REF_DIR = ROOT / "data/scratch/reference/ri_manhua/ch01"
if not REF_DIR.exists():  # a worktree has no gitignored data; the primary checkout holds the reference slices
    REF_DIR = Path.home() / "Desktop/EchoTales/data/scratch/reference/ri_manhua/ch01"
REFERENCE = {
    "p01_hero": "018", "p02_accuser": "013", "p03_overhead": "033", "p04_laugh": "080", "p05_detonation": "087",
    "p06_village": "095", "p07_clanhead": "101", "p08_elders": "103", "p09_elder": "152", "p10_bainingbing": "128",
    "p11_garret": "161", "p12_eyes": "043", "p13_young": "168",
}
Runner = Callable[[str, Path], None]


def seed_of(i: int) -> int:
    return 4200 + i


def panels():
    from _art_bakeoff_panels import bakeoff_panels

    return bakeoff_panels()


def parse_loras(items: list[str]) -> dict[str, dict]:
    """`--lora fang_yuan=/path/pytorch_lora_weights.safetensors[:0.8]` -> {character name: {path, scale, trigger}}."""
    from build_lora_set import CHARACTERS

    out = {}
    for it in items:
        key, _, rest = it.partition("=")
        path, _, scale = rest.partition(":")
        if key not in CHARACTERS or not path:
            raise SystemExit(f"--lora expects <{'|'.join(CHARACTERS)}>=<path>[:scale], got {it!r}")
        c = CHARACTERS[key]
        out[c["name"]] = {"path": path, "scale": float(scale or 0.8), "trigger": c["trigger"]}
    return out


def lora_for(bp, loras: dict[str, dict]) -> dict | None:
    """The first cast member of the panel that has a LoRA (match on the cast name, first or full name)."""
    for m in bp.panel.cast:
        for name, spec in loras.items():
            if m.name == name or m.name == name.split()[0] or name.startswith(m.name + " "):
                return spec
    return None


def compile_all(loras: dict[str, dict] | None = None) -> dict[str, dict]:
    """Every panel's prompts for every arm. Pure CPU."""
    from echotales.pipeline.render.drama import compile_drama
    from echotales.pipeline.render.drama_tags import compile_c2

    rows: dict[str, dict] = {}
    for bp in panels():
        row = {"B2": {"positive": (b := compile_drama(bp.brief, bp.panel)).positive, "sections": b.section_texts()}}
        lo = lora_for(bp, loras or {})
        for ck in ("noobai", "illustrious"):
            for suffix, trig in (("", ""), ("_lora", lo["trigger"] if lo else None)):
                if trig is None:
                    continue
                t = compile_c2(bp.panel, bp.brief, checkpoint=ck, trigger=trig)
                row[f"C2_{ck}{suffix}"] = {"positive": t.positive, "negative": t.negative, "sections": t.sections}
        row["D"] = row["C2_noobai"]
        if lo:
            row["D_lora"] = row["C2_noobai_lora"]
        rows[bp.panel_id] = row
    return rows


def plan_arm(arm: str, rows: dict[str, dict], out: Path, loras: dict[str, dict] | None = None, *, strength: float = 0.45,
             control: dict | None = None) -> list[dict]:
    """The job list for one arm (`<arm>` or `<arm>_lora`). A `_lora` arm only has the panels whose cast has a LoRA."""
    lora_arm = arm.endswith("_lora")
    engine = ARMS[arm[:-5] if lora_arm else arm][0]
    bps = {bp.panel_id: bp for bp in panels()}
    jobs = []
    for i, pid in enumerate(rows):
        lo = lora_for(bps[pid], loras or {}) if lora_arm else None
        if lora_arm and (lo is None or engine == "zimage"):
            continue
        r = rows[pid][arm]
        job = {"panel_id": pid, "out": str(out / arm / f"{pid}.png"), "prompt": r["positive"], "seed": seed_of(i), "width": SIZE[0], "height": SIZE[1]}
        if engine != "zimage":
            job["negative"] = r["negative"]
        if engine == "sdxl_i2i":
            job.update(init=str(out / "B2" / f"{pid}.png"), strength=strength)
        if lo:
            job["lora"] = {"path": lo["path"], "scale": lo["scale"]}
        if control and engine != "zimage":
            job["control"] = control
        jobs.append(job)
    return jobs


def gpu_runner(engine: str, spec: Path) -> None:
    """One model, one subprocess, under the GPU lock (owner rule: ollama and image models never share the 8 GB card)."""
    py = sys.executable
    cmd = [py, str(WORKER), str(spec)] if engine != "zimage" else [py, __file__, "--internal-zimage", str(spec)]
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'packages/core/src'}:{ROOT / 'packages/pipeline/src'}"}
    subprocess.run(["flock", LOCK, *cmd], check=True, env=env)


def stub_runner(engine: str, spec: Path) -> None:
    """No GPU: a solid PNG per job, colour from the prompt hash. Used by `--stub` and the unit tests."""
    from PIL import Image

    s = json.loads(spec.read_text())
    for j in s["jobs"]:
        c = zlib.crc32(j["prompt"].encode())
        Path(j["out"]).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (j["width"], j["height"]), (c % 200 + 30, (c >> 8) % 200 + 30, (c >> 16) % 200 + 30)).save(j["out"])
    Path(s["stats"]).write_text(json.dumps({"stub": True, "images": [{"out": j["out"]} for j in s["jobs"]]}))


def run_arm(arm: str, rows: dict[str, dict], out: Path, runner: Runner, loras: dict[str, dict] | None = None, **kw) -> Path | None:
    jobs = plan_arm(arm, rows, out, loras, **kw)
    if not jobs:
        return None
    engine, ck = ARMS[arm[:-5] if arm.endswith("_lora") else arm]
    spec = out / f"jobs_{arm}.json"
    spec.write_text(json.dumps({"checkpoint": CHECKPOINT.get(ck, ""), "stats": str(out / f"stats_{arm}.json"), "jobs": jobs}, indent=1))
    t = time.time()
    runner(engine, spec)
    print(f"{arm}: {len(jobs)} images in {time.time() - t:.0f}s")
    return spec


def internal_zimage(spec_path: str) -> int:
    """Subprocess body for arm B2: one `LocalZImageWorker`, all panels in one batch."""
    import base64

    from echotales.pipeline.workers_contract import ImageWorkerRequest
    from echotales.pipeline.workers_zimage import LocalZImageWorker

    spec = json.loads(Path(spec_path).read_text())
    rows = json.loads((Path(spec["stats"]).parent / "prompts.json").read_text())
    w = LocalZImageWorker()
    reqs = [ImageWorkerRequest(prompt=j["prompt"], width=j["width"], height=j["height"], seed=j["seed"]) for j in spec["jobs"]]
    resp = w.generate_many(reqs, [rows[j["panel_id"]]["B2"]["sections"] for j in spec["jobs"]])
    for j, r in zip(spec["jobs"], resp, strict=True):
        Path(j["out"]).parent.mkdir(parents=True, exist_ok=True)
        Path(j["out"]).write_bytes(base64.b64decode(r.image_b64))
    w.close()
    Path(spec["stats"]).write_text(json.dumps({"per_image": w.stats}, indent=1, default=str))
    return 0


def phase_sheets(out: Path, arms: list[str]) -> list[Path]:
    """One sheet per panel (ref | arms ...) and `all_<n>.png` stacking four panel strips each, so a whole round reads top to bottom."""
    from PIL import Image, ImageDraw, ImageFile, ImageOps

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    th = 420
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    cols = ["ref", *[a for a in arms if any((out / a / f"{bp.panel_id}.png").exists() for bp in panels())]]
    strips, written = [], []
    for bp in panels():
        tiles = []
        for col in cols:
            f = REF_DIR / f"{REFERENCE.get(bp.panel_id, '')}.jpg" if col == "ref" else out / col / f"{bp.panel_id}.png"
            im = Image.open(f).convert("RGB") if f.exists() else Image.new("RGB", (300, th), (40, 40, 40))
            tiles.append((col, ImageOps.contain(im, (int(th * 0.8), th))))
        strip = Image.new("RGB", (sum(t.width for _, t in tiles) + 6 * len(tiles), th + 44), "white")
        d = ImageDraw.Draw(strip)
        d.text((4, 2), f"{bp.panel_id}  {bp.panel.purpose.value}/{bp.panel.shot.value}/{bp.panel.layer.value}  {bp.note}", fill="black")
        x = 0
        for label, im in tiles:
            strip.paste(im, (x, 40))
            d.text((x + 4, 24), label, fill="red")
            x += im.width + 6
        p = out / "sheets" / f"{bp.panel_id}.png"
        strip.save(p)
        written.append(p)
        strips.append(strip)
    for n in range(0, len(strips), 4):
        grp = strips[n:n + 4]
        stack = Image.new("RGB", (max(s.width for s in grp), sum(s.height for s in grp)), "white")
        y = 0
        for s in grp:
            stack.paste(s, (0, y))
            y += s.height
        p = out / "sheets" / f"all_{n // 4 + 1}.png"
        stack.save(p)
        written.append(p)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--phase", choices=["prompts", "run", "sheets", "all"], default="all")
    ap.add_argument("--arms", default="B2,C2_noobai,C2_illustrious,D")
    ap.add_argument("--out", type=Path, default=ROOT / "data/scratch/art_v3")
    ap.add_argument("--lora", action="append", default=[], help="<fang_yuan|klein|kim_dokja>=<safetensors>[:scale]; adds <arm>_lora arms")
    ap.add_argument("--strength", type=float, default=0.45)
    ap.add_argument("--control", help='JSON {"kind": "canny|lineart|depth", "image": path, "scale": 0.6} applied to SDXL arms')
    ap.add_argument("--stub", action="store_true", help="no GPU: solid-colour stand-in images")
    ap.add_argument("--internal-zimage", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.internal_zimage:
        return internal_zimage(a.internal_zimage)
    loras = parse_loras(a.lora)
    out: Path = a.out
    out.mkdir(parents=True, exist_ok=True)
    arms = [x for x in a.arms.split(",") if x]
    arms += [f"{x}_lora" for x in arms if x in ("C2_noobai", "C2_illustrious", "D") and loras]
    for x in arms:
        if (x[:-5] if x.endswith("_lora") else x) not in ARMS:
            raise SystemExit(f"unknown arm {x!r}; known: {list(ARMS)} (+ _lora)")
    rows = compile_all(loras)
    if a.phase in ("prompts", "all"):
        (out / "prompts.json").write_text(json.dumps(rows, indent=1))
        print("prompts for", len(rows), "panels ->", out / "prompts.json")
    if a.phase in ("run", "all"):
        (out / "prompts.json").write_text(json.dumps(rows, indent=1))  # the Z-Image subprocess reads the sections from here
        runner: Runner = stub_runner if a.stub else gpu_runner
        for arm in sorted(arms, key=lambda x: list(ARMS).index(x[:-5] if x.endswith("_lora") else x)):
            run_arm(arm, rows, out, runner, loras, strength=a.strength, control=json.loads(a.control) if a.control else None)
    if a.phase in ("sheets", "all"):
        print(f"{len(phase_sheets(out, SHEET_COLS + [x for x in arms if x.endswith('_lora')]))} sheets in {out / 'sheets'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
