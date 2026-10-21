# docs/

Start with the two files at this level; everything else is grouped by purpose.

| File / folder | Read it when |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | you are picking up work: current state, open defects, what to do next |
| [`EVOLUTION.md`](EVOLUTION.md) | you need to know *why* something is the way it is: the numbered, append-only log of every decision and reversal |
| [`design/`](design/) | changing the system: [`decisions.md`](design/decisions.md) (**start here to learn the project**: every decision, why, and effect, kept current), [`architecture.md`](design/architecture.md) (the model, `state_of()`, the ten non-negotiables), [`plans.md`](design/plans.md) (original phase-by-phase spec), [`details.md`](design/details.md) (per-file rationale), [`VISUAL_RENDERING.md`](design/VISUAL_RENDERING.md) |
| [`results/`](results/) | citing a number. [`FINAL_EVIDENCE_TABLE.md`](results/FINAL_EVIDENCE_TABLE.md) is the per-claim status; [`CANONICAL_RUN.md`](results/CANONICAL_RUN.md) says which database every number comes from; [`EXPERIMENT_RESULTS.md`](results/EXPERIMENT_RESULTS.md), [`ABLATIONS.md`](results/ABLATIONS.md) and [`GOLD_AND_ANNOTATION.md`](results/GOLD_AND_ANNOTATION.md) hold the individual experiments (merged 2026-10-22 from 16 files) |
| [`research/`](research/) | choosing what to research next: [`DECISION_LOG.md`](research/DECISION_LOG.md) (state of record: every hypothesis verdict with its artifact), [`CONVERGENCE.md`](research/CONVERGENCE.md) (the 2026-10-03 convergence pass and its KILL verdict), generated [`EXPERIMENT_STATUS`](research/EXPERIMENT_STATUS.md), [`RESEARCH_ARENA`](research/RESEARCH_ARENA.md) (the `packages/research` arena), [`ENGINEERING_NOTES`](research/ENGINEERING_NOTES.md). The idea-generation docs were removed 2026-10-03; see [`research/README.md`](research/README.md) |
| [`status/`](status/) | asking "is it done?": [`STATUS.md`](status/STATUS.md) (readiness, per-subsystem matrix, and what's not done and why — merged 2026-09-29 from three overlapping files), [`CURRENT_ARCHITECTURE.md`](status/CURRENT_ARCHITECTURE.md) (package map, production vs. research vs. historical) |
| [`paper/`](paper/) | writing the paper or the university report: tables, figures, claim boundaries, related work, venue analysis, report material |
| [`ops/`](ops/) | running things: GPU rental plan, key rotation |
| [`archive/`](archive/) | superseded plans, earlier validation passes and the 2026-09-29 refactor report, kept for provenance |
| `private/` | gitignored: the patent packet (`private/IP/`) and anything embargoed until the IPR decision. Never commit it |

Rules that keep this folder usable:

- **One place per kind of thing.** A new experiment write-up goes in `results/`, a new plan in `status/`, and the numbers themselves in `data/eval/`. No new loose files at this level.
- **Every accuracy figure is against an LLM-drafted silver reference set**, never called gold. Each results doc says so.
- **Measured, not asserted.** A number in a doc cites the file in `data/eval/` it came from. Drafts whose numbers do not trace to a result file stay in `private/` until they do.
- **Few docs, merged not scattered.** A new finding extends an existing doc (`decisions.md` for choices, `EVOLUTION.md` for fixes, `HANDOFF.md` for open work). Research docs were merged on 2026-10-22 into one file per topic (see `research/README.md`); preregistrations stay as separate files because they are locked records.
- **Superseded, not deleted.** When a doc stops being current, move it to `archive/` and point to its replacement.
