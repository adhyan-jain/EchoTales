# A7 — cache-key ablation (isolating the state-derived part of the key)

**2026-09-26.**
- Script: `scripts/a7_cache_ablation.py`.
- Results: `data/eval/a7_cache_ablation_before_fix.json` (shipped key) and `data/eval/a7_cache_ablation.json` (after the fix below).
- Setup: canonical database copies; stub image engine and no LLM client, so prompts are deterministic and no GPU is used. 218 panels from chapters 1, 2, 166, 178 and 197.

## Why the earlier result was confounded

"Keys differ 10/10 across observers" could not isolate the state digest. Between observers the prompt changes too, and `plan_digest` itself hashes each drawn `persona_id` and the `state_digest` (`render/contract.py`).

## Design

**Key conditions**, computed from the *same* captured plan and request objects for every panel:

| | Condition |
|---|---|
| **A** | The key exactly as shipped (`render/cache_key.py`). The harness asserts it reproduces the renderer's own key on every panel. |
| **B** | A, with `state_digest` removed from the key **and** from `plan_digest`. Prompt, plan shape, seed and config are unchanged. |
| **C** | B, plus persona ids removed from `plan_digest`. Nothing state-derived is left except what reaches the prompt. |

**Events.** Each is applied to a fresh database copy and compared with a baseline render pass:

| Event | What changes |
|---|---|
| E0 | Replay, no change |
| E1 | Cast persona hair colour |
| E1b | Cast persona attire |
| E2 | Off-cast persona appearance |
| E3 | New concurrent body for a cast member |
| E4 | Observer switch (reader → a witness) |
| E5 | Alias-only change |
| E6 | Cast Self attribute |

A second pass freezes each panel's prompt at its baseline value; it gave identical numbers here, because no persona edit reached the prompt.

**Ground truth, computed independently of any key:**
- **State-stale** (pre-registered): for any cast member, the `state_of` persona ids, Self attributes, or drawn-persona attributes changed.
- **Drawn-stale** (added after the first run showed state-stale over-counts): only what can reach the generator changed, i.e. the drawn persona or its attributes.

Both are reported.

## Result 1 — the shipped key served stale images (defect found)

Shipped key, drawn-stale truth:

| Event | Drawn-stale panels | Prompt changed | A stale reuses | B stale reuses | C stale reuses |
|---|---:|---:|---:|---:|---:|
| E1 hair colour | 23 | 0 | **23** | 23 | 23 |
| E1b attire | 23 | 0 | **23** | 23 | 23 |

- `state_of` on a Self returns only Self-targeted attributes, while every appearance attribute in the corpus is Persona-targeted. The appearance change therefore reached neither the digest nor the prompt.
- It reaches pixels through the persona's reference sheet, and the key hashes reference *paths*, not bytes (a documented limitation).
- **Fix** (`render/plan_builder.py`): the drawn persona's standing attributes are now hashed into `state_digest`.
- Regression tests: `test_readset_invalidation.py::test_an_appearance_change_on_the_drawn_persona_invalidates` and `…_offstage_persona_does_not`.

## Result 2 — after the fix, the digest is necessary and isolated

Fixed key; counts per condition over 218 panels.

**Drawn-stale truth:**

| Event | Stale | A: stale reuse / unnecessary regen | B | C |
|---|---:|---|---|---|
| E0 replay | 0 | 0 / 0 (218 reused) | 0 / 0 | 0 / 0 |
| E1 hair colour | 23 | **0 / 0** (23 regenerated) | **23 / 0** | **23 / 0** |
| E1b attire | 23 | **0 / 0** | **23 / 0** | **23 / 0** |
| E2 off-cast change | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| E3 new concurrent body | 0 | 0 / **137** | 0 / 0 | 0 / 0 |
| E5 alias only | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| E6 Self attribute | 0 | 0 / **137** | 0 / 0 | 0 / 0 |
| E4 observer switch | 188 | 0 / 0 | 0 / 0 | 0 / 0 |

**State-stale truth** (pre-registered): A is exact on every event. B and C additionally reuse stale artifacts on E3 and E6, 137 each.

## Reading it honestly

1. **The controlled isolation survived.** With prompt, plan shape, seed and config identical, removing the state digest (B, C) serves **46 stale artifacts** (E1 + E1b) that the full key (A) correctly regenerates. This holds only after the fix: before it, all three conditions served them stale.
2. **The digest over-invalidates.** A regenerates **274** panels whose generator inputs did not change: a new concurrent body that is not drawn (E3), and a non-visual Self attribute (E6). This follows from hashing all bound persona ids and Self attributes, a deliberate auditability choice. At the one recorded NoobAI timing (22 s/panel on the local RTX 4060), that is about **1.7 GPU-hours of avoidable re-rendering**. This is an **estimate, not a measurement**.
3. **Observer separation does not need the digest.** For the observer switch (E4), 182 of 188 changed panels also changed prompt, and all conditions separate them (406 unique keys in each). The digest adds nothing there on this corpus, so the earlier "keys differ 10/10" result was driven by prompt and plan differences, not the digest.
4. **Reuse works when nothing relevant changes.** E0, E2 and E5 reuse all 218 panels under every condition. At the same 22 s/panel estimate, a replay avoids about 80 GPU-minutes. That is a property of caching in general, not of the state digest.
5. **Aliases are still not in the key** (E5: 137 name changes, 0 regenerations). Whether a name change should re-render an image is a policy question; it is documented, not changed.
6. **Not measured:**
   - GPU time: the stub engine generates nothing.
   - Stub wall-clock: 155–245 s per 218-panel pass, dominated by planning and state queries, identical across conditions, so it is not informative about generation cost.
   - The effect of the reference-image *bytes*: sheets were not regenerated here.

**Technical effect, stated plainly:** the state-derived digest is what makes an appearance change produce a new cache identity when the prompt does not change. That is a correctness effect (no stale identity served). It is not a computational saving; the digest as designed costs extra re-rendering.
