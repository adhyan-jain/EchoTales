"""Figures for the journal manuscript (journal Revision 1), each written as vector PDF and 600 dpi PNG.

Why this exists: the revision asked for (a) a conceptual figure that says which evaluation detects each leakage
channel and where each mitigation acts, (b) an architecture figure that shows both research tracks instead of ten
memory-study stages, (c) exploratory and confirmatory results drawn as visibly separate blocks without the
unexplained +10-point line, (d) intervals on the cue-preserving gaps, (e) group sizes and intervals on the post hoc
familiarity analysis, and (f) card results distinguishable in greyscale and to colour-vision-deficient readers. The
course-document figures (course_submission_scripts/make_project_figures.py) did none of these, so this script
replaces them for the article. Every plotted number is read from stored result files; nothing is typed in.

Palette: Okabe-Ito, with marker shape (not colour alone) carrying each distinction.
Run: python scripts/paper/make_journal_figures.py   (repo .venv; writes docs/paper/journal/figures/)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

sys.path.insert(0, "scripts/chimera")
C = Path("data/eval/chimera")
OUT = Path("docs/paper/journal/figures")
OUT.mkdir(parents=True, exist_ok=True)

OI = dict(orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442", blue="#0072B2", vermillion="#D55E00",
          purple="#CC79A7", black="#000000", grey="#7F7F7F", light="#F2F2F2", ink="#1A1A1A")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
                     "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "axes.linewidth": 0.6,
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6, "lines.linewidth": 1.2,
                     "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42, "svg.fonttype": "none"})


def J(p):
    return json.loads(Path(p).read_text())


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=600, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / f"{name}.pdf")


def box(ax, x, y, w, h, text, fc="white", ec=OI["ink"], lw=0.8, size=7.5, weight="normal", ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=fc, ec=ec, lw=lw, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, weight=weight, color=OI["ink"], linespacing=1.25)


def arrow(ax, x0, y0, x1, y1, color=OI["ink"], ls="-", lw=0.9):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=8, color=color, lw=lw, ls=ls,
                                 shrinkA=0, shrinkB=0))


# ------------------------------------------------------------------------------------------------ Fig 1
def fig_channels():
    """Reader-faithfulness and the three leakage channels: what each is, which test sees it, where the fix acts."""
    # One axis unit is half an inch; at 6.5 pt a DejaVu Sans line holds about 10 characters per unit, so every label
    # below is wrapped to fit its box (the first draft overflowed at 7 pt).
    fig, ax = plt.subplots(figsize=(7.0, 3.3))
    ax.set_xlim(0, 14)
    ax.set_ylim(0.15, 6.6)
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0.1, 5.75), 7.6, 0.42, fc=OI["sky"], ec=OI["ink"], lw=0.6))
    ax.add_patch(plt.Rectangle((7.7, 5.75), 4.6, 0.42, fc="white", ec=OI["ink"], lw=0.6, hatch="////"))
    ax.text(3.9, 5.96, "prefix $P(c)$: text the reader has read", ha="center", va="center", fontsize=7)
    ax.text(10.0, 5.96, "suffix: unread text", ha="center", va="center", fontsize=7, bbox=dict(fc="white", ec="none", pad=0.8))
    ax.plot([7.7, 7.7], [5.6, 6.32], color=OI["vermillion"], lw=1.6)
    ax.text(7.7, 6.42, "reader position $c$", ha="center", fontsize=7, color=OI["vermillion"])
    ax.text(12.45, 5.96, "book $B$", ha="left", va="center", fontsize=7)
    for x, t in ((0.1, "Leakage channel"), (4.85, "Evaluation that detects it"), (9.6, "Mitigation evaluated")):
        ax.text(x, 5.15, t, fontsize=7.5, weight="bold", va="center")
    rows = [
        ("Parametric memory\nthe model already knows the book;\nthe input may be prefix-only",
         "Renaming contrast (Sect. 4.2)\noriginal vs renamed names,\nscored at reveal time",
         "Pseudonymise and map back\n(a trade-off; Sect. 6.5)", OI["purple"]),
        ("Content leakage\nunread text enters the input\n(whole-volume card, long context)",
         "Truncate-and-rebuild;\nsuffix canaries (string match)",
         "Prefix-built (versioned) cards;\nphysical truncation", OI["orange"]),
        ("Selection or derivation leakage\nprefix text is served, but chosen\nor derived using the suffix",
         "Truncate-and-rebuild;\ncounterfactual suffix\n(canaries are blind to it)",
         "Evidence-horizon versioning;\nprefix-decided gate;\nprefix-causal index", OI["green"]),
    ]
    y = 3.65
    for ch, det, mit, col in rows:
        box(ax, 0.1, y, 4.45, 1.12, ch, fc=col + "33", ec=col, lw=1.0, size=6.5)
        box(ax, 4.85, y, 4.45, 1.12, det, size=6.5)
        box(ax, 9.6, y, 4.3, 1.12, mit, size=6.5, ls="--")
        arrow(ax, 4.6, y + 0.56, 4.83, y + 0.56)
        arrow(ax, 9.35, y + 0.56, 9.58, y + 0.56)
        y -= 1.4
    save(fig, "fig1_channels")


# ------------------------------------------------------------------------------------------------ Fig 2
def fig_workflow():
    """Two research tracks sharing the reader-position and evidence-horizon concepts."""
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.set_xlim(0, 14)
    ax.set_ylim(0.1, 8.0)
    ax.axis("off")
    box(ax, 3.2, 7.05, 7.6, 0.8, "Shared concepts: reader position $c$ (cutoff before the reveal)\n"
        "and evidence horizon (latest chapter a derived value reads)", fc=OI["light"], size=6.8)
    ax.text(3.0, 6.3, "Track 1: parametric memory (RQ1)", fontsize=7.5, weight="bold", color=OI["purple"], ha="center")
    ax.text(11.0, 6.3, "Track 2: pipeline and assistant leakage (RQ2, RQ3)", fontsize=7.5, weight="bold", color=OI["green"], ha="center")
    m = ["Public-domain novels\n(Project Gutenberg)", "Event mining (model) and\nexact reveal-sentence match",
         "Cutoff verification, model\naudit, human subset", "Pre-reveal items in arms\nA, B, B2, B3",
         "Answers from local, open\nand reference models", "Premature naming;\nevent-cluster statistics"]
    p = ["Book $B$ (web novels,\nEnglish originals, synthetic)", "Full build $F(B)$ and\nprefix build $F(P(c))$",
         "Divergence at $c$; exposure\nscreen; counterfactual suffix", "Disclosure labels\n(two model annotators)",
         "Repairs (versioning, gate,\ncards, truncation, index)", "Re-audit; cost and\nwithheld values"]
    y0, dy, w, h = 5.25, 0.98, 5.6, 0.74
    for col, xs, labels in ((OI["purple"], 0.2, m), (OI["green"], 8.2, p)):
        for i, t in enumerate(labels):
            box(ax, xs, y0 - i * dy, w, h, t, fc=col + "1A", ec=col, size=6.6)
            if i:
                arrow(ax, xs + w / 2, y0 - (i - 1) * dy, xs + w / 2, y0 - i * dy + h)
    arrow(ax, 5.0, 7.05, 3.0, 6.5)
    arrow(ax, 9.0, 7.05, 11.0, 6.5)
    # the generic-assistant experiments reuse Track 1's reveal-time events and Track 2's prefix-versus-full contrast
    box(ax, 6.15, 2.45, 1.7, 1.6, "Generic\nassistant:\ncards, canaries,\nselection\n(Sect. 4.4)", fc="white", ec=OI["orange"], size=6.2, ls="--")
    arrow(ax, 5.8, y0 - 2 * dy + h / 2, 6.6, 4.05, color=OI["orange"], ls="--")
    arrow(ax, 8.2, y0 - 1 * dy + h / 2, 7.4, 4.05, color=OI["orange"], ls="--")
    save(fig, "fig2_workflow")


# ------------------------------------------------------------------------------------------------ Fig 3
def fig_forest():
    fp = J(C / "pd_final_pooled.json")
    cf = J(C / "confirm/main/analysis.json")
    rows = []
    for key, lab in (("v2", "v2, 19 events"), ("v3", "v3, 12 events"), ("v6", "v6, 7 events"), ("all_v2_v3_v6", "all 38 events")):
        r = fp["luna_only"][key]
        rows.append((f"Reference model, {lab}", r["gap_A_minus_B"], *r["ci"], OI["purple"], "D", "E"))
        r = fp["valid_pool"][key]
        rows.append((f"Local pool (4 models), {lab}", r["gap_A_minus_B"], *r["ci"], OI["blue"], "o", "E"))
    names = {"mistral24": "Mistral-Small-3.2-24B", "olmo32b": "OLMo-2-32B", "qwen32b": "Qwen2.5-32B"}
    for m, nm in names.items():
        r = cf["per_model"][m]["primary_test"]
        rows.append((f"{nm}, 32 events", r["gap_A_minus_B"], *r["ci"], OI["green"], "s", "C"))
    rows.append(("Random-effects pool (H1), 3 models", cf["H1"]["pooled"], *cf["H1"]["ci"], OI["black"], "P", "C"))
    fig, ax = plt.subplots(figsize=(6.4, 4.3))
    ypos, y = [], 0.0
    for i, r in enumerate(rows):
        if i and r[6] != rows[i - 1][6]:
            y += 1.4
        ypos.append(y)
        y += 1
    top = max(ypos)
    ypos = [top - v for v in ypos]
    for (lab, g, lo, hi, col, mk, _), yy in zip(rows, ypos):
        ax.plot([100 * lo, 100 * hi], [yy, yy], color=col, lw=1.4)
        ax.plot([100 * g], [yy], mk, color=col, ms=5.2, mec="black", mew=0.4)
    ax.set_yticks(ypos)
    ax.set_yticklabels([r[0] for r in rows])
    ax.axvline(0, color="black", lw=0.7)
    ax.axhline((ypos[7] + ypos[8]) / 2, color=OI["grey"], lw=0.6, ls="--")
    ax.set_xlim(-45, 58)
    ax.text(57, ypos[0] + 0.55, "Exploratory (PD v2, v3, v6)", ha="right", fontsize=7.5, weight="bold")
    ax.text(57, ypos[8] + 0.55, "Confirmatory, pre-registered primary set", ha="right", fontsize=7.5, weight="bold")
    ax.set_ylim(min(ypos) - 0.8, top + 1.3)
    ax.set_xlabel("Leakage gap $p_A - p_B$ (percentage points), point estimate and 95% event-cluster interval")
    save(fig, "fig3_forest")


# ------------------------------------------------------------------------------------------------ Fig 4
def fig_cue():
    v5 = J(C / "pd_v5/analysis.json")
    order = [("gpt-5.6-luna", "Reference\nmodel"), ("qwen2.5:7b", "Qwen2.5-7B"), ("llama3.1:8b", "Llama-3.1-8B"),
             ("mistral:7b-instruct", "Mistral-7B"), ("gemma2:9b", "Gemma-2-9B"), ("phi4-mini:latest", "Phi-4-mini")]
    fig, ax = plt.subplots(figsize=(6.3, 3.0))
    arms = ((-0.17, "gap_A_minus_B", "gap_A_minus_B_ci", OI["vermillion"], "o"),
            (0.17, "gap_A_minus_B3", "gap_A_minus_B3_ci", OI["blue"], "s"))
    for i, (m, _) in enumerate(order):
        r = v5["per_model"][m]["pd_v2"]["per_event"]
        for off, key, cik, col, mk in arms:
            ax.plot([i + off] * 2, [100 * r[cik][0], 100 * r[cik][1]], color=col, lw=1.2)
            ax.plot([i + off], [100 * r[key]], mk, color=col, ms=5, mec="black", mew=0.4)
    p = v5["pools"]["G2_valid"]
    xi = len(order) + 0.4
    for off, key, cik, col, mk in arms:
        ax.plot([xi + off] * 2, [100 * p[cik][0], 100 * p[cik][1]], color=col, lw=1.6)
        ax.plot([xi + off], [100 * p[key]], mk, color=col, ms=6.5, mec="black", mew=0.5)
    ax.set_xticks(list(range(len(order))) + [xi])
    ax.set_xticklabels([nm for _, nm in order] + [f"Valid pool,\nv2+v3 ({p['events']} ev.)"], fontsize=7)
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(len(order) - 0.3, color=OI["grey"], lw=0.6, ls="--")
    ax.set_ylabel("Leakage gap (percentage points)")
    ax.plot([], [], "o", color=OI["vermillion"], mec="black", mew=0.4, label="A $-$ B: original names minus letter cipher")
    ax.plot([], [], "s", color=OI["blue"], mec="black", mew=0.4, label="A $-$ B3: original names minus cue-preserving pseudonyms")
    ax.legend(loc="upper left", frameon=False, ncol=2, bbox_to_anchor=(0.0, 1.13), columnspacing=1.2)
    ax.set_ylim(-8, 62)
    save(fig, "fig4_cue_preserving")


# ------------------------------------------------------------------------------------------------ Fig 5
def fig_dose():
    import pd_dose_response as D
    v4, v6 = D.runs("pd_v4"), D.runs("pd_v6")
    ds = {"v2": D.runs("pd_v2"), "v3": D.runs("pd_v3"), "v6": v6}
    recog = {}
    for m in D.LOCAL:
        if m in v4:
            for e, t in v4[m]["truth"].items():
                recog[e] = recog.get(e, 0) + int(v4[m]["probe"][e]["M2_orig"] == t)
        if m in v6:
            for e, t in v6[m]["m2_truth"].items():
                recog[e] = recog.get(e, 0) + int(v6[m]["m2"][e]["M2_orig"] == t)
    luna, pool = {}, {}
    for runs_ in ds.values():
        for m, r in runs_.items():
            g = D.event_gaps(r)
            if m == "gpt-5.6-luna":
                luna.update({e: sum(v) / len(v) for e, v in g.items()})
            if m in D.LOCAL and m in ds["v3"] and D.g2_valid(r, ds["v3"][m]):
                for e, v in g.items():
                    pool.setdefault(e, []).extend(v)
    pool = {e: sum(v) / len(v) for e, v in pool.items()}
    bins = [("0-1 of 5", (0, 1)), ("2-3 of 5", (2, 3)), ("4-5 of 5", (4, 5))]
    rng = random.Random(20261019)

    def grp(outcome, lo, hi):
        ys = [outcome[e] for e in outcome if e in recog and lo <= recog[e] <= hi]
        bs = sorted(sum(rng.choice(ys) for _ in ys) / len(ys) for _ in range(5000))
        return sum(ys) / len(ys), bs[124], bs[4874], len(ys)

    res = {}
    fig, ax = plt.subplots(figsize=(5.0, 2.9))
    for off, (name, outc, col, mk) in zip((-0.12, 0.12), (("Reference model", luna, OI["purple"], "D"),
                                                         ("Valid local pool", pool, OI["blue"], "o"))):
        pts = [grp(outc, *b) for _, b in bins]
        res[name] = [dict(group=lab, mean=round(m_, 4), ci=[round(l_, 4), round(h_, 4)], events=n_)
                     for (lab, _), (m_, l_, h_, n_) in zip(bins, pts)]
        for k, (m_, l_, h_, _) in enumerate(pts):
            ax.plot([k + off] * 2, [100 * l_, 100 * h_], color=col, lw=1.2)
            ax.plot([k + off], [100 * m_], mk, color=col, ms=5.5, mec="black", mew=0.4, label=name if k == 0 else None)
    ns = [r["events"] for r in res["Valid local pool"]]
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"{lab} local models\nrecognise the book\n(n = {n} events)" for (lab, _), n in zip(bins, ns)], fontsize=7)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("Mean per-event gap (points)")
    ax.legend(frameon=False, loc="upper left")
    (OUT / "fig5_dose_groups.json").write_text(json.dumps(res, indent=1))
    save(fig, "fig5_familiarity_posthoc")


# ------------------------------------------------------------------------------------------------ Fig 6
def fig_cards():
    rf = J(C / "rf_e2e/analysis.json")
    nm = {"llama3.1:8b": "Llama-3.1-8B", "mistral:7b-instruct": "Mistral-7B", "qwen2.5:7b": "Qwen2.5-7B",
          "mistral24": "Mistral-Small-24B", "qwen32b": "Qwen2.5-32B"}
    small, large = ["llama3.1:8b", "mistral:7b-instruct", "qwen2.5:7b"], ["mistral24", "qwen32b"]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.9), sharey=True)
    for ax, key, title in ((axes[0], "B_EXPLICIT_IMPLIED", "Judge rule (model judge), 54 events"),
                           (axes[1], "A_primary_EXPLICIT_IMPLIED", "Text rule (string match), 19 events")):
        cols = [(m, rf[key]["per_model"][m]) for m in small]
        lg = (rf.get("larger") or {}).get(key, {}).get("per_model", {})
        cols += [(m, lg[m]) for m in large if m in lg]
        for i, (m, r) in enumerate(cols):
            ax.plot([i, i], [100 * r["P_ren"], 100 * r["W_ren"]], color=OI["grey"], lw=0.8, zorder=1)
            ax.plot(i, 100 * r["W_ren"], "o", color=OI["vermillion"], ms=6, mec="black", mew=0.4, zorder=3)
            ax.plot(i, 100 * r["P_ren"], "s", color=OI["blue"], ms=5.5, mec="black", mew=0.4, zorder=3)
        rob = rf["robust"]["ruleB" if key.startswith("B") else "ruleA"]["rates"]
        qi = [m for m, _ in cols].index("qwen2.5:7b")
        ax.plot(qi + 0.25, 100 * rob["W_ren_nospoil"], "^", color=OI["orange"], ms=6, mec="black", mew=0.4, zorder=3)
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels([nm[m] for m, _ in cols], rotation=25, ha="right", fontsize=7)
        if len(cols) > 3:
            ax.axvline(2.5, color=OI["grey"], lw=0.6, ls="--")
        ax.set_title(title)
    axes[0].set_ylabel("Cards naming the hidden identity\nbefore the reveal (% of events)")
    axes[0].plot([], [], "o", color=OI["vermillion"], mec="black", mew=0.4, label="Whole-volume card (W)")
    axes[0].plot([], [], "s", color=OI["blue"], mec="black", mew=0.4, label="Versioned, prefix-built card (P)")
    axes[0].plot([], [], "^", color=OI["orange"], mec="black", mew=0.4, label="W with an 'avoid spoilers' instruction")
    fig.legend(loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.09))
    save(fig, "fig6_cards")


if __name__ == "__main__":
    fig_channels()
    fig_workflow()
    fig_forest()
    fig_cue()
    fig_dose()
    fig_cards()
