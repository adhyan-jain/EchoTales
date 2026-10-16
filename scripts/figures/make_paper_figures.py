"""make_paper_figures.py: Generate paper figures for reader-faithfulness research.

Reads (read-only):
  - data/eval/chimera/pd_final_pooled.json
  - data/eval/chimera/pd_dose_response.json
  - data/eval/chimera/remote/*/analysis_*.json
  - data/eval/chimera/confirm/e2/analysis.json

Writes PNG+SVG to docs/paper/figures/rf/:
  (a) leakage gap per model with 95% CI (fig_leakage_gap_per_model)
  (b) gap vs book-fame dose-response (fig_dose_response)
  (c) original vs renamed vs pseudonym bars (fig_cue_preserving_bars)
  (d) unseen-text control (fig_unseen_text_control)

Every figure labels its data provenance ("text-derived oracle; model-selected events").
If a file is missing, the corresponding figure is skipped with a clear explanation.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROVENANCE_LABEL = "Data provenance: text-derived oracle; model-selected events"
OUT_DIR = Path("docs/paper/figures/rf")

# Style palette
COLORS = {
    "luna": "#6a1b9a",      # deep purple (reference model)
    "local": "#1565c0",     # deep blue (local models)
    "remote": "#00838f",    # teal (remote open-weight models)
    "pooled": "#37474f",    # slate gray (pooled)
    "armA": "#2e7d32",      # green (original names)
    "armB": "#c62828",      # red (letter cipher)
    "armB2": "#e65100",     # amber (second cipher)
    "armB3": "#f57c00",     # orange (pseudonyms)
    "neutral": "#546e7a",
    "grid": "#eceff1",
    "text": "#212121",
}

plt.rcParams.update({
    "font.size": 9,
    "axes.labelsize": 9.5,
    "axes.titlesize": 10.5,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.family": "DejaVu Sans",
    "figure.titlesize": 11,
})


def pct(x: float | None) -> float:
    return (x or 0.0) * 100.0


def add_provenance(ax, text: str = PROVENANCE_LABEL, y: float = -0.15):
    """Adds standard data provenance note below the axis."""
    ax.text(
        0.5, y, text,
        transform=ax.transAxes, ha="center", va="top",
        fontsize=7.5, fontstyle="italic", color="#555555"
    )


# -----------------------------------------------------------------------------
# Figure (a): Leakage gap per model with 95% CI
# -----------------------------------------------------------------------------
def make_figure_a():
    """Figure (a): Leakage gap per model with 95% CI."""
    pooled_file = Path("data/eval/chimera/pd_final_pooled.json")
    remote_pattern = "data/eval/chimera/remote/*/analysis_*.json"
    remote_files = sorted(glob.glob(remote_pattern))

    if not pooled_file.exists():
        print(f"Skipping Figure (a): missing {pooled_file}")
        return

    pooled_data = json.loads(pooled_file.read_text())

    # Collect entries
    # 1. Local models on v6 (fresh books)
    v6_models = pooled_data.get("v6_per_model", {})

    # 2. Remote models across datasets
    remote_entries = []
    for rf in remote_files:
        try:
            d = json.loads(Path(rf).read_text())
            cluster = d.get("cluster", {})
            gap = cluster.get("gap_A_minus_B")
            ci = cluster.get("gap_A_minus_B_ci")
            if gap is not None and ci is not None:
                remote_entries.append({
                    "model": d.get("model", "unknown"),
                    "set": d.get("set", "unknown"),
                    "gap": gap,
                    "ci": ci,
                    "events": cluster.get("events", 0),
                })
        except Exception as e:
            print(f"Warning: error reading {rf}: {e}")

    # Build rows for a comprehensive forest plot
    rows = []

    # Section 1: Pooled benchmarks
    valid_all = pooled_data.get("valid_pool", {}).get("all_v2_v3_v6", {})
    if valid_all:
        rows.append({
            "label": "Valid Local Pool (all 38 events)",
            "gap": valid_all["gap_A_minus_B"],
            "ci": valid_all["ci"],
            "color": COLORS["pooled"],
            "events": valid_all.get("events", 38),
        })

    luna_all = pooled_data.get("luna_only", {}).get("all_v2_v3_v6", {})
    if luna_all:
        rows.append({
            "label": "Reference: gpt-5.6-luna (all 38 events)",
            "gap": luna_all["gap_A_minus_B"],
            "ci": luna_all["ci"],
            "color": COLORS["luna"],
            "events": luna_all.get("events", 38),
        })

    # Section 2: Remote 24B-32B models on v2, v3, v6
    remote_name_map = {
        "mistral24": "Mistral-Large-24B",
        "olmo32b": "OLMo-2-32B",
        "qwen32b": "Qwen2.5-32B",
    }
    for entry in remote_entries:
        if entry["set"] in ("v2", "v3", "v6"):
            display_name = remote_name_map.get(entry["model"], entry["model"])
            rows.append({
                "label": f"{display_name} ({entry['set']}, {entry['events']} ev)",
                "gap": entry["gap"],
                "ci": entry["ci"],
                "color": COLORS["remote"],
                "events": entry["events"],
            })

    # Section 3: Local models (v6 fresh books)
    for model_name, info in sorted(v6_models.items()):
        cluster = info.get("cluster", {})
        gap = cluster.get("gap_A_minus_B")
        ci = cluster.get("ci")
        if gap is not None and ci is not None:
            col = COLORS["luna"] if "luna" in model_name else COLORS["local"]
            rows.append({
                "label": f"{model_name} (v6, 7 ev)",
                "gap": gap,
                "ci": ci,
                "color": col,
                "events": cluster.get("events", 7),
            })

    fig, ax = plt.subplots(figsize=(8.5, 7.0))

    for i, r in enumerate(rows[::-1]):
        gap_pts = pct(r["gap"])
        ci_lo = pct(r["ci"][0])
        ci_hi = pct(r["ci"][1])
        ax.plot([ci_lo, ci_hi], [i, i], color=r["color"], lw=2.0, alpha=0.9)
        ax.plot([ci_lo, ci_lo], [i - 0.15, i + 0.15], color=r["color"], lw=1.5)
        ax.plot([ci_hi, ci_hi], [i - 0.15, i + 0.15], color=r["color"], lw=1.5)
        ax.plot([gap_pts], [i], "o", color=r["color"], ms=5.5)
        ax.text(
            max(ci_hi + 1.2, gap_pts + 1.5), i,
            f"{gap_pts:+.1f} pts [{ci_lo:.1f}, {ci_hi:.1f}]",
            va="center", fontsize=7.2, color="#333333"
        )

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["label"] for r in rows[::-1]], fontsize=8)
    ax.axvline(0, color="k", lw=0.9, ls="-", alpha=0.7)
    ax.axvline(10, color="gray", lw=0.6, ls=":", alpha=0.7)
    ax.set_xlabel("Leakage Gap A − B (% points; 95% event-cluster CI)")
    ax.set_title("Figure 1. Leakage Gap per Model with 95% CI (Original vs. Renamed)")
    ax.grid(axis="x", ls="--", color=COLORS["grid"], alpha=0.8)
    ax.set_xlim(-48, 65)

    add_provenance(ax, PROVENANCE_LABEL, y=-0.12)
    fig.tight_layout()

    out_png = OUT_DIR / "fig_leakage_gap_per_model.png"
    out_svg = OUT_DIR / "fig_leakage_gap_per_model.svg"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote Figure (a) to {out_png} and {out_svg}")


# -----------------------------------------------------------------------------
# Figure (b): Gap vs book-fame dose-response
# -----------------------------------------------------------------------------
def make_figure_b():
    """Figure (b): Gap vs book-fame dose-response."""
    dose_file = Path("data/eval/chimera/pd_dose_response.json")
    if not dose_file.exists():
        print(f"Skipping Figure (b): missing {dose_file}")
        return

    dose_data = json.loads(dose_file.read_text())
    luna = dose_data.get("luna_gap_vs_local_recognition", {})
    local_pool = dose_data.get("valid_local_pool_gap_vs_local_recognition", {})

    counts = sorted(int(k) for k in luna.get("mean_gap_by_recognition_count", {}).keys())
    if not counts:
        print("Skipping Figure (b): no recognition counts found.")
        return

    luna_gaps = [pct(luna["mean_gap_by_recognition_count"][str(c)]) for c in counts]
    local_gaps = [pct(local_pool["mean_gap_by_recognition_count"][str(c)]) for c in counts]
    n_events = [luna["events_per_count"][str(c)] for c in counts]

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    w = 0.36
    xs = counts

    ax.bar(
        [x - w / 2 for x in xs],
        luna_gaps,
        width=w,
        color=COLORS["luna"],
        alpha=0.9,
        label=f"Reference (gpt-5.6-luna): Spearman ρ = {luna.get('spearman', 0):+.2f} (p = {luna.get('perm_p', 0):.3f})"
    )
    ax.bar(
        [x + w / 2 for x in xs],
        local_gaps,
        width=w,
        color=COLORS["local"],
        alpha=0.9,
        label=f"Valid local pool: Spearman ρ = {local_pool.get('spearman', 0):+.2f} (p = {local_pool.get('perm_p', 0):.5f})"
    )

    for x, n in zip(xs, n_events):
        ax.text(x, -8.0, f"n={n}", ha="center", va="top", fontsize=7.5, color="#555555")

    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{c} / 5 models" for c in counts])
    ax.set_xlabel("Book Familiarity: Number of local models recognising book in title probe")
    ax.set_ylabel("Mean Leakage Gap A − B (% points)")
    ax.set_ylim(-12, 55)
    ax.set_title("Figure 2. Parametric Leakage Gap vs. Book Familiarity (Dose-Response)")
    ax.legend(loc="upper left", frameon=True, framealpha=0.9)
    ax.grid(axis="y", ls="--", color=COLORS["grid"], alpha=0.8)

    add_provenance(ax, PROVENANCE_LABEL, y=-0.20)
    fig.tight_layout()

    out_png = OUT_DIR / "fig_dose_response.png"
    out_svg = OUT_DIR / "fig_dose_response.svg"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote Figure (b) to {out_png} and {out_svg}")


# -----------------------------------------------------------------------------
# Figure (c): Original vs renamed vs pseudonym bars
# -----------------------------------------------------------------------------
def make_figure_c():
    """Figure (c): Original vs renamed vs pseudonym bars (A vs B vs B3)."""
    pooled_file = Path("data/eval/chimera/pd_final_pooled.json")
    remote_v6_files = sorted(glob.glob("data/eval/chimera/remote/v6/analysis_*.json"))

    if not pooled_file.exists():
        print(f"Skipping Figure (c): missing {pooled_file}")
        return

    pooled_data = json.loads(pooled_file.read_text())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.2))

    # Subplot 1: Plain control accuracy across arms
    models = []
    acc_A, acc_B, acc_B3 = [], [], []

    for rf in remote_v6_files:
        try:
            d = json.loads(Path(rf).read_text())
            ctrl = d.get("ctrl_acc", {})
            if "A" in ctrl and "B" in ctrl and "B3" in ctrl:
                m_name = d.get("model", "unknown")
                models.append(m_name)
                acc_A.append(pct(ctrl["A"]))
                acc_B.append(pct(ctrl["B"]))
                acc_B3.append(pct(ctrl["B3"]))
        except Exception as e:
            print(f"Warning reading {rf}: {e}")

    if models:
        xs = range(len(models))
        w = 0.25
        ax1.bar([x - w for x in xs], acc_A, width=w, color=COLORS["armA"], label="Arm A (original)")
        ax1.bar(xs, acc_B, width=w, color=COLORS["armB"], label="Arm B (cipher)")
        ax1.bar([x + w for x in xs], acc_B3, width=w, color=COLORS["armB3"], label="Arm B3 (pseudonyms)")
        ax1.set_xticks(list(xs))
        ax1.set_xticklabels(models)
        ax1.set_ylabel("Plain-Control Accuracy (%)")
        ax1.set_ylim(65, 103)
        ax1.set_title("(a) Pseudonyms restore comprehension")
        ax1.legend(loc="lower left", fontsize=7.5)
        ax1.grid(axis="y", ls="--", color=COLORS["grid"], alpha=0.8)
    else:
        ax1.text(0.5, 0.5, "No v6 control accuracy data available", ha="center")

    # Subplot 2: Leakage gap under Cipher (A-B) vs Pseudonym (A-B3)
    gap_rows = []
    vp = pooled_data.get("valid_pool", {}).get("all_v2_v3_v6", {})
    if vp:
        gap_rows.append({
            "name": "Valid Local Pool\n(38 events)",
            "gap_B": pct(vp["gap_A_minus_B"]),
            "ci_B": [pct(vp["ci"][0]), pct(vp["ci"][1])],
            "gap_B3": pct(vp["gap_A_minus_B3"]),
            "ci_B3": [pct(vp["ci_B3"][0]), pct(vp["ci_B3"][1])],
        })

    luna_all = pooled_data.get("luna_only", {}).get("all_v2_v3_v6", {})
    if luna_all:
        gap_rows.append({
            "name": "Reference Luna\n(38 events)",
            "gap_B": pct(luna_all["gap_A_minus_B"]),
            "ci_B": [pct(luna_all["ci"][0]), pct(luna_all["ci"][1])],
            "gap_B3": pct(luna_all["gap_A_minus_B3"]),
            "ci_B3": [pct(luna_all["ci_B3"][0]), pct(luna_all["ci_B3"][1])],
        })

    xs2 = range(len(gap_rows))
    w2 = 0.32
    for i, gr in enumerate(gap_rows):
        ax2.bar(i - w2 / 2, gr["gap_B"], width=w2, color=COLORS["armB"], label="A − B (cipher)" if i == 0 else "")
        ax2.plot([i - w2 / 2, i - w2 / 2], gr["ci_B"], color="k", lw=1.3)
        ax2.bar(i + w2 / 2, gr["gap_B3"], width=w2, color=COLORS["armB3"], label="A − B3 (pseudonyms)" if i == 0 else "")
        ax2.plot([i + w2 / 2, i + w2 / 2], gr["ci_B3"], color="k", lw=1.3)

    ax2.axhline(0, color="k", lw=0.8)
    ax2.set_xticks(list(xs2))
    ax2.set_xticklabels([gr["name"] for gr in gap_rows])
    ax2.set_ylabel("Leakage Gap (% points; 95% CI)")
    ax2.set_ylim(-5, 45)
    ax2.set_title("(b) Leakage persists under pseudonyms")
    ax2.legend(loc="upper left", fontsize=7.5)
    ax2.grid(axis="y", ls="--", color=COLORS["grid"], alpha=0.8)

    fig.suptitle("Figure 3. Cue-Preserving Control: Comprehension vs. Leakage Persistence", y=0.98)
    add_provenance(ax1, PROVENANCE_LABEL, y=-0.22)
    add_provenance(ax2, PROVENANCE_LABEL, y=-0.22)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))

    out_png = OUT_DIR / "fig_cue_preserving_bars.png"
    out_svg = OUT_DIR / "fig_cue_preserving_bars.svg"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote Figure (c) to {out_png} and {out_svg}")


# -----------------------------------------------------------------------------
# Figure (d): Unseen-text control
# -----------------------------------------------------------------------------
def make_figure_d():
    """Figure (d): Unseen-text control (E2 synthetic stories without prior memory)."""
    e2_file = Path("data/eval/chimera/confirm/e2/analysis.json")
    if not e2_file.exists():
        print(f"Skipping Figure (d): missing {e2_file}")
        return

    e2_data = json.loads(e2_file.read_text())
    per_model = e2_data.get("per_model", {})
    qwen = per_model.get("qwen32b", {})

    if not qwen:
        print("Skipping Figure (d): qwen32b results not found in confirm/e2/analysis.json")
        return

    ctrl_acc = qwen.get("ctrl_acc", {})
    prim = qwen.get("primary_test", {})

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 4.0))

    # Panel (a): Plain control accuracy on unseen text
    arms = ["A", "B", "B2", "B3"]
    labels = ["A\n(Original)", "B\n(Cipher 1)", "B2\n(Cipher 2)", "B3\n(Pseudonyms)"]
    accs = [pct(ctrl_acc.get(a)) for a in arms]
    bar_cols = [COLORS["armA"], COLORS["armB"], COLORS["armB2"], COLORS["armB3"]]

    ax1.bar(range(len(arms)), accs, width=0.45, color=bar_cols, alpha=0.9)
    for i, v in enumerate(accs):
        ax1.text(i, v + 1.0, f"{v:.1f}%", ha="center", fontsize=8)
    ax1.set_xticks(range(len(arms)))
    ax1.set_xticklabels(labels)
    ax1.set_ylabel("Comprehension Accuracy (%)")
    ax1.set_ylim(60, 105)
    ax1.set_title("(a) Comprehension on Unseen Text (17 events)")
    ax1.grid(axis="y", ls="--", color=COLORS["grid"], alpha=0.8)

    # Panel (b): Leakage gap on unseen text vs zero
    gap_B = pct(prim.get("gap_A_minus_B", 0))
    ci_B = [pct(prim.get("ci", [0, 0])[0]), pct(prim.get("ci", [0, 0])[1])]
    gap_B3 = pct(prim.get("gap_A_minus_B3", 0))
    ci_B3 = [pct(prim.get("ci_B3", [0, 0])[0]), pct(prim.get("ci_B3", [0, 0])[1])]

    gap_labels = ["A − B\n(Cipher)", "A − B3\n(Pseudonyms)"]
    gap_vals = [gap_B, gap_B3]
    cis = [ci_B, ci_B3]
    gap_cols = [COLORS["armB"], COLORS["armB3"]]

    ax2.bar(range(len(gap_labels)), gap_vals, width=0.45, color=gap_cols, alpha=0.9)
    for i, (g, ci, col) in enumerate(zip(gap_vals, cis, gap_cols)):
        ax2.plot([i, i], ci, color="k", lw=1.5)
        ax2.text(i, max(ci[1], g) + 0.5, f"{g:+.1f} pts\n[{ci[0]:.1f}, {ci[1]:.1f}]", ha="center", fontsize=8)

    ax2.axhline(0, color="k", lw=0.9, ls="-")
    ax2.set_xticks(range(len(gap_labels)))
    ax2.set_xticklabels(gap_labels)
    ax2.set_ylabel("Leakage Gap (% points; 95% CI)")
    ax2.set_ylim(-8, 8)
    ax2.set_title("(b) Zero Premature Naming on Unseen Text")
    ax2.grid(axis="y", ls="--", color=COLORS["grid"], alpha=0.8)

    fig.suptitle("Figure 4. Unseen-Text Negative Control (E2: Qwen2.5-32B, 17 LLM-Authored Stories)", y=0.98)
    add_provenance(ax1, PROVENANCE_LABEL, y=-0.22)
    add_provenance(ax2, PROVENANCE_LABEL, y=-0.22)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))

    out_png = OUT_DIR / "fig_unseen_text_control.png"
    out_svg = OUT_DIR / "fig_unseen_text_control.svg"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote Figure (d) to {out_png} and {out_svg}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating reader-faithfulness paper figures...")
    make_figure_a()
    make_figure_b()
    make_figure_c()
    make_figure_d()
    print("All paper figures completed.")


if __name__ == "__main__":
    main()
