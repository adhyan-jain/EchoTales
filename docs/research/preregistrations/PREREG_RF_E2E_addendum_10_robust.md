# RF-E2E addendum 10: two robustness checks asked for by an external adversarial review (written 2026-10-16 21:58 IST, before any of these cells exists)

**Seen before writing:** all results of addenda 6 to 9 (five models, both rules, both judges) and an external LLM review that asked, among other things, whether an instruction not to spoil would fix the whole-volume card and whether the cipher control depends on one cipher.

**R1, don't-spoil baseline.** The whole-volume card W with the fixed prefix "Avoid spoilers: do not reveal secret identities, disguises or plot twists. " before the same card prompt, in both naming arms (cells W_orig_nospoil, W_ren_nospoil). **Reported:** leak(W_nospoil) against leak(W) and against leak(P) by rules A and B, pooled with event bootstrap. **Reading fixed now:** if leak(W_ren_nospoil) minus leak(P_ren) has a 95% lower limit above 0, prompting does not remove the input-channel leak and the versioned build is still needed; otherwise the instruction is reported as a cheaper partial or full mitigation.

**R2, second cipher.** The frozen second consistent cipher (`renamers_for(books)[gid][1]`, seed of arm B2) applied to W and P (cells W_ren2, P_ren2). **Reported:** the input channel W_ren2 minus P_ren2 by rules A and B beside the first cipher's value. **Reading fixed now:** the cipher result is called robust to the cipher if the second cipher's input channel has a 95% lower limit above 0.

**Models and time.** `qwen2.5:7b` first, then `llama3.1:8b` only if qwen has finished by 22:40 IST; local ollama, same options; judge `qwen3:8b` as in addendum 6. Anything not finished by 22:50 is reported "not run (time)". No verdict of addenda 6 to 9 changes.
