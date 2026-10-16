# Pre-registration T4: renaming validity (version 3)

Supersedes v2 (`PREREG_T4_renaming_validity_v2.md`, sha256 `2cec3c56e7aff87b93329cceea96ee831615778a762839d4ff06716e235f1784`). v1 and v2 stay unedited. Everything in v2 (and through it v1) applies unchanged except sections 1 and 2 below. Frozen (hash in `MANIFEST_v3.json`) **before any resolver run on the full novel exists**.

## 0. Deviation record

1. v2 added a pre-run commutation gate (G1 display-label commutation, G2 comparison-key class bijection, G3 token containment) and said violations are reported as a pi defect and fixed only in a new version.
2. The gate was run against the real vocabulary (335 distinct name surfaces) **before any resolver call**. Result: **FAILED**, G1 = 8 violations, G2 = 25, G3 = 0. Raw output: `data/eval/chimera/t4_results.json` (`status: GATE_FAILED_NO_RUN`). No O1/O2/I/R/N run was executed. No decision outcome has been seen.
3. The violations fall into three classes, read from the gate's own output (not from any resolver behaviour):
   - **Independently renamed inflections.** Surfaces such as "Gu Masters", "Moonblades", "Reinforcements", "Thunderwings", "Southern Borders" and "Blood Sea Inheritances" have a plural token that pi renamed independently of its singular, so `strip_morphology`'s plural folding (which makes "Moonblades" and "Moonblade" one key) no longer joins them. Same mechanism for "Fang Yuan" vs a pluralised "Yuans".
   - **Common words used as names.** "May", "Great Immortal", "Gu Master" appear both capitalised and lower-case ("may", "great immortal"); `comparison_key` casefolds them to one key, but pi renamed only the capitalised form.
   - **Lower-case variants of real names** ("fang Yuan"): same split.

## 1. Changes to pi (replaces v2 section 1 items 1-2's token rules; v2 items on exact length, class preservation and honorifics stay)

1. **Inflection closure.** If a vocabulary token `u = t + "s"` has `s_class(u)` true and `t` is also a vocabulary token, then `pi(u) = pi(t) + "s"` exactly, and `pi(t)` is generated with a final letter in `{a, e, n, o, r, l, k, m, t}` so that the plural stays in the strippable class. If `t` is protected (any rule below), `u` is protected too.
2. **Common lower-case words are never renamed.** Count, over all block text, the occurrences of each lower-cased vocabulary token as a **standalone token that itself starts with a lower-case letter**. If a token's lower-case form occurs **5 or more times** this way, the token is protected (not renamed). The threshold 5 is fixed now. This protects words such as "may", "great", "immortal", "master".
3. **Lower-case variants of renamed names are renamed too.** For a renamed capitalised token `T`, the all-lower-case token `T.lower()` maps to `pi(T).lower()`, **only** when `T.lower()` passed rule 2 (it is not a common lower-case word). All-upper-case and mixed-case variants are left unrenamed and counted.
4. Everything else is as in v2: exact length, same `s_class`, honorific/article protection, bijection, seed 20261015, protected title/role/kinship/blocklist/stop-word vocabularies, monotone offset map.

## 2. Gate and stop rule

- The v2 gate (G1, G2, G3) is applied unchanged **before any resolver run**.
- **This is the last planned revision.** If the gate fails again under v3, T4 is reported as **"token-level renaming cannot be made to commute with the repo's normalisers without further design; control not validated"** and a **v4 is written only if the owner asks for it**. No further revision is made by the assistant on its own. The reason is stated now so that gate-driven iteration cannot become open-ended tuning.
- If the gate passes, everything else (runs O1, O2, I, R, N; per-mention agreement by label under pi; decision rule PASS/FAIL/INCONCLUSIVE; power; scope) is exactly v2 section 4, with the classification of v2 section 3.

## 3. Consequence for T3 and C1 (recorded before the run)

Whatever T4 shows, the three defect classes above apply to **any** renaming control used for C1: an input-level renaming that does not preserve inflection, case-variant and common-word structure changes what the repo's normalisation sees. A renaming control for an LLM test (T3) acts on prompts rather than the resolver's normalisers, so these specific defects matter less there, but v3's rules are used for T3's name replacement too, so both controls use one function.

## 4. Deviations log

v2 -> v3: as section 0. No other deviation at freeze.
