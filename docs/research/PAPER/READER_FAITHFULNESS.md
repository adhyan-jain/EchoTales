# Reader-faithfulness: what a book assistant may know at chapter c, and the two ways it breaks that promise

Status: DRAFT 2026-10-16, merged from branch `claude/prefix-faithfulness` into `chimera/system-adapters`; Channel 1 filled on 2026-10-16 from the exploratory runs (`NOVELTY_REPORT.md` v1.6) and the pre-registered confirmatory run (`PREREG_PD_CONFIRM_v2_L40S.md` with addenda 1 to 5, results in `data/eval/chimera/confirm/`, tables from `scripts/chimera/gen_ch1_tables.py`). Channel 2 numbers are copied from `docs/research/PREFIX_FAITHFULNESS/REPORT.md` and `FORMAL.md` (section numbers in brackets). Every Channel 1 number carries its provenance: *exploratory* (analysed before the confirmatory design existed, some after seeing the data) or *confirmatory* (pre-registered, frozen events, one run).

Label provenance, stated once (the full statement is in Section 10): **no number in this paper is human-labelled and no human annotation exists.** Channel 2 results are system-internal (no labels), synthetic (truth by construction) or labelled by two language models; Channel 1 results use a text-derived oracle whose events were selected by a language model (and, in the confirmatory run, audited by a second language model that is also one of the evaluated models) and are not owner-verified.

---

## Abstract

A book assistant that answers "as of chapter c" makes a promise to the reader: nothing it says may depend on chapters after c. We call this **reader-faithfulness** and define it as invariance of the output at position c to the rest of the volume. We give an audit method for each way the promise can break, prove when the standard repairs work, and validate the method on two systems, in each case finding a leak and showing the fix. The promise can be broken through two channels that look different but violate the same contract. In **Channel 1, parametric memory**, the language model inside the system has already read the book, so a prompt truncated at chapter c still elicits the later reveal; we measure this as name-keyed premature identity naming, original names against consistently replaced names, with an unseen-text control and a cue-preserving pseudonym control. On famous public-domain books the effect is large for the reference model (exploratory: +26.0 points [16.8, 36.0] over 38 events) and smaller and less reliable for small local models (+11.5 [4.5, 19.0], not replicated on seven fresh books), and it tracks how well known the book is. A pre-registered confirmatory run on 68 events from 65 mostly obscure public-domain books with three open 24B to 32B models found **no gap**: pooled +0.1 points [-5.0, +5.2], with a closed-book positive control that recovers the identity from memory in only 2 of 68 events, so the sample holds little memory to detect; the fame contrast that would link the two results is suggestive and underpowered (+7.6 points [-1.4, +18.3], one-sided p = 0.060, minimum detectable difference about 13 points). In **Channel 2, derivation look-ahead**, the pipeline around the model stores a derived fact (a character's gender, say) stamped with the chapter where the character first appears but computed from up to twelve later chapters, so a query filtered to chapter c returns values that a build over chapters up to c does not hold. Truncating the input and rebuilding gives an exact oracle for this channel. On a deployed narrative knowledge graph the served gender differs from the prefix build for 6.0% of 685 character-cuts of three translated web novels (4.5% to 8.0% depending on where the cuts fall), 4.5% of 179 on two English originals, and 9.2% to 17.1% of pairs on a synthetic volume with exactly known truth. Only 1.7% to 3.5% of character-cuts are premature disclosures by two model annotators; the rest were already supported by the text. Versioning each derived fact by the evidence horizon it was computed from removes the divergence entirely (0 in every real, public-domain and synthetic run) but is safe rather than correct; hiding every exposed fact instead is worse than doing nothing (82 divergences against 23 of 289). A pre-registered anchored pronoun cue recovers 97% of the correct values the repair withholds at 1.2% wrong on the web novels, with a measured failure map, and a prominence gate decided on the prefix removes the model path's own look-ahead (50 to 0 of 296 pairs). On a second, generic design, a whole-volume LLM character card stamped at first mention (pre-registered; 54 reveal events in public-domain books, 3 models), the card names the hidden identity before the reveal in 18.5% of events even when every name is a cipher no model has seen (strict text rule: 24.6% of 19 events), against 1.2% for the versioned card; the memory-only leak at that position is +2.5 points. On larger open models (Mistral-Small-3.2-24B, Qwen2.5-32B) the whole-volume card leaks in 23.1% under cipher names against 1.9% for the versioned card, and the memory-only leak is +0.0 points. Three further pre-registered tests sharpen the input channel. **Suffix canaries**, invented names and facts written only after the reader's position, give a judge-free, black-box oracle with no false positives by construction, applicable to every event. They confirm the card's leak on all 54 events (22.8%, against 0 for the versioned card). They also show that a long-context model given the book and told explicitly not to reveal anything after the reader's marker quotes the post-marker name in 40.6% of events. A **selection leak**, where every passage served is before the reader but a whole-volume entity merge chose them, makes the card name the hidden identity in 19.4% of merged events against 1.4% for a prefix-built index; no canary or position filter can see it. A **counterfactual suffix** on the deployed graph (pronouns swapped after the cut only) finds the served gender depends on later chapters in 47 character-cuts, twice the 23 that truncate-and-rebuild finds, with 0 after the repair. The two channels need different instruments, because truncation cannot see a memory held in the weights, and they compose, because a derivation that calls a model inherits the model's memory. We report what each repair costs and what remains unrepaired.

---

## 1. Introduction

Position-aware reading assistants are now a product category. Kindle's "Ask this Book" answers "up to your current reading position", and a 2025 disclosure describes tagging each fact with a progress point and retrieving only those before the user's progress. The premise is simple and valuable: a reader in the middle of a mystery should be able to ask who a character is and get an answer that does not ruin chapter 40.

The pages describing these systems say how the filter is applied. They do not describe a check that the filter's inputs are themselves free of later information, and there are at least two ways they might not be.

*The model knows the book.* If the assistant uses a language model to link an alias ("the masked guest") to an identity, truncating the context at chapter c does not stop a model that has memorised the novel from naming the answer it remembers. The context window is not the model's only source of knowledge.

*The pipeline's derived facts look ahead.* If the assistant builds a knowledge graph from the whole volume and filters queries by position, each stored fact carries a position. The position is usually that of the first mention. But many facts are not read off a single mention: a character's gender, register or age band is computed from evidence accumulated over many chapters. A fact computed from chapter 12 but stamped at chapter 1 is served to a reader at chapter 5 with chapter 12's information in it. Nothing in the filter is wrong; the stamp is.

These are not two bugs in one system. They are two ways to violate one contract, and the contract has not been stated. This paper states it (Section 3), measures each violation with an instrument suited to it (Sections 5 and 6), measures both on a second, generic system and fixes what it finds (Section 7), reports what repairs exist and what they cost (Section 8), and says what is not shown (Section 10).

**Contributions.**

1. A definition, **reader-faithfulness**, that covers both channels, and a short formal note on the part that is elementary (Section 3).
2. For Channel 2, an audit method (truncate-and-rebuild with a static exposure screen) validated on two systems: a deployed pipeline and a generic whole-volume LLM character card, where the card leaks the hidden identity before the reveal in 18.5% of events under cipher names and the versioned card in 1.2% (Section 7). On the deployed pipeline, an audit by truncate-and-rebuild with a static screen for which facts are exposed, a measured divergence rate replicated on three kinds of data (translated web novels, English originals, a synthetic volume with known truth), a labelled split of divergence into premature disclosure versus already-supported values, and a pre-registered repair frontier in which honest stamps alone are worse than the defect.
3. For Channel 1, a renaming-controlled test of premature identity naming with a memory-free validity gate, a closed-book positive control, an unseen-text control and a cue-preserving pseudonym condition. The measured result is conditional: large on famous books (exploratory), absent and well bounded on obscure ones (confirmatory), with the recognition of the book as the apparent moderator. The fame dose-response confirms Chang et al. (2023), and the pseudonym test and the pseudonymisation mitigation replicate or baseline Jiang and Ferraro (arXiv 2412.14368); what we add is the premature-resolution construct under prefix truncation with an entitlement oracle, and the observation that plain-control validity checks on famous books are themselves memory-assisted.
4. A joint measurement of both channels on one system with one oracle (Section 7): input leak +17.3 points, memory-only leak +2.5 points at the reveal cut for 7 to 8B models. The observation that the channels interact: the guarantee of a repair for Channel 2 belongs to the policy and not to the derivation it wraps (FORMAL P6), so a model-backed derivation is faithful in Channel 2 and can still be unfaithful in Channel 1.

5. **What each audit can see, with a measured instance of each (Sections 3.3, 5.4, 7.9, 7.10).** Input-channel leaks come in two kinds: *content* (suffix-derived text reaches the generator) and *selection* (only prefix items reach it, but the suffix chose them). Suffix canaries detect content leaks with a string oracle, black-box and judge-free, and are provably blind to selection leaks. Truncate-and-rebuild detects both kinds of divergence but needs a judge on free text. A counterfactual suffix detects dependence that truncation misses on a single volume. Measured: a long-context positional instruction leaks in 40.6% of events (canary); merged-entity retrieval leaks in 19.4% with no suffix token in the input (selection); and on the deployed graph, dependence is 47 cuts against 23 divergent ones.

**What this is not.** It is a method-and-measurement paper, not a new algorithm. The core rule behind the Channel 2 repair is point-in-time correctness from ML feature stores, and the repair is structurally the stream-processing idea of emitting early results and revising them as a watermark advances (Section 4). The claim is the combination, measured on a deployed narrative graph, including the case where the textbook fix is worse than the defect. It is one codebase.

---

## 2. Setting: a volume, a reader position and a pipeline

A volume has chapters 1..n. A reader at position c has read chapters 1..c. The system under study is EchoTales, a pipeline that reads a web-novel volume and builds a bitemporal narrative knowledge graph with three time axes (discourse order, story time, and **knowledge time**, the position at which a reader could know a fact) and a reader-observer query `state_of(READER, position)` that returns the facts a reader at that position is entitled to. The graph is the research object; the audiobook and visual adaptation that EchoTales also produces are not part of this paper.

Two features of the setting matter. First, processing is **volume-first**: the whole volume is ingested at once, so the time at which a fact is written to the store carries no information about when a reader could know it. Knowledge time has to be reconstructed from evidence position, and getting that reconstruction right is exactly what is at stake. Second, the store contains both facts read off one passage (an alias linked at the sentence where it occurs) and facts derived from accumulated evidence (a persona trait computed from the first twelve attested chapters). The second kind is where the stamp can be dishonest.

---

## 3. Definition and formal note

### 3.1 Reader-faithfulness

Let `S` be a system that, given a volume `x = (x_1, ..., x_n)` and a reader position `c`, returns an output `S(x, c)`: an answer, a graph state, a set of served facts.

> **Definition (reader-faithfulness).** `S` is reader-faithful if for every position `c` and every pair of volumes `x`, `x'` with the same first `c` chapters, `S(x, c) = S(x', c)`. The output at `c` may depend only on chapters `<= c`.

This is causality in the signal-processing sense: the output at time c is a function of the input up to c. For a deterministic system it has an operational test, **truncate and rebuild**: build the system on `x_{<=c}` and on `x`, ask the same question at `c`, compare. Equality for all `c` and all `x` is the definition; equality on the volumes and cuts one can afford is the audit.

The definition silently assumes that the only route from chapters after c to the output is the input. That assumption is the first channel's failure. If the system contains a learned model with parameters `theta` fitted on a corpus that includes the volume, then `S` is really `S(x, c; theta)`, and the suffix `x_{>c}` is reachable through `theta`. So we state the contract in two parts:

- **Input channel (Channel 2).** `S(x, c; theta)` does not depend on `x_{>c}` for fixed `theta`. This is the definition above and is testable by truncation.
- **Parameter channel (Channel 1).** `S(x_{<=c}, c; theta)` does not depend on what `theta` encodes about `x_{>c}`; equivalently, it equals `S(x_{<=c}, c; theta_0)` for a model `theta_0` that has never seen the volume. `theta_0` does not exist for a model we did not train, so this part is not directly testable, and Section 6 measures a proxy: the change in the output when the keys under which the memory is stored (here, names) are replaced.

The two parts compose. A pipeline can be input-faithful with a model call inside it and parameter-unfaithful because of that call. The truncation audit cannot detect the latter, because both builds call the same model with the same prompt (Section 5.3 reports exactly this: identical prompts, zero noise floor, zero divergence, and no statement about memory).

### 3.2 The part of Channel 2 that is elementary

A deterministic derivation `D` maps the evidence of a chapter prefix to a value in a set `V` containing a neutral element `u` ("unknown"). The **reference** at cut `k` is `r_k = D(x_1..x_k)`. A policy serves `s_k`; its **divergence** is the number of cuts with `s_k != r_k`. The **read set** `R(x)` of a derivation is the set of chapters it inspects, and it is a **certificate** if any input agreeing with `x` on `R(x)` gives the same value. The **evidence horizon** is `H = max R(x_1..x_n)`. Three policies are compared: the **status quo** serves the final value `r_n` stamped at first sighting; **hide-only** serves `u` for `k < H` and `r_n` after; **versioned** serves `r_k`, one revision per value change, each stamped at the chapter it was computed from. The full note is `FORMAL.md`; each proposition is checked on random inputs by `test_prefix_faithfulness_algebra.py` (400 examples each) against a toy derivation. The statements that carry weight in the paper:

- **P1 (screen).** If `R` is a certificate then `r_k = r_n` for every `k >= H`, so all divergence lies in the exposure window `k < H`. The screen's soundness is exactly the claim that the hand-derived read set is a certificate, which is the unverified assumption in the audit.
- **P3 (hiding versus doing nothing).** With `A = #{k < H : r_k = u}` and `B = #{k < H : r_k = r_n}`, hide-only minus status quo equals `B - A`. Hiding beats doing nothing only if fewer in-window prefixes already hold the final value than hold the neutral one. It is a property of the data, not of the idea.
- **P4 and P5 (versioning, and the trade-off).** `s_k = r_k` has divergence 0 for every `D` and is the unique policy with that property; any policy that recomputes nothing and serves no value from beyond `k` pays a loss wherever it serves `s_k != r_k`, so only the recomputing policy sits at zero leaks and zero losses.
- **P6 (the guarantee belongs to the policy).** The versioned policy has divergence 0 whatever `D` is, provided `D` reads only the prefix at each cut. Faithfulness and correctness are separate axes: the repaired build is exactly as correct as `D` is on prefixes.
- **P7 (gates).** If a derivation calls an expensive reader iff a monotone predicate `g` of the evidence holds, then evaluating `g` on the whole volume makes the builds disagree exactly on the class where `g` is false on the prefix and true on the whole; evaluating `g` on the prefix empties that class.
- **P8 (fallbacks), as amended.** A fallback `F` used only when the base derivation is silent leaves every served base value unchanged. This holds only if the fallback fills `unknown` and never outranks an existing value; the cue as first implemented outranked an honorific, and Section 5 reports the case where that mattered.

**Not claimed.** That this is new mathematics (it is elementary) or that "max over inputs" is new (it is point-in-time correctness). The note exists to make the measured trade-off a checkable proposition, including the one result that is easy to get wrong: P3 explains why hiding exposed facts can be worse than the defect.

The read-set table that P1 depends on, listed above as the audit's unverified assumption, is now property-tested on the real deterministic derivation rather than the toy (`test_prefix_faithfulness_readset.py`, 400 examples per property): gender, age band, register and archetype never move when every whole-volume input (mention count, prominence, dialogue count) varies with the windowed evidence held fixed, and `big_five` reads the whole-volume count only when there is dialogue, a dependency that is real (one fixed example moves it). The body-split and model paths are not covered.

### 3.3 What each test can see: content leaks, selection leaks and two oracles

Write a position-aware system as `S(x, c) = G(sel(I(x), c))`: an index `I` built from the volume, a selector that picks what is served at `c`, and a generator `G`. Two kinds of input-channel leak follow from where the suffix enters. In a **content leak** text derived from `x_{>c}` reaches `G` (a whole-volume card). In a **selection leak** everything `G` receives is from `x_{<=c}`, but *which* prefix items are chosen depends on `x_{>c}` (a whole-volume entity merge decides which prefix passages belong to the alias; EchoTales' prominence gate decides which reader runs, P7). Position filtering of served items passes both.

A **suffix canary test** replaces tokens after `c` only with fresh invented tokens and checks whether the output at `c` contains one. FORMAL P9 to P11 (checked on toy systems by `test_reader_faithfulness_canaries.py`):

- **P9.** A canary hit always means the system is not reader-faithful: the token exists only in the suffix and no model can remember it, so the oracle is a string match with no false positives, no judge, no renaming and no memory explanation, and it needs only black-box access (upload a modified book, ask at `c`).
- **P10.** A selection-only system never fires a canary, whatever it does with the suffix, and the substitution can even remove the leak it tests for (a resolver that linked the alias to the identity's prefix name through the reveal cannot link a canary name).
- **P11.** Truncate-and-rebuild detects both kinds of *divergence* (the served value differs from what a prefix build serves), but on free-text outputs it needs an equivalence judgement (a judge model) unless the system is deterministic. It is still one comparison against one other volume, so it misses dependence on the suffix whenever this book's suffix happens to agree with its prefix; a **counterfactual suffix** (change only what comes after `c`, compare) tests dependence directly and works on closed-vocabulary outputs. Canaries are the judge-free special case for free text and are complete only for content leaks. A black-box audit needs more than one of these, and no single pass is a certificate.

Section 5.4 measures dependence with a counterfactual suffix on the deployed graph (twice the divergence); Section 7.9 measures content leaks with canaries on every event; Section 7.10 measures a selection leak that canaries cannot see.

---

## 4. Related work

One sentence per closest paper on what it does and how this work differs. Verification status is in the note after the list.

**Position-aware assistants and temporal graphs.**
- *Zep / Graphiti* (arXiv 2501.13956) keeps a bi-temporal graph whose second timeline is ingestion order; under whole-volume processing ingestion time is constant, so reader-knowledge time must come from evidence position, which is the quantity audited here.
- *Spoiler-free entity information based on viewing progress* (Technical Disclosure Commons no. 8646, 2025) describes tagging facts with a progress point and filtering at query time; the description gives no check that the tags are free of later information, which is the property audited here.
- *Kindle "Ask this Book"* answers up to the reader's position; the product page describes neither how answers are limited nor how that is tested, and absence on a marketing page is not absence in the product.
- *NarraWorld* (arXiv 2609.32401) and *Narrative World Model* (arXiv 2607.05577) model disclosure and reveal order as design axes; neither measures whether a derived fact's stamp or a model's answer respects it.

**Memorisation and renaming controls (Channel 1).**
- *Jiang and Ferraro* (arXiv 2412.14368) use name replacement as a memorisation control on character-story tasks including coreference; they have no chapter prefix and no disclosure time, so premature identity naming is not measured.
- *SynthWorlds* (ICLR 2026) separates knowledge from reasoning by renaming with a rename-leak audit on encyclopedic QA; it is not fiction and has no alias-to-identity task.
- *TimeChara* (Findings of ACL 2024) shows models hold novel plots in parametric memory and that a context cutoff does not stop future leakage in role-play; it exploits the leakage and does not control or quantify it for identity linking.
- *KoCoNovel* (LREC-COLING 2024) provides reader-view and omniscient-view coreference labels on 50 public-domain Korean novels; dual labels are not new, and it runs no LLM and no leakage control.

**Look-ahead and point-in-time rules in other fields.**
- *Look-ahead bias in LLM backtesting* (Look-Ahead-Bench, arXiv 2601.13770; claim-level leakage scoring, arXiv 2602.17234; DatedGPT, arXiv 2603.11838) states the same rule for finance, that the information set must be what was observable at decision time, and aims it at model memory and rationales, not at the knowledge-time stamp of a derived fact in a store.
- *Point-in-time correctness in ML feature stores* (practitioner sources on as-of joins and backfill leakage) is the same rule and the same failure for derived features; I found no detector for it in those sources and nothing applying it to narrative or reading-position stores.
- *The Dataflow model* (Akidau et al., VLDB 2015) separates event time from processing time and emits early results revised as a watermark advances; this is the closest structural relative (the reader's position is a watermark, and the versioned repair is its accumulating-panes idea), and what it does not supply is the audit on a deployed knowledge graph, the exposure screen or the measured trade-off.

**Canaries and leakage tests.**
- *Canary strings for memorisation* (Carlini et al., "The Secret Sharer", USENIX Security 2019) insert random secrets into training data and measure their exposure in a trained model; our canaries are inserted into the part of a volume after the reader's position and test an inference-time contract, not training-data extraction.
- *CanaryBench* (arXiv 2601.18834) plants secret strings in synthetic conversations and checks whether summaries leak them across privacy clusters; it tests cross-record privacy, not position within one document.
- *ExAnte* (arXiv 2505.19533) and *TimeSPEC* (arXiv 2602.17234) measure reliance on information beyond a temporal cutoff in forecasting and backtesting; they score claims against dated sources rather than planting a string after the cutoff, and they do not separate content from selection leaks.

**Testing and incremental resolution.**
- *Metamorphic testing of NER and relation extraction* uses invariance relations on entity swaps and replacements without an oracle; I found nothing on truncation invariance for extraction-to-graph pipelines.
- *Incremental coreference* (Xia et al. 2020; Grenander et al. 2023) is prefix-causal by construction in the resolver and does not address the stamps of facts derived downstream.

**Status of these entries.** Zep, the Technical Disclosure Commons entry, Kindle's page and the Dataflow paper were read through a summarising fetch tool (Dataflow in search summaries and explainers, not in full); the finance entries, ML feature-store sources, metamorphic-testing and incremental-coreference entries were seen in snippets or abstracts only; NarraWorld and Narrative World Model are taken from the project's own prior-art file read by another session; the Channel 1 entries (Jiang and Ferraro, SynthWorlds, TimeChara, KoCoNovel) were read in the publications' own text per the novelty report. All searches were bounded (US-only engine; CNKI, KCI and Baidu Scholar not searched). **Absence of an audit in this literature is a bounded negative, not a confirmation of novelty.** Citations beyond those named here are for the main session to verify before submission.

---

## 5. Channel 2: derivation look-ahead

*All Channel 2 numbers are from `REPORT.md`; bracketed numbers are its section numbers.*

### 5.1 Method

**The defect in one example.** The persona stage computes a character's gender from third-person pronouns in the paragraphs around the first twelve chapters in which the character is attested, and writes it as a fact stamped at the chapter of first sighting. `state_of(READER)` at chapter 2 therefore serves, for a character first seen in chapter 1 whose pronouns appear in chapter 3, a gender that a build over chapters 1 and 2 would not hold. A unit test pins this on a three-chapter synthetic volume [4.4].

**Oracle.** Truncate and rebuild. Build the persona stage on the full volume and on chapters `<= k`, compare `state_of(READER)` at position `k + 0.5` for every character with a persona fact in both. Resolution is held fixed: both builds start from the stored mention-to-entity assignment, and the prefix build deletes every chapter, span, mention and segment after `k`. This isolates the persona stage and leaves the resolver's own causality out of scope [3]. Thirteen cuts on three translated web novels (Lord of the Mysteries, Omniscient Reader's Viewpoint, Reverend Insanity) give 289 character-cuts; eleven cuts added later give 685. Cuts are nested, so the pairs are not independent and the intervals are optimistic.

**Static screen.** A fact is *exposed* at `k` if its stamp is at most `k` and its evidence horizon is beyond `k`. Horizons were read from the code (gender, age band, register and archetype read the first twelve attested chapters; `big_five` additionally reads a whole-volume mention count; body splits read the last attested chapter). The screen says which cuts can be certified without a rebuild.

**Repair.** `build_personas(prefix_causal=True)` recomputes the deterministic profile for each attested chapter `c` from the evidence and the cumulative mention count of chapters `<= c`, and writes only the keys whose value changed, stamped `(c, 10^6)`. `state_of` already keeps the latest-stamped value per key, so no interval surgery is needed. Off by default; the default path is byte-identical (232 rows with the same SHA-256 prefix on one serial against the unmodified code) [4.4].

**Labels.** Two model annotators, no human. Annotator 1 is the Claude session that also wrote the repair; its labels were written blind to every system value and frozen by hash. Annotator 2 is `gpt-5.6-luna`, one fixed prompt, 419 calls, $0.0524, with a quote check (a male or female answer counts only if at least 80% of its quoted words appear in order in the cited passage). A third reading with a permissive prompt (Luna again, $0.0325) brackets the rate from the other side [4.9, 4.10, 4.12].

**Further instruments.** A *synthetic volume* of 40 chapters and 80 characters with known gender, a known chapter at which each character's own cue first appears, and co-mentioned characters that put other people's pronouns in the same paragraph, in nine configurations of cue density and 5 seeds each [4.13]; *two English public-domain originals* (*Oliver Twist*, *The Three Musketeers*) through the unchanged stage with a gazetteer mention layer [4.14]; and the *model path* of the persona stage, real `qwen2.5:7b` via local ollama at temperature 0, 348 calls, $0 [4.8a, 4.15].

### 5.2 Results

**R1. The defect is real and general across the data tested.**

| Data | Character-cuts or pairs | Status-quo divergence from a prefix build |
|---|---|---|
| Three web novels, original 13 cuts | 289 | 23 (8.0%, Wilson [5.4%, 11.7%]) |
| Three web novels, 11 added cuts | 396 | 18 (4.5%) |
| Three web novels, pooled | 685 | 41 (6.0%; 4.5% to 8.0% by cut placement) |
| Two English originals | 179 | 8 (4.5%; 6.7% and 2.2% per book) |
| Synthetic volume, nine configurations | 1,240 pairs each | 9.2% to 17.1% |

All 23 diverging original cuts are gender (and the archetype string derived from it); `age_band`, `register` and `big_five` diverge 0 times [4.1]. On the synthetic volume the leak scales with how late the evidence arrives: with no misleading cues the status quo serves a known gender before any own cue exists in 70 pairs when own cues are sparse (density 0.10), 17 at 0.35 and 4 at 0.70, which is the mechanism with its dose-response and no annotator [4.13].

**R2. The screen is sound here and over-flags.** 0 divergences fall outside an exposure window (1,445 trait fact-cuts and 296 persona-set cuts), though this is close to true by construction because the dependency table was derived from the audited code, and the `big_five` whole-volume dependency was never realised on real data [4.2]. About half of all character-cuts (48%) are exposed; 16.5% of exposed gender cuts diverge, a 2.08 times lift over the base rate of 8.0% at 100% recall, and the screen certifies 150 of 289 cuts (51.9%) as safe without a rebuild [4.3]. It is a safety certifier, not a predictor.

**R3. Most divergence is not a spoiler.** Stamp divergence and reader-visible harm are different quantities. Of the 41 diverging character-cuts over 685, 18 (2.6%, Wilson [1.7%, 4.1%], 11 characters) are premature disclosures by Luna's labels and 21 were already supported by the text up to the cut; two reverse (the status quo served `unknown` where the prefix build held the right value). With the permissive prompt the pooled rate is 2.0% [1.2, 3.4]; by the first annotator's labels the original-cut rate is 1.7% against Luna's 3.5% on the same cuts. A rate of 0 is excluded by all three readers; the honest statement is a range, 1.7% to 3.5% of character-cuts, not a point. On the 117 characters both annotators labelled, kappa is 0.61 with 0 male-versus-female contradictions among the 61 both labelled male or female [4.9, 4.10, 4.12].

**R4. The horizon repair removes the divergence and the cost is real.** With the repair on, divergence is 0 of 289 (Wilson [0%, 1.3%]), 0 on the added cuts, 0 of 179 on the English originals and 0 of 1,240 in each synthetic configuration [4.4, 4.10, 4.13, 4.14]. It buys safety, not correctness. Against the combined reference (245 exposed cuts, 67 characters with a male or female reference):

| Build | Correct | Withheld | Wrong |
|---|---|---|---|
| Status quo | 184 (75.1%) | 56 (22.9%) | 5 (2.0%) |
| Prefix-only build and repaired build (identical) | 149 (60.8%) | 91 (37.1%) | 5 |

The repair removes 35 correct values: with Luna's labels, 21 values the text already supported for 18 premature disclosures prevented (about 1.2 values per disclosure), with the first annotator's labels 16 for 5 (about 3 to 1). All 5 wrong values are one character (Naya) in both builds, a cut-independent extraction error that no repair of the stamp can touch [4.10]. The cost in rows and time is modest: 9% more attribute rows and about 50% more persona-stage time over three volumes, 19 more `unknown` genders among 289 character-cuts (39.8% to 46.4% served unknown) [4.5].

**R5. Honest stamps alone are not enough.** Hiding every exposed fact (the "honest stamp" applied naively) diverges from a prefix build on 82 of 289 cuts, more than the 23 it started with: it removes the 21 leaks and destroys the 80 values the prefix build already held, plus 2 that the full build would have changed. In 58% of exposed cuts the value was already final in the prefix, because the coarse horizon is later than the chapter in which the pronouns settled the value. This is FORMAL P3 with `B - A = 59` for gender; on a corpus where values typically settle only at the horizon, hiding would win [4.6].

**R6. A pre-registered anchored cue closes most of the price on the web novels.** The anchored cue reads the first third-person pronoun after each mention inside its own narration span and is used only when the paragraph rule says `unknown`. Setting chosen leave-one-serial-out, scored on the held-out serial, 24 cuts and 512 pairs (98 characters):

| Build (held-out, pooled) | Correct | Withheld | Wrong |
|---|---|---|---|
| Status quo | 361 (70.5%) | 146 | 5 (1.0%) |
| Plain horizon repair | 326 (63.7%) | 181 | 5 |
| Horizon repair plus anchored cue | 360 (70.3%) | 146 | 6 (1.2%) |

H5 supported on all three declared conditions: stamp divergence 0 on every cut for every setting, 97% of the lost correct values recovered (threshold 50%), 1.2% wrong (limit 3%), the same setting `(min_obs = 1, majority = 0.8)` chosen in every fold, and it holds with each annotator alone as the reference. The cue decided 35 values the plain repair withheld and 34 were right; it changed 0 values the plain repair already served [4.11].

**R7. The cue does not transfer uniformly, and the failure map says why.** On the English originals the pre-registered third hypothesis (the cue transfers: wrong rate at most 3%) is **not supported**: the anchored build is 7.8% wrong (14 of 179). Attribution before reading the bar: 11 of the status quo's 12 wrong values are three women the paragraph rule calls male in every build at every cut, a cut-independent extractor error, so the 3% bar, taken from a web-novel baseline where the status quo is about 1% wrong, fails every build including the unmodified one. The cue's own errors are one character (Milady), and of 11 values added 8 are right (73%), against 34 of 35 on the web novels [4.14]. On the synthetic volume the cue's wrong rate is 1.0% or less in seven of nine configurations and 4.1% and 5.5% in the two where own cues are sparse and misleading cues are at least half as common; the stricter `(2, 0.8)` stays at 1.8% and 3.1% there at lower availability. A usable rule: `(1, 0.8)` while misleading cues are much rarer than true ones, `(2, 0.8)` otherwise [4.13].

**R8. A shorter cue window fixed one failure and exposed a precedence flaw.** After R7, a pre-registered v2 window (also cut at `;`, `:` and dashes, and before an article plus a role noun) with the English books as a development set and the web novels as confirmatory data gave a split verdict: supported at `(2, 0.8)`, not supported at `(1, 0.8)` (9 wrong against 6), because a single surviving male pronoun overrode the correct honorific value for one character (Mother Shen) at three cuts. The flaw is the cue's precedence rule, not its window; the recommended window stays v1 and P8 was amended. The natural next step, a cue that only fills `unknown` and never overrides an honorific, is untested and must be pre-registered on data not used so far [4.16].

### 5.3 The model path of the same stage

The persona stage also calls a local model for characters with at least 25 mentions. With a real `qwen2.5:7b`, 101 pairs (47 characters) have a model read in both builds with an identical prompt; the discrete trait differs in 0 of them and the noise floor (a prefix build against its own repeat) is 0. So later chapters do not change the model read at these settings, and the per-character rate is bounded at about 6% (rule of three, 3/47). The large effect is the **gate**: the decision to call the model depended on a whole-volume mention count, so in 50 of 296 pairs (16.9%) the full build served the model's read and the prefix build the deterministic one, and these disagreed on a discrete trait in 37 (gender 27, register 15, age band 7), 12.5% of all character-cuts, a larger rate than the stamp defect. This is a leak of prominence, not of content (FORMAL P7). Deciding the gate chapter by chapter on the mentions read so far, with a memo that answers a repeated prompt without a new call, gives 0 gate-class pairs, 0 divergences among the 101 both-model pairs, a noise floor of 0 and an unchanged call count (348). The price: 37 of those 50 pairs now carry the deterministic read until the prefix itself reaches 25 mentions, and which of the two reads is right is unlabelled [4.8a, 4.15].

**What this does not say.** The audit compares a model with itself on identical prompts. It says nothing about whether the model's read depends on what the model remembers of the book. That is Channel 1.

### 5.4 Dependence, not only divergence: a counterfactual-suffix test (pre-registered, 2026-10-17)

Truncate-and-rebuild compares the full build with one other volume, the prefix. The definition (Section 3.1) quantifies over every volume with the same first `c` chapters, so a served value that depends on later chapters but happens to agree with the prefix is scored clean. `PREREG_COUNTERFACTUAL.md` (written before any modified build) keeps chapters `<= k` byte-identical, swaps the gendered pronouns of every later span (he and she, him and her, and so on), rebuilds the whole volume and asks whether the gender served at `k + 0.5` moves. It needs no truncation and no labels, and it works on a closed-vocabulary output where a string canary (Section 7.9) can never appear. Source: `data/eval/prefix_audit/counterfactual_suffix.json`, `scripts/prefix_audit/counterfactual_suffix.py`; CPU, deterministic path.

| Quantity, original 13 cuts of the three web novels | Status quo | Repaired |
|---|---|---|
| Gender character-cuts scored by both oracles | 289 | 296 compared |
| Diverge under truncate-and-rebuild | 23 (8.0%) | 0 |
| Depend on the suffix (served value moves when only the suffix changes) | **47 (16.3%)** | **0** |
| of which also diverge | 23 of 23 (H14.1: 100%, bar 70%) | - |
| of which do not diverge (H14.2) | 24: prefix already male, full male, counterfactual unknown 11 or female 8; female to unknown 2; unknown to female 3 | - |
| Outside the exposure window (H14.3) | 0 of 47 (all inside the 139 exposed cuts) | - |

All four pre-registered hypotheses are supported. Three readings follow. **(i)** Truncate-and-rebuild is a sound but not complete oracle on a single volume: it finds every divergence (all 23 also flip) and misses half of the dependence. In 24 cuts the served value is right on this book only because the later chapters happen to agree with the early ones; in 8 of them a book with the same first `k` chapters would make the system serve the opposite gender. **(ii)** The exposure screen holds under a second, independent oracle: every dependent cut is inside a window, and the share of exposed cuts that truly depend is 33.8% (47 of 139), twice the 16.5% that diverge, so the screen's "over-flagging" in R2 was partly dependence that truncation cannot see. **(iii)** The repair's guarantee (P6) holds under the stronger test: 0 of 296 cuts move. The archetype string derived from gender moves with it (51 cuts, status quo; 0 repaired); age band, register and `big_five` never move. Four further flips are for entities with no evidence before the cut, which the truncation audit does not score. Limits: one intervention (a pronoun swap; other suffix changes could expose other dependence), the deterministic path only, resolution held fixed.

---

## 6. Channel 1: parametric memory

*Exploratory numbers are from `NOVELTY_REPORT.md` Sections 4, 5.14 to 5.22 and `NOVELTY_ONE_PAGER.md`; confirmatory numbers are from `data/eval/chimera/confirm/main/analysis.json` and `e2/analysis.json` and are printed by `scripts/chimera/gen_ch1_tables.py`. Intervals are 95% event-cluster bootstrap intervals unless stated. Every result is tagged EXPLORATORY or CONFIRMATORY.*

### 6.1 Method

**Task.** An alias-reveal item: a passage in which a character is referred to by an alias ("the masked guest"), a candidate list that contains the true identity and decoys, and a question that asks who the alias is. For an item whose cutoff is before the reveal, the reader-warranted answer is UNDETERMINED. A **premature naming** is an answer that names the true identity when the reader-warranted answer is UNDETERMINED. The omniscient answer and the reader answer are reported together.

**Oracle.** Text-derived: the book's own explicit reveal sentence located by exact search, with the cutoff placed conservatively before it. Events (alias, reveal sentence, cast list) were selected by a language model and are **not owner-verified**. *Exploratory set:* 38 events from Project Gutenberg public-domain books (famous and obscure), 19 of whose books were never used in tuning. *Confirmatory set:* a seeded draw from 3,523 eligible Gutenberg books in three fame bands (fame W is the Wikidata sitelinks count of the book's item: high W >= 20, mid 3 to 19, low W < 3), mined with a frozen cue list and deterministic verification (reveal sentence located by exact search, identity token absent from the prefix, cast rules) by `qwen32b`, then audited by `mistral24` as EXPLICIT (42), IMPLIED (21) or NOT_SUPPORTED (5). The result is **68 events from 65 books** (53 test, 15 development); the pre-registered primary set is the **32 EXPLICIT test events** (25 low-fame, 6 mid, 1 high; 31 books). The mining yield was about 0.025 events per book, below the 75 events targeted, and the high band was exhausted after round 3, so the sample is dominated by obscure books (deviations log, addendum 4). Both the miner and the auditor are models that were also evaluated.

**Leakage as a difference.** For each item the same passage and candidate list are shown under original names (arm A) and with names replaced (arms B, B2, B3). Leakage is the rate of premature naming under A minus the rate under the renamed arms, with event-level (cluster) intervals because items within an event are not independent. The cipher arm B replaces proper nouns with consistent gibberish; the second independent cipher arm B2 checks the control against itself; the cue-preserving arm B3 replaces only cast and alias names with natural pseudonyms matched on gender and name type, which answers the objection that the gap measures lost name-borne cues rather than memory.

**Controls.**
1. *Unseen-text control.* The same items built on synthetic text no model has seen: any gap there is renaming damage, not memory. *Exploratory:* the gap on synthetic text is about zero. *Confirmatory E2 (exploratory-small):* 17 verified LLM-authored stories, gaps +0.0 (Mistral), +1.5 [0.0, +4.4] (OLMo) and -1.5 [-4.4, 0.0] (Qwen); underpowered, so a null of the control, not evidence that renaming costs nothing.
2. *Memory-free validity gate.* Two renamed arms against each other on real controls, plus A against B on unseen text; the usual original-versus-renamed gate on plain controls of famous books is itself partly memory-assisted and is not used as the gate. *Exploratory:* four of six models satisfy the memory-free gate. *Confirmatory:* the two cipher arms give the same answer on 84.6% to 87.5% of control items and 0% of answers are invalid for all three models; the original-versus-renamed control gap is 10 to 23 points (control accuracy A 0.85 to 0.90 against B 0.67 to 0.76), which is the memory-assisted plain-control effect the memory-free gate was built to avoid.
3. *Closed-book positive control.* Alias plus candidate list plus book title, no passage: shows whether the model maps the alias to the identity from memory, and that renaming removes it. *Exploratory (famous books):* models map the alias to the cast with the book title for 10 to 25 of 31 events, falling to 0 to 6 when renamed. *Confirmatory (mostly obscure books):* **2 of 68 events for each of the three models** with original names, so the positive control shows these models hold almost no usable memory of this sample.
4. *Cue-preserving pseudonym condition (B3).* Pre-registered. *Exploratory PD v5 (famous books):* gap with pseudonyms +16.1 [8.2, 25.0], recovered fraction -0.11 [-0.36, 0.06], i.e. the lost name cues do not explain the effect (supported). *Confirmatory H2:* pooled gap A minus B3 +5.7 [-1.3, +12.6] (one-sided p = 0.036, the pre-registered pass rule needs +10 points and a positive lower limit), **not passed**; the recovered fraction is undefined because the A minus B gap it divides by is about zero (interval [-28.5, +45.0]).
5. *Dose-response.* The per-event gap against how many models recognise the book (post hoc in the exploratory set, pre-registered as H3 in the confirmatory run). *Exploratory (38 events):* the small models' gap is about zero when at most two of them recognise the book and +40.9 points when all five do (Spearman +0.59, p = 0.00015); the reference model's gap against the local models' recognition is +0.37 (p = 0.024). *Confirmatory H3 (32 events, 31 books, fame W against mean event gap over the three models):* Spearman +0.30, raw one-sided p = 0.041, Holm-adjusted p = 0.145 against the pre-registered level 0.0125, so **not confirmed**. *Confirmatory P1 (addendum 5, written before any model saw an event):* the mean gap of high- and mid-fame events minus low-fame events is +7.6 points [-1.4, +18.3], one-sided p = 0.060, **not passed**; 7 against 25 events and a minimum detectable difference of 12.8 points at 80% power.

**Models.** *Exploratory:* five local models of 7B to 9B parameters at temperature 0 and one API model (`gpt-5.6-luna`, used before the owner's no-OpenAI instruction) as the reference; later exploratory runs add the three open models below on the famous-book sets. *Confirmatory:* `qwen32b` (Qwen2.5-32B, AWQ), `olmo32b` (OLMo-2-32B, fp8) and `mistral24` (Mistral-Small-3.2-24B, fp8) served by vLLM on one rented L40S at temperature 0, 2,220 E1 calls per model. A fourth arm, Claude Sonnet 5.5 through the owner's subscription, was stopped by the subscription session limit after 211 of 1,218 answers (8 events, no renamed-mention control) and is excluded from every pooled statistic; the pre-registered rule H1 needs at least three of four core models positive, so H1 cannot be met with three models and is reported as not passed by construction as well as by its estimate.

### 6.2 Results

**Exploratory results on famous and obscure public-domain books (analysed before the confirmatory design).** Gap = premature-naming rate under original names minus under renamed arms, percentage points.

| Quantity | Result | Tag |
|---|---|---|
| Reference model, all 38 events | +26.0 [16.8, 36.0]; 22 events positive against 1 (p = 1e-5) | EXPLORATORY |
| Reference model, 19 books never used in tuning | +17.7 [8.0, 28.3] | EXPLORATORY |
| Four 7B to 9B local models pooled, all 38 events | +11.5 [4.5, 19.0]; 22 events positive, 10 negative (p = 0.050) | EXPLORATORY |
| Local pool, final 7 fresh books (pre-registered PD v6) | -5.9 [-14.8, 1.0], **NOT SUPPORTED** (these models barely recognise the books) | pre-registered, exploratory set |
| Unseen synthetic text | about 0 | EXPLORATORY |
| Cue-preserving pseudonyms (PD v5) | gap +16.1 [8.2, 25.0], recovered fraction -0.11 [-0.36, 0.06] | pre-registered, exploratory set |
| Dose-response with recognition | local pool Spearman +0.59 (p = 0.00015); reference against local recognition +0.37 (p = 0.024) | post hoc |
| Weak-label robustness (20 events an independent model judged explicit) | valid-model pool +15.7 [4.7, 26.8]; reference model +29.9 [15.0, 45.8] | EXPLORATORY |
| Three open 24B to 32B models on famous sets (pod, exploratory) | 19 events: Mistral +34.4 [19.7, 49.2], Qwen +16.3 [5.3, 30.1], OLMo +7.4 [3.2, 12.0]; 12 events: Mistral +20.8, Qwen +4.7, OLMo +11.5; obscure sets (v6, v7): Mistral +11.1 and +2.8, Qwen and OLMo about 0 | EXPLORATORY |

**Confirmatory results (pre-registered, frozen events, one run; primary set = 32 EXPLICIT test events).** Source: `confirm/main/analysis.json`.

| Model | Events | Gap A-B (pts) | 95% CI | Gap A-B3 | Events +/- | Control accuracy A / B / B3 | Cipher arms agree |
|---|---|---|---|---|---|---|---|
| Mistral-Small-3.2-24B | 32 | +4.4 | [-2.3, +12.0] | +9.9 | 4/2 | 0.897 / 0.757 / 0.853 | 0.875 |
| OLMo-2-32B | 32 | +0.0 | [-4.4, +4.9] | +5.5 | 2/3 | 0.897 / 0.669 / 0.831 | 0.846 |
| Qwen2.5-32B | 32 | -0.8 | [-4.7, +2.3] | +3.4 | 1/1 | 0.846 / 0.750 / 0.809 | 0.846 |

| Pre-registered test | Estimate | One-sided p | Verdict |
|---|---|---|---|
| H1: pooled gap A-B >= +10 with positive lower limit, at least 3 of 4 models | +0.1 [-5.0, +5.2] | 0.468 | **not passed** (3 models only) |
| H2: pooled gap A-B3 >= +10 and recovered fraction < 1/3 | +5.7 [-1.3, +12.6] | 0.036 | **not passed** |
| H3: fame dose-response, Spearman >= 0.20 and p < 0.05 | +0.30 (32 events, 31 books) | 0.041 raw, 0.145 Holm | raw rule met, **not confirmed** after Holm (level 0.0125) |
| P1 (addendum 5, primary): high+mid minus low fame gap | +7.6 [-1.4, +18.3]; 7 against 25 events | 0.060 | **not passed**; minimum detectable 12.8 pts |

Mean gap by fame band (events, mean): high 1, +16.7; mid 6, +5.6; low 25, -0.4. Over all 53 verified test events the per-model gaps are +3.1 [-1.4, +8.0] (Mistral), +0.6 [-2.4, +3.9] (OLMo) and -0.9 [-3.3, +0.9] (Qwen).

**What the confirmatory run says.** On a sample that is 78% low-fame books, three open models show no premature-naming gap that original names add: the pooled interval excludes a gap above about 5 points, and the closed-book control shows why, because the models recover the identity from memory in 2 of 68 events. The positive control passing in the exploratory set and failing here is the consistent reading with the dose-response, not a contradiction of the exploratory result. The fame contrast is in the expected direction (+7.6 points) but is underpowered: with 7 high- and mid-fame events the study could only detect a difference of about 13 points, and the one high-fame event contributes almost nothing. **Nothing here shows that the effect is absent on famous books** (the high band was exhausted with 2 events, 1 in the primary set), and nothing here replaces the exploratory famous-book numbers; it bounds the effect on obscure books.

**E4: pseudonymisation as a mitigation (H5; replicates the idea of Jiang and Ferraro).** Pooled over the three models, pre-reveal premature naming is 5.0% under original names, 5.6% under a plain "do not name early" instruction (P1) and 2.6% under cue-preserving pseudonyms (P2); the reduction for P2 is 48% (one-sided p = 0.037, interval limited to [0, 1] by the small base rate). The price is accuracy: post-reveal accuracy falls 6.7 points [-13.3, -2.2] and control accuracy 15.6 points [-22.9, -8.9], outside the 5-point non-inferiority margin, so **H5 is not met**. Per model the pre-reveal rate goes 6.0% to 2.1% (Qwen), 9.1% to 3.9% (Mistral) and 0.0% to 1.8% (OLMo, an increase from zero). The base rate is so low that these reductions rest on a handful of items.

**E5: recap and profile spoilers (exploratory-small).** 24 events, 3 models, 2 tasks, 3 conditions (original, plain instruction, pseudonyms), 144 outputs per condition. The text-derived spoiler rule (a capitalised identity token that is absent from the input) fired **0 times in every condition and model**; the rate is 0.0% with a degenerate interval. This is a floor result under a narrow detector, not evidence that recaps are safe: the faithfulness check by a second model finds 90.0% to 90.9% of recap statements supported by the prefix in every condition, i.e. about 10% unsupported statements regardless of condition, which the spoiler rule does not measure. The E5 harm contribution is therefore **not shown**.

**OLMo training-data link (exploratory; infini-gram index of the OLMo-2 1124 corpus).** 62 books queried, 50 with a gap; presence score distribution {0: 24, 1: 9, 2: 9, 3: 8}; Spearman +0.13, permutation p = 0.41; mean gap +2.9 points for books present in the training data against +1.0 for books absent. **No evidence of a link**, and with these small gaps the check could not have found a small one. The check queried string hits, so a presence score of 0 does not rule out paraphrases or excerpts.

**What the claim says now.** Models can name a hidden identity before the book reveals it, much more often with the original names than with consistently replaced names, on famous public-domain books, and the effect rises with how well known the book is. This is exploratory evidence from 38 events, strongest for one API model; it reproduces at smaller size for open 24B to 32B models on the famous sets; it is **not** detected by a pre-registered run on obscure books where the closed-book control finds almost no memory, and the pre-registered fame contrast that would tie the two together is underpowered (p = 0.06, not passed). The claim is name-keyed memory leakage as an effect that depends on the book being known, not that it is the only mechanism, and it is a result about language models on public-domain Western fiction, not about the EchoTales pipeline or web serials.

### 6.3 What Channel 1 cannot be

Renaming removes memory keyed to names. Memory keyed to plot structure, style or quoted phrases is not removed, so the measured gap is a lower bound on parametric dependence in that sense and an upper bound in another (any residual renaming damage counts as leakage; the unseen-text control and the pseudonym arm bound it). The numbers describe the models tested, and the reference model is a single API model whose training data is unknown. The confirmatory numbers support one bound only: for three open 24B to 32B models on a mostly obscure sample, a pooled premature-naming gap above about 5 points (the upper 95% limit, +5.2) is excluded; the fame contrast cannot be resolved below about 13 points with this sample.

---

## 7. Both channels in one measurement: a second, generic system

*Pre-registered as `PREREG_RF_E2E_addendum_6.md` (frozen by `MANIFEST_RF_E2E.json` before any card existed; one amendment before any card, stated in the file). Results in `data/eval/chimera/rf_e2e/`, produced by `scripts/chimera/pd_rf_e2e.py`.*

### 7.1 Why a second system

Section 5 found derivation look-ahead in one pipeline, EchoTales' deterministic persona stage. That leaves open whether the defect belongs to that code or to a design. A widespread pattern in LLM reading assistants and retrieval pipelines is different from ours: a language model writes a **character card** from passages that mention the character, the card is built once over the whole volume, and it is stamped at the character's first appearance, so a reader-position filter serves it from that chapter on. We do not claim that a specific product builds cards exactly this way; W is a controlled stress test of that pattern, and the measurement is what it serves early when it is used. This section applies the same truncate-and-rebuild oracle to that design, on the 68 frozen confirmatory events of Section 6 (public-domain books, text-derived reveal and cut), and uses the renaming control of Section 6 to split what leaks into the part that needs the input and the part that needs only the model's memory.

### 7.2 Method

For each event the reader stands at the pre-registered cut, just before the reveal chapter. Two builds produce a card of at most 80 words for the aliased character with one fixed prompt ("Write a character card of at most 80 words for the character referred to as ALIAS, using these passages from the book"): the **whole-volume build W** sees up to 12 passages spaced evenly over all alias mentions in the book (each 500 characters before to 700 after the mention), and the **prefix build P** sees the same rule over mentions before the cut with every passage clipped at the cut. P is the truncate-and-rebuild reference, and a build versioned by evidence horizon equals P at every position by construction (P6), so P is also the repaired build. Each build is run on the original text (**orig**) and on the text under the frozen consistent letter cipher (**ren**). Local models (Llama-3.1-8B, Mistral-7B, Qwen2.5-7B) run at temperature 0; each cell is generated once.

A card **leaks** if it tells a reader at the cut who the alias really is. **Rule A (text-derived, primary; independent of any judge)** counts a leak when the card contains a name token of the identity that never occurs in the reader's prefix; it applies only to events whose identity name is new at the reveal (19 of 57 measurable events). **Rule B (model-judged, secondary)** asks a fixed judge outside the generator set (Qwen3-8B, thinking off, temperature 0) whether the card states or clearly implies that the alias and the identity are the same person; it applies to all 57 events with alias mentions on both sides of the reveal. In the renamed arm both rules compare cipher forms.

The four cells give a decomposition. **W-ren** can leak only through the input, because no model has seen the cipher names. **P-ren** should not leak at all (the validity check). **P-orig** can leak only through memory or inference from the prefix. **W-orig** is what a whole-volume card built by a model that knows the book serves to the reader. The input channel is W-ren minus P-ren (pre-registered RF1: at least +10 points pooled, positive lower limit, at least 2 of 3 models); the memory channel is P-orig minus P-ren (descriptive).

Events come from 65 books with almost one event per book (68 events), so the event-level bootstrap is close to a book-level one. The pre-registered primary endpoint is RF1 on rule A; rule B and the second judge are secondary and reported beside it, never pooled with it.

### 7.3 Results: the whole-volume card leaks through the input


#### Small local models (7 to 8B; addenda 6 and 7)

**Rule A (text-derived), primary set: 19 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Llama-3.1-8B | 36.8 | 31.6 | 0.0 | 0.0 | +31.6 [+10.5, +52.6] | 6 / 0 (p = 0.0156) | +0.0 [+0.0, +0.0] |
| Mistral-7B | 31.6 | 21.1 | 0.0 | 0.0 | +21.1 [+5.3, +42.1] | 4 / 0 (p = 0.0625) | +0.0 [+0.0, +0.0] |
| Qwen2.5-7B | 26.3 | 21.1 | 0.0 | 0.0 | +21.1 [+5.3, +42.1] | 4 / 0 (p = 0.0625) | +0.0 [+0.0, +0.0] |
| **Pooled (mean over models)** | 31.6 | 24.6 | 0.0 | 0.0 | +24.6 [+8.8, +42.1] | 3 of 3 models positive | +0.0 [+0.0, +0.0] |

RF1 SUPPORTED; RF2 validity P-ren rate 0.0% (valid); RF4 W-orig minus P-orig +31.6 [+14.0, +50.9].

**Rule B (judge), EXPLICIT and IMPLIED events: 54 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Llama-3.1-8B | 27.8 | 27.8 | 3.7 | 3.7 | +24.1 [+11.1, +37.0] | 14 / 1 (p = 0.000488) | +0.0 [+0.0, +0.0] |
| Mistral-7B | 13.0 | 11.1 | 5.6 | 0.0 | +11.1 [+3.7, +20.4] | 6 / 0 (p = 0.0156) | +5.6 [+0.0, +13.0] |
| Qwen2.5-7B | 16.7 | 16.7 | 1.9 | 0.0 | +16.7 [+7.4, +27.8] | 9 / 0 (p = 0.00195) | +1.9 [+0.0, +5.6] |
| **Pooled (mean over models)** | 19.1 | 18.5 | 3.7 | 1.2 | +17.3 [+9.3, +26.5] | 3 of 3 models positive | +2.5 [+0.0, +5.6] |

RF1 SUPPORTED; RF2 validity P-ren rate 1.2% (valid); RF4 W-orig minus P-orig +15.4 [+6.8, +25.3].

**Fixes.**

| Fix | Rule | Events | Leak before | Leak after | Removed [95% CI] | Content check |
|---|---|---|---|---|---|---|
| Versioned card (fix 1), orig names | A | 19 | 31.6% | 0.0% | +31.6 [+14.0, +50.9] | alias named 86.0% vs 82.5%; 94 vs 86 words |
| Versioned card (fix 1), ren names | A | 19 | 24.6% | 0.0% | +24.6 [+8.8, +42.1] | alias named 86.0% vs 82.5%; 94 vs 86 words |
| Versioned card (fix 1), orig names | B | 54 | 19.1% | 3.7% | +15.4 [+6.8, +25.3] | alias named 85.2% vs 82.7%; 93 vs 89 words |
| Versioned card (fix 1), ren names | B | 54 | 18.5% | 1.2% | +17.3 [+9.3, +26.5] | alias named 85.2% vs 82.7%; 93 vs 89 words |
| Pseudonymise and map back (fix 2) | A | 19 | 0.0% | 0.0% | +0.0 [+0.0, +0.0] | alias named 82.5% vs 87.7%; RF5 evaluated False, passes None |
| Pseudonymise and map back (fix 2) | B | 54 | 3.7% | 3.1% | +0.6 [-1.9, +3.7] | alias named 82.7% vs 87.7%; RF5 evaluated False, passes False |

Second judge (OLMo-2-32B, addendum 9, robustness only): W-ren 19.1% vs P-ren 1.9%, input channel +17.3 [+8.6, +27.2] over 54 events. Agreement with the first judge: 97.8% identical labels, kappa 0.88 (684 labels).

#### Larger open models (24 to 32B on the pod; addendum 8, separate stratum)

**Rule A (text-derived), primary set: 19 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Mistral-Small-3.2-24B | 26.3 | 26.3 | 0.0 | 0.0 | +26.3 [+5.3, +47.4] | 5 / 0 (p = 0.0312) | +0.0 [+0.0, +0.0] |
| Qwen2.5-32B | 15.8 | 15.8 | 0.0 | 0.0 | +15.8 [+0.0, +31.6] | 3 / 0 (p = 0.125) | +0.0 [+0.0, +0.0] |
| **Pooled (mean over models)** | 21.1 | 21.1 | 0.0 | 0.0 | +21.1 [+5.3, +39.5] | 2 of 2 models positive | +0.0 [+0.0, +0.0] |

RF1 SUPPORTED; RF2 validity P-ren rate 0.0% (valid); RF4 W-orig minus P-orig +21.1 [+5.3, +39.5].

**Rule B (judge), EXPLICIT and IMPLIED events: 54 events.** Leak rate (% of events) per cell; input channel = W-ren minus P-ren; memory channel = P-orig minus P-ren.

| Model | W-orig | W-ren | P-orig | P-ren | Input channel [95% CI] | Events W-ren > P-ren / < | Memory channel [95% CI] |
|---|---|---|---|---|---|---|---|
| Mistral-Small-3.2-24B | 27.8 | 31.5 | 1.9 | 3.7 | +27.8 [+16.7, +40.7] | 15 / 0 (p = 3.05e-05) | -1.9 [-9.3, +3.7] |
| Qwen2.5-32B | 14.8 | 14.8 | 1.9 | 0.0 | +14.8 [+5.6, +24.1] | 8 / 0 (p = 0.00391) | +1.9 [+0.0, +5.6] |
| **Pooled (mean over models)** | 21.3 | 23.1 | 1.9 | 1.9 | +21.3 [+13.0, +30.6] | 2 of 2 models positive | +0.0 [-3.7, +4.6] |

RF1 SUPPORTED; RF2 validity P-ren rate 1.9% (valid); RF4 W-orig minus P-orig +19.4 [+9.3, +30.6].

**Fixes.**

| Fix | Rule | Events | Leak before | Leak after | Removed [95% CI] | Content check |
|---|---|---|---|---|---|---|
| Versioned card (fix 1), orig names | A | 19 | 21.1% | 0.0% | +21.1 [+5.3, +39.5] | alias named 84.2% vs 78.9%; 91 vs 81 words |
| Versioned card (fix 1), ren names | A | 19 | 21.1% | 0.0% | +21.1 [+5.3, +39.5] | alias named 84.2% vs 78.9%; 91 vs 81 words |
| Versioned card (fix 1), orig names | B | 54 | 21.3% | 1.9% | +19.4 [+9.3, +30.6] | alias named 84.3% vs 80.6%; 90 vs 82 words |
| Versioned card (fix 1), ren names | B | 54 | 23.1% | 1.9% | +21.3 [+13.0, +30.6] | alias named 84.3% vs 80.6%; 90 vs 82 words |
| Pseudonymise and map back (fix 2) | A | 19 | 0.0% | 0.0% | +0.0 [+0.0, +0.0] | alias named 78.9% vs 81.6%; RF5 evaluated False, passes None |
| Pseudonymise and map back (fix 2) | B | 54 | 1.9% | 2.8% | -0.9 [-4.6, +1.9] | alias named 80.6% vs 84.3%; RF5 evaluated False, passes False |

Second judge (OLMo-2-32B, addendum 9, robustness only): W-ren 22.2% vs P-ren 0.9%, input channel +21.3 [+13.0, +30.6] over 54 events. Agreement with the first judge: 97.8% identical labels, kappa 0.89 (456 labels).

**Verdicts (pre-registered).** RF1, the input channel, is **supported** on the primary rule A (19 events: W-ren minus P-ren +24.6 points [+8.8, +42.1], 3 of 3 models positive) and **supported** on the secondary judge rule B (54 events: +17.3 [+9.3, +26.5]). The validity check RF2 holds: the prefix card on renamed text leaks in 0.0% (rule A) and 1.2% (rule B) of events. The memory channel RF3 (P-orig minus P-ren) is +2.5 points [+0.0, +5.6] by rule B. RF4, what a reader of the whole-volume card meets beyond the prefix card on original names, is +15.4 points [+6.8, +25.3] by rule B.

**Larger open models (addendum 8, separate stratum: Mistral-Small-3.2-24B, Qwen2.5-32B).** Rule B: W-ren 23.1% vs P-ren 1.9%, input channel +21.3 [+13.0, +30.6], RF1 supported; rule A: 21.1% vs 0.0%, RF1 supported. Memory channel (rule B) +0.0 [-3.7, +4.6]; W-orig minus P-orig +19.4 [+9.3, +30.6]. Fix 2 on these models: prefix-card leak 1.9% to 2.8% (-0.9 [-4.6, +1.9]), alias named 80.6% to 84.3%; RF5 not evaluated (no memory leak with a positive lower limit).

**Second judge (addendum 9, robustness only), the 7 to 8B models.** With OLMo-2-32B as the judge the whole-volume card leaks in 19.1% of events on renamed text against 1.9% for the versioned card (input channel +17.3 [+8.6, +27.2]); the two judges give the same label on 97.8% of 684 cards (Cohen's kappa 0.88). **Second judge (addendum 9, robustness only), the larger models.** With OLMo-2-32B as the judge the whole-volume card leaks in 22.2% of events on renamed text against 0.9% for the versioned card (input channel +21.3 [+13.0, +30.6]); the two judges give the same label on 97.8% of 456 cards (Cohen's kappa 0.89).

### 7.4 The fixes

**Fix 1, the versioned card.** Building the card from the prefix (the versioned policy at this position) removes +17.3 points [+9.3, +26.5] of leak on renamed text and +15.4 [+6.8, +25.3] on original names by rule B (rule A: +24.6 and +31.6); the residual is the memory channel. The price is one card build per distinct evidence horizon instead of one per character (here, one extra build per event at this position); cards stay about as long and name the alias about as often (content check column).

**Fix 2, pseudonymise and map back.** RF5 was not evaluated, because the memory channel had no lower limit above 0 (no memory leak to fix at these models). Descriptively, the prefix card's judge-rule leak goes from 3.7% to 3.1% (+0.6 [-1.9, +3.7]) and the share of cards naming the alias from 82.7% to 87.7%; by the strict text rule from 0.0% to 0.0%.

### 7.5 What the second system adds

The look-ahead defect of Section 5 is not a property of one codebase: a standard whole-volume, first-mention-stamped LLM card has it, at a rate measured on public-domain books with a text-derived oracle, and it persists when every name is replaced by a cipher no model has seen, so it is a property of the build, not of memory. The versioned repair, whose guarantee is a policy property (P6), removes it here as it did in Section 5. At the cut, for 7 to 8B models on these mostly obscure books, the memory channel is small, which agrees with the confirmatory bound of Section 6; both channels are now measured on one system with one oracle. Limits: one card prompt, one reader position per event, small local models plus at most two larger open models, a judge that is a language model (rule B), and model-selected events.

### 7.6 Robustness: a don't-spoil instruction and a second cipher (addendum 10)

Pre-registered after an external review asked both questions and before any of these cells existed (Qwen2.5-7B; same events, rules and judge; the second model of the addendum, Llama-3.1-8B, was stopped part-way to meet the submission time and is reported not run). **R1:** the whole-volume card with the instruction "Avoid spoilers: do not reveal secret identities, disguises or plot twists." **R2:** the same comparison under the frozen second, independent cipher.

| Rule | W renamed % | W renamed + don't-spoil % | P renamed % | Don't-spoil W minus P [95% CI] | Second cipher W vs P %, input channel [95% CI] |
|---|---|---|---|---|---|
| Rule A (text), 19 events | 21.1 | 15.8 | 0.0 | +15.8 [+0.0, +31.6] | 31.6 vs 0.0: +31.6 [+10.5, +52.6] |
| Rule B (judge), 54 events | 16.7 | 14.8 | 0.0 | +14.8 [+5.6, +24.1] | 13.0 vs 7.4: +5.6 [-5.6, +18.5] |

Rule A (text): with the instruction the whole-volume card still leaks in 15.8% (renamed) and 21.1% (original) against 21.1% and 26.3% without it; the remaining gap to the versioned card (+15.8 points) is not significant at 19 events (95% lower limit 0.0); with the second cipher the input channel is +31.6 [+10.5, +52.6], robust to the cipher. Rule B (judge): with the instruction the whole-volume card still leaks in 14.8% (renamed) and 18.5% (original) against 16.7% and 16.7% without it; prompting does not remove the input leak; with the second cipher the input channel is +5.6 [-5.6, +18.5], not shown robust to the cipher (the judge flags 7.4% of second-cipher prefix cards, which cannot contain the identity, above the 5% validity bound of addendum 6, so this judge-rule value is not interpretable and the text rule is the reading for the second cipher).

### 7.7 Two checks on the measurement (post hoc, no new model calls)

**The judge against a criterion with no model in it.** On the 19 events where rule A applies, every card of all five models and four cells has both a text-derived label and a judge label (380 labels). Taking rule A as the reference, the judge finds 91.7% of the text-rule leaks (44 of 48) and flags 0.9% of non-leaks (3 of 332); agreement 98.2%, Cohen's kappa 0.92. This is validity against a text-derived criterion, not only agreement between two models (Section 7.3), though it covers only the events whose identity name is new at the reveal.

**How long a reader is exposed.** A first-mention-stamped card is visible from the alias's first mention until the reveal. Over the 54 events that window is a median 37.4% of the book; for the 55 whole-book cards on cipher names that the judge marks as leaking, the reader can see the spoiler for a median 11.4% (mean 17.8%) of the book before the book itself reveals it. Source: `data/eval/chimera/rf_e2e/posthoc_judge_validity_and_exposure.json`.

### 7.8 Earlier reader positions and a second prompt (addendum 11, Qwen2.5-7B)

Pre-registered after the external review and before any of these cells existed. Cipher names throughout.

| Rule | Whole-volume card (any position) % | Versioned at 50% % | Versioned at 75% % | Versioned at the cut % | Second prompt W vs P %, input channel [95% CI] |
|---|---|---|---|---|---|
| Rule A (text), 19 events | 21.1 | 0.0 | 0.0 | 0.0 | 26.3 vs 0.0: +26.3 [+10.5, +47.4] |
| Rule B (judge), 54 events | 16.7 | 1.9 | 1.9 | 0.0 | 18.5 vs 0.0: +18.5 [+9.3, +29.6] |

Rule A (text): the versioned card leaks in 0.0% at the half-way position and 0.0% at three quarters, while the whole-volume card, served from the first mention, leaks in 21.1% at every position; with the second prompt the input channel is +26.3 [+10.5, +47.4], robust to the prompt. Rule B (judge): the versioned card leaks in 1.9% at the half-way position and 1.9% at three quarters, while the whole-volume card, served from the first mention, leaks in 16.7% at every position; with the second prompt the input channel is +18.5 [+9.3, +29.6], robust to the prompt.

### 7.9 Suffix canaries: a judge-free test on every event, and a second design (addendum 12, pre-registered 2026-10-17)

Rule A could score only 19 of 57 events and rule B needs a judge. `PREREG_RF_E2E_addendum_12_suffix_canaries.md` (frozen by `MANIFEST_RF_CANARY.json` before any cell existed) changes the text **after the cut only**: every identity name token is replaced by a fresh invented token (the book still reveals the alias, now under a name nobody has seen), and one sentence "<alias> had been born in <invented place>." is planted after the first post-reveal alias mention. Original names everywhere else; no renaming, no judge. A hit is a string match against tokens we planted, so by P9 it has no false positives and no memory explanation. Two designs: the whole-volume card W of Section 7.2 (against the versioned card P), and a new one, **a long-context assistant told where the reader is**. It receives up to 24,000 characters before the cut, the line `[READER POSITION: the reader has read up to here]`, and up to 16,000 characters after it with the reveal inside. The instruction is "Answer the reader's question using only the text before the marker, and do not reveal anything that happens after it", the question is "Who is <alias>?" (L_can), and the control is the same prompt with the suffix removed (L_trunc). Three local models, temperature 0. Source: `data/eval/chimera/rf_e2e/canary_analysis.json`, `scripts/chimera/rf_canary.py`.

| Design (EXPLICIT and IMPLIED events) | Events | Llama-3.1-8B | Mistral-7B | Qwen2.5-7B | Pooled [95% CI] | Without the suffix | Events +/- per model |
|---|---|---|---|---|---|---|---|
| Whole-volume card, reveal canary (H12.1) | 54 | 35.2% | 18.5% | 14.8% | **22.8% [14.2, 31.5]** | 0 (versioned card) | 19/0, 10/0, 8/0 |
| Long-context positional instruction, reveal canary (H12.2) | 46 | 34.8% | 47.8% | 39.1% | **40.6% [29.7, 51.4]** | 0 (truncated context) | 16/0, 22/0, 18/0 |
| Whole-volume card, fact canary | 54 | 20.4% | 20.4% | 22.2% | 21.0% [12.3, 30.9] | 0 | |
| Long-context positional instruction, fact canary | 39 | 15.4% | 5.1% | 12.8% | 11.1% [5.1, 17.9] | 0 | |

All three pre-registered hypotheses are supported. H12.1 and H12.2 pass with 3 of 3 models positive and not one event in which the prefix-only cell leaked and the suffix cell did not. H12.3, the structural validity check, holds: 0 hits in every versioned-card and truncated-context cell (342 outputs), so the harness is sound. On EXPLICIT events only the rates are 27.2% [17.5, 37.7] (38 events) and 46.2% [32.3, 60.2] (31 events). **What it adds.** (i) The input-channel leak of Section 7.3 is confirmed on all 54 events by a criterion with no model in it: 22.8% by canary against 18.5% by the judge on cipher names. On the 19 rule-A events the canary and the earlier text rule agree closely (canary 5, 6 and 4 events per model against rule A 5, 7 and 6, with 5, 5 and 4 in both), although the texts differ. (ii) **Telling a long-context model where the reader is does not keep it there.** With an explicit instruction not to reveal anything after the marker, the answer quotes the invented post-marker name in 40.6% of events, nearly twice the whole-volume card's rate. Typical outputs: "Grieve is revealed to be Ferdinand count Venthan"; "The person referred to as 'She' is Venbraost ... However, at this point in the story, she has not yet been identified by name." (iii) The leak is not specific to the spoiler: an ordinary planted fact (a birthplace) is carried into 21.0% of whole-volume cards and 11.1% of long-context answers. (iv) Memory plays almost no part here. Without the suffix, the real identity of the 19 rule-A events is named once in 114 prefix-only outputs (Qwen, truncated context). **Exposure.** In 35 of 54 events at least one of the card's 12 sampled passages contains a canary; given exposure, the card carries it in 22.9% to 54.3% of events by model. **Look-ahead or spoiler?** A canary hit measures look-ahead (suffix content in the output), which is the contract. *Post hoc* (not pre-registered; `scripts/chimera/rf_canary_posthoc.py`, `posthoc_canary_judge.json`), the Section 7.2 judge asked of every hit whether the output equates the alias with the canary-named identity. It says yes for 29 of 38 whole-volume card hits (76%) and 49 of 56 long-context hits (88%), so most hits are the spoiler itself and not an incidental mention. **Limits.** The long-context design was run with a 7 to 8B model's 12,288-token window, not a whole book, and one prompt. The fresh tokens are invented words, which a model might treat differently from real names. The events are the same model-selected events.

### 7.10 A selection leak: every passage is before the reader, and the answer still spoils (addendum 13, pre-registered 2026-10-17)

The position filter described for reading assistants checks what is served, and P10 says a canary cannot see a leak that moves no suffix content. `PREREG_RF_E2E_addendum_13_selection_leak.md` (frozen by `MANIFEST_RF_SELECTION.json`) measures one on a generic entity-indexed design, on the 36 EXPLICIT and IMPLIED events whose identity is already named in the reader's prefix. These are exactly the events rule A could not score. At index time a resolver (Qwen2.5-7B) reads the reveal window and decides whether the alias and the identity are one person. It merged them in 24 of 36 events. Retrieval for the alias then returns up to 12 passages spaced over the pre-cut mentions of **both** names, each clipped at the cut (asserted in code; 37.8% of passages are identity passages), and the card prompt of Section 7.2 runs on cipher names, so memory cannot contribute. The reference is the prefix-built index (the stored P_ren card of Section 7.2), which has no reveal to merge on. Judge: Qwen3-8B, rule B.

| Events | Merged-entity card M | Prefix-built card P | M minus P [95% CI] | Per model, events +/- |
|---|---|---|---|---|
| Resolver merged (H13.1, primary), 24 | 19.4% | 1.4% | **+18.1 [+4.2, +33.3]** | Llama 4/1, Mistral 5/0, Qwen 5/0 |
| Ideal merge (H13.2), 36 | 14.8% | 1.9% | +13.0 [+3.7, +24.1] | 4/1, 5/0, 6/0 |

Both hypotheses are supported, with 3 of 3 models positive. The cards fuse the two people without any later text: "Euaculhtk (also known as Acktvit Eteitu)", "Name: Jtvliack Woqtkk (also referred to as Mr. Woqtkk)", "Mr. Ktcvz (also known as Ncbhtqs)". Every sentence the generator saw is one the reader has read. The suffix entered only through the index's decision about which prefix passages belong to the alias. A suffix canary cannot fire here, because the input holds no suffix token, and canarying the reveal would also break the link the resolver used (P10). A position filter on served passages passes it. Only a rebuild from the prefix (here, the prefix-built card) exposes it. **Checks.** The author session read the 16 cards the judge flagged (not a human check). In one event (two models), the "identity" is a descriptive phrase rather than a name and the judge's yes looks wrong. Excluding that event post hoc gives +15.9 [+2.9, +30.4] over 23 events. **Limits.** The judge was validated against the text rule only on rule-A events (Section 7.7), and here both names occur in the input, which is the case where a judge is most needed and least validated. The resolver is a 7B model on one window. The design is a controlled stand-in for an entity-indexed assistant, not a specific product. 24 events.

**What Sections 7.9 and 7.10 add together.** The input channel has (at least) two mechanisms that need different detectors. Content leaks are caught by a judge-free black-box canary on every event. Selection leaks are invisible to canaries and to any filter on served items, and they need a rebuild from the prefix or a counterfactual suffix. The two measured selection leaks in this paper are EchoTales' prominence gate (Section 5.3) and merged-entity retrieval.

---

## 8. Repairs and trade-offs

The two channels have different repairs because they have different causes. Table 1 puts them side by side.

| | Channel 2, derivation look-ahead | Channel 1, parametric memory |
|---|---|---|
| Cause | A derived fact is stamped earlier than the evidence it was computed from | The model's weights encode the suffix |
| Instrument | Truncate and rebuild: an exact oracle, the system itself | Renaming (and pseudonym) control, unseen-text control, closed-book probe: a proxy |
| Can the input alone fix it? | Yes: recompute from the prefix | No: the suffix is not in the input |
| Repair measured | Versioning by evidence horizon; anchored cue; prefix-causal gate | Pseudonymisation (E4, cue-preserving pseudonyms; replicates Jiang and Ferraro) and a plain instruction not to name early; pseudonyms halve premature naming (5.0% to 2.6%, p = 0.037) and the plain instruction does nothing (5.6%) |
| What it guarantees | Divergence 0, for any derivation that reads only the prefix (P6) | Nothing: a statistical reduction on a small base rate, not a guarantee; H5 not met |
| Price | 1 to 4 supported values withheld per premature disclosure prevented; cue recovers 97% at 1.2% wrong on web novels, less on English originals | Post-reveal accuracy -6.7 points and plain-control accuracy -15.6 points, both outside the 5-point margin |
| What it leaves | Body splits (7 of 296 cuts), appearance and world facts, the `prominence` column unrepaired; derivation errors (Naya, Charlotte, Mrs. Bedwin, Kitty) untouched | Name-keyed memory is measured, not removed |

**The Channel 2 frontier, as a trade-off.** Plotted as leaks against losses on the 289 gender cuts: doing nothing sits at (23, 0); hiding every exposed fact at (0, 82); versioning at divergence 0, but with 35 fewer correct values than the status quo on the 245 labelled exposed cuts. On the separate held-out set of 512 labelled pairs, versioning plus the anchored cue also has divergence 0 and brings the correct share back to 70.3% against the status quo's 70.5%, with 1.2% wrong against 1.0%. Each step up the frontier replaces a structural defect with an extractor-quality question: after the repair, how much of a reader's accessible knowledge the system serves depends on how well `D` reads a prefix, and the cue is an attempt to improve `D` on prefixes at a bounded error.

**What this means for deployment.** A reader-synchronised assistant must not serve the anticipation; a consumer that must commit before a reveal (voice casting for an audiobook, which must pick a voice before the narrator names the speaker's gender) wants it. The repair is therefore a flag, off by default, and the cost is stated: the choice is a product decision, and the data say what each side of it costs.

**How the channels interact.** The versioned policy's guarantee belongs to the policy and not to the derivation (P6), so replacing the lexical derivation with a model call leaves divergence at 0 (Section 5.3) and leaves Channel 1 untouched. A system can pass the full Channel 2 audit and still name a character prematurely because the model remembers the novel. Conversely a memory-free model inside a pipeline with dishonest stamps still serves look-ahead. The two instruments are independent and neither alone certifies reader-faithfulness.

---

## 9. Combined view of the evidence

| Claim | Tier | Where |
|---|---|---|
| Stamp-versus-evidence look-ahead exists in a deployed narrative graph | System-internal (no labels), exact oracle | Section 5.2 R1 |
| It reproduces without annotators and has a dose-response | Synthetic, truth by construction | R1, R6 to R7 |
| It reproduces on a second text domain | System-internal; mention layer is a gazetteer | R1, R7 |
| 1.7% to 3.5% of character-cuts are premature disclosures | Two model annotators, no human | R3 |
| The repair gives exactly 0 divergence | System-internal, every run | R4 |
| Hiding exposed facts is worse than doing nothing | System-internal (stored values) | R5 |
| The anchored cue recovers 97% at 1.2% wrong | Model-labelled, pre-registered, held-out serial | R6 |
| The prominence gate repair gives 50 to 0 | System-internal, real local model | Section 5.3 |
| Models name hidden identities earlier under original names, on famous books | Text-derived oracle, model-selected events; EXPLORATORY | Section 6.2 (reference model +26.0 [16.8, 36.0] over 38 events) |
| The effect is not explained by lost name-borne cues | Pre-registered PD v5, famous books; text-derived | Section 6.2 (recovered fraction -0.11) |
| The effect depends on how well known the book is | Post hoc in the exploratory set; CONFIRMATORY fame contrast underpowered and not passed | Section 6.2 (Spearman +0.59; P1 +7.6, p = 0.060) |
| Open 24B to 32B models show no gap on obscure books | CONFIRMATORY, one run, 32 events; closed-book control finds memory in 2 of 68 events | Section 6.2 (pooled +0.1 [-5.0, +5.2]) |
| Pseudonymisation lowers premature naming at an accuracy cost | CONFIRMATORY E4, small base rate; H5 not met | Section 6.2 |
| A whole-volume LLM character card leaks the reveal through the input; the versioned card fixes it | Pre-registered (addenda 6 and 7); rule A text-derived, rule B judge-labelled | Section 7 (W-ren 18.5% vs P-ren 1.2%) |
| Recap spoilers and a link to OLMo training data | EXPLORATORY-small; both null | Section 6.2 (0 spoilers in 144 outputs per condition; Spearman +0.13, p = 0.41) |
| The deployed stage depends on later chapters twice as often as it diverges; the repair removes both | System-internal, pre-registered counterfactual suffix | Section 5.4 (47 vs 23 of 289; 0 repaired) |
| The whole-volume card's leak holds on every event by a judge-free criterion | Pre-registered (addendum 12); suffix canaries, text-derived | Section 7.9 (22.8% vs 0, 54 events) |
| A long-context model told where the reader is still quotes later text | Pre-registered (addendum 12); suffix canaries | Section 7.9 (40.6% vs 0, 46 events) |
| A selection leak spoils with no suffix text in the input | Pre-registered (addendum 13); judge-labelled | Section 7.10 (19.4% vs 1.4%, 24 events) |
| Canaries are sound and blind to selection leaks; the read-set table holds on the real derivation | Elementary propositions, property-tested | Sections 3.2, 3.3 (P9 to P11) |

### 9.1 Claim-to-evidence matrix

| Claimed contribution | Evidence | Status | Closest prior work and how it differs |
|---|---|---|---|
| 1. Premature resolution under prefix truncation with an entitlement oracle | Section 6; 38 exploratory and 68 confirmatory events | Construct and instrument demonstrated; effect shown on famous books only (exploratory) | WhoDunIt (arXiv 2502.07747, abstract read; Gutenberg source and "full-story only" are LEAD until read in full) and Jiang and Ferraro (arXiv 2412.14368, abstract read, v6) rename characters but do not truncate before the reveal |
| 2. Renaming validity checks on famous books are themselves memory-assisted | Section 6.1 control 2 and the control accuracy gap in Section 6.2 | Supported in the exploratory pool; the confirmatory control gap is 10 to 23 points | not found in the works above; absence is a bounded negative |
| 3. Derived-attribute horizon leakage and its repair | Section 5 (Channel 2) | Strongest result: exact oracle, three data kinds, divergence 0 after repair | point-in-time correctness (feature stores) and look-ahead bias (DatedGPT, arXiv 2603.11838, abstract read) are the parent concepts; SurrealDB's spoiler-safe memory is a LEAD for stamped events, not derived attributes |
| 3b. The look-ahead defect generalises to a standard LLM card design and the versioned repair fixes it | Section 7 | Pre-registered; RF1 supported (rule A), supported (rule B) | position-aware assistants (Kindle Ask this Book, TDC 8646) describe progress filtering, not a check of derived summaries |
| 3c. Suffix canaries: a black-box, judge-free oracle for content look-ahead, with a long-context positional-instruction design measured | Sections 3.3, 7.9 | Pre-registered; H12.1, H12.2, H12.3 supported | canary strings for memorisation (Carlini et al. 2019) and CanaryBench (arXiv 2601.18834, snippet) plant secrets in training data or conversations, not after a reading position; cutoff-leakage benchmarks (ExAnte, TimeSPEC, snippets) score claims against dated sources |
| 3d. Selection leaks: a class invisible to content tests and to position filters, measured on a generic entity-indexed design | Sections 3.3, 7.10 | Pre-registered; H13.1, H13.2 supported (judge-labelled) | entity resolution for GraphRAG is a standard step (search results, not read in full); no source found that tests it against a reading position |
| 3e. Counterfactual-suffix dependence on the deployed graph | Section 5.4 | Pre-registered; H14.1 to H14.4 supported | metamorphic testing uses input changes without an oracle (Section 4); not found applied to a reading position |
| 4. Link to OLMo training data | Section 6.2 | **Null**: Spearman +0.13, p = 0.41 | none |
| 5. Recap harm (E5) | Section 6.2 | **Not shown**: 0 spoilers under the detector | none |
| Not claimed: fame dose-response | Section 6.2 | Confirms Chang et al. (2023) | the claim is theirs |
| Not claimed: pseudonymisation mitigation | Section 6.2 | Replicates the idea of Jiang and Ferraro | the method is theirs |

---

## 10. Limitations

**Label provenance, plainly.**
- *Channel 2 labels are model-generated.* The first annotator is the Claude session that also designed and implemented the repair; its labels were written blind to every system value and frozen by hash before scoring, but it is not independent of the work. The second annotator is `gpt-5.6-luna`. They agree with kappa 0.61 on 117 characters (0.63 on 46 prefix items) and never contradict, and the premature rate depends on the annotator (1.7% to 3.5% on the same cuts). 31.0% of the 142 labelled characters remain unknown or non-person, above the declared 25% limit, so correctness results are flagged as a subset result. A 30-character human sheet is prepared (`labels/human_check.csv`) and **unfilled**.
- *Channel 2's system-internal and synthetic results use no labels.* The divergence counts, the repair's zero and the synthetic grid need no annotator; the synthetic generator shares the cue's assumption (own pronouns sit right after the name), so a high cue score there is partly true by construction.
- *Channel 1's oracle is text-derived, not human-labelled.* The reveal sentence is found by exact search; the choice of events, reveal sentences and cast lists was made by a language model and is not owner-verified. No human check has arrived and none is claimed. In the confirmatory run the miner (`qwen32b`) and the auditor (`mistral24`) are both evaluated models, so event selection and audit are not independent of the subjects; the audit labelled 5 of 68 events NOT_SUPPORTED and 21 IMPLIED, and the primary set keeps only the 42 EXPLICIT events of which 32 are in the test split.
- *Section 7's rule B is labelled by a judge model (Qwen3-8B), outside the generator set but a language model, and a second judge (OLMo-2-32B) agrees with it; agreement between two models is reliability, not validity, so rule A, text-derived and independent of any judge, is the primary endpoint and applies to 19 events only. A don't-spoil instruction baseline and a second cipher were run (Section 7.6, two small models). The judge was checked against the text-derived rule (Section 7.7: kappa 0.92). Not yet done and the natural next steps: judge validation on events where the text rule does not apply, paraphrase controls and further cipher families, more prompts and models for Sections 7.6 and 7.8 (run on one model), and products other than this stress-test card.*
- *Label files contain short quotations from copyrighted translated novels and are not for publication as they are.* Source novels are not distributed.

**Scope.**
- One codebase and one persona stage; five real volumes (three translated web novels and two English originals), plus a synthetic volume. The second domain's mention layer is a gazetteer, which is cleaner than the real resolver and flatters the extractor.
- Cuts are nested, so intervals over character-cuts are optimistic; the divergence rate itself depends on where the cuts fall (4.5% to 8.0%).
- Resolution is held fixed in the Channel 2 audit; the resolver's own causality is not re-tested here, and the whole-volume title-holder and transmigration passes are non-causal by design.
- The static screen's soundness rests on a read set that is now property-tested on the real deterministic derivation (Section 3.2). It also held under a second, independent oracle (counterfactual suffix: 0 of 47 dependent cuts outside a window, Section 5.4). The body-split and model paths are not covered, and the `big_five` whole-volume dependency never occurred on real data.
- The counterfactual suffix is one intervention (a pronoun swap); the canaries are invented words; the long-context design used a 12,288-token window with 7 to 8B models, not a whole book in a frontier model; the selection-leak result is judge-labelled on events where the judge is least validated, with a 7B resolver. All of Sections 7.9 and 7.10 use local models only.
- The cue is English-translation specific; its precision is 97% on the web novels, 73% to 88% on the English originals, and a pre-registered bar failed there. It has a documented precedence flaw (R8) whose fix is untested.
- Unrepaired: body splits (7 of 296 cuts), unnamed title holders (one verified example with a 61-chapter window), the `prominence` column, appearance and world facts (unmeasured because they need a model whose prompt holds all passages). At least five modules read persona attributes outside `state_of` and have not been audited against several rows per key, which is why the repair is a flag with no CLI wiring.
- Chapter granularity: a revision is stamped at the end of its chapter, so a character introduced mid-chapter has no traits until the chapter ends.
- The model-path result is one 7B model at temperature 0, shared GPU, memo valid only if identical prompts give identical answers (noise floor 0 over 101 pairs here, not a general guarantee), and does not say which of the two reads is correct.
- Channel 1 is a result about language models on famous public-domain books; weaker and not reliably replicated for small local models on less-famous books; the strongest evidence rests on one API model; not evidence that the EchoTales pipeline itself leaks a memorised identity. The confirmatory run has 68 events (target 75 to 150) from a sample that is 78% low-fame, so its tests are underpowered (minimum detectable fame contrast about 13 points) and its nulls are not evidence of absence; the Claude arm is partial and excluded; the E5 spoiler detector is narrow; E2 has 17 LLM-authored stories; the OLMo link uses string hits on one model's corpus index; and the renaming control misses memory keyed to plot or style. Several earlier Channel 1 verdicts were inconclusive or partially supported by their pre-registered rules and are reported as such.
- Several analyses were run in sequence on the same data (the report records six Channel 1 analysis versions, each pre-registered, none discarded; Channel 2's cue grid was chosen by leave-one-serial-out, and the English books became a development set after they were used to diagnose the cue).

**What would change the conclusions.** A human-labelled check that moves the premature-disclosure rate outside the 1.7% to 3.5% range; a second, independently built system showing the same stamp-versus-evidence gap (or not); a property-based test over the real derivation that finds a read set that is not a certificate; for Channel 1, a larger human-verified event set and a model for which the closed-book control fails.

---

## 11. Conclusion

We stated one contract for position-aware reading assistants, reader-faithfulness: the output at chapter c may depend only on chapters up to c. We showed that it can be broken through the input, when a derived fact is stamped earlier than the evidence it was computed from, and through the parameters, when a model has read the book. For the first channel truncate-and-rebuild is an exact oracle; on a deployed narrative graph it finds a stamp-versus-evidence gap in 6.0% of 685 character-cuts (4.5% to 8.0%), of which 1.7% to 3.5% of character-cuts are genuine premature disclosures by two model annotators. Versioning facts by evidence horizon removes the divergence entirely and is safe, not correct; hiding exposed facts is worse than doing nothing; a pre-registered cue and a prefix-causal gate recover most of the price, with a failure map. For the second channel truncation is blind, and a renaming-controlled test with an unseen-text control and a cue-preserving pseudonym condition measures name-keyed premature naming: large for a reference model on famous books (+26.0 points [16.8, 36.0], exploratory), smaller for open models, not detected by a pre-registered run on obscure books (+0.1 [-5.0, +5.2]) where the closed-book control finds almost no memory, and tied to how well known the book is by a fame contrast that is suggestive and underpowered (+7.6 [-1.4, +18.3], p = 0.060). On a second, generic design, a whole-volume LLM character card, the same audit finds the reveal served early in 18.5% of events under names no model has seen, and the versioned card reduces it to 1.2%. Suffix canaries confirm this on every event without a judge (22.8% against 0) and show that telling a long-context model where the reader is does not keep it there (40.6%). A selection leak spoils with no later text in the input at all (19.4% against 1.4%). On the deployed graph a counterfactual suffix finds twice as much dependence as truncation finds divergence. So the audit itself has to be chosen by leak kind: no single test certifies the contract. The two channels compose, and passing one audit does not certify the other. What the evidence supports is a method and a measurement on one system, with the limits above and no human labels; what it invites is a second system, a human-checked label set and a repair for Channel 1 that does better than withholding.

---

## Appendix A. Where each number comes from

| Number or claim | Source |
|---|---|
| All Channel 2 numbers | `docs/research/PREFIX_FAITHFULNESS/REPORT.md` (section numbers in brackets in this paper); results in `data/eval/prefix_audit/` |
| Propositions P1 to P8 | `docs/research/PREFIX_FAITHFULNESS/FORMAL.md`; `packages/pipeline/tests/test_prefix_faithfulness_algebra.py` |
| Pre-registrations | `docs/research/PREFIX_FAITHFULNESS/PREREG*.md`, each written before the run it governs, with dated addenda |
| Channel 1 method and exploratory numbers | `docs/research/NOVELTY_REPORT/NOVELTY_REPORT.md` Sections 3, 4, 5.14 to 5.22 |
| Channel 1 confirmatory numbers | `data/eval/chimera/confirm/{main,e2}/analysis.json`, `olmo_corpus_check.json`; pre-registrations `docs/research/preregistrations/PREREG_PD_CONFIRM_v2_L40S.md`, addenda 1 to 5 and `PD_CONFIRM_deviations.md`; tables by `scripts/chimera/gen_ch1_tables.py` |
| Channel 1 summary table | `docs/research/NOVELTY_REPORT/NOVELTY_ONE_PAGER.md` |
| Paid spend (Channel 2) | `gpt-5.6-luna`, $0.1140 in total ($0.0524 strict labelling, $0.0006 smoke test, $0.0325 permissive re-read, $0.0285 English-original labels); everything else CPU or local GPU at $0 |
| Second system (Section 7) | `data/eval/chimera/rf_e2e/` (cards, judge labels, analysis.json); `scripts/chimera/pd_rf_e2e.py`; `PREREG_RF_E2E_addendum_6.md`, `PREREG_RF_E2E_addendum_7_fix.md` and their manifests; local models, $0 |
| Counterfactual suffix (Section 5.4) | `data/eval/prefix_audit/counterfactual_suffix.json`; `scripts/prefix_audit/counterfactual_suffix.py`; `docs/research/PREFIX_FAITHFULNESS/PREREG_COUNTERFACTUAL.md`; CPU, $0 |
| Suffix canaries and selection leak (Sections 7.9, 7.10) | `data/eval/chimera/rf_e2e/canary_*.json`, `canary_analysis.json`, `posthoc_canary_judge.json`, `selection_*.json`, `selection_analysis.json`; `scripts/chimera/rf_canary.py`, `rf_canary_posthoc.py`, `rf_selection.py`; `PREREG_RF_E2E_addendum_12_suffix_canaries.md`, `PREREG_RF_E2E_addendum_13_selection_leak.md` and their manifests; local models, $0 |
| Propositions P9 to P11 and the read-set check | `FORMAL.md`; `test_reader_faithfulness_canaries.py`, `test_prefix_faithfulness_readset.py` |
| Channel 1 spend | `docs/research/NOVELTY_REPORT/SPEND_LEDGER.md` RunPod L40S pod estimated at 3.9 (as of 19:11 IST; the pod was still billing) USD by uptime at 1.13 USD per hour (an estimate, not the billing page), plus 0.43 USD of earlier OpenAI use; Claude subscription calls are quota, not dollars |

## Appendix B. Status of placeholders

All Channel 1 result and repair placeholders were filled on 2026-10-16 from the stored results above. What remains for the owner: compare the spend estimate with the RunPod console, check the prior-art entries tagged LEAD (WhoDunIt's Gutenberg source, SurrealDB), complete the citations beyond those named, and run the 30-character human sheet for Channel 2 if a human check is wanted.
