"""PD reveal benchmark: text-derived disclosure items on famous public-domain novels (implements PREREG_PD v1).

  verify   locates every reveal sentence and cutoff by exact search and prints counts (no model)
  build    writes data/eval/chimera/pd/items_manifest.json (offsets, kinds, distances, hashes; NO novel text)
  run      runs arms A/B (+ closed book + the synthetic unseen-text control) on one local ollama model, or on Luna
  analyze  the pre-registered metrics and the leakage-supported / partial / not-supported decision

LABEL PROVENANCE: text-derived oracle (explicit verbatim reveal sentence + regex-located cutoff); event selection by the
model-drafter, owner spot-check pending; no human labels. Texts are read from a local Gutenberg copy; prompts are built
in memory and never written to disk. No API key is read or printed.

    python scripts/chimera/pd_reveal_benchmark.py verify --texts <dir with pgNNN.txt>
    python scripts/chimera/pd_reveal_benchmark.py build  --texts <dir>
    python scripts/chimera/pd_reveal_benchmark.py run    --texts <dir> --ri-db <scratch RI copy> --model qwen2.5:7b
    python scripts/chimera/pd_reveal_benchmark.py run    --texts <dir> --ri-db <scratch RI copy> --model gpt-5.6-luna --budget-usd 0.04
    python scripts/chimera/pd_reveal_benchmark.py analyze
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
from collections import Counter, defaultdict
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import l1_llm_leakage as L1  # noqa: E402
import l2u_unseen_text as L2U  # noqa: E402
import t4_renaming_v4 as V4  # noqa: E402
import t4_renaming_v5 as V5  # noqa: E402

P = Path("docs/research/preregistrations")
EVENTS = P / "PD_events_v1.json"
PROMPTS = P / "PD_prompts_v1.json"
MANIFEST = P / "MANIFEST_PD.json"
OUT = Path("data/eval/chimera/pd")
SEED_ITEM = 20261017
WINDOW = 1200
LETTERS = "ABCDEFGHIJKL"
HONORIFICS = {"mr", "mrs", "miss", "dr", "sir", "lord", "lady", "madame", "monsieur", "count", "st"}
TOKEN = re.compile(r"[A-Za-z]+")


# ---------------------------------------------------------------- text and events
def load_text(texts: Path, gid: int) -> str:
    t = (texts / f"pg{gid}.txt").read_text(encoding="utf-8").replace("\r", "")
    a, b = t.find("*** START"), t.find("*** END")
    return t[t.find("\n", a) + 1 : b]


def load_events() -> list[dict]:
    raw = EVENTS.read_bytes()
    man = json.loads(MANIFEST.read_text())
    if hashlib.sha256(raw).hexdigest() != man["events_sha256"]:
        sys.exit("REFUSING: PD_events_v1.json does not match MANIFEST_PD.json")
    return json.loads(raw)["events"]


def load_prompts() -> dict:
    raw = PROMPTS.read_bytes()
    if hashlib.sha256(raw).hexdigest() != json.loads(MANIFEST.read_text())["prompts_sha256"]:
        sys.exit("REFUSING: PD_prompts_v1.json does not match MANIFEST_PD.json")
    return json.loads(raw)


def ws_regex(sentence: str) -> re.Pattern:
    return re.compile(r"\s+".join(re.escape(w) for w in sentence.split()))


def spaced(n: int, k: int) -> list[int]:
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def sentence_end(text: str, pos: int) -> int:
    m = re.compile(r"[.!?][”\"’')]*(?:\s|$)").search(text, pos)
    return m.end() if m else len(text)


def locate(ev: dict, text: str) -> dict:
    rv = ws_regex(ev["reveal_sentence"]).search(text)
    assert rv, f"{ev['id']}: reveal sentence not found"
    # anchors may contain line breaks inside the text; chapter headings also occur in the table of contents, so the
    # anchor is the LAST match that starts at or before the reveal sentence (the nearest preceding one)
    cut_re = re.compile(ev["cut"]["regex"].replace(" ", r"\s+"))
    cut_ms = [m for m in cut_re.finditer(text) if m.start() <= rv.end()]
    assert cut_ms, f"{ev['id']}: cut anchor not found"
    cut = cut_ms[-1].start() - ev["cut"]["back"]
    assert cut < rv.start(), f"{ev['id']}: cutoff is not before the reveal sentence"
    alias_re = re.compile("|".join(r"\b" + re.escape(a) + r"\b" for a in sorted(ev["alias"], key=len, reverse=True)))
    mentions = [(m.start(), m.end(), m.group(0)) for m in alias_re.finditer(text)]
    pre = [m for m in mentions if sentence_end(text, m[1]) <= cut]
    post = [m for m in mentions if m[0] > rv.end()]
    ident_tok = [t for t in TOKEN.findall(ev["identity"]) if t[:1].isupper() and t not in {"Sir", "Mr", "Abel"}]
    leaks = 0
    for m in re.finditer(r"[^.!?]*[.!?]+", text[:cut]):
        s = m.group(0)
        if alias_re.search(s) and any(re.search(r"\b" + re.escape(t) + r"\b", s) for t in ident_tok):
            leaks += 1
    return dict(reveal_start=rv.start(), reveal_end=rv.end(), cut=cut, alias_re=alias_re, pre=pre, post=post,
                prefix_sentences_with_alias_and_identity_token=leaks,
                identity_in_prefix=any(re.search(r"\b" + re.escape(t) + r"\b", text[:cut]) for t in ident_tok))


def surfaces_for(name: str) -> list[str]:
    toks = [t for t in TOKEN.findall(name) if t[:1].isupper() and t.lower() not in HONORIFICS and len(t) >= 3]
    return list(dict.fromkeys([name] + toks))


def control_mentions(ev: dict, text: str, cut: int):
    best = None
    for nm in ev["cast"]:
        if nm == ev["identity"]:
            continue
        for sf in surfaces_for(nm):
            ms = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\b" + re.escape(sf) + r"\b", text[:cut])]
            ms = [m for m in ms if sentence_end(text, m[1]) <= cut]
            if best is None or len(ms) > len(best[2]):
                best = (nm, sf, ms)
    nm, _sf, ms = best
    if len(ms) >= 3:
        idx = sorted({round(0.25 * (len(ms) - 1)), round(0.5 * (len(ms) - 1)), round(0.75 * (len(ms) - 1))})
    else:
        idx = list(range(len(ms)))
    return nm, [ms[i] for i in idx]


def build_items(texts: Path):
    items, books = [], {}
    for ev in load_events():
        text = books.setdefault(ev["gutenberg"], load_text(texts, ev["gutenberg"]))
        loc = locate(ev, text)
        pre = [loc["pre"][i] for i in spaced(len(loc["pre"]), 8)]
        post = [loc["post"][i] for i in spaced(len(loc["post"]), 2)]
        cname, cms = control_mentions(ev, text, loc["cut"])
        for kind, ms, truth in (("pre", pre, None), ("post", post, ev["identity"]), ("ctrl", cms, cname)):
            for m in ms:
                items.append(dict(event=ev["id"], kind=kind, start=m[0], end=m[1], surface=m[2], truth=truth,
                                  distance=(loc["cut"] - sentence_end(text, m[1])) if kind == "pre" else None))
    for i, it in enumerate(items):
        it["id"] = f"{it['event']}-{it['kind']}{i:03d}"
    return items, books


def window_for(text: str, it: dict) -> str:
    end = sentence_end(text, it["end"])
    start = max(0, end - WINDOW)
    w = text[start:end]
    a, b = it["start"] - start, it["end"] - start
    return w[:a] + "[[" + w[a:b] + "]]" + w[b:]


def cand_letters(ev: dict, idx: int):
    rng = random.Random(SEED_ITEM + idx)
    names = list(ev["cast"])
    rng.shuffle(names)
    return [(LETTERS[i], n, "0000") for i, n in enumerate(names)]


# ---------------------------------------------------------------- prompts
def make_renamer(text: str):
    toks = TOKEN.findall(text)
    lower = {t for t in toks if t[:1].islower()}
    proper = {t for t in toks if t[:1].isupper() and t.lower() not in lower and len(t) >= 3}
    existing = {t.lower() for t in toks}
    return V5.CipherRenamerV5(proper, V4.honorific_words(), 20261015, existing)


def prompts_for(texts: Path):
    tpl = load_prompts()
    items, books = build_items(texts)
    evs = {e["id"]: e for e in load_events()}
    renamers = {gid: make_renamer(t) for gid, t in books.items()}
    out = []
    for i, it in enumerate(items):
        ev = evs[it["event"]]
        text, pi = books[ev["gutenberg"]], renamers[ev["gutenberg"]]
        cl = cand_letters(ev, i)
        letter_of = {n: L for L, n, _ in cl}
        truth_letter = "UNDETERMINED" if it["kind"] == "pre" else letter_of[it["truth"]]
        win = window_for(text, it)
        pa = L1.fill(tpl["A_B_prefix"], WINDOW=win, SURFACE=it["surface"], CANDIDATES=L1.cand_block(cl))
        pb = L1.fill(tpl["A_B_prefix"], WINDOW=pi.rename(win), SURFACE=pi.rename(it["surface"]),
                     CANDIDATES=L1.cand_block(cl, pi.rename))
        out.append(dict(id=it["id"], event=it["event"], kind=it["kind"], truth_letter=truth_letter,
                        identity_letter=letter_of[ev["identity"]], cands=cl, A=pa, B=pb, distance=it["distance"]))
    cb = []
    for k, ev in enumerate(load_events()):
        pi = renamers[ev["gutenberg"]]
        cl = cand_letters(ev, 9000 + k)
        letter_of = {n: L for L, n, _ in cl}
        cb.append(dict(event=ev["id"], identity_letter=letter_of[ev["identity"]], cands=cl,
                       C_orig=L1.fill(tpl["C_closed_book"], SURFACE=ev["alias"][0], CANDIDATES=L1.cand_block(cl)),
                       C_ren=L1.fill(tpl["C_closed_book"], SURFACE=pi.rename(ev["alias"][0]),
                                     CANDIDATES=L1.cand_block(cl, pi.rename))))
    return out, cb


def synthetic_prompts(ri_db: str):
    tpl = L2U.tpl_v1()
    protected = V5.build_v5(ri_db)[1]
    items = L2U.make_items()
    ps = L2U.build_prompts(items, tpl, protected)
    for it, p in zip(items, ps):
        w = it["world"]
        p["identity_letter"] = None
        if it["type"] == "pre_alias":
            y = w.names[w.reveals[0]["y"]]
            p["identity_letter"] = next(L for L, n, _ in p["cands"] if n == y)
    return ps


# ---------------------------------------------------------------- commands
def cmd_verify(args):
    texts = Path(args.texts)
    for ev in load_events():
        text = load_text(texts, ev["gutenberg"])
        loc = locate(ev, text)
        print(f"{ev['id']}: reveal@{loc['reveal_start']} cut@{loc['cut']} pre-alias mentions {len(loc['pre'])} "
              f"post {len(loc['post'])} | identity token in prefix: {loc['identity_in_prefix']} | "
              f"prefix sentences with alias AND identity token: {loc['prefix_sentences_with_alias_and_identity_token']}")


def cmd_build(args):
    items, _ = build_items(Path(args.texts))
    OUT.mkdir(parents=True, exist_ok=True)
    c = Counter((i["event"], i["kind"]) for i in items)
    slim = []
    for i in items:
        d = {k: v for k, v in i.items() if k != "surface"}
        d["surface_sha"] = hashlib.sha256(i["surface"].encode()).hexdigest()[:12]
        slim.append(d)
    man = dict(label_provenance="TEXT-DERIVED oracle; selection by model-drafter; owner spot-check pending; no novel text here",
               n_items=len(items), counts={f"{e}|{k}": v for (e, k), v in sorted(c.items())}, items=slim)
    (OUT / "items_manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(man["counts"], indent=1), "total", len(items))


def local_run(args, real, cb, syn):
    import httpx

    host = "http://127.0.0.1:11434"
    opts = {"temperature": 0, "seed": 20261016, "num_predict": 8, "num_ctx": 4096}

    def ask(c, prompt):
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 1.0:
                sys.exit("stopping: available RAM below 1 GiB")
        r = c.post(f"{host}/api/chat", json=dict(model=args.model, stream=False, options=opts,
                                                  messages=[dict(role="user", content=prompt)]))
        r.raise_for_status()
        return r.json()["message"]["content"]

    def parse(text, cands):
        m = re.match(r"\W*(UNDETERMINED|[A-Z])\b", text.strip())
        t = m.group(1) if m else ""
        return t if (t == "UNDETERMINED" or t in {L for L, _n, _i in cands}) else "INVALID"

    res = dict(model=args.model, options=opts, real={}, closed={}, synth={}, status="COMPLETE")
    with httpx.Client(timeout=180.0) as c:
        first = True
        for p in real:
            res["real"][p["id"]] = {arm: parse(ask(c, p[arm]), p["cands"]) for arm in ("A", "B")}
            if first:
                ps = c.get(f"{host}/api/ps").json().get("models", [])
                m = next((x for x in ps if x["name"] == args.model), None)
                if m is None or m.get("size_vram", 0) < m.get("size", 1):
                    sys.exit(f"stopping: {args.model} not fully in VRAM; no CPU offload allowed")
                first = False
        for p in cb:
            res["closed"][p["event"]] = {arm: parse(ask(c, p[arm]), p["cands"]) for arm in ("C_orig", "C_ren")}
        for p in syn:
            res["synth"][p["id"]] = {arm: parse(ask(c, p[arm]), p["cands"]) for arm in ("A", "B")}
        c.post(f"{host}/api/generate", json=dict(model=args.model, keep_alive=0, prompt=""))  # unload
    return res


def luna_run(args, real, cb, syn):
    import httpx

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set in the environment")
    budget = L1.Budget(args.budget_usd)
    res = dict(model=L1.MODEL, real={}, closed={}, synth={}, status="COMPLETE")
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as c:
        del key

        def go(prompt, cands):
            if not budget.can(L1.est_tokens(prompt), L1.CAPS["A"]):
                res["status"] = "STOPPED_AT_BUDGET"
                return None
            r = L1.call_model(c, prompt, L1.CAPS["A"])
            budget.calls += 1
            budget.tok_in += r["tok_in"]
            budget.tok_out += r["tok_out"]
            budget.actual += r["tok_in"] * L1.PRICE_IN + r["tok_out"] * L1.PRICE_OUT
            return L1.parse_letter(r["text"], cands)

        for section, rows, arms, key_of in (("real", real, ("A", "B"), lambda p: p["id"]),
                                            ("closed", cb, ("C_orig", "C_ren"), lambda p: p["event"]),
                                            ("synth", syn, ("A", "B"), lambda p: p["id"])):
            for p in rows:
                got = [go(p[a], p["cands"]) for a in arms]
                if any(g is None for g in got):
                    break
                res[section][key_of(p)] = dict(zip(arms, got))
    res.update(spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in, tok_out=budget.tok_out)
    return res


def cmd_run(args):
    real, cb = prompts_for(Path(args.texts))
    syn = synthetic_prompts(args.ri_db)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"run_{args.model.replace(':', '_').replace('/', '_')}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    res = luna_run(args, real, cb, syn) if args.model == "gpt-5.6-luna" else local_run(args, real, cb, syn)
    res["truth"] = {p["id"]: dict(truth_letter=p["truth_letter"], identity_letter=p["identity_letter"],
                                  kind=p["kind"], event=p["event"], distance=p["distance"]) for p in real}
    res["closed_truth"] = {p["event"]: p["identity_letter"] for p in cb}
    res["synth_truth"] = {p["id"]: dict(type=p["type"], truth_letter=p["truth_letter"],
                                        identity_letter=p["identity_letter"]) for p in syn}
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "| real", len(res["real"]), "closed", len(res["closed"]), "synth", len(res["synth"]),
          "| status", res["status"])


# ---------------------------------------------------------------- analysis
def sign_test(n10: int, n01: int) -> float:
    n = n10 + n01
    if n == 0:
        return 1.0
    k = min(n10, n01)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2**n)


def cmd_analyze(args):
    runs = {}
    for f in sorted(OUT.glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    out: dict = dict(preregistration="PREREG_PD_reveal_benchmark.md v1", models={},
                     label_provenance="TEXT-DERIVED oracle; selection by model-drafter; owner spot-check pending; no human labels")
    pooled_pairs, syn_pairs = [], []
    for model, r in runs.items():
        T = r["truth"]
        pre = [i for i, t in T.items() if t["kind"] == "pre"]
        ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
        post = [i for i, t in T.items() if t["kind"] == "post"]
        same = sum(r["real"][i]["A"] == r["real"][i]["B"] for i in ctrl)
        valid = bool(ctrl) and same / len(ctrl) >= 0.95
        pa = {i: int(r["real"][i]["A"] == T[i]["identity_letter"]) for i in pre}
        pb = {i: int(r["real"][i]["B"] == T[i]["identity_letter"]) for i in pre}
        n10 = sum(pa[i] == 1 and pb[i] == 0 for i in pre)
        n01 = sum(pa[i] == 0 and pb[i] == 1 for i in pre)
        gap = (sum(pa.values()) - sum(pb.values())) / max(len(pre), 1)
        rng = random.Random(20261016)
        boots = sorted(sum(pa[j] - pb[j] for j in (rng.choice(pre) for _ in pre)) / len(pre) for _ in range(5000))
        S = r["synth_truth"]
        spre = [i for i, t in S.items() if t["type"] == "pre_alias"]
        sa = {i: int(r["synth"][i]["A"] == S[i]["identity_letter"]) for i in spre}
        sb = {i: int(r["synth"][i]["B"] == S[i]["identity_letter"]) for i in spre}
        cb_k = sum(v["C_orig"] == r["closed_truth"][e] for e, v in r["closed"].items())
        cr_k = sum(v["C_ren"] == r["closed_truth"][e] for e, v in r["closed"].items())
        by_bin = {}
        for lab, lo, hi in (("<2k", 0, 2000), ("2k-20k", 2000, 20000), (">20k", 20000, 10**9)):
            ids = [i for i in pre if lo <= T[i]["distance"] < hi]
            by_bin[lab] = dict(n=len(ids), A=sum(pa[i] for i in ids), B=sum(pb[i] for i in ids))
        out["models"][model] = dict(
            R0_valid=valid, controls_A_equals_B=L1.row(same, len(ctrl)), pre_items=len(pre),
            premature_A=L1.row(sum(pa.values()), len(pre)), premature_B=L1.row(sum(pb.values()), len(pre)),
            gap_A_minus_B=gap, gap_ci95=[boots[125], boots[4875]], discordant_A_only=n10, discordant_B_only=n01,
            sign_test_p=sign_test(n10, n01),
            abstain_A=sum(r["real"][i]["A"] == "UNDETERMINED" for i in pre),
            abstain_B=sum(r["real"][i]["B"] == "UNDETERMINED" for i in pre),
            post_reveal_accuracy_A=L1.row(sum(r["real"][i]["A"] == T[i]["truth_letter"] for i in post), len(post)),
            plain_control_accuracy_A=L1.row(sum(r["real"][i]["A"] == T[i]["truth_letter"] for i in ctrl), len(ctrl)),
            by_distance=by_bin,
            synthetic=dict(pre_items=len(spre), premature_A=sum(sa.values()), premature_B=sum(sb.values()),
                           gap=(sum(sa.values()) - sum(sb.values())) / max(len(spre), 1)),
            closed_book=dict(events=len(r["closed"]), C_orig_names_identity=cb_k, C_ren_names_identity=cr_k,
                             memory_present=bool(cb_k >= 3)),
            invalid_answers=sum(v == "INVALID" for d in list(r["real"].values()) + list(r["synth"].values())
                                for v in d.values()))
        if valid:
            pooled_pairs += [(i, model, pa[i], pb[i]) for i in pre]
            syn_pairs += [(i, model, sa[i], sb[i]) for i in spre]
    if pooled_pairs:
        items = sorted({p[0] for p in pooled_pairs})
        by_item = defaultdict(list)
        for i, _m, a, b in pooled_pairs:
            by_item[i].append(a - b)
        s_items = sorted({p[0] for p in syn_pairs})
        s_by = defaultdict(list)
        for i, _m, a, b in syn_pairs:
            s_by[i].append(a - b)
        rng, rng2 = random.Random(20261016), random.Random(20261017)
        pooled_gap = sum(sum(v) for v in by_item.values()) / sum(len(v) for v in by_item.values())
        s_gap = (sum(sum(v) for v in s_by.values()) / sum(len(v) for v in s_by.values())) if s_by else 0.0
        gaps, dids = [], []
        for _ in range(5000):
            pick = [rng.choice(items) for _ in items]
            g = sum(sum(by_item[i]) for i in pick) / sum(len(by_item[i]) for i in pick)
            sg = 0.0
            if s_items:
                sp = [rng2.choice(s_items) for _ in s_items]
                sg = sum(sum(s_by[i]) for i in sp) / sum(len(s_by[i]) for i in sp)
            gaps.append(g)
            dids.append(g - sg)
        gaps.sort()
        dids.sort()
        n_mem = sum(1 for m in out["models"].values() if m["R0_valid"] and m["closed_book"]["memory_present"])
        c1 = pooled_gap >= 0.10 and gaps[125] > 0
        c2 = (pooled_gap - s_gap) > 0 and dids[125] > 0
        c3 = n_mem >= 3
        verdict = "LEAKAGE SUPPORTED" if (c1 and c2 and c3) else ("PARTIALLY SUPPORTED" if c1 else "NOT SUPPORTED")
        out["pooled"] = dict(
            models_passing_R0=len({p[1] for p in pooled_pairs}), pooled_gap=pooled_gap,
            pooled_gap_ci95=[gaps[125], gaps[4875]], synthetic_gap=s_gap, did=pooled_gap - s_gap,
            did_ci95=[dids[125], dids[4875]], models_with_memory_present_among_R0=n_mem,
            conditions=dict(i_gap_ge_10pts_ci_above_0=c1, ii_did_positive_ci_excludes_0=c2,
                            iii_memory_present_in_ge_3_models=c3), verdict=verdict)
    (OUT / "analysis.json").write_text(json.dumps(out, indent=2, default=str))
    brief = {m: {k: v[k] for k in ("R0_valid", "pre_items", "premature_A", "premature_B", "gap_A_minus_B", "gap_ci95",
                                   "sign_test_p", "closed_book", "synthetic")} for m, v in out["models"].items()}
    print(json.dumps(dict(pooled=out.get("pooled"), models=brief), indent=1, default=str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["verify", "build", "run", "analyze"])
    ap.add_argument("--texts", default="")
    ap.add_argument("--ri-db", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--budget-usd", type=float, default=0.0)
    args = ap.parse_args()
    {"verify": cmd_verify, "build": cmd_build, "run": cmd_run, "analyze": cmd_analyze}[args.cmd](args)


if __name__ == "__main__":
    main()
