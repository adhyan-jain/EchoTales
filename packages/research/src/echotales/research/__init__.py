"""EchoTales research arena.

One product, one shared data/evaluation layer, many experiment branches.
Every hypothesis the project tests lives here as a registered, seeded,
provenance-stamped experiment, so a claim in `docs/research/` always traces
to an artifact under `data/eval/research/` -- the rule the rest of the repo
learned the hard way (EVOLUTION 4.81: results that did not trace to a commit).

Dependency direction is one-way: this package imports `echotales.core` and
`echotales.pipeline`; neither ever imports it (enforced by
`tests/test_import_direction.py`). Research code can therefore never change
product behaviour except through opt-in hook points that default to off.
"""
