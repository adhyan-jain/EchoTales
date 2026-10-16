"""Unit tests and adversarial audits for adjudication packages, validation scripts, and stratified estimators."""

from __future__ import annotations

import csv
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "review"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_adjudication_package import (
    KNOWN_LINKED_POPULATION_2026_09_25,
    STRATUM_POPULATION,
    TOTAL_POPULATION,
    calculate_boundary_aware_confidence_bounds,
    calculate_cohen_kappa,
    calculate_hypergeometric_upper_error_bound,
    calculate_precision_with_known_denominator,
    calculate_stratified_ratio_precision,
    check_adjudication_progress,
    normalize_decision_label,
    validate_initial_state,
    validate_v2_package,
)


def test_v1_adjudication_package_files_exist_and_match() -> None:
    p_std_blind = REPO_ROOT / "data/eval/adjudication/standard_200_blind.csv"
    p_hc_blind = REPO_ROOT / "data/eval/adjudication/hardcases_88_blind.csv"
    p_recon = REPO_ROOT / "data/eval/adjudication/model_annotations_reconciliation.csv"
    p_std_src = REPO_ROOT / "data/eval/human_review_200.csv"
    p_hc_src = REPO_ROOT / "data/eval/human_review_hardcases_88.csv"

    assert p_std_blind.exists()
    assert p_hc_blind.exists()
    assert p_recon.exists()

    ok = validate_initial_state(p_std_blind, p_hc_blind, p_recon, p_std_src, p_hc_src)
    assert ok is True


def test_v2_package_blinding_shuffling_and_integrity() -> None:
    std_v2 = REPO_ROOT / "data/eval/adjudication/standard_200_v2_blind.csv"
    hc_v2 = REPO_ROOT / "data/eval/adjudication/hardcases_88_v2_blind.csv"
    v2_map = REPO_ROOT / "data/eval/adjudication/v2_metadata_mapping.csv"
    std_src = REPO_ROOT / "data/eval/human_review_200.csv"
    hc_src = REPO_ROOT / "data/eval/human_review_hardcases_88.csv"

    assert std_v2.exists()
    assert hc_v2.exists()
    assert v2_map.exists()

    # Blinding assertion: standard must NOT contain category or reference_set_decision
    with std_v2.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        assert "category" not in fields
        assert "reference_set_decision" not in fields
        assert "presentation_order" in fields
        assert "system_link_status" in fields
        rows = list(reader)
        assert len(rows) == 200
        assert all(r["adjudicated_decision"] == "" for r in rows)
        assert all(r["adjudication_status"] == "pending" for r in rows)
        assert [int(r["presentation_order"]) for r in rows] == list(range(1, 201))

    # Blinding assertion: hardcases must NOT contain category
    with hc_v2.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        assert "category" not in fields
        assert "presentation_order" in fields
        rows = list(reader)
        assert len(rows) == 88
        assert all(r["adjudicated_decision"] == "" for r in rows)
        assert all(r["adjudication_status"] == "pending" for r in rows)
        assert [int(r["presentation_order"]) for r in rows] == list(range(1, 89))

    # Validate package via validation script function
    ok_v2 = validate_v2_package(std_v2, hc_v2, v2_map, std_src, hc_src)
    assert ok_v2 is True


def test_adversarial_reproduction_of_11082_denominator_and_precision() -> None:
    """Verify that published stratum counts reproduce X_hat = 11,082.6 and R_hat = 99.68% when using system actions."""
    src_path = REPO_ROOT / "data/eval/human_review_200.csv"
    ann_path = REPO_ROOT / "data/eval/human_review_200_annotated.csv"

    src_rows = list(csv.DictReader(src_path.open(encoding="utf-8")))
    ann_rows = list(csv.DictReader(ann_path.open(encoding="utf-8")))

    stratum_obs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for s, a in zip(src_rows, ann_rows):
        is_linked = 1 if s["predicted_entity"] != "UNRESOLVED" else 0
        is_corr = 1 if (is_linked and a["reviewer_label"].lower() == "correct") else 0
        stratum_obs[s["category"]].append((is_linked, is_corr))

    res = calculate_stratified_ratio_precision(stratum_obs, STRATUM_POPULATION)

    # 1. Numerator Y_hat must equal 11,046.86 (11004 + 125 * 12/35)
    expected_Y = 11004.0 + 125.0 * (12.0 / 35.0)
    assert abs(res["Y_hat"] - expected_Y) < 1e-4

    # 2. Denominator X_hat must equal 11,082.57 (11004 + 125 * 22/35 + 39 * 0/30)
    expected_X = 11004.0 + 125.0 * (22.0 / 35.0)
    assert abs(res["X_hat"] - expected_X) < 1e-4

    # 3. Ratio precision R_hat must equal 99.6777%
    expected_R = expected_Y / expected_X
    assert abs(res["R_hat"] - expected_R) < 1e-6
    assert abs(res["R_hat"] - 0.996777) < 1e-5


def test_adversarial_conflated_denominator_rejection() -> None:
    """Verify that treating candidate 'correct + incorrect' as links yields 11,103.0 and 99.49%, explaining the discrepancy."""
    src_path = REPO_ROOT / "data/eval/human_review_200.csv"
    ann_path = REPO_ROOT / "data/eval/human_review_200_annotated.csv"

    src_rows = list(csv.DictReader(src_path.open(encoding="utf-8")))
    ann_rows = list(csv.DictReader(ann_path.open(encoding="utf-8")))

    stratum_obs_conflated: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for s, a in zip(src_rows, ann_rows):
        is_conflated_link = 1 if a["reviewer_label"].lower() in {"correct", "incorrect"} else 0
        is_corr = 1 if a["reviewer_label"].lower() == "correct" else 0
        stratum_obs_conflated[s["category"]].append((is_conflated_link, is_corr))

    res_conflated = calculate_stratified_ratio_precision(stratum_obs_conflated, STRATUM_POPULATION)

    expected_X_conflated = 11004.0 + 39.0 * (2.0 / 30.0) + 125.0 * (27.0 / 35.0)
    assert abs(res_conflated["X_hat"] - expected_X_conflated) < 1e-4

    expected_R_conflated = (11004.0 + 125.0 * (12.0 / 35.0)) / expected_X_conflated
    assert abs(res_conflated["R_hat"] - expected_R_conflated) < 1e-4
    assert abs(res_conflated["R_hat"] - 0.994941) < 1e-5


def test_adversarial_candidate_unresolved_not_treated_as_abstention_without_source_check() -> None:
    """Verify that candidate label 'unresolved' is only counted as abstention if source predicted_entity is UNRESOLVED."""
    raw_linked_uncertain = "unresolved"
    canon, dis = normalize_decision_label(raw_linked_uncertain, is_linked=True)
    assert canon == "unresolved"
    assert dis == "uncertain_link"

    raw_abstained_unres = "unresolved"
    canon_a, dis_a = normalize_decision_label(raw_abstained_unres, is_linked=False)
    assert canon_a == "unresolved"
    assert dis_a == "uncertain_abstention"


def test_precision_with_known_exact_denominator() -> None:
    """Verify calculation of precision when the full-population link count is known exactly (11,092)."""
    obs = {
        "easy_name": [(1, 1)] * 30,
        "background": [(1, 1)] * 34,
        "alias": [(1, 1)] * 35,
        "observer_sensitive": [(1, 1)] * 30,
        "relational": [(1, 1)] * 12 + [(1, 0)] * 10 + [(0, 0)] * 13,
        "title": [(0, 0)] * 30,
        "unresolved_name": [(0, 0)] * 6,
    }

    res_known = calculate_precision_with_known_denominator(obs, STRATUM_POPULATION, KNOWN_LINKED_POPULATION_2026_09_25)

    expected_Y = 11004.0 + 125.0 * (12.0 / 35.0)
    assert abs(res_known["Y_hat"] - expected_Y) < 1e-4

    expected_P = expected_Y / 11092.0
    assert abs(res_known["P_known"] - expected_P) < 1e-6
    assert abs(res_known["P_known"] - 0.995930) < 1e-5
    assert res_known["se_P"] > 0.0


def test_boundary_aware_confidence_bounds_on_zero_error_strata() -> None:
    """Test that zero observed errors produce zero plug-in variance, but conservative boundary bounds are realistic."""
    obs = {
        "easy_name": [(1, 1)] * 30,
        "background": [(1, 1)] * 34,
        "alias": [(1, 1)] * 35,
        "observer_sensitive": [(1, 1)] * 30,
        "relational": [(1, 1)] * 12 + [(1, 0)] * 10 + [(0, 0)] * 13,
        "title": [(0, 0)] * 30,
        "unresolved_name": [(0, 0)] * 6,
    }

    res_ratio = calculate_stratified_ratio_precision(obs, STRATUM_POPULATION)
    assert abs(res_ratio["se_R"] - 0.00074) < 1e-4

    bounds = calculate_boundary_aware_confidence_bounds(obs, STRATUM_POPULATION, confidence_level=0.95)
    assert set(bounds["zero_error_strata"]) == {"easy_name", "background", "alias", "observer_sensitive"}
    assert bounds["R_conservative_lower"] < res_ratio["R_hat"]
    assert abs(bounds["R_conservative_lower"] - 0.90451) < 1e-4


def test_zero_link_stratum_edge_case() -> None:
    """Test that strata with zero proposed links contribute zero variance and do not trigger divide-by-zero."""
    obs = {
        "linked": [(1, 1)] * 20,
        "zero_link": [(0, 0)] * 10,
    }
    pops = {"linked": 100, "zero_link": 50}

    res = calculate_stratified_ratio_precision(obs, pops)
    assert res["R_hat"] == 1.0
    assert res["strata"]["zero_link"]["m"] == 0
    assert res["strata"]["zero_link"]["p"] is None


def test_human_incomplete_data_fails_require_complete_gate() -> None:
    """Verify that validation script rejects incomplete adjudication when require_complete is set."""
    p_std_v2 = REPO_ROOT / "data/eval/adjudication/standard_200_v2_blind.csv"
    adj, total, errs = check_adjudication_progress(p_std_v2, require_complete=True)
    assert adj == 0
    assert total == 200
    assert len(errs) == 200
    assert "is unadjudicated" in errs[0]


def test_model_annotations_quarantine() -> None:
    """Verify that model annotations are quarantined in reconciliation file and not present in blind sheets."""
    std_v2 = REPO_ROOT / "data/eval/adjudication/standard_200_v2_blind.csv"
    hc_v2 = REPO_ROOT / "data/eval/adjudication/hardcases_88_v2_blind.csv"
    recon = REPO_ROOT / "data/eval/adjudication/model_annotations_reconciliation.csv"

    assert recon.exists()
    recon_rows = list(csv.DictReader(recon.open(encoding="utf-8")))
    assert len(recon_rows) == 288
    assert "model_reviewer_label" in recon_rows[0]
    assert "model_reviewer_notes" in recon_rows[0]

    with std_v2.open(encoding="utf-8") as f:
        std_fields = csv.DictReader(f).fieldnames or []
        assert "model_reviewer_label" not in std_fields
        assert "model_reviewer_notes" not in std_fields

    with hc_v2.open(encoding="utf-8") as f:
        hc_fields = csv.DictReader(f).fieldnames or []
        assert "model_reviewer_label" not in hc_fields
        assert "model_reviewer_notes" not in hc_fields


# -----------------------------------------------------------------------------
# ADVERSARIAL SAMPLING DESIGN & INCLUSION PROBABILITY AUDIT TESTS
# -----------------------------------------------------------------------------

def test_sampling_inclusion_probabilities_and_non_uniformity() -> None:
    """Adversarial test proving that the 99 general pool mentions are NOT a simple random sample.

    Inclusion probabilities vary by a factor of 12.5x across strata in the general pool:
    alias (0.0388) vs easy_name (0.0064) vs scored_background (0.0031).
    """
    N_total = 11174
    n_phase1 = 166
    M_rem = N_total - n_phase1  # 11008
    n_rem = 34

    # Calculate exact inclusion probabilities
    pi_easy = (30 / 8933) + (1.0 - 30 / 8933) * (n_rem / M_rem)
    pi_alias = (35 / 977) + (1.0 - 35 / 977) * (n_rem / M_rem)
    pi_bg = (0 / 981) + (1.0 - 0 / 981) * (n_rem / M_rem)

    # 1. Alias inclusion probability is > 6x higher than easy_name
    assert pi_alias / pi_easy > 6.0
    # 2. Alias inclusion probability is > 12.5x higher than scored_background
    assert pi_alias / pi_bg > 12.5
    # 3. Prove non-uniformity: they cannot be treated as an unweighted simple random sample
    assert abs(pi_alias - pi_easy) > 0.03


def test_database_denominator_version_reconciliation_sql() -> None:
    """Adversarial test directly verifying SQLite database link counts and commit c8bfda9 lineage."""
    db_path = REPO_ROOT / "data/db/reverend-insanity.db"
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Total mentions in population
    cursor.execute('SELECT COUNT(*) FROM mention WHERE novel_id = "reverend-insanity";')
    assert cursor.fetchone()[0] == 11174

    # Current linked mentions (post-c8bfda9)
    cursor.execute('SELECT COUNT(*) FROM mention WHERE novel_id = "reverend-insanity" AND target_id IS NOT NULL;')
    assert cursor.fetchone()[0] == 11122

    # Mentions linked by TITLE_HOLDER (commit c8bfda9)
    cursor.execute('SELECT COUNT(*) FROM mention WHERE novel_id = "reverend-insanity" AND target_id IS NOT NULL AND method = "TITLE_HOLDER";')
    assert cursor.fetchone()[0] == 30

    # Mentions linked on 2026-09-25 (frozen review sheet version)
    cursor.execute('SELECT COUNT(*) FROM mention WHERE novel_id = "reverend-insanity" AND target_id IS NOT NULL AND (method IS NULL OR method != "TITLE_HOLDER");')
    pre_title_count = cursor.fetchone()[0]
    assert pre_title_count == 11092
    conn.close()


def test_zero_sample_in_scored_background_stratum() -> None:
    """Adversarial test proving that 0 of the 34 'background' rows in human_review_200.csv came from scored mentions."""
    src_path = REPO_ROOT / "data/eval/human_review_200.csv"
    rows = list(csv.DictReader(src_path.open(encoding="utf-8")))

    bg_rows = [r for r in rows if r["category"] == "background"]
    assert len(bg_rows) == 34

    # All 34 'background' rows in CSV are GAZETTEER_EXACT (33) or NAME_CONTAINMENT (1)
    # ZERO of them are SCORED or from the 981-mention heuristic pool!
    scored_in_bg = [r for r in bg_rows if "SCORED" in r["system_decision"]]
    assert len(scored_in_bg) == 0


def test_exact_denominator_estimator_imputation_audit() -> None:
    """Adversarial audit verifying that the 11,046.86 numerator imputes 100% correctness

    to all 981 unobserved scored background mentions, and rejecting it as an empirical estimate.
    """
    src_path = REPO_ROOT / "data/eval/human_review_200.csv"
    src_rows = list(csv.DictReader(src_path.open(encoding="utf-8")))

    # Verify that the 34 background rows in human_review_200.csv have 0 SCORED mentions
    bg_rows = [s for s in src_rows if s["category"] == "background"]
    assert len(bg_rows) == 34
    assert all("SCORED" not in s["system_decision"] for s in bg_rows)

    # Reconstruct the 11,046.86 numerator formula
    # Y_hat = sum_h N_h * (c_h / n_h)
    # easy_name: 8933 * (30/30) = 8933
    # background: 981 * (34/34) = 981  <-- unobserved scored stratum imputed at 100%!
    # alias: 977 * (35/35) = 977
    # observer_sensitive: 113 * (30/30) = 113
    # relational: 125 * (12/35) = 42.85714...
    # title: 39 * 0 = 0
    # unresolved_name: 6 * 0 = 0
    expected_Y = 8933.0 + 981.0 + 977.0 + 113.0 + 125.0 * (12.0 / 35.0)
    assert abs(expected_Y - 11046.85714) < 1e-4

    # The exact-denominator estimate is 11,046.86 / 11,092 = 99.593%
    p_exact = expected_Y / KNOWN_LINKED_POPULATION_2026_09_25
    assert abs(p_exact - 0.995930) < 1e-5

    # Sensitivity: If true precision in the 981 scored mentions was p_scored,
    # then Y_hat(p_scored) = (11,046.86 - 981 * (1 - p_scored)).
    # At p_scored = 0.90: precision = (11,046.86 - 98.1) / 11092 = 98.71%
    # At p_scored = 0.00: precision = (11,046.86 - 981) / 11092 = 90.75%
    p_sens_90 = (expected_Y - 981.0 * 0.10) / KNOWN_LINKED_POPULATION_2026_09_25
    assert abs(p_sens_90 - 0.987086) < 1e-5
    p_sens_00 = (expected_Y - 981.0 * 1.00) / KNOWN_LINKED_POPULATION_2026_09_25
    assert abs(p_sens_00 - 0.907488) < 1e-5


def test_horvitz_thompson_hajek_estimator_and_missing_domain() -> None:
    """Adversarial audit verifying that Horvitz-Thompson / Hajek ratio (99.67%)

    evaluates precision only over the sampled domain and yields 95.66% against X_pop.
    """
    import random
    from echotales.core.store import Store

    novel = "reverend-insanity"
    db_path = REPO_ROOT / "data/db/reverend-insanity.db"
    store = Store(str(db_path))
    conn = store.conn
    label = dict(conn.execute("SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (novel,)))
    revealed = {}
    for fact_ref, first in conn.execute(
            "SELECT fact_ref, MIN(learned_chapter) FROM observation GROUP BY fact_ref"):
        target = fact_ref.split(":", 1)[1].rsplit(":", 1)[0]
        revealed[target] = min(first, revealed.get(target, 10**6))

    rows = conn.execute(
        "SELECT id, chapter, block_index, offset, text, alias_type, method, target_id "
        "FROM mention WHERE novel_id=? ORDER BY chapter, block_index, offset", (novel,)).fetchall()

    def stratum_pred(r: tuple) -> str:
        _id, ch, _b, _o, text, alias_type, method, target = r
        if target in revealed and abs(ch - revealed[target]) <= 10:
            return "observer_sensitive"
        if alias_type == "TRANSFERABLE_TITLE":
            return "title"
        if alias_type == "RELATIONAL_DEICTIC":
            return "relational"
        if target is None:
            return "unresolved_name"
        if method == "GAZETTEER_EXACT" and label.get(target, "").casefold() == text.casefold():
            return "easy_name"
        if label.get(target, "").casefold() != text.casefold():
            return "alias"
        return "scored_background"

    rng = random.Random(20260925)
    pools = {}
    for r in rows:
        pools.setdefault(stratum_pred(r), []).append(r)

    targets = {"easy_name": 30, "alias": 35, "title": 30, "relational": 35,
               "unresolved_name": 10**6, "observer_sensitive": 30}
    chosen = []
    for name, n in targets.items():
        pool = pools.get(name, [])
        chosen += [(name, r) for r in rng.sample(pool, min(n, len(pool)))]

    taken = {c[1][0] for c in chosen}
    remaining = [r for r in rows if r[0] not in taken]
    chosen += [("background", r) for r in rng.sample(remaining, 34)]
    store.close()

    sorted_chosen = sorted(chosen, key=lambda x: (x[1][1], x[1][2], x[1][3]))

    strata_specs = {
        "easy_name": (8933, 30),
        "alias": (977, 35),
        "relational": (125, 35),
        "observer_sensitive": (113, 30),
        "title": (39, 30),
        "unresolved_name": (6, 6),
        "scored_background": (981, 0),
    }
    M_rem = 11174 - 166
    n_stage2 = 34
    pi_dict = {k: (n_k / N_k) + (1.0 - n_k / N_k) * (n_stage2 / M_rem) for k, (N_k, n_k) in strata_specs.items()}

    src_path = REPO_ROOT / "data/eval/human_review_200.csv"
    ann_path = REPO_ROOT / "data/eval/human_review_200_annotated.csv"
    src_rows = list(csv.DictReader(src_path.open(encoding="utf-8")))
    ann_rows = list(csv.DictReader(ann_path.open(encoding="utf-8")))

    Y_HT = 0.0
    X_HT = 0.0
    for (assigned_cat, r), s_csv, a_csv in zip(sorted_chosen, src_rows, ann_rows):
        true_cat = stratum_pred(r)
        pi_i = pi_dict[true_cat]
        w_i = 1.0 / pi_i
        is_linked = 1 if s_csv["predicted_entity"] != "UNRESOLVED" else 0
        is_corr = 1 if (is_linked and a_csv["reviewer_label"].lower() == "correct") else 0
        X_HT += w_i * is_linked
        Y_HT += w_i * is_corr

    # Numerator Y_HT = 10,610.91, Denominator X_HT = 10,646.34
    assert abs(Y_HT - 10610.91) < 0.1
    assert abs(X_HT - 10646.34) < 0.1

    # Hajek ratio is 99.667%
    hajek_ratio = Y_HT / X_HT
    assert abs(hajek_ratio - 0.99667) < 1e-4

    # If Y_HT is divided by the known denominator (11,092), it yields 95.66%
    ht_over_known = Y_HT / KNOWN_LINKED_POPULATION_2026_09_25
    assert abs(ht_over_known - 0.956627) < 1e-4


def test_finite_population_sample_size_hypergeometric_bounds() -> None:
    """Verify exact finite-population hypergeometric upper error bounds for N=981.

    Proves that n=25 cannot rule out a 1% error rate (yielding 11.11%), and that n=253 is required.
    """
    N = 981

    # n = 25: K_upper = 109 errors, rate = 11.11%
    k_25, rate_25 = calculate_hypergeometric_upper_error_bound(N, 25, 0.95)
    assert k_25 == 109
    assert abs(rate_25 - 0.1111) < 1e-3
    assert rate_25 > 0.10  # Far above 1%

    # n = 50: K_upper = 55 errors, rate = 5.61%
    k_50, rate_50 = calculate_hypergeometric_upper_error_bound(N, 50, 0.95)
    assert k_50 == 55
    assert abs(rate_50 - 0.0561) < 1e-3

    # n = 60: K_upper = 46 errors, rate = 4.69%
    k_60, rate_60 = calculate_hypergeometric_upper_error_bound(N, 60, 0.95)
    assert k_60 == 46
    assert abs(rate_60 - 0.0469) < 1e-3

    # n = 100: K_upper = 27 errors, rate = 2.75%
    k_100, rate_100 = calculate_hypergeometric_upper_error_bound(N, 100, 0.95)
    assert k_100 == 27
    assert abs(rate_100 - 0.0275) < 1e-3

    # n = 253: K_upper = 9 errors, rate = 0.92% (first n to achieve <= 1.0%)
    k_253, rate_253 = calculate_hypergeometric_upper_error_bound(N, 253, 0.95)
    assert k_253 == 9
    assert rate_253 <= 0.010

    # Verify that n=252 fails to achieve <= 1.0%
    k_252, rate_252 = calculate_hypergeometric_upper_error_bound(N, 252, 0.95)
    assert rate_252 > 0.010


def test_scored_background_sampling_frame_and_system_links() -> None:
    """Verify that all 981 scored background records form a well-defined frame of linked predictions."""
    from echotales.core.store import Store

    novel = "reverend-insanity"
    db_path = REPO_ROOT / "data/db/reverend-insanity.db"
    store = Store(str(db_path))
    conn = store.conn
    label = dict(conn.execute("SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (novel,)))
    revealed = {}
    for fact_ref, first in conn.execute(
            "SELECT fact_ref, MIN(learned_chapter) FROM observation GROUP BY fact_ref"):
        target = fact_ref.split(":", 1)[1].rsplit(":", 1)[0]
        revealed[target] = min(first, revealed.get(target, 10**6))

    rows = conn.execute(
        "SELECT id, chapter, block_index, offset, text, alias_type, method, target_id "
        "FROM mention WHERE novel_id=? ORDER BY chapter, block_index, offset", (novel,)).fetchall()

    def stratum_pred(r: tuple) -> str:
        _id, ch, _b, _o, text, alias_type, method, target = r
        if target in revealed and abs(ch - revealed[target]) <= 10:
            return "observer_sensitive"
        if alias_type == "TRANSFERABLE_TITLE":
            return "title"
        if alias_type == "RELATIONAL_DEICTIC":
            return "relational"
        if target is None:
            return "unresolved_name"
        if method == "GAZETTEER_EXACT" and label.get(target, "").casefold() == text.casefold():
            return "easy_name"
        if label.get(target, "").casefold() != text.casefold():
            return "alias"
        return "scored_background"

    bg_rows = [r for r in rows if stratum_pred(r) == "scored_background"]
    store.close()

    # Exact population size of scored_background is 981
    assert len(bg_rows) == 981

    # ALL 981 have target_id IS NOT NULL (all are system-linked predictions)
    assert all(r[7] is not None for r in bg_rows)

    # All 981 are RIGID_NAME
    assert all(r[5] == "RIGID_NAME" for r in bg_rows)

    # Methods: exactly 964 SCORED and 17 DECLARATION
    methods = [r[6] for r in bg_rows]
    assert methods.count("SCORED") == 964
    assert methods.count("DECLARATION") == 17
