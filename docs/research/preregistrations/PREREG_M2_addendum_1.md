# Addendum 1 to PREREG_M2_haiku_subagent.md v1 (pilot finding, before any real M2 spawn)

Frozen file `PREREG_M2_haiku_subagent.md` and `MANIFEST_M2.json` are unchanged. The two-spawn pilot on dummy, non-novel text (pre-registered in section 5) found:

1. **Counting convention.** Each pilot spawn reported `tool_uses = 3`. Reading the tool names (names only) showed Read, Write and the harness's own `SubagentHandback` (the call that returns the final reply). The pre-registered rule "exactly two tool calls" was a counting error about the harness, not a change in what a spawn may do. **Corrected rule: a valid spawn reports exactly 3 tool_uses (Read, Write, SubagentHandback).** To keep the frozen script `m2_haiku_prepare.py` unchanged (it tests `== 2`), the tool counts written to `toolcounts.tsv` are the reported `tool_uses` minus 1, and this is the only transformation.
2. **Overhead.** Each pilot spawn used about 50,700 and 50,900 subagent tokens (harness-reported) for a one-line task, so the fixed per-spawn overhead is about 50,800 tokens. For 124 spawns that is about **6.3 million tokens** of subscription quota, almost all fixed overhead. Per-token quota weighting for Haiku is not known to me.
3. **Protocol works.** Both pilot spawns read their file, wrote a valid token (a correct answer and a sensible abstention) and used no other tools.

No decision rule, metric, item set or prompt is changed by this addendum. Whether to run the 124 spawns, or a smaller fixed subset, is for the owner to decide given the overhead; any subset would be a new version, chosen by a rule that does not look at outcomes.
