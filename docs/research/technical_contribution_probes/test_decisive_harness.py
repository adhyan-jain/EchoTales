"""Tests for decisive_harness.py: they check harness *mechanics* (oracle truth table, oracle
independence, differential agreement, determinism, artifact fixtures behave as labelled). None asserts
that T beats a baseline; the comparison lives in DECISIVE_EXPERIMENT_RESULTS.md.

    .venv/bin/python -m pytest -o addopts="" docs/research/technical_contribution_probes/test_decisive_harness.py
"""
import inspect
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import decisive_harness as h  # noqa: E402

R = h.R


def fact(**kw):
    base = dict(fid="a:p1:hair_color:v1", kind="attr", target="p1", key="hair_color", value="v1",
                start=1, end=None, learned=1)
    base.update(kw)
    return h.F(**base)


# ---- oracle truth table (hand-computed from PREREGISTRATION.md section 1) --------------------
def test_oracle_story_interval_is_half_open():
    f = fact(start=5, end=10)
    assert not h.o_fact(f, 4, 99, R)
    assert h.o_fact(f, 5, 99, R) and h.o_fact(f, 9.5, 99, R)
    assert not h.o_fact(f, 10, 99, R)


def test_oracle_retrospective_reveal_needs_disclosure():
    f = fact(start=3, learned=100)
    assert not h.o_fact(f, 5, 10, R)       # true in the story, not yet disclosed
    assert h.o_fact(f, 5, 100, R)


def test_oracle_foreshadow_is_not_admissible():
    f = fact(start=40, learned=2)
    assert not h.o_fact(f, 5, 10, R)       # disclosed, but not yet true at p


def test_oracle_retraction_is_positional():
    f = fact(learned=1, retracted=50)
    assert h.o_fact(f, 20, 20, R)          # belief kept in the past
    assert not h.o_fact(f, 20, 50, R)      # gone once the retraction is disclosed, even for p < retraction


def test_oracle_observer_door():
    private = fact(observer="WU")
    shared = fact(witness=(("WU", 7),))
    assert not h.o_fact(private, 5, 99, R)
    assert h.o_fact(private, 5, 99, "WU")
    assert not h.o_fact(private, 5, 99, "LI")
    assert not h.o_fact(shared, 5, 99, "LI")
    assert not h.o_fact(shared, 5, 6, "WU")
    assert h.o_fact(shared, 5, 7, "WU")    # effective learned = witness time


def test_oracle_persona_binding_gate():
    w = h.W((), bindings=((R, 1), ("WU", 5)))
    assert h.o_persona_ok(w, 1, R)
    assert not h.o_persona_ok(w, 4, "WU")
    assert h.o_persona_ok(w, 5, "WU")
    assert not h.o_persona_ok(w, 99, "LI")


def test_oracle_does_not_reference_candidate_code():
    src = "".join(inspect.getsource(fn) for fn in (
        h.o_fact, h.o_persona_ok, h.in_view, h.o_admissible, h.group_of, h.o_true_closure, h.o_asset_verdict))
    for banned in ("StateResolver", "state_of", "RowPolicy", "Store", "store.", "compile_render_state"):
        assert banned not in src, banned


def test_scoring_counts_both_error_types():
    b = h.Build()
    a1 = b.attr("p1", "hair_color", 1, None, 1)
    late = b.attr("p1", "eye_color", 1, None, 99)
    w = h.W(tuple(b.facts))
    adm = {a1}
    assert h.score_set(w, set(), adm) == ([], ["g:p1:hair_color"], 1)            # exposing nothing is an omission
    assert h.score_set(w, {late}, adm)[0] == [late]                              # forbidden fact is an exposure
    assert h.score_set(w, {a1}, adm) == ([], [], 1)


# ---- differential: oracle vs state_of vs RowPolicy --------------------------------------------
def test_differential_oracle_state_of_rowpolicy_agree():
    d = h.differential(range(1000, 1040))
    assert d["n_comparisons"] == 40 * 10 * 5
    assert d["oracle_vs_rowpolicy_mismatches"] == []
    assert d["oracle_vs_state_of_mismatches"] == []


def test_fuzz_exercises_every_rule():
    """Guards against a vacuous differential: each rule must be the sole reason some fact is hidden."""
    sole = defaultdict(int)
    for s in range(1000, 1030):
        b, qs, _ = h.gen_fz(s)
        w = h.W(tuple(b.facts))
        for (p, k, o) in qs:
            for f in w.facts:
                if h.o_fact(f, p, k, o):
                    continue
                sole["retraction"] += f.retracted is not None and h.o_fact(replace(f, retracted=None), p, k, o)
                sole["story"] += h.o_fact(replace(f, start=0, end=None), p, k, o)
                sole["knowledge"] += h.o_fact(
                    replace(f, learned=0, witness=tuple((x, 0) for x, _ in f.witness)), p, k, o)
    assert all(sole[x] > 50 for x in ("retraction", "story", "knowledge")), dict(sole)


# ---- B1 really runs production code and reproduces the documented defects ----------------------
def _run(cls, system, consumer, seed=0):
    b, qs, _ = h.CONS_CLASSES[cls](seed)
    w = h.W(tuple(b.facts))
    st = h.build_store(w)
    return [h.score_set(w, system(st, w, consumer, p, k, o), h.o_admissible(w, consumer, p, k, o))
            for (p, k, o) in qs]


def test_b1_reproduces_retrospective_leak_d1():
    ex, _, _ = _run("X1", h.b1, "ATTR")[0]      # first query is (p, p, READER): k == p, production-reachable
    assert ex, "appearance_of is p-only: the late-disclosed fact must reach the attribute set"


def test_b1_reproduces_retraction_erasure_d2():
    ex, om, _ = _run("X3", h.b1, "ATTR")[0]     # retracted belief is still admissible before its retraction
    assert om and not ex


def test_benign_class_is_clean_for_all_consumer_systems():
    b, qs, _ = h.gen_xb(0)
    w = h.W(tuple(b.facts))
    st = h.build_store(w)
    for system in (h.b1, h.b2, h.t_consumer):
        for cons in ("ATTR", "BRIEF", "ALIAS", "REL", "RESOLVE"):
            for (p, k, o) in qs:
                ex, om, n = h.score_set(w, system(st, w, cons, p, k, o), h.o_admissible(w, cons, p, k, o))
                assert (ex, om) == ([], []) and n >= 1, (system.__name__, cons)


# ---- artifacts ------------------------------------------------------------------------------
def _art(case, seed=0):
    c = h.gen_art(case, seed)
    w, st = c.world, h.build_store(c.world)
    w_eval = w
    if c.mutation:
        h.apply_retraction_to_store(st, w, *c.mutation)
        w_eval = h.retract_in_spec(w, *c.mutation)
    return c, w, w_eval, st, h.registry_of(w)


def _score(case, system, seed=0):
    c, w, w_eval, st, reg = _art(case, seed)
    tot = defaultdict(int)
    for (p, k, o) in c.queries:
        v = {a.aid: h.o_asset_verdict(w_eval, a, p, k, o) for a in w.assets if a.present}
        acc = system(st, reg, w_eval, p, k, o)
        tot["forbid"] += sum(v.get(a) == "FORBID" for a in acc)
        tot["unver"] += sum(v.get(a) == "UNVERIFIABLE" for a in acc)
        tot["omit"] += sum(x == "ADMIT" and a not in acc for a, x in v.items())
        tot["admit"] += sum(x == "ADMIT" for x in v.values())
    return dict(tot)


def test_registry_tag_detects_edit_but_not_clean_record():
    _, _, _, _, reg = _art("XT-tamper-drop-fact")
    r = reg["kid"]
    assert r.tag != h.sign(r.aid, r.kind, r.facts, r.parents, r.content)     # stored manifest != signed one
    _, _, _, _, reg2 = _art("X7-chain-clean")
    r2 = reg2["a1"]
    assert r2.tag == h.sign(r2.aid, r2.kind, r2.facts, r2.parents, r2.content)


def test_t_fail_closed_on_missing_parent_cycle_tamper():
    for case in ("XT-missing-parent", "XT-missing-parent-late", "XT-cycle", "XT-tamper-drop-parent",
                 "XT-tamper-drop-fact", "XT-tamper-in-parent"):
        s = _score(case, h.art_t)
        assert s["forbid"] == 0 and s["unver"] == 0, (case, s)


def test_t_does_not_suppress_admissible_artifacts():
    for case in ("X7-chain-clean", "X7-late-in-parent", "X7-diamond", "X9-derived-text", "XT-underdeclared-text",
                 "X8-stale-retraction", "X7-observer-witness"):
        s = _score(case, h.art_t)
        assert s["omit"] == 0 and s["admit"] > 0, (case, s)


def test_underdeclared_image_is_outside_t_threat_model():
    """Pinned limitation, pre-declared in PREREGISTRATION.md: opaque content plus a signed, self-consistent manifest."""
    assert _score("XT-underdeclared-image", h.art_t)["forbid"] > 0


def test_b3_snapshot_goes_stale_after_retraction_and_t_does_not():
    b3 = lambda st, reg, w, p, k, o: h.art_b3(st, w, p, k, o)  # noqa: E731
    assert _score("X8-stale-retraction", b3)["forbid"] > 0
    assert _score("X8-stale-retraction", h.art_t)["forbid"] == 0


def test_naive_transitive_misses_tamper_t_catches():
    assert _score("XT-tamper-drop-parent", h.art_b2x)["forbid"] > 0
    assert _score("XT-tamper-drop-parent", h.art_t)["forbid"] == 0


# ---- determinism and ablations ------------------------------------------------------------
def test_case_generation_is_deterministic():
    a = [(c.cid, c.queries, len(c.world.facts)) for c in h.build_cases()]
    b = [(c.cid, c.queries, len(c.world.facts)) for c in h.build_cases()]
    assert a == b and len(a) == 1260


def test_run_is_deterministic_on_a_subset():
    cases = [c for c in h.build_cases() if c.seed < 2 and c.cls != "FZ"]
    r1 = [h.run_case(c, defaultdict(float)) for c in cases]
    r2 = [h.run_case(c, defaultdict(float)) for c in cases]
    assert r1 == r2


def test_ablation_flag_changes_behaviour():
    b, qs, _ = h.gen_x1(0)
    w = h.W(tuple(b.facts))
    st = h.build_store(w)
    p, k, o = qs[1]                                  # k before the late disclosure
    adm = h.o_admissible(w, "ATTR", p, k, o)
    full = h.score_set(w, h.t_consumer(st, w, "ATTR", p, k, o), adm)
    no_k = h.score_set(w, h.t_consumer(st, w, "ATTR", p, k, o, h.ABLATIONS["A1-no-knowledge-time"]), adm)
    assert full[0] == [] and no_k[0] != []
