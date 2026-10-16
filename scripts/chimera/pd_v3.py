"""PD benchmark v3 (PREREG_PD_v3.md): confirmatory re-test of the v2 design on 12 books no earlier version used, with the
renaming-validity bar fixed at 80% in advance (owner convention). Generated from the frozen pd_v2.py with only these changes:
event file, paths, R0 bar 0.95 -> 0.80 (strict 95% flag kept), per-event secondary analysis. Original v2 docstring follows.

PD benchmark v2 (PREREG_PD_v2.md): re-run of the public-domain reveal test with the repairs the v1 result called for.

Why v2 exists (v1 result, 2026-10-16): four of five models failed the 95% renaming-validity gate on 21 plain
controls, partly through answer-format noise (Mistral 35 invalid answers) and partly through misreading ciphered classic
prose, so their large A-minus-B gaps could not be attributed to memory. v2 changes only what that diagnosis named:
  1. constrained output (ollama `format` JSON schema with an enum of the allowed answers), so format noise cannot
     masquerade as renaming damage;
  2. more plain controls (up to 8 per event, two cast names) so the 95% gate is not decided by one item;
  3. a second independent cipher arm B2 (different seed), so renaming damage is also measured as B-versus-B2
     disagreement on controls, and a gap that appears under both ciphers is not a one-cipher artefact;
  4. the "most-mentioned candidate" baseline that the v1 prereg listed but v1 never computed.
Verdict rule change declared in the prereg: fewer than 3 models passing the gate is INCONCLUSIVE, not NOT SUPPORTED
(v1's rule could not return SUPPORTED when fewer than 3 models passed, so it conflated "no leakage" with "no power").

Commands: freeze | verify | build | run --model M | analyze. Local ollama only; no API key, no spend.
Texts come from a local Gutenberg copy (never written to the repo)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_reveal_benchmark as PD  # noqa: E402
import l1_llm_leakage as L1  # noqa: E402
import t4_renaming_v5 as V5  # noqa: E402
import t4_renaming_v4 as V4  # noqa: E402

P = Path("docs/research/preregistrations")
EVENT_FILES = [P / "PD_events_v3_additions.json"]
PROMPTS_V1 = P / "PD_prompts_v1.json"
PROMPTS_V2 = P / "PD_prompts_v2.json"
MANIFEST = P / "MANIFEST_PD_v3.json"
OUT = Path("data/eval/chimera/pd_v3")
R0_BAR = 0.80
SEED_B2 = 20261016
CTRL_NAMES, CTRL_PER_NAME = 2, 4
OPTS = {"temperature": 0, "seed": 20261016, "num_predict": 24, "num_ctx": 2048}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_events() -> list[dict]:
    man = json.loads(MANIFEST.read_text())
    evs = []
    for f in EVENT_FILES:
        if sha(f) != man["event_files_sha256"][f.name]:
            sys.exit(f"REFUSING: {f.name} does not match MANIFEST_PD_v3.json")
        evs += json.loads(f.read_text())["events"]
    ids = [e["id"] for e in evs]
    if len(set(ids)) != len(ids):
        sys.exit("REFUSING: duplicate event ids across event files")
    return evs


def tail_swap(prompt: str, tpl2: dict) -> str:
    assert tpl2["tail_old"] in prompt, "prompt tail not found; template drift"
    return prompt.replace(tpl2["tail_old"], tpl2["tail_new"])


def controls(ev: dict, text: str, cut: int):
    """Two non-identity cast names with the most prefix mentions, four evenly spaced mentions each. v1 used the single
    best name with 3 mentions, which left the 95% renaming gate resting on 21 items."""
    cands = []
    for nm in ev["cast"]:
        if nm == ev["identity"]:
            continue
        best = None
        for sf in PD.surfaces_for(nm):
            ms = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\b" + re.escape(sf) + r"\b", text[:cut])]
            ms = [m for m in ms if PD.sentence_end(text, m[1]) <= cut]
            if best is None or len(ms) > len(best):
                best = ms
        cands.append((nm, best))
    cands.sort(key=lambda c: -len(c[1]))
    out = []
    for nm, ms in cands[:CTRL_NAMES]:
        out += [(nm, ms[i]) for i in PD.spaced(len(ms), CTRL_PER_NAME)]
    return out


def most_mentioned(ev: dict, text: str, cut: int) -> str:
    counts = {}
    for nm in ev["cast"]:
        counts[nm] = max(len(re.findall(r"\b" + re.escape(sf) + r"\b", text[:cut])) for sf in PD.surfaces_for(nm))
    return max(counts, key=lambda k: (counts[k], k))


def build_items(texts: Path):
    items, books = [], {}
    for ev in load_events():
        text = books.setdefault(ev["gutenberg"], PD.load_text(texts, ev["gutenberg"]))
        loc = PD.locate(ev, text)
        pre = [loc["pre"][i] for i in PD.spaced(len(loc["pre"]), 8)]
        post = [loc["post"][i] for i in PD.spaced(len(loc["post"]), 2)]
        for m in pre:
            items.append(dict(event=ev["id"], kind="pre", start=m[0], end=m[1], surface=m[2], truth=None,
                              distance=loc["cut"] - PD.sentence_end(text, m[1])))
        for m in post:
            items.append(dict(event=ev["id"], kind="post", start=m[0], end=m[1], surface=m[2], truth=ev["identity"],
                              distance=None))
        for nm, m in controls(ev, text, loc["cut"]):
            items.append(dict(event=ev["id"], kind="ctrl", start=m[0], end=m[1], surface=m[2], truth=nm, distance=None))
    for i, it in enumerate(items):
        it["id"] = f"{it['event']}-{it['kind']}{i:03d}"
    return items, books


def renamers_for(books):
    def mk(text, seed):
        toks = PD.TOKEN.findall(text)
        lower = {t for t in toks if t[:1].islower()}
        proper = {t for t in toks if t[:1].isupper() and t.lower() not in lower and len(t) >= 3}
        return V5.CipherRenamerV5(proper, V4.honorific_words(), seed, {t.lower() for t in toks})

    return {g: (mk(t, 20261015), mk(t, SEED_B2)) for g, t in books.items()}


def prompts(texts: Path):
    tpl = json.loads(PROMPTS_V2.read_text())
    base = json.loads(PROMPTS_V1.read_text())
    items, books = build_items(texts)
    evs = {e["id"]: e for e in load_events()}
    rn = renamers_for(books)
    out = []
    for i, it in enumerate(items):
        ev = evs[it["event"]]
        text = books[ev["gutenberg"]]
        r1, r2 = rn[ev["gutenberg"]]
        cl = PD.cand_letters(ev, i)
        letter_of = {n: L for L, n, _ in cl}
        win = PD.window_for(text, it)
        row = dict(id=it["id"], event=it["event"], kind=it["kind"], cands=cl, distance=it["distance"],
                   truth_letter="UNDETERMINED" if it["kind"] == "pre" else letter_of[it["truth"]],
                   identity_letter=letter_of[ev["identity"]])
        row["A"] = L1.fill(base["A_B_prefix"], WINDOW=win, SURFACE=it["surface"], CANDIDATES=L1.cand_block(cl))
        for arm, r in (("B", r1), ("B2", r2)):
            row[arm] = L1.fill(base["A_B_prefix"], WINDOW=r.rename(win), SURFACE=r.rename(it["surface"]),
                               CANDIDATES=L1.cand_block(cl, r.rename))
        for arm in ("A", "B", "B2"):
            row[arm] = tail_swap(row[arm], tpl)
        row["baseline_letter"] = letter_of[most_mentioned(ev, text, PD.locate(ev, text)["cut"])]
        out.append(row)
    cb = []
    for k, ev in enumerate(evs.values()):
        r1, r2 = rn[ev["gutenberg"]]
        cl = PD.cand_letters(ev, 9000 + k)
        letter_of = {n: L for L, n, _ in cl}
        row = dict(event=ev["id"], identity_letter=letter_of[ev["identity"]], cands=cl)
        row["C_orig"] = L1.fill(base["C_closed_book"], SURFACE=ev["alias"][0], CANDIDATES=L1.cand_block(cl))
        for arm, r in (("C_ren", r1), ("C_ren2", r2)):
            row[arm] = L1.fill(base["C_closed_book"], SURFACE=r.rename(ev["alias"][0]),
                               CANDIDATES=L1.cand_block(cl, r.rename))
        for arm in ("C_orig", "C_ren", "C_ren2"):
            row[arm] = tail_swap(row[arm], tpl)
        cb.append(row)
    return out, cb


def synthetic(ri_db: str):
    tpl = json.loads(PROMPTS_V2.read_text())
    ps = PD.synthetic_prompts(ri_db)
    for p in ps:
        for arm in ("A", "B"):
            p[arm] = tail_swap(p[arm], tpl)
    return ps


# ---------------------------------------------------------------- commands
def cmd_freeze(args):
    if MANIFEST.exists():
        sys.exit("REFUSING: manifest exists; a change is a new version")
    man = dict(frozen_for="PREREG_PD_v3.md", event_files_sha256={f.name: sha(f) for f in EVENT_FILES},
               prompts_v2_sha256=sha(PROMPTS_V2), prompts_v1_sha256=sha(PROMPTS_V1),
               prereg_sha256=sha(P / "PREREG_PD_v3.md"), script_sha256_at_freeze=sha(Path(__file__)))
    MANIFEST.write_text(json.dumps(man, indent=1))
    print("frozen", json.dumps(man, indent=1))


def cmd_verify(args):
    for ev in load_events():
        text = PD.load_text(Path(args.texts), ev["gutenberg"])
        loc = PD.locate(ev, text)
        nctrl = len(controls(ev, text, loc["cut"]))
        print(f"{ev['id']}: pre {len(loc['pre'])} post {len(loc['post'])} ctrl {nctrl} "
              f"identity-in-prefix {loc['identity_in_prefix']} leaks {loc['prefix_sentences_with_alias_and_identity_token']}")


def cmd_build(args):
    items, _ = build_items(Path(args.texts))
    OUT.mkdir(parents=True, exist_ok=True)
    c = Counter((i["event"], i["kind"]) for i in items)
    kinds = Counter(i["kind"] for i in items)
    slim = [{k: v for k, v in i.items() if k != "surface"} | dict(
        surface_sha=hashlib.sha256(i["surface"].encode()).hexdigest()[:12]) for i in items]
    (OUT / "items_manifest.json").write_text(json.dumps(dict(
        label_provenance="TEXT-DERIVED oracle; selection by model-drafter; owner spot-check pending; no novel text here",
        n_items=len(items), kinds=dict(kinds), counts={f"{e}|{k}": v for (e, k), v in sorted(c.items())},
        items=slim), indent=1))
    print(dict(kinds), "total", len(items))


def cmd_run(args):
    import httpx

    real, cb = prompts(Path(args.texts))
    syn = synthetic(args.ri_db)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"run_{args.model.replace(':', '_').replace('/', '_')}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    host = "http://127.0.0.1:11434"

    def ask(c, prompt, cands):
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 1.0:
                sys.exit("stopping: available RAM below 1 GiB")
        allowed = [L for L, _n, _i in cands] + ["UNDETERMINED"]
        schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": allowed}},
                  "required": ["answer"]}
        r = c.post(f"{host}/api/chat", json=dict(model=args.model, stream=False, options=OPTS, format=schema,
                                                  messages=[dict(role="user", content=prompt)]))
        r.raise_for_status()
        try:
            a = json.loads(r.json()["message"]["content"]).get("answer", "")
        except (ValueError, AttributeError):
            return "INVALID"
        return a if a in allowed else "INVALID"

    res = dict(model=args.model, options=OPTS, real={}, closed={}, synth={}, status="COMPLETE")
    with httpx.Client(timeout=240.0) as c:
        first = True
        for p in real:
            res["real"][p["id"]] = {arm: ask(c, p[arm], p["cands"]) for arm in ("A", "B", "B2")}
            if first:
                ps = c.get(f"{host}/api/ps").json().get("models", [])
                m = next((x for x in ps if x["name"] == args.model), None)
                if m is None or m.get("size_vram", 0) < m.get("size", 1):
                    sys.exit(f"stopping: {args.model} not fully in VRAM; no CPU offload allowed")
                first = False
        for p in cb:
            res["closed"][p["event"]] = {arm: ask(c, p[arm], p["cands"]) for arm in ("C_orig", "C_ren", "C_ren2")}
        for p in syn:
            res["synth"][p["id"]] = {arm: ask(c, p[arm], p["cands"]) for arm in ("A", "B")}
        c.post(f"{host}/api/generate", json=dict(model=args.model, keep_alive=0, prompt=""))
    res["truth"] = {p["id"]: dict(truth_letter=p["truth_letter"], identity_letter=p["identity_letter"],
                                  kind=p["kind"], event=p["event"], distance=p["distance"],
                                  baseline_letter=p["baseline_letter"]) for p in real}
    res["closed_truth"] = {p["event"]: p["identity_letter"] for p in cb}
    res["synth_truth"] = {p["id"]: dict(type=p["type"], truth_letter=p["truth_letter"],
                                        identity_letter=p["identity_letter"]) for p in syn}
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "| real", len(res["real"]), "closed", len(res["closed"]), "synth", len(res["synth"]))


def binom_tail(n: int, k: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def cmd_analyze(args):
    runs = {}
    for f in sorted(OUT.glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    out = dict(preregistration="PREREG_PD_v3.md", models={},
               label_provenance="TEXT-DERIVED oracle; selection by model-drafter; owner spot-check pending; no human labels")
    pooled, syn_pairs = [], []
    for model, r in runs.items():
        T, S = r["truth"], r["synth_truth"]
        pre = [i for i, t in T.items() if t["kind"] == "pre"]
        ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
        post = [i for i, t in T.items() if t["kind"] == "post"]

        def eq(x, y):
            return sum(r["real"][i][x] == r["real"][i][y] for i in ctrl)

        r0 = eq("A", "B") / len(ctrl)
        pa = {i: int(r["real"][i]["A"] == T[i]["identity_letter"]) for i in pre}
        pb = {i: (int(r["real"][i]["B"] == T[i]["identity_letter"]) + int(r["real"][i]["B2"] == T[i]["identity_letter"])) / 2
              for i in pre}
        spre = [i for i, t in S.items() if t["type"] == "pre_alias"]
        sa = {i: int(r["synth"][i]["A"] == S[i]["identity_letter"]) for i in spre}
        sb = {i: int(r["synth"][i]["B"] == S[i]["identity_letter"]) for i in spre}
        n_ev = len(r["closed"])
        k_need = next(k for k in range(n_ev + 1) if binom_tail(n_ev, k, 1 / 8) <= 0.05)
        cb_k = sum(v["C_orig"] == r["closed_truth"][e] for e, v in r["closed"].items())
        cr_k = sum(v["C_ren"] == r["closed_truth"][e] for e, v in r["closed"].items())
        cr2_k = sum(v["C_ren2"] == r["closed_truth"][e] for e, v in r["closed"].items())
        gap = (sum(pa.values()) - sum(pb.values())) / len(pre)
        rng = random.Random(20261016)
        boots = sorted(sum(pa[j] - pb[j] for j in (rng.choice(pre) for _ in pre)) / len(pre) for _ in range(5000))
        out["models"][model] = dict(
            R0_valid=r0 >= R0_BAR, R0_strict_95=r0 >= 0.95, R0_A_eq_B=L1.row(eq("A", "B"), len(ctrl)), A_eq_B2=L1.row(eq("A", "B2"), len(ctrl)),
            B_eq_B2=L1.row(eq("B", "B2"), len(ctrl)), pre_items=len(pre), controls=len(ctrl),
            premature_A=L1.row(sum(pa.values()), len(pre)), premature_B_mean=sum(pb.values()) / len(pre),
            gap_A_minus_B_mean=gap, gap_ci95=[boots[125], boots[4875]],
            damage_rate_1_minus_R0=1 - r0, gap_minus_damage=gap - (1 - r0),
            baseline_most_mentioned_premature=sum(T[i]["baseline_letter"] == T[i]["identity_letter"] for i in pre) / len(pre),
            abstain_A=sum(r["real"][i]["A"] == "UNDETERMINED" for i in pre),
            post_reveal_accuracy_A=L1.row(sum(r["real"][i]["A"] == T[i]["truth_letter"] for i in post), len(post)),
            plain_control_accuracy_A=L1.row(sum(r["real"][i]["A"] == T[i]["truth_letter"] for i in ctrl), len(ctrl)),
            plain_control_accuracy_B=L1.row(sum(r["real"][i]["B"] == T[i]["truth_letter"] for i in ctrl), len(ctrl)),
            synthetic_gap=(sum(sa.values()) - sum(sb.values())) / max(len(spre), 1),
            closed_book=dict(events=n_ev, k_needed=k_need, C_orig=cb_k, C_ren=cr_k, C_ren2=cr2_k, memory_present=cb_k >= k_need),
            invalid_answers=sum(v == "INVALID" for d in list(r["real"].values()) + list(r["synth"].values())
                                for v in d.values()))
        if r0 >= R0_BAR:
            pooled += [(i, model, pa[i], pb[i]) for i in pre]
            syn_pairs += [(i, model, sa[i], sb[i]) for i in spre]
    n_valid = len({p[1] for p in pooled})
    verdict = "INCONCLUSIVE (fewer than 3 models passed the 80% renaming-validity bar)"
    pool = {}
    if pooled:
        by, sy = {}, {}
        for i, _m, a, b in pooled:
            by.setdefault(i, []).append(a - b)
        for i, _m, a, b in syn_pairs:
            sy.setdefault(i, []).append(a - b)
        ids, sids = sorted(by), sorted(sy)
        gp = sum(x for v in by.values() for x in v) / sum(len(v) for v in by.values())
        gs = (sum(x for v in sy.values() for x in v) / sum(len(v) for v in sy.values())) if sy else 0.0
        rng = random.Random(20261016)
        gb, db = [], []
        for _ in range(5000):
            si = [rng.choice(ids) for _ in ids]
            g1 = sum(x for i in si for x in by[i]) / sum(len(by[i]) for i in si)
            ss = [rng.choice(sids) for _ in sids] if sids else []
            g2 = (sum(x for i in ss for x in sy[i]) / sum(len(sy[i]) for i in ss)) if ss else 0.0
            gb.append(g1)
            db.append(g1 - g2)
        gb.sort()
        db.sort()
        n_mem = sum(1 for m in out["models"].values() if m["R0_valid"] and m["closed_book"]["memory_present"])
        cond = dict(i=gp >= 0.10 and gb[125] > 0, ii=(gp - gs) > 0 and db[125] > 0, iii=n_mem >= 3)
        pool = dict(models_passing_R0=n_valid, pooled_gap=gp, pooled_gap_ci95=[gb[125], gb[4875]], synthetic_gap=gs,
                    did=gp - gs, did_ci95=[db[125], db[4875]], memory_models_among_R0=n_mem, conditions=cond)
        if n_valid >= 3:
            verdict = ("LEAKAGE SUPPORTED" if all(cond.values()) else
                       "PARTIALLY SUPPORTED" if cond["i"] else "NOT SUPPORTED")
    # secondary: premature rate per event (original names, pooled over models passing R0) vs closed-book recognition
    ev_rate, ev_cb = {}, {}
    for model, r in runs.items():
        if out["models"][model]["R0_valid"]:
            for i, t in r["truth"].items():
                if t["kind"] == "pre":
                    v = ev_rate.setdefault(t["event"], [0, 0])
                    v[0] += int(r["real"][i]["A"] == t["identity_letter"])
                    v[1] += 1
        for e, v in r["closed"].items():
            ev_cb[e] = ev_cb.get(e, 0) + int(v["C_orig"] == r["closed_truth"][e])
    evs = sorted(ev_rate)

    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        rk = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return rk

    if len(evs) >= 3:
        x, y = ranks([ev_rate[e][0] / ev_rate[e][1] for e in evs]), ranks([ev_cb.get(e, 0) for e in evs])
        mx, my = sum(x) / len(x), sum(y) / len(y)
        den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
        rho = sum((a - mx) * (b - my) for a, b in zip(x, y)) / den if den else None
        out["per_event_secondary"] = dict(
            premature_A_by_event={e: ev_rate[e] for e in evs}, models_naming_identity_closed_book=ev_cb,
            spearman_premature_vs_closed_book=rho, n_events=len(evs))
    out["pooled"] = pool
    out["verdict"] = verdict
    (OUT / "analysis.json").write_text(json.dumps(out, indent=1))
    keys = ("R0_valid", "R0_A_eq_B", "B_eq_B2", "gap_A_minus_B_mean", "gap_ci95", "baseline_most_mentioned_premature",
            "invalid_answers", "closed_book")
    print(json.dumps({m: {k: v[k] for k in keys} for m, v in out["models"].items()}, indent=1))
    print(json.dumps(pool, indent=1), "\nVERDICT:", verdict)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("freeze", "verify", "build", "run", "analyze"):
        s = sp.add_parser(n)
        if n in ("verify", "build", "run"):
            s.add_argument("--texts", required=True)
        if n == "run":
            s.add_argument("--ri-db", required=True)
            s.add_argument("--model", required=True)
    a = ap.parse_args()
    dict(freeze=cmd_freeze, verify=cmd_verify, build=cmd_build, run=cmd_run, analyze=cmd_analyze)[a.cmd](a)


if __name__ == "__main__":
    main()
