# CHIMERA novelty gate (Checkpoint 1, Gate 4 preparation)

| Field | Value |
|---|---|
| Commit | `6c7e2c2`, 2026-10-15 |
| Inputs | `CHIMERA_REPOSITORY_AUDIT.md`, `CHIMERA_PRIOR_ART.md`, `CHIMERA_COMPONENT_MATRIX.md`, `CHIMERA_DATA_AND_BENCHMARK_PLAN.md`; the existing ledger `ECHOTALES_NOVELTY_LEDGER.md` (not contradicted, only extended) |
| Ran | Nothing new. No experiment, no model, no paid call |
| Verdict | **No candidate passes the gate today.** None is killed either. Reason in section 1 |

## 0. The gate

A candidate passes only if all six hold: (1) the closest work lacks the substantive mechanism; (2) it is more than connecting components; (3) it addresses a meaningful failure; (4) a strong baseline is implementable; (5) a plausible result could falsify it; (6) it fits the repo, data and budget. "Passes" means the evidence needed to *start* building exists. It does not mean the idea is novel in the field.

## 1. Why nothing passes yet (the shared blocker)

- **There is no human-verified label for any EchoTales item.** 0 confirmed records across all six gold files; the 288-item package is model pre-labelled and unadjudicated. [INSPECT, see data plan] So criterion 5 (falsifiability on real data) cannot currently be met for C1, C2 or C3; the tests that would meet it (T1-T6) are designed and not run.
- The closest published systems (NWM, NarraWorld) already implement chapter-safe or admissible-view reads, observer/belief views and provenance, so the architecture alone is not a contribution. [PUB, prior-art rows 1.2, 1.3]
- The real data cannot exercise the interesting axes: the RI database has 0 retracted rows, 0 relations, and 12 observation rows. [INSPECT]

## 2. Re-ranking (my ranking; it differs from the seed order)

| Rank | Candidate | Why this position | Gate status |
|---|---|---|---|
| 1 | **C5** floor: systems/findings paper with negative results | Evidence already exists in the repo and is partly strengthened by this audit (e.g. no human gold, silver-only numbers, scorer links nothing, `retry_deferred` counts, reference conditioning off). Needs no new labels to be honest | Always alive (floor) |
| 2 | **C3** title-aware detection (engineering) | Diagnosed causes in code; $0 CPU; measurable target. But it is **not** a contribution on identity, and its evaluation needs human-verified hard cases | Not a novelty candidate; a workstream. Blocked on labels; GenWebNovel is Chinese text and cannot test the English mention layer |
| 3 | **C1** disclosure-faithful identity under parametric leakage | The only candidate with a cheap, decisive kill test (T3) and a meaningful failure. Prior art overlaps on each ingredient (renaming control 2412.14368; admissible views NarraWorld/NWM; reader vs omniscient KoCoNovel). The combination on identity over long serials is not shown covered, **but I only did partial reads** | Pending T3, T4, T6; needs reader-view labels |
| 4 | **C2** long-span identity benchmark | KoCoNovel precedes the reader/omniscient design, though its documents are short. The translation-share angle needs GuoFeng, whose licence and contents I did not open. Annotation cost is the real constraint | Pending D5, licence check, T5, T6 |
| 5 | **C4** progression-aware disclosure-safe state for multimodal adaptation | Overlaps NWM and NarraWorld on the state side; the visual-lineage side overlaps CANVAS and an unlocated "VividWorld", neither read. Production has no reference conditioning, so a visual claim has no downstream effect to measure. Real data has no retractions or relations, so a leak class beyond "cutoff filter + short label check" cannot be shown | **Fails today.** Reopen only if a named leak class is found that the cutoff filter cannot catch, shown on real data |

I disagree with the seed order in one place: C3 ranks above C1 as a *workstream* because it is actionable now, but it does not compete as a *paper* candidate.

---

## 3. Candidate sheets

### C1. Disclosure-faithful identity resolution under parametric leakage

| Field | Content |
|---|---|
| Formal task | Given a text prefix of chapters 1..c, a mention m at position <= c and a candidate set of entities, output the entity the **reader at c** is warranted in linking m to, or abstain. Distinguish the reader-warranted label from the final-truth label on items where they differ (hidden identities, title transfers, disguises, body changes) |
| Input / output | Prefix text, mention span, candidates -> link or abstain plus the citing spans |
| Falsifiable novelty sentence | "On identity items where reader-warranted and final-truth labels differ, an LLM-based resolver links prematurely at a rate that exceeds chance because of parametric knowledge of the novel, and an evidence-gated link rule (a link must cite in-prefix spans that entail it, names masked) lowers that rate below what whole-input renaming achieves." Each clause is testable |
| Closest prior art and exact difference | **2412.14368**: renaming as a memorisation control for character reasoning (does not address linking against a reader-warranted label, per the sections I read). **NarraWorld / NWM**: admissible-view and chapter-safe reads (memory-level filtering; no leakage control found by keyword search). **KoCoNovel**: reader vs omniscient labels (short stories, coreference, no leakage measurement). **TimeChara** [LEAD]: point-in-time hallucination in role-play, not identity linking. Exact difference to establish: the premature-resolution metric on long serials, and mechanism vs plain renaming |
| Minimal mechanism | A link is accepted only if a deterministic check finds, inside the prefix, spans that entail it with names masked |
| Strongest simple baseline | Renaming the whole input consistently (pure function) plus the existing deterministic resolver |
| Strongest published baseline | Prefix-only memory systems (NWM-style chapter-safe packet) with an LLM resolver |
| Datasets | RI/LOTM/ORV as local; hard-case slice; KoCoNovel only as a protocol reference |
| Required annotation | Reader-view and omniscient-view labels on the hard cases, two annotators on at least 20% (D5, T6). **Does not exist** |
| Metrics | Premature-resolution rate; leakage = change between original and renamed text; abstention rate; precision and recall on non-hidden items to show no collapse |
| Ablations | Remove masking; remove gating; renaming vs gating vs both |
| Failure modes | Renaming destroys evidence (T4); leakage not above chance (T3); labels cannot reach kappa 0.7 (T6); gating cuts recall excessively |
| Cost | $0 for T4; T3 needs local-model inference approved per run (D4); annotation human time |
| **Rejection criteria (pre-registered)** | T3 recall not above chance -> C1 dies. T4 agreement under 98% -> renaming control invalid, redesign. T6 kappa under 0.7 in either view -> labels unusable. Mechanism not better than renaming in a paired test -> no mechanism contribution |

### C2. Long-span identity benchmark for translated web serials

| Field | Content |
|---|---|
| Formal task | Resolve alias-to-identity links over long reveal distances in English translations, scored under reader and omniscient views |
| Falsifiable novelty sentence | "A benchmark of translated web-serial identity items with reader and omniscient labels and reveal distances above N chapters has at least a 15-point headroom gap between easy and hard slices for existing tools, and at least 10% of hard alias pairs are introduced by translation." |
| Closest prior art | KoCoNovel [PUB]: reader/omniscient versions, 50 short Korean stories. FantasyCoref and BookCoref [LEAD]. GenWebNovel [PUB]: Chinese mention recognition only. Difference to establish: reveal distance, serials, translation decomposition |
| Baselines | BookNLP, Maverick, existing mention layer (T1, T2) |
| Annotation | Large; two annotators on 20%; D5 open |
| Rejection | T2 gap under 15 points; T5 share under 10% (drop the translation angle); T6 kappa under 0.7; GuoFeng not licensed for the decomposition |
| Cost | Mostly human time. Dataset release is also constrained by D2 and copyright (the source texts cannot be redistributed; only offsets and checksums, as GenWebNovel does) |

### C3. Title-aware mention detection (workstream, not a paper claim)

| Field | Content |
|---|---|
| Task | Raise detection of transferable-title and relational-deictic mentions without adding false entities |
| Mechanism | Pass `is_address`; widen or learn the title list; revisit `AMBIGUITY_BLOCKLIST` and the commonness filter for deictics |
| Baseline | Current detector (58 of 88 hard cases undetected on silver; at most 55 real) |
| Evaluation | Recall on **human-verified** hard cases and precision on the *added* mentions; GenWebNovel is not applicable to the English layer without a Chinese path (data plan finding 3) |
| Rejection | Added-mention precision below the precision of the current detector, or no downstream resolution gain |
| Note | Any gain is engineering. It also changes how existing numbers read, so it should be done after human labels exist, or silver numbers will move without meaning |

### C4. Progression-aware, disclosure-safe state reconstruction for multimodal adaptation

| Field | Content |
|---|---|
| Task | Reconstruct state for story position p, disclosure cutoff k, observer o, with retractions and asset lineage, for rendering |
| Prior art | NWM [PUB] (chapter-safe reads, reveal order, observer); NarraWorld [PUB] (admissible views, beliefs, validity intervals, provenance); CANVAS, FilmWorld, "VividWorld" not read or not found |
| Why it fails the gate today | (a) the repo ledger already reduces it to snapshot reads plus an information-flow check; (b) production has `reference_images=[]`, so visual lineage has no effect to measure; (c) the real database has no retractions or relations; (d) no leak class beyond a cutoff filter has been named |
| Reopen condition | A concrete leak that "cutoff filter + short transitive label check" misses, shown on real data. The audit surfaced real, *integration-level* leaks (wiki canon, `appearance_of`, audio, brief) but those are bugs fixed by routing through `state_of`, not a new mechanism |

### C5. Floor: systems/findings paper

| Field | Content |
|---|---|
| Claim set | Only what the repo can support: pipeline description; the finding that gold is model-provenance; the scorer diagnosis; hard cases are lost at detection (with the corrected 58/88 and the control and span-defect caveats); the measured failure of existing baselines on a surface-trivial subset reported as cost and failure shape; the integration defects found in this audit |
| Needs | No new labels to be honest; benefits strongly from the 288-item adjudication |
| Venue | The repo's own analysis (2026-09-25) names WNU 2027, ACL 2027 System Demonstrations and the January 2027 ARR cycle; I did not re-verify those dates. The October 2026 ARR deadline (2026-10-12) has passed (per the directive) |
| Risk | The public repo is already visible (audit section 1). That affects D2 timing, and a reviewer can already see the branch |

---

## 4. Cheap falsification tests (status)

All designed in the data plan; **none run**. T3 and T4 are the highest-value, because they decide C1 at $0 to small cost.

| Test | Decides | Needs before running |
|---|---|---|
| T4 renaming validity | C1 control validity | Nothing but approval to run in a scratch copy (CPU, deterministic) |
| T3 memorisation probe | C1 | D4 (local model, owner's GPU, asked each time) |
| T6 agreement | C1, C2 | D5 and an annotation protocol |
| T1, T2 | C2, C3 headroom | Human-verified chapters; BookNLP/Maverick runs; check their licences |
| T5 | C2 translation angle | GuoFeng licence and contents |

## 5. Recommendation for this gate

**INSUFFICIENT EVIDENCE** to pass any candidate. Not NO-GO, because C1 has a cheap decisive test and C5 is intact; not CONDITIONAL GO, because every candidate that matters needs human labels that do not yet exist and the closest prior art for the state-and-memory side (C4) is already substantial.
