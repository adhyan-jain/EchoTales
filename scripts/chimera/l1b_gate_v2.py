"""L1b (M1): evidence gate v2 on the 72-item pilot (implements PREREG_L1b_gate_v2.md v1).

LABEL PROVENANCE: silver only (model-drafted gold; the pipeline's own link for system-sourced items); reveal chapters
from repository data only. Reuses the L1 machinery by import (not edited) and the v1 arm-A outputs as the ungated
comparison. Prompt text and quotations are never written to disk (letters, hashes, offsets, counts only).

  --dry-run   no key, no network: builds prompts, split, token and cost estimate
  --run       needs --budget-usd and OPENAI_API_KEY in the environment (never printed); stops before any call that
              could exceed the budget
  --analyze   metrics and decision rules P1/P2 from the run output plus the v1 results

    python scripts/chimera/l1b_gate_v2.py --db <scratch RI copy> --dry-run --out data/eval/chimera/l1b_dryrun.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import l1_llm_leakage as L1  # noqa: E402

from echotales.core.store import Store  # noqa: E402

PROMPTS_V2 = "docs/research/preregistrations/L1_prompts_v2.json"
MANIFEST_V2 = "docs/research/preregistrations/MANIFEST_L1b.json"
V1_RESULTS = "data/eval/chimera/l1_results.json"
DETERMINERS = {"The", "A", "An"}


def load_prompts_v2() -> dict:
    raw = Path(PROMPTS_V2).read_bytes()
    man = json.loads(Path(MANIFEST_V2).read_text()) if Path(MANIFEST_V2).exists() else {}
    if man.get("prompts_file_sha256") != hashlib.sha256(raw).hexdigest():
        sys.exit("REFUSING: L1_prompts_v2.json does not match MANIFEST_L1b.json")
    d = json.loads(raw)
    for name, h in man["template_sha256"].items():
        if hashlib.sha256(d[name].encode()).hexdigest() != h:
            sys.exit(f"REFUSING: template {name} hash mismatch")
    v1 = json.loads(Path(L1.MANIFEST).read_text())["template_sha256"]
    if man["template_sha256"]["D2_entailment_call2"] != v1["D2_entailment_call2"]:
        sys.exit("REFUSING: D2 template is not byte-identical to v1")
    return d


def split_of(item_id: str) -> str:
    h = int(hashlib.sha256(f"L1v2-split-20261016-{item_id}".encode()).hexdigest(), 16)
    return "dev" if h % 2 == 0 else "test"


def norm_text(s: str) -> str:
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).casefold().strip()


def cap_tokens(s: str) -> set[str]:
    return {t for t in L1.TOKEN.findall(s) if t[:1].isupper() and t not in DETERMINERS}


def d1_prompts(items, chapters, tpl):
    out = []
    for it in items:
        win, _ = L1.build_window(chapters, it)
        p = L1.fill(tpl["D1_gated_call1"], WINDOW=win, SURFACE=it["surface"], CANDIDATES=L1.cand_block(it["cands"]))
        out.append(dict(item=it, window=win, prompt=p))
    return out


def dry_run(args, items, chapters, vocab, tpl):
    ps = d1_prompts(items, chapters, tpl)
    n = len(ps)
    d1_in = sum(L1.est_tokens(p["prompt"]) for p in ps)
    d2_in = n * (L1.est_tokens(tpl["D2_entailment_call2"]) + math.ceil(2 * 400 / L1.CHARS_PER_TOKEN))
    exp_in = d1_in + d2_in
    exp_out = n * 70 + n * 4
    worst_in = exp_in * 1.3
    worst_out = n * L1.CAPS["D1"] + n * L1.CAPS["D2"]
    res = dict(
        mode="dry-run (no network, no key)", model=L1.MODEL, n_items=n,
        split={s: sum(split_of(i["id"]) == s for i in items) for s in ("dev", "test")},
        primary_in_test=[i["id"] for i in items if i["tier"] == "P" and i["reveal_chapter"] is not None
                         and i["truth_letter"] and split_of(i["id"]) == "test"],
        calls=dict(D1=n, D2_max=n),
        expected=dict(input_tokens=exp_in, output_tokens=exp_out, usd=exp_in * L1.PRICE_IN + exp_out * L1.PRICE_OUT),
        worst_case=dict(input_tokens=int(worst_in), output_tokens=worst_out,
                        usd=worst_in * L1.PRICE_IN + worst_out * L1.PRICE_OUT,
                        assumption="every call hits its max_completion_tokens cap; input 1.3x the estimate"),
        token_estimate_method=f"chars/{L1.CHARS_PER_TOKEN} + {L1.OVERHEAD_TOK} per call; no tokenizer; ESTIMATE",
        prices_usd_per_1M=dict(input=0.20, output=1.20,
                               source="OpenAI pricing page, fetched 2026-10-15 (summarising tool)"),
    )
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


def apply_gate(it, win, text, tpl, vocab, go):
    """Gate v2 (PREREG_L1b section 2). `go(prompt)` makes the entailment call. Returns a result dict."""
    m = re.match(r"\s*ANSWER:\s*([A-Z]|UNDETERMINED)\b.*?\n\s*SPANS:\s*(.*)", text, re.S)
    ans, spans_raw = (m.group(1), m.group(2).strip()) if m else ("INVALID", "")
    letters = {L for L, _n, _i in it["cands"]}
    if ans not in letters and ans != "UNDETERMINED":
        ans = "INVALID"
    spans = [s.strip().strip('"') for s in spans_raw.split(" || ")] if spans_raw and spans_raw != "NONE" else []
    wn = norm_text(win.replace("[[", "").replace("]]", ""))
    valid = [s for s in spans if s and norm_text(s) in wn]
    res = dict(raw_answer=ans, accepted=False, gate="abstained_or_invalid", n_spans=len(spans),
               n_valid_spans=len(valid))
    if ans not in letters:
        return res
    claimed = next(n for L, n, _i in it["cands"] if L == ans)
    if cap_tokens(it["surface"]) & cap_tokens(claimed):  # rule 3: the mention itself names the candidate
        return dict(res, accepted=True, gate="surface_identity")
    if not valid or len(valid) != len(spans):
        return dict(res, gate="no_valid_spans")
    p2 = L1.d2_prompt(tpl, it["surface"], claimed, valid, vocab)
    if p2 is None:
        return dict(res, gate="claimed_name_not_in_spans")
    ok = go(p2).strip() == "ENTAILED"
    return dict(res, accepted=ok, gate="entailed" if ok else "not_entailed")


def live_run(args, items, chapters, vocab, tpl):
    import httpx

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set in the environment")
    budget = L1.Budget(args.budget_usd)
    ps = d1_prompts(items, chapters, tpl)
    results: dict = {}
    log: list = []
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as client:
        del key

        def go_factory(arm, item_id):
            def go(prompt, cap_key="D2"):
                if not budget.can(L1.est_tokens(prompt), L1.CAPS[cap_key]):
                    Path(args.out).write_text(json.dumps(dict(status="STOPPED_AT_BUDGET", spent_usd=budget.actual,
                                                              results=results, log=log), indent=2))
                    sys.exit(f"stopping: next call could exceed the approved budget (spent ${budget.actual:.4f})")
                r = L1.call_model(client, prompt, L1.CAPS[cap_key])
                budget.calls += 1
                budget.tok_in += r["tok_in"]
                budget.tok_out += r["tok_out"]
                budget.actual += r["tok_in"] * L1.PRICE_IN + r["tok_out"] * L1.PRICE_OUT
                log.append(dict(item=item_id, arm=arm, tok_in=r["tok_in"], tok_out=r["tok_out"],
                                prompt_sha=hashlib.sha256(prompt.encode()).hexdigest()[:16]))
                return r["text"]
            return go

        for p in ps:
            it = p["item"]
            text = go_factory("D1v2", it["id"])(p["prompt"], "D1")
            results[it["id"]] = apply_gate(it, p["window"], text, tpl, vocab, go_factory("D2v2", it["id"]))
            results[it["id"]]["split"] = split_of(it["id"])
    out = dict(status="COMPLETE", spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in,
               tok_out=budget.tok_out, results=results, log=log)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"complete. calls={budget.calls} tokens_in={budget.tok_in} tokens_out={budget.tok_out} "
          f"spent=${budget.actual:.4f}")


def analyze(args, items):
    run = json.loads(Path(args.results).read_text())
    v1 = json.loads(Path(V1_RESULTS).read_text())["results"]
    R = run["results"]
    prim, ctrl, _other, _cb = L1.sets(items)

    def gated(it):
        r = R.get(it["id"])
        return None if r is None else (r["raw_answer"] if r["accepted"] else "UNDETERMINED")

    out = dict(label_provenance="SILVER; reveal chapters from repo data; one model; v1 outcomes were seen before "
                                "the design (PREREG_L1b section 1)",
               status=run.get("status"), spent_usd=run.get("spent_usd"), calls=run.get("calls"),
               tokens=dict(input=run.get("tok_in"), output=run.get("tok_out")))
    for label, pred in (("test", lambda i: split_of(i["id"]) == "test"),
                        ("dev", lambda i: split_of(i["id"]) == "dev"), ("all", lambda i: True)):
        cs = [i for i in ctrl if pred(i)]
        gk = sum(gated(i) == i["truth_letter"] for i in cs)
        ak = sum(v1[i["id"]]["A"] == i["truth_letter"] for i in cs)
        paths: dict[str, int] = {}
        for i in cs:
            paths[R[i["id"]]["gate"]] = paths.get(R[i["id"]]["gate"], 0) + 1
        entailed_ok = [i for i in cs if R[i["id"]]["gate"] == "entailed"]
        out[f"controls_{label}"] = dict(
            n=len(cs), gated_correct=L1.row(gk, len(cs)), ungated_A_correct=L1.row(ak, len(cs)), gate_paths=paths,
            entailed_path_matches_silver=L1.row(sum(gated(i) == i["truth_letter"] for i in entailed_ok),
                                                len(entailed_ok)))
    pt = [i for i in prim if split_of(i["id"]) == "test"]
    out["primary_test"] = dict(
        n=len(pt), accepted_as_silver_final_identity=sum(gated(i) == i["truth_letter"] for i in pt),
        per_item=[dict(id=i["id"], gate=R[i["id"]]["gate"], accepted=R[i["id"]]["accepted"]) for i in pt])
    ct = out["controls_test"]
    p1 = ct["gated_correct"]["k"] >= ct["ungated_A_correct"]["k"] - 1
    p2 = out["primary_test"]["accepted_as_silver_final_identity"] <= 1
    out["decision"] = dict(P1_keeps_correct_links_test=bool(p1), P2_blocks_premature_test=bool(p2),
                           result="PASS (descriptive; see interpretation guard)" if (p1 and p2) else "FAIL")
    Path(args.analysis_out).write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="data/eval/chimera/l1b_results.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--analyze", action="store_true")
    ap.add_argument("--budget-usd", type=float, default=0.0)
    ap.add_argument("--results", default="data/eval/chimera/l1b_results.json")
    ap.add_argument("--analysis-out", default="data/eval/chimera/l1b_analysis.json")
    args = ap.parse_args()
    if args.run and args.budget_usd <= 0:
        sys.exit("--run needs an explicit --budget-usd (the amount the owner approved)")
    store = Store(args.db)
    items = L1.load_items(store)
    if args.analyze:
        return analyze(args, items)
    tpl = load_prompts_v2()
    need = {it["chapter"] - k for it in items for k in range(0, 4)}
    chapters = {c.number: c.story_text for c in store.iter_chapters(L1.NOVEL) if c.number in need}
    vocab = set(L1.build_pi(args.db)[0].mapping)
    (dry_run if args.dry_run else live_run)(args, items, chapters, vocab, tpl)


if __name__ == "__main__":
    main()
