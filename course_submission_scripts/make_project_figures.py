"""Figures for the VIT project document and the slides. Every plotted number is read from a stored result file.

Run with the scratch venv that has matplotlib:  data/scratch/docs_venv/bin/python scripts/chimera/make_project_figures.py
Inputs (read-only): data/eval/chimera/pd_final_pooled.json, pd_dose_response.json, pd_v5/analysis.json, pd_memory_free_validity.json
Outputs: docs/paper/project_doc/figures/fig*.png
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path("data/eval/chimera")
OUT = Path("docs/paper/project_doc/figures")
OUT.mkdir(parents=True, exist_ok=True)
C = dict(luna="#8e44ad", local="#1f77b4", all="#7f7f7f", A="#2ca02c", B="#d62728", B3="#ff7f0e", ink="#222222", box="#eef2f7", edge="#34495e")
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})


def pct(x):
    return 100 * x


def fig_forest():
    d = json.loads((ROOT / "pd_final_pooled.json").read_text())
    rows = []
    for label, key in (("v2 (19 events)", "v2"), ("v3 (12 fresh events)", "v3"), ("v6 (7 fresh events)", "v6"), ("All 38 events", "all_v2_v3_v6")):
        for who, src, col in (("Luna (reference model)", d["luna_only"], C["luna"]), ("4 valid local models", d["valid_pool"], C["local"])):
            r = src[key]
            rows.append((f"{label}  |  {who}", pct(r["gap_A_minus_B"]), pct(r["ci"][0]), pct(r["ci"][1]), col, r["events"]))
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    for i, (lab, g, lo, hi, col, n) in enumerate(rows[::-1]):
        ax.plot([lo, hi], [i, i], color=col, lw=2.2)
        ax.plot([g], [i], "o", color=col, ms=6)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows[::-1]], fontsize=8)
    ax.axvline(0, color="k", lw=0.8)
    ax.axvline(10, color="k", lw=0.6, ls=":")
    ax.set_xlabel("Leakage gap, original minus renamed (points; 95% event-cluster interval)", fontsize=8.5)
    ax.set_title("Figure 1. Name-keyed leakage gap by model group and dataset", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_forest.png", dpi=200)
    plt.close(fig)


def fig_cue():
    a = json.loads((ROOT / "pd_v5/analysis.json").read_text())
    models = [m for m in a["per_model"] if "pd_v2" in a["per_model"][m]]
    short = {"gemma2:9b": "gemma2", "qwen2.5:7b": "qwen2.5", "mistral:7b-instruct": "mistral", "llama3.1:8b": "llama3.1", "phi4-mini:latest": "phi4-mini"}
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.6))
    xs = range(len(models))
    w = 0.26
    for k, (arm, col, lab) in enumerate((("A", C["A"], "A original names"), ("B", C["B"], "B letter cipher"), ("B3", C["B3"], "B3 cue-preserving pseudonyms"))):
        axes[0].bar([x + (k - 1) * w for x in xs], [pct(a["per_model"][m]["pd_v2"][f"ctrl_acc_{arm}"]) for m in models], w, color=col, label=lab)
    axes[0].set_xticks(list(xs))
    axes[0].set_xticklabels([short.get(m, m) for m in models], rotation=20)
    axes[0].set_ylim(60, 102)
    axes[0].set_ylabel("Plain-control accuracy (%)")
    axes[0].set_title("(a) Cue restoration repairs comprehension\n(v2 events, each model)", fontsize=9)
    axes[0].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
    pool = a["pools"]["G2_valid"]
    vals = [pct(pool["gap_A_minus_B"]), pct(pool["gap_A_minus_B3"])]
    cis = [pool["gap_A_minus_B_ci"], pool["gap_A_minus_B3_ci"]]
    for i, (v, ci, col) in enumerate(zip(vals, cis, (C["B"], C["B3"]))):
        axes[1].bar(i, v, 0.55, color=col)
        axes[1].plot([i, i], [pct(ci[0]), pct(ci[1])], color="k", lw=1.5)
    axes[1].set_xticks([0, 1])
    axes[1].set_xticklabels(["A minus B\n(cipher)", "A minus B3\n(pseudonyms)"])
    axes[1].set_ylabel("Leakage gap (points)")
    axes[1].set_title(f"(b) Premature naming is not restored\n(recovered fraction {pool['recovered_fraction']:+.2f})", fontsize=9)
    fig.suptitle("Figure 2. Cue-preserving control; panel (b) pooled over 31 events, 4 valid local models", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / "fig_cue.png", dpi=200)
    plt.close(fig)


def fig_dose():
    d = json.loads((ROOT / "pd_dose_response.json").read_text())
    lu, lo = d["luna_gap_vs_local_recognition"], d["valid_local_pool_gap_vs_local_recognition"]
    ks = sorted(int(k) for k in lu["mean_gap_by_recognition_count"])
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    w = 0.38
    ax.bar([k - w / 2 for k in ks], [pct(lu["mean_gap_by_recognition_count"][str(k)]) for k in ks], w, color=C["luna"], label=f"Luna (cross-family), Spearman {lu['spearman']:+.2f}, p={lu['perm_p']:.3f}")
    ax.bar([k + w / 2 for k in ks], [pct(lo["mean_gap_by_recognition_count"][str(k)]) for k in ks], w, color=C["local"], label=f"Valid local pool, Spearman {lo['spearman']:+.2f}, p={lo['perm_p']:.5f}")
    for k in ks:
        ax.text(k, -7, f"n={lu['events_per_count'][str(k)]}", ha="center", fontsize=7)
    ax.set_xlabel("How many of 5 local models recognise the book (title-assisted probe)")
    ax.set_ylabel("Mean leakage gap (points)")
    ax.set_ylim(-9, 55)
    ax.axhline(0, color="k", lw=0.7)
    ax.legend(fontsize=7)
    ax.set_title("Figure 3. Leakage gap rises with book familiarity (38 events, post hoc)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_dose.png", dpi=200)
    plt.close(fig)


def fig_pooled():
    d = json.loads((ROOT / "pd_final_pooled.json").read_text())
    items = [("Luna", d["luna_only"]["all_v2_v3_v6"], C["luna"]), ("All models\n(G2a >= 80%)", d["all_models_g2a80"]["all_v2_v3_v6"], C["all"]), ("4 valid local\nmodels", d["valid_pool"]["all_v2_v3_v6"], C["local"])]
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    for i, (lab, r, col) in enumerate(items):
        ax.bar(i, pct(r["gap_A_minus_B"]), 0.55, color=col)
        ax.plot([i, i], [pct(r["ci"][0]), pct(r["ci"][1])], color="k", lw=1.5)
        ax.text(i, pct(r["ci"][1]) + 1.2, f"{r['events_positive']} pos / {r['events_negative']} neg\np={r['sign_p']:.3g}", ha="center", fontsize=7)
    ax.set_xticks(range(len(items)))
    ax.set_xticklabels([x[0] for x in items])
    ax.set_ylabel("Leakage gap (points)")
    ax.set_ylim(0, 48)
    ax.set_title("Figure 4. Pooled over all 38 events (event-level inference)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_pooled.png", dpi=200)
    plt.close(fig)


def box(ax, x, y, w, h, text, fc=C["box"], fs=7.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.015", fc=fc, ec=C["edge"], lw=1.1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=C["ink"], weight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9, color=C["edge"], lw=1.1))


def fig_arch():
    fig, ax = plt.subplots(figsize=(10.2, 5.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.97, "Figure 5. System architecture of the leakage study", ha="center", fontsize=11, weight="bold")
    # row 1: data and events
    box(ax, 0.02, 0.76, 0.17, 0.14, "1. Corpus\nProject Gutenberg\npublic-domain novels\n(46 books used so far)", fs=7.5)
    box(ax, 0.23, 0.76, 0.17, 0.14, "2. Event mining\nreveal-cue patterns\n+ LLM extraction\n(alias -> identity)", fs=7.5)
    box(ax, 0.44, 0.76, 0.17, 0.14, "3. Verifier + audit\nexact reveal sentence,\ncutoff, no lexical cue;\nindependent model audit", fs=7.5)
    box(ax, 0.65, 0.76, 0.14, 0.14, "4. Frozen event\nlist (SHA-256)\ndev / test split\nby book", fs=7.5)
    box(ax, 0.83, 0.76, 0.15, 0.14, "5. Item builder\n1,200-character\nprefix window +\ncandidate list", fs=7.5)
    for x1, x2 in ((0.19, 0.23), (0.40, 0.44), (0.61, 0.65), (0.79, 0.83)):
        arrow(ax, x1, 0.83, x2, 0.83)
    arrow(ax, 0.905, 0.76, 0.905, 0.66)
    # row 2: arms
    ax.text(0.5, 0.655, "6. Four arms per item (same text, same candidates)", ha="center", fontsize=8.5, weight="bold")
    arms = [("A  original names", C["A"]), ("B  letter cipher\n(all proper nouns)", C["B"]), ("B3  cue-preserving\npseudonyms (gender,\nname type kept)", C["B3"]), ("Closed-book +\ntitle-assisted\nmemory probes", "#9467bd")]
    for i, (t, col) in enumerate(arms):
        box(ax, 0.06 + i * 0.225, 0.50, 0.19, 0.12, t, fc="white", fs=7.5)
        ax.add_patch(FancyBboxPatch((0.06 + i * 0.225, 0.50), 0.19, 0.012, boxstyle="square,pad=0", fc=col, ec=col))
    # row 3: models
    box(ax, 0.03, 0.30, 0.31, 0.12, "7a. Open-weight models on RunPod (vLLM)\nLlama-3.3-70B, Qwen2.5-72B,\nOLMo-2-32B", fs=7.5)
    box(ax, 0.37, 0.30, 0.27, 0.12, "7b. Claude Sonnet 5.5\n(headless CLI, subscription)", fs=7.5)
    box(ax, 0.67, 0.30, 0.30, 0.12, "7c. Exploratory so far:\nlocal 7-9B models (ollama)\nand gpt-5.6-luna", fs=7.5)
    for i in range(4):
        pass
    arrow(ax, 0.5, 0.50, 0.5, 0.42)
    # row 4: scoring and stats
    box(ax, 0.06, 0.10, 0.2, 0.13, "8. Scoring\npremature rate =\nanswer is the true\nidentity before the reveal", fs=7.5)
    box(ax, 0.30, 0.10, 0.34, 0.13, "9. Statistics (fixed in advance)\nevent-cluster bootstrap, random-effects pooling,\npermutation dose-response, Holm correction", fs=7.5)
    box(ax, 0.68, 0.10, 0.3, 0.13, "10. Outputs\nleakage gap A - B, recovered fraction (B3),\nmitigation and spoiler-rate tests, report", fs=7.5)
    arrow(ax, 0.5, 0.30, 0.5, 0.235)
    arrow(ax, 0.26, 0.165, 0.30, 0.165)
    arrow(ax, 0.64, 0.165, 0.68, 0.165)
    fig.savefig(OUT / "fig_arch.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_channels():
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.96, "Figure 6. Reader-faithfulness: two ways an output at chapter c can depend on later chapters", ha="center", fontsize=10, weight="bold")
    box(ax, 0.02, 0.52, 0.44, 0.31, "Channel 1: parametric memory (this study)\nThe model remembers the book, so it names a\ndisguised character before the reveal.\nMeasured by renaming; repair tested:\npseudonymise the names, map the answer back.", fs=8)
    box(ax, 0.54, 0.52, 0.44, 0.31, "Channel 2: derivation look-ahead (graph audit)\nA pipeline stage stamps a property at chapter c\nfrom evidence in later chapters.\nMeasured by truncate-and-rebuild:\npersona stage differs for 8.0% of characters.", fs=8)
    box(ax, 0.1, 0.08, 0.8, 0.27, "Reader-faithfulness: the output at chapter c may depend only on chapters up to c.\nEchoTales' observer-scoped query state_of(target, timeline, position, observer)\nis the substrate on which both violations are defined and measured.", fs=8, bold=False)
    arrow(ax, 0.24, 0.55, 0.40, 0.35)
    arrow(ax, 0.76, 0.55, 0.60, 0.35)
    fig.savefig(OUT / "fig_channels.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_rf():
    """Whole-book vs versioned character card leak per model, renamed (cipher) text, both rules; addenda 6 to 10."""
    rf = json.loads((ROOT / "rf_e2e/analysis.json").read_text())
    nm = {"qwen2.5:7b": "Qwen2.5-7B", "llama3.1:8b": "Llama-3.1-8B", "mistral:7b-instruct": "Mistral-7B", "qwen32b": "Qwen2.5-32B", "mistral24": "Mistral-24B"}
    rob = rf.get("robust") or {}
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.3), sharey=True)
    for ax, key, title in ((axes[0], "A_primary_EXPLICIT_IMPLIED", "Strict text rule (19 events)"), (axes[1], "B_EXPLICIT_IMPLIED", "Judge rule (54 events)")):
        labels, w, pv = [], [], []
        for st in (rf, rf.get("larger") or {}):
            for m, r in ((st.get(key) or {}).get("per_model") or {}).items():
                labels.append(nm.get(m, m)); w.append(pct(r["W_ren"])); pv.append(pct(r["P_ren"]))
        x = range(len(labels))
        ax.bar([i - 0.2 for i in x], w, 0.4, color=C["B"], label="Whole-book card (stamped at first mention)")
        ax.bar([i + 0.2 for i in x], pv, 0.4, color=C["A"], label="Versioned card (reader's prefix only)")
        rr = (rob.get("ruleA" if key.startswith("A") else "ruleB") or {}).get("rates")
        if rr and "Qwen2.5-7B" in labels:
            i = labels.index("Qwen2.5-7B")
            ax.scatter([i - 0.2], [pct(rr["W_ren_nospoil"])], marker="v", color=C["ink"], zorder=3, label="Whole-book + 'avoid spoilers' (Qwen2.5-7B)")
        ax.axvline(2.5, color="#bbbbbb", lw=0.8, ls=":")
        ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
        ax.set_title(title, fontsize=9)
    axes[0].set_ylabel("% of events where the card names\nthe hidden identity early (cipher names)")
    h, lab = axes[1].get_legend_handles_labels()
    fig.legend(h, lab, fontsize=7.5, loc="lower center", ncol=3, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(OUT / "fig_rf.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    for f in (fig_forest, fig_cue, fig_dose, fig_pooled, fig_arch, fig_channels, fig_rf):
        f()
        print("wrote", f.__name__)
