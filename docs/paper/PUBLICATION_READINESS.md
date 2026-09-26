# Publication readiness

**2026-09-25; status updated 2026-09-26.** A fact-based assessment. It gives no acceptance estimates.

## Where the evidence stands

- **Solid:** an end-to-end system on a real 199-chapter volume; a reproducible script; honest diagnostic findings (`CONTRIBUTION_MATRIX.md` class H); an observer-state demonstration with persisted checks; a same-range baseline comparison.
- **Weak for a main-conference NLP paper:**
  1. every accuracy number is against an **LLM-drafted silver** set with no human agreement figure;
  2. the discriminative sets are small (88 hard cases, 46 retrieval cases, 3 reveals);
  3. one novel at volume scale, and the second (LOTM ch1–3) is markedly weaker;
  4. no external benchmark;
  5. the generation evidence is five panels in one chapter with no quality metric.

## Status after the evidence-upgrade pass (2026-09-26)

| MUST item | Status |
|---|---|
| 1. Human confirmation sample | **Package prepared** (`data/eval/human_review_200.csv`, `human_review_hardcases_88.csv`, gitignored; protocol in `docs/results/HUMAN_REVIEW_PROTOCOL.md`). **0 labels. Waiting on reviewers.** |
| 2. A1 + A2 | Done (`docs/results/A1_OBSERVER_ABLATION.md`, `A2_OBSERVER_ABLATION.md`) |
| 3. A7 | Done. It found and fixed a real key defect (`docs/results/A7_CACHE_ABLATION.md`). |
| 4. External benchmark | Done on LitBank, 100 documents (`docs/results/EXTERNAL_BENCHMARK.md`). The result is weak on the full key (15.9) and moderate on names only (42.4). |
| 5. LOTM limitation | Already measured; in `EXPERIMENT_TABLE.md` |

**Evidence-standard decision.**
- *Main track (ARR → ACL 2027):* **not yet.** The human sample is the single blocker. Without it, every in-domain number remains silver, and the only external number is weak.
- *Workshop (WNU 2027) or ACL 2027 demo:* **ready in evidence terms** once the human sample has at least one reviewer's labels, reported as silver-vs-human agreement.
- *ARR October 2026 (2026-10-12):* **do not target.**
- *Any public version:* sequenced after the IPR cell's decision (see below).

## Minimum experiment set (as planned 2026-09-25)

### MUST DO BEFORE SUBMISSION

1. **Small human-annotated confirmation sample.**
   - *What:* two annotators label (a) the 88 hardcases records' identities and (b) a random 200-mention sample from the silver RI set.
   - *Outputs:* Cohen's κ, plus silver-vs-human agreement.
   - *Why this size:* 200 mentions gives a ±7-point 95% interval on precision near 0.5, and tighter near 0.9. This is the smallest sample that lets the paper say whether silver-based numbers transfer, and reviewers at ACL venues will ask exactly that.
   - *Cost:* about 6–8 person-hours.
2. **Observer-mechanism ablations A1 + A2** (`ABLATION_PLAN.md`) over all detected reveals.
   - *Metric:* spoiler-leakage counts.
   - Runnable now, and cheap.
3. **Read-set ablation A7** in stub mode. It turns "keys differ" into a measured reuse/regeneration count. Hold the prompt and plan digest fixed, so that the digest's contribution is isolated.
4. **External comparability.** Run on BOOKCOREF or LitBank (a subset is acceptable) and report CoNLL-F1 with the same pipeline. It is the only non-silver, externally comparable number available without new annotation.
5. **Report the LOTM generalisation result and the transmigration failure** as a stated limitation (already measured).

### NICE TO HAVE

- Multi-chapter observer-contrast render (3 chapters), with a CLIPScore or identity-similarity measure.
- One re-resolve ablation (A4 or A5) for causal evidence on the resolution design.
- Witness-derivation precision on a hand-checked sample of reveal scenes.
- LOTM full-volume run.

### NOT WORTH DOING NOW

- A large human-annotation campaign (hundreds or thousands of mentions).
- A formal audio MOS or listening study.
- Scorer re-tuning.
- A GraphRAG / CORE-KG reimplementation.
- Concurrent-persona or retraction features built only to be evaluated.

## Transmigration: v1.1, or needed for this paper?

**v1.1, provided the paper does not claim transmigration handling.** The paper's Self/Persona evidence is the sequential reincarnation case and the representation. The LOTM two-Self split must appear as a measured limitation. If the paper's headline were "handles body change", this would be a must-fix; with the recommended framing (`PAPER_CLAIM_BOUNDARIES.md`), it is not.

## Single highest-value additional experiment

**The 200-mention human-annotated confirmation sample, with κ.** Every other result depends on whether silver numbers can be trusted, and it is the most likely reviewer objection. The observer ablations A1/A2 are the cheapest second, since they make the headline mechanism causal rather than illustrative.

## Sequencing constraint (IP)

Submitting to anonymous ARR review is generally treated as non-public. An arXiv preprint is public. Any public version of the paper, and any push of the current branch, must wait for the IPR cell's decision.
