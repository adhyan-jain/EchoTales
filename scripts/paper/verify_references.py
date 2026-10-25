"""Check every references.bib entry against its live record and write the verification log (journal Revision 1).

Why this exists: the revision asks for DOI information on all references and for every 2026 preprint to be checked
against its current record. The course document's reference list had entries no one had re-checked: KoCoNovel was
listed as LREC-COLING 2024 but is an arXiv-only preprint, and a changelog page cited as evidence for a spoiler-filter
product now reads "OpenFiction has retired". This script resolves each DOI (Crossref for publisher DOIs, the arXiv
API for 10.48550 DOIs, plus doi.org itself) and each URL, compares the record's title with the .bib title, and
writes docs/paper/journal/reference_verification.md. A title mismatch or an unresolvable identifier fails the run.

Run: python scripts/paper/verify_references.py
"""
from __future__ import annotations

import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BIB = Path("docs/paper/journal/references.bib")
OUT = Path("docs/paper/journal/reference_verification.md")
UA = {"User-Agent": "EchoTales-reference-check/1.0 (mailto:music1000plus@gmail.com)"}


def entries(text: str):
    for m in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, re.S):
        fields = dict((k.lower(), v.strip()) for k, v in re.findall(r"(\w+)\s*=\s*\{(.*)\},?\s*$", m.group(3), re.M))
        yield m.group(1).lower(), m.group(2).strip(), fields


def norm(s: str) -> str:
    s = re.sub(r"\\[a-zA-Z]+|[{}\\'\"`^~’‘]", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def get(url: str, timeout=60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def status(url: str) -> int:
    req = urllib.request.Request(url, headers={**UA, "User-Agent": "Mozilla/5.0"}, method="GET")
    try:
        return urllib.request.urlopen(req, timeout=60).status
    except urllib.error.HTTPError as e:
        return e.code


def record_title(doi: str):
    if doi.lower().startswith("10.48550/arxiv."):
        aid = doi.split(".", 2)[2] if doi.count(".") >= 2 else doi
        aid = re.sub(r"^arxiv\.", "", doi.split("/", 1)[1], flags=re.I)
        x = get(f"https://export.arxiv.org/api/query?id_list={aid}").decode()
        e = x.split("<entry>", 1)[1]
        title = re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", e, re.S).group(1))
        ver = re.search(r"<id>.*?abs/([^<]+)</id>", e).group(1)
        return title, f"arXiv API ({ver})"
    d = json.loads(get("https://api.crossref.org/works/" + urllib.parse.quote(doi)))
    return (d["message"].get("title") or [""])[0], "Crossref"


def main():
    rows, failures = [], []
    for kind, key, f in entries(BIB.read_text()):
        title = f.get("title", "")
        doi, url = f.get("doi"), f.get("url") or re.sub(r"^\\url\{(.*)\}$", r"\1", f.get("howpublished", ""))
        try:
            if doi:
                rec, src = record_title(doi)
                ok_title = norm(title)[:40] in norm(rec) or norm(rec)[:40] in norm(title)
                # Registration is checked at the handle API: following the redirect lands on publisher pages that
                # answer scripts with 404/406 (Springer, the old aclweb.org host) even though the DOI resolves.
                reg = json.loads(get(f"https://doi.org/api/handles/{urllib.parse.quote(doi)}")).get("responseCode") == 1
                ok = ok_title and reg
                rows.append((key, f"`{doi}`", src, rec[:90], "yes" if ok else f"NO (title match {ok_title}, registered {reg})"))
            elif url.startswith("http"):
                code = status(url)
                ok = code == 200
                rows.append((key, "none (see note)", "URL", url, "yes" if ok else f"NO (HTTP {code})"))
            else:
                ok = False
                rows.append((key, "none", "-", "-", "NO identifier"))
        except Exception as e:  # noqa: BLE001 - every failure is reported, none hidden
            ok = False
            rows.append((key, doi or url, "error", str(e)[:80], "NO"))
        if not ok:
            failures.append(key)
        time.sleep(0.4)
    today = datetime.date.today().isoformat()
    lines = [f"# Reference verification ({today})", "",
             "Each entry of `references.bib` checked against its live record by `scripts/paper/verify_references.py`.",
             "Publisher DOIs were resolved through Crossref and doi.org; arXiv DOIs through the arXiv API (the version listed",
             "is the latest at the check date); entries without any DOI are checked by fetching their URL.", "",
             "| Key | DOI | Record | Title or URL in record | Verified |", "|---|---|---|---|---|"]
    lines += [f"| {k} | {d} | {s} | {t.replace('|', '/')} | {v} |" for k, d, s, t, v in rows]
    lines += ["", f"Entries: {len(rows)}; failures: {len(failures)} {failures if failures else ''}"]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-1:]))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
