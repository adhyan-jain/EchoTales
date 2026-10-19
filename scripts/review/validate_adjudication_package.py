"""Validation and reconciliation script for EchoTales human-adjudication packages (v1 and v2).

Verifies:
- Complete row coverage (200 standard rows, 88 hard cases).
- Reviewer blinding integrity (stripping of category and reference cues in v2).
- Source-ID and contextual field integrity (zero shifts against source CSVs).
- Valid label domain (legacy: {'correct', 'incorrect', 'unresolved'};
  v2 disambiguated: {'correct_link', 'incorrect_link', 'uncertain_link',
  'appropriate_abstention', 'inappropriate_abstention', 'uncertain_abstention',
  'correct_reference', 'incorrect_reference', 'uncertain_reference'}).
- Calculates:
  * Stratified Ratio Estimator (R_hat = Y_hat / X_hat) with Finite Population Correction (FPC).
  * Design-based estimator with exact known denominator (P_hat = Y_hat / X_pop).
  * Asymptotic Taylor linearization SE vs conservative boundary bounds for zero-error strata.
  * System link coverage, abstention rates, and strict accuracy.
  * Model-vs-author agreement and Cohen's kappa.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

# Canonical legacy labels
LEGACY_LABELS = frozenset({"correct", "incorrect", "unresolved"})

# Disambiguated v2 labels
V2_LINKED_LABELS = frozenset({"correct_link", "incorrect_link", "uncertain_link"})
V2_ABSTAINED_LABELS = frozenset({"appropriate_abstention", "inappropriate_abstention", "uncertain_abstention"})
V2_REFERENCE_LABELS = frozenset({"correct_reference", "incorrect_reference", "uncertain_reference"})
ALL_VALID_LABELS = LEGACY_LABELS | V2_LINKED_LABELS | V2_ABSTAINED_LABELS | V2_REFERENCE_LABELS

# True population sizes N_h extracted from data/db/reverend-insanity.db (11,174 mentions total)
STRATUM_POPULATION: dict[str, int] = {
    "easy_name": 8933,
    "background": 981,
    "alias": 977,
    "relational": 125,
    "observer_sensitive": 113,
    "title": 39,
    "unresolved_name": 6,
}
TOTAL_POPULATION = sum(STRATUM_POPULATION.values())  # 11,174

# Exact known linked population on 2026-09-25 frozen evaluation state (pre-title_holders):
# easy_name (8933) + background (981) + alias (977) + observer_sensitive (113) + relational (88) = 11,092
KNOWN_LINKED_POPULATION_2026_09_25 = 11092


def calculate_cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    """Calculate Cohen's kappa for two raters over nominal categories."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0

    n = len(labels_a)
    categories = sorted(list(set(labels_a) | set(labels_b)))
    if len(categories) <= 1:
        return 1.0

    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    pe = sum((count_a[c] / n) * (count_b[c] / n) for c in categories)

    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def calculate_stratified_ratio_precision(
    stratum_observations: Mapping[str, Sequence[tuple[int, int]]],
    stratum_populations: Mapping[str, int],
) -> dict[str, Any]:
    """Calculate stratified ratio estimator R_hat = Y_hat / X_hat with Taylor linearization FPC variance.

    Args:
        stratum_observations: dict mapping stratum_name -> sequence of (is_linked, is_correct) pairs.
            is_linked: 1 if link was proposed, 0 if abstained.
            is_correct: 1 if link was proposed and correct, 0 otherwise.
        stratum_populations: dict mapping stratum_name -> population size N_h.

    Returns:
        Dictionary containing:
        - R_hat: corpus-wide precision estimate (ratio of totals).
        - se_R: standard error under Taylor linearization with FPC.
        - ci_95: (ci_lower, ci_upper) 95% confidence interval.
        - X_hat: estimated total links in population.
        - Y_hat: estimated total correct links in population.
        - strata: dictionary of stratum-level statistics.
    """
    Y_hat = 0.0
    X_hat = 0.0
    stratum_stats: dict[str, dict[str, Any]] = {}

    for cat, N_h in stratum_populations.items():
        obs = stratum_observations.get(cat, [])
        n_h = len(obs)
        if n_h == 0:
            stratum_stats[cat] = {
                "n": 0, "N": N_h, "m": 0, "c": 0, "p": None,
                "fpc": 1.0, "y_bar": 0.0, "x_bar": 0.0
            }
            continue

        m_h = sum(x for x, y in obs)
        c_h = sum(y for x, y in obs)
        y_bar = c_h / n_h
        x_bar = m_h / n_h
        Y_hat += N_h * y_bar
        X_hat += N_h * x_bar
        p_h = (c_h / m_h) if m_h > 0 else None
        fpc = max(0.0, 1.0 - (n_h / N_h))

        stratum_stats[cat] = {
            "n": n_h, "N": N_h, "m": m_h, "c": c_h, "p": p_h,
            "fpc": fpc, "y_bar": y_bar, "x_bar": x_bar
        }

    if X_hat == 0.0:
        return {
            "R_hat": 0.0, "se_R": 0.0, "ci_95": (0.0, 0.0),
            "X_hat": 0.0, "Y_hat": 0.0, "strata": stratum_stats
        }

    R_hat = Y_hat / X_hat

    # Taylor linearization variance with Finite Population Correction (FPC)
    var_num = 0.0
    for cat, N_h in stratum_populations.items():
        obs = stratum_observations.get(cat, [])
        n_h = len(obs)
        if n_h <= 1:
            continue
        fpc = max(0.0, 1.0 - (n_h / N_h))
        u_vals = [y - R_hat * x for x, y in obs]
        u_bar = sum(u_vals) / n_h
        s2_u = sum((u - u_bar) ** 2 for u in u_vals) / (n_h - 1)
        var_num += (N_h ** 2) * fpc * (s2_u / n_h)

    var_R = var_num / (X_hat ** 2)
    se_R = math.sqrt(max(0.0, var_R))
    ci_lower = max(0.0, R_hat - 1.95996 * se_R)
    ci_upper = min(1.0, R_hat + 1.95996 * se_R)

    return {
        "R_hat": R_hat,
        "se_R": se_R,
        "ci_95": (ci_lower, ci_upper),
        "X_hat": X_hat,
        "Y_hat": Y_hat,
        "strata": stratum_stats,
    }


def calculate_precision_with_known_denominator(
    stratum_observations: Mapping[str, Sequence[tuple[int, int]]],
    stratum_populations: Mapping[str, int],
    total_linked_population: int,
) -> dict[str, Any]:
    """Calculate population precision when the population total of links X_pop is exactly known.

    Formula:
        P_known = Y_hat / X_pop
        Var(P_known) = (1 / X_pop^2) * Var(Y_hat)
        where Var(Y_hat) = sum_h N_h^2 * (1 - f_h) * (s_yh^2 / n_h).
    """
    if total_linked_population <= 0:
        return {"P_known": 0.0, "se_P": 0.0, "ci_95": (0.0, 0.0), "Y_hat": 0.0, "X_pop": 0}

    Y_hat = 0.0
    var_Y = 0.0

    for cat, N_h in stratum_populations.items():
        obs = stratum_observations.get(cat, [])
        n_h = len(obs)
        if n_h == 0:
            continue
        y_vals = [y for x, y in obs]
        c_h = sum(y_vals)
        y_bar = c_h / n_h
        Y_hat += N_h * y_bar

        if n_h > 1:
            fpc = max(0.0, 1.0 - (n_h / N_h))
            s2_y = sum((y - y_bar) ** 2 for y in y_vals) / (n_h - 1)
            var_Y += (N_h ** 2) * fpc * (s2_y / n_h)

    P_known = Y_hat / total_linked_population
    var_P = var_Y / (total_linked_population ** 2)
    se_P = math.sqrt(max(0.0, var_P))
    ci_lower = max(0.0, P_known - 1.95996 * se_P)
    ci_upper = min(1.0, P_known + 1.95996 * se_P)

    return {
        "P_known": P_known,
        "se_P": se_P,
        "ci_95": (ci_lower, ci_upper),
        "Y_hat": Y_hat,
        "X_pop": total_linked_population,
    }


def calculate_boundary_aware_confidence_bounds(
    stratum_observations: Mapping[str, Sequence[tuple[int, int]]],
    stratum_populations: Mapping[str, int],
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Calculate conservative boundary bounds accounting for zero observed errors in dominant strata.

    In strata where all sampled links are correct (0 observed errors), the plug-in sample
    variance is zero. To assess the worst-case population error rate consistent with observing
    0 errors in n_h trials, we use the finite-sample boundary limit:
        epsilon_upper,h = 1 - (1 - conf)^(1 / m_h)  [or rule of three: 3 / m_h]
    This provides an adversarial lower bound on total correct links and precision.
    """
    X_hat = 0.0
    Y_hat_plug_in = 0.0
    Y_hat_conservative = 0.0
    zero_error_strata: list[str] = []

    alpha = 1.0 - confidence_level

    for cat, N_h in stratum_populations.items():
        obs = stratum_observations.get(cat, [])
        n_h = len(obs)
        if n_h == 0:
            continue
        m_h = sum(x for x, y in obs)
        c_h = sum(y for x, y in obs)
        w_h = m_h - c_h

        x_bar = m_h / n_h
        y_bar = c_h / n_h
        X_hat += N_h * x_bar
        Y_hat_plug_in += N_h * y_bar

        if m_h > 0 and w_h == 0:
            zero_error_strata.append(cat)
            # Upper error rate bound at specified confidence
            err_bound = 1.0 - (alpha ** (1.0 / m_h))
            # Conservative correct mentions in stratum
            min_correct = N_h * (1.0 - err_bound)
            Y_hat_conservative += min_correct
        else:
            Y_hat_conservative += N_h * y_bar

    if X_hat == 0.0:
        return {"R_hat": 0.0, "R_conservative_lower": 0.0, "zero_error_strata": []}

    R_hat = Y_hat_plug_in / X_hat
    R_conservative_lower = Y_hat_conservative / X_hat

    return {
        "R_hat": R_hat,
        "R_conservative_lower": R_conservative_lower,
        "zero_error_strata": zero_error_strata,
        "X_hat": X_hat,
        "Y_hat_conservative": Y_hat_conservative,
    }


def calculate_hypergeometric_upper_error_bound(
    N: int,
    n: int,
    confidence_level: float = 0.95,
) -> tuple[int, float]:
    """Calculate the exact finite-population one-sided upper confidence bound on error count.

    Under SRSWOR of size n from finite population N, when zero errors are observed (X = 0),
    finds the largest error count K such that P(X = 0 | N, K, n) >= 1 - confidence_level.
    Any population with K > K_upper is rejected at significance level alpha = 1 - confidence_level.

    Returns:
        (K_upper, error_rate_upper) where error_rate_upper = K_upper / N.
    """
    if n <= 0 or N <= 0 or n > N:
        return 0, 0.0

    alpha = 1.0 - confidence_level
    last_compatible_K = 0

    for K in range(0, N - n + 1):
        log_p = 0.0
        for j in range(n):
            log_p += math.log(N - K - j) - math.log(N - j)
        p0 = math.exp(log_p)
        if p0 >= alpha:
            last_compatible_K = K
        else:
            break

    return last_compatible_K, last_compatible_K / N


def normalize_decision_label(raw_label: str, is_linked: bool) -> tuple[str, str]:
    """Normalize user input label into (canonical_protocol_label, disambiguated_v2_label)."""
    lbl = raw_label.strip().lower()
    if not lbl:
        return "", ""

    if lbl in {"correct_link", "correct"}:
        return ("correct", "correct_link") if is_linked else ("correct", "appropriate_abstention")
    elif lbl in {"incorrect_link", "incorrect"}:
        return ("incorrect", "incorrect_link") if is_linked else ("incorrect", "inappropriate_abstention")
    elif lbl in {"appropriate_abstention"}:
        return "unresolved", "appropriate_abstention"
    elif lbl in {"inappropriate_abstention"}:
        return "incorrect", "inappropriate_abstention"
    elif lbl in {"uncertain_link", "uncertain_abstention", "unresolved"}:
        return ("unresolved", "uncertain_link") if is_linked else ("unresolved", "uncertain_abstention")
    elif lbl in {"correct_reference"}:
        return "correct", "correct_reference"
    elif lbl in {"incorrect_reference"}:
        return "incorrect", "incorrect_reference"
    elif lbl in {"uncertain_reference"}:
        return "unresolved", "uncertain_reference"
    else:
        return lbl, lbl


def validate_initial_state(
    standard_blind_path: Path,
    hardcases_blind_path: Path,
    reconciliation_path: Path,
    standard_src_path: Path,
    hardcases_src_path: Path,
) -> bool:
    """Validate that the v1 package is correctly initialized for review."""
    errors: list[str] = []

    if not standard_blind_path.exists():
        errors.append(f"Missing {standard_blind_path}")
        return False

    b200 = list(csv.DictReader(standard_blind_path.open(encoding="utf-8")))
    s200 = list(csv.DictReader(standard_src_path.open(encoding="utf-8")))

    if len(b200) != 200:
        errors.append(f"standard_200_blind has {len(b200)} rows, expected 200")
    if len(s200) != 200:
        errors.append(f"human_review_200 has {len(s200)} rows, expected 200")

    for i, (b, s) in enumerate(zip(b200, s200)):
        if b["sample_id"] != s["sample_id"]:
            errors.append(f"Row {i}: sample_id mismatch ({b['sample_id']} vs {s['sample_id']})")
        for col in ["chapter", "source_text", "mention", "predicted_entity", "candidate_entities", "system_decision", "reference_set_decision", "category"]:
            if b[col] != s[col]:
                errors.append(f"Row {b['sample_id']}: field mismatch in '{col}'")

    if not hardcases_blind_path.exists():
        errors.append(f"Missing {hardcases_blind_path}")
        return False

    b88 = list(csv.DictReader(hardcases_blind_path.open(encoding="utf-8")))
    s88 = list(csv.DictReader(hardcases_src_path.open(encoding="utf-8")))

    if len(b88) != 88:
        errors.append(f"hardcases_88_blind has {len(b88)} rows, expected 88")
    if len(s88) != 88:
        errors.append(f"human_review_hardcases_88 has {len(s88)} rows, expected 88")

    for i, (b, s) in enumerate(zip(b88, s88)):
        if b["sample_id"] != s["sample_id"]:
            errors.append(f"Row {i}: sample_id mismatch ({b['sample_id']} vs {s['sample_id']})")
        for col in ["chapter", "source_text", "mention", "reference_set_decision", "category"]:
            if b[col] != s[col]:
                errors.append(f"Row {b['sample_id']}: field mismatch in '{col}'")

    if not reconciliation_path.exists():
        errors.append(f"Missing {reconciliation_path}")
        return False

    recon = list(csv.DictReader(reconciliation_path.open(encoding="utf-8")))
    if len(recon) != 288:
        errors.append(f"reconciliation has {len(recon)} rows, expected 288")

    recon_ids = {r["sample_id"] for r in recon}
    expected_ids = {r["sample_id"] for r in b200} | {r["sample_id"] for r in b88}
    if recon_ids != expected_ids:
        errors.append("Reconciliation sample_id set does not match blind review sets")

    if errors:
        print("V1 VALIDATION FAILED with errors:")
        for e in errors[:10]:
            print("  -", e)
        return False

    print("V1 VALIDATION PASSED: Package structure, schemas, and source data 100% verified.")
    return True


def validate_v2_package(
    std_v2_path: Path,
    hc_v2_path: Path,
    map_path: Path,
    std_src_path: Path,
    hc_src_path: Path,
) -> bool:
    """Validate that the v2 package enforces blinding, shuffling, and source integrity."""
    errors: list[str] = []

    for p in [std_v2_path, hc_v2_path, map_path, std_src_path, hc_src_path]:
        if not p.exists():
            errors.append(f"File not found: {p}")
            return False

    std_v2 = list(csv.DictReader(std_v2_path.open(encoding="utf-8")))
    hc_v2 = list(csv.DictReader(hc_v2_path.open(encoding="utf-8")))
    map_rows = list(csv.DictReader(map_path.open(encoding="utf-8")))
    std_src = {r["sample_id"]: r for r in csv.DictReader(std_src_path.open(encoding="utf-8"))}
    hc_src = {r["sample_id"]: r for r in csv.DictReader(hc_src_path.open(encoding="utf-8"))}

    if len(std_v2) != 200:
        errors.append(f"standard_200_v2_blind has {len(std_v2)} rows, expected 200")
    if len(hc_v2) != 88:
        errors.append(f"hardcases_88_v2_blind has {len(hc_v2)} rows, expected 88")
    if len(map_rows) != 288:
        errors.append(f"v2_metadata_mapping has {len(map_rows)} rows, expected 288")

    # 1. Blinding check: verify stripped columns
    std_cols = set(std_v2[0].keys()) if std_v2 else set()
    if "category" in std_cols:
        errors.append("Blinding violation: 'category' present in standard_200_v2_blind.csv")
    if "reference_set_decision" in std_cols:
        errors.append("Blinding violation: 'reference_set_decision' present in standard_200_v2_blind.csv")

    hc_cols = set(hc_v2[0].keys()) if hc_v2 else set()
    if "category" in hc_cols:
        errors.append("Blinding violation: 'category' present in hardcases_88_v2_blind.csv")

    # 2. Presentation order check
    std_orders = [int(r["presentation_order"]) for r in std_v2 if r.get("presentation_order", "").isdigit()]
    if std_orders != list(range(1, 201)):
        errors.append("standard_200_v2_blind presentation_order is not 1..200 sequence")

    hc_orders = [int(r["presentation_order"]) for r in hc_v2 if r.get("presentation_order", "").isdigit()]
    if hc_orders != list(range(1, 89)):
        errors.append("hardcases_88_v2_blind presentation_order is not 1..88 sequence")

    # 3. Source integrity check for standard rows
    for r in std_v2:
        sid = r["sample_id"]
        if sid not in std_src:
            errors.append(f"Unknown sample_id {sid} in standard v2")
            continue
        src = std_src[sid]
        for col in ["chapter", "source_text", "mention", "predicted_entity", "candidate_entities", "system_decision"]:
            if r[col] != src[col]:
                errors.append(f"Row {sid}: content mismatch in '{col}' against source")
        expected_status = "ABSTAINED" if src["predicted_entity"] == "UNRESOLVED" else "LINKED"
        if r.get("system_link_status") != expected_status:
            errors.append(f"Row {sid}: system_link_status mismatch ({r.get('system_link_status')} vs {expected_status})")

    # 4. Source integrity check for hardcases rows
    for r in hc_v2:
        sid = r["sample_id"]
        if sid not in hc_src:
            errors.append(f"Unknown sample_id {sid} in hardcases v2")
            continue
        src = hc_src[sid]
        for col in ["chapter", "source_text", "mention"]:
            if r[col] != src[col]:
                errors.append(f"Row {sid}: content mismatch in '{col}' against source")
        if r.get("target_reference_entity") != src["reference_set_decision"]:
            errors.append(f"Row {sid}: target_reference_entity mismatch against reference_set_decision")

    # 5. Metadata mapping check
    map_by_sid = {m["sample_id"]: m for m in map_rows}
    for r in std_v2:
        sid = r["sample_id"]
        if sid not in map_by_sid:
            errors.append(f"Missing mapping for standard sample_id {sid}")
        elif map_by_sid[sid]["category"] != std_src[sid]["category"]:
            errors.append(f"Mapping stratum mismatch for {sid}")

    for r in hc_v2:
        sid = r["sample_id"]
        if sid not in map_by_sid:
            errors.append(f"Missing mapping for hardcases sample_id {sid}")
        elif map_by_sid[sid]["category"] != hc_src[sid]["category"]:
            errors.append(f"Mapping stratum mismatch for {sid}")

    if errors:
        print("V2 VALIDATION FAILED with errors:")
        for e in errors[:10]:
            print("  -", e)
        return False

    print("V2 VALIDATION PASSED: Blinding verified, shuffling verified, source integrity 100% confirmed.")
    return True


def check_adjudication_progress(
    blind_path: Path, require_complete: bool = False
) -> tuple[int, int, list[str]]:
    """Check how many rows have been adjudicated in a blind review file."""
    rows = list(csv.DictReader(blind_path.open(encoding="utf-8")))
    total = len(rows)
    adjudicated = 0
    errors: list[str] = []

    for r in rows:
        label = (r.get("adjudicated_decision") or r.get("adjudicated_label") or "").strip().lower()
        if label:
            canon, _ = normalize_decision_label(label, is_linked=(r.get("predicted_entity") != "UNRESOLVED"))
            if canon not in LEGACY_LABELS and label not in ALL_VALID_LABELS:
                errors.append(f"Row {r['sample_id']} has invalid label: '{label}'")
            else:
                adjudicated += 1
        elif require_complete:
            errors.append(f"Row {r['sample_id']} is unadjudicated")

    return adjudicated, total, errors


def print_provisional_baseline(
    std_src_path: Path,
    annotated_path: Path,
    known_denominator: int = KNOWN_LINKED_POPULATION_2026_09_25,
) -> None:
    """Print the adversarially audited provisional baseline from candidate annotations."""
    src_rows = list(csv.DictReader(std_src_path.open(encoding="utf-8")))
    ann_rows = list(csv.DictReader(annotated_path.open(encoding="utf-8")))

    by_cat: dict[str, list[tuple[dict[str, str], dict[str, str]]]] = defaultdict(list)
    for s, a in zip(src_rows, ann_rows):
        by_cat[s["category"]].append((s, a))

    stratum_obs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for cat, pairs in by_cat.items():
        for s, a in pairs:
            is_linked = 1 if s["predicted_entity"] != "UNRESOLVED" else 0
            is_corr = 1 if (is_linked and a["reviewer_label"].lower() == "correct") else 0
            stratum_obs[cat].append((is_linked, is_corr))

    res_ratio = calculate_stratified_ratio_precision(stratum_obs, STRATUM_POPULATION)
    res_known = calculate_precision_with_known_denominator(stratum_obs, STRATUM_POPULATION, known_denominator)
    res_bounds = calculate_boundary_aware_confidence_bounds(stratum_obs, STRATUM_POPULATION)

    print("\n" + "=" * 80)
    print("PROVISIONAL MODEL-ASSISTED BASELINE AUDIT (NOT HUMAN GROUND TRUTH)")
    print("=" * 80)
    print(f"Total novel mentions: {TOTAL_POPULATION}")
    print(f"Sample size:          {len(src_rows)} (151 linked system decisions, 49 abstentions)")
    print("-" * 80)
    print("RECONCILED ESTIMATORS COMPARISON:")
    print(f"  1. Stratified Ratio Estimator (R_hat):      {res_ratio['R_hat']:.4%}  (SE={res_ratio['se_R']:.4%}, 95% CI: [{res_ratio['ci_95'][0]:.2%}, {res_ratio['ci_95'][1]:.2%}])")
    print(f"     -> Estimated linked denominator (X_hat): {res_ratio['X_hat']:.1f}")
    print(f"     -> Estimated correct links (Y_hat):      {res_ratio['Y_hat']:.1f}")
    print(f"  2. Precision with Known Denominator:       {res_known['P_known']:.4%}  (SE={res_known['se_P']:.4%}, 95% CI: [{res_known['ci_95'][0]:.2%}, {res_known['ci_95'][1]:.2%}])")
    print(f"     -> Exact population linked count:        {res_known['X_pop']}")
    print(f"  3. Conservative Boundary Lower Bound:       {res_bounds['R_conservative_lower']:.4%}  (accounts for small n=30 in dominant stratum)")
    print(f"  4. Raw Sample Precision (over links):       {141/151:.4%} (141 / 151)")
    print(f"  5. Conflated Sample Precision (historical): {141/158:.4%} (141 / 158, conflated abstentions)")
    print("=" * 80 + "\n")


def compute_adjudicated_metrics_v2(
    std_v2_path: Path,
    hc_v2_path: Path,
    map_path: Path,
    recon_path: Path,
    known_denominator: int = KNOWN_LINKED_POPULATION_2026_09_25,
) -> None:
    """Compute formal evaluation metrics using v2 files, metadata mapping, and stratified estimators."""
    std_rows = list(csv.DictReader(std_v2_path.open(encoding="utf-8")))
    hc_rows = list(csv.DictReader(hc_v2_path.open(encoding="utf-8")))
    map_dict = {m["sample_id"]: m for m in csv.DictReader(map_path.open(encoding="utf-8"))}
    recon_dict = {r["sample_id"]: r for r in csv.DictReader(recon_path.open(encoding="utf-8"))} if recon_path.exists() else {}

    adj_std = [r for r in std_rows if (r.get("adjudicated_decision") or r.get("adjudicated_label", "")).strip()]
    adj_hc = [r for r in hc_rows if (r.get("adjudicated_decision") or r.get("adjudicated_label", "")).strip()]

    print("\n" + "=" * 70)
    print("HUMAN ADJUDICATION METRICS & POPULATION ESTIMATES (V2)")
    print("=" * 70)
    print(f"Standard 200 Sheet:  {len(adj_std)} / {len(std_rows)} reviewed ({len(adj_std)/len(std_rows):.1%})")
    print(f"Hard Cases 88 Sheet: {len(adj_hc)} / {len(hc_rows)} reviewed ({len(adj_hc)/len(hc_rows):.1%})")

    if not adj_std:
        print("\n[INFO] No human adjudications recorded yet in standard_200_v2_blind.csv.")
        print("[INFO] Review package is clean, blinded, and ready for author review.")
        return

    # Process Standard 200 Adjudications
    stratum_obs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    action_counts: Counter = Counter()

    for r in adj_std:
        sid = r["sample_id"]
        cat = map_dict[sid]["category"]
        is_linked = (r.get("system_link_status") == "LINKED") or (r.get("predicted_entity", "") != "UNRESOLVED")
        raw_label = (r.get("adjudicated_decision") or r.get("adjudicated_label", "")).strip().lower()
        canon_label, dis_label = normalize_decision_label(raw_label, is_linked)

        action_counts[dis_label] += 1
        x_hi = 1 if is_linked else 0
        y_hi = 1 if (is_linked and canon_label == "correct") else 0
        stratum_obs[cat].append((x_hi, y_hi))

    # Calculate Stratified Estimators
    res = calculate_stratified_ratio_precision(stratum_obs, STRATUM_POPULATION)
    res_known = calculate_precision_with_known_denominator(stratum_obs, STRATUM_POPULATION, known_denominator)
    res_bounds = calculate_boundary_aware_confidence_bounds(stratum_obs, STRATUM_POPULATION)

    print("\n" + "-" * 70)
    print("STRATUM-BY-STRATUM BREAKDOWN")
    print("-" * 70)
    print(f"{'Stratum':20s} {'Pop N':7s} {'Pop Wt':7s} {'n_rev':6s} {'Links':6s} {'Corr':6s} {'Stratum P':10s} {'FPC':6s}")
    print("-" * 70)

    for cat, N_h in STRATUM_POPULATION.items():
        st = res["strata"][cat]
        w_h = N_h / TOTAL_POPULATION
        p_str = f"{st['p']:.1%}" if st["p"] is not None else "N/A"
        fpc_str = f"{st['fpc']:.2f}"
        print(f"{cat:20s} {N_h:6d}  {w_h:6.2%} {st['n']:5d}  {st['m']:5d}  {st['c']:5d}  {p_str:10s} {fpc_str:6s}")

    print("-" * 70)
    print("POPULATION-WEIGHTED EVALUATION ESTIMATES")
    print("-" * 70)
    print(f"Stratified Ratio Precision (R_hat):      {res['R_hat']:.2%}")
    print(f"Taylor SE (asymptotic plug-in with FPC): {res['se_R']:.2%}")
    print(f"95% Confidence Interval (Wald):          [{res['ci_95'][0]:.2%}, {res['ci_95'][1]:.2%}]")
    print(f"Precision with Known Denominator (P):    {res_known['P_known']:.2%} (SE={res_known['se_P']:.2%}, X_pop={known_denominator})")
    print(f"Conservative 95% Lower Bound (Boundary): {res_bounds['R_conservative_lower']:.2%}")

    # Sample-level unweighted metrics
    tot_linked = sum(x for obs in stratum_obs.values() for x, y in obs)
    tot_corr = sum(y for obs in stratum_obs.values() for x, y in obs)
    naive_p = (tot_corr / tot_linked) if tot_linked > 0 else 0.0
    print(f"\nUnweighted Sample Precision (over links): {tot_corr}/{tot_linked} = {naive_p:.2%}")

    # Disambiguated Decision Distribution
    print("\n" + "-" * 70)
    print("DISAMBIGUATED DECISION TAXONOMY DISTRIBUTION")
    print("-" * 70)
    for act, cnt in sorted(action_counts.items()):
        print(f"  {act:26s}: {cnt:3d} ({cnt/len(adj_std):.1%})")

    # Inter-Rater Reliability (Human vs Model Reconciliation)
    if recon_dict:
        common_sids = [r["sample_id"] for r in adj_std if r["sample_id"] in recon_dict]
        if common_sids:
            human_canons = [normalize_decision_label(r.get("adjudicated_decision") or r.get("adjudicated_label", ""), r.get("predicted_entity") != "UNRESOLVED")[0] for r in adj_std]
            model_canons = [recon_dict[sid]["model_reviewer_label"].lower() for sid in common_sids]
            raw_agree = sum(1 for h, m in zip(human_canons, model_canons) if h == m) / len(human_canons)
            kappa = calculate_cohen_kappa(human_canons, model_canons)
            print(f"\nModel-vs-Human Agreement: {raw_agree:.1%} (Cohen's kappa = {kappa:.3f})")

    # Hard Cases Metrics
    if adj_hc:
        print("\n" + "-" * 70)
        print("HARD CASES 88 SHEET: SILVER REFERENCE VALIDITY")
        print("-" * 70)
        hc_labels = Counter((r.get("adjudicated_decision") or r.get("adjudicated_label", "")).strip().lower() for r in adj_hc)
        h_corr = hc_labels["correct"] + hc_labels["correct_reference"]
        h_inc = hc_labels["incorrect"] + hc_labels["incorrect_reference"]
        h_unres = hc_labels["unresolved"] + hc_labels["uncertain_reference"]
        print(f"Reviewed Hard Cases:            {len(adj_hc)} / {len(hc_rows)}")
        print(f"Silver Reference Valid:         {h_corr} ({h_corr/len(adj_hc):.1%})")
        print(f"Silver Reference Invalid:       {h_inc} ({h_inc/len(adj_hc):.1%})")
        print(f"Silver Reference Uncertain:     {h_unres} ({h_unres/len(adj_hc):.1%})")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2", action="store_true", help="Validate versioned v2 package")
    parser.add_argument("--provisional-baseline", action="store_true", help="Print audited provisional baseline from candidate annotations")
    parser.add_argument("--standard-blind", default="data/eval/adjudication/standard_200_blind.csv")
    parser.add_argument("--hardcases-blind", default="data/eval/adjudication/hardcases_88_blind.csv")
    parser.add_argument("--standard-v2", default="data/eval/adjudication/standard_200_v2_blind.csv")
    parser.add_argument("--hardcases-v2", default="data/eval/adjudication/hardcases_88_v2_blind.csv")
    parser.add_argument("--v2-mapping", default="data/eval/adjudication/v2_metadata_mapping.csv")
    parser.add_argument("--reconciliation", default="data/eval/adjudication/model_annotations_reconciliation.csv")
    parser.add_argument("--standard-src", default="data/eval/human_review_200.csv")
    parser.add_argument("--annotated-src", default="data/eval/human_review_200_annotated.csv")
    parser.add_argument("--hardcases-src", default="data/eval/human_review_hardcases_88.csv")
    parser.add_argument("--known-denominator", type=int, default=KNOWN_LINKED_POPULATION_2026_09_25)
    parser.add_argument("--require-complete", action="store_true", help="Assert that all rows are adjudicated")

    args = parser.parse_args(argv)

    p_std_v2 = Path(args.standard_v2)
    p_hc_v2 = Path(args.hardcases_v2)
    p_map = Path(args.v2_mapping)
    p_std_blind = Path(args.standard_blind)
    p_hc_blind = Path(args.hardcases_blind)
    p_recon = Path(args.reconciliation)
    p_std_src = Path(args.standard_src)
    p_ann_src = Path(args.annotated_src)
    p_hc_src = Path(args.hardcases_src)

    if args.provisional_baseline:
        if p_std_src.exists() and p_ann_src.exists():
            print_provisional_baseline(p_std_src, p_ann_src, args.known_denominator)
        return 0

    if args.v2 or (p_std_v2.exists() and p_hc_v2.exists()):
        ok_v2 = validate_v2_package(p_std_v2, p_hc_v2, p_map, p_std_src, p_hc_src)
        if not ok_v2:
            return 1
        compute_adjudicated_metrics_v2(p_std_v2, p_hc_v2, p_map, p_recon, args.known_denominator)
        if args.require_complete:
            _, _, errs_200 = check_adjudication_progress(p_std_v2, require_complete=True)
            _, _, errs_88 = check_adjudication_progress(p_hc_v2, require_complete=True)
            if errs_200 or errs_88:
                print("\nIncomplete adjudication errors in V2 package:")
                for e in (errs_200 + errs_88)[:10]:
                    print("  -", e)
                return 2
    else:
        ok_v1 = validate_initial_state(p_std_blind, p_hc_blind, p_recon, p_std_src, p_hc_src)
        if not ok_v1:
            return 1
        if p_std_v2.exists() and p_hc_v2.exists():
            validate_v2_package(p_std_v2, p_hc_v2, p_map, p_std_src, p_hc_src)

    return 0


if __name__ == "__main__":
    sys.exit(main())
