"""CLIPScore for rendered panels: how well each image matches its own prompt.

REMAINING_WORK 1.4 listed prompt-image alignment as "not run" because the
1.7 GB CLIP ViT-L/14 download was never made; the weights were already in the
local Hugging Face cache. This scores every panel in a render manifest with
CLIPScore (Hessel et al., 2021: 2.5 * max(cos(image, text), 0), reported x100)
and, as a control, against a prompt drawn from a *different* panel of the same
render. The control is the point: a mean CLIPScore alone says little, because
panels of one chapter share style tags; the gap between matched and shuffled
prompts says whether the image follows the prompt's content.

The prompt is truncated to CLIP's 77 tokens, the same budget the image engines
see (`persona/prompt.py::fit_to_budget`). Style-only tokens are not stripped,
so the score is conservative about content.

Usage:
    python3 scripts/eval/clip_score.py MANIFEST [MANIFEST ...] [--out data/eval/clipscore.json] [--seed 20260927]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

#: Manifests record the image path that was true when they were written; the
#: 2026-09-27 restructure moved the folders (data/README.md).
_LEGACY = [
    ("data/RI/panels-obs-reader/", "data/novels/RI/experiments/observer-contrast/reader/"),
    ("data/RI/panels-obs-nonwitness/", "data/novels/RI/experiments/observer-contrast/nonwitness/"),
    ("data/RI/", "data/novels/RI/"),
    ("data/lord-of-the-mysteries/", "data/novels/LOTM/"),
]


def resolve_image(recorded: str, manifest: Path) -> Path | None:
    path = Path(recorded)
    if path.is_file():
        return path
    for old, new in _LEGACY:
        if recorded.startswith(old):
            moved = Path(new + recorded[len(old):])
            if moved.is_file():
                return moved
    local = manifest.parent / path.name
    return local if local.is_file() else None


def load(manifest: Path) -> list[tuple[Path, str]]:
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        image = resolve_image(row.get("image_path", ""), manifest)
        if image is not None and row.get("prompt"):
            rows.append((image, row["prompt"]))
    return rows


def score(rows: list[tuple[Path, str]], rng: random.Random, model, processor, device) -> dict:
    import torch
    from PIL import Image

    images = [Image.open(p).convert("RGB") for p, _ in rows]
    prompts = [t for _, t in rows]
    # A derangement by index, so no image is scored against its own prompt.
    # Comparing prompt *strings* looped forever: a render repeats identical
    # prompts across panels, so no string-level derangement exists.
    order = list(range(len(prompts)))
    while len(order) > 1 and any(i == j for i, j in enumerate(order)):
        rng.shuffle(order)
    shuffled = [prompts[j] for j in order]
    def emb(out):  # transformers 5 returns an output object, 4 a tensor
        return out if isinstance(out, torch.Tensor) else out.pooler_output

    with torch.no_grad():
        img = emb(model.get_image_features(**processor(images=images, return_tensors="pt").to(device)))
        img = img / img.norm(dim=-1, keepdim=True)

        def text_emb(texts: list[str]):
            enc = processor(text=texts, return_tensors="pt", padding=True, truncation=True, max_length=77).to(device)
            t = emb(model.get_text_features(**enc))
            return t / t.norm(dim=-1, keepdim=True)

        matched = (img * text_emb(prompts)).sum(-1).clamp(min=0) * 250
        control = (img * text_emb(shuffled)).sum(-1).clamp(min=0) * 250
    m, c = matched.tolist(), control.tolist()
    wins = sum(a > b for a, b in zip(m, c, strict=True))
    return {
        "panels": len(rows),
        "clipscore_mean": round(statistics.mean(m), 2),
        "clipscore_sd": round(statistics.pstdev(m), 2),
        "shuffled_prompt_mean": round(statistics.mean(c), 2),
        "matched_beats_shuffled": f"{wins}/{len(m)}",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifests", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/eval/clipscore.json"))
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--model", default="openai/clip-vit-large-patch14")
    args = ap.parse_args()

    import torch
    from transformers import CLIPModel, CLIPProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CLIPModel.from_pretrained(args.model).to(device).eval()
    processor = CLIPProcessor.from_pretrained(args.model)
    rng = random.Random(args.seed)

    results = {"model": args.model, "seed": args.seed,
               "metric": "CLIPScore = 2.5 * max(cos, 0) * 100 (Hessel et al., 2021); prompt truncated to 77 tokens",
               "control": "the same images scored against a prompt from another panel of the same render",
               "runs": {}}
    for manifest in args.manifests:
        rows = load(manifest)
        if len(rows) < 2:
            print(f"skip {manifest}: {len(rows)} resolvable panels")
            continue
        results["runs"][str(manifest)] = score(rows, rng, model, processor, device)
        print(manifest, results["runs"][str(manifest)])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
