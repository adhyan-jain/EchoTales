# Paper skeleton v1 and claim-to-evidence matrix (CP-I), 2026-10-15

Status: **skeleton only; no manuscript prose.** Every number is silver, synthetic or system-internal and is tagged as such; no human label exists yet (arrives with the owner's weekend labels). At most three Track P contributions plus a system section. Track P and Track S are kept in separate sections.

## 1. Working title and one-sentence claim

*Reading in order: measuring premature identity resolution in long serials.* We define a **premature-resolution rate** for alias-to-identity linking under a chapter prefix, with a reader-warranted oracle that allows UNDETERMINED, and show on controlled synthetic worlds that it separates resolvers that respect disclosure from those that do not; we also audit a real pipeline against it.

## 2. Track P contributions after the evidence (re-ranked)

| # | Contribution | Survives? | Evidence (provenance) | Closest work and exact difference | Falsifier (stated) |
|---|---|---|---|---|---|
| P1 | **The measurement design**: premature-resolution rate against a reader-warranted oracle with an UNDETERMINED label, reported with reader-view and omniscient-view accuracy (the metric needs both) | **Yes, narrowly.** Construct validity shown on synthetic worlds; real-novel use not yet shown | M3: 160 synthetic worlds, 872 pre-reveal aliases: retroactive system 872/872 premature and 100% omniscient, reader-observer 0/872 premature and 100% reader view, do-nothing floor 49.7%, shipped resolver 0 on both accuracy views (`m3_results.json`, SYNTHETIC) | SynthWorlds' knowledge-advantage gap (real minus renamed) is the leakage definition; Jiang & Ferraro for renaming; KoCoNovel and LitBank 4.2.5 for the two views. Difference: prefix/entitlement framing, a reveal-position oracle and the joint reporting rule | The metric fails to separate the designed systems (it did not fail) |
| P2 | **A pre-registered synthetic suite plus an engine audit showing that rule-based reveal detection does not generalise** | **Yes, as a diagnostic result** | M3 R4: repo `REVEAL_PATTERNS` recall 80/80 on one phrasing, 0/80 on three; patterns written for two phrasings 0/80 on two held-out phrasings (SYNTHETIC) | None found that measures reveal-detector generalisation for serials | Detection recall on real serials is high (unmeasured; needs labels) |
| P3 | **The failure audit (C5)** of an identity-resolution pipeline on a real serial | **Yes, as grounding** | 58/88 silver hard cases never detected; scorer reaches 0.550 vs 0.80 (0 of 880 links scored); 5 of 11,122 links stamped before the reader's binding (5 of 547 briefs); LitBank CoNLL F1 15.95 / 42.44 (human-keyed external) | Audit papers exist for coreference tools (BookCoref evaluates BookNLP); none on a bitemporal story graph | Defects fixed and numbers move (planned via the branch) |
| — | Evidence-gated linking (C1b) | **No** | Gate v1 over-rejected (14/30 vs 29/30); v2 passes only via a surface-identity shortcut (19 of 20 accepted hard items) and a lexical visibility rule explains the primary-item blocks; entailment rejected 9 of 10 uses (SILVER) | BookCoref step 2 overlaps (precision-first LLM verification) | Moves to the system section or a negative-result paragraph |
| — | Leakage under renaming (C1a) | **Not established** | L1: +9.7 points A-minus-B over 62 items, sign test p = 0.031, 6 vs 0 discordant (SILVER, one model); renaming control validated against the deterministic resolver in T4 v5 (99.96% agreement; v3 and v4 failed first) but not for an LLM; unseen-text control L2U run (Luna) and repeated on Qwen (difference-in-differences +6.5 [-3.2, +17.7], inconclusive): synthetic renaming-damage gap +3.2 points [0.0, 8.1], difference-in-differences +6.5 [-1.6, +14.5], inconclusive by the pre-registered rule | J&F, SynthWorlds, finance-domain work show the gap includes renaming damage | The gap equals the gap on unseen synthetic text (run: synthetic gap +3.2 of the real +9.7; difference not distinguishable from 0) |
| — | Title-holder temporal model | **No (system)** | M3b: bitemporal stamp serves both views (SYNTHETIC); TAC-KBP covers tenure intervals | TAC-KBP temporal slot filling | n/a |

**Rating against the novelty gate** (formal task; one novelty sentence; closest work and difference; strongest baseline; falsifier): P1 meets the first four on paper and has a stated falsifier, but its strongest evidence is synthetic and it has **no human-labelled real-novel result**; the strongest baseline for the central question (a renaming-only or gist-prompt control) is defined, not yet run. Verdict today: **a workshop-level measurement-and-audit paper with a pilot, not a main-track method paper.** It becomes stronger if the weekend human labels support P1 on real text and the unseen-text control separates leakage from renaming damage.

## 2b. Track S status (system section, no novelty claimed)

Scope-A adapters are implemented and tested on the local branch `chimera/system-adapters` (B1, B2, B3, B4, B13, A7, A1/A2; see `NOVELTY_REPORT.md` 5.12): honest counters, prefix resolve, causal title option, reader-entitled briefs, honest conditioning, dated wiki canon. Defaults change only for the two counter fixes.

## 3. Proposed sections

1. Introduction: why identity timing matters in serials; the gap (reader view vs final truth) and what exists (KoCoNovel, LitBank, SynthWorlds).
2. Task and metric: the oracle, UNDETERMINED, the three reported numbers, leakage as the renaming gap (credited to SynthWorlds/J&F), power.
3. Synthetic suite (SIO v1, M3, M3b): construction, systems, results, what is by construction and what is not.
4. A real-serial pilot: the 72-item sheet, silver and (when available) human labels, model-versus-human agreement, the closed-book probe and its limits.
5. Pipeline audit (C5) and gate analyses, with the gate-versus-engine diagnosis as a methodological note.
6. System (Track S, separate section): bitemporal graph, reader-observer `state_of`, the integration register adopted/adapted components, defects fixed on the authorised branch.
7. Limitations; ethics and data (no novel text distributed; public-exposure note); related work (from `PRIOR_ART.md` and the register).

## 4. Tables and figures to build (each traced to a file)

| Item | Source | Status |
|---|---|---|
| T1 metric definitions and oracle | `PREREG_M3`, `sio_synthetic_oracle.py` | ready |
| T2 M3 pooled system-by-detector table | `m3_results.json` | ready |
| F1 reader vs omniscient accuracy plane per system | `m3_results.json` | to draw |
| T3 detector recall by template | `m3_results.json` | ready |
| T4 pilot sheet composition and (later) human-label agreement | `pilot_manifest.json`, `human_pilot_analysis.py` | waits for labels |
| T5 L1 and L1b arm results (silver) | `l1_analysis.json`, `l1b_analysis.json` | ready |
| T6 audit table (C5) | `silver_pilot_results.json`, `prompt_invariant_ri.json`, repo files | ready |
| T7 gate diagnosis | `gate_failure_diagnosis.json` | ready |

## 5. What a reviewer would attack, and the prepared answer

1. **"The leakage claim is renaming damage."** True and conceded: the gap is not established as leakage. The unseen-text control (run, $0.0095) found a synthetic renaming-damage gap of +3.2 points and an inconclusive difference-in-differences (+6.5, CI [-1.6, +14.5]); a validated renaming control exists for the deterministic engine (T4 v5). The paper does not claim leakage.
2. **"Silver labels from a model that may share the resolver's memory."** Conceded and disclosed everywhere; the weekend human labels test model-versus-human agreement; M2 on a same-family model does not resolve it, a third-family run would.
3. **"The synthetic results are by construction."** Partly: the sensitivity of the metric is the claim, not any system's merit; the non-by-construction finding is detector brittleness.
4. **"n is tiny on the real novel."** Yes: 4 primary items with repo-derived reveal chapters; up to 23 with human labels; the paper states the smallest detectable effect.
5. **"Renaming and dual labels already exist."** Yes, and they are credited; the contribution is the prefix/entitlement metric and its validity checks.
6. **"The gate result is a shortcut."** Conceded; reported as a negative result with the gate-versus-engine diagnosis.

## 6. Claim-to-evidence matrix

Every sentence that will carry a number in the paper maps to a file and a command in `NOVELTY_REPORT.md` section 10 and `INTEGRATION_REGISTER.md`; no number is used that is not in a results file produced by a logged command.

## 7. Public exposure (information only)

No novel text is in any file created for this skeleton; the standing public-exposure issue stays with the owner.
