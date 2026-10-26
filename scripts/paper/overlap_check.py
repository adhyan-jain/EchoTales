"""Word n-gram overlap between the journal manuscript and the abstracts of every work it cites (journal Revision 1).

Why this exists: the draft goes to a supervisor who will run it through a similarity checker, and the related-work
section paraphrases about thirty papers. iThenticate and Turnitin are not available to us, so this is the check we can
run: strip main.tex to prose, then look for any run of N identical words (default 8) shared with a cited abstract
(arXiv API for 10.48550 DOIs, Semantic Scholar otherwise, Crossref as a fallback). Abstracts are where copied phrasing
usually comes from when a related-work paragraph is written from the paper's landing page. A shared run is reported
with its sentence so it can be rewritten; the script never decides that something is fine. Abstracts are cached so a
rerun does not refetch them.

Run: python scripts/paper/overlap_check.py [--n 8]
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from verify_references import BIB, UA, entries, get

TEX = Path("docs/paper/journal/main.tex")
CACHE = Path("data/eval/validation/cited_abstracts.json")
OUT = Path("docs/paper/journal/overlap_check.md")


def prose(tex: str) -> str:
    body = tex.split("\\begin{document}", 1)[1]
    body = re.sub(r"(?<!\\)%.*", "", body)
    body = re.sub(r"\\begin\{(table|tabular\*?|equation)\}.*?\\end\{\1\}", " ", body, flags=re.S)
    body = re.sub(r"\\(cite|ref|label|includegraphics|url|eqref|email|bibliography)\*?(\[[^\]]*\])?\{[^}]*\}", " ", body)
    body = re.sub(r"\$[^$]*\$", " ", body)
    body = re.sub(r"\\[a-zA-Z]+\*?", " ", body)
    return re.sub(r"[{}~\\]", " ", body)


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def abstract(doi: str) -> str:
    if doi.lower().startswith("10.48550/arxiv."):
        aid = re.sub(r"^arxiv\.", "", doi.split("/", 1)[1], flags=re.I)
        x = get(f"https://export.arxiv.org/api/query?id_list={aid}").decode()
        m = re.search(r"<summary>(.*?)</summary>", x.split("<entry>", 1)[1], re.S)
        return re.sub(r"\s+", " ", m.group(1)) if m else ""
    try:
        d = json.loads(get("https://api.semanticscholar.org/graph/v1/paper/DOI:" + urllib.parse.quote(doi) + "?fields=abstract"))
        if d.get("abstract"):
            return d["abstract"]
    except urllib.error.HTTPError:
        pass
    d = json.loads(get("https://api.crossref.org/works/" + urllib.parse.quote(doi)))
    return re.sub(r"<[^>]+>", " ", d["message"].get("abstract", ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    n = ap.parse_args().n
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for _, key, f in entries(BIB.read_text()):
        if cache.get(key) or "doi" not in f:
            continue
        try:
            cache[key] = abstract(f["doi"])
        except Exception as e:  # noqa: BLE001 -- a missing abstract is reported, not fatal
            cache[key] = ""
            print(f"{key}: no abstract ({e})")
        time.sleep(1.5)
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))

    text = prose(TEX.read_text())
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", re.sub(r"\s+", " ", text)) if len(words(s)) >= n]
    grams = {}
    for key, abs_ in cache.items():
        w = words(abs_)
        for i in range(len(w) - n + 1):
            grams.setdefault(tuple(w[i:i + n]), set()).add(key)
    hits = []
    for s in sentences:
        w = words(s)
        found = {g: grams[g] for g in (tuple(w[i:i + n]) for i in range(len(w) - n + 1)) if g in grams}
        if found:
            hits.append((s, sorted({k for v in found.values() for k in v}), " ".join(next(iter(found)))))
    have = sum(1 for v in cache.values() if v)
    lines = [f"# Overlap check: main.tex against cited abstracts ({n}-word runs)", "",
             f"Abstracts compared: {have} of {len(cache)} cited works with a DOI. Manuscript sentences checked: {len(sentences)}.",
             f"Sentences sharing a run of {n} or more identical words with a cited abstract: {len(hits)}.", "",
             "This is not iThenticate or Turnitin: it compares only against the abstracts of works we cite, so it finds",
             "phrasing carried over from a source's landing page, not overlap with uncited text on the web.", ""]
    for s, keys, g in hits:
        lines += [f"- [{', '.join(keys)}] \"{g}\"", f"  > {s}", ""]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:5]))
    for s, keys, g in hits:
        print(keys, "|", g)


if __name__ == "__main__":
    main()
