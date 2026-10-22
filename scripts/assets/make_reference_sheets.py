"""Generate character reference sheets from the bible with the local NoobAI worker, plus one contact sheet per character.

    ECHOTALES_IMAGE_WORKER=noobai python scripts/assets/make_reference_sheets.py <db> <novel_id> <chapter> \
        --names "Zhou Mingrui,Daly" --out data/scratch/phase_c/lotm

What goes into each prompt is exactly what the bible holds for that character at `chapter` (`bible_at`, so nothing the
reader has not met yet), turned into image tags by `assets/turnaround.py::look_clauses`. Nothing is hand-written here: a
look the book states shows up in the picture, a look it does not state does not. That is the point of reviewing these:
the images are a readable view of what the extraction knows.

Output goes under `data/scratch/` by default (disposable). The GPU must be free (the worker refuses to start otherwise)
and the memory-heavy model is freed when the script ends.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

from echotales.core.store import Store
from echotales.pipeline.assets.turnaround import generate_character_assets, look_clauses
from echotales.pipeline.workers_local import close_local_worker


def _contact_sheet(label: str, looks: list[str], asset, out: Path) -> Path:  # type: ignore[no-untyped-def]
    """One image: the 3-view sheet on top, the three view crops and the expression crops below, with the prompt tags."""
    tiles = [Image.open(asset.sheet_image_path)]
    tiles += [Image.open(p) for p in asset.view_crops.values()]
    expr = [Image.open(p) for p in asset.expression_crops.values()]
    width = 1400
    top = tiles[0].resize((width, int(tiles[0].height * width / tiles[0].width)))
    thumb = 220
    row1 = [t.resize((thumb, int(t.height * thumb / t.width))) for t in tiles[1:]]
    row2 = [e.resize((thumb, thumb)) for e in expr]
    h1 = max((t.height for t in row1), default=0)
    sheet = Image.new("RGB", (width, top.height + 70 + h1 + thumb + 20), (20, 20, 28))
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 8), f"{label}", fill=(255, 255, 255))
    draw.text((12, 28), "prompt tags from the bible: " + ", ".join(looks), fill=(190, 190, 215))
    sheet.paste(top, (0, 50))
    y = 50 + top.height + 10
    for i, t in enumerate(row1):
        sheet.paste(t, (10 + i * (thumb + 10), y))
    y += h1 + 10
    for i, e in enumerate(row2):
        sheet.paste(e, (10 + i * (thumb + 10), y))
    path = out / f"contact_{re.sub(r'[^a-z0-9]+', '_', label.lower())}.png"
    sheet.save(path)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("novel_id")
    ap.add_argument("chapter", type=float)
    ap.add_argument("--names", required=True, help="comma-separated canonical labels")
    ap.add_argument("--out", default="data/scratch/phase_c")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    store = Store(args.db)
    bible = store.bible_at(args.novel_id, args.chapter)
    wanted = [n.strip() for n in args.names.split(",") if n.strip()]
    by_label = {c.canonical_label: c for c in bible.characters.values()}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = []
    try:
        for name in wanted:
            char = by_label.get(name)
            if char is None:
                print(f"skip {name!r}: not in the bible at chapter {args.chapter:g}", file=sys.stderr)
                continue
            started = time.time()
            asset = generate_character_assets(char, out, visual_genre="anime", seed=args.seed)
            looks = look_clauses(char)
            contact = _contact_sheet(name, looks, asset, out)
            report.append({"character": name, "looks": looks, "seconds": round(time.time() - started), "contact": str(contact)})
            print(f"{name}: {report[-1]['seconds']}s -> {contact}", flush=True)
    finally:
        close_local_worker()
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
