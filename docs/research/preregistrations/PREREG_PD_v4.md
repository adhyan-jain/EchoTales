# Pre-registration PD v4: title-assisted memory probe (M2) and memory-free validity gate (G2), as a re-evaluation of PD v2 and v3 (version 1)

Written and frozen **before any M2 call**. Branch `chimera/system-adapters`, 2026-10-16. Hashes in `MANIFEST_PD_v4.json`. Nothing in PD v1, v2 or v3 is changed; their pre-registered verdicts stand (v2 INCONCLUSIVE at 95%; v3 PARTIALLY SUPPORTED, also with Luna in the pool).

**Why v4 (owner request, 2026-10-16: "then do those 2 things somehow").** v3 left two weaknesses: (1) condition (iii), memory in at least 3 valid models, failed because the alias-only closed-book probe under-detects memory (models name 2 to 3 of 12 events; the probe gives no title); (2) the A-versus-B validity gate is partly memory (plain-control disagreement is asymmetric toward the original-names arm), so loosening it mixes the gate with the effect.

**What is and is not new data.** M2 calls are **new data** (collected after this freeze). The v2 and v3 leakage items, runs and gaps are **already seen**; v4 re-evaluates them under rules fixed now, so the result is a pre-registered *re-evaluation*, not a new confirmation. Label provenance as before: text-derived oracle, model-drafter selection, not owner-verified, no human labels.

## 1. The two instruments

- **M2 (title-assisted closed-book probe).** For each of the 31 events (19 in v1 + v2, 12 in v3): the prompt in `PD_prompts_v4.json` gives the novel's title (the events files' `book` field), the expression used for the character (the first alias) and the cast list, with **no passage**, asking which candidate the expression refers to; JSON answer with ollama schema-constrained decoding (local) or parsed (Luna). Arms: M2_orig; M2_ren and M2_ren2, which rename the expression and the candidates with the two v2 ciphers (seeds 20261015 and 20261016) and **leave the title unchanged**. Candidate order seeded as 9500 plus the event index. Models: the five local models of v2 (`qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct`, `phi4-mini`, `gemma2:9b`); `gpt-5.6-luna` only if the owner approves an exact cost estimate. Each cell once; temperature 0, seed 20261016, GPU only, no CPU offload.
- **`memory_present` (per model, per event set).** M2_orig names the revealed identity for at least k of N events, with k the smallest value whose exact one-sided binomial probability under chance 1 in 8 is at most 0.05 (N = 19 gives 6, N = 12 gives 5, N = 31 gives 8). M2_ren and M2_ren2 are reported beside it; a probe that also names the identity under renaming is reported as not memory-specific.
- **G2 (memory-free validity gate).** A model is valid in a dataset if (a) its B-versus-B2 agreement on that dataset's real plain controls is at least **90%** (two ciphers, no original names, so memory cannot affect it; 90% is inside the owner's stated 88-95% range) **and** (b) its A-versus-B agreement on the unseen synthetic non-reveal items is at least **80%** (no real text, memory impossible).

## 2. Re-evaluation rules (fixed now)

For each of v2 (19 events) and v3 (12 events) separately: valid models by G2; pooled gap (A minus the mean of B and B2) over valid models with the item bootstrap used before (5,000 resamples, seed 20261016); pooled synthetic gap and difference-in-differences; `memory_present` by M2 on that dataset's own events among valid models. **SUPPORTED** needs (i) pooled gap at least +10 points with the 95% interval above 0, (ii) difference-in-differences above 0 with the interval above 0, (iii) M2 `memory_present` in at least 3 valid models. **PARTIALLY SUPPORTED:** (i) holds but not (ii) or (iii). **NOT SUPPORTED:** (i) fails. **INCONCLUSIVE:** fewer than 3 valid models. Secondary (descriptive): M2 counts per model and arm; Spearman correlation between an event's premature rate (original names, valid models) and the number of models naming its identity under M2.

## 3. Limits stated before the run

M2 gives the title, so it measures whether a model can map the alias to the cast given the book, not unprompted recall; the title can itself contain a cast name (for example Gatsby, Jane Eyre), which can make M2 easy for those books, and the renamed arms keep the title; the 90% and 80% bars are conventions chosen by the owner's range statement before M2 data but after seeing the v2 and v3 gap data; synthetic items are not fresh; the v2 and v3 events are model-selected and not owner-verified; local 7B to 9B models only unless Luna is approved; the result concerns LLM behaviour on public-domain novels, not EchoTales or web serials.

## 4. Safety and deviations

No novel text is written to the repository; no key is read and no paid call is made by the local runs. Deviations log: none at freeze.
