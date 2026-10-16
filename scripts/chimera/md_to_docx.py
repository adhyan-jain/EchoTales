"""Convert the Novelty Report's Markdown subset to .docx via HTML + LibreOffice (no third-party Python deps).

Supported: # headings, paragraphs, - / 1. lists, pipe tables, fenced code, **bold**, *italic*, `code`, [text](url).
Used only for docs/research/NOVELTY_REPORT/; not a general Markdown converter.

    python scripts/chimera/md_to_docx.py docs/research/NOVELTY_REPORT/NOVELTY_REPORT.md
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def convert(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(html.escape(lines[j]))
                j += 1
            out.append("<pre>" + "\n".join(buf) + "</pre>")
            i = j + 1
            continue
        m = re.match(r"(#{1,6})\s+(.*)", ln)
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
            continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"\|[\s:|-]+\|?\s*$", lines[i + 1]):
            hdr = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            t = ["<table border='1' cellspacing='0' cellpadding='3' width='100%' style='table-layout:fixed;width:100%;font-size:9pt'>",
                 "<tr>" + "".join(f"<th>{inline(c)}</th>" for c in hdr) + "</tr>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</table>")
            out.append("\n".join(t))
            i = j
            continue
        if re.match(r"\s*([-*]|\d+\.)\s+", ln):
            ordered = bool(re.match(r"\s*\d+\.", ln))
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(inline(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{x}</li>" for x in items) + f"</{tag}>")
            continue
        if ln.strip() == "---":
            out.append("<hr/>")
            i += 1
            continue
        if ln.strip() == "":
            i += 1
            continue
        para = [ln]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"(#{1,6}\s|```|\||\s*([-*]|\d+\.)\s+)", lines[i]):
            para.append(lines[i])
            i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
    return (
        "<html><head><meta charset='utf-8'><style>body{font-family:Calibri,Arial;font-size:11pt}"
        "code,pre{font-family:Consolas,monospace;font-size:9.5pt}table{border-collapse:collapse;word-wrap:break-word}td,th{word-wrap:break-word;font-size:9pt}</style></head><body>"
        + "\n".join(out) + "</body></html>"
    )


def main() -> None:
    src = Path(sys.argv[1])
    html_path = src.with_suffix(".html")
    html_path.write_text(convert(src.read_text(encoding="utf-8")), encoding="utf-8")
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "docx:MS Word 2007 XML", "--outdir", str(src.parent), str(html_path)],
        check=True,
    )
    html_path.unlink()  # intermediate file this script created itself
    print(src.with_suffix(".docx"))


if __name__ == "__main__":
    main()
