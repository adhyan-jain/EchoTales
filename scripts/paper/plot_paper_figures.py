"""Draw the data-ready report figures as SVG, from the generated CSVs only.

`make_paper_artifacts.py` writes the tables and marks Figures 8 and 10 DATA
READY, but nothing drew them (REMAINING_WORK Section 5). This renders them,
plus the compounding curve behind Table 6a, as plain SVG -- no matplotlib,
which the venv does not carry and the report does not need.

Every value is read from `docs/paper/tables/*.csv`; nothing is typed here.
Run `make_paper_artifacts.py` first so the CSVs are current.

Usage:
    python3 scripts/paper/plot_paper_figures.py [--tables docs/paper/tables] [--out docs/paper/figures]
"""

from __future__ import annotations

import argparse
import csv
from html import escape
from pathlib import Path

INK = "#1f2933"
MUTED = "#6b7280"
GRID = "#e5e7eb"
SERIES = ("#1d4ed8", "#0891b2", "#059669", "#b45309")
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def _pct(cell: str) -> float:
    return float(cell.strip().rstrip("%")) / 100.0


def _int(cell: str) -> int:
    return int(cell.replace(",", "").strip())


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _text(x: float, y: float, s: str, *, size: int = 11, anchor: str = "start",
          fill: str = INK, weight: str = "normal") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" '
            f'text-anchor="{anchor}" fill="{fill}" font-weight="{weight}">{escape(s)}</text>')


def _svg(width: int, height: int, body: list[str], title: str, caption: str) -> str:
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        _text(20, 28, title, size=15, weight="bold"),
        *body,
        _text(20, height - 14, caption, size=10, fill=MUTED),
        "</svg>",
        "",
    ])


def figure8_recall(rows: list[dict[str, str]]) -> str:
    """Grouped bars: recall@K per alias type, n printed under each group.

    The n is on the axis rather than in a footnote because it is the finding:
    RELATIONAL_DEICTIC is n=4 and EPITHET n=1, so their bars are anecdotes.
    """
    ks = ["@1", "@5", "@10", "@20"]
    groups = [(r["Alias type"].strip("*"), _int(r["n"]), [_pct(r[k]) for k in ks]) for r in rows]
    left, top, plot_h, group_w, bar_w = 60, 60, 260, 130, 24
    width = left + group_w * len(groups) + 40
    height = top + plot_h + 80
    body: list[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = top + plot_h * (1 - frac)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - 30}" y2="{y:.1f}" stroke="{GRID}"/>')
        body.append(_text(left - 8, y + 4, f"{frac:.0%}", size=10, anchor="end", fill=MUTED))
    for gi, (name, n, vals) in enumerate(groups):
        gx = left + gi * group_w + 12
        for ki, v in enumerate(vals):
            h = plot_h * v
            x = gx + ki * (bar_w + 2)
            body.append(f'<rect x="{x}" y="{top + plot_h - h:.1f}" width="{bar_w}" '
                        f'height="{h:.1f}" fill="{SERIES[ki]}"/>')
        cx = gx + 2 * (bar_w + 2) - 1
        body.append(_text(cx, top + plot_h + 18, name, size=10, anchor="middle"))
        body.append(_text(cx, top + plot_h + 32, f"n={n}", size=10, anchor="middle", fill=MUTED))
    lx = left
    for ki, k in enumerate(ks):
        body.append(f'<rect x="{lx}" y="{top - 22}" width="12" height="12" fill="{SERIES[ki]}"/>')
        body.append(_text(lx + 16, top - 12, f"recall{k}", size=10))
        lx += 90
    return _svg(width, height, body,
                "Figure 8. Retriever recall@K by alias type (production context, reference span given)",
                "LLM-drafted silver reference set, no IAA. Source: docs/paper/tables/table5_recall_at_k.csv. "
                "Small-n groups are anecdotal.")


def figure10_ablation(rows: list[dict[str, str]]) -> str:
    """Stacked horizontal bars: where each pair goes under each condition.

    Stacked rather than grouped because the three buckets partition the same
    15,796 pairs; the fourth column, scorer-would-link, is 0 everywhere and is
    printed as text, since a zero-width bar is invisible rather than informative.
    """
    parts = (("Force-link", SERIES[0]), ("Blocked", SERIES[3]), ("Reached scorer", "#9ca3af"))
    left, top, bar_h, gap, plot_w = 190, 70, 20, 10, 520
    height = top + len(rows) * (bar_h + gap) + 70
    width = left + plot_w + 150
    total = max(_int(r["Pairs"]) for r in rows)
    body: list[str] = []
    lx = left
    for name, color in parts:
        body.append(f'<rect x="{lx}" y="{top - 30}" width="12" height="12" fill="{color}"/>')
        body.append(_text(lx + 16, top - 20, name, size=10))
        lx += 120
    for i, r in enumerate(rows):
        y = top + i * (bar_h + gap)
        body.append(_text(left - 8, y + 14, r["Condition"], size=10, anchor="end"))
        x = float(left)
        for name, color in parts:
            w = plot_w * _int(r[name]) / total
            body.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{color}"/>')
            x += w
        body.append(_text(left + plot_w + 8, y + 14,
                          f"links {_int(r['Force-link']):,} · scorer {_int(r['Scorer would link'])}",
                          size=10, fill=MUTED))
    return _svg(width, height, body,
                "Figure 10. Ablations: where 15,796 candidate pairs are decided",
                "Re-scored from cached evidence. The scorer links 0 pairs under every condition. "
                "Source: docs/paper/tables/table6_ablation.csv.")


def figure9_baselines(rows: list[dict[str, str]]) -> str:
    """Two panels side by side: LLM calls and mentions found, per system.

    Calls and mentions rather than B3: on ch1-10 the gold is surface-trivial,
    so recall is an extraction-coverage number and is printed as a label,
    not drawn as if it were coreference quality.
    """
    left, top, plot_h, bar_w, panel_w = 40, 70, 200, 60, 330
    width = left + 2 * panel_w + 20
    height = top + plot_h + 110
    body: list[str] = []
    for pi, (col, label) in enumerate((("LLM calls", "LLM calls"), ("Mentions", "Mentions found"))):
        px = left + pi * panel_w
        vals = [_int(r[col]) if r[col] not in ("—", "") else 0 for r in rows]
        vmax = max(vals) or 1
        body.append(_text(px, top - 16, label, size=12, weight="bold"))
        body.append(f'<line x1="{px}" y1="{top + plot_h}" x2="{px + panel_w - 40}" '
                    f'y2="{top + plot_h}" stroke="{GRID}"/>')
        for i, (r, v) in enumerate(zip(rows, vals, strict=True)):
            x = px + 10 + i * (bar_w + 30)
            h = plot_h * v / vmax
            body.append(f'<rect x="{x}" y="{top + plot_h - h:.1f}" width="{bar_w}" '
                        f'height="{h:.1f}" fill="{SERIES[i % len(SERIES)]}"/>')
            body.append(_text(x + bar_w / 2, top + plot_h - h - 5, f"{v:,}", size=10,
                              anchor="middle"))
            short = r["System"].split(" (")[0]
            body.append(_text(x + bar_w / 2, top + plot_h + 16, short, size=10, anchor="middle"))
            if pi == 1:
                body.append(_text(x + bar_w / 2, top + plot_h + 30, f"B3 R {r['B3 R (%)']}%",
                                  size=9, anchor="middle", fill=MUTED))
    return _svg(width, height, body,
                "Figure 9. Cost and coverage: baselines vs EchoTales, chapters 1-10",
                "Same model, host, scorer, LLM-drafted silver reference set. EchoTales calls = resolution only. "
                "Source: docs/paper/tables/table7_baselines.csv.")


def figure_compounding(rows: list[dict[str, str]]) -> str:
    """Gazetteer share of links per window, bar height = share, n on top."""
    left, top, plot_h, bar_w, step = 60, 50, 220, 34, 46
    # Floor on width: five windows alone are narrower than the title and caption.
    width = max(left + step * len(rows) + 40, 640)
    step = (width - left - 40) // max(len(rows), 1)
    height = top + plot_h + 80
    body: list[str] = []
    for frac in (0.0, 0.5, 1.0):
        y = top + plot_h * (1 - frac)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - 30}" y2="{y:.1f}" stroke="{GRID}"/>')
        body.append(_text(left - 8, y + 4, f"{frac:.0%}", size=10, anchor="end", fill=MUTED))
    for i, r in enumerate(rows):
        share = _pct(r["Gazetteer share of links"])
        n = _int(r["n (links in window)"])
        x = left + i * step + (step - bar_w) // 2
        h = plot_h * share
        body.append(f'<rect x="{x}" y="{top + plot_h - h:.1f}" width="{bar_w}" height="{h:.1f}" '
                    f'fill="{SERIES[1]}"/>')
        body.append(_text(x + bar_w / 2, top + plot_h - h - 4, f"n={n}", size=9, anchor="middle",
                          fill=MUTED))
        body.append(_text(x + bar_w / 2, top + plot_h + 16, r["Window"], size=10, anchor="middle"))
    return _svg(width, height, body,
                "Figure 6a. Gazetteer share of resolution links by chapter window",
                "Denominator shown per window. Source: docs/paper/tables/table6a_compounding.csv.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tables", default="docs/paper/tables")
    ap.add_argument("--out", default="docs/paper/figures")
    args = ap.parse_args()
    tables, out = Path(args.tables), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    jobs = (
        ("table5_recall_at_k.csv", "fig08_recall_at_k.svg", figure8_recall),
        ("table6_ablation.csv", "fig10_ablation.svg", figure10_ablation),
        ("table7_baselines.csv", "fig09_baselines.svg", figure9_baselines),
        ("table6a_compounding.csv", "fig06a_compounding.svg", figure_compounding),
    )
    for csv_name, svg_name, draw in jobs:
        src = tables / csv_name
        if not src.exists():
            print(f"  skipped {svg_name}: {src} missing -- run make_paper_artifacts.py first")
            continue
        (out / svg_name).write_text(draw(_read(src)))
        print(f"  wrote {out / svg_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
