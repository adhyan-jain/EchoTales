"""Invariants of the SIO world generator (PREREG_SIO_synthetic_identity_oracle.md v1).

The oracle's labels are only trustworthy if the generator's structure is what
the pre-registration says it is: exact offsets, exactly one PRESENT named
mention in every alias chapter (otherwise the resolver's sole-co-present rule
is not controlled), UNDETERMINED reader label for every pre-reveal alias, and
determinism by seed. Synthetic text only.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from echotales.core.enums import AliasType, ReferenceMode

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "chimera" / "sio_synthetic_oracle.py"


@pytest.fixture(scope="module")
def sio():
    spec = importlib.util.spec_from_file_location("chimera_sio", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["chimera_sio"] = m
    spec.loader.exec_module(m)
    return m


def test_offsets_are_exact_and_world_is_deterministic(sio) -> None:
    for seed in range(sio.N_WORLDS):
        a, b = sio.make_world(seed), sio.make_world(seed)
        assert a.chapters == b.chapters and [m.id for m in a.mentions] == [m.id for m in b.mentions]
        for m in a.mentions:
            assert a.chapters[m.chapter][m.offset:m.offset + len(m.text)] == m.text


def test_alias_chapters_have_exactly_one_present_named_mention(sio) -> None:
    for seed in range(sio.N_WORLDS):
        w = sio.make_world(seed)
        alias_chapters = {m.chapter for m in w.mentions if m.kind in ("pre_alias", "post_alias")}
        for ch in alias_chapters:
            present_named = [m for m in w.mentions if m.chapter == ch and m.alias_type is AliasType.RIGID_NAME
                             and m.mode is ReferenceMode.PRESENT]
            assert len(present_named) == 1, (seed, ch)


def test_pre_reveal_aliases_are_undetermined_and_reveal_distance_ok(sio) -> None:
    for seed in range(sio.N_WORLDS):
        w = sio.make_world(seed)
        assert all(m.reader is None for m in w.mentions if m.kind in ("pre_alias", "title_pre"))
        assert all(m.reader is not None for m in w.mentions if m.kind in ("post_alias", "title_post", "control"))
        for rv in w.reveals:
            assert rv["r"] >= rv["a"] + 2 and rv["r"] <= sio.N_CHAPTERS and rv["y"] != rv["z"]
        # the revealed identity was named before the reveal chapter, so "already-named" holds
        for rv in w.reveals:
            first_named = min(m.chapter for m in w.mentions
                              if m.kind == "control" and m.text == w.names[rv["y"]])
            assert first_named < rv["r"]


def test_resolver_run_is_deterministic_on_a_world(sio) -> None:
    w = sio.make_world(0)
    assert sio.run(w, sio.N_CHAPTERS) == sio.run(w, sio.N_CHAPTERS)


def test_wilson_matches_known_value(sio) -> None:
    lo, hi = sio.wilson(0, 80)
    assert lo == 0.0 and hi == pytest.approx(0.0457, abs=1e-3)  # prereg power statement: 0/80 -> 4.6%
