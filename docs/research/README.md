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
