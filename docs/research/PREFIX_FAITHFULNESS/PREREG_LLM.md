# Pre-registration: prefix-faithfulness of the LLM trait path

Written 2026-10-16, **before the model backend has been run**; the only thing run so far is a plumbing dry-run with a fake client that returns answers hashed from the prompt (it measures nothing about a model and is labelled so in its output). Status: **NOT RUN, waiting on a free GPU and the owner's go-ahead.** Label provenance: SYSTEM-INTERNAL (no labels). Same fixed-resolution design as `PREREG.md` Amendment 1.

## Why this audit

`PREREG.md` covers the deterministic trait path. In `persona/build.py` a character with at least `LLM_MENTION_FLOOR = 25` mentions gets an additional model read (`persona/extract.py::extract_traits`), which stamps its traits the same way (first sighting). Two stages (`appearance_extract`, `world/extract`) are LLM-only and use a different rule (`attesting_chapter`); they are the unmeasured rows of REPORT 4.7. This audit measures the model path of the persona stage, and gives a second derivation mechanism for the claim, which is the main weakness of the deterministic result (one system, one derivation).

## What the model sees (read from the code)

`build_prompt` passes at most 12 spoken lines and 6 narration samples, taken from the **earliest** attested chapters (the evidence list is built in reading order and truncated). So the model's read set is smaller and earlier than the deterministic stage's (up to 24 narration samples). Prediction: model-path divergence from later chapters is **smaller** than the deterministic 8.0%, unless the gate or nondeterminism dominates.

## Three causes of a difference between a full build and a prefix build, kept apart

1. **Gate-induced.** The decision to call the model uses the whole-volume mention count (`mention_count >= 25`). At cut k a character with 10 mentions so far gets only the deterministic read in the prefix build but a model read in the full build. This is itself a prefix-causality violation, by design, and is reported as its own class.
2. **Content-induced.** Both builds call the model, but the evidence lists differ because later chapters changed the first-12/first-6 selection, or the deterministic base profile fed to the model differs.
3. **Noise.** The same prompt can return a different answer (GPU nondeterminism, even at temperature 0). Estimated by building each prefix twice and comparing the two prefix builds.

## Hypotheses and falsifiers (declared now)

- **L1 (the model path is also not prefix-causal).** Among (character, cut) pairs where **both** builds used the model, the discrete traits (`gender`, `age_band`, `register`; exact match) differ in more than the noise floor. Falsifier: the full-versus-prefix difference rate does not exceed the repeat-versus-repeat rate (paired difference with a bootstrap 95% interval over characters that includes 0).
- **L2 (the gate is a separate, measurable source).** The share of (character, cut) pairs whose provenance differs (`llm` in one build, `deterministic` in the other). Reported, not thresholded. I expect it to dominate at early cuts (1 to 5 characters per serial cross the gate at cuts 5 to 10).
- **L3 (the repair transfers).** Not tested here: `build_personas(prefix_causal=True)` refuses a model client. A model-path repair would need a per-prefix call and is out of scope until L1 is measured.

`big_five` is compared as continuous values: a pair differs if any of the five components moves by more than 0.10 (declared now; an arbitrary but fixed threshold, and the result is also reported at 0.05 and 0.20 so the choice cannot decide the verdict).

## Design and budget

- Cuts: the same 13 as `PREREG.md` (LOTM 5/10/20/30, ORV 5/10/20/30, RI 10/20/40/80/120), stored mention assignment held fixed.
- Per serial: one full build with the model, one prefix build per cut with the model, and a second prefix build per cut for the noise floor.
- Calls: **218 for one pass** over the three full volumes and the 13 cuts (77 full + 141 cuts), **359 with the noise-floor repeats**, counted by the dry-run (Addendum 1). My first estimate (164, from entity counts above the gate) was too low because body-change adjudication (`detect_body_changes`) goes through the same client. At a few seconds per call on a 7B model this is on the order of an hour.
- Model: the project's configured local backend (`config.json`), recorded in the output. Locally available at the time of writing: `qwen2.5:7b`, `qwen3:8b`, `mistral:7b-instruct`, `llama3.1:8b`, `gemma2:9b`, `gemma3:12b`, `phi4-mini`. The model that CLAUDE.md names (`qwen2.5:7b`) is the default choice. $0 API spend.
- Hard guard in the harness: it refuses to run the model backend unless `PREFIX_AUDIT_ALLOW_GPU=1` is set **and** the GPU is not already in use (memory used under 35% and no other `ollama runner`), encoding the owner's rule that heavy models run on a GPU checked free first. At the time of writing the GPU was at 6.5 of 8 GB with a runner that is not this session's, so the run was not started.

## Power, stated now

Few characters cross the gate early (LOTM k=5: 1; ORV k=5: 1; RI k=10: 2), so early-cut content-induced comparisons rest on 1 to 5 characters. The pooled both-model count is expected to be a few dozen (upper bound by the counts above). Effects below roughly 15 to 20 points will not be detectable. A null result will therefore be reported as "no evidence at this power", not as "the model path is causal".

## Addendum 1 (2026-10-16, after the fake-client dry-run, before any model run)

The dry-run with the prompt-hashing fake client, run on all three serials and 13 cuts, observed two things that do not need a model, and they change what the model run can still tell us:

- **Gate (L2), model-independent:** of 296 character-cut pairs, 145 are deterministic in both builds, 101 use the model in both, and **50 (16.9% of all pairs; 33% of pairs where the model is involved at all)** use the model in exactly one build. This depends only on mention counts.
- **Content (the core of L1), structurally zero where the gate passes:** in all 101 both-model pairs the prompt (label, first 12 spoken lines, first 6 narration samples) is identical in the full and prefix builds (fake-client outputs hashed from the prompt differ in 0 of 101 pairs; had any prompt differed, the chance of the fake returning equal discrete and extraversion answers is about 0.4%). A temperature-0 model given an identical prompt can only differ by noise. So the model run can no longer test "does later-chapter content change the model read" except through noise; it can still measure (a) the noise floor, and (b) how often the model value differs from the deterministic value for the 50 gate pairs.

Interpretation constraint, decided now: a gate pair is a difference in **which read was computed**, not necessarily a spoiler. The model reads early evidence; what the gate leaks is that the character later becomes prominent (the whole-volume count), not later story content. It is reported as gate-induced divergence and is not counted as a content leak.

## Addendum 2 (2026-10-16, before any model run): how the backend is pinned

Found while preparing the run, not from a run: in this worktree `get_settings()` resolves to the **stub** backend, because `.env` is gitignored and absent here (the main checkout's `.env` sets `ECHOTALES_LLM_MODE=local`, `qwen2.5:7b` on `localhost:11434`). The first version of `llm_audit.py --backend model` would therefore have passed `require_ready()` and measured the stub. The harness now refuses unless the client's backend is the local ollama one, and writes the resolved model per task into the output (`backend_name`). `config.json` names a gateway on `:11435` (`coding-best`); where it routes is unknown, so it is not used (the budget is $0 and the run is local). The run must be started with `ECHOTALES_LLM_MODE=local` and the local model settings given explicitly. Model run status: **RUN 2026-10-16** after the owner's explicit approval; results in `REPORT.md` 4.8a. Two further harness faults were found and fixed before any model call: `ECHOTALES_MODEL_BACKEND=ollama` also has to be set (not only `ECHOTALES_LLM_MODE`), and `require_ready()` demands `llama3:latest` for tasks this audit never calls, so readiness is now checked only for the two persona tasks. Actual calls: 348 (the dry-run predicted 359). My own model stays resident after a run and trips the GPU guard, so I unloaded it with `ollama stop` between serials and left the guard unchanged. Outcome against the declared rules: L1 not supported (0 of 101, noise floor 0); L2 reported (50 gate pairs, 37 differ).

## Addendum 3 (2026-10-16, written BEFORE the code and the run): a prefix-causal gate for the model path

Result of the real run (REPORT 4.8a): the model read itself is stable (0 of 101 both-model pairs differ, noise floor 0), but the whole-volume gate `mention_count >= 25` makes the full and the prefix build disagree on a discrete trait in 37 of 50 gate pairs. L3 (above) left the repair for later; the owner asked for more novelty to be farmed while away, so this tests the obvious repair.

**Change (declared).** `build_personas(..., prefix_causal=True, client=...)` stops refusing a client. In `_prefix_trait_revisions`, at each attested chapter `c` with `seen` = mentions up to `c`: if `seen >= llm_mention_floor`, refine that chapter's deterministic profile with `extract_traits` on the evidence of chapters at or before `c`; otherwise keep the deterministic profile. Model calls are memoised by prompt within a character (the prompt depends only on the label, the first 12 spoken lines and the first 6 narration samples, so it stops changing once that window fills). The default model read is skipped when `prefix_causal` is on. Default behaviour with `prefix_causal=False` is unchanged.

**Hypothesis L4.** On the same 13 cuts and three serials, with the real model (`qwen2.5:7b` via local ollama, temperature 0 as configured), the prefix-causal model path has (a) 0 gate-class pairs and 0 both-model divergences between the full build and a build over the prefix, and (b) a repeat-versus-repeat noise floor of 0, as in 4.8a. Falsified by any divergence in (a): that would mean the model is not stable under prompt-identical repeats, or the memoisation changes answers, and is reported as such.

**Also reported, not thresholded.** Model calls for the prefix-causal full build against the 218 of one non-causal pass; the share of (character, cut) pairs served by a model read (provenance `llm`) before and after, since the repair withholds a model read until the prefix itself has 25 mentions; and the number of characters whose served discrete traits at a cut differ between the old full build and the repaired one (the price of removing the gate effect).

**GPU rule.** The run is on the local GPU only after it has been checked free; the harness guard of `llm_audit.py` stays as it is and the model is unloaded between serials. Spend: $0 (local model), none of the extra $0.20.

**Outcome of Addendum 3 (2026-10-16).** L4 supported on the real model (`qwen2.5:7b`, local ollama, recorded in each output file): gate-class pairs 50 to 0 of 296; 0 divergences among the 101 both-model pairs; noise floor 0; `big_five` moves above 0.05 from 3 to 0; model calls 348 before and after. The run waited for quiet windows on a GPU shared with another session (`run_llm_when_free.py`); the first launch was refused by the guard because the other session had loaded `gemma2:9b`, and nothing of theirs was touched. Results: REPORT 4.15. Spend $0 (local).

## Scope limits declared now

- One local model family and size, one run of each build plus one repeat; results do not transfer to other models.
- No labels: nothing says which trait value is correct.
- The model's own memory of a famous novel is not separated from later-chapter evidence here (all three serials are translated web novels, where the other session's closed-book probe found little memory for another model, but this model is untested). A renaming control would be a follow-up.
- Greedy decoding at temperature 0 is assumed from `llm/tasks.py`; it is not verified per request.
