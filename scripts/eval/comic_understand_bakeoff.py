"""Bake-off for comic page understanding on Pepper&Carrot (David Revoy, CC BY 4.0) pages.

Compares OCR engines through the real understanding path: dialogue character accuracy against a hand
transcription, false speech bubbles (in-art text and sound effects that must NOT be voiced), panel-count
correctness, and seconds per page. Writes data/eval/comic/understand_bakeoff.json.

    ECHOTALES_COMIC_LIBS=... python scripts/eval/comic_understand_bakeoff.py --engines rapidocr easyocr
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from PIL import Image

from echotales.pipeline.comic.ocr import OcrUnavailable, get_ocr
from echotales.pipeline.comic.understand import understand_pages
from echotales.pipeline.comic.ingest import PageImage

ROOT = Path("data/raw/comics/pepper-carrot")
#: Hand transcription (read off the page images by eye): the spoken text in reading order, and the panel count.
#: ep02 pages carry no dialogue, only sound effects and in-art lettering (a sign, bottle labels): they measure
#: false positives.
TRUTH = {
    "ep01/en_E01P01.jpg": {"panels": 3, "dialogue": ["...and the last touch.", "...mmm probably not strong enough."]},
    "ep01/en_E01P02.jpg": {"panels": 3, "dialogue": ["ha... perfect.", "NO! Don't even think about it."]},
    "ep02/en_E02P01.jpg": {"panels": 2, "dialogue": []},
    "ep02/en_E02P02.jpg": {"panels": 3, "dialogue": []},
}


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def run(engine_name: str) -> dict:
    ocr = get_ocr(engine_name)
    ocr.read(Image.new("RGB", (64, 64), "white"))  # load models before timing
    per_page, edits, ref_chars, false_speech, panels_ok = [], 0, 0, 0, 0
    sp_edits, sp_ref = 0, 0
    for rel, truth in TRUTH.items():
        img = Image.open(ROOT / rel).convert("RGB")
        t0 = time.perf_counter()
        und = understand_pages([PageImage(0, rel, img)], ocr)
        secs = time.perf_counter() - t0
        spoken = [b.text for b in und.bubbles() if b.kind in ("speech", "narration")]
        ref, hyp = _squash("".join(truth["dialogue"])), _squash("".join(spoken))
        edits += levenshtein(ref, hyp)
        ref_sp, hyp_sp = " ".join(truth["dialogue"]).lower(), " ".join(spoken).lower()
        sp_edits += levenshtein(ref_sp, hyp_sp)
        sp_ref += len(ref_sp)
        ref_chars += len(ref)
        # A speech bubble beyond the expected count is text that would be voiced and should not be.
        extra = max(0, len(spoken) - len(truth["dialogue"]))
        false_speech += extra
        ok = len(und.pages[0].panels) == truth["panels"]
        panels_ok += ok
        per_page.append({"page": rel, "seconds": round(secs, 2), "panels": len(und.pages[0].panels), "panels_ok": ok,
                         "spoken": spoken, "expected": truth["dialogue"], "extra_spoken": extra,
                         "kinds": [b.kind for b in und.bubbles()]})
    return {
        "engine": engine_name,
        "dialogue_char_accuracy": round(1 - edits / max(ref_chars, 1), 4),
        "dialogue_char_accuracy_with_spaces": round(1 - sp_edits / max(sp_ref, 1), 4),
        "reference_chars": ref_chars, "edit_distance": edits,
        "false_spoken_bubbles": false_speech,
        "panel_pages_correct": f"{panels_ok}/{len(TRUTH)}",
        "seconds_per_page": round(sum(p["seconds"] for p in per_page) / len(per_page), 2),
        "pages": per_page,
    }


def speaker_check(engine_name: str) -> dict:
    """ep01 has one speaker (Pepper says all four lines). This measures only that her bubbles merge into one cluster;
    it cannot show that two different characters split, because no page here has two speakers. Reported as such."""
    ocr = get_ocr(engine_name)
    pages = [PageImage(i, rel, Image.open(ROOT / rel).convert("RGB"))
             for i, rel in enumerate(["ep01/en_E01P01.jpg", "ep01/en_E01P02.jpg"])]
    und = understand_pages(pages, ocr)
    speech = [b for b in und.bubbles() if b.kind == "speech"]
    return {
        "truth": "one speaker (Pepper) for all 4 spoken lines",
        "speech_bubbles": len(speech),
        "with_tail": sum(b.tail is not None for b in speech),
        "clusters": sorted({b.speaker for b in speech if b.speaker}),
        "same_speaker_merged": len({b.speaker for b in speech if b.speaker}) == 1,
        "not_measured": "splitting two different characters (no multi-speaker page in the test set)",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", nargs="+", default=["rapidocr", "easyocr"])
    ap.add_argument("--out", default="data/eval/comic/understand_bakeoff.json")
    args = ap.parse_args()
    results, skipped = [], {}
    for name in args.engines:
        try:
            results.append(run(name))
        except OcrUnavailable as exc:
            skipped[name] = str(exc)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out.read_text()) if out.exists() else {}
    existing.update({"source": "Pepper&Carrot ep01 P01-P02, ep02 P01-P02 (David Revoy, CC BY 4.0)",
                     "results": results, "skipped": skipped,
                     "speaker_clustering": speaker_check(args.engines[0]),
                     "magi_v2": "not run: model card README states unrestricted use only for personal, research and "
                                "non-commercial endeavours (commercial use needs a separate arrangement), 2 GB pickled "
                                "weights and trust_remote_code; manga-ocr not run: Japanese-trained recogniser, wrong "
                                "script for these English pages"})
    out.write_text(json.dumps(existing, indent=1, ensure_ascii=False))
    for r in results:
        print({k: v for k, v in r.items() if k != "pages"})


if __name__ == "__main__":
    main()
