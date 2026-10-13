# Research arena

`packages/research/` (`echotales-research`): one shared data, evaluation and
provenance layer, with many experiment branches. It imports `echotales.core`
and `echotales.pipeline`; neither imports it (`tests/test_import_direction.py`).
Product behaviour cannot change through research code.

## Layout

```
packages/research/src/echotales/research/
  schema.py         Unit / Trial / RunResult; Status (OPEN, SURVIVING, KILLED, PARKED)
  config.py         TOML configs; derive_seed(base, *keys) -- adding a cell never shifts another's seed
  provenance.py     git sha + dirty flag, config hash, input digests, env
  registry.py       loads hypotheses.toml (status, kill criterion, evidence, firewall note)
  hypotheses.toml   the machine-checked registry; DECISION_LOG.md is the narrative
  runner.py         python -m echotales.research {list | run <experiment> [--stub] [--param k=json]}
  compare.py        cross-run tables for a hypothesis
  aggregate.py      python -m echotales.research.aggregate regenerates docs/research/EXPERIMENT_STATUS.md
  stats.py          re-exports pipeline/eval/stats.py + Wilson, permutation, ECE, Bradley-Terry
  datasets/         pdnc.py (human gold), public_chapters.py, echotales_artifacts.py (read-only DB/manifests/corrections),
                    visual_beats.py (fixed-seed visual stimuli via product persona/prompt.py::build_image_prompt; render_gpu)
  models/           listener.py (ideal-observer listener)
  transforms/       attribution_probe.py (product ladder on PDNC), error_injection.py
  controllers/      casting.py (distinctiveness-controlled casting)
  evaluators/       voice_geometry.py (Chatterbox speaker-embedding space; manipulation check),
                    attribute_probe.py (CLIP zero-shot + llava via ollama)
  baselines/        moment_scorers.py (product drama port, visualness, dialogue, LLM, random)
  human_studies/    listening_study.html, analyze_listening.py (cluster bootstrap, power sim),
                    synthesize.py (product TTS, cached by voice+text),
                    moment_annotation.html, moment_pairs.py
  experiments/      attribution_calibration, commitment_gating, error_cost_stimuli,
                    hedged_voice_feasibility, moment_selection_baselines, ideal_listener, confusion_casting,
                    correction_leverage, complementarity_selection, visual_rungs,
                    judge_intervention, disagreement_posterior
```

**GPU rule.** `datasets/visual_beats.py::render_gpu` loads NoobAI-XL directly to the GPU and refuses if the GPU is busy. Check the GPU is free first, never use CPU offload, and ask the owner before any RAM-heavy job.

## Output

Each run writes to `data/eval/research/<HYPOTHESIS>/<run-id>/`:
- `results.json`: deterministic (sorted keys, no timestamps). Stub reruns are byte-identical, and CI checks this.
- `trials.jsonl`: per unit. **Not committed**; several carry PDNC annotation content, and all can be regenerated.
- `run_config.json` (named so the repo-wide `config.json` ignore rule does not swallow it) and `provenance.json`.

Paths come from `pipeline/paths.py` (`RESEARCH_DIR`, `RESEARCH_CACHE_DIR`,
`RESEARCH_SCRATCH_DIR`, `research_run_dir`).

## Adding an experiment

1. Register the hypothesis in `hypotheses.toml` with a kill criterion written **before** running.
2. Add `experiments/<name>.py` exposing `HYPOTHESIS_ID`, `DEFAULT_PARAMS` and `run(cfg, *, stub) -> (RunResult, trials, inputs)`.
3. Give it a stub path that needs no GPU, network or corpus. `tests/test_arena.py` runs every experiment in stub mode twice and checks determinism.
4. Run it for real, then record the verdict in `DECISION_LOG.md` and the status plus evidence path in the registry (`tests/test_registry.py` checks the artifact exists).

## Data

- **PDNC.** Fetch the GitHub tarball into `data/cache/research/pdnc` (gitignored; `datasets/pdnc.py` accepts both repo layouts).
- **EARS embeddings.** Cached at `data/cache/research/voice_embeddings_ears.json`.
- **Stimuli and audio.** Written under `data/scratch/research/`.

## Running the human studies

- **Listening study.** Serve the stimulus directory statically (`stimuli.json` plus `audio/`) and open `listening_study.html`. Assignment is a Latin square keyed by participant code. Responses download as JSON. Analyse with `python -m echotales.research.human_studies.analyze_listening responses-*.json`.
- **Moment study.** Build a pairs file with `moment_pairs.make_pairs`, open `moment_annotation.html`, and analyse agreement and Bradley-Terry strengths with `moment_pairs.py`.

## Product hooks

None added in this pass. Proposed opt-in hooks (default off) are
`voice/runner.py` casting policy and `render/panels.py` framing rung. Add them
only after H-COST or H-VABST produce a loss table worth acting on.
