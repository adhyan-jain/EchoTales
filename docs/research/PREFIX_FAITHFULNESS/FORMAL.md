# Formal note: leak, loss and the exposure window

Companion to `REPORT.md`. Everything here is elementary; the point is to state the measured result as a checkable proposition, not to claim a deep theorem. Each proposition is checked on random inputs by `packages/pipeline/tests/test_prefix_faithfulness_algebra.py` (400 examples each, all passing, 2026-10-16). That test exercises a toy derivation; the real stage is covered by `test_persona_prefix_causal.py` and by the audit.

## Setting

A volume has chapters 1..n. A deterministic *derivation* `D` maps the evidence of a chapter prefix to a value in a set `V` containing a neutral element `u` ("unknown"). The **reference** at cut k is the value a build from chapters <= k holds: `r_k = D(x_1..x_k)`. A *policy* serves a value `s_k` at cut k. Its **divergence** is the number of cuts with `s_k != r_k`.

The **read set** `R(x)` of a derivation on input `x` is the set of chapters whose content it inspects. `R` is a **certificate** if every input `x'` that agrees with `x` on `R(x)` gives `D(x') = D(x)`. The **evidence horizon** is `H = max R(x_1..x_n)`.

## Policies

- **Status quo** (the persona stage before the repair): `s_k = r_n`, stamped at first sighting.
- **Hide-only** (the honest-stamp rule applied naively): `s_k = u` for `k < H`, `s_k = r_n` for `k >= H`.
- **Versioned** (the repair): `s_k = r_k`, one revision per value change, each stamped at the chapter it was computed from.

A divergence is a **leak** when the served value was computed from evidence after k (status quo: always), and a **loss** when it was produced by suppression (hide-only: `s_k = u != r_k`).

## Propositions

**P1 (soundness of the screen).** If `R` is a certificate, then `r_k = r_n` for every `k >= H`. Hence no policy that serves `r_n` diverges at or after `H`: all divergence lies in the exposure window `k < H`.
*Proof.* For `k >= H` the prefix `x_1..x_k` agrees with the full input on `R(x) subseteq [1, H]`, so `D` returns the same value. QED. *Consequence:* the screen's soundness is exactly the claim that the hand-derived read set is a certificate. That claim is the unverified assumption; the audit's "0 divergences outside a window" is a test of it, and it can only fail on dependencies the data realises (`big_five`'s whole-volume count was not realised on the real serials).

**P2 (status quo).** Divergence(status quo) = `#{k < H : r_k != r_n}`, all of it leaks, no losses. *Proof.* By P1, cuts `k >= H` agree; for `k < H`, `s_k = r_n`. QED.

**P3 (hide-only against the status quo).** Let `A = #{k < H : r_k = u}` and `B = #{k < H : r_k = r_n}`. Then
`divergence(hide-only) - divergence(status quo) = B - A`.
So hide-only beats doing nothing **iff fewer in-window prefixes already hold the final value (B) than hold the neutral value (A)**. It removes every leak and creates `#{k < H : r_k != u}` losses.
*Proof.* Divergence(hide-only) = `#{k < H : r_k != u} = (H-1) - A`; divergence(status quo) = `#{k < H : r_k != r_n} = (H-1) - B`. Subtract. QED.
*Reading of the measurement.* On the three serials hide-only diverges on 82 of 289 cuts and the status quo on 23, so `B - A = 59 > 0` for gender (pooled). The 139 exposed gender cuts decompose as: 80 where the prefix already held the final value (65 male, 15 female), 36 `unknown` in both, 21 `unknown` in the prefix and known in the full build (the leaks), and 2 where the prefix held `female` and the full build says `unknown`. Hide-only therefore fixes the 21 leaks and destroys the 80 settled values plus the 2 reversed ones. The reason is that the coarse horizon (up to 12 chapters of evidence) is later than the chapter in which the pronouns settled the value for most exposed characters; in 58% of exposed cuts the value was already final. The condition is a property of the data, not of the idea: on a corpus where values are typically settled only at the horizon, hide-only would win.

**P4 (versioning).** `s_k = r_k` has divergence 0 for every `D`. It is the unique policy with that property (divergence 0 forces `s_k = r_k` for all k). Its cost is the number of value changes of `D` along the prefixes (revisions written), not n rebuilds, when `D` is incrementally computable; the persona stage is, in the repair implemented in `_prefix_trait_revisions`.

**P5 (what hiding can and cannot buy).** Any policy that never serves a value computed from evidence beyond k (zero leaks) and serves `s_k != r_k` at some cut incurs a loss there; zero leaks plus zero losses forces `s_k = r_k`. So the leak/loss pair is a genuine trade-off for every policy that does not recompute from the prefix, and only the recomputing policy sits at (0, 0).

**P6 (the guarantee belongs to the policy, not to the extractor).** Let `D` be any derivation whose value on the prefix `x_{<=k}` is `r_k = D(x_{<=k})` and which reads only that prefix (same read-set rule at every `k`). The versioned policy `s_k = r_k` then has divergence 0 whatever `D` is: a lexical rule, a rule with a fallback cue, a deterministic model call. *Proof.* P4 used no property of `D` other than that `r_k` is a function of the prefix. QED. *Consequence.* Prefix-faithfulness and correctness are separate axes. The repaired build's correctness equals `D`'s correctness on prefixes, so its loss against the status quo is the set of cuts where `D(x_{<=k})` is weaker than `D(x_{<=H})` (REPORT 4.9: those are the "justified by text" values), and it can be reduced only by improving `D` on prefixes, at whatever error that costs `D`. *Measured instances:* the lexical rule (0 of 289 and 0 of 685), the rule with the anchored cue (0 on all six settings and 24 cuts; REPORT 4.11), the model call (0 of 101 both-model pairs; REPORT 4.15), the English originals (0 of 179; REPORT 4.14), and a synthetic volume (0 of 1,240 pairs in each of 9 configurations; REPORT 4.13).

**P7 (gates).** Let a derivation call an expensive reader `M` iff a predicate `g` of the evidence holds, and let `g` be non-decreasing in the prefix (mention counts are). If `g` is evaluated on the whole input the policy disagrees with the prefix build exactly on the *gate class* `G = {k : g(x_{<=k}) = false and g(x) = true}`, and on a pair outside `G` the two builds call the same reader on the same prompt (when `M` is a function of the prompt, no divergence). If `g` is evaluated on `x_{<=k}` then `G` is empty. *Proof.* Immediate from monotonicity and the definition. QED. *Measured instance:* 50 of 296 pairs in `G` with the whole-volume gate, 0 with the prefix gate, 0 divergences among the 101 pairs outside it (REPORT 4.8a and 4.15). Note that `G` is a leak of *prominence*, not of content: the reader `M` sees the same early evidence either way.

**P8 (a fallback cannot change what the base serves).** *Amended after REPORT 4.16: this holds only when `D` is the whole base extractor and the fallback is allowed to fill only an `unknown`. The implemented cue is applied when the paragraph rule alone is silent and then outranks the honorific table, so it can override an honorific-derived value; with window v2 it did so for one character at three cuts and produced three wrong values.* Let `D'(x) = D(x)` if `D(x) != unknown` and `F(x)` otherwise. Then every value `D` serves is unchanged by `D'`, the divergence of the versioned policy stays 0 (P6), and the only new errors are errors of `F` on inputs where `D` was silent. *Measured instance:* the anchored cue changed 0 of the values the plain repair already served and decided 35 (web novels) and 11 (English originals) values that the plain repair had withheld, with 34 and 8 correct (REPORT 4.11, 4.14). The precision of `F` is the whole question, and it is an empirical one (REPORT 4.13 maps it against the density of misleading cues).

## What is and is not claimed

- Claimed: the decomposition, P1-P5 as stated, and the measured instance (REPORT 4.1-4.6).
- Not claimed: that this is new mathematics. It is elementary, and the "max over inputs" horizon is the point-in-time correctness rule of ML feature stores (REPORT section 5). The contribution is that the trade-off is made explicit and measured on a deployed narrative graph, including the case where the textbook fix is worse than the defect.
- Open: whether the read set of the real stage is a certificate beyond the realised data (a property-based test over the real `infer_traits_deterministic`, not the toy, would tighten P1); and the continuous middle of the trade-off, where a policy hides only some exposed facts (for example those whose evidence is mixed), is not built.
