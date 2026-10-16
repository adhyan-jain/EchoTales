# RF-E2E addendum 11: earlier reader positions and a second card prompt (written 2026-10-16 22:24 IST, before any of these cells exists)

**Seen before writing:** all results of addenda 6 to 10 and the post hoc judge check. The external review asked whether the result holds at other reader positions and with another prompt.

**Positions.** The versioned card is rebuilt for a reader at two earlier positions: the end of the sentence of the alias mention at 50% and at 75% of the event's pre-cut alias mentions (cells P_ren_pos50, P_ren_pos75; cipher names). The whole-volume card is built once and served from the first mention, so its leak at these positions is the W_ren value already measured. **Reported:** leak of the versioned card at each position against the whole-volume card, rules A and B.

**Second prompt.** "Describe who the character called {ALIAS} is in this story, in at most 80 words, using only these passages. Passages:\n{PASSAGES}\nDescription:" for W and P on cipher names (cells W_ren_p2, P_ren_p2). **Reading fixed now:** the result is called robust to the prompt if W_ren_p2 minus P_ren_p2 has a 95% event-bootstrap lower limit above 0 on rule A or rule B (both reported).

**Model and time.** `qwen2.5:7b` on the local GPU, judge `qwen3:8b`, same options; anything not finished by 22:50 IST is reported "not run (time)". No earlier verdict changes.
