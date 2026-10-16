# Addendum 1 to PREREG_PD_v7: Luna is the headline test; local runs are exploratory (written before the Luna run and before any v7 result was inspected)

Date: 2026-10-16. Authority: owner instruction in this session ("approved 0.10 for PD v7 Luna"; "the five local runs ... are the last ones; their results go in as exploratory context, not headline evidence"). The frozen files (`PREREG_PD_v7.md`, `MANIFEST_PD_v7.json`, `pd_v7.py`) are unchanged.

**What changes.** (1) The headline test of the prospective fame hypothesis is **H2**, Luna alone: mean event gap for famous events minus obscure events at least +10 points with a one-sided permutation p below 0.05 (the rule in `PREREG_PD_v7.md`, section 2, unchanged). (2) The five local models' results, including **H1** and **H3** as computed by the frozen script, are reported as **exploratory context** and not as the headline verdict. (3) The frozen script prints its own verdict string using the original ordering (H1 primary); in the report that string is shown as "script verdict (original rule)", and the headline sentence is the H2 result.

**Why this is not a data-dependent change.** At the time of writing the five local runs were still being produced, none had been analysed, and the Luna run had not started. The reason is the earlier finding that the small local models show no reliable effect on poorly recognised books (PD v6, report 5.21), so a test built mainly on them mostly measures their lack of memory; Luna is the model that shows the effect.

**Budget.** The Luna run is guarded at $0.10 (expected $0.055, worst case $0.091 from the exact estimate). Spent before this run: $0.3992; with the guard the total cannot exceed $0.4992, which is $0.017 above the earlier ceiling of $0.4824 by the owner's explicit approval of this run.

**Unchanged limits.** Nine events (5 famous, 4 obscure); the fame proxy is one month of Gutenberg download counts; the smallest attainable one-sided permutation p is about 0.008; model-selected events; one run per cell.
