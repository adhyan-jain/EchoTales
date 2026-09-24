"""Generate report tables and figure specifications from real artifacts.

`docs/STATUS.md` has carried "Paper artifacts: **None found** -- no figure/
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
    python3 scripts/make_paper_artifacts.py [--out docs/paper]
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
    "Scored against an LLM-derived SILVER reference set, not human gold, with "
    "no inter-annotator agreement. See docs/GOLD_DATASET_README.md."
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


@dataclass
class Figure:
    number: str
    title: str
    kind: str  # "diagram" | "plot"
    status: str  # "DATA READY" | "RENDERED" | "TODO" | "HAND-DRAWN"
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
        if "silver" in data.get("metrics", {}) and data.get("gold_path") == gold_path:
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
        "identity resolver; see docs/EVAL_RETRIEVER.md section 1.",
        source="data/eval/validation/*.json (echotales eval --validate-gold)",
    )


def table_recall(metrics: dict) -> Table | None:
    rk = metrics.get("metrics", {}).get("silver", {}).get("recall_at_k")
    if not rk or "by_alias_type" not in rk:
        return None
    ns = rk.get("by_alias_type_n", {})
    rows = []
    overall = rk.get("overall", {})
    if overall:
        rows.append(
            ["**Overall**", str(rk.get("cases", "?"))]
            + [f"{overall.get(k, 0) * 100:.1f}%" for k in ("1", "5", "10", "20")]
        )
    for alias, at_k in sorted(rk["by_alias_type"].items()):
        rows.append(
            [alias, str(ns.get(alias, "?"))]
            + [f"{at_k.get(k, 0) * 100:.1f}%" for k in ("1", "5", "10", "20")]
        )
    return Table(
        "5",
        "Retriever Recall@K by alias type",
        ["Alias type", "n", "@1", "@5", "@10", "@20"],
        rows,
        note=SILVER_NOTE + " n is small for the hard alias types; single cases move "
        "TRANSFERABLE_TITLE by roughly 11 points and RELATIONAL_DEICTIC by 25.",
        source=f"data/eval/results/{metrics.get('run_id', '?')}/metrics.json (gold: {metrics.get('gold_path', '?')}, db: {metrics.get('database', '?')})",
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
        note=SILVER_NOTE + " B3/MUC are TAUTOLOGICAL on a surface-trivial gold set "
        "and must not be quoted as accuracy; CEAF-e is entity-based and is the "
        "discriminative one here.",
        source=f"data/eval/results/{metrics.get('run_id', '?')}/metrics.json (gold: {metrics.get('gold_path', '?')}, db: {metrics.get('database', '?')})",
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
        "threshold (docs/SCORER_DIAGNOSIS.md), so this table measures the pre-filters. "
        "Not answerable from the cache: " + ", ".join(sorted(d.get("requires_reresolve", {}))) + ".",
        source=f"{path} (echotales ablate --out, db: {d.get('db', '?')})",
    )


def figures() -> list[Figure]:
    return [
        Figure("1", "Overall EchoTales architecture", "diagram", "HAND-DRAWN",
               source="architecture.md sections 2, 4, 7, 8"),
        Figure("2", "Three-axis temporal model", "diagram", "HAND-DRAWN",
               source="architecture.md section 2",
               blocked_on="No fact is ever written to a non-MAIN timeline, so the "
                          "story-time axis must be drawn as designed, not as measured."),
        Figure("3", "Self/Persona temporal binding", "diagram", "HAND-DRAWN",
               source="core/models.py SelfPersonaBinding; real case self1 -> body1/body2",
               blocked_on="Concurrency is unit-tests-only; draw the sequential case as "
                          "real and any concurrent case as designed."),
        Figure("4", "Incremental entity-resolution pipeline", "diagram", "HAND-DRAWN",
               source="resolve/runner.py, resolve/score.py PREFILTER_GATES"),
        Figure("5", "state_of() query flow, observer and knowledge time", "diagram",
               "HAND-DRAWN", source="docs/STATE_OF_VALIDATION.md sections 2 and 3"),
        Figure("6", "Graph state to modality render plan", "diagram", "HAND-DRAWN",
               source="render/plan_builder.py::build_render_plan",
               blocked_on="The audio half does NOT consume state_of. Draw the visual path "
                          "as real and the audio path as absent, or the figure asserts a "
                          "compiler that does not exist."),
        Figure("7", "Evaluation pipeline and provenance tiers", "diagram", "HAND-DRAWN",
               source="eval/gold.py tiers; eval/validate_gold.py checks"),
        Figure("8", "Retriever Recall@K by alias type", "plot", "DATA READY",
               source="docs/paper/tables/table5_recall_at_k.csv",
               columns=["alias_type", "n", "k", "recall"]),
        Figure("9", "Baseline comparison", "plot", "DATA READY",
               source="docs/BASELINES.md section 4",
               columns=["system", "calls", "prompt_tokens", "wall_seconds",
                        "mentions_found", "b3_recall"],
               blocked_on="Both baselines ran (ch1-10); the values live only in "
                          "BASELINES.md, not a persisted file, and EchoTales has no "
                          "comparable prompt-token or wall-time figure for that range. "
                          "Plot calls and mentions found; do not plot B3 as accuracy -- "
                          "the gold for that range is surface-trivial."),
        Figure("10", "Ablation results", "plot", "DATA READY",
               source="docs/paper/tables/table6_ablation.csv",
               columns=["condition", "force_links", "reached_scorer", "scorer_would_link"]),
        Figure("11", "Human review / escalation rate", "plot", "TODO",
               columns=["stage", "calls", "escalations", "rate"],
               blocked_on="Escalation is 0 of 660 calls and deferrals are 2 of 1,532 "
                          "groups. A bar chart of zeros is not a figure -- report it as a "
                          "sentence unless a corpus produces non-zero escalation."),
        Figure("12", "Observer contrast: one scene, two observers", "image", "RENDERED",
               source="data/RI/panels-obs-reader/, data/RI/panels-obs-nonwitness/; "
                      "docs/OBSERVER_CONTRAST_VALIDATION.md",
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
    recall_metrics = _latest_metrics("data/gold/reverend-insanity-hardcases.jsonl")
    built: list[Table] = []
    for table, stem in (
        (table_dataset(), "table2_dataset"),
        (table_coref(coref_metrics), "table4_coref"),
        (table_recall(recall_metrics), "table5_recall_at_k"),
        (table_ablation(), "table6_ablation"),
        (table_compounding(), "table6a_compounding"),
    ):
        if table is None:
            continue
        built.append(table)
        write_csv(out / "tables" / f"{stem}.csv", table.headers, table.rows)

    md = [
        "# Report tables — generated, do not hand-edit",
        "",
        "Regenerate with `python3 scripts/make_paper_artifacts.py`.",
        "Every number traces to a file under `data/eval/`; nothing here is typed by hand.",
        "",
    ]
    for table in built:
        md += [table.to_markdown(), ""]
    (out / "TABLES.md").write_text("\n".join(md), encoding="utf-8")

    fmd = [
        "# Report figures — specifications",
        "",
        "Generated by `scripts/make_paper_artifacts.py`. A figure whose data does",
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
    ready = sum(1 for f in figures() if f.status in ("DATA READY", "RENDERED"))
    todo = sum(1 for f in figures() if f.status == "TODO")
    print(
        f"  figures: {ready} data-ready, {todo} TODO, "
        f"{len(figures()) - ready - todo} hand-drawn diagrams"
    )
    for label, found in (("coreference", coref_metrics), ("recall@K", recall_metrics)):
        if not found:
            print(
                f"  WARNING: no persisted {label} run carried silver metrics -- run "
                "`echotales eval --novel <id> --gold <file>` first"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
