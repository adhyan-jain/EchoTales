"""Assemble a character-LoRA training set (images + captions) from a character's locked identity sheets and turnarounds.

Reads `data/novels/<CODE>/references/turnarounds/<entity>/<persona>/` (what `persona/identity_sheet.py` and `assets/turnaround.py`
write: view_front/side/back, expr_*.png, turnaround_sheet.png, expression_sheet.png), optionally more approved images via
`--extra`, and writes `<out>/*.png` letterboxed to one square plus `<out>/metadata.jsonl` ({file_name, text}) for
`train_character_lora.py`.

Placeholders are refused: on 2026-11-28 every turnaround on disk (RI, LotM and the test novel) was one of three byte-identical stub
renders from 2026-10-20 (6-12 KB, the same md5 across novels), which would train a LoRA on grey rectangles. An image is rejected if
its file is under 30 KB or its content hash occurs more than once among everything scanned. `--list` prints what exists per
character and why each file is or is not usable, and never fails."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/core/src"))
sys.path.insert(0, str(ROOT / "packages/pipeline/src"))
#: The first three characters: (novel code, turnaround entity folder, trigger word). Folders are the ids the identity-sheet code wrote;
#: a novel with no sheet yet has an empty folder list, and `--list` says so.
CHARACTERS: dict[str, dict] = {
    "fang_yuan": {"name": "Fang Yuan", "novel": "RI", "dirs": ["reverend-insanity_self_476821534c"], "trigger": "fangyuan_ri"},
    "klein": {"name": "Klein Moretti", "novel": "LOTM", "dirs": ["lord-of-the-mysteries%3Aself%3A8f906ddc75"], "trigger": "klein_lotm"},
    "kim_dokja": {"name": "Kim Dokja", "novel": "ORV", "dirs": [], "trigger": "kimdokja_orv"},
}
MIN_BYTES = 30_000
SIZE = 768
_VIEW = {"view_front": "facing viewer, standing", "view_side": "from side, standing", "view_back": "from behind, standing",
         "turnaround_sheet": "multiple views, character sheet, turnaround", "expression_sheet": "multiple views, expression chart"}
_EXPR = {"neutral": "expressionless", "angry": "angry, clenched teeth", "shocked": "shocked, wide-eyed", "crying": "crying, tears",
         "smirking": "smirk", "shouting": "shouting, open mouth", "in_pain": "pained, grimace"}


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def scan(data_root: Path) -> dict[str, list[Path]]:
    """Every turnaround image under data/novels, so duplicates across characters and novels are visible."""
    return {str(p): [p] for p in sorted(data_root.glob("novels/*/references/turnarounds/*/*/*.png"))}


def character_files(key: str, data_root: Path) -> list[Path]:
    c = CHARACTERS[key]
    out: list[Path] = []
    for d in c["dirs"]:
        out += sorted((data_root / "novels" / c["novel"] / "references/turnarounds" / d).glob("*/*.png"))
    return out


def classify(files: list[Path], data_root: Path) -> list[tuple[Path, str]]:
    """(file, "" if usable else the reason). Duplicates are judged against the whole data root, not just this character."""
    counts: dict[str, int] = {}
    for p in data_root.glob("novels/*/references/turnarounds/*/*/*.png"):
        counts[_md5(p)] = counts.get(_md5(p), 0) + 1
    out = []
    for f in files:
        if f.stat().st_size < MIN_BYTES:
            out.append((f, f"placeholder: {f.stat().st_size} bytes"))
        elif counts.get(_md5(f), 0) > 1:
            out.append((f, f"duplicate content ({counts[_md5(f)]} identical files)"))
        else:
            out.append((f, ""))
    return out


def caption(path: Path, trigger: str, base_tags: str) -> str:
    stem = path.stem
    view = _VIEW.get(stem) or (f"portrait, {_EXPR.get(stem[5:], stem[5:].replace('_', ' '))}" if stem.startswith("expr_") else "")
    return ", ".join(t for t in (trigger, base_tags, view, "simple background, grey background") if t)


def letterbox(src: Path, dst: Path, size: int = SIZE) -> None:
    """Pad to a square on the image's own corner colour: the diffusers trainer has no bucketing (see train_character_lora.py)."""
    from PIL import Image

    im = Image.open(src).convert("RGB")
    scale = size / max(im.size)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), im.getpixel((0, 0)))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    canvas.save(dst)


def identity_base_tags(look_json: Path | None, tags: str) -> str:
    if tags:
        return tags
    if look_json is None:
        return ""
    from echotales.pipeline.render.compiler import CharacterBrief
    from echotales.pipeline.render.drama_tags import identity_tags

    return ", ".join(identity_tags(CharacterBrief(**json.loads(look_json.read_text()))))


def build(key: str, out: Path, data_root: Path, *, base_tags: str = "", extra: list[Path] | None = None) -> dict:
    c = CHARACTERS[key]
    classified = classify(character_files(key, data_root), data_root)
    usable = [f for f, why in classified if not why] + [p for p in (extra or []) if p.exists()]
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, f in enumerate(usable):
        name = f"{i:03d}_{f.stem}.png"
        letterbox(f, out / name)
        rows.append({"file_name": name, "text": caption(f, c["trigger"], base_tags)})
    (out / "metadata.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return {"character": key, "trigger": c["trigger"], "found": len(classified), "usable": len(rows),
            "rejected": {str(f): why for f, why in classified if why}, "out": str(out)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--character", choices=sorted(CHARACTERS))
    ap.add_argument("--list", action="store_true", help="print what exists for the three characters and exit")
    # a worktree has no gitignored data; the primary checkout holds the sheets
    ap.add_argument("--data-root", type=Path, default=ROOT / "data" if (ROOT / "data/novels").exists() else Path.home() / "Desktop/EchoTales/data")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--tags", default="", help="identity tags every caption carries (hair, eyes, clothes)")
    ap.add_argument("--look-json", type=Path, help="a CharacterBrief as JSON; its identity tags are used when --tags is empty")
    ap.add_argument("--extra", type=Path, nargs="*", default=[], help="more approved images (e.g. approved panel crops)")
    a = ap.parse_args(argv)
    if a.list or not a.character:
        for k, c in CHARACTERS.items():
            rows = classify(character_files(k, a.data_root), a.data_root)
            print(f"{k} ({c['name']}, {c['novel']}): {len(rows)} files, {sum(1 for _, w in rows if not w)} usable")
            for f, why in rows:
                print(f"   {f.name:22} {f.stat().st_size:>7} B  {why or 'usable'}")
        return 0
    if a.out is None:
        ap.error("--out is required")
    res = build(a.character, a.out, a.data_root, base_tags=identity_base_tags(a.look_json, a.tags), extra=a.extra)
    print(json.dumps(res, indent=1))
    if res["usable"] == 0:
        print("no usable identity images: regenerate the sheets (echotales persona / Studio), approve them, then rerun", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
