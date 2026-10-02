"""Typed records every experiment reads and writes.

Kept deliberately small: a *unit* (the thing measured -- a dialogue line, a
passage, a panel), a *condition* (one cell of the design), a *trial* (one unit
under one condition, with its seed and outcomes), and a *run* (the whole
experiment). Experiments differ in what goes inside `features`/`outputs`/
`metrics`, never in the envelope, which is what lets `compare.py` line up any
two runs without per-experiment glue.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Status(StrEnum):
    """Where a hypothesis stands. KILLED is a result, not a failure to report."""

    OPEN = "OPEN"
    SURVIVING = "SURVIVING"
    KILLED = "KILLED"
    PARKED = "PARKED"  # not killed by evidence; deprioritised by prior art or cost


class Unit(BaseModel):
    """One measured thing. `id` must be stable across runs and machines."""

    id: str
    source: str  # dataset or artifact name, e.g. "pdnc:emma" or "ri-ch1-audio"
    features: dict[str, Any] = Field(default_factory=dict)


class Trial(BaseModel):
    unit_id: str
    condition: str
    seed: int
    outputs: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


class RunResult(BaseModel):
    """What `results.json` holds. Contains nothing time- or machine-dependent,
    so a stub-mode rerun at the same seed is byte-identical (provenance --
    git sha, timestamps, hostname -- goes in a separate `provenance.json`)."""

    hypothesis_id: str
    experiment: str
    mode: str  # "stub" | "real"
    config_hash: str
    n_units: int
    n_trials: int
    summary: dict[str, Any]
    #: The experiment's own reading against its pre-registered kill criterion.
    #: Advisory: a human records the actual decision in DECISION_LOG.md.
    verdict_hint: str
    notes: list[str] = Field(default_factory=list)
