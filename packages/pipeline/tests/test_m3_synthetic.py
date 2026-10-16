"""Invariants of the M3 / M3b synthetic experiments (PREREG_M3 v1, PREREG_M3b v1). Synthetic strings only.

These check the machinery, not the findings: exact offsets for every template, the oracle detector being perfect,
the causal system never being premature under the oracle detector, volume-first being premature by design, and the
bitemporal title model serving both views.
"""

from __future__ import annotations

import collections
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts" / "chimera"


def _load(name: str, fname: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def m3():
    return _load("chimera_m3", "m3_reveal_aware.py")


@pytest.fixture(scope="module")
def tt():
    return _load("chimera_tt", "title_tenure_model.py")


def test_every_template_has_exact_offsets_and_a_reveal_sentence_start(m3) -> None:
    for tpl in m3.TEMPLATES:
        for seed in (0, 7, 23):
            w = m3.make_world2(seed, tpl)
            for m in w.mentions:
                assert w.chapters[m.chapter][m.offset:m.offset + len(m.text)] == m.text
            assert all("sent_start" in rv for rv in w.reveals)


def test_oracle_detector_is_perfect_on_every_template(m3) -> None:
    for tpl in m3.TEMPLATES:
        w = m3.make_world2(3, tpl)
        got = {(d["alias"], d["chapter"], d["label"]) for d in m3.detect(w, "oracle")}
        assert got == {(rv["alias"], rv["r"], w.names[rv["y"]]) for rv in w.reveals}


def test_causal_system_is_never_premature_under_the_oracle_and_retro_always_is(m3) -> None:
    for tpl in m3.TEMPLATES:
        w = m3.make_world2(5, tpl)
        base = m3.S.run(w, m3.S.N_CHAPTERS)
        found = m3.detect(w, "oracle")
        for system, premature_expected in (("S_causal", False), ("S_retro", True)):
            labels = m3.system_labels(system, w, base, found)
            acc: dict = collections.defaultdict(int)
            m3.score(w, labels, acc)
            assert (acc["premature"] > 0) == premature_expected


def test_held_out_templates_are_not_detected_by_the_added_patterns(m3) -> None:
    # PREREG_M3: D_plus patterns were written for T0 and T1 only
    assert all(len(m3.detect(m3.make_world2(1, t), "plus")) == 2 for t in ("T0", "T1"))
    assert all(len(m3.detect(m3.make_world2(1, t), "plus")) == 0 for t in ("T2", "T3"))


def test_title_world_bare_title_precedes_the_declaration_in_even_seeds(tt) -> None:
    w = tt.S.make_world(0)  # even seed: bare title precedes the holder's declaration
    fd = tt.first_decl(tt.declarations(w))
    h1 = w.names[w.title["h1"]]
    pre = next(m for m in w.mentions if m.kind == "title_pre")
    assert fd[h1] > (pre.chapter, pre.offset)  # the reader has not been told yet
    assert pre.reader is None and pre.omni == h1
