# Research program

The research arena: a broad, prior-art-filtered search for one strong paper
core, plus the infrastructure that tests candidates without touching the
product. Start with `DECISION_LOG.md` for the current state.

| Doc | What it holds |
|---|---|
| [DECISION_LOG.md](DECISION_LOG.md) | **State of record.** Every hypothesis verdict with numbers and artifact paths, including the mutation lab and the convergence pass |
| [CONVERGENCE.md](CONVERGENCE.md) | Convergence pass (2026-10-03): decision and 13 answers, analysis, frozen protocols with results (C1-C3, S1), prior-art recheck. Final status KILL; XDIS kept as product infrastructure |
| [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md) | Generated status table (`python -m echotales.research.aggregate`); do not edit |
| [RESEARCH_ARENA.md](RESEARCH_ARENA.md) | How `packages/research/` is built and how to add an experiment |
| [ENGINEERING_NOTES.md](ENGINEERING_NOTES.md) | Running log of every problem hit, its diagnosis, fix and lesson |

Merged topic documents (2026-10-22; each section keeps the original text and names its old path, so an old
reference still resolves by searching this table). Preregistrations, `PREFIX_FAITHFULNESS/`, `PAPER/`,
`experiments/` and `technical_contribution_probes/` were left as they were: they are locked records or are read by code.

| Doc | Merged from |
|---|---|
| [CHIMERA.md](CHIMERA.md) | `CHIMERA_*` (plan, novelty gate, prior art, data and benchmark plan, annotation guide, component matrix, defect backlog, errata, repository audit) |
| [AUDITS_AND_ADJUDICATION.md](AUDITS_AND_ADJUDICATION.md) | `CLAIM_TO_EVIDENCE_MATRIX`, `FINAL_SAMPLING_DESIGN_AUDIT`, `FINAL_STATISTICAL_CLAIMS_GATE`, `PRE_ADJUDICATION_*`, `HUMAN_ADJUDICATION_PLAN`, `API_ANNOTATION_PILOT` |
| [PD_EVENTS_NOTES.md](PD_EVENTS_NOTES.md) | `PD_EVENTS_V2/V3/V6/V7_NOTES` |
| [RESEARCH_RECORD.md](RESEARCH_RECORD.md) | `ECHOTALES_*` (summary, history, novelty ledger, source inventory, next decision), `METHODS_PAPER_EXPERIMENT_PLAN`, `TECHNICAL_CONTRIBUTION_INVENTORY` |
| [ENGINEERING_PROBES.md](ENGINEERING_PROBES.md) | `ENGINEERING_NOVELTY_PROBE/` E1-E6 and summary |
| [NOVELTY_SUPPORT.md](NOVELTY_SUPPORT.md) | `NOVELTY_REPORT/` prior-art, register notes, work plan, spend ledger, gate diagnosis (the report itself stays in `NOVELTY_REPORT/`) |
| [FORMAL_NARRATIVE_COMPILER.md](FORMAL_NARRATIVE_COMPILER.md) | `formal_narrative_compiler/*.md` (probe scripts stay in that folder) |
| [REVEAL_AWARE_VISUAL_MEMORY.md](REVEAL_AWARE_VISUAL_MEMORY.md) | `reveal_aware_visual_memory/` phase 1 and 2 |

Per-hypothesis statements and kill criteria live in
`packages/research/src/echotales/research/hypotheses.toml`. The earlier
idea-generation documents (opportunity map, themes, mutation catalog, kill
matrices, portfolio, roadmap, research cards) were removed on 2026-10-03 once
the convergence pass superseded them; their verdicts survive in
`DECISION_LOG.md`, and git history has the tracked ones.

Scope rules: StoryTrace firewall (no narrative temporal/observer/identity/
alias/consistency contribution); separately-scoped prototypes stay out; any
PATENT-CANDIDATE detail goes to the gitignored `docs/private/IP/`, with
only a pointer here. As of the mutation pass (2026-10-02) no mechanism qualifies;
the convergence pass found one weak candidate with thin inventive step
(`CONVERGENCE.md`, part 1, answer 12).
