"""Experiment configuration and seed derivation.

Configs are TOML (stdlib `tomllib`, no new dependency) because the repo's
hand-edited settings already are (`data/sources.toml`). Seeds are *derived*,
never drawn: `derive_seed(base, "condition", "unit")` hashes its parts, so
adding a condition or a unit never shifts the seed of any existing trial --
the property that makes a rerun after a design change comparable cell by cell.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def derive_seed(base: int, *parts: object) -> int:
    payload = json.dumps([base, *[str(p) for p in parts]], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:4], "big")


def stable_hash(obj: object) -> str:
    """Order-independent digest of a JSON-able object (dict keys sorted)."""
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass(slots=True)
class ExperimentConfig:
    experiment: str
    hypothesis_id: str
    base_seed: int = 20261002
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def hash(self) -> str:
        return stable_hash(
            {"experiment": self.experiment, "hypothesis": self.hypothesis_id,
             "seed": self.base_seed, "params": self.params}
        )

    @classmethod
    def load(cls, path: Path) -> ExperimentConfig:
        data = tomllib.loads(Path(path).read_text())
        return cls(
            experiment=data["experiment"],
            hypothesis_id=data["hypothesis_id"],
            base_seed=int(data.get("base_seed", 20261002)),
            params=dict(data.get("params", {})),
        )
