# Pre-registration PD: a text-derived disclosure benchmark on famous public-domain novels (version 1)

Written and frozen **before the benchmark builder exists and before any model sees any item**. Repo working tree on branch `chimera/system-adapters`, 2026-10-16. Hashes in `MANIFEST_PD.json`. L1, L2U and M2Q results are unchanged.

**Why this exists (owner decision, 2026-10-16).** The real-serial pilot cannot test memory-driven leakage: its labels are model-drafted (so they may share a memory with the resolver), it has 4 primary items, and the closed-book probe has no positive control (the serials are not demonstrably memorised). This benchmark replaces those weaknesses with: a **reveal oracle derived from the text itself** (an explicit verbatim reveal sentence located by exact search), **famous public-domain novels** (so memory is present and a closed-book positive control is meaningful), many items, and **several model families**. Field note: this corpus is outside the web-serial scope of plan section 15; the owner approved it as a **validation corpus for the metric**, not a product corpus.

**Label provenance (every number).** Labels are **text-derived**: the identity truth is the book's own explicit sentence; the cutoff is a position in the text; the chapter or paragraph anchors are regex-located. The *selection* of which events, reveal sentences and cast lists to use was made by the model-drafter (me) and is **not yet verified by the owner**; each reveal sentence can be checked by exact search in minutes (`PD_events_v1.json`). Nothing is silver-by-model-judgement and nothing is human-verified. Reader-warranted identity is **UNDETERMINED** before the cutoff by the **conservative-cutoff convention** (the cutoff is the start of the chapter or a fixed distance before the reveal sentence), under which the prefix never contains the explicit reveal; a careful reader may still *infer* an identity earlier from hints, which is why the leakage contrast (original names vs renamed names) is the measurement of interest and not raw accuracy.

## 1. Items (built by `scripts/chimera/pd_reveal_benchmark.py build`, rules fixed now)

- **Events:** the seven in `PD_events_v1.json` (frozen, hash in the manifest). Texts: Project Gutenberg plain-text files, boilerplate stripped by the `*** START` and `*** END` markers.
- **Pre-reveal alias items:** every occurrence of an alias surface strictly before the cutoff; if an event has more than 8, the 8 at evenly spaced ranks. Correct answer for a reader: **UNDETERMINED**. **Premature resolution** = the model answers the letter of the revealed identity.
- **Post-reveal alias items:** up to 2 occurrences after the reveal sentence (evenly spaced), window may include the reveal; truth = the revealed identity.
- **Plain controls:** 3 mentions per event of a non-identity cast name before the cutoff (evenly spaced ranks); truth = that name.
- **Window:** the last 1,200 characters of text ending at the end of the mention's sentence, mention marked `[[ ]]`; always prefix-only.
- **Candidates:** the event's cast list (7 to 9 names) in a seeded shuffle (seed 20261017 plus item index), the same list and order in every arm and model, plus the letter `UNDETERMINED` offered in the prompt.
- **Distance** = characters between the mention's sentence end and the cutoff, reported in bins (under 2,000; 2,000 to 20,000; over 20,000).

## 2. Arms and models

- **A** original names; **B** all proper nouns renamed under the **T4 v5 class-protected letter cipher** (same code, seed 20261015), built per book from that book's own capitalised tokens that never occur in lower case; renaming applies to window, mention surface and candidate names. **C_orig / C_ren** closed book: alias plus candidate list only, per event (not per item).
- **Models (local, free, temperature 0, seed 20261016, GPU only, no CPU offload):** `qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct`, `gemma2:9b`, `phi4-mini`. **Paid, within the owner's cumulative cap ($0.10, $0.0471 already spent):** `gpt-5.6-luna`, guarded at $0.04. A model that cannot be run is reported as not run. Each cell is run once.
- **Synthetic unseen-text control, per model:** the 62 L2U items and prompts (arms A and B, T4 v5 cipher), measuring renaming damage where memory is impossible; the premature measure there is "names the revealed identity" for pre-reveal alias items.

## 3. Metrics and decision rules (fixed now)

- **R0 renaming validity, per model:** A and B give the same letter on at least **95%** of the plain controls (and report post-reveal items too). A model that fails R0 is excluded from pooled leakage statistics and reported separately.
- **Premature rate per arm:** share of pre-reveal alias items answered with the revealed identity's letter, Wilson 95%. **Gap** = rate(A) minus rate(B), exact two-sided sign test on discordant items and a bootstrap interval (10,000 resamples, seed 20261016).
- **Synthetic gap** per model from the L2U items; **difference-in-differences** `D = gap_real - gap_synthetic` with independent bootstrap resampling of the two item sets.
- **Positive control (closed book):** per model, `memory_present` if C_orig names the revealed identity for at least **3 of the 7 events** (chance is about 1 in 9; 3 of 7 has exact one-sided probability below 0.04); C_ren is reported beside it.
- **Pooled primary statistic:** among models passing R0, the premature-rate gap pooled over (model, item) pairs with a bootstrap that resamples items (all models for a resampled item together).
- **Leakage-supported (all must hold):** (i) pooled gap at least **+10 percentage points** with the 95% interval above 0; (ii) pooled difference-in-differences above 0 with the 95% interval excluding 0; (iii) `memory_present` for at least **3** models passing R0. **Partially supported:** (i) holds but (ii) or (iii) does not. **Not supported:** (i) fails. Each outcome is reported as it falls; no model, item, prompt or threshold changes after the first model call.
- **Secondary (descriptive):** premature rate and gap by distance bin; abstention rate (UNDETERMINED) per arm and model; post-reveal accuracy (does the model name the identity once the text discloses it); plain-control accuracy; always-most-frequent-candidate baseline (the candidate with the most mentions in the prefix).

## 4. Limits stated before the run

Event and cast selection is mine and unverified by the owner; one conservative-cutoff convention; hints before the explicit sentence may let a careful reader infer early (the leakage contrast, not raw accuracy, is the target); 7 events from 7 books by 5 authors (Western canon, English, public domain, not web serials); candidate lists anchor; small-model abstention may dominate; closed book depends on the alias alone. A result here is about **LLM behaviour on famous novels**, not about the EchoTales pipeline or web serials.

## 5. Safety

No novel text is written to the repository (items are offsets and hashes; text is read from a local Gutenberg copy in the scratchpad at run time). No API key is read or printed; the paid run needs an explicit budget argument and stops before any call that could exceed it.

## 6. Deviations log

None at freeze.
