"""Build data/gold/ner_romanized/*.jsonl from hand-authored, marker-annotated passages.

Why markers instead of hand-typed offsets: a single off-by-one in a hand-counted offset silently poisons every
metric computed from it. Passages are authored as "[[Fang Yuan|p|ord]] bowed" and offsets are derived here, so
`text[start:end] == surface` holds by construction (and is re-checked by `ner_spans.validate_record`).

Marker grammar: [[surface|label|category]]; category defaults to `ord`.
  label    p=person  t=title_epithet  l=location  o=organization  i=item
  category ord=ordinary  unf=unfamiliar_fantasy  inv=invented  tit=title  ali=alias_epithet
           wl=word_like  si=sentence_initial  sh=shared_title

The passages are original prose written for this set (no copyrighted text). They live in
scripts/eval/ner_gold_passages/<background>.py, each exposing PASSAGES = [(doc_id, text), ...].

Split: per background, doc_ids are ordered by md5 and the first 40% (rounded) become dev, so the split is a
deterministic function of the id set and stays balanced per background.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "gold" / "ner_romanized"
sys.path.insert(0, str(Path(__file__).parent))

LABELS = {"p": "person", "t": "title_epithet", "l": "location", "o": "organization", "i": "item"}
CATS = {
    "ord": "ordinary", "unf": "unfamiliar_fantasy", "inv": "invented", "tit": "title",
    "ali": "alias_epithet", "wl": "word_like", "si": "sentence_initial", "sh": "shared_title",
}
BACKGROUNDS = ["zh", "ko", "ja", "in", "eu", "invented", "mixed"]
_MARK = re.compile(r"\[\[([^\[\]]+?)\]\]")


def parse(doc_id: str, marked: str) -> tuple[str, list[dict]]:
    text_parts: list[str] = []
    spans: list[dict] = []
    pos = 0
    out_len = 0
    for m in _MARK.finditer(marked):
        plain = marked[pos : m.start()]
        text_parts.append(plain)
        out_len += len(plain)
        fields = m.group(1).split("|")
        surface = fields[0]
        label = LABELS[fields[1]]
        cat = CATS[fields[2] if len(fields) > 2 else "ord"]
        span = {"start": out_len, "end": out_len + len(surface), "surface": surface, "label": label, "category": cat}
        # Bare lower-case role noun ("the dean", "guild master"): EchoTales keeps generic descriptors out of the graph
        # (non-negotiable 4), so the benchmark must not charge detectors for skipping them. Capitalised titles
        # ("the Emperor", "Heavenly Demon") stay ordinary gold. The key is only written when true, so every other
        # span stays byte-identical.
        if label == "title_epithet" and re.sub(r"^(the|a|an) ", "", surface, flags=re.I).islower():
            span["generic_role"] = True
        spans.append(span)
        text_parts.append(surface)
        out_len += len(surface)
        pos = m.end()
    text_parts.append(marked[pos:])
    text = "".join(text_parts)
    if "[[" in text or "]]" in text:
        raise ValueError(f"{doc_id}: unbalanced marker")
    for s in spans:
        assert text[s["start"] : s["end"]] == s["surface"], doc_id
    return text, spans


def lint(doc_id: str, text: str, spans: list[dict]) -> list[str]:
    """Warn when a surface annotated once appears unannotated elsewhere: the usual authoring slip."""
    warns = []
    covered = [(s["start"], s["end"]) for s in spans]
    # Individual tokens of multi-word names too: "Lady Hinako" annotated while a bare "Hinako" is left
    # unmarked is the commonest slip, and an exact-surface check cannot see it.
    surfaces = {s["surface"] for s in spans if len(s["surface"]) > 2}
    for s in spans:
        if s["label"] in ("person", "location", "organization"):
            surfaces |= {t for t in re.split(r"[ \-]", s["surface"]) if len(t) > 3 and t[0].isupper()}
    for surf in surfaces:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(surf) + r"(?![A-Za-z])", text):
            a, b = m.span()
            if not any(cs <= a and b <= ce for cs, ce in covered):
                warns.append(f"{doc_id}: unannotated occurrence of {surf!r} at {a}")
    return warns


def assign_splits(ids: list[str]) -> dict[str, str]:
    ordered = sorted(ids, key=lambda i: hashlib.md5(i.encode()).hexdigest())
    n_dev = round(0.4 * len(ordered))
    return {i: ("dev" if k < n_dev else "test") for k, i in enumerate(ordered)}


def main() -> None:
    records: list[dict] = []
    warns: list[str] = []
    for bg in BACKGROUNDS:
        mod = importlib.import_module(f"ner_gold_passages.{bg}")
        splits = assign_splits([d for d, _ in mod.PASSAGES])
        for doc_id, marked in mod.PASSAGES:
            text, spans = parse(doc_id, marked)
            warns += lint(doc_id, text, spans)
            records.append({"doc_id": doc_id, "source": "synthetic", "background": bg,
                            "split": splits[doc_id], "text": text, "spans": spans})
    ids = [r["doc_id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate doc_id"
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ("dev", "test"):
        with (OUT / f"synthetic_{split}.jsonl").open("w", encoding="utf-8") as fh:
            for r in records:
                if r["split"] == split:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    # Public-domain excerpts: same markers, but each passage is a dict carrying work / gutenberg_id, and the output goes
    # to its own files so the synthetic outputs stay byte-identical.
    pd_mod = importlib.import_module("ner_gold_passages.public_domain")
    pd_records: list[dict] = []
    for bg in BACKGROUNDS:
        group = [p for p in pd_mod.PASSAGES if p["background"] == bg]
        splits = assign_splits([p["doc_id"] for p in group])
        for p in group:
            text, spans = parse(p["doc_id"], p["marked"])
            warns += lint(p["doc_id"], text, spans)
            pd_records.append({"doc_id": p["doc_id"], "source": "public_domain", "background": bg,
                               "split": splits[p["doc_id"]], "work": p["work"], "gutenberg_id": p["gutenberg_id"],
                               "text": text, "spans": spans})
    assert len({r["doc_id"] for r in pd_records} | set(ids)) == len(pd_records) + len(ids), "duplicate doc_id"
    for split in ("dev", "test"):
        with (OUT / f"public_domain_{split}.jsonl").open("w", encoding="utf-8") as fh:
            for r in pd_records:
                if r["split"] == split:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(pd_records)} public-domain passages, {sum(len(r['spans']) for r in pd_records)} spans")
    for w in warns:
        print("LINT", w)
    for r in records + pd_records:
        flagged = [s["surface"] for s in r["spans"] if s.get("generic_role")]
        if flagged:
            print("GENERIC", r["source"], r["split"], r["doc_id"], flagged)
    for src, rs in (("synthetic", records), ("public_domain", pd_records)):
        for split in ("dev", "test"):
            n = sum(1 for r in rs if r["split"] == split for s in r["spans"] if s.get("generic_role"))
            print(f"generic_role {src} {split}: {n}")
    print(f"{len(records)} passages, {sum(len(r['spans']) for r in records)} spans, {len(warns)} lint warnings")


if __name__ == "__main__":
    main()
