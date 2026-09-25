# EchoTales — what is left after the completion pass

**Written 2026-09-25, updated after the finalization pass (EVOLUTION 4.90; `docs/FINAL_EVIDENCE_TABLE.md` is the current per-claim status)**, branch `validation/evidence-pass-2026-09-24` (not yet
pushed or merged). This lists everything the project will **not** have when the
current plan is done: missing metrics, unbuilt mechanisms, open defects, and
gaps in the patent, report, and reproducibility work. It is organised by
audience, and every item says *why* it is missing and *what it would take*.

Companion documents: `docs/FINAL_ECHOTALES_READINESS.md` (what **is** ready,
with evidence) and `docs/STATUS.md` (the per-subsystem state map).

Tags used below:
- **Blocked by decision**: the owner chose not to do it (for example, human annotation).
- **Blocked by data**: the corpus contains no instance to measure.
- **Not built**: the code does not exist.
- **Not run**: the code exists; the measurement has not been taken.
- **Human-only**: needs a person, not a session.

---

## 1. Metrics we will not have

### 1.1 Entity resolution (the research core)

| Metric | State | Why | What it would take |
|---|---|---|---|
| Any **human-anchored** P / R / F1 | Blocked by decision | Every figure is scored against the **SILVER** set, which Claude drafted. There is no human gold and no IAA. | Two annotators on 3–5 chapters of `reverend-insanity-c1-c5.jsonl`, then Cohen's κ. Roughly 6–10 person-hours. |
| **Inter-annotator agreement** | Blocked by decision | The two independent LLM drafts (Sonnet, Opus) cover different chapters, so they cannot even stand in for a model–model agreement figure. | As above. A cheaper proxy is having a second model re-draft chapters 1–5 blind and computing κ, labelled as model–model agreement. |
| Coreference on **non-trivial** gold | Blocked by data | Two of three silver files are **100% surface-trivial**: a string matcher reproduces their partition. B³ 98.1% and MUC 98.4% on the 1,816-record set therefore measure string matching. CEAF-e (63.1%) is the only discriminative number on it. | Annotate more hard cases. The hardcases file has 89 records over 51 chapters, which is too sparse for coreference metrics. |
| **Hard-case accuracy by category, end to end** | Measured 2026-09-25, small n | `scripts/hardcase_resolution.py` (SCORER_DIAGNOSIS Section 4a): 29 of 88 detected; of the decidable ones, **23 of 23 linked correctly, 0 wrong, 0 deferred**; 6 undecidable (gold identity unmapped). The resolver is precise on what it sees, and the loss is at detection. | More hard-case annotation. n ≈ 23 cannot support a per-category precision figure. |
| **LINK / NEW / DEFER decision accuracy** | Not measurable | No labelled decisions exist. All 103 labelled gold candidates are decided by pre-filters, so none reach the scorer. DEFER fired on 2 of 1,532 groups. | Blind-annotate a sample of `SCORE`-verdict pairs (`eval/blind_review.py` exists for this). About 200 pairs is roughly 3 hours of human work. |
| **Review burden / escalation rate** | Measured, but degenerate | The escalation rate is **0 of 703 LLM calls**. The review queue is effectively empty, so non-negotiable 7's "bounded, measurable review queue" is bounded at zero. That is either excellent or a sign the ladder cannot fire; nothing distinguishes the two. | A corpus or a fault injection that forces escalation, to show the ladder works when needed. |
| **Held-out conformal coverage** | Not evaluable | "No held-out pairs after the chapter-0 split": calibration has nothing to hold out, because pre-filters decide every labelled pair. | Same fix as LINK/NEW/DEFER: labelled SCORE-region pairs. |
| **Scorer contribution** | Measured: **zero** | Under all 8 cache-answerable ablation conditions (Table 6), "scorer would link" is 0. Output is capped at p = 0.550 against a threshold of 0.80, and three features are inert. A refit does not help. | A design decision, not a measurement: retire the scorer, or make it comparative (rank plus margin). Ranking is already 94.2% correct. |
| **Speaker attribution accuracy** | Coverage re-measured; precision spot-checked only | 46.1% attributed after the fix (EVOLUTION 4.88). Precision exists only as LLM-judged spot checks: the pronoun pass was right 2 times in 15 (now opt-in), and the real LLM tier 12 right / 16 wrong over ch1-3. | A labelled speaker set (human-only for a real number). Until then, make casting respect span confidence. |

### 1.2 Baselines and external comparison

| Metric | State | Why |
|---|---|---|
| Baselines on the **full volume** | Not run | A and B ran on chapters 1–10 only. B takes 177 calls for 10 chapters, which extrapolates to about 3,500 calls and roughly 2.4 h of GPU time per volume. |
| Baselines on **non-trivial** gold | Blocked by data | Chapters 1–10 silver gold is surface-trivial, so the B³ columns (A 0.2%, B 4.6%, EchoTales 79.1% on the same range; Table 7) measure extraction coverage, not coreference quality. |
| A **GraphRAG / CORE-KG** baseline | Not built | These are the baselines LINK-KG itself used. Neither is implemented here. |
| **BOOKCOREF / LitBank** numbers | Not run | This is the only route to an externally comparable, non-silver figure. It needs an adapter from their formats to `GoldMention`, and those corpora do not contain the transfer and disguise phenomena this project targets. |
| **Generalisation** to LOTM / ORV | Measured on LOTM ch1–3 only (EVOLUTION 4.90) | Current code on LOTM ch1–20, scored on 155 independent silver records: B³ recall 62.3%, CEAF-e F1 41.4, well below RI; the transmigration (Zhou Mingrui / Klein) is split into two Selves. ORV has only circular records. LOTM full volume is not scored. |

### 1.3 Ablations that need a re-resolve

The ablation cache answers 8 conditions (`docs/paper/TABLES.md` Table 6).
Three are **not answerable from it** and have never been run:
- `no-alias-typing`: alias type is assigned upstream of evidence capture.
- `no-self-persona-split`: changes which entities exist.
- `no-truth-status`: changes what `state_of` returns.

Each needs a full 199-chapter re-resolve with the mechanism disabled. That is about 47 min per condition on the local GPU, plus a code flag for each that does not exist yet.

There is also no **visual ablation** (render with a flat, non-temporal state versus `state_of`). That is the render-side twin of the resolver ablations, and plans.md treats it as central.

### 1.4 Visual generation

| Metric | State | Why |
|---|---|---|
| **CLIPScore** / prompt–image alignment | Not run | The 1.7 GB CLIP ViT-L/14 download was never made. `RUNPOD_MIGRATION.md` Section 5 lists it as the cheapest high-value paid item, though it runs locally too. |
| **Character identity consistency** (face or embedding similarity across panels) | Not built | No metric exists. Consistency is judged by eye in `VERSIONS.md`. |
| **Human preference / quality rating** | Human-only | None. |
| Observer contrast **at scale** | 5 panels, 1 chapter | It demonstrates the mechanism (reader 5/5 conditioned, non-reader 0/5), but it is not a benchmark. |
| **Two depictions of one character** by observer | Blocked by data | This needs a sustained disguise, and Reverend Insanity has none. |
| Per-panel wall time on a larger GPU | Not run | Planned for the first RunPod session. |

### 1.5 Audio

| Metric | State | Why |
|---|---|---|
| **MOS / listening test** | Human-only | None. The EARS render (ch1, 97 lines, 892 s) has not been rated by anyone. |
| **Speaker similarity** (embedding cosine between clip and reference) | Not built | Straightforward with an ECAPA model, but not done. |
| **Voice–character fit** (gender or age mismatch) | Not measured | One observed mismatch: a line spoken by a woman, voiced by a male speaker, caused by attribution rather than casting. |
| **Temporal voice state** | Not built | The voice path never calls `state_of`, so Zhou Mingrui and Klein Moretti would sound identical. |

---

## 2. Architecture: designed or partial, not delivered

| Mechanism | State | Evidence |
|---|---|---|
| Retraction as distinct from interval end | Query semantics implemented and tested; **the writer has no caller** | `retract_alias_bindings` has zero callers, and `retracted_chapter IS NOT NULL` returns 0 rows in every database. |
| Story-time axis (dream, flashback) | Defined; **no fact is ever written off `MAIN_TIMELINE`** | Segments are detected, but facts are never attached to them. |
| Concurrent Self/Persona (disguise, possession, body-swap, clone, dream persona) | **Unit tests only** | The real corpus contains only sequential reincarnation (Fang Yuan, body1 → body2). |
| Observer-scoped persona bindings | Column exists; **no writer** | A witness learns the alias but not the persona, so a witness-conditioned render drops the character (`SELF_PERSONA_VALIDATION.md` Section 3). |
| Shared multimodal `GenerationState` | **Not built** | The visual path consumes `state_of` through `build_render_plan`; audio does not. `state.py:6` still implies otherwise. |
| Aliases in the render read set | **Missing** | The render digest hashes persona ids and attributes, not aliases, so a name-only reveal does not invalidate a panel. |
| Transmigration merge (one Self, new Persona) | **Not built** | LOTM ch1–3: Zhou Mingrui and Klein resolved as two Selves (EVOLUTION 4.90). |
| Detection of relational / deictic and title spans | **Weak** | 25 of 29 relational and 16 of 17 title mentions are never detected. This is the real bottleneck for the hard cases. |
| Bounded LLM investigator for uncertain pairs | **Not built, deliberately** | There are no labelled SCORE-region pairs to show it would help ("do not add architecture to make claims true"). |

---

## 3. Open defects

1. **Speaker attribution**: the real LLM tier (ch1-3) credits lines to vocative addressees and absent characters (EVOLUTION 4.87/4.88). The worse, pronoun-based pass is now opt-in. Voice casting ignores span confidence.
2. **Silver span drift**: 7 records past the end of ch1 on the rerun database. The new ingest correctly drops the author's note (`GOLD_DATASET_README.md` Section 5, item 7).
3. **Two hardcases records need adjudication** (`GOLD_DATASET_README.md` Section 5, items 2–3): one `not_an_entity` record carrying an identity, and one within-chapter identity conflict. This is human-only.
4. **Render pipeline items** from EVOLUTION 4.51/4.52 are still open (see `HANDOFF.md`).
5. `render/reels.py` has no ffmpeg call, and no standalone per-chapter audio artifact exists.
6. `render_novel` has zero direct test coverage (`STATUS.md` Audio/TTS row).

---

## 4. Patent disclosure (VIT filing)

| Gap | Why it matters |
|---|---|
| **The repo has been public since 2026-08-07** | Prior public disclosure is counsel's first question. Grace-period rules are jurisdiction-specific. |
| **Narrative Graph Prompting (ICCVW 2025) and StoryWeaver (2024) are unread** | Both are close prior art for graph-conditioned story visualisation. They must be read before filing. |
| **CORE-KG unread** | It is LINK-KG's own baseline and may sit closer to this work. |
| **Temporal KG literature not searched** | Bitemporal and knowledge-time modelling has a database and TKG literature, and it has not been surveyed. |
| **Mechanisms M2–M4 are EXPERIMENTAL or DESIGNED** | Retraction, concurrency, and observer-scoped bindings are not demonstrated on real data (Section 2). A claim resting on them rests on tests. |
| **Every "potentially differentiating" line says ASSERT — VERIFY WITH COUNSEL** | Nothing here is a legal opinion. |

The disclosure itself lives in `docs/IP/` (gitignored, never committed).

---

## 5. University report

- Complete author lists for references 3–12 (`REPORT_MATERIAL.md`). Only LLMLINK and LINK-KG have been read in full; the others are cited from abstracts.
- The ≥5-papers-per-member related-work requirement needs each member to confirm their papers and write their own limitations paragraph (human-only).
- Team confirmation of the Section 7 work split.
- Draw the 7 hand-drawn diagram figures (`docs/paper/FIGURES.md` Figures 1–7).
- Figures 6a, 8, 9 and 10 are rendered as SVG (`scripts/plot_paper_figures.py`, `docs/paper/figures/`) from generated CSVs. Only Figure 11 (escalation, all zeros) and the seven diagrams remain.
- Figure 11 (escalation) stays a sentence rather than a chart: it would be a bar chart of zeros.

---

## 6. Reproducibility and hygiene

| Item | State |
|---|---|
| Branch `validation/evidence-pass-2026-09-24` | **50+ commits, not pushed, not merged to `master`.** A disk failure loses the whole pass. Pushing is the owner's call, because the repo is public. |
| Canonical database | **Promoted 2026-09-25**: `data/reverend-insanity.db` (sha256 `42107645…`), built from scratch by the current code (`docs/CANONICAL_RUN.md`). The webview still defaults to `data/webview-working/`. |
| `.env` API keys | Never committed, but printed into an earlier session. **Rotate them.** |
| Lint / types | Clean on touched files. Repo-wide, `mypy` reports `import-untyped` noise, and `cli.py:567` has one pre-existing ruff SIM105. |
| Venv drift | `chatterbox-tts` 0.1.7 and `setuptools` 80.10.2 are installed directly in `.venv`. The documented route is the `uv run --with` overlay. |
| `reproduce_results.sh` | Runs end to end (exit 0, 2026-09-25) against an **existing** database. It cannot regenerate one from a clean checkout, because the source EPUBs are copyrighted and never committed. |
| Eval outputs | Every table in `docs/paper/TABLES.md`, including the baseline comparison (Table 7), names its source file, gold file, and database. |

---

## 7. What only a person can do

1. Annotate 3–5 chapters as human gold, with two annotators for IAA.
2. Blind-label about 200 SCORE-region pairs, which unblocks the scorer, calibration, and the investigator question.
3. Adjudicate the two flagged hardcases records.
4. Listen to the EARS render and rate it; rate a sample of panels.
5. Read Narrative Graph Prompting, StoryWeaver, and CORE-KG before filing.
6. Decide on pushing the branch, promoting the database, and rotating keys.
7. Give the team's confirmations for the report.

## 8. What does **not** need doing

- More resolver tuning on silver data. A negative result (scorer contributes 0) is already established and documented.
- A rented GPU for anything except the four items in `RUNPOD_MIGRATION.md` Section 5.
- Building `GenerationState`, the investigator, or concurrent-persona writers *to make a document true*. Each should wait for a measurement that justifies it.
