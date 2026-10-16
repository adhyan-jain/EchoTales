# Pre-registration T3: memorisation probe (DRAFT, NOT FROZEN)

**Status: draft v0. Not frozen. Nothing in this file may run until the owner confirms the model and tag (authorisation A4) and the file is frozen as v1 with its SHA-256 in `MANIFEST.json`.** The two blanks below are the only things that change at freezing.

- Model and tag: **TO BE CONFIRMED BY THE OWNER**. Installed on this host (ollama, read-only listing at 2026-10-15): `qwen2.5:7b` (the repo's default), `qwen3:8b`, `llama3.1:8b`, `mistral:7b`, `mistral:7b-instruct`, `gemma2:9b`, `gemma3:12b`, `phi4-mini:latest`. Recommendation: **`qwen2.5:7b`**, because it is the project's own local model and the repo notes it is trained on Chinese web-novel content, which is where leakage would come from. Note `gemma3:12b` may not fit 8 GB without offloading, and the owner's rule is no CPU offload to RAM.
- Max wall-clock per run: **TO BE CONFIRMED** (estimate below).

## 1. Question

Does a local model, with **no passage** in the prompt, identify who a pre-reveal mention "really" refers to more often than chance and more often than a structural prior? If not, there is no memorisation signal **for that model configuration**, and candidate C1's leakage premise is not supported for it.

**Scope limit (required):** a 7B-class local model that shows no signal kills C1 **for that model configuration only**, not for larger models. Whether to test a larger model is an owner decision (A4 permits local GPU only; A5 forbids paid APIs).

## 2. Items

- The 72 pilot items (`data/eval/human_review_chimera_pilot.csv`). Scoring sets, fixed now:
  - **Primary: pre-reveal items by the owner's labels** = items where `reader_warranted != omniscient_id` and `reveal_chapter > chapter`, scored against `omniscient_id`.
  - **Secondary: tier P** (the 23 pre-reveal candidates chosen before labelling), scored against `omniscient_id`.
  - **Descriptive:** all 72.
- Model outputs can be collected **before** labels exist (the prompt contains no label); scoring waits for labels. The prompts and the candidate lists are fixed by the sheet, so collecting early does not let the labels influence the run.
- The model sees no passage, no chapter text, and no machine suggestion.

## 3. Conditions

| Cond | Prompt content | Purpose |
|---|---|---|
| a | the real novel title, chapter number, the mention surface, and the **candidate names** from the sheet | memorisation test |
| b | the same, with the title replaced by "a web novel" and every name (mention surface, candidates) replaced by pi (the T4 renaming, applied to names only, no passage exists to rename) | **renamed control**: any accuracy left in (b) is structure, not memory |
| c | **synthetic-story control**: an invented novel title, 72 items with the same candidate counts and the same position of the true answer as in (a), invented names, same template | measures the structural prior (list position, name length, salience) rather than assuming it |

## 4. Prompts (fixed; text hashed at freezing)

Three phrasings, each used in each condition; temperature 0, seed 0, `num_predict` small, no system prompt, answer letter only. Template A:

> Question about the web novel "{TITLE}". Around chapter {CHAPTER}, a character is referred to as "{SURFACE}". Who is this character really (the person the story eventually reveals them to be)? Options: {OPTIONS}. Answer with the letter only.

Template B: "In "{TITLE}", at about chapter {CHAPTER}, the text mentions "{SURFACE}". Which option is that mention truly about? {OPTIONS} Reply with one letter."

Template C: "{TITLE}, chapter {CHAPTER}: "{SURFACE}". Identify the real identity. {OPTIONS} Letter only."

(Final text and its SHA-256 are written into the freeze manifest.) Output parsing: first letter A-Z in the reply; no valid letter = wrong. Free-text answers are not scored as correct.

## 5. Baselines

- **Chance:** mean over items of 1/|options|.
- **Structural prior:** the accuracy the model gets in condition (c) on the synthetic items, plus the fixed rule "always the first option" on the real items. The stronger of chance and prior is the bar.

## 6. Metrics and intervals

Accuracy per condition and per phrasing; Wilson 95% intervals; paired exact (McNemar) test for (a) vs (b) on the same items, one-sided; the headline uses the **majority vote across the three phrasings** per item (ties wrong) and also reports each phrasing.

## 7. Decision rule (fixed now)

- **Signal for this model configuration:** the Wilson lower bound of condition (a) on the primary set exceeds max(chance, accuracy in (c)) **and** (a) beats (b) in the paired test at one-sided p < 0.05. Both conditions are required, so a model that merely guesses structurally does not count.
- **No signal for this configuration:** the lower bound does not exceed that bar, or (a) does not beat (b). This **kills C1 for this configuration**, not for others.
- **Inconclusive:** fewer than 10 primary items, or the interval straddles the bar.
- Pre-declared: a result in (a) alone, with (b) equal, is reported as "structure, not memory".

## 8. Power statement (exact Wilson bounds, 95%)

Minimum number correct for the lower bound to exceed the null accuracy p0:

| n primary items | p0 = 0.10 | p0 = 0.20 | p0 = 0.25 |
|---|---|---|---|
| 10 | 3 (30%) | 5 (50%) | 6 (60%) |
| 15 | 4 (27%) | 7 (47%) | 8 (53%) |
| 20 | 5 (25%) | 8 (40%) | 9 (45%) |
| 23 | 6 (26%) | 9 (39%) | 10 (43%) |
| 72 | 13 (18%) | 22 (31%) | 26 (36%) |

So with the roughly 20 pre-reveal items this pilot can supply, a signal is detectable only if the model gets about 40-45% right against a 20-25% bar, or about 25% against 10% chance. Subtler leakage cannot be seen. The number of primary items is **not known until the owner's labels return** and may be well below 20; if it is below 10 the test is inconclusive by rule.

## 9. Where and how it runs

Owner's GPU (RTX 4060 Laptop, 8 GB), through ollama, only after the model is confirmed. No CPU offload to RAM. About 72 items x 3 phrasings x 3 conditions = 648 short generations; at a few seconds each, roughly 10-30 minutes, to be measured on a 10-item smoke run and reported. VRAM must be checked free before loading (7.9 GiB free at 2026-10-15). Raw outputs are saved under `data/eval/chimera/`; no key is involved.

## 10. Deviations log

None (draft).
