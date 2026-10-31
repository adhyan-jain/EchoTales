"""Score the human Prefix Check labels (VALIDATION_PROTOCOL.md, Layer 3).

Why this exists: the paper reports pipeline-disclosure rates that were first judged by model annotators. This script says
how far two humans per case agree with each other, how far the adjudicated human label agrees with each model annotator,
and how often the served value was right (matches the book) yet not backed by the passages up to the cut.

Design notes the numbers depend on:
  * 48 sampled cases are the analysis set; the 4 repeats (R001-R004) only measure self-consistency.
  * Each case has two of the three annotators in rotation, so agreement is Fleiss' kappa with two raters per case, not
    Cohen's kappa (the two raters are not the same people across cases), as in score_reveal_validation.py.
  * Adjudication (revised 2026-10-31): per question, where the pair agreed that is the label; where they split and the
    first author was one of the pair, the other annotator's label stands; where two non-first-author annotators split, the
    case is resolved by a third human reader if adjudication_third.json exists, else provisionally by the model
    passages-only reading, else left out of the denominators. The first author's own labels were partly name-based: they
    never answered "undetermined" (0 of 32 primary cases, against 7 and 8 of 32 for the other two) and all 7 of their splits
    with a partner were a gender against "undetermined", while the guideline says a name is not a signal. The earlier rule (first
    author rules on splits, and overrode one pair that agreed on "undetermined") is kept as `first_author_adjudication`
    so both are reported. book_truth is the character's gender in the novel; q1 is what the shown passages establish.

Inputs : scripts/review/disclosure_validation_app/cases.json (gitignored), data/eval/validation/pipeline_disclosure_sample*.json,
         data/eval/validation/disclosure_labels/{labels_*.json, adjudicated.json}
Output : data/eval/validation/disclosure_human_v1.json
Run    : python scripts/review/score_disclosure_validation.py
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

VAL = Path("data/eval/validation")
LAB = VAL / "disclosure_labels"
CASES = Path("scripts/review/disclosure_validation_app/cases.json")
OUT = VAL / "disclosure_human_v1.json"
CATS = {"q1": ["male", "female", "undetermined"], "q2": ["clear", "suspect", "none"],
        "q3": ["supported", "unsupported", "contradicted", "settled", "not_settled"], "q4": ["yes", "no"]}


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h) * 100, 1), round(min(1.0, c + h) * 100, 1)]


def pct(k: int, n: int):
    return dict(k=k, n=n, pct=round(100 * k / n, 1) if n else None, wilson95=wilson(k, n))


def fleiss2(pairs: list[tuple[str, str]], cats: list[str]):
    """Fleiss' kappa for exactly two raters per item."""
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    tot = Counter(x for p in pairs for x in p)
    pe = sum((tot[c] / (2 * n)) ** 2 for c in cats)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def cohen(pairs: list[tuple[str, str]], cats: list[str]):
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in cats) / n ** 2
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def main() -> None:
    cases = {c["case"]: c for c in json.load(open(CASES))["cases"]}
    man = {c["case"]: c for c in json.load(open(VAL / "pipeline_disclosure_sample.json"))["cases"]}
    key = json.load(open(VAL / "pipeline_disclosure_sample_key.json"))
    lab = {n: json.load(open(LAB / f"labels_{n}.json"))["labels"] for n in ("Adhyan", "Aryan", "Atharva")}
    adj_first_author = json.load(open(LAB / "adjudicated.json"))["adjudicated"]
    prim = [k for k in cases if not k.startswith("R")]
    fb_files = {n: json.load(open(LAB / n))["labels"] for n in ("adjudication_third.json", "adjudication_model_passages_only.json")
                if (LAB / n).exists()}

    def fallback(k, f):
        for n in ("adjudication_third.json", "adjudication_model_passages_only.json"):  # a human third reader outranks the model
            v = fb_files.get(n, {}).get(k, {}).get(f)
            if v:
                return v, n.removesuffix(".json").removeprefix("adjudication_")
        return None, "unresolved"

    # The first author's labels are the one set that was partly name-based, so on any split they lose to the other annotator.
    adj = {}
    for k in prim:
        a, b = cases[k]["annotators"]
        adj[k] = dict(book_truth=adj_first_author[k]["book_truth"], basis={})
        for f in ("q1", "q3"):
            x, y = lab[a][k].get(f), lab[b][k].get(f)
            if x == y:
                adj[k][f], adj[k]["basis"][f] = x, "agreement"
            elif "Adhyan" in (a, b):
                adj[k][f], adj[k]["basis"][f] = (y if a == "Adhyan" else x), "non_first_author"
            else:
                adj[k][f], adj[k]["basis"][f] = fallback(k, f)
    rep = {k: man[k]["repeat_of"] for k in cases if k.startswith("R")}
    assert len(prim) == 48 and len(rep) == 4, (len(prim), len(rep))

    def pair(k):
        a, b = cases[k]["annotators"]
        return lab[a][k], lab[b][k]

    res: dict = {"n_primary": len(prim), "n_repeats": len(rep)}

    # 1. human-human agreement before any adjudication
    hh = {}
    for q, cats in CATS.items():
        items = []
        for k in prim:
            x, y = pair(k)
            if x.get(q) is None or y.get(q) is None:  # q3/q4 are only asked when a value was served
                continue
            items.append((x[q], y[q]))
        hh[q] = dict(agree=pct(sum(a == b for a, b in items), len(items)), fleiss_kappa=fleiss2(items, cats))
    res["human_human"] = hh
    strat_agree = defaultdict(lambda: [0, 0])
    for k in prim:
        x, y = pair(k)
        s = strat_agree[man[k]["stratum"]]
        s[0] += x["q1"] == y["q1"]
        s[1] += 1
    res["human_human_q1_by_stratum"] = {s: pct(*v) for s, v in sorted(strat_agree.items())}
    res["q1_disagreement_cases"] = sorted(k for k in prim if pair(k)[0]["q1"] != pair(k)[1]["q1"])

    # 2. adjudicated human label against each model annotator
    mod = {}
    for name, f in (("claude_annotator1", "annotator1"), ("luna_strict", "annotator2_strict"), ("luna_permissive", "annotator2_permissive")):
        items = [(adj[k]["q1"], key[k][f]) for k in prim if key[k].get(f) is not None]
        mod[name] = dict(agree=pct(sum(a == b for a, b in items), len(items)), cohen_kappa=cohen(items, CATS["q1"]),
                         confusion={f"{a}->{b}": v for (a, b), v in sorted(Counter(items).items())})
    res["human_vs_model_q1"] = mod

    # 2b. same comparison restricted to cases where both annotators agreed, so no ruling is involved. The adjudicated
    # comparison is lower because rulings turned the models' "undetermined" into a gender where the people had split.
    agreed = {k: pair(k)[0]["q1"] for k in prim if pair(k)[0]["q1"] == pair(k)[1]["q1"]}
    ag_only = {}
    for name, f in (("claude_annotator1", "annotator1"), ("luna_strict", "annotator2_strict"), ("luna_permissive", "annotator2_permissive")):
        items = [(h, key[k][f]) for k, h in agreed.items() if key[k].get(f) is not None]
        ag_only[name] = dict(agree=pct(sum(a == b for a, b in items), len(items)), cohen_kappa=cohen(items, CATS["q1"]))
    res["human_vs_model_q1_agreed_pairs_only"] = ag_only

    # 3. correct versus backed by the passages, on the cases where a value was served
    served = [k for k in prim if cases[k]["served"] in ("male", "female") and adj[k]["q3"] is not None]
    res["unresolved_excluded"] = sorted(k for k in prim if cases[k]["served"] in ("male", "female") and adj[k]["q3"] is None)
    cell = Counter()
    for k in served:
        correct = cases[k]["served"] == adj[k]["book_truth"]
        backed = adj[k]["q3"] == "supported"
        cell[("correct" if correct else "wrong", "supported" if backed else "not_supported")] += 1
    res["served_value"] = dict(n=len(served), cells={f"{a}|{b}": v for (a, b), v in sorted(cell.items())},
                               not_supported=pct(sum(v for (a, b), v in cell.items() if b == "not_supported"), len(served)),
                               correct_but_not_supported=sorted(k for k in served if cases[k]["served"] == adj[k]["book_truth"] and adj[k]["q3"] != "supported"))
    by_s = defaultdict(Counter)
    for k in served:
        by_s[man[k]["stratum"]][adj[k]["q3"]] += 1
    res["q3_by_stratum"] = {s: dict(c) for s, c in sorted(by_s.items())}
    s1 = [k for k in served if man[k]["stratum"] == "S1"]
    res["s1_model_disclosures_confirmed"] = pct(sum(adj[k]["q3"] != "supported" for k in s1), len(s1))
    s2 = [k for k in served if man[k]["stratum"] == "S2"]
    res["s2_model_supported_confirmed"] = pct(sum(adj[k]["q3"] == "supported" for k in s2), len(s2))
    s6 = [k for k in served if man[k]["stratum"] == "S6"]
    res["s6_controls_not_supported"] = pct(sum(adj[k]["q3"] != "supported" for k in s6), len(s6))

    # 3b. sensitivity to the adjudication rule. S1 is where the annotators disagree most (q1 agreement 3 of 10), and the
    # adjudicated label there came from an annotator who had read the books, so the raw pairs are reported too.
    sens = {}
    for st in ("S1", "S2", "S3", "S6"):
        ks = [k for k in served if man[k]["stratum"] == st]
        bad = [sum(x.get("q3") in ("unsupported", "contradicted") for x in pair(k)) for k in ks]
        sens[st] = dict(n=len(ks), both_say_not_supported=sum(b == 2 for b in bad), one_says_not_supported=sum(b == 1 for b in bad),
                        neither=sum(b == 0 for b in bad), adjudicated_not_supported=sum(adj[k]["q3"] != "supported" for k in ks))
    res["q3_sensitivity_by_stratum"] = sens
    res["s1_not_supported_by_rule"] = {r: pct(sum(b >= m for b in [sum(x.get("q3") in ("unsupported", "contradicted") for x in pair(k)) for k in s1]), len(s1))
                                        for r, m in (("both_annotators", 2), ("at_least_one_annotator", 1))}
    res["s1_not_supported_by_rule"]["adjudicated"] = res["s1_model_disclosures_confirmed"]

    # 4. self-consistency on the repeats, per annotator
    sc = []
    for r, o in rep.items():
        for a in cases[r]["annotators"]:
            sc.append(dict(case=o, repeat=r, annotator=a, q1=lab[a][r]["q1"] == lab[a][o]["q1"],
                           q3=lab[a][r].get("q3") == lab[a][o].get("q3")))
    res["self_consistency"] = dict(q1=pct(sum(x["q1"] for x in sc), len(sc)), q3=pct(sum(x["q3"] for x in sc), len(sc)),
                                   inconsistent=[x for x in sc if not (x["q1"] and x["q3"])])
    # 5. alternative adjudications of the 11 cases the first author ruled on. VALIDATION_PROTOCOL.md asked a third author to rule
    # from the passages alone; the first-author rulings are the stand-in. Each optional file below has the shape of the scratch
    # template (case -> q1, q3); its labels replace the first author's on those cases and the adjudicated results are recomputed.
    # adjudication_third.json: a human third author (not yet received). adjudication_model_passages_only.json: MODEL-GENERATED,
    # a coding-assistant session reading only the passages.
    for fname, rkey in (("adjudication_third.json", "third_author"), ("adjudication_model_passages_only.json", "model_passages_only"),
                         ("adjudication_model_llama31_8b.json", "model_llama31_8b"), ("adjudication_model_qwen25_7b.json", "model_qwen25_7b")):
        f = LAB / fname
        if not f.exists():
            continue
        tl = json.load(open(f))["labels"]
        alt = {k: dict(v) for k, v in adj_first_author.items()}  # these probe the first-author rulings, so they start from them
        for k, v in tl.items():
            if v.get("q1"):
                alt[k]["q1"] = v["q1"]
            if v.get("q3"):
                alt[k]["q3"] = v["q3"]
        res[rkey] = dict(
            cases=sorted(k for k, v in tl.items() if v.get("q1")),
            changed_q1=sorted(k for k in tl if tl[k].get("q1") and tl[k]["q1"] != adj[k]["q1"]),
            changed_q3=sorted(k for k in tl if tl[k].get("q3") and tl[k]["q3"] != adj[k].get("q3")),
            s1_not_supported=pct(sum(alt[k]["q3"] != "supported" for k in s1), len(s1)),
            served_not_supported=pct(sum(alt[k]["q3"] != "supported" for k in served), len(served)),
            vs_model={n: dict(agree=pct(sum(alt[k]["q1"] == key[k][f_] for k in prim if key[k].get(f_) is not None),
                                         sum(key[k].get(f_) is not None for k in prim)))
                      for n, f_ in (("claude_annotator1", "annotator1"), ("luna_strict", "annotator2_strict"), ("luna_permissive", "annotator2_permissive"))})
    res["adjudication_basis"] = {f: dict(Counter(adj[k]["basis"][f] for k in prim)) for f in ("q1", "q3")}
    res["changed_by_revision"] = dict(q1=sorted(k for k in prim if adj[k]["q1"] != adj_first_author[k]["q1"]),
                                      q3=sorted(k for k in prim if adj[k]["q3"] != adj_first_author[k].get("q3")))
    # why the first author's labels lose splits: no "undetermined" at all, and every split with a partner had them committing
    # to a gender where the partner declined. Over the 48 primary cases only; repeats are self-consistency data.
    prof = {}
    for n in ("Adhyan", "Aryan", "Atharva"):
        ks = [k for k in prim if n in cases[k]["annotators"]]
        prof[n] = dict(cases=len(ks), undetermined=sum(lab[n][k]["q1"] == "undetermined" for k in ks),
                       knew_plot=sum(lab[n][k].get("q0") == "yes" for k in ks))
    splits = [(k, [x for x in cases[k]["annotators"] if x != "Adhyan"][0]) for k in prim
              if "Adhyan" in cases[k]["annotators"] and pair(k)[0]["q1"] != pair(k)[1]["q1"]]
    res["annotator_profile"] = dict(per_annotator=prof, first_author_splits=len(splits),
                                    first_author_splits_gender_vs_undetermined=sum(
                                        lab["Adhyan"][k]["q1"] in ("male", "female") and lab[o][k]["q1"] == "undetermined" for k, o in splits),
                                    s1_lone_dissent_first_author_supporter=sum(
                                        1 for k in prim if man[k]["stratum"] == "S1" and cases[k]["served"] in ("male", "female")
                                        and sum(x.get("q3") in ("unsupported", "contradicted") for x in pair(k)) == 1
                                        and "Adhyan" in cases[k]["annotators"] and lab["Adhyan"][k].get("q3") == "supported"))
    # the earlier rule, reported on the same quantities so the effect of the revision is visible and nothing is hidden
    fa = adj_first_author
    fa_served = [k for k in prim if cases[k]["served"] in ("male", "female")]
    ns = lambda ks: pct(sum(fa[k]["q3"] != "supported" for k in ks), len(ks))
    res["first_author_adjudication"] = dict(
        s1_not_supported=ns([k for k in fa_served if man[k]["stratum"] == "S1"]),
        s2_supported=pct(sum(fa[k]["q3"] == "supported" for k in fa_served if man[k]["stratum"] == "S2"),
                         len([k for k in fa_served if man[k]["stratum"] == "S2"])),
        s6_not_supported=ns([k for k in fa_served if man[k]["stratum"] == "S6"]), served_not_supported=ns(fa_served),
        vs_model={n: dict(agree=pct(sum(fa[k]["q1"] == key[k][f_] for k in prim if key[k].get(f_) is not None),
                                    sum(key[k].get(f_) is not None for k in prim)),
                          cohen_kappa=cohen([(fa[k]["q1"], key[k][f_]) for k in prim if key[k].get(f_) is not None], CATS["q1"]))
                  for n, f_ in (("claude_annotator1", "annotator1"), ("luna_strict", "annotator2_strict"), ("luna_permissive", "annotator2_permissive"))})
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
