# Evidence-horizon honesty in a position-filtered narrative knowledge graph

Status: DRAFT 2026-10-16. Branch `claude/prefix-faithfulness` (worktree), nothing committed. Label provenance is stated per section: 4.1 to 4.8 are **SYSTEM-INTERNAL** (no labels; the oracle is the system rebuilt on truncated input); 4.9 to 4.12, 4.14 use **MODEL-GENERATED** labels (two model annotators, no human labels); 4.13 is **SYNTHETIC** (truth set by construction); 4.8a and 4.15 run a real local model (`qwen2.5:7b`). Spend on OpenAI `gpt-5.6-luna`: $0.1140 in total ($0.0524 strict labelling and $0.0006 smoke test under the owner's instruction to use Luna, $0.0325 permissive re-read and $0.0285 public-domain labels from the owner's extra $0.20 grant); everything else is CPU or the local GPU at $0. Pre-registrations (each written before the run it governs, with dated addenda): `PREREG.md`, `PREREG_LLM.md`, `PREREG_LABELS.md`, `PREREG_ANCHORED.md`, `PREREG_SYNTHETIC.md`, `PREREG_PD.md`.

Evidence tags: `[RAN]` produced by a command this session; `[INSPECT]` read in code; `[SUMM]` a page read through a summarising fetch tool, not verbatim; `[LEAD]` seen only in a search snippet or abstract; `UNVERIFIED`.

## 0. Bottom line (current, end of 2026-10-16)

1. **The defect is real and general across the data I could test.** A derived fact (a persona trait) is stamped with the chapter of first sighting but computed from up to 12 later chapters, so the position-filtered reader query serves values a build over the prefix does not hold. Gender diverges on 6.0% of 685 character-cuts of three translated web novels (4.5% to 8.0% depending on where the cuts fall), 4.5% of 179 on two English originals (*Oliver Twist*, *The Three Musketeers*, PD1 supported) and 9% to 17% of pairs on a synthetic volume with known truth, where the mechanism and its dose-response are checked without any annotator (4.13).
2. **Most of the divergence is not a spoiler.** With the second model annotator the premature-disclosure rate is 2.6% of character-cuts (2.0% with a permissive prompt; 1.7% by my labels on the original cuts); the rest of the diverging values were already supported by the text up to the cut. A rate of 0 is excluded by all three readers (4.10, 4.12). Honest range, not a point.
3. **Three repairs, measured.**
   - The horizon repair (revisions stamped by evidence horizon) drives divergence to exactly 0 in every real, public-domain and synthetic run. It buys safety, not correctness, and costs about 1 to 4 text-supported values per premature disclosure removed (4.9, 4.10). Hiding exposed facts instead is worse than doing nothing (4.6).
   - An anchored pronoun cue closes that price on the web novels: pre-registered H5 supported (97% of the lost correct values recovered, 1.2% wrong, same setting chosen in every leave-one-serial-out fold, holds with each annotator alone; 4.11). It transfers only partly to the English originals (availability gain yes, precision 73% to 88% and a pre-registered 3% bar failed because the base extractor is already 6.7% wrong there; 4.14), and the synthetic failure map shows when it breaks (4.13).
   - The model path's prominence gate (`mention_count >= 25` over the whole volume, 37 of 50 gate pairs changing a trait) is repaired by deciding the gate on the mentions read so far: gate pairs 50 to 0 of 296, 0 divergences in 101 both-model pairs, noise floor 0, call count unchanged (4.15).
4. **Not shown.** No human labels (a 30-character sheet is prepared and unfilled). Body splits (7 of 296) are not repaired; appearance and world facts are not measured. One persona stage (one codebase), five real volumes. The cue is English-translation specific and its precision varies by text; the second domain's mention layer is a gazetteer, not the resolver. Cut positions are nested, so intervals are optimistic.
5. **Novelty rating: narrow, better supported than at the start.** The stamp-versus-horizon rule is point-in-time correctness, not new, and the versioned repair is structurally the stream-processing idea of emitting early results per watermark and revising them (the Dataflow model's accumulating panes; section 5). What is defensible is the combination, measured: an audit of position-stamp honesty in a deployed narrative graph, replicated on three kinds of data, with a pre-registered repair frontier (honest stamps alone are worse than the defect; the principled repair is safe but over-conservative; a cue and a gate fix recover most of the price) and a failure map. It is a method-and-measurement contribution, not a new algorithm, and still one system.

### 0.1 First-pass bottom line (kept for the record; superseded where 4.9 to 4.15 differ)

1. **What is shown.** In the deterministic persona stage, the trait facts that `state_of(READER)` serves at the end of chapter k are, for 23 of 289 character-cuts (8.0%, Wilson 95% [5.4%, 11.7%]), different from the facts a graph built from chapters <= k alone holds. All 23 are gender (and the archetype string derived from it). The cause is a mismatch between the stamp (chapter of first sighting) and the evidence the value is computed from (up to 12 later chapters). `[RAN]`
2. **What was done about it.** A repair that writes each trait as revisions stamped by their evidence horizon brings the divergence to 0 of 289 (Wilson [0%, 1.3%]) on the same 13 cuts. Cost: 19 more character-cuts with an `unknown` gender (39.8% to 46.4% served unknown), 9% more attribute rows, about 50% more persona-stage time (9.1 s to 13.8 s over three volumes). `[RAN]`
3. **Beyond the persona stage.** An inventory of all 12 stamping sites (4.7) finds the same stamp-versus-evidence mismatch in two more stages (body splits, measured at 7 of 296 cuts; unnamed title holders, one verified example with a 61-chapter window) and shows the project had already fixed the same class for appearance, which supports the claim that this is a systematic failure mode of position-filtered graphs, not a one-off bug.
4. **What is not shown.** Body-split differences (7 of 296) are not repaired. The LLM trait path is audited (4.8a: no content leak at these settings, but the whole-volume gate changes a discrete trait in 37 of 296 character-cuts) and not repaired; appearance and world facts are still unmeasured. `big_five`'s whole-volume dependency is never exercised on the real data (no character has a dialogue line in its evidence sample), so its 0 divergences carry no weight there; it is covered by a synthetic unit test instead. Three serials, one system, and the resolution is held fixed (section 3).
5. **Novelty rating: narrow.** An audit with a design rule and a small repair, not a new algorithm. The contribution is the measurement, the static exposure screen and the safety-versus-availability numbers; every ingredient has precedent (section 5). The "horizon = max over inputs" rule is **not new**: it is point-in-time correctness, a standard concern for derived features in ML feature stores (section 5). What I could not find is an audit of it on narrative or reading-position stores; that absence is a bounded search negative, not a confirmation.

6. **Checked against labels (4.9 and 4.10, `LABELS: MODEL-GENERATED`, two model annotators, no human labels).** Over 685 character-cuts (the original 13 cuts plus 11 added), 41 diverge (6.0%; 4.5% to 8.0% depending on where the cuts fall). Of the 41, 18 (2.6% of all cuts, 11 characters) are premature disclosures by the second annotator's labels and 21 were already supported by the text; by my own, more permissive labels the original-cut figure is 1.7% rather than 3.5%. So the reader-visible harm is roughly 1.7% to 3.5% of character-cuts, not 8.0%, and the repair removes it by withholding about one to four values the text already supported per premature disclosure. The repair buys safety, not correctness (wrong values: 5, all one character, identical in every build).

## 1. Why this is the engineering candidate worth keeping

Triage of the four candidates from the engineering-audit report, after reading the probe notes (E1-E6) and searching the literature:

| Candidate | Verdict | Reason |
|---|---|---|
| Prefix-causality (E1 + E6) | **Kept; this report** | The only one with a measured violation on real data, a mechanism traced to two lines of code, and a repair that removes it. |
| Resolver as string lookup (E5, E2) | Not claimed | 95-97% of assignments equal "same normalised string, same entity" and the compounding curve sits inside a chapter-shuffle null. That is a negative audit of a claim in the project's own docs (non-negotiable 8), useful as honesty, not a contribution. Not re-run here. |
| Observer-global retraction (E3) | Not claimed; documented gap | A real modelling gap, zero instances in the real data. The formal theory exists (multi-agent belief revision, `[LEAD]`: Lorini and Schwarzentruber, IJCAI 2021). Only the narrative-store framing would be ours. The optional extension in the plan was not attempted. |
| Discourse-position order (E4) | Not claimed | An integrity defect (same-chapter order agrees with text order 47-58% of the time) with no downstream error today. Fix it, do not publish it. |

## 2. The claim, and what it is not

> For a fact derived from text, prefix-causality (the value `state_of(READER)` serves at position k equals the value a build from chapters <= k would hold) requires that the fact's knowledge-time stamp be at least its **evidence horizon**, the latest input position it was computed from. A stamp below the horizon is checkable without a rebuild. Stamping honestly is not enough on its own: the value must also be *versioned* by evidence prefix, or the reader gets a hidden fact where a prefix build would hold an earlier value.

Not claimed: that the full-graph value is *wrong* (there are no labels; a character introduced in chapter 4 may well be male). The claim is that the value is **not what a reader of chapters <= k can know**, which is what the reader-observer query promises.

The second sentence is tested as an ablation in 4.6: hiding every exposed fact (the honest-stamp-only repair) diverges from a prefix build on 82 of 289 cuts, more than the 23 it started with, because it also hides values the prefix build already held.

## 3. Method (what changed from the pre-registration)

- **Oracle (E6's).** Full-volume graph versus a graph from chapters <= k, compared with `state_of(READER)` at `position = k + 0.5` and `knowledge_pos = (k, 10**6)`, for every person with a persona fact in both. Cuts: LOTM 5/10/20/30, ORV 5/10/20/30, RI 10/20/40/80/120 (13 cuts, 289 character-cuts; the cuts are nested, so the pairs are not independent).
- **Amendment 1 (before any result).** `resolve_novel` at this worktree's HEAD lacks the `chapters`, `prefix_volume_passes`, `causal_titles` and `apply_deferred_links` parameters that E1 and E6 used; those exist only in the other session's **uncommitted** edit of `resolve/runner.py` (verified with a plain `diff` of the two files). The audit therefore does not re-resolve: both graphs start from the stored mention-to-entity assignment, and the prefix graph deletes every `chapter`, `span`, `mention` and `narrative_segment` row after k. This tests the persona stage in isolation, conditional on a fixed resolution, and is independent of unmerged code. The resolver's own causality (E1) is not re-tested.
- **Static side.** A fact is *exposed* at k if `stamp <= k < horizon`. Horizons per key were derived by reading `persona/build.py` and `persona/traits.py`: `gender`, `age_band`, `register`, `archetype` read the first 12 attested chapters; `big_five` additionally reads the whole-volume mention count when dialogue lines > 0; body splits read the last attested chapter. `[INSPECT]`
- **Repair.** `build_personas(..., prefix_causal=True)`: for each attested chapter c, recompute the deterministic profile from the evidence and the cumulative mention count of chapters <= c, and write only the keys whose value changed, stamped `(c, 10**6)`. `state_of` already keeps the latest-stamped value per key (`core/state.py:298`), so no interval surgery is needed. Default is off. `[INSPECT]`

## 4. Results `[RAN]` (`data/eval/prefix_audit/summary.json`; regenerate with `scripts/prefix_audit/summarize.py`)

### 4.1 Baseline (repair off) and replication of E6

| | character-cuts | with a trait divergence | Wilson 95% | gender diverges | body-split (persona-set) diverges |
|---|---|---|---|---|---|
| this audit | 289 | 23 | [5.4%, 11.7%] | 23 | 7 of 296 |
| E6 (published) | 288 | 23 | | 23 | 7 |

Per serial (trait-facts that diverge, gender plus its derived archetype): LOTM 16 (8 character-cuts), ORV 10 (5), RI 20 (10). `age_band`, `register` and `big_five` diverge 0 times. One more character-cut than E6 (289 vs 288) comes from the fixed-resolution design; the headline counts coincide.

### 4.2 H1, soundness of the exposure screen: holds, with a caveat

0 divergences fall outside an exposure window (1,445 trait fact-cuts and 296 persona-set cuts). **Caveat: this is close to true by construction**, because the dependency table was hand-derived from the same code that was then audited; a table missing a dependency would have produced violations, and none appeared, but only dependencies that are *realised* in the data can be caught. The `big_five` whole-volume dependency was not realised (0 of 289 rows had dialogue lines in the sample), so it is untested on real data.

### 4.3 H2, usefulness of the screen: a conservative filter, not a predictor

| key | fact-cuts scored | exposed | diverged inside window | precision |
|---|---|---|---|---|
| gender | 289 | 139 | 23 | 16.5% |
| archetype | 289 | 139 | 23 | 16.5% |
| age_band, register, big_five | 289 each | 139 each | 0 | 0% |
| persona set (body splits) | 296 | 162 | 7 | 4.3% |

About half of all character-cuts (48%) are exposed to later evidence; about one in six of those realises a different value. The pre-registered 10% absolute precision bar was an arbitrary number (the registered wording only said the report would call it a necessary-condition screen below it), so the screen is also scored against fairer yardsticks, gender key: a flag-everything screen has precision equal to the base rate, 23/289 = 8.0%, so the screen's 16.5% is a **2.08x lift** at **100% recall** (23 of 23); and it **certifies 150 of 289 cuts (51.9%) as safe without a rebuild, with 0 divergences among them**. It is best read as a safety certifier, not a failure predictor. It never missed a divergence here, but it over-flags.

### 4.4 H3, the repair: holds for trait facts

| | character-cuts | with a trait divergence | Wilson 95% | body-split diverges |
|---|---|---|---|---|
| repair off | 289 | 23 | [5.4%, 11.7%] | 7 |
| repair on | 289 | **0** | [0.0%, 1.3%] | 7 (unrepaired, out of scope) |

Unit tests (`packages/pipeline/tests/test_persona_prefix_causal.py`, 11 tests): the defect is pinned on a synthetic three-chapter volume (gender evidence only in chapter 3; the unrepaired stage serves `female` at the end of chapter 2), the repaired stage equals a prefix build at every cut, and the extraversion path (dialogue lines over a growing mention count), which no real character exercised, is covered. The default path writes byte-identical rows: 232 rows with the same SHA-256 prefix from this worktree's code and from the unmodified main-tree code on ORV. `[RAN]`

### 4.5 H4, the cost of honesty

| | repair off | repair on |
|---|---|---|
| gender `unknown` among 289 character-cuts, as served | 115 (39.8%) | 134 (46.4%) |
| gender `unknown` in a prefix-only build (the honest value) | 134 (46.4%) | 134 (46.4%) |
| attribute rows, 3 full builds | 1,074 | 1,172 (+9.1%) |
| persona-stage seconds, 3 full builds | 9.1 | 13.8 |

The unrepaired stage anticipated a gender for 19 more character-cuts (6.6 points) than a reader of the prefix could know (net of 21 anticipations and 2 reversals reported by E6). Whether that is a defect or a feature depends on the consumer: voice casting for an audiobook that must pick a voice before the reveal wants the anticipation; a reader-synchronised assistant must not have it. This is the safety-versus-availability trade-off, measured at one point (honest, all-or-nothing); an intermediate setting was not built.

### 4.6 Ablation: is an honest stamp enough? No. `[RAN]` (summarize.py; values stored by audit.py)

Three ways to serve gender at the end of chapter k, scored against a prefix-only build over the same 289 character-cuts:

| repair | serves a value the prefix build lacks (leak) | hides or changes a value the prefix build held (loss) | total divergence |
|---|---|---|---|
| none (status quo) | 23 | 0 | 23 |
| hide-only: hide every exposed fact (fall back to `unknown`) | 0 | 82 (80 hide a value the full build agrees with; 2 hide a value the full build would have changed) | 82 |
| versioned by evidence horizon | 0 | 0 | 0 |

The coarse horizon marks 139 cuts as exposed, but only 23 would have leaked; hiding all 139 discards 80 gender values that a reader of the prefix could already have had. Honest stamping alone therefore **removes the leak and creates 3.5 times as many losses** (80 against 23). Versioning, which recomputes the value from the prefix, is what achieves both. Decomposition of the 139 exposed gender cuts (prefix value, full value): male-male 65 and female-female 15 (80 settled before the horizon; these are the values hide-only destroys), unknown-unknown 36, unknown-to-known 21 (18 male, 3 female; the leaks), female-to-unknown 2. The coarse horizon over-approximates: in 58% of exposed cuts the value was already final in the prefix. A closed-form statement (hide-only minus status quo equals B minus A) and its mechanical check are in `FORMAL.md`. Hide-only was scored from stored values, not built as a separate stage, and only for gender (the one key that diverges); other keys fall back to defaults that I did not model.

### 4.7 Is it only the persona stage? An inventory of every stamping site `[INSPECT]` unless marked `[RAN]`

12 sites in 11 files write a time-stamped fact (grep of `learned_at_pos=` at this worktree's HEAD, plus `persona/build.py`). The other session has uncommitted edits to `resolve/runner.py`, `resolve/title_holders.py`, `persona/canon.py` and `world/context.py`; this table reads HEAD, not those edits.

| site | stamp rule | evidence the value depends on | class | status |
|---|---|---|---|---|
| alias linker, `resolve/runner.py:406` | the mention's own position | the mention and earlier state | prefix-causal | measured exact by the other session's E1 (0 of 28,165 mention-cut pairs differ; uncommitted code, not re-run here) |
| persona traits, `persona/build.py` | first sighting | up to 12 later chapters, plus the whole-volume mention count | **not causal** | `[RAN]` 23 of 289 character-cuts; repaired behind a flag |
| body splits, `persona/split.py:862` | position of the change | a change is only confirmed if the entity is attested enough chapters after it, counted over the whole volume | **not causal** | `[RAN]` 7 of 296 cuts; unrepaired (needs binding supersession in `state_of`) |
| unnamed title holders, `resolve/title_holders.py:516` | chapter of the first mention | the identity exists only once at least `MIN_UNNAMED_MENTIONS = 3` qualified mentions occur in the volume | **not causal** | `[RAN]` RI has 1 such identity: stamped chapter 125, created by the third mention at chapter 186 (a 61-chapter window); LOTM and ORV have none. n = 1, an existence example, not a rate |
| named title holders, `title_holders.py:451` and transmigration, `resolve/transmigration.py:155` | first mention or start chapter | tenure from declarations anywhere in the volume; a volume-wide merge | non-causal by design | not re-measured; the other session reports up to 39% of early LOTM mentions change under these passes (E1) and 40 of 40 retroactive links on synthetic worlds (M4) |
| appearance, `resolve/appearance_extract.py:1228`; world facts, `world/extract.py:295` | the earliest chapter whose passage grounds the value (`attesting_chapter`) | an LLM reads all passages | a deliberate, earlier fix of this same defect class | **not measured**: stub mode would audit the stub, so this needs the LLM-path audit. Untested concern: when passages conflict, the value is chosen by a model that sees later chapters |
| observations, `resolve/detect_observations.py:155` | position of the observed segment | that segment | looks local | not audited |
| voice override, `webview_server.py:1119`; reference-image markers, `persona/reference_gen.py:444`; scoped copies, `persona/scoped_reference.py:278` | chapter 0, first sighting, inherited | a production decision, not story content | by design / not narrative | not applicable |

Two readings. First, the project had already hit this defect class and fixed it for appearance: the docstring of `attesting_chapter` says that stamping at first sighting "asserts that a description revealed in chapter 90 was true -- and known to the reader -- from chapter 1". The persona traits are the instance that fix never reached, which is independent evidence that the class is natural to hit, not an exotic edge case. Second, the defect is not confined to one stage: persona traits, body splits and unnamed title holders show it, with measured counts for the first two and a single example for the third. Of the 12 sites: 1 is measured prefix-causal, 3 are measured non-causal here (persona traits, body splits, unnamed title holders), 2 are non-causal by design and measured only in aggregate by the other session (named title holders, transmigration), 2 are unmeasured because they depend on an LLM (appearance, world facts), 1 is unaudited (observations), and 3 are not narrative content (voice override, reference markers, scoped copies).

### 4.8 The model path of the persona stage `[RAN]` (fake client for the structure; real `qwen2.5:7b` for 4.8a; `PREREG_LLM.md`, Addenda 1 and 2)

The persona stage also calls a local model for characters with at least 25 mentions. The real run is reported in 4.8a. Before it, a dry-run with a client whose answers are hashed from the prompt separates what depends on the model from what does not:

| class of the 296 character-cut pairs | pairs | meaning |
|---|---|---|
| deterministic in both builds | 145 | covered by 4.1 to 4.4 |
| model in both builds | 101 | the prompt is identical in the full and prefix builds in all 101 |
| model in exactly one build (the gate) | 50 (16.9% of all pairs) | decided by the whole-volume mention count (`mention_count >= 25`) |

Two consequences, neither of which needed a GPU. (1) Where the gate passes in both builds the model sees the same 12 spoken lines and 6 narration samples (they come from the earliest attested chapters), so a temperature-0 model cannot differ except by noise: later-chapter *content* does not reach the model read. (2) The model path is not prefix-causal for a different reason than the deterministic one: the decision to call the model depends on how prominent the character becomes later. That is a leak of future prominence, not of story content, and it is reported as gate-induced divergence, not as a spoiler. How often the model's value differs from the deterministic value in those 50 pairs, and the nondeterminism floor, are the two things only the real run can measure. The fake-client run counted 218 calls for one pass over the three volumes and 13 cuts (359 with the noise-floor repeats), more than the 164 I first estimated, because body-change adjudication goes through the same client.

This gives the claim a second derivation mechanism with a different failure: the deterministic stage leaks through the stamp (evidence after the stamp), the model stage through the gate (a decision after the cut). The appearance and world-fact stages remain unmeasured (they need a model whose prompt contains all passages).

### 4.8a Real-model run `[RAN]` (local ollama `qwen2.5:7b` for both persona tasks, recorded in each output file; `data/eval/prefix_audit/llm_model_*.json`; 348 calls, $0)

Same 13 cuts, stored resolution fixed, each prefix built twice for the noise floor. The class counts equal the fake-client dry-run exactly (145 / 101 / 50), so the structure in 4.8 was right.

| quantity | result |
|---|---|
| model in both builds (101 pairs, 47 characters): discrete trait differs, full vs prefix | **0** |
| the same, prefix vs its own repeat (noise floor) | **0** (the model returned identical answers on repeat, so the floor is zero at these settings) |
| `big_five` moves by more than 0.05 / 0.10 / 0.20 in those 101 pairs | 3 / 0 / 0 (noise floor 0 / 0 / 0) |
| model in exactly one build (the gate, 50 pairs, 29 characters): a discrete trait differs | **37 of 50 (74%)**: gender 27, register 15, age band 7 (a pair can differ in several); `big_five` moves by more than 0.10 in 44 of 50 |

Reading, with the attribution kept apart (gate, deterministic part, model):
- **L1 is not supported.** With identical prompts and a zero noise floor, later chapters do not change the model read. This is the pre-registered prediction (Addendum 1), now measured; the 101 pairs come from only 47 characters and are not independent, so 0 differences bounds the per-character rate at about 6% (rule of three, 3/47), not 3%; this is evidence against a large model-content leak at these settings, not a proof of none, and it holds for one 7B model.
- **The 3 small `big_five` moves are not the model.** The prompt is identical in those pairs, and extraversion also depends on a cumulative mention count and dialogue total (`persona/build.py:197`), which differ between a whole-volume and a prefix build. This is consistent with the deterministic part, not individually traced.
- **The gate is the large effect, and it is a gate effect, not a model-content effect.** In 50 of 296 pairs (16.9%) the full build serves the model's read and the prefix build the deterministic read, and these disagree on a discrete trait in 37 of them: 12.5% of all character-cuts, above the 8.0% found for the deterministic stamp. The model itself is not the cause (noise 0, identical prompt where both run); the whole-volume `mention_count >= 25` decision is. As pre-registered, this is a difference in *which read was computed* (the model reads early evidence; what leaks is later prominence), not a spoiler. With no labels, nothing here says whether the model's value or the deterministic one is the correct one, so the 74% is a measure of disagreement between two readers, not of error.
- **Not tested:** whether a prefix-causal gate (decide on mentions up to the cut) is the right repair, how the two readers' values compare to ground truth, other models, and the model's own memory of the novels (no renaming control).

### 4.9 Checked against labels `[RAN]`, `LABELS: MODEL-GENERATED` (`PREREG_LABELS.md`; `data/eval/prefix_audit/labels_summary.json`)

**Read 4.10 first: it supersedes the headline numbers in this section (second annotator, more cuts).** Labels were generated by me (one annotator, no human review) because none could be supplied before the deadline: 117 truth labels from passages spread over each character's chapters, and 46 prefix labels (all 23 diverging gender cuts plus 23 random exposed ones, shuffled, flag hidden) from the text up to the cut. They were written blind to every system value, frozen by hash, and scored afterwards. 34.2% of truth labels are `unknown` or `non-person` (the declared 25% falsifier fired), so B and C below are on the labelled subset: 118 exposed cuts, 53 characters.

**A. Are the 23 diverging cuts spoilers? Mostly not.**

| class of the 23 (17 characters) | cuts | meaning |
|---|---|---|
| justified by text | 16 | the status quo served a value that the text up to the cut already supports; the prefix-only build left it `unknown` |
| premature disclosure | 5 (4 characters) | the text up to the cut does not settle it, yet a value was served |
| reverse | 2 | the status quo served `unknown` where the prefix-only build held the right value (one character, Melissa) |

So the stamp is early in all 23 (the integrity violation of 4.1 stands), but the harm a reader would see is 5 of 289 character-cuts, **1.7% (Wilson [0.7%, 4.0%])**, not 8.0%. The 5 are weaker than they sound: two are the same character at two cuts (the alias "Dokja", who is Kim Dokja), and one (Gu Yue Peng, stamp ch81, evidence horizon ch131, cut 120) has a truth label of `unknown`, so I cannot say whether the served `male` is right or merely beyond my sample. Four of the five are labelled with high confidence, one medium.

**B and C. Correctness, and what the repair buys (118 labelled exposed cuts).**

| build | correct | withheld (`unknown`) | wrong |
|---|---|---|---|
| status quo | 92 (78.0%, [69.7, 84.5]) | 24 (20.3%) | 2 (1.7%) |
| prefix-only build | 74 (62.7%, [53.7, 70.9]) | 42 (35.6%) | 2 (1.7%) |
| repaired | 74 (62.7%) | 42 (35.6%) | 2 (1.7%) |

- **The repair buys safety, not correctness**, as declared in advance: wrong stays at 2 of 118 in all three. The repaired build equals the prefix-only build exactly, which is what it is meant to do.
- **It is over-conservative by about 4 to 1.** Going from the status quo to the repair removes 20 true values and restores 2; of the 20 removed, 4 were verifiable premature disclosures and 16 (80%) were values the text already supported. Net, 18 fewer correct values (-15.3 points) to stop 4 verifiable (5 counting the unverifiable one) premature disclosures.
- **Attribution (gate vs engine).** The 16 are not caused by the stamp rule. They arise because the prefix-only build needs more evidence than a reader does (the labels accept a single "his", "uncle", "Lady" or "granddaughter"; the deterministic extractor does not), so this is the extractor's evidence threshold, not the horizon rule. A repair that kept the horizon rule but lowered that threshold is the obvious next step and is **not tested**.
- **The only wrong values** are one character: Naya (LOTM) is served `male` at cuts 20 and 30 in the status-quo and the prefix-only build alike, while the text says "Miss Naya" and "Madam Naya". That is a cut-independent extraction error, not a prefix-causality finding.

**What this does to the claim.** The audit's headline should now read: a stamp-versus-evidence violation affecting 8.0% of character-cuts, of which about a fifth (1.7% of all) is a premature disclosure by the labels, and a repair that removes it at the cost of withholding four times as many values the reader could already have. The first half is the contribution; the second half is the honest price, and it makes the repair look less attractive than it did in 4.4, which is the point of measuring it.

**Limits, plainly.** One annotator, one model family, no inter-annotator agreement; 4 premature characters, so the 1.7% rests on very few cases; "justified by text" means a reader could infer it, not that any extractor would; my labels accept cues (titles, kinship) that a stricter reader might not; the sample of passages can make a label `unknown` where more text would settle it. A 30-character sheet with no model labels shown is prepared at `labels/human_check.csv` (the five characters that carry the claim are on it); until a human fills it in, nothing here is human-verified.

### 4.10 Two annotators and more cuts `[RAN]`, `LABELS: MODEL-GENERATED` (`PREREG_LABELS.md` Addenda 2 and 2a; `data/eval/prefix_audit/labels_summary_v2.json`)

The owner asked for the limits of 4.9 to be addressed with `gpt-5.6-luna` as a second annotator. One fixed prompt, 419 calls ($0.0524 of a pre-registered $0.075 estimate and a $0.12 cap, run once): truth labels for 142 characters (the 117 of 4.9 plus 25 that appear at the added cuts) and a prefix label for every exposed (character, cut) pair, 277 pairs, with passages up to the cut. Eleven cuts were added to the original thirteen (LOTM and ORV at 15, 25, 35; RI at 30, 60, 100, 140, 160), audited on CPU into separate files. A male or female answer counts only if at least 80% of its quoted words appear in order in the cited passage (an amendment made after a three-call smoke test, recorded as Addendum 2a; 14 of 196 prefix answers failed it).

**Agreement.** On the 117 characters both annotators labelled: kappa 0.61 (raw 76.1%); **0 male-versus-female contradictions among the 61 both labelled male or female** (declared limit 5%, so the procedure passes). Luna is more conservative than I was: 16 characters I called male or female it left undetermined, against 11 it resolved that I had left unknown. On the 46 prefix items kappa is 0.63, with 0 contradictions and 11 items I called male or female that Luna left undetermined, none the other way round. After combining (declared rule), 31.0% of the 142 characters are still unknown or non-person (34.2% in 4.9), above the 25% limit, so correctness results stay flagged as a subset result. Most of the remaining unknowns are footnote figures and bare names with no gendered cue in the text.

**A'. Premature disclosure, with Luna's label as the uniform reference.**

| cuts | character-cuts | diverge | premature disclosure | justified by text | reverse |
|---|---|---|---|---|---|
| original 13 | 289 | 23 (8.0%) | 10 (3.5%, [1.9, 6.3]) | 11 | 2 |
| added 11 | 396 | 18 (4.5%) | 8 (2.0%, [1.0, 3.9]) | 10 | 0 |
| pooled | 685 | 41 (6.0%) | **18 (2.6%, [1.7, 4.1]), 11 distinct characters** | 21 (3.1%) | 2 |

- **Annotator-dependent.** On the same 23 original diverging cuts my labels give 5 premature, 16 justified and 2 reverse; Luna's give 10, 11 and 2. They are nested: all 5 of mine are among Luna's 10, and Luna adds 5 that I had accepted on thinner cues (a title, a kinship term). So the premature rate on the original cuts is 1.7% (mine) to 3.5% (Luna), and the share of divergences that are premature is 22% to 43%. Two of Luna's 18 pooled cases are borderline (it answered male or female, but the quote failed the 80% check).
- **Not an evidence-cap artefact.** In both the premature and the justified groups Luna saw a median of 2 passages (maximum 7, none near the cap of 24), that is, essentially every first-mention passage available at those early cuts.
- **The divergence rate itself depends on where the cut is placed:** 8.0% on the original cuts, 4.5% on the added ones, 6.0% pooled.
- **Cases:** premature disclosures went from 5 cuts in 4 characters (4.9) to 18 cuts in 11 characters.
- **Not a stamp effect:** another 43 exposed cuts (6.3% of all) serve a known value in both builds where Luna finds the text undetermined. The prefix-only build serves it too, so it is not caused by the stamp. It may be extractor over-reading, or evidence Luna's window did not show; not resolved.

**B'. Correctness against the combined reference (245 exposed cuts, 67 characters with a male or female reference).**

| build | correct | withheld | wrong |
|---|---|---|---|
| status quo | 184 (75.1%) | 56 (22.9%) | 5 (2.0%) |
| prefix-only build | 149 (60.8%) | 91 (37.1%) | 5 |
| repaired | 149 (60.8%) | 91 (37.1%) | 5 |

The repaired build again equals the prefix-only build exactly, now also on the added cuts, and again buys safety rather than correctness. All 5 wrong values are Naya (LOTM) in both builds: the cut-independent extraction error of 4.9, unchanged. The price of the repair is annotator-dependent too: it removes 35 correct values; with Luna's labels that is **21 values the text already supported for 18 premature disclosures prevented (about 1.2 to 1)**, with mine 16 to 5 (about 3 to 1; 4 to 1 counting only verifiable cases, as in 4.9). So "the repair is over-conservative" holds, but by a factor of roughly 1 to 4, not a fixed 4.

**What this does to the claim.** The defensible headline is now a range, not a point: a stamp-versus-evidence violation in 6.0% of 685 character-cuts (4.5% to 8.0% by cut placement), of which 1.7% to 3.5% of character-cuts (about a fifth to a half of the violations) is a premature disclosure depending on how strict the annotator is, and a repair that removes it at the cost of withholding about one to four values the text already supported per premature disclosure. The limits that this does fix: unknown share 34.2% to 31.0% (not below 25%), single annotator to two with kappa 0.6 and no contradiction, 4 to 11 characters, a post-hoc rule to a uniform protocol. What it does not fix: both annotators are language models and there is no human label (the 30-character sheet at `labels/human_check.csv` is still unfilled); three serials and one system; the added cuts re-use the same serials, so cut positions are not independent; and the quote-check threshold was set after a smoke test.

### 4.11 A cue that closes most of the gap `[RAN]`, pre-registered (`PREREG_ANCHORED.md`; `anchored_summary*.json`), `LABELS: MODEL-GENERATED`

4.9 and 4.10 located the repair's price in the extractor, not the horizon rule: the gender rule needs six third-person pronouns from the whole paragraph around every mention, so an early prefix often cannot call a gender that one sentence states ("Alger Wilson stood on deck, **his** body ..."). The pre-registered fix is an *anchored* cue: the first third-person pronoun after each mention, inside its own narration span, before the sentence ends or another name appears; used only when the paragraph rule says `unknown`; off by default (`build_personas(..., anchored_gender=(min_obs, majority))`). The default path is byte-identical (all 366 ORV audit rows reproduced exactly) and the core and pipeline suites pass (1253 passed, 6 skipped; 16 new tests).

Grid fixed beforehand (`min_obs` 1 to 3 times `majority` 0.8 or 1.0), setting chosen **leave-one-serial-out** on the other two serials subject to a wrong-value rate of at most 3%, scored on the held-out serial. 24 cuts, 512 (character, cut) pairs with a male or female reference, 98 characters:

| build (held-out, pooled) | correct | withheld | wrong |
|---|---|---|---|
| status quo | 361 (70.5%) | 146 | 5 (1.0%) |
| plain horizon repair | 326 (63.7%) | 181 | 5 |
| **horizon repair + anchored cue** | **360 (70.3%)** | 146 | 6 (1.2%) |

**H5 SUPPORTED** on all three declared conditions: stamp divergence 0 on every cut for every setting; 97% of the values the plain repair loses are recovered (threshold 50%); wrong rate 1.2% (limit 3%). The same setting, `min_obs = 1, majority = 0.8`, won every fold. It holds with each annotator alone as the reference, not only the combined one:

| reference | pairs / characters | status quo | plain | anchored | wrong sq to anchored | recovered |
|---|---|---|---|---|---|---|
| combined (declared) | 512 / 98 | 70.5% | 63.7% | 70.3% | 5 to 6 | 97% |
| my labels only | 445 / 77 | 76.0% | 69.2% | 76.2% | 5 to 6 | 103% |
| Luna only | 431 / 82 | 73.3% | 65.9% | 72.9% | 0 to 1 | 94% |

What the cue actually did: it decided 35 values where the plain repair withheld them, across 13 characters; 34 were right (97%, a wide interval at this count). It changed **0** values the plain repair already served, so it is a pure fallback. The one wrong value is Qing Shu at cut 100 (served `female`, both annotators `male`), the known weakness of the cue: a pronoun after the name that belongs to someone else in the sentence. Against the second annotator's prefix labels on the 277 exposed pairs, the number of served values where the text is undetermined is 61 for the status quo, 43 for the plain repair and 51 for the anchored build; that counts disagreement with a conservative reader, not error (errors are the wrong column).

All six settings, in-sample, for the frontier: `(1, 0.8)` 70.3% correct, `(1, 1.0)` 68.0%, `(2, 0.8)` and `(3, 0.8)` 66.4%, `(2, 1.0)` and `(3, 1.0)` 64.1%; wrong 6, 6, 5, 5, 5, 5 of 512. A looser cue buys availability at one extra wrong value in this sample.

**Limits.** The labels are model-generated. The chosen setting is the least strict `min_obs` in the grid in every fold, so the optimum may sit at or beyond that edge. An annotator-free check is thin by construction: against the engine's own final reading the cue agrees on 376 of 377 served values, but only 9 of its 35 added values have such a reading, 8 of them agree, and the others are exactly the cases where the engine is blind. The cue is English-translation-specific, tested on the same three serials, and its decision count (35) is small.

### 4.12 The premature rate with a third reader `[RAN]` (`PREREG_LABELS.md` Addendum 3; `labels_summary_permissive.json`), `LABELS: MODEL-GENERATED`

To bracket the premature-disclosure rate from the permissive side with a model instead of me, `gpt-5.6-luna` re-read the 277 exposed pairs with only the instruction relaxed (a single gendered pronoun, title, kinship term, form of address or description is enough). 277 calls, $0.0325.

| reader | premature on the 23 original diverging cuts | pooled over 685 character-cuts |
|---|---|---|
| my labels | 5 (22%) | n/a (46 items only) |
| Luna, permissive prompt | 8 (35%) | 14 = **2.0%** [1.2, 3.4], 8 characters |
| Luna, strict prompt | 10 (43%) | 18 = **2.6%** [1.7, 4.1], 11 characters |

The two Luna readings are nested (every permissive premature pair is also strict-premature), agree with kappa 0.80 on the 277 pairs and never contradict (male against female). So the premature rate is 2.0% to 2.6% of character-cuts for the model reader however it is instructed, and 1.7% on the original cuts for me; a rate of 0 is excluded by all three readers.

### 4.13 A volume with exactly known truth `[RAN]`, SYNTHETIC (`PREREG_SYNTHETIC.md`; `data/eval/prefix_audit/synthetic/`)

Every result above needs labels from language models. This one needs none: 40 chapters of invented text, 80 characters with known gender, a known chapter at which each character's own gender cue (a pronoun right after the name) first appears, and co-mentioned characters that put other people's pronouns in the same paragraph. Nine configurations (own-cue density 0.10, 0.35, 0.70 times misleading-cue density 0, 0.05, 0.15), 5 seeds each, 6 cuts, 1,240 (character, cut) pairs per configuration. Same code path as the real runs (`build_personas`, the audit's `build` and `read_state`).

| own cue / misleading | status-quo divergence | premature / justified | correct: status quo, plain, anchored (1, 0.8) | wrong: anchored (1, 0.8) / (2, 0.8) |
|---|---|---|---|---|
| 0.10 / 0 | 212 (17.1%) | 70 / 140 | 39.7%, 23.4%, 80.2% | 0.6% / 0.6% |
| 0.10 / 0.05 | 171 (13.8%) | 50 / 91 | 32.8%, 24.3%, 63.3% | **4.1%** / 1.8% |
| 0.10 / 0.15 | 122 (9.8%) | 32 / 24 | 13.6%, 13.9%, 41.3% | **5.5%** / 3.1% |
| 0.35 / 0 | 187 (15.1%) | 17 / 107 | 47.5%, 42.3%, 96.5% | 0.3% / 0.3% |
| **0.35 / 0.05 (base)** | **149 (12.0%)** | **11 / 68** | **42.4%, 41.4%, 91.6%** | **1.0% / 0.3%** |
| 0.35 / 0.15 | 136 (11.0%) | 8 / 44 | 27.7%, 30.0%, 76.9% | 0.9% / 0.3% |
| 0.70 / 0 | 154 (12.4%) | 4 / 75 | 49.5%, 49.1%, 99.4% | 0.1% / 0.1% |
| 0.70 / 0.05 | 139 (11.2%) | 1 / 62 | 44.9%, 45.9%, 98.3% | 0.2% / 0.1% |
| 0.70 / 0.15 | 114 (9.2%) | 1 / 39 | 30.9%, 33.4%, 93.3% | 0.4% / 0.2% |

- **S1, the mechanism: supported.** The status quo diverges from a build over the prefix in every configuration (9.2% to 17.1% of pairs), and both repairs diverge on **exactly 0 of 1,240 pairs in all nine configurations**, so the audit's defect and its repair do not depend on annotators or on the three serials.
- **The leak scales with how late the evidence arrives.** With no misleading cues, the status quo serves a known gender before any own cue exists in 70 pairs when own cues are sparse (0.10), 17 at 0.35 and 4 at 0.70. That is the mechanism of 4.1 (a stamp at first sighting, evidence in later chapters) with its dose-response.
- **The price of the repair is not universal.** Here the plain repair costs almost nothing against the status quo (41.4% against 42.4% correct at the base), because the paragraph rule is held back by co-mention noise whichever way it is stamped; in the real serials it costs 7 points (4.11). The size of the price depends on how much the paragraph rule gains from later chapters.
- **S2, the cue: the wrong-rate condition holds, the recovery metric is vacuous.** At the base the anchored build is 91.6% correct with 1.0% wrong. The pre-registered recovered fraction divides by the gap between the status quo and the plain repair, which is about one point here, so it is meaningless and is not quoted; absolute shares are reported instead. This is the generator's own cue structure (own pronouns sit right after the name), so a high figure is partly true by construction.
- **S3, the failure map.** The cue at `(1, 0.8)` has a wrong rate of 1.0% or less in seven of nine configurations and 4.1% and 5.5% in the two where own cues are sparse (0.10) and misleading cues are at least half as common as true ones. The stricter `(2, 0.8)` stays at 1.8% and 3.1% there, at lower availability (50.6% and 34.8%, against 63.3% and 41.3%). A unanimity requirement (majority 1.0) loses availability as soon as any misleading cue exists (72.1% against 91.6% correct at the base). A usable rule: `(1, 0.8)` while misleading cues are much rarer than true ones, `(2, 0.8)` otherwise.

Limits: invented English, one attribute, co-mention noise only from other characters' sentences (no titles, kinship terms or group pronouns), 5 seeds, and a generator that shares the cue's assumption. It shows that the machinery behaves as the real-data finding says and where the cue breaks; it does not show the cue works on real text (that is 4.11, with its labels).

### 4.14 A second text domain: two public-domain English originals `[RAN]`, pre-registered (`PREREG_PD.md`; `labels_summary_pd.json`), `LABELS: MODEL-GENERATED` (one annotator)

*Oliver Twist* (53 chapters, 25 characters) and *The Three Musketeers* (67 chapters and an epilogue, 20 characters), local Gutenberg copies, through the unchanged persona stage. The mention layer is a name gazetteer, not EchoTales' resolver (cleaner than the real one, which flatters the extractor); cuts and the anchored setting `(1, 0.8)` were fixed beforehand and **not re-tuned**; reference is `gpt-5.6-luna` alone (180 calls, $0.0285). 179 (character, cut) pairs.

| | *Oliver Twist* | *Three Musketeers* | pooled |
|---|---|---|---|
| status-quo stamp divergence (gender) | 6 of 89 (6.7%) | 2 of 90 (2.2%) | 8 of 179 (4.5%) |
| diverging pairs: premature / justified / other | 3 / 2 / 1 | 0 / 2 / 0 | 3 / 4 / 1 (premature 1.7% of pairs, [0.6, 4.8]) |
| plain repair, anchored `(1, 0.8)`, anchored `(2, 0.8)`: divergence | 0, 0, 0 | 0, 0, 0 | **0, 0, 0** |

- **PD1 (the defect reproduces): supported**, on original English text with a different narration style. **PD2 (the repairs hold): supported**, 0 divergences for all three repairs on both books, and label-free.
- **PD3 (the cue transfers): NOT SUPPORTED as pre-registered.** Correct shares are close (status quo 74.9%, plain repair 71.0%, anchored `(1, 0.8)` 75.4%, within the 5 points allowed), but the wrong rate of the anchored build is 7.8% (14 of 179), above the declared 3%.
- **Attribution of the wrong values, before any reading of the bar.** 11 of the status quo's 12 wrong values are three women the paragraph rule calls male in every build and at every cut: Charlotte (6 pairs), Mrs. Bedwin (4) and Kitty (2), whose paragraphs are dominated by men's pronouns (Luna's label is right in all three). That is the same cut-independent extractor error as Naya in 4.9, not a prefix effect and not the cue. The cue's own errors are one character: Milady, wrong in 3 pairs under `(1, 0.8)` where the other builds said `unknown`. Of the 11 values `(1, 0.8)` added to the plain repair, 8 are right and 3 wrong (73%, a wide interval at this count), against 34 of 35 (97%) on the web novels. `(2, 0.8)` added 8, of which 7 are right: it recovers all 7 correct values the plain repair lost (134 against 127) and leaves the wrong count at the status quo's 12.
- **Was the 3% bar fair?** It was set from the web-novel baseline, where the status quo is about 1% wrong. Here the status quo is already 6.7% wrong, so an absolute 3% limit fails every build, the unmodified one included; it measures the base extractor on this text, not the cue. The pre-registered verdict is not changed by this. Read after the fact and labelled as such: relative to the plain repair, the cue buys 8 more correct values for 3 more wrong ones with `(1, 0.8)` and 7 for 1 with `(2, 0.8)`.

What it changes in the claim: the defect and the repair reproduce on a second domain; the cue's availability gain reproduces; the cue's precision does not transfer uniformly (97% on the web novels, 73% to 88% here), which agrees with the synthetic failure map of 4.13 (misleading cues cost precision) and argues for the stricter `(2, 0.8)` when the cast is mixed-gender and the narration is dialogue-heavy. Limits: one annotator, two books, third-person English only, a gazetteer mention layer, and the persona stage's other keys are not scored.

### 4.15 The model path repaired `[RAN]`, pre-registered (`PREREG_LLM.md` Addendum 3, hypothesis L4; `llm_model_pc_*.json`), real model `qwen2.5:7b` via local ollama, $0

4.8a found that the model read is stable but that the whole-volume gate `mention_count >= 25` makes a full build and a prefix build disagree on a discrete trait in 37 of the 50 gate pairs. The repair decides the gate chapter by chapter on the mentions read so far (`build_personas(prefix_causal=True, client=...)`, which no longer refuses a client) and answers a repeated prompt from memory (`_MemoClient`), since the prompt holds only the label, the first 12 spoken lines and the first 6 narration samples and so stops changing once those windows fill. Same 13 cuts, same three serials, same real model, one pass plus one repeat for the noise floor.

| (character, cut) pairs, 296 | before (4.8a) | after (repaired gate) |
|---|---|---|
| model in exactly one build (gate class) | 50 (16.9%) | **0** |
| model in both builds | 101 | 101 |
| discrete trait differs, full vs prefix, among both-model pairs | 0 | **0** |
| noise floor (prefix vs its repeat) | 0 | 0 |
| `big_five` moves by more than 0.05 (full vs prefix, both-model pairs) | 3 | **0** (the earlier ones came from the non-causal deterministic part) |
| model calls over the three serials | 348 | 348 (the memo makes the repair cost-neutral) |

**L4 is supported**: 0 gate-class pairs and 0 both-model divergences on all three serials, with the backend recorded as the real local model in each output file. Unit tests pin the gate (deterministic, then model, then model as the mention count crosses the floor), the equality with a build over the prefix at every cut, and the call count (1259 passed, 6 skipped in the core and pipeline suites).

**The price.** The 50 pairs that used to be served by a model read are now served by the deterministic read until the prefix itself reaches 25 mentions; 37 of them had a different discrete trait (gender 27, register 15, age band 7, in 4.8a), so about 12.5% of all character-cuts change value relative to the old full build. Those are values a reader of the prefix could not have had from the model; the repair makes the stage consistent, it does not say which of the two reads was right (no labels exist for the model path).

**Limits.** One 7B model with deterministic decoding; the memo relies on identical prompts giving identical answers (noise floor 0 over 101 pairs here, not a general guarantee); the harness shared the GPU with another session and ran only in quiet windows; the repair covers the persona traits only, not appearance or world facts.

### 4.16 A v2 window for the cue: split verdict, and a precedence flaw `[RAN]`, pre-registered (`PREREG_ANCHORED.md` Addendum 1, H6; `anchored_v2_summary.json`), `LABELS: MODEL-GENERATED`

After PD3 failed (4.14) the cue's window was extended, with the rule fixed beforehand and not tuned: also cut at `;`, `:` and dashes, and before "the/a/an" plus a role noun (stranger, man, woman, officer, ...). The English originals became a **development set** (the failure was diagnosed there), the three web novels the **confirmatory** data (24 cuts, 512 pairs, 98 characters), settings `(1, 0.8)` and `(2, 0.8)`, hypothesis H6: zero divergence, correct share within 2 points of v1, no more wrong values than v1.

| web novels (confirmatory) | v1 correct / wrong | v2 correct / wrong | v2 added decisions (correct) | H6 |
|---|---|---|---|---|
| `(2, 0.8)` | 340 (66.4%) / 5 | 340 (66.4%) / 5 | 14 (14) | **SUPPORTED** |
| `(1, 0.8)` | 360 (70.3%) / 6 | 357 (69.7%) / 9 | 35 (34) | **NOT SUPPORTED** (condition c: 9 wrong against 6) |

Stamp divergence is 0 for v2 at both settings. On the development set v2 at `(1, 0.8)` removes the three Milady errors (wrong 14 to 11, all 8 added decisions right), which is what it was built to do and is not evidence.

**Attribution of the failure.** The 3 extra wrong values at `(1, 0.8)` are one character, Mother Shen, at three cuts (RI, truth female). The plain repair served `female` correctly from the honorific "Mother"; under v2 a single surviving male pronoun in an anchored window gave `male` and **overrode the correct honorific value**. This is not a window problem but a precedence rule in the cue as pre-registered ("a pronoun outranks an address form", copied from the paragraph rule, which has far more evidence behind it): a one-observation cue should not outrank an honorific. v1 never triggered it on these data (0 overrides), v2's shorter windows did. So the recommended window stays v1, `(2, 0.8)` is safe with either window, and the natural next step, not tested, is a cue that may only fill an `unknown` (never override an honorific) or that needs two observations to do so. Because the English books were used to design v2, that change should be pre-registered and tested on data not used so far.

**Correction to `FORMAL.md` P8.** It says a fallback cannot change what the base serves. That holds when the base is the paragraph rule alone, not when it is the whole extractor including the honorific table, which is what the implementation overrides; P8 is amended accordingly.

## 5. Prior art, and the exact difference

| Work | What it does | Difference | Tag |
|---|---|---|---|
| Zep / Graphiti, arXiv 2501.13956 | Bi-temporal model: timeline T for the chronological order of events, T' for "the transactional order of Zep's data ingestion". Episodes are added one at a time. | T' is real ingestion order. When a whole volume is processed at once, ingestion time is constant, so reader-knowledge time has to be reconstructed from evidence position. The paper does not discuss batch ingestion or evidence-derived knowledge time (the page I read had no such passage). | `[SUMM]` |
| Technical Disclosure Commons no. 8646, Molina, Tsai, Jiang, 2025-09-29 | "Spoiler-free entity information based on viewing progress": tag each fact with a progress point, retrieve only facts before the user's progress, let a generative model answer. | Describes the tag-and-filter design. The page describes no check that the tags are free of later information, which is the property audited here. | `[SUMM]` |
| Amazon Kindle "Ask this Book" | Answers "up to your current reading position", "without spoilers". | The page describes neither how answers are limited nor how that is tested. Absence on a marketing page is not absence in the product. | `[SUMM]` |
| Paige, LoreGraph | Open-source book assistants with a reading-position setting (Paige) and a claim-to-sentence graph (LoreGraph). | Seen in a search result only; the LoreGraph page fetch returned a rate-limit notice. Not relied on. | `[LEAD]` |
| NarraWorld (arXiv 2609.32401), Narrative World Model (arXiv 2607.05577) | Validity-interval store with an alias stage; chapter-safe evidence and reveal order as a modelled axis. | Per the CHIMERA `PRIOR_ART.md` (read by the other session, not re-read by me): they model disclosure, none audits whether derived facts' stamps are honest. | secondhand |
| Metamorphic testing of NER and relation extraction | Invariance relations on entity swaps and replacements; no oracle needed. | Searches found nothing on truncation invariance for extraction-to-graph pipelines. A bounded negative: US-only engine, snippets only. | `[LEAD]` |
| Incremental coreference (Xia et al. 2020; Grenander et al. 2023) | Architecturally incremental resolvers. | Prefix-causal by construction in the resolver; they do not address downstream derived-fact stamps. | `[LEAD]` |
| Look-ahead bias in LLM backtesting (Look-Ahead-Bench, arXiv 2601.13770; claim-level leakage scoring, arXiv 2602.17234; DatedGPT, arXiv 2603.11838) | Finance: the information set must be limited to what was observable at decision time; models trained or prompted with later data leak; the 2602.17234 line of work splits a model's rationale into atomic claims, tags each by temporal verifiability and scores how much of the decision rests on contaminated claims. | The same rule and an auditing mindset, aimed at a different object: model memory and rationales, not the knowledge-time stamp of a derived fact in a store. The search showed no knowledge-graph timestamp audit among them. Adjacent, not overlapping. | `[LEAD]` (search summary, abstracts only) |
| Stream processing, the Dataflow model (Akidau et al., VLDB 2015; Flink time docs) | Distinguishes event time from processing time; a **watermark** is a monotone lower bound on the event times still to arrive, so a result for a window is final only once the watermark passes it; early results are emitted and later revised ("triggers", accumulating panes, retractions). | **The closest structural relative, and it should be cited as such.** The reader's position is a watermark; a derived fact computed from evidence beyond the watermark is a result emitted before its window is complete; the horizon repair (revisions stamped by their evidence horizon, so the served value equals a build over the prefix) is the accumulating-panes idea transplanted to a narrative store. What the stream literature does not give is the audit on a deployed knowledge graph, the exposure screen, or the measured trade-off. I did not see a statement of it for reading-position stores. | `[SUMM]` (search summary of the paper and explainers, paper not read in full) |
| Point-in-time correctness in ML feature stores (practitioner sources: as-of / temporal joins, backfill leakage) | A derived feature must use only data available at its timestamp; backfills that use late or corrected records without their original timestamps "leak future info"; reconstructing intermediate state for derived features "is often needed, and is hard to get right". | **This is the same rule and the same failure, in another domain.** The horizon rule is not new. Searches (2026-10-16) found no automated detector for it in those sources, and nothing applying it to narrative or reading-position stores. | `[LEAD]` |
| Temporal provenance / lineage (e.g. arXiv 2601.04722, temporal attribution in dataflows) | Timestamps on provenance records; queries over which sources contributed in a time window. | Snippets only. A "max over input timestamps" rule for derived facts was not stated in what I saw; not ruled out. | `[LEAD]` |
| Audits of spoiler leakage in progress-aware assistants | None found in five extended searches (one USPTO patent on comparing reading stages for spoiler filtering; LLM spoiler-review detection; the fifth search returned only whole-book long-context QA benchmarks such as NovelQA and NarrativeQA, which have no reading-position cutoff). | A bounded negative: US-only engine, snippet-level reading. | `[LEAD]` |

## 6. Weak spots, stated plainly

- **"Truncate-and-rebuild is standard."** Yes. The test is not the contribution. What this adds is the static exposure screen, the measured exposure-to-divergence ratio, the repair and the cost. The screen over-flags (4.3), so its standalone value is modest.
- **One system, three serials, nested cuts.** 289 character-cuts are not 289 independent samples; the Wilson intervals are optimistic. This is an audit of the repository's own stage plus a design rule, not a general law.
- **Fixed resolution.** The persona stage is isolated from the resolver. If the resolver is not prefix-causal in some configuration (the whole-volume title-holder and transmigration passes are not, by design, per the other session's A7), a deployed pipeline can still leak through that route. E1 (other session, uncommitted code) found the resolver loop exactly causal with those passes off.
- **Gaps in the repair.** Body splits unrepaired (`state_of` unions persona bindings with no supersession, so a late-confirmed split cannot be stamped honestly without a core change). The `prominence` column is unstamped derived state (whole-volume count) and is unrepaired. The LLM trait path is refused, not repaired. At least five modules read persona attributes outside `state_of` (`persona/runner.py:133`, `webview.py`, `reference_gen.py`, `appearance_extract.py`, `world/context.py`) and none has been audited against several rows per key; `get_attributes` has no `ORDER BY`. This is why the flag defaults to off and has no CLI wiring.
- **Chapter granularity.** A revision is stamped at the end of its chapter, so a character introduced mid-chapter has no traits until the chapter ends. Counted in 4.5.
- **No labels.** Nothing here says which value is correct.

## 7. Files, and how to reproduce

Changed in the worktree (branch `claude/prefix-faithfulness`, uncommitted): `packages/pipeline/src/echotales/pipeline/persona/build.py` (`prefix_causal`, `_prefix_trait_revisions`, `_gather_evidence(upto=)`), `packages/core/src/echotales/core/store.py` (additive `mention_counts_by_chapter`). New: `packages/pipeline/tests/test_persona_prefix_causal.py` (11 tests), `packages/pipeline/tests/test_prefix_faithfulness_algebra.py` (5 property tests), `scripts/prefix_audit/{common,audit,summarize,llm_audit}.py`, `docs/research/PREFIX_FAITHFULNESS/{PREREG,PREREG_LLM,FORMAL,REPORT}.md`, results in `data/eval/prefix_audit/` (the `llm_fake_*.json` files are plumbing output and say so).

```
W=<worktree>
PYTHONPATH=$W/packages/core/src:$W/packages/pipeline/src python scripts/prefix_audit/audit.py --novel <id> --repair off|on
PYTHONPATH=... python scripts/prefix_audit/summarize.py
PYTHONPATH=... python -m pytest packages/pipeline/tests/test_persona_prefix_causal.py -o addopts=""
```

`PYTHONPATH` is required because the venv's editable install points at the main checkout, not the worktree. The audit reads the canonical databases only through the SQLite backup API.

Added after the first draft (all uncommitted): `persona/traits.py` (`anchored_window`, `gender_from_anchors`, optional `anchor_*` arguments), `persona/build.py` (`anchored_gender`, `_gather_anchors`, `_MemoClient`, `prefix_causal` with a client), tests `test_persona_anchored_gender.py` and six model-path tests in `test_persona_prefix_causal.py` (core and pipeline suites: 1259 passed, 6 skipped); scripts `label_sheets.py`, `luna_labels.py` (the paid step: `estimate` first, hard `--budget-usd`, key read in-process and never printed), `score_labels.py`, `score_labels2.py`, `score_permissive.py`, `score_anchored.py`, `score_pd.py`, `sweep_anchored.py`, `synthetic_oracle.py`, `pd_volume.py`, `run_pd_audits.py`, `run_llm_when_free.py` (GPU shared with another session; waits for a quiet window); docs `PREREG_LABELS.md`, `PREREG_ANCHORED.md`, `PREREG_SYNTHETIC.md`, `PREREG_PD.md`; results `labels_summary*.json`, `anchored_summary*.json`, `synthetic/`, `llm_model_pc_*.json` and the label files under `data/eval/prefix_audit/labels/` (frozen by `LABELS.sha256`; the labels contain short quotes from the source novels and should not be published as they are). `data/scratch/pd_db/` holds stores built from public-domain text and is disposable.

Not done: the `docs-sync` agent (it edits HANDOFF, EVOLUTION and README, which the other session also edits; run it at merge time), commits (owner rule), the E3 extension, human labels (the sheet `labels/human_check.csv` is unfilled), repair of body splits, measurement of appearance and world facts, a genuinely independent second system (the second domain reuses the same persona stage).

## 8. Paragraph for the other session's `NOVELTY_REPORT.md` section 8a (not pasted there)

**Updated version (use this one; the first-pass paragraph below is kept for the record):**

> **6. Prefix-faithfulness of derived facts in a position-filtered graph.** Position-filtered book assistants are deployed or published (Kindle "Ask this Book"; a 2025 Technical Disclosure Commons entry that tags facts with a progress point and filters at query time); the pages I read describe no check that the tags are honest. A truncate-and-rebuild audit of EchoTales' persona stage finds that a trait stamped at first sighting but computed from up to 12 later chapters makes the served gender differ from a prefix-only build for 6.0% of 685 character-cuts on three translated web novels (4.5% to 8.0% by cut placement), 4.5% of 179 on two English originals, and 9% to 17% of pairs on a synthetic volume with exactly known truth. Labelled by two model annotators (no human labels), 1.7% to 3.5% of character-cuts are genuine premature disclosures; the other diverging values were already supported by the text. A revision-by-evidence-horizon repair gives exactly 0 divergence in every run, but is safe rather than correct and withholds about one to four supported values per disclosure removed; hiding exposed facts is worse than doing nothing. A pre-registered anchored pronoun cue under the same horizon recovers 97% of the lost values at 1.2% wrong on the web novels (and only partly on the English originals, precision 73% to 88%, with a synthetic failure map), and a prefix-causal prominence gate removes the model path's own gate effect (50 to 0 of 296 pairs, 0 divergences, call count unchanged). Tier: system-internal plus model-generated labels plus a synthetic oracle, no human labels. Overlap: truncate-and-rebuild testing and point-in-time correctness from ML feature stores; Zep's bi-temporal model uses ingestion time, which is constant under whole-volume processing. Weak spots: one codebase, five real volumes, no human labels, a gazetteer mention layer on the second domain, body splits and appearance not repaired.

**First-pass paragraph (superseded):**

> **6. Prefix-faithfulness of derived facts in a position-filtered graph.** Position-filtered book assistants are deployed or published (Kindle "Ask this Book"; a 2025 Technical Disclosure Commons entry that tags facts with a progress point and filters at query time); the pages I read describe no check that the tags are honest. A truncate-and-rebuild audit of EchoTales' persona stage finds that the served gender differs from a prefix-only build for 23 of 289 character-cuts (5.4-11.7%), because traits are stamped at first sighting but computed from up to 12 later chapters. A static exposure screen flags 48% of character-cuts and never missed a divergence (precision 16.5% for gender). A revision-by-evidence-horizon repair removes the divergence (0 of 289) at 9% more rows and 19 more `unknown` genders; the cheaper alternative, hiding every exposed fact, is worse than doing nothing (82 of 289 cuts differ from a prefix build, because it discards 80 values the prefix already held), so honest stamps alone are not sufficient. Checked against two model annotators (no human labels) on 685 character-cuts: 41 diverge (6.0%), and 1.7% to 3.5% of all character-cuts (depending on the annotator) are premature disclosures, the rest being values the text up to the cut already supported; the repair withholds about one to four such values per premature disclosure it removes and does not change correctness. Tier: system-internal plus model-generated labels, no human labels. Overlap: truncate-and-rebuild testing and (probably) data lineage; Zep's bi-temporal model uses ingestion time, which is constant under whole-volume processing. Weak spot: one system, three serials, resolution held fixed, body splits unrepaired.
