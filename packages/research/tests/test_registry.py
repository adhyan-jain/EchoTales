"""The registry and the artifacts it cites must agree.

A status that cites a missing artifact is exactly the kind of claim this
arena exists to prevent (EVOLUTION 4.49/4.50: a fix documented as done that
was not).
"""

from pathlib import Path

from echotales.research import registry
from echotales.research.schema import Status

ROOT = Path(__file__).resolve().parents[3]


def test_every_decided_hypothesis_cites_an_existing_artifact():
    for h in registry.load().values():
        if h.status in (Status.KILLED, Status.SURVIVING):
            assert h.evidence, f"{h.id} is {h.status} with no evidence"
            for path in h.evidence:
                assert (ROOT / path).exists(), f"{h.id} cites missing {path}"


def test_every_hypothesis_has_a_kill_criterion_and_firewall_note():
    for h in registry.load().values():
        assert h.kill_criterion.strip(), h.id
        assert h.firewall.strip(), h.id


def test_registered_experiments_exist():
    from echotales.research.runner import available

    names = set(available())
    for h in registry.load().values():
        for e in h.experiments:
            assert e in names, f"{h.id} lists unknown experiment {e}"
