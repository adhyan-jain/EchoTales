"""Properties of the CHIMERA renaming function pi (PREREG_T4, section 3).

Synthetic strings only. The properties are what T4's validity rests on:
bijection, token-level compositionality (containment survives), type
preservation, offset-map correctness and round-trip reversibility.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "chimera" / "renaming.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("chimera_renaming", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    # `dataclasses` resolves annotations through sys.modules[cls.__module__],
    # so a path-loaded module must be registered before it executes.
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


VOCAB = {"Fang", "Yuan", "Gu", "Yue", "Bo", "Mo", "Bei", "Chi", "Lian", "Master", "Village", "He"}
PROTECTED = {"master", "elder", "uncle", "clan", "head"}
EXISTING = {"the", "and", "he", "said", "clan", "head", "master", "walked", "to", "village"}


@pytest.fixture(scope="module")
def pi(mod):
    return mod.Renamer.build(VOCAB, protected_lower=PROTECTED, existing_lower=EXISTING, seed=20261015)


def test_mapping_is_a_bijection_on_the_renamed_vocabulary(pi):
    assert len(set(pi.mapping.values())) == len(pi.mapping)
    assert set(pi.mapping) <= VOCAB


def test_protected_titles_pronouns_and_stopwords_are_never_renamed(pi):
    for kept in ("Master", "He"):
        assert kept not in pi.mapping
    assert pi.rename("the clan head and the Master said") == "the clan head and the Master said"


def test_replacements_never_collide_with_existing_words(pi):
    assert not ({v.lower() for v in pi.mapping.values()} & EXISTING)


def test_containment_and_shared_tokens_survive(pi):
    full, part = pi.rename("Fang Yuan"), pi.rename("Yuan")
    assert part in full and full.endswith(part)
    assert pi.rename("Gu Yue Fang Yuan").split()[:2] == pi.rename("Gu Yue Bo").split()[:2]


def test_capitalisation_and_token_count_are_preserved(pi):
    s = "Fang Yuan walked to Gu Yue Village."
    out = pi.rename(s)
    assert len(out.split()) == len(s.split())
    assert all(t[0].isupper() for t, o in zip(out.split(), s.split()) if o[0].isupper())


def test_independent_whole_string_renaming_would_break_containment(pi):
    """The negative control T4 uses: renaming strings rather than tokens loses it."""
    whole = {"Fang Yuan": "Tor Vael", "Yuan": "Quilm"}
    assert whole["Yuan"] not in whole["Fang Yuan"]


def test_round_trip_through_the_inverse(pi):
    rng = random.Random(1)
    words = list(VOCAB) + ["the", "and", "walked", "clan", "head", "to", ",", ".", "'s"]
    for _ in range(200):
        s = " ".join(rng.choice(words) for _ in range(rng.randint(1, 30)))
        assert pi.inverse().rename(pi.rename(s)) == s


def test_offset_map_points_at_the_renamed_token(pi, mod):
    rng = random.Random(2)
    words = ["Fang", "Yuan", "walked", "the", "Gu", "Yue", "village", "Bo", "said"]
    for _ in range(300):
        toks = [rng.choice(words) for _ in range(rng.randint(2, 25))]
        text = " ".join(toks)
        new, omap = pi.rename_with_map(text)
        assert new == pi.rename(text)
        pos = 0
        for t in toks:
            at = text.index(t, pos)
            assert new[omap.map_offset(at) : omap.map_offset(at) + len(pi.rename(t))] == pi.rename(t)
            pos = at + len(t)


def test_build_is_deterministic_for_a_seed(mod):
    a = mod.Renamer.build(VOCAB, protected_lower=PROTECTED, existing_lower=EXISTING, seed=7)
    b = mod.Renamer.build(VOCAB, protected_lower=PROTECTED, existing_lower=EXISTING, seed=7)
    c = mod.Renamer.build(VOCAB, protected_lower=PROTECTED, existing_lower=EXISTING, seed=8)
    assert a.mapping == b.mapping != c.mapping


S_VOCAB = {"Gus", "Chris", "Bosses", "Ras", "Fang", "Yuan", "Mo", "Bei", "Lao", "Dass", "Nellus", "Ximenis"}


def test_replacement_has_exact_length_and_the_same_morphology_class(mod):
    """PREREG_T4 v2 section 1. The v1 smoke run turned "Brom Das" into "Brom Da"
    because a renamed token ended in a strippable "s" the original did not."""
    for seed in range(200):
        pi = mod.Renamer.build(S_VOCAB, protected_lower=set(), existing_lower=EXISTING, seed=seed)
        assert set(pi.mapping) == S_VOCAB
        for old, new in pi.mapping.items():
            assert len(new) == len(old), (seed, old, new)
            assert mod.s_class(new) == mod.s_class(old), (seed, old, new)
            assert new[0].isupper()


def test_s_class_mirrors_strip_morphology_plural_rule(mod):
    assert mod.s_class("Gus") is False and mod.s_class("Chris") is False and mod.s_class("Dass") is False
    assert mod.s_class("Bosses") is True and mod.s_class("Ras") is True and mod.s_class("Nellus") is False
    assert mod.s_class("Fang") is False


def test_v3_plural_closure_and_protection(mod):
    """PREREG_T4 v3 section 1 item 1: plural = pi(base) + "s" and stays strippable;
    the plural of a protected base is protected."""
    vocab = {"Moonblade", "Moonblades", "Yuan", "Yuans", "Masters", "Thunderwing"}
    for seed in range(100):
        pi = mod.Renamer.build(vocab, protected_lower={"master"}, existing_lower=EXISTING, seed=seed)
        assert pi.mapping["Moonblades"] == pi.mapping["Moonblade"] + "s"
        assert pi.mapping["Yuans"] == pi.mapping["Yuan"] + "s"
        assert mod.s_class(pi.mapping["Moonblades"]) is True
        assert "Masters" not in pi.mapping  # base "master" is protected


def test_v3_common_lowercase_words_are_protected_and_name_variants_follow(mod):
    pi = mod.Renamer.build(
        {"May", "Fang", "Yuan"}, protected_lower=set(), existing_lower=EXISTING, seed=5,
        common_lower={"may"},
    )
    assert "May" not in pi.mapping  # "may" is an ordinary lower-case word
    assert pi.rename("may you go") == "may you go"
    assert pi.rename("fang Yuan") == pi.mapping["Fang"].lower() + " " + pi.mapping["Yuan"]
    assert pi.rename("FANG") == "FANG"  # all-upper variants are left alone by design


def test_broken_control_is_context_dependent_and_loses_containment(mod):
    pi = mod.Renamer.build(VOCAB, protected_lower=PROTECTED, existing_lower=EXISTING, seed=3)
    broken = mod.BrokenYuanRenamer(dict(pi.mapping))
    full, alone = broken.rename("Fang Yuan"), broken.rename("Yuan")
    assert alone not in full  # the compositional property T4's negative control must break
    assert pi.rename("Yuan") in pi.rename("Fang Yuan")  # and pi keeps it
