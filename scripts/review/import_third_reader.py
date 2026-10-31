"""Turn the exported labels of the independent third reader into adjudication_third.json for the scorer.

Why this exists: the protocol asked someone who has not read the books to settle the cases the first author had ruled on. Under the
revised rule (2026-10-31) the scorer needs this reader only for C017, C038, C021 (gender) and C038, C021, C020 (support); the other
cases they label are a cross-check. Build their page with scripts/review/build_third_reader_set.py; they send back labels_Friend.json;
the scorer reads adjudication_third.json, which outranks the model passages-only reading.
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
    # the revised adjudication needs these four (two non-first-author annotators split); the rest is a cross-check
    # C020 (a support split) is optional: the page the reader actually used was the earlier 11-case set, which never
    # contained it, so C020 stays excluded from the served-value rates rather than blocking the import.
    needed = {"C017", "C038", "C021"}
    assert needed <= set(labs), f"missing needed cases: {sorted(needed - set(labs))}"
    if "C020" not in labs:
        print("note: C020 not labelled by the third reader; it stays excluded from the served-value rates")
    out = {k: {"q0": v.get("q0"), "q1": v["q1"], "q3": v.get("q3"), "q4": v.get("q4"), "note": v.get("note", "")} for k, v in labs.items()}
    json.dump({"adjudicator": "independent reader, not an author, who had not read the books", "labels": out}, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}: {len(out)} cases, knew the book on {sum(v['q0'] == 'yes' for v in out.values())}")


if __name__ == "__main__":
    main(sys.argv[1])
