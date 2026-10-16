# Pre-registration PD CONFIRM, version 2 (L40S edition): amendments to PREREG_PD_CONFIRM.md, frozen before any event is mined

Written 2026-10-16 (about 17:00 IST) on branch `chimera/system-adapters`, **before** the Gutenberg catalogue was filtered, before any candidate passage was read and before any confirmatory model call. It supersedes `PREREG_PD_CONFIRM.md` (version 1, never frozen) **only where stated here**; every hypothesis, estimator, margin, seed and rule not mentioned below is exactly as in version 1 and in `PD_CONFIRM_event_mining_rules_v1.md`. Its SHA-256 and those of the files it names are in `MANIFEST_PD_CONFIRM_v2.json`. A later change is a new version. Owner instruction at the time (verbatim): "I need a publication level completion by today any way possible"; the owner chose the hardware (one RunPod L40S 48 GB pod) and a RunPod budget of **15 USD in total**.

## 1. What changed and why
| Item | Version 1 | Version 2 | Reason |
|---|---|---|---|
| GPU | one 80 GB GPU | one L40S 48 GB, USD 1.13 per hour all-in (GPU 1.09 + disks 0.04) | owner's choice and budget |
| Budget | not fixed | **hard ceiling USD 14.00 for everything on RunPod, stop at 13.50**; about USD 2.00 already spent on exploratory runs (ledger) | owner: 15 USD in total |
| Evaluated open models | Llama-3.3-70B AWQ, Qwen2.5-72B AWQ, OLMo-2-32B | **`Qwen/Qwen2.5-32B-Instruct-AWQ` (served `qwen32b`), `allenai/OLMo-2-0325-32B-Instruct` fp8 (`olmo32b`), `mistralai/Mistral-Small-3.2-24B-Instruct-2506` fp8 (`mistral24`)** | 70B models do not fit 48 GB |
| Closed model | Claude Sonnet 5.5 via subscription, E1 and M2 only | unchanged (owner approved the "cloud arm"; terms of use for bulk subscription calls **unverified**, scope capped at the test split, throttling stops the arm) | |
| Families | Meta, Alibaba, AI2, Anthropic | Alibaba, AI2, Mistral, Anthropic (four) | |
| Core models for H1 ("at least 3 of 4 positive") | llama, qwen72, olmo, claude | **qwen32b, olmo32b, mistral24, claude** | |
| Miner | Llama-3.3-70B | **qwen32b**, temperature 0 | |
| Auditor | Qwen2.5-72B | **mistral24** (different family from the miner), temperature 0 | |
| Faithfulness judge (H6c) | Qwen72 or Llama70 | **mistral24 for qwen32b and olmo32b outputs, qwen32b for mistral24 outputs** | |
| Context | 8,192 tokens | qwen32b and mistral24 8,192, olmo32b 4,096 | memory |
| E5 prefix | last 24,000 characters | **last 10,000 characters** | fits olmo32b |
| E2 story author | Mistral-Small | **Claude Sonnet 5.5 (CLI)**, which is not evaluated on E2 (it is not in H4) | Mistral is now evaluated |
| Fame variable W | Wikipedia editions via API | **Wikidata `wikibase:sitelinks` count (all sitelinks, including sister projects) of the item carrying property P2034 (Project Gutenberg id)**, one SPARQL query saved with its date in `data/raw/pd_confirm/`; books without an item W = 0; bands high W >= 20, mid 3 <= W < 20, low W < 3 | one query for all books; deviation stated |
| Serving | one model at a time, manual swap | a small router on the pod (port 8000) starts the requested model on demand; same models, same vLLM, same decoding | removes manual swaps |

## 2. Calls and decoding (unchanged unless stated)
Temperature 0, seed 20261016, guided JSON schema whose enum is the candidate letters plus UNDETERMINED (the exploratory v2 to v7 runs on the same pod used the identical decoding). Open-name arms use the JSON `{"answer": X}` without an enum, `max_tokens` 48. E5 `max_tokens` 450. Failures retried 3 times then recorded missing.

## 3. Priority and shrink rule (fixed now)
Time is limited (submission the same day), so the work is staged and **each stage is reported whether or not the next one is reached**:
1. **E1 + M2 + H1, H2, H3** on all events and the three open models plus Claude. This is the primary result.
2. **E4 (H5)** on the test split with the three open models.
3. **E5 (H6)** on at most 60 test events (a seeded subset) if time allows.
4. **E2 (H4)** only if at least 40 stories verify; dropped first if short.
Event target 150 (acceptable 100 to 200). If fewer than 100 events verify within the mining limit (every one of the 120 drawn books processed, or 2 hours of mining), the shortfall is reported and nothing is padded. Stages not reached are reported as **not run**, never as passed.

## 4. Honest expectations written before the data
Exploratory runs on the same pod (v2, v3, v6, v7; 38 events) show gaps (original minus renamed) of +16.3, +4.7, about 0 (Qwen), +7.4, +11.5, about 0 (OLMo), +34.4, +20.8, +11.1 and +2.8 (Mistral) on famous then obscure sets. H1's +10 threshold on the pooled open models may therefore fail if the new books are mostly obscure; that is a result, to be reported as such. H3 (fame dose-response) is the hypothesis most likely to hold.

## 5. Provenance
The oracle is text-derived. Events are mined by qwen32b and audited by mistral24, **both of which are also evaluated** (stated limit). **No human verification of events exists; none is claimed.** Every number carries the label "text-derived, model-selected".

## 6. Files
`PREREG_PD_CONFIRM.md`, `PD_CONFIRM_event_mining_rules_v1.md`, `PD_CONFIRM_excluded_books.json`, `PD_confirm_prompts_v1.json`, `PD_prompts_v1.json`, `PD_prompts_v2.json`, `PD_prompts_v4.json` (all hashed in `MANIFEST_PD_CONFIRM.json`), and this file. Frozen before any test-split model call: `PD_confirm_events_v1.json` (CP-L).
