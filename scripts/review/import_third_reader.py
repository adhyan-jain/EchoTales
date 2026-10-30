"""Turn the exported labels of the independent third reader into adjudication_third.json for the scorer.

Why this exists: the protocol asked someone who has not read the books to settle the cases the first author had ruled on. That person
labels the 11 cases on the same page as the others and sends back labels_Friend.json; the scorer reads adjudication_third.json.
Anything the reader says he knew from the book (q0 = yes) is kept in the file so the paper can report it.

Run: python scripts/review/import_third_reader.py <path to labels_Friend.json>
"""
import json
import sys
from pathlib import Path

OUT = Path("data/eval/validation/disclosure_labels/adjudication_third.json")


def main(src: str) -> None:
    d = json.load(open(src))
    labs = d["labels"]
    assert len(labs) == 11, f"expected 11 cases, got {len(labs)}"
    out = {k: {"q0": v.get("q0"), "q1": v["q1"], "q3": v.get("q3"), "q4": v.get("q4"), "note": v.get("note", "")} for k, v in labs.items()}
    json.dump({"adjudicator": "independent reader, not an author, who had not read the books", "labels": out}, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}: {len(out)} cases, knew the book on {sum(v['q0'] == 'yes' for v in out.values())}")


if __name__ == "__main__":
    main(sys.argv[1])
