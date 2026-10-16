"""PD v5 (PREREG_PD_v5.md): cue-preserving rename arm B3, to separate memory from name-borne cue loss.

Why: an external adversarial review (report 5.19) objected that the letter cipher destroys name-borne cues (gender, name
type), so A minus B could measure lost cues, not memorisation. B3 keeps those cues and removes only the specific names:
the event's cast and alias NAME tokens are replaced by natural pseudonyms matched in gender (inferred from pronouns that
follow the name in the book) and name type (first name or surname); every other proper noun keeps the v2 cipher
(seed 20261015), so places and bystanders stay memory-free; honorifics, pronouns and all other words are untouched.
If cue loss explained the gap, B3 would recover A-like premature rates; if memory explains it, B3 stays near B.
The v2 and v3 items, windows, candidates and letters are rebuilt identically (same item ids) and compared with the
stored A, B and B2 answers; only B3 is newly asked (one call per item).

Commands: freeze | build | run --model M [--budget-usd X for gpt-5.6-luna] | estimate | analyze. Local ollama or Luna
(budget-guarded); no key is printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_llm_leakage as L1  # noqa: E402
import pd_reveal_benchmark as PD  # noqa: E402
import pd_v2 as V2  # noqa: E402
import pd_v3 as V3  # noqa: E402
import t4_renaming_v4 as V4  # noqa: E402

P = Path("docs/research/preregistrations")
MANIFEST = P / "MANIFEST_PD_v5.json"
OUT = Path("data/eval/chimera/pd_v5")
SEED = 20261018
OPTS = {"temperature": 0, "seed": 20261016, "num_predict": 24, "num_ctx": 2048}
CAP_OUT = 32
MALE_PRON, FEMALE_PRON = {"he", "him", "his", "himself"}, {"she", "her", "hers", "herself"}
MALE_FIRST = ("Daniel Samuel Peter Henry Walter Oliver Edwin Gordon Nigel Roland Franklin Clifford Hugh Leonard Alan Bernard "
              "Stanley Lionel Maurice Norman Percival Quentin Rupert Sidney Theodore Vincent Wilfred Alden Barnaby Cedric "
              "Dudley Ellis Fenton Gilbert Harold Irving Julian Kenneth Lawrence Marcus Nathan Orson Philip Reginald Silas "
              "Terrence Ulric Victor Warren Alistair Basil Conrad Desmond Emmett Felix Gideon Hector Ivor Jasper Kendall").split()
FEMALE_FIRST = ("Alice Beatrice Clara Dorothy Edith Florence Gwendolen Harriet Irene Josephine Katherine Louisa Margaret "
                "Nora Olive Phoebe Rosalind Sylvia Theresa Ursula Violet Winifred Agnes Bridget Cecilia Diana Eleanor "
                "Frances Georgiana Hester Imogen Joan Lucille Muriel Naomi Odette Pauline Rhoda Stella Tabitha Una "
                "Vera Wendy Adela Blanche Corinne Delia Estelle Flora Gertrude Helena Ingrid Judith Lorna Mabel").split()
NEUTRAL_FIRST = "Alex Jordan Morgan Taylor Casey Riley Avery Quinn Rowan Sasha Dana Robin Sidney Hollis Marion Lee".split()
SURNAMES = ("Ashford Bellamy Carrow Dalby Everett Fairfax Garrick Halloran Ingram Jessop Kingsley Lockwood Marlowe "
            "Northcott Ormsby Pemberton Quillfeather Radcliffe Sheridan Thornbury Underhill Vandeleur Whitcombe Yardley "
            "Zeller Aldrich Beresford Calloway Denholm Eastwick Farrow Gresham Hollis Ironside Jarvis Kestrel Langley "
            "Merrick Nethercott Oakes Prescott Rutherford Sinclair Tennant Upton Valentine Winslow Yeomans Abernathy "
            "Blackwood Crandall Draycott Ellsworth Fenwick Goodwin Hartley Islington Jennings Kimball Lindsay Mortimer "
            "Newbury Overton Pickering Rowley Stanhope Trevelyan Whitaker Alderley Brasher Chaloner Dunmore Fitzroy").split()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gender_of(token: str, text: str) -> str:
    m = f = 0
    for mt in re.finditer(r"\b" + re.escape(token) + r"\b", text):
        nxt = re.findall(r"[A-Za-z']+", text[mt.end(): mt.end() + 160])[:14]
        for w in nxt:
            lw = w.lower()
            if lw in MALE_PRON:
                m += 1
            elif lw in FEMALE_PRON:
                f += 1
    if m >= 3 and m >= 2 * f:
        return "male"
    if f >= 3 and f >= 2 * m:
        return "female"
    return "unknown"


def name_tokens(name: str, honor: set[str]):
    return [t for t in PD.TOKEN.findall(name) if t[:1].isupper() and len(t) >= 3 and t.lower() not in honor]


def build_maps(evs: list[dict], books: dict[int, str]):
    """per book: token -> pseudonym for the cast and alias NAME tokens of that book's events (deterministic)."""
    honor = V4.honorific_words() | PD.HONORIFICS
    maps, audit = {}, {}
    for gid, text in books.items():
        toks = PD.TOKEN.findall(text)
        lower = {t for t in toks if t[:1].islower()}
        lowered_all = {t.lower() for t in toks}
        roles = {}  # token -> 'first' | 'last'; insertion order is deterministic
        ident_gender = {}
        for ev in (e for e in evs if e["gutenberg"] == gid):
            for nm in ev["cast"]:
                ts = name_tokens(nm, honor)
                for k, t in enumerate(ts):
                    if t in lower or t in roles:
                        continue
                    roles[t] = "first" if (k == 0 and (len(ts) > 1 or gender_of(t, text) != "unknown")) else "last"
            its = name_tokens(ev["identity"], honor)
            g = gender_of(its[0], text) if its else "unknown"
            for al in ev["alias"]:
                first_tok = PD.TOKEN.findall(al)
                has_hon = bool(first_tok) and first_tok[0].lower() in honor
                for t in name_tokens(al, honor):
                    if t in lower or t in roles:
                        continue
                    roles[t] = "last" if has_hon else "first"
                    ident_gender[t] = g
        rng = random.Random(SEED + gid)
        pools = {"male": MALE_FIRST[:], "female": FEMALE_FIRST[:], "unknown": NEUTRAL_FIRST[:], "last": SURNAMES[:]}
        for v in pools.values():
            rng.shuffle(v)
        used, mp = set(), {}
        for t, role in roles.items():
            g = ident_gender.get(t) or gender_of(t, text)
            key = "last" if role == "last" else (g if g in ("male", "female") else "unknown")
            while pools[key] and (pools[key][-1].lower() in lowered_all or pools[key][-1] in used):
                pools[key].pop()
            if not pools[key]:
                continue
            ps = pools[key].pop()
            used.add(ps)
            mp[t] = ps
            audit.setdefault(gid, {})[t] = dict(role=role, gender=g, pseudonym=ps)
        maps[gid] = mp
    return maps, audit


def make_b3(base, mp: dict[str, str]):
    def rename(text: str) -> str:
        return V4.TOKEN.sub(lambda m: mp.get(m.group(0)) or base._run(m.group(0)), text)

    return rename


def datasets(texts: Path, mod):
    """(events, items, books) of a frozen dataset module, so ids match the stored v2 / v3 runs."""
    items, books = mod.build_items(texts)
    evs = {e["id"]: e for e in mod.load_events()}
    return evs, items, books


def prompts(texts: Path):
    base_tpl = json.loads((P / "PD_prompts_v1.json").read_text())
    tail = json.loads((P / "PD_prompts_v2.json").read_text())
    out, audit_all = [], {}
    for ver, mod in (("pd_v2", V2), ("pd_v3", V3)):
        evs, items, books = datasets(texts, mod)
        maps, audit = build_maps(list(evs.values()), books)
        audit_all[ver] = audit
        rn = mod.renamers_for(books)
        for i, it in enumerate(items):
            ev = evs[it["event"]]
            r1, _r2 = rn[ev["gutenberg"]]
            b3 = make_b3(r1, maps[ev["gutenberg"]])
            cl = PD.cand_letters(ev, i)
            win = PD.window_for(books[ev["gutenberg"]], it)
            p3 = L1.fill(base_tpl["A_B_prefix"], WINDOW=b3(win), SURFACE=b3(it["surface"]), CANDIDATES=L1.cand_block(cl, b3))
            out.append(dict(dataset=ver, id=it["id"], cands=cl, B3=V2.tail_swap(p3, tail)))
    return out, audit_all


def cmd_freeze(args):
    if MANIFEST.exists():
        sys.exit("REFUSING: manifest exists; a change is a new version")
    man = dict(frozen_for="PREREG_PD_v5.md", prereg_sha256=sha(P / "PREREG_PD_v5.md"),
               script_sha256_at_freeze=sha(Path(__file__)),
               inputs_sha256={f.name: sha(f) for f in (P / "PD_events_v1.json", P / "PD_events_v2_additions.json",
                                                     P / "PD_events_v3_additions.json", P / "PD_prompts_v1.json",
                                                     P / "PD_prompts_v2.json")})
    MANIFEST.write_text(json.dumps(man, indent=1))
    print("frozen", json.dumps(man, indent=1))


def check_frozen():
    man = json.loads(MANIFEST.read_text())
    for name, h in man["inputs_sha256"].items():
        if sha(P / name) != h:
            sys.exit(f"REFUSING: {name} does not match MANIFEST_PD_v5.json")


def cmd_build(args):
    check_frozen()
    rows, audit = prompts(Path(args.texts))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pseudonym_map_audit.json").write_text(json.dumps(audit, indent=1))
    n = sum(len(v) for ds in audit.values() for v in ds.values())
    unk = sum(1 for ds in audit.values() for v in ds.values() for t in v.values() if t["gender"] == "unknown" and t["role"] == "first")
    print(len(rows), "B3 prompts;", n, "name tokens mapped;", unk, "first-name tokens of unknown gender (neutral pool)")


def parse(text, cands):
    m = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
    t = (m.group(1) if m else "").strip()
    return t if (t == "UNDETERMINED" or t in {L for L, _n, _i in cands}) else "INVALID"


def cmd_estimate(args):
    check_frozen()
    rows, _ = prompts(Path(args.texts))
    est_in = sum(L1.est_tokens(r["B3"]) for r in rows)
    exp_in, exp_out = math.ceil(est_in * 0.8958), len(rows) * 10
    worst_in = math.ceil(est_in * 1.3)
    print(json.dumps(dict(calls=len(rows), expected=dict(input_tokens=exp_in, output_tokens=exp_out,
                                                         usd=round(exp_in * L1.PRICE_IN + exp_out * L1.PRICE_OUT, 4)),
                          worst_case=dict(input_tokens=worst_in, output_tokens=len(rows) * CAP_OUT,
                                          usd=round(worst_in * L1.PRICE_IN + len(rows) * CAP_OUT * L1.PRICE_OUT, 4))), indent=1))


def cmd_run(args):
    import httpx

    check_frozen()
    rows, _ = prompts(Path(args.texts))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"run_{args.model.replace(':', '_').replace('/', '_')}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    res = dict(model=args.model, B3={}, status="COMPLETE")
    if args.model == "gpt-5.6-luna":
        if args.budget_usd is None:
            sys.exit("REFUSING: gpt-5.6-luna needs --budget-usd")
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            sys.exit("OPENAI_API_KEY is not set in the environment")
        budget = L1.Budget(args.budget_usd)
        with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as c:
            del key
            for r in rows:
                if not budget.can(L1.est_tokens(r["B3"]), CAP_OUT):
                    res["status"] = "STOPPED_AT_BUDGET"
                    break
                x = L1.call_model(c, r["B3"], CAP_OUT)
                budget.calls += 1
                budget.tok_in += x["tok_in"]
                budget.tok_out += x["tok_out"]
                budget.actual += x["tok_in"] * L1.PRICE_IN + x["tok_out"] * L1.PRICE_OUT
                res["B3"][r["id"]] = parse(x["text"], r["cands"])
        res.update(spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in, tok_out=budget.tok_out)
    else:
        host = "http://127.0.0.1:11434"
        with httpx.Client(timeout=240.0) as c:
            first = True
            for r in rows:
                for ln in open("/proc/meminfo"):
                    if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 1.0:
                        sys.exit("stopping: available RAM below 1 GiB")
                allowed = [L for L, _n, _i in r["cands"]] + ["UNDETERMINED"]
                schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": allowed}}, "required": ["answer"]}
                x = c.post(f"{host}/api/chat", json=dict(model=args.model, stream=False, options=OPTS, format=schema,
                                                          messages=[dict(role="user", content=r["B3"])]))
                x.raise_for_status()
                try:
                    a = json.loads(x.json()["message"]["content"]).get("answer", "")
                except (ValueError, AttributeError):
                    a = "INVALID"
                res["B3"][r["id"]] = a if a in allowed else "INVALID"
                if first:
                    ps = c.get(f"{host}/api/ps").json().get("models", [])
                    m = next((y for y in ps if y["name"] == args.model), None)
                    if m is None or m.get("size_vram", 0) < m.get("size", 1):
                        sys.exit(f"stopping: {args.model} not fully in VRAM; no CPU offload allowed")
                    first = False
            c.post(f"{host}/api/generate", json=dict(model=args.model, keep_alive=0, prompt=""))
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "| status", res["status"], "| spent_usd", round(res.get("spent_usd", 0.0), 4))


# ---------------------------------------------------------------- analysis
def stored(ver):
    runs = {}
    for f in sorted(Path(f"data/eval/chimera/{ver}").glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    return runs


def g2(r):
    T, S = r["truth"], r["synth_truth"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
    sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
    return (sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl),
            sum(r["synth"][i]["A"] == r["synth"][i]["B"] for i in sp) / len(sp))


def ev_boot(per_event: dict, seed=SEED, n=5000):
    """per_event: event -> list of (a, b, b3) per (model, pre-item). Point + event-cluster CI for gap A-B, gap A-B3, recovered fraction."""
    evs = sorted(per_event)

    def stat(es):
        rows = [x for e in es for x in per_event[e]]
        a = sum(x[0] for x in rows) / len(rows)
        b = sum(x[1] for x in rows) / len(rows)
        b3 = sum(x[2] for x in rows) / len(rows)
        return a - b, a - b3, ((b3 - b) / (a - b) if a - b > 1e-9 else float("nan"))

    pt = stat(evs)
    rng = random.Random(seed)
    bs = [stat([rng.choice(evs) for _ in evs]) for _ in range(n)]
    ci = []
    for k in range(3):
        v = sorted(x[k] for x in bs if not math.isnan(x[k]))
        ci.append([round(v[int(0.025 * len(v))], 4), round(v[int(0.975 * len(v))], 4)])
    ev_pos = sum(1 for e in evs if sum(x[0] - x[2] for x in per_event[e]) > 0)
    ev_neg = sum(1 for e in evs if sum(x[0] - x[2] for x in per_event[e]) < 0)
    return dict(events=len(evs), pairs=sum(len(v) for v in per_event.values()), gap_A_minus_B=round(pt[0], 4), gap_A_minus_B_ci=ci[0],
                gap_A_minus_B3=round(pt[1], 4), gap_A_minus_B3_ci=ci[1], recovered_fraction=round(pt[2], 4),
                recovered_fraction_ci=ci[2], events_A_gt_B3=ev_pos, events_A_lt_B3=ev_neg)


def cmd_analyze(args):
    new = {}
    for f in sorted(OUT.glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            new[r["model"]] = r["B3"]
    out = dict(preregistration="PREREG_PD_v5.md", per_model={}, pools={},
               label_provenance="TEXT-DERIVED oracle; selection by model-drafter; owner spot-check pending; no human labels")
    per_pool = {"G2_valid": {}, "all_models": {}}
    for ver in ("pd_v2", "pd_v3"):
        for m, r in stored(ver).items():
            if m not in new:
                continue
            T = r["truth"]
            pre = [i for i, t in T.items() if t["kind"] == "pre"]
            ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
            if not all(i in new[m] for i in pre + ctrl):
                continue

            def hit(arm, i, r=r, T=T):
                return int(r["real"][i][arm] == T[i]["identity_letter"])

            rows = {}
            for i in pre:
                rows.setdefault(T[i]["event"], []).append((hit("A", i), (hit("B", i) + hit("B2", i)) / 2,
                                                           int(new[m][i] == T[i]["identity_letter"])))

            def acc(arm, r=r, T=T, m=m, ctrl=ctrl):
                return sum((r["real"][i][arm] if arm != "B3" else new[m][i]) == T[i]["truth_letter"] for i in ctrl) / len(ctrl)

            out["per_model"].setdefault(m, {})[ver] = dict(
                per_event=ev_boot(rows), ctrl_acc_A=round(acc("A"), 4), ctrl_acc_B=round(acc("B"), 4), ctrl_acc_B3=round(acc("B3"), 4),
                ctrl_A_eq_B3=round(sum(r["real"][i]["A"] == new[m][i] for i in ctrl) / len(ctrl), 4),
                invalid_B3=sum(v == "INVALID" for v in new[m].values()))
            valid = g2(r)[0] >= 0.90 and g2(r)[1] >= 0.80
            for pool, ok in (("all_models", True), ("G2_valid", valid)):
                if ok:
                    for e, v in rows.items():
                        per_pool[pool].setdefault(e, []).extend(v)
    for pool, pe in per_pool.items():
        if pe:
            out["pools"][pool] = ev_boot(pe)
    for st in out["pools"].values():
        rec = st["recovered_fraction"]
        st["reading"] = ("MEMORY-DOMINANT (B3 recovers under one third of the gap)" if rec < 1 / 3 else
                         "CUE-DOMINANT (B3 recovers over two thirds)" if rec > 2 / 3 else "MIXED (B3 recovers one to two thirds)")
        st["primary_gap_condition_met"] = bool(st["gap_A_minus_B3"] >= 0.10 and st["gap_A_minus_B3_ci"][0] > 0)
        st["verdict"] = ("CUE-DOMINANT" if rec > 2 / 3 else
                         "MEMORY SURVIVES (strong)" if st["primary_gap_condition_met"] and rec < 1 / 3 else
                         "MEMORY SURVIVES (partial)" if st["primary_gap_condition_met"] else "INCONCLUSIVE")
    (OUT / "analysis.json").write_text(json.dumps(out, indent=1))
    for m, d in out["per_model"].items():
        for ver, v in d.items():
            e = v["per_event"]
            print(f"{m:22s} {ver} gapAB {e['gap_A_minus_B']:+.3f} gapAB3 {e['gap_A_minus_B3']:+.3f} {e['gap_A_minus_B3_ci']} rec {e['recovered_fraction']:+.2f} | ctrl acc A {v['ctrl_acc_A']:.3f} B {v['ctrl_acc_B']:.3f} B3 {v['ctrl_acc_B3']:.3f} inv {v['invalid_B3']}")
    for pool, st in out["pools"].items():
        print(pool, json.dumps(st))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("freeze", "build", "run", "estimate", "analyze"):
        s = sp.add_parser(n)
        if n in ("build", "run", "estimate"):
            s.add_argument("--texts", required=True)
        if n == "run":
            s.add_argument("--model", required=True)
            s.add_argument("--budget-usd", type=float, default=None)
    a = ap.parse_args()
    dict(freeze=cmd_freeze, build=cmd_build, run=cmd_run, estimate=cmd_estimate, analyze=cmd_analyze)[a.cmd](a)


if __name__ == "__main__":
    main()
