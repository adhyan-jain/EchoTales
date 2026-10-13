"""The hypothesis registry: every claim the arena can test, with its kill
criterion written down *before* the experiment runs.

Stored as TOML next to this module (`hypotheses.toml`) so a status change is a
reviewable one-line diff. `DECISION_LOG.md` is the narrative record; this file
is the machine-checkable one, and `tests/test_registry.py` holds the two in
step (every non-OPEN status must cite an artifact that exists).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from echotales.research.schema import Status

REGISTRY_PATH = Path(__file__).with_name("hypotheses.toml")


@dataclass(slots=True)
class Hypothesis:
    id: str
    title: str
    theme: str
    statement: str
    kill_criterion: str
    status: Status
    experiments: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # artifact paths backing the status
    firewall: str = ""  # why this is not StoryTrace territory
    patent_candidate: bool = False
    #: Mutation-lab provenance (docs/research/DECISION_LOG.md): which
    #: earlier candidates this one transforms, the prior art it was checked
    #: against, the highest experiment level reached (0 none, 1 existing-code
    #: run, 2 research module, 3 controlled benchmark, 4 human study), and
    #: which research-depth layers (L1-L6) it can plausibly reach.
    mutation_of: list[str] = field(default_factory=list)
    prior_art: list[str] = field(default_factory=list)
    level: int = 0
    depth: list[str] = field(default_factory=list)


def load(path: Path = REGISTRY_PATH) -> dict[str, Hypothesis]:
    data = tomllib.loads(path.read_text())
    out: dict[str, Hypothesis] = {}
    for hid, h in data.items():
        out[hid] = Hypothesis(
            id=hid,
            title=h["title"],
            theme=h["theme"],
            statement=h["statement"],
            kill_criterion=h["kill_criterion"],
            status=Status(h.get("status", "OPEN")),
            experiments=list(h.get("experiments", [])),
            evidence=list(h.get("evidence", [])),
            firewall=h.get("firewall", ""),
            patent_candidate=bool(h.get("patent_candidate", False)),
            mutation_of=list(h.get("mutation_of", [])),
            prior_art=list(h.get("prior_art", [])),
            level=int(h.get("level", 0)),
            depth=list(h.get("depth", [])),
        )
    return out
