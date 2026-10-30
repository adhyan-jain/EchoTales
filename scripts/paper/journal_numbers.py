"""Every number the journal manuscript reports, recomputed from stored result files (journal Revision 1).

Why this exists: the revision's "cross-table consistency checks" found pooled figures that could not be traced to
their aggregation (+26.0 against per-dataset +35.2/+18.2/+16.7), denominators that drifted between sections (23/289
against 41/685), and two different metrics merged into one range (18.5% judge rule against 24.6% text rule). The
old course document hard-coded the pipeline-audit numbers as literals; one of them ("about 50% more persona-stage
time") no longer matched the stored summary (6.49 s to 13.83 s). This script reads only stored JSON, names every
value with its source and denominator, writes docs/paper/journal/numbers_manifest.json, and with --check confirms
each formatted value appears in the manuscript, so a number cannot silently drift from its source again.

Run: python scripts/paper/journal_numbers.py [--check docs/paper/journal/main.tex]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

C = Path("data/eval/chimera")
PA = Path("data/eval/prefix_audit")
OUT = Path("docs/paper/journal/numbers_manifest.json")


def J(p):
    return json.loads(Path(p).read_text())


def pts(x, d=1):
    return f"{100 * x:+.{d}f}"


def pc(x, d=1):
    return f"{100 * x:.{d}f}"


def ci(lo, hi, signed=True):
    f = pts if signed else pc
    return f"[{f(lo)}, {f(hi)}]"


N: dict[str, dict] = {}


def put(key, value, source, note=""):
    N[key] = dict(value=value, source=source, note=note)


def build():
    # ---------------------------------------------------------------- exploratory memory study
    fp = J(C / "pd_final_pooled.json")
    adv = J(C / "pd_adversarial_checks.json")
    lu, vl = fp["luna_only"], fp["valid_pool"]
    for ds in ("v2", "v3", "v6", "all_v2_v3_v6"):
        put(f"ref_gap_{ds}", pts(lu[ds]["gap_A_minus_B"]), "pd_final_pooled.json luna_only",
            "reference model, item-pooled over pre-reveal items, event-cluster bootstrap")
        put(f"ref_ci_{ds}", ci(*lu[ds]["ci"]), "pd_final_pooled.json luna_only")
        put(f"pool_gap_{ds}", pts(vl[ds]["gap_A_minus_B"]), "pd_final_pooled.json valid_pool")
        put(f"pool_ci_{ds}", ci(*vl[ds]["ci"]), "pd_final_pooled.json valid_pool")
    put("ref_events_pos_neg", f"{lu['all_v2_v3_v6']['events_positive']}/{lu['all_v2_v3_v6']['events_negative']}", "pd_final_pooled.json")
    put("pool_sign_p", f"{vl['all_v2_v3_v6']['sign_p']:.2f}", "pd_final_pooled.json")
    put("pool_v6_pos_neg", f"{vl['v6']['events_positive']}/{vl['v6']['events_negative']}", "pd_final_pooled.json")
    # The aggregation the reviewer asked about: item-pooled, so v2's larger per-event item count weighs more.
    items = {ds: adv[f"pd_{ds}"]["per_model_cluster"]["gpt-5.6-luna"]["items"] for ds in ("v2", "v3")}
    items["v6"] = sum(t["kind"] == "pre" for t in J(C / "pd_v6/run_gpt-5.6-luna.json")["truth"].values())
    w = sum(items[d] * lu[d]["gap_A_minus_B"] for d in ("v2", "v3", "v6")) / sum(items.values())
    put("pre_items_by_dataset", f"{items['v2']}/{items['v3']}/{items['v6']}", "pd_adversarial_checks.json, pd_v6 run truth")
    put("ref_gap_reconstructed", pts(w), "weighted by pre-reveal items", "equals ref_gap_all_v2_v3_v6 to 0.1 point")
    assert abs(w - lu["all_v2_v3_v6"]["gap_A_minus_B"]) < 0.0015, (w, lu["all_v2_v3_v6"])
    # Per-model cells use the same estimator, resamples and seed as the pooled rows (pd_final_pooled.stat). The course
    # report mixed pd_adversarial_checks.json (a different bootstrap run) into its per-model table, so the reference
    # model's v2 interval read [+20.2, +50.7] in the table and [+20.2, +50.0] in the figure.
    sys.path.insert(0, "scripts/chimera")
    import pd_final_pooled as FP
    for m in ("gpt-5.6-luna", "gemma2:9b", "llama3.1:8b", "mistral:7b-instruct", "phi4-mini:latest", "qwen2.5:7b"):
        cells = []
        for ds, runs in (("v2", FP.V2), ("v3", FP.V3), ("v6", FP.V6)):
            st = FP.stat(FP.rows(runs[m], FP.b3_source(ds, m, runs[m])))
            cells.append(f"{pts(st['gap_A_minus_B'])} {ci(*st['ci'])}")
        put(f"tab_explor_{m}", cells, "pd_final_pooled.stat per model and dataset (item-pooled, event bootstrap, seed 20261019)")

    # ---------------------------------------------------------------- cue-preserving control and familiarity
    v5 = J(C / "pd_v5/analysis.json")["pools"]["G2_valid"]
    put("b3_events", str(v5["events"]), "pd_v5/analysis.json pools.G2_valid")
    put("b3_gap_AB", f"{pts(v5['gap_A_minus_B'])} {ci(*v5['gap_A_minus_B_ci'])}", "pd_v5/analysis.json")
    put("b3_gap_AB3", f"{pts(v5['gap_A_minus_B3'])} {ci(*v5['gap_A_minus_B3_ci'])}", "pd_v5/analysis.json")
    put("b3_recovered", f"{v5['recovered_fraction']:+.2f} [{v5['recovered_fraction_ci'][0]:+.2f}, {v5['recovered_fraction_ci'][1]:+.2f}]",
        "pd_v5/analysis.json")
    dose = J(C / "pd_dose_response.json")
    dl, dr = dose["valid_local_pool_gap_vs_local_recognition"], dose["luna_gap_vs_local_recognition"]
    put("dose_local", f"{dl['spearman']:+.2f}, p = {dl['perm_p']:.5f}", "pd_dose_response.json")
    put("dose_ref", f"{dr['spearman']:+.2f}, p = {dr['perm_p']:.3f}", "pd_dose_response.json")
    put("dose_group_n", "/".join(str(dl["events_per_count"][str(k)]) for k in range(6)), "pd_dose_response.json events_per_count")

    # ---------------------------------------------------------------- confirmatory study
    cf = J(C / "confirm/main/analysis.json")
    put("conf_events", f"{cf['n_events']}/{cf['n_test']}/{cf['n_primary_test']}", "confirm/main/analysis.json", "all/test/primary")
    for m in ("mistral24", "olmo32b", "qwen32b"):
        r = cf["per_model"][m]["primary_test"]
        put(f"conf_{m}", f"{pts(r['gap_A_minus_B'])} {ci(*r['ci'])}", "confirm/main/analysis.json per_model.primary_test",
            "event-weighted mean of per-event gaps")
        put(f"conf_{m}_closed", str(cf["per_model"][m]["closed_orig_correct"]), "confirm/main/analysis.json closed_orig_correct")
    h1, h2, h3, p1, h5 = cf["H1"], cf["H2"], cf["H3"], cf["P1"], cf["H5"]["pooled"]
    put("H1", f"{pts(h1['pooled'])} {ci(*h1['ci'])}", "confirm/main/analysis.json H1", "DerSimonian-Laird, Hartung-Knapp, 3 models")
    put("H2", f"{pts(h2['pooled_A_minus_B3'])} {ci(*h2['ci'])}", "confirm/main/analysis.json H2")
    put("H3", f"{h3['spearman']:+.2f}", "confirm/main/analysis.json H3")
    put("H3_holm", f"{cf['holm_adjusted_p']['H3']:.3f}", "confirm/main/analysis.json holm_adjusted_p")
    put("P1", f"{pts(p1['difference'])} {ci(*p1['ci'])}", "confirm/main/analysis.json P1")
    put("P1_mdd", pc(p1["minimum_detectable_difference_80pct_power"]), "confirm/main/analysis.json P1")
    put("P1_p", f"{p1['p_one_sided']:.3f}", "confirm/main/analysis.json P1")
    put("H5_premature", f"{pc(h5['pre_O'])}% to {pc(h5['pre_P2'])}%", "confirm/main/analysis.json H5.pooled")
    put("H5_post_cost", pts(h5["utility_post_P2_minus_O"]["point"]), "confirm/main/analysis.json H5.pooled")
    put("H5_ctrl_cost", pts(h5["utility_ctrl_P2_minus_O"]["point"]), "confirm/main/analysis.json H5.pooled")
    e1 = J(C / "confirm/main/e1_qwen32b.json")
    n_items, n_closed, n_m2 = len(e1["real"]), len(e1["closed"]), len(e1["m2"])
    arms = len(next(iter(e1["real"].values())))
    assert n_items * arms + 3 * n_closed + 3 * n_m2 == e1["calls"], e1["calls"]
    put("conf_calls", f"{e1['calls']:,} = {n_items} x {arms} + {n_closed} x 3 + {n_m2} x 3", "confirm/main/e1_qwen32b.json")

    # ---------------------------------------------------------------- pipeline audit
    s = J(PA / "summary.json")["pooled"]
    put("pa_orig", f"{s['off']['with_divergence']}/{s['off']['character_cuts']}", "prefix_audit/summary.json pooled.off")
    put("pa_orig_wilson", ci(*s["off"]["wilson"], signed=False), "prefix_audit/summary.json")
    put("pa_ehv", f"{s['on']['with_divergence']}/{s['on']['character_cuts']}", "prefix_audit/summary.json pooled.on")
    put("pa_hide", f"{s['hide_only']['diverge']}/{s['hide_only']['n']}", "prefix_audit/summary.json hide_only")
    put("pa_hide_destroyed", str(s["hide_only"]["hides_correct_known"]), "prefix_audit/summary.json hide_only")
    put("pa_certified_safe", f"{s['screen_yardsticks']['certified_safe']}/{s['screen_yardsticks']['n']}", "prefix_audit/summary.json")
    co = s["cost"]
    put("pa_time", f"{co['off']['persona_stage_seconds']:.1f} s to {co['on']['persona_stage_seconds']:.1f} s",
        "prefix_audit/summary.json cost", "single wall-clock run; the course report's 'about 50%' used an older 9.1 s timing")
    put("pa_rows", f"{co['off']['attribute_rows']:,} to {co['on']['attribute_rows']:,}", "prefix_audit/summary.json cost")
    put("pa_unknown", f"{pc(co['off']['unknown_served'] / co['off']['n'])}% to {pc(co['on']['unknown_served'] / co['on']['n'])}%",
        "prefix_audit/summary.json cost")
    lp = J(PA / "labels_summary_permissive.json")
    put("pa_pooled", f"{lp['diverging_pairs']}/{lp['character_cuts']}", "prefix_audit/labels_summary_permissive.json")
    put("pa_premature_strict", f"{lp['luna_strict']['premature_rate']['n']}/{lp['character_cuts']} ({pc(lp['luna_strict']['premature_rate']['share'])}%)",
        "labels_summary_permissive.json luna_strict")
    put("pa_premature_permissive", f"{pc(lp['luna_permissive']['premature_rate']['share'])}%", "labels_summary_permissive.json")
    l2 = J(PA / "labels_summary_v2.json")
    ao = l2["Aprime"]["original"]
    put("pa_ann2_orig", f"{ao['premature_rate']['n']}/289 ({pc(ao['premature_rate']['share'])}%)", "labels_summary_v2.json Aprime.original")
    put("pa_kappa", f"{l2['Dprime_truth']['kappa_4class']:.2f} on {l2['Dprime_truth']['characters_labelled_by_both']}", "labels_summary_v2.json Dprime_truth")
    b = l2["Bprime"]["all"]
    put("pa_frontier", f"{b['status_quo']['cuts']} cuts, {b['characters']} characters; status quo {b['status_quo']['correct']['n']}/{b['status_quo']['withheld']['n']}/"
        f"{b['status_quo']['wrong']['n']}; versioned {b['repaired']['correct']['n']}/{b['repaired']['withheld']['n']}/{b['repaired']['wrong']['n']}",
        "labels_summary_v2.json Bprime.all")
    an = J(PA / "anchored_v2_summary.json")["confirmatory_web_novels"]
    put("pa_anchor", f"{an['pairs']} pairs: {an['status_quo']['correct']}/{an['plain']['correct']}/{an['setting_1_0.8']['v1']['correct']}",
        "anchored_v2_summary.json")
    # 304 cuts were compared; 289 of them are the truncate-and-rebuild cuts. The course report's "47" is the dependent
    # count on those 289 (23 that also diverge + 24 that do not); 4 more dependent cuts have no truncation match.
    cp = J(PA / "counterfactual_suffix.json")["pooled"]["status_quo"]
    matched = cp["diverge_and_flip"] + cp["flip_no_diverge"]
    put("pa_cf", f"{matched}/289 ({pc(matched / 289)}%)", "counterfactual_suffix.json pooled.status_quo",
        f"{cp['diverge_and_flip']} also diverge, {cp['flip_no_diverge']} do not; {cp['flip_unmatched']} more among "
        f"{cp['compared'] - 289} unmatched cuts ({cp['flips']} of {cp['compared']} compared)")
    put("pa_cf_compared", f"{cp['flips']}/{cp['compared']}", "counterfactual_suffix.json pooled.status_quo")

    # ---------------------------------------------------------------- cards, canaries, selection
    rf = J(C / "rf_e2e/analysis.json")
    A, B = rf["A_primary_EXPLICIT_IMPLIED"], rf["B_EXPLICIT_IMPLIED"]
    put("card_W_text", f"{pc(A['pooled']['rates']['W_ren'])}% of {A['events']}", "rf_e2e/analysis.json rule A (text)")
    put("card_W_judge", f"{pc(B['pooled']['rates']['W_ren'])}% of {B['events']}", "rf_e2e/analysis.json rule B (judge)")
    put("card_P_text", pc(A["pooled"]["rates"]["P_ren"]), "rf_e2e/analysis.json")
    put("card_P_judge", pc(B["pooled"]["rates"]["P_ren"]), "rf_e2e/analysis.json")
    put("card_input_text", f"{pts(A['pooled']['RF1_input_channel']['estimate'])} {ci(*A['pooled']['RF1_input_channel']['ci'])}", "rf_e2e/analysis.json")
    put("card_input_judge", f"{pts(B['pooled']['RF1_input_channel']['estimate'])} {ci(*B['pooled']['RF1_input_channel']['ci'])}", "rf_e2e/analysis.json")
    put("card_memory_judge", pts(B["pooled"]["RF3_memory_channel"]["estimate"]), "rf_e2e/analysis.json")
    rob = rf["robust"]
    put("card_nospoil", f"{pc(rob['ruleB']['rates']['W_ren_nospoil'])}% judge, {pc(rob['ruleA']['rates']['W_ren_nospoil'])}% text", "rf_e2e/analysis.json robust")
    if (rf.get("larger") or {}).get("B_EXPLICIT_IMPLIED"):
        L = rf["larger"]["B_EXPLICIT_IMPLIED"]["pooled"]
        put("card_larger", f"{pc(L['rates']['W_ren'])}% vs {pc(L['rates']['P_ren'])}%", "rf_e2e/analysis.json larger")
    jv = J(C / "rf_e2e/posthoc_judge_validity_and_exposure.json")["judge_vs_text_rule"]
    put("judge_validity", f"sens {pc(jv['sensitivity'])}%, FP {pc(1 - jv['specificity'])}%, kappa {jv['kappa']:.2f}, {jv['labels']} labels",
        "rf_e2e/posthoc_judge_validity_and_exposure.json")
    can = J(C / "rf_e2e/canary_analysis.json")
    for k, lab in (("H12_1_W_card", "canary_W"), ("H12_2_long_context", "canary_L")):
        put(lab, f"{pc(can[k]['estimate'])}% {ci(*can[k]['ci'], signed=False)} of {can[k]['events']}; control {pc(can[k]['rate_y'])}%",
            "rf_e2e/canary_analysis.json")
    sel = J(C / "rf_e2e/selection_analysis.json")["H13_1_resolver_merged"]
    put("selection", f"{pc(sel['M_rate'])}% vs {pc(sel['P_rate'])}%; diff {pts(sel['estimate'])} {ci(*sel['ci'])}; {sel['events']} events",
        "rf_e2e/selection_analysis.json", "CI is for the paired event-level difference")
    put("selection_per_model", " / ".join(pc(sel["per_model"][m]["M_rate"]) for m in ("llama3.1:8b", "mistral:7b-instruct", "qwen2.5:7b")),
        "rf_e2e/selection_analysis.json")
    for k, lab in (("H12_1_W_card", "canary_W_per_model"), ("H12_2_long_context", "canary_L_per_model")):
        put(lab, " / ".join(pc(can[k]["per_model"][m]["rate_x"]) for m in ("llama3.1:8b", "mistral:7b-instruct", "qwen2.5:7b")),
            "rf_e2e/canary_analysis.json")
    put("canary_fact", f"{pc(can['secondary']['W_fact']['estimate'])}% cards, {pc(can['secondary']['L_fact']['estimate'])}% long context",
        "rf_e2e/canary_analysis.json secondary")
    ja = rf["judge_agreement"]
    put("judge_agreement", f"{pc(ja['identical'])}% of {ja['labels']}, kappa {ja['kappa']:.2f}", "rf_e2e/analysis.json judge_agreement")
    rbB = rf["robust"]["ruleB"]["contrasts"]["nospoil_vs_versioned_ren"]
    rbA = rf["robust"]["ruleA"]["contrasts"]["nospoil_vs_versioned_ren"]
    put("card_nospoil_diff", f"{pts(rbB['estimate'])} {ci(*rbB['ci'])}; text {ci(*rbA['ci'])}", "rf_e2e/analysis.json robust")
    for key, lab in (("A_primary_EXPLICIT_IMPLIED", "text"), ("B_EXPLICIT_IMPLIED", "judge")):
        for stratum, src in (("small", rf), ("large", rf.get("larger") or {})):
            q = (src.get(key) or {}).get("pooled")
            if q:
                r = q["rates"]
                put(f"cards_{lab}_{stratum}", f"{pc(r['W_orig'])}/{pc(r['W_ren'])}/{pc(r['P_orig'])}/{pc(r['P_ren'])}; "
                    f"{pts(q['RF1_input_channel']['estimate'])} {ci(*q['RF1_input_channel']['ci'])}", "rf_e2e/analysis.json")

    # ---------------------------------------------------------------- further values quoted in the text
    put("label_audit_explicit", f"{pts(adv['label_audit_sensitivity']['gpt-5.6-luna|explicit_only|luna_only']['pooled_gap'])} "
        f"{ci(*adv['label_audit_sensitivity']['gpt-5.6-luna|explicit_only|luna_only']['event_cluster_ci95'])}",
        "pd_adversarial_checks.json label_audit_sensitivity (20 audited-EXPLICIT events)")
    put("H5_post_ci", ci(*h5["utility_post_P2_minus_O"]["ci"]), "confirm/main/analysis.json H5.pooled")
    put("H3_events", f"{h3['events']} events, {h3['books']} books", "confirm/main/analysis.json H3")
    occ = J(C / "confirm/main/olmo_corpus_check.json")
    put("olmo_corpus", f"{occ['books_queried']} books; Spearman {occ['spearman']:+.2f}, p = {occ['perm_p_two_sided']:.2f}", "confirm/main/olmo_corpus_check.json")
    put("recap_outputs", str(cf["E5"]["per_model"]["qwen32b"]["O"]["outputs"] * 3), "confirm/main/analysis.json E5 (48 per model x 3)")
    pdi = J(C / "posthoc_descriptive_identity.json")
    ex = pdi["confirmatory_H1"]["excluding_descriptive"]
    put("H1_excl_descriptive", f"{pts(ex['H1_pooled'])} {ci(*ex['ci'])}", "posthoc_descriptive_identity.json")
    sx = pdi["selection_leak"]["excluding_descriptive"]
    put("selection_excl_descriptive", f"{pts(sx['estimate'])} {ci(*sx['ci'])} over {sx['events']}", "posthoc_descriptive_identity.json")
    put("descriptive_counts", f"{pdi['descriptive_count_all']}; primary {pdi['descriptive_count_primary']}", "posthoc_descriptive_identity.json")
    groups = J("docs/paper/journal/figures/fig6_dose_groups.json")
    put("dose_groups_pool", "; ".join(f"{pts(g['mean'])} {ci(*g['ci'])} n {g['events']}" for g in groups["Valid local pool"]),
        "figures/fig6_dose_groups.json (make_journal_figures.py)")
    v5m = J(C / "pd_v5/analysis.json")["per_model"]["qwen2.5:7b"]["pd_v2"]
    put("qwen_ctrl_acc_v2", f"{pc(v5m['ctrl_acc_A'])}/{pc(v5m['ctrl_acc_B'])}/{pc(v5m['ctrl_acc_B3'])}", "pd_v5/analysis.json per_model")
    v5all = J(C / "pd_v5/analysis.json")["pools"]["all_models"]
    put("b3_all_models", f"{pts(v5all['gap_A_minus_B'])} {ci(*v5all['gap_A_minus_B_ci'])}; {pts(v5all['gap_A_minus_B3'])} "
        f"{ci(*v5all['gap_A_minus_B3_ci'])}; {v5all['recovered_fraction']:+.2f}", "pd_v5/analysis.json pools.all_models")
    syn = []
    for f in sorted((PA / "synthetic").glob("syn_*.json")):
        t = J(f)["totals"]["status_quo"]
        syn.append(t["diverge"] / t["pairs"])
    put("synthetic_range", f"{pc(min(syn))} to {pc(max(syn))}", "prefix_audit/synthetic/syn_*.json totals.status_quo")
    prem = [J(PA / f"synthetic/syn_pa{d}_pd0.json")["totals"]["status_quo"]["diverge_premature"] for d in (10, 35, 70)]
    put("synthetic_premature", "/".join(map(str, prem)), "prefix_audit/synthetic/syn_pa{10,35,70}_pd0.json")
    gate = both = disc = 0
    for n in ("lord-of-the-mysteries", "omniscient-readers-viewpoint", "reverend-insanity"):
        sm = J(PA / f"llm_model_{n}.json")["summary"]
        gate += sm["classes"].get("gate", 0)
        both += sm["both_llm_pairs"]
        disc += sm["discrete_full_vs_prefix"]
    put("model_path", f"{disc} of {both} pairs differ; gate {gate} of 296", "prefix_audit/llm_model_*.json")
    res_tot = res_dis = 0
    for n in ("reverend-insanity", "lord-of-the-mysteries", "omniscient-readers-viewpoint"):
        for v in J(C / f"eng_probe_E1_{n}.json")["by_k"].values():
            res_tot += v["prefix_vs_F0"]["mentions_leq_k"]
            res_dis += v["prefix_vs_F0"]["disagree"]
    put("resolver", f"{res_dis} of {res_tot:,}", "eng_probe_E1_*.json by_k.*.prefix_vs_F0")
    # ---------------------------------------------------------------- human reveal validation (scripts/review)
    hv = J("data/eval/validation/reveal_human_v1.json")
    el, ag = hv["event_level"], hv["agreement_fleiss"]

    def wl(w):
        return f"{w['k']}/{w['n']} ({pc(w['rate'])}% [{pc(w['ci'][0])}, {pc(w['ci'][1])}])"

    put("human_explicit_both", wl(el["reveal_explicit_both"]), "validation/reveal_human_v1.json")
    ac = hv["model_audit_agreement"]["explicit_confirmed"]
    put("human_audit_confirmed", f"{ac['k']} of {ac['n']}, lower {pc(ac['ci'][0])}", "validation/reveal_human_v1.json")
    put("human_confident", f"{el['inferable_confident_any']['k']}/{el['inferable_confident_any']['n']}, upper {pc(el['inferable_confident_any']['ci'][1])}",
        "validation/reveal_human_v1.json")
    put("human_suspect", f"{el['inferable_suspect_or_more_any']['k']} any, {el['inferable_suspect_or_more_both']['k']} both",
        "validation/reveal_human_v1.json")
    put("human_reminder_any", str(el["reminder_any"]["k"]), "validation/reveal_human_v1.json")
    put("human_invalid_any", f"{hv['by_track']['confirmatory']['invalid_any']['k']} of {hv['by_track']['confirmatory']['events']} confirmatory; "
        f"{hv['by_track']['exploratory']['invalid_any']['k']} exploratory", "validation/reveal_human_v1.json")
    put("human_agreement", f"q1 raw {pc(ag['q1']['raw_agreement'])} kappa {ag['q1']['kappa']:.2f}; q3 raw {pc(ag['q3']['raw_agreement'])} "
        f"kappa {ag['q3']['kappa']:.2f}; q4 raw {pc(ag['q4']['raw_agreement'])}; q2 raw {pc(ag['q2']['raw_agreement'])}",
        "validation/reveal_human_v1.json")
    pk = hv["prior_knowledge"]["labels_knowing_plot"]
    put("human_knew_plot", f"{pk['k']} of {pk['n']}", "validation/reveal_human_v1.json")
    gs = hv["gap_sensitivity"]
    r = gs["validated_subset"]["reference_model_exploratory"]
    put("human_ref_gap", f"{pts(r['gap_A_minus_B'])} {ci(*r['ci'])}", "validation/reveal_human_v1.json gap_sensitivity")
    for lab, key in (("human_conf_validated", "validated_subset"), ("human_conf_minus_flagged", "validated_subset_minus_flagged")):
        h = gs[key]["confirmatory_H1_pooled"]
        put(lab, f"{pts(h['pooled'])} {ci(*h['ci'])}", "validation/reveal_human_v1.json gap_sensitivity")

    dh = J(Path("data/eval/validation/disclosure_human_v1.json"))
    src = "validation/disclosure_human_v1.json"
    put("dh_q1_agree", f"{dh['human_human']['q1']['agree']['k']}/{dh['human_human']['q1']['agree']['n']} ({pc(dh['human_human']['q1']['agree']['pct'] / 100)}%), "
        f"kappa {dh['human_human']['q1']['fleiss_kappa']:.2f}", src)
    sb = dh["s1_not_supported_by_rule"]
    put("dh_s1_by_rule", f"both {sb['both_annotators']['k']} of {sb['both_annotators']['n']}; at least one {sb['at_least_one_annotator']['k']}; adjudicated {sb['adjudicated']['k']}", src)
    sv = dh["served_value"]
    put("dh_served_not_supported", f"{sv['not_supported']['k']} of {sv['not_supported']['n']} ({sv['not_supported']['pct']}%)", src)
    put("dh_vs_models", "; ".join(f"{n} {m['agree']['k']}/{m['agree']['n']} kappa {m['cohen_kappa']:.2f}" for n, m in dh["human_vs_model_q1"].items()), src)
    put("dh_vs_models_agreed_only", "; ".join(f"{n} {m['agree']['k']}/{m['agree']['n']}" for n, m in dh["human_vs_model_q1_agreed_pairs_only"].items()), src)
    put("dh_self_consistency", f"gender {dh['self_consistency']['q1']['k']}/{dh['self_consistency']['q1']['n']}; support {dh['self_consistency']['q3']['k']}/{dh['self_consistency']['q3']['n']}", src)

    eng = J(PA / "anchored_v2_summary.json")["development_english_originals"]
    v1 = eng["setting_1_0.8"]["v1"]
    put("anchor_english_wrong", f"{pc(v1['wrong'] / v1['cuts'])}% ({v1['wrong']} of {v1['cuts']})", "anchored_v2_summary.json")


# Values shown only in a figure or deliberately left to the supplement; everything else must be quoted in the text.
NUM = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"  # commas only as thousands separators
NOT_QUOTED = {"pool_gap_v2", "pool_ci_v2", "pool_gap_v3", "pool_ci_v3", "pa_certified_safe", "pa_cf_compared",
              "pre_items_by_dataset", "ref_gap_reconstructed", "conf_mistral24_closed", "conf_olmo32b_closed"}


def check(tex_path: str):
    """Every number inside each manifest value must appear in the manuscript as a number.

    Values are compared number by number rather than as strings, because the prose writes "23 of 289" where the
    manifest writes "23/289"; a decimal keeps its sign only where the manifest gives one (a gap is "+26.0", a rate is
    "18.5"), so a sign error in the text is still caught."""
    tex = Path(tex_path).read_text()
    flat = re.sub(r"\$|\\,|\\;|\{|\}|~|\\mathrm|\\text|\\%", " ", tex).replace("--", "-").replace("−", "-")
    present = set(re.findall(NUM, flat))
    present |= {t.lstrip("+") for t in present}
    missing = []
    for k, v in N.items():
        if k in NOT_QUOTED:
            continue
        for x in (v["value"] if isinstance(v["value"], list) else [v["value"]]):
            for tok in re.findall(NUM, x):
                if tok not in present and tok.lstrip("+-") not in present:
                    missing.append((k, tok, x))
    print(f"\ncheck {tex_path}: {len(missing)} numbers not found")
    for k, tok, x in missing:
        print(f"  {k}: {tok}   (in '{x}')")
    return missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", help="manuscript .tex to verify against")
    a = ap.parse_args()
    build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(N, indent=1, ensure_ascii=False))
    for k, v in N.items():
        print(f"{k:26s} {v['value']}")
    if a.check:
        return 1 if check(a.check) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
