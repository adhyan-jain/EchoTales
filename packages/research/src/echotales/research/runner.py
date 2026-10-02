"""`python -m echotales.research run <experiment>` -- the one entry point.

An experiment is a module under `echotales.research.experiments` exposing
`HYPOTHESIS_ID`, `DEFAULT_PARAMS` and `run(cfg, *, stub) -> (RunResult-parts,
trials)`. The runner owns everything that must be uniform across experiments:
config hashing, seed base, output layout, provenance, and the guarantee that
`results.json` is deterministic (sorted keys, no timestamps) so `--stub` reruns
can be diffed byte-for-byte in CI.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from pathlib import Path

from echotales.pipeline.paths import research_run_dir
from echotales.research import experiments as _experiments_pkg
from echotales.research import provenance
from echotales.research.config import ExperimentConfig
from echotales.research.schema import RunResult


def available() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(_experiments_pkg.__path__)
                  if not m.name.startswith("_"))


def run_experiment(
    name: str,
    *,
    stub: bool,
    params: dict | None = None,
    base_seed: int | None = None,
    out_root: Path | None = None,
    run_id: str | None = None,
) -> Path:
    mod = importlib.import_module(f"echotales.research.experiments.{name}")
    merged = {**getattr(mod, "DEFAULT_PARAMS", {}), **(params or {})}
    cfg = ExperimentConfig(
        experiment=name,
        hypothesis_id=mod.HYPOTHESIS_ID,
        base_seed=base_seed if base_seed is not None else 20261002,
        params=merged,
    )
    result, trials, inputs = mod.run(cfg, stub=stub)
    assert isinstance(result, RunResult)
    rid = run_id or f"{'stub' if stub else 'real'}-{cfg.hash}"
    out = (Path(out_root) / mod.HYPOTHESIS_ID / rid) if out_root else research_run_dir(
        mod.HYPOTHESIS_ID, rid
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    with (out / "trials.jsonl").open("w") as fh:
        for t in trials:
            fh.write(json.dumps(t.model_dump(mode="json"), sort_keys=True) + "\n")
    (out / "run_config.json").write_text(json.dumps(
        {"experiment": name, "hypothesis_id": cfg.hypothesis_id, "base_seed": cfg.base_seed,
         "params": cfg.params, "config_hash": cfg.hash, "stub": stub},
        indent=2, sort_keys=True, default=str) + "\n")
    (out / "provenance.json").write_text(
        json.dumps(provenance.collect(cfg.hash, inputs), indent=2, sort_keys=True) + "\n"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="echotales.research")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list experiments and registered hypotheses")
    r = sub.add_parser("run", help="run one experiment")
    r.add_argument("experiment")
    r.add_argument("--stub", action="store_true", help="synthetic inputs, no GPU/network")
    r.add_argument("--seed", type=int, default=None)
    r.add_argument("--param", action="append", default=[], metavar="KEY=JSON",
                   help="override one param, value parsed as JSON (falls back to string)")
    r.add_argument("--out", type=Path, default=None)
    r.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    if args.cmd == "list":
        from echotales.research import registry
        for name in available():
            mod = importlib.import_module(f"echotales.research.experiments.{name}")
            print(f"{name:32s} -> {mod.HYPOTHESIS_ID}")
        print()
        for h in registry.load().values():
            print(f"{h.id:10s} {h.status.value:9s} {h.title}")
        return 0

    params = {}
    for kv in args.param:
        k, _, v = kv.partition("=")
        try:
            params[k] = json.loads(v)
        except json.JSONDecodeError:
            params[k] = v
    out = run_experiment(args.experiment, stub=args.stub, params=params, base_seed=args.seed,
                         out_root=args.out, run_id=args.run_id)
    print(out)
    print((out / "results.json").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
