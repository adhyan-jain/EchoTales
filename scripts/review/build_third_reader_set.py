"""Build the deployable page for the independent third reader (revised adjudication, 2026-10-31).

Why this exists: the revised rule in score_disclosure_validation.py lets Aryan's and Atharva's labels win every split with the
first author, and leaves four cases open where those two split with each other. Those four are the ones a further human reader
must settle: C017, C038 and C021 on gender, and C038, C021 and C020 on support. The earlier plan sent the 11 cases the first
author had ruled on; they are kept as a cross-check (does a reader who has not read the books side with Aryan and Atharva?), and
C020 is added because it is the support split the 11 did not cover.

Output: data/scratch/third_reader_app/ (disposable, gitignored). It holds excerpts of copyrighted web serials, so deploy it only
behind Vercel deployment protection and take it down once the labels are exported, as for the main page. Nothing is deployed here.

Run: python scripts/review/build_third_reader_set.py
Then: import the exported file with scripts/review/import_third_reader.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

APP = Path("scripts/review/disclosure_validation_app")
OUT = Path("data/scratch/third_reader_app")
NEEDED = ["C017", "C038", "C021", "C020"]
CROSS_CHECK = ["C005", "C014", "C015", "C016", "C018", "C028", "C036", "C041"]
VERSION = "disclosure-validation-v1-third"


def main() -> None:
    src = json.load(open(APP / "cases.json"))
    keep = set(NEEDED + CROSS_CHECK)
    cases = [dict(c, annotators=["Friend"]) for c in src["cases"] if c["case"] in keep]
    assert {c["case"] for c in cases} == keep, sorted(keep - {c["case"] for c in cases})
    OUT.mkdir(parents=True, exist_ok=True)
    for f in ("index.html", "app.js", "style.css", "favicon.svg", "vercel.json", ".vercelignore"):
        if (APP / f).exists():
            shutil.copy(APP / f, OUT / f)
    json.dump(dict(src, version=VERSION, annotators=["Friend"], cases=cases), open(OUT / "cases.json", "w"), ensure_ascii=False)
    print(f"wrote {OUT}: {len(cases)} cases for one reader ({len(NEEDED)} needed, {len(CROSS_CHECK)} cross-check)")


if __name__ == "__main__":
    main()
