"""Generate report tables and figure specifications from real artifacts.

`docs/status/STATUS.md` has carried "Paper artifacts: **None found** -- no figure/
diagram/table generation scripts exist" for the project's whole life. This is
that script.

**It plots nothing, deliberately.** `matplotlib` is not a declared dependency
of this repository (neither is `scipy` -- `coref_score.py` hand-writes a
Jonker-Volgenant assignment rather than pull it in), and adding a plotting
stack to emit six charts would be a worse trade than emitting the numbers that
feed them. Every table is written as **both** Markdown (paste into the report)
and CSV (feed to whatever plots), and every figure is written as a spec naming
its exact data source and columns.

**It invents nothing.** A figure whose data does not exist yet is emitted as a
TODO naming what would have to be measured first, never as an empty axis or a
placeholder number. That rule is why this file is mechanical rather than
hand-written: a hand-written table is where a plausible-looking number gets
typed in, and this project retracted a headline result for precisely that
(EVOLUTION 4.74).

Usage:
    python3 scripts/paper/make_paper_artifacts.py [--out docs/paper]
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

RESULTS = Path("data/eval/results")
COMPOUNDING = Path("data/eval/compounding")
VALIDATION = Path("data/eval/validation")
ABLATION = Path("data/eval/ablation")

SILVER_NOTE = (
    "Scored against the LLM-DRAFTED SILVER REFERENCE SET -- not human-annotated, "
    "no inter-annotator agreement. See docs/results/GOLD_DATASET_README.md."
)


@dataclass
class Table:
    number: str
    title: str
    headers: list[str]
    rows: list[list[str]]
    note: str = ""
    source: str = ""

    def to_markdown(self) -> str:
        out = [f"### Table {self.number} — {self.title}", ""]
        out.append("| " + " | ".join(self.headers) + " |")
        out.append("|" + "|".join("---" for _ in self.headers) + "|")
        for row in self.rows:
            out.append("| " + " | ".join(str(c) for c in row) + " |")
        if self.source:
            out += ["", f"*Source: {self.source}*"]
        if self.note:
            out += ["", f"*{self.note}*"]
        return "\n".join(out) + "\n"


#: Result records keep the database path that was true when they ran; the
#: 2026-09-27 restructure moved the databases (data/README.md). Tables print
#: where the file is now.
_MOVED_DBS = {
    "data/reverend-insanity.db": "data/db/reverend-insanity.db",
    "data/reruns/": "data/scratch/reruns/",
    "data/webview-working/": "data/db/",
    # The v1.1 build, promoted to the database of record on 2026-09-27 (the
    # scratch file itself no longer exists; CANONICAL_RUN.md section 0).
    "data/scratch/db/ri-v1.1.db": "data/db/reverend-insanity.db at v1.1; v1.2 mentions are identical",
}


def _is_canonical(path: str) -> bool:
    try:
        registry = json.loads(Path("data/canonical_dbs.json").read_text())["paths"]
    except (OSError, ValueError, KeyError):
        return False
    return _db(path) in registry


def _db(path: str) -> str:
    for old, new in _MOVED_DBS.items():
        if path == old or (old.endswith("/") and path.startswith(old)):
            return new + path[len(old):]
    return path


@dataclass
class Figure:
    number: str
    title: str
    kind: str  # "diagram" | "plot"
    status: str  # "DATA READY" | "RENDERED" | "RENDERED (private)" | "TODO"
    source: str = ""
    columns: list[str] = field(default_factory=list)
    blocked_on: str = ""

    def to_markdown(self) -> str:
        out = [
            f"### Figure {self.number} — {self.title}",
            "",
            f"- **Kind:** {self.kind}",
            f"- **Status:** {self.status}",
        ]
        if self.source:
            out.append(f"- **Data source:** `{self.source}`")
        if self.columns:
            out.append(f"- **Required columns:** {', '.join('`' + c + '`' for c in self.columns)}")
        if self.blocked_on:
            out.append(f"- **Blocked on:** {self.blocked_on}")
        return "\n".join(out) + "\n"


def _latest_metrics(gold_path: str) -> dict:
    """Newest persisted run over `gold_path` that actually carries silver metrics.

    Several early runs predate the silver tier and carry only escalation and
    linked_share, so "newest" alone would select a file with nothing in it.
    Filtered by gold file because "newest" also silently swapped Table 4 to the
    45-case hardcases run the first time reproduce_results.sh evaluated both
    files back to back (2026-09-25): coreference over 45 hard cases and over
    1,816 silver records are different measurements, not a refresh.
    """
    best: dict = {}
    for path in sorted(RESULTS.glob("*/metrics.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        # Only a run on a database of record: a scratch experiment with the
        # same numbers once became Table 4's cited source (2026-09-27).
        if ("silver" in data.get("metrics", {}) and data.get("gold_path") == gold_path
                and _is_canonical(data.get("database", ""))):
            best = data
    return best


def table_dataset() -> Table:
    rows = []
    for path in sorted(VALIDATION.glob("*.json")):
        try:
            d = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        by = {f["check"]: f for f in d["findings"]}
        triv = by.get("surface-triviality", {}).get("detail", "")
        share = triv.split("%")[0] if "%" in triv else "?"
        prov = by.get("provenance", {}).get("detail", "")
        rows.append(
            [
                f"`{Path(d['path']).name}`",
                f"{d['records']:,}",
                prov.split("silver=")[1].split()[0] if "silver=" in prov else "?",
                prov.split("circular=")[1].split()[0] if "circular=" in prov else "?",
                f"{share}%",
                "PASS" if d["ok"] else "FAIL",
            ]
        )
    return Table(
        "2",
        "Dataset characteristics and structural validation",
        ["File", "Records", "Silver", "Circular", "Surface-trivial", "Validator"],
        rows,
        note="Surface-trivial = share of mentions whose identity is recoverable "
        "from the surface string alone. A file near 100% cannot measure an "
        "identity resolver; see docs/results/EVAL_RETRIEVER.md section 1.",
        source="data/eval/validation/*.json (echotales eval --validate-gold)",
    )


def table_recall() -> Table | None:
    """Recall@K by alias type under the *production* query context.

    Read from `recall_by_category.json` rather than the CLI's metrics.json:
    the CLI queries with the gold record's ~70-char snippet, the resolver
    with `_context_for`. The paper reports the context the system actually
    uses, and the snippet figure only as a footnote (finalization pass).
    """
    path = Path("data/eval/recall_by_category.json")
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    prod = d.get("recall_by_alias_type", {}).get("production")
    snip = d.get("recall_by_alias_type", {}).get("snippet", {}).get("ALL", {})
    if not prod:
        return None

    def row(name: str, r: dict) -> list[str]:
        return [name, str(r["n"])] + [f"{r[f'@{k}'] * 100:.1f}%" for k in (1, 5, 10, 20)]

    rows = [row("**Overall**", prod["ALL"])] + [row(a, r) for a, r in prod.items() if a != "ALL"]
    return Table(
        "5",
        "Retriever Recall@K by alias type, production query context",
        ["Alias type", "n", "@1", "@5", "@10", "@20"],
        rows,
        note="LLM-DRAFTED SILVER REFERENCE SET (hardcases file), not human-annotated, no IAA. "
        "The reference span is handed to the retriever, so this measures retrieval, not "
        "detection. n is small for the hard types: one case moves TRANSFERABLE_TITLE "
        f"about 11 points and RELATIONAL_DEICTIC 25. With the CLI's snippet context "
        f"instead, overall @10 is {snip.get('@10', 0) * 100:.1f}%.",
        source=f"{path} (scripts/eval/recall_by_category.py, db: {_db(d.get('db', '?'))})",
    )


def table_coref(metrics: dict) -> Table | None:
    silver = metrics.get("metrics", {}).get("silver", {})
    rows = []
    for key, label in (
        ("muc", "MUC"),
        ("b3", "B3"),
        ("ceafe", "CEAF-e"),
        ("conll", "CoNLL"),
        ("b3_project_variant", "B3 (project variant)"),
    ):
        m = silver.get(key)
        if not m:
            continue
        rows.append(
            [label, f"{m['precision'] * 100:.1f}", f"{m['recall'] * 100:.1f}",
             f"{m['f1'] * 100:.1f}"]
        )
    if not rows:
        return None
    return Table(
        "4",
        "Coreference metrics, current run",
        ["Metric", "P (%)", "R (%)", "F1 (%)"],
        rows,
        note=SILVER_NOTE + " B3/MUC are TAUTOLOGICAL on a surface-trivial reference set "
        "and must not be quoted as accuracy; CEAF-e is entity-based and is the "
        "discriminative one here.",
        source=f"data/eval/results/{metrics.get('run_id', '?')}/metrics.json (reference: {metrics.get('gold_path', '?')}, db: {_db(metrics.get('database', '?'))})",
    )


def table_compounding() -> Table | None:
    path = COMPOUNDING / "reverend-insanity.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    rows = [[f"w{w}", f"{rate * 100:.1f}%", str(n)] for w, rate, n in d.get("resolution", [])]
    if not rows:
        return None
    return Table(
        "6a",
        f"Gazetteer compounding by window (size {d.get('window_size', '?')})",
        ["Window", "Gazetteer share of links", "n (links in window)"],
        rows,
        note="Reported WITH the denominator on purpose: a rate without its n invites "
        "reading an early window of four links at 100% as evidence.",
        source="data/eval/compounding/reverend-insanity.json",
    )


def table_baselines() -> Table | None:
    path = Path("data/eval/baseline_comparison.json")
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    def cell(v: object, fmt: str = "{:,}") -> str:
        return "—" if v is None else fmt.format(v)

    rows = [
        [s["name"], cell(s["calls"]), cell(s["prompt_tokens"]), cell(s["wall_seconds"], "{:,.0f} s"),
         cell(s["mentions"]), f"{s['b3_precision'] * 100:.1f}", f"{s['b3_recall'] * 100:.1f}"]
        for s in d.get("systems", [])
    ]
    if not rows:
        return None
    lo, hi = d.get("chapters", ["?", "?"])
    return Table(
        "7",
        f"Baselines vs EchoTales, chapters {lo}-{hi} ({d.get('gold_mentions', '?')} silver mentions)",
        ["System", "LLM calls", "Prompt tokens", "Wall time", "Mentions", "B3 P (%)", "B3 R (%)"],
        rows,
        note=SILVER_NOTE + " The reference set for this range is surface-trivial, so B3 recall here "
        "measures extraction coverage, not coreference quality. EchoTales' calls column counts "
        "resolution only; its upstream NER calls are excluded.",
        source=f"{path} (scripts/eval/baseline_comparison.py)",
    )


def table_ablation() -> Table | None:
    path = ABLATION / "reverend-insanity.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    rows = [
        [r["condition"], f"{r['pairs']:,}", f"{r['force_links']:,}", f"{r['blocks']:,}",
         f"{r['scored']:,}", str(r["links_above_threshold"])]
        for r in d.get("rows", [])
    ]
    if not rows:
        return None
    return Table(
        "6",
        f"Ablations over {d.get('cached_evidence_vectors', 0):,} cached evidence vectors",
        ["Condition", "Pairs", "Force-link", "Blocked", "Reached scorer", "Scorer would link"],
        rows,
        note="Re-scores cached evidence; it does not re-run resolution. 'Scorer would link' "
        "is 0 under every condition because the scorer's output is capped below its "
        "threshold (docs/results/SCORER_DIAGNOSIS.md), so this table measures the pre-filters. "
        "Not answerable from the cache: " + ", ".join(sorted(d.get("requires_reresolve", {}))) + ".",
        source=f"{path} (echotales ablate --out, db: {_db(d.get('db', '?'))})",
    )


def figures() -> list[Figure]:
    return [
        Figure("1", "Overall EchoTales architecture", "diagram", "RENDERED",
               source="docs/paper/figures/fig01_architecture.svg (scripts/paper/draw_diagrams.py)"),
        Figure("2", "Three-axis temporal model", "diagram", "RENDERED",
               source="docs/paper/figures/fig02_temporal_axes.svg (scripts/paper/draw_diagrams.py)",
               blocked_on="No fact is written to a non-MAIN timeline; that axis is drawn dashed, as designed."),
        Figure("3", "Self/Persona temporal binding", "diagram", "RENDERED",
               source="docs/paper/figures/fig03_self_persona.svg (body intervals read from the canonical database)",
               blocked_on="Concurrency is unit-tests-only and is drawn dashed."),
        Figure("4", "Incremental entity-resolution pipeline", "diagram", "RENDERED",
               source="docs/paper/figures/fig04_resolution.svg (gates read from resolve/score.py; counts from data/eval/ablation)"),
        Figure("5", "state_of() query flow, observer and knowledge time", "diagram", "RENDERED (private)",
               source="docs/private/paper/figures/fig05_state_of.svg -- embargoed with the patent packet until the IPR decision"),
        Figure("6", "Graph state to modality render plan", "diagram", "RENDERED (private)",
               source="docs/private/paper/figures/fig06_render_plan.svg -- embargoed; the audio path is drawn as not consuming state"),
        Figure("7", "Evaluation pipeline and provenance tiers", "diagram", "RENDERED",
               source="docs/paper/figures/fig07_evaluation.svg (tiers and checks read from eval/gold.py, eval/validate_gold.py)"),
        Figure("8", "Retriever Recall@K by alias type", "plot", "RENDERED",
               source="docs/paper/figures/fig08_recall_at_k.svg (scripts/paper/plot_paper_figures.py "
                      "from docs/paper/tables/table5_recall_at_k.csv)",
               columns=["alias_type", "n", "k", "recall"]),
        Figure("9", "Baseline comparison", "plot", "RENDERED",
               source="docs/paper/figures/fig09_baselines.svg (scripts/paper/plot_paper_figures.py "
                      "from docs/paper/tables/table7_baselines.csv)",
               columns=["System", "LLM calls", "Mentions", "B3 R (%)"],
               blocked_on="Plot calls and mentions, not B3 as accuracy -- the reference set "
                          "for ch1-10 is surface-trivial."),
        Figure("10", "Ablation results", "plot", "RENDERED",
               source="docs/paper/figures/fig10_ablation.svg (scripts/paper/plot_paper_figures.py "
                      "from docs/paper/tables/table6_ablation.csv)",
               columns=["condition", "force_links", "reached_scorer", "scorer_would_link"]),
        Figure("11", "Human review / escalation rate", "plot", "TODO",
               columns=["stage", "calls", "escalations", "rate"],
               blocked_on="Escalation is 0 of 660 calls and deferrals are 2 of 1,532 "
                          "groups. A bar chart of zeros is not a figure -- report it as a "
                          "sentence unless a corpus produces non-zero escalation."),
        Figure("12", "Observer contrast: one scene, two observers", "image", "RENDERED",
               source="data/novels/RI/experiments/observer-contrast/reader/, data/novels/RI/experiments/observer-contrast/nonwitness/; "
                      "docs/results/OBSERVER_CONTRAST_VALIDATION.md",
               blocked_on="Five blocks, one chapter, NoobAI XL on the local card. It shows "
                          "the cast changing with the observer (2boys vs 1boy solo); it "
                          "cannot show two depictions of one character, which needs a "
                          "sustained disguise the corpus does not contain."),
    ]


def write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/paper")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "tables").mkdir(parents=True, exist_ok=True)

    # Coreference is scored over the full silver file; recall@K over the
    # hardcases file, the only one with non-RIGID_NAME alias types (on the full
    # file every case is RIGID_NAME and recall is 99.9% by construction).
    coref_metrics = _latest_metrics("data/gold/reverend-insanity.jsonl")
    built: list[Table] = []
    for table, stem in (
        (table_dataset(), "table2_dataset"),
        (table_coref(coref_metrics), "table4_coref"),
        (table_recall(), "table5_recall_at_k"),
        (table_ablation(), "table6_ablation"),
        (table_baselines(), "table7_baselines"),
        (table_compounding(), "table6a_compounding"),
    ):
        if table is None:
            continue
        built.append(table)
        write_csv(out / "tables" / f"{stem}.csv", table.headers, table.rows)

    md = [
        "# Report tables — generated, do not hand-edit",
        "",
        "Regenerate with `python3 scripts/paper/make_paper_artifacts.py`.",
        "Every number traces to a file under `data/eval/`; nothing here is typed by hand.",
        "",
    ]
    for table in built:
        md += [table.to_markdown(), ""]
    (out / "TABLES.md").write_text("\n".join(md), encoding="utf-8")

    fmd = [
        "# Report figures — specifications",
        "",
        "Generated by `scripts/paper/make_paper_artifacts.py`. A figure whose data does",
        "not exist is a TODO naming what must be measured, never a placeholder.",
        "",
        "`matplotlib` is not a declared dependency of this repository; the tables",
        "ship as CSV so any plotting tool can consume them.",
        "",
    ]
    for fig in figures():
        fmd.append(fig.to_markdown())
    (out / "FIGURES.md").write_text("\n".join(fmd), encoding="utf-8")

    print(f"wrote {len(built)} table(s) -> {out / 'TABLES.md'} (+ CSV)")
    print(f"wrote {len(figures())} figure spec(s) -> {out / 'FIGURES.md'}")
    ready = sum(1 for f in figures() if f.status.startswith(("DATA READY", "RENDERED")))
    todo = sum(1 for f in figures() if f.status == "TODO")
    print(
        f"  figures: {ready} data-ready, {todo} TODO, "
        f"{len(figures()) - ready - todo} hand-drawn diagrams"
    )
    for label, found in (("coreference", coref_metrics),):
        if not found:
            print(
                f"  WARNING: no persisted {label} run carried silver metrics -- run "
                "`echotales eval --novel <id> --gold <file>` first"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
