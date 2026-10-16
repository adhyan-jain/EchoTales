# Pre-registration PD v5: cue-preserving rename arm B3 (version 1)

Written and frozen **before any B3 call**. Branch `chimera/system-adapters`, 2026-10-16. Hashes in `MANIFEST_PD_v5.json`. Nothing in PD v1 to v4 is changed.

**Why v5.** An external adversarial review of the PD leakage claims (report section 5.19) named name-borne cue loss as the main open risk: the letter cipher turns names into gibberish, destroying gender and name-type cues, so the gap A minus B could measure lost cues rather than memorised knowledge. v5 adds one arm, **B3**, that keeps those cues and removes only the specific names. If cue loss explained the gap, B3 would restore the premature rates of the original text; if memory explains it, B3 stays near the cipher arms.

**New data and old data.** The B3 answers are new. The items, windows, candidate lists, letters, and the stored answers for arms A, B and B2 are the PD v2 and PD v3 runs (same 533 items; the item ids, kinds, events and distances were rebuilt from re-downloaded Gutenberg texts and match the stored runs exactly, 0 mismatches). Labels: text-derived oracle; events model-selected and not owner-verified; no human labels.

## 1. The B3 arm

- **Pseudonyms.** For every book, the cast and alias NAME tokens of its events (capitalised, at least 3 letters, not an honorific, and never occurring in lower case in the book) are replaced by natural pseudonyms from fixed pools (male first names, female first names, neutral first names, surnames), seeded per book (seed 20261018 plus the Gutenberg id), skipping any pseudonym that already occurs in the book. **Gender** of a token is inferred from the pronouns that follow its occurrences in the book (male if at least 3 male pronouns and at least twice the female count; female symmetrically; otherwise unknown); alias tokens take the gender of the event's revealed identity. **Name type** is first name for the first token of a multi-token cast name (or a single-token name of known gender) and surname otherwise; alias tokens with a leading honorific are surnames. Unknown-gender first names draw from the neutral pool.
- **Everything else.** All other proper nouns keep the v2 cipher (seed 20261015), so places and bystanders stay memory-free; honorifics, pronouns and all non-name words are untouched; the candidate list and the expression of interest are renamed with the same mapping; the answer letters and the prompt (with the v2 JSON-answer instruction) are as in v2 and v3.
- **Items.** All 533 items of v2 and v3 (231 pre-reveal, 54 post-reveal, 248 plain controls), one B3 call each. Models: the five local models of v2 (`qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct`, `phi4-mini`, `gemma2:9b`; ollama schema-constrained JSON, temperature 0, seed 20261016, GPU only, no CPU offload); `gpt-5.6-luna` only after an exact cost estimate is approved by the owner. Each cell once.

## 2. Decision rules (fixed now)

- **Pools.** Primary: the memory-free-gate pool (G2: B-versus-B2 agreement on real plain controls at least 90% and A-versus-B agreement on unseen synthetic items at least 80%, per dataset, as in PD v4). Secondary: every model.
- **Statistics (event-cluster; the resampling unit is the event, 5,000 resamples, seed 20261018).** gap A-B = premature rate in A minus the mean of B and B2; gap A-B3 = premature rate in A minus B3; **recovered fraction R = (rate B3 minus rate B) / (rate A minus rate B)**, the share of the original gap that restoring name cues brings back.
- **Verdict (primary pool).** **MEMORY SURVIVES (strong):** gap A-B3 at least +10 points with the event-cluster 95% interval above 0, and R below 1/3. **MEMORY SURVIVES (partial):** the same gap condition and R from 1/3 to 2/3. **CUE-DOMINANT:** R above 2/3. **INCONCLUSIVE:** anything else (for example the gap A-B3 interval includes 0 with R below 2/3).
- **Secondary (descriptive).** Per-model, per-dataset values of the same quantities; plain-control accuracy in arms A, B and B3 (if B3 raises control accuracy toward A, cue loss damaged comprehension on controls); invalid-answer counts; events where A exceeds B3 versus the reverse.

## 3. Limits stated before the run

Gender and name type are heuristic (pronoun counts and position in the name); only cast and alias names are pseudonymised by name, so other characters keep the cipher; pseudonyms are English-style and so change nationality cues of foreign names; a pseudonym can evoke some other book; plot details, setting and phrasing still carry memory, so B3 removes name-keyed memory only; the G2-valid pool is four local models; events are model-selected and not owner-verified; one run per cell; B3 was designed after the PD v2 to v4 results and the adversarial review, so it is a pre-registered test, not blind to those results; a result concerns LLM behaviour on public-domain novels, not EchoTales or web serials.

## 4. Safety and deviations

No novel text is written to the repository (texts live in the git-ignored `data/raw/pd_gutenberg/`); no key is read and no paid call is made by the local runs. Deviations log: none at freeze.
