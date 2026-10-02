# docs/

Start with the two files at this level; everything else is grouped by purpose.

| File / folder | Read it when |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | you are picking up work: current state, open defects, what to do next |
| [`EVOLUTION.md`](EVOLUTION.md) | you need to know *why* something is the way it is: the numbered, append-only log of every decision and reversal |
| [`design/`](design/) | changing the system: [`architecture.md`](design/architecture.md) (the model, `state_of()`, the ten non-negotiables), [`plans.md`](design/plans.md) (original phase-by-phase spec), [`details.md`](design/details.md) (per-file rationale), [`VISUAL_RENDERING.md`](design/VISUAL_RENDERING.md) |
| [`results/`](results/) | citing a number. [`FINAL_EVIDENCE_TABLE.md`](results/FINAL_EVIDENCE_TABLE.md) is the per-claim status; [`CANONICAL_RUN.md`](results/CANONICAL_RUN.md) says which database every number comes from; the rest are the individual experiments |
| [`research/`](research/) | choosing what to research next: the research opportunity map (33 candidates), themes, prior-art matrix, kill analysis, the `packages/research` arena, roadmap, and [`DECISION_LOG.md`](research/DECISION_LOG.md) -- every hypothesis verdict with its artifact (2026-10-02) |
| [`status/`](status/) | asking "is it done?": [`STATUS.md`](status/STATUS.md) (readiness, per-subsystem matrix, and what's not done and why — merged 2026-09-29 from three overlapping files), [`CURRENT_ARCHITECTURE.md`](status/CURRENT_ARCHITECTURE.md) (package map, production vs. research vs. historical), [`REFACTOR_REPORT.md`](status/REFACTOR_REPORT.md) (the 2026-09-29 cleanup pass) |
| [`paper/`](paper/) | writing the paper or the university report: tables, figures, claim boundaries, related work, venue analysis, report material |
| [`ops/`](ops/) | running things: GPU rental plan, key rotation |
| [`archive/`](archive/) | superseded plans and earlier validation passes, kept for provenance |
| `private/` | gitignored: the patent packet (`private/IP/`) and anything embargoed until the IPR decision. Never commit it |

Rules that keep this folder usable:

- **One place per kind of thing.** A new experiment write-up goes in `results/`, a new plan in `status/`, and the numbers themselves in `data/eval/`. No new loose files at this level.
- **Every accuracy figure is against an LLM-drafted silver reference set**, never called gold. Each results doc says so.
- **Measured, not asserted.** A number in a doc cites the file in `data/eval/` it came from. Drafts whose numbers do not trace to a result file stay in `private/` until they do.
- **Superseded, not deleted.** When a doc stops being current, move it to `archive/` and point to its replacement.
