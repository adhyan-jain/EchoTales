"""Confirmatory study runner (PREREG_PD_CONFIRM_v2_L40S.md and addenda 1 to 3): E1 + M2 arms, E4 mitigation arms, E5 recap and profile
generation with the spoiler check, and the faithfulness judge, all through the pod router (pod_router.py).

Callers: run by hand after pd_confirm_mine.py freeze (the events file PD_confirm_events_v1.json must match its hash in
MANIFEST_PD_CONFIRM_v2.json) or, for E2, on the LLM-authored stories events file. Reuses the frozen PD builders unchanged except for two
declared patches of module globals: the item counts per event (4 pre-reveal, 1 post-reveal, 2 controls of one cast name, as in the
pre-registration, instead of 8/2/8 of the exploratory sets) and the event loader (reads the confirmatory events file). Outputs under
data/eval/chimera/confirm/<tag>/. Label provenance: TEXT-DERIVED oracle, model-selected events, no human labels.

  e1      --model M      A, B, B2, B3 arms on every pre/post/control item, alias-only closed book, title-assisted memory probe M2
  e4      --model M      open-name arms O, P1 (plain instruction), P2 (cue-preserving pseudonyms), P3 (cipher) on test-split items
  e5      --model M      recap and profile generation (O, P1, P2) on the E5 events (addendum 3)
  e5judge --model J --of N   faithfulness judge J over the outputs of model N
Common: --events FILE --texts DIR --tag NAME (defaults: the main study).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_llm_leakage as L1  # noqa: E402
import pd_confirm_mine as M  # noqa: E402
import pd_reveal_benchmark as PD  # noqa: E402
import pd_v3 as V3  # noqa: E402
import pd_v5_cuepres as V5  # noqa: E402
import pd_v6 as V6  # noqa: E402

P = Path("docs/research/preregistrations")
EVENTS = P / "PD_confirm_events_v1.json"
MANIFEST = P / "MANIFEST_PD_CONFIRM_v2.json"
TEXTS = Path("data/raw/pd_confirm/texts")
OUT = Path("data/eval/chimera/confirm")
PROMPTS = json.loads((P / "PD_confirm_prompts_v1.json").read_text())
PLAIN = PROMPTS["plain_instruction_prefix"]
E5_N, E5_CHARS, E5_SEED = 24, 10000, 20261101
WORKERS = 12


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spaced(n: int, k: int) -> list[int]:
    """PD.spaced divides by zero for k == 1; one item is taken from the middle of the available mentions."""
    return [n // 2] if (k == 1 and n) else ([] if n == 0 else PD.spaced(n, k))


def build_items(texts: Path):
    """pd_v3.build_items with the pre-registered per-event counts: 4 pre-reveal (evenly spaced), 1 post-reveal, controls from V3.controls
    (patched to 1 name x 2 mentions)."""
    items, books = [], {}
    for ev in V3.load_events():
        text = books.setdefault(ev["gutenberg"], PD.load_text(texts, ev["gutenberg"]))
        loc = PD.locate(ev, text)
        pre = [loc["pre"][i] for i in spaced(len(loc["pre"]), 4)]
        post = [loc["post"][i] for i in spaced(len(loc["post"]), 1)]
        for m in pre:
            items.append(dict(event=ev["id"], kind="pre", start=m[0], end=m[1], surface=m[2], truth=None,
                              distance=loc["cut"] - PD.sentence_end(text, m[1])))
        for m in post:
            items.append(dict(event=ev["id"], kind="post", start=m[0], end=m[1], surface=m[2], truth=ev["identity"], distance=None))
        for nm, m in V3.controls(ev, text, loc["cut"]):
            items.append(dict(event=ev["id"], kind="ctrl", start=m[0], end=m[1], surface=m[2], truth=nm, distance=None))
    for i, it in enumerate(items):
        it["id"] = f"{it['event']}-{it['kind']}{i:03d}"
    return items, books


def setup(a):
    ev_path = Path(a.events)
    if ev_path == EVENTS:
        files = json.loads(MANIFEST.read_text())["files_sha256"]
        if sha(EVENTS) != files.get("PD_confirm_events_v1.json"):
            sys.exit("REFUSING: events file does not match the frozen hash in MANIFEST_PD_CONFIRM_v2.json")
        for name, h in files.items():
            if name.startswith("PD_prompts") and sha(P / name) != h:
                sys.exit(f"REFUSING: {name} changed since the freeze")
    evs = json.loads(ev_path.read_text())["events"]
    V3.load_events = lambda: evs
    V3.build_items = build_items
    V3.CTRL_NAMES, V3.CTRL_PER_NAME = 1, 2
    V6.check_frozen = lambda: None  # prompt files were hash-checked above
    out = OUT / a.tag
    out.mkdir(parents=True, exist_ok=True)
    return evs, Path(a.texts), out


def save_name(out: Path, kind: str, model: str) -> Path:
    return out / f"{kind}_{model}.json"


# ---------------------------------------------------------------- E1 + M2
def cmd_e1(a):
    _evs, texts, out = setup(a)
    path = save_name(out, "e1", a.model)
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    real, cb, m2, _ = V6.prompts(texts)
    js = V6.jobs(real, cb, m2)
    pod = M.Pod()
    pod.ensure(a.model)
    t0 = time.time()

    def work(j):
        _sec, _kid, _arm, prompt, cands = j
        allowed = [L for L, _n, _i in cands] + ["UNDETERMINED"]
        schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": allowed}}, "required": ["answer"]}
        return V6.parse(pod.chat(a.model, prompt, 32, schema), cands)

    res = dict(model=a.model, set=a.tag, real={}, closed={}, m2={}, status="COMPLETE", calls=len(js))
    with ThreadPoolExecutor(WORKERS) as ex:
        for n, (j, ans) in enumerate(zip(js, ex.map(work, js)), 1):
            res[j[0]].setdefault(j[1], {})[j[2]] = ans
            if n % 400 == 0:
                print(f"{a.model} e1 {n}/{len(js)} {time.time() - t0:.0f}s", flush=True)
    res["wall_seconds"] = round(time.time() - t0, 1)
    res["truth"] = {p["id"]: dict(truth_letter=p["truth_letter"], identity_letter=p["identity_letter"], kind=p["kind"], event=p["event"],
                                  distance=p["distance"], baseline_letter=p["baseline_letter"]) for p in real}
    res["closed_truth"] = {p["event"]: p["identity_letter"] for p in cb}
    res["m2_truth"] = {p["event"]: p["identity_letter"] for p in m2}
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "calls", len(js), "wall", res["wall_seconds"], "s", flush=True)


# ---------------------------------------------------------------- E4
def norm(x: str) -> str:
    return re.sub(r"\W+", " ", x or "").strip().lower()


def parse_open(txt: str, names: list[str]) -> str:
    m = re.search(r'"answer"\s*:\s*"([^"]*)"', txt)
    t = norm(m.group(1) if m else "")
    if t == "undetermined":
        return "UNDETERMINED"
    for n in names:
        if norm(n) == t:
            return n
    return "INVALID"


def e4_rows(evs, texts):
    items, books = V3.build_items(texts)
    byid = {e["id"]: e for e in evs}
    maps, _ = V5.build_maps(list(evs), books)
    rn = V3.renamers_for(books)
    tpl = PROMPTS["open_name"]
    rows = []
    for i, it in enumerate(items):
        ev = byid[it["event"]]
        if ev.get("split") != "test":
            continue
        gid = ev["gutenberg"]
        r1, _r2 = rn[gid]
        b3 = V5.make_b3(r1, maps[gid])
        cl = PD.cand_letters(ev, i)
        names = [n for _L, n, _i in cl]
        win = PD.window_for(books[gid], it)
        truth = None if it["kind"] == "pre" else it["truth"]
        for arm, tf, pref in (("O", lambda x: x, ""), ("P1", lambda x: x, PLAIN), ("P2", b3, ""), ("P3", r1.rename, "")):
            prompt = pref + L1.fill(tpl, WINDOW=tf(win), SURFACE=tf(it["surface"]), CANDIDATE_NAMES="\n".join(tf(n) for n in names))
            rows.append(dict(id=it["id"], event=it["event"], kind=it["kind"], arm=arm, prompt=prompt, names=[tf(n) for n in names],
                             identity=tf(ev["identity"]), truth=tf(truth) if truth else None))
    return rows


def cmd_e4(a):
    evs, texts, out = setup(a)
    path = save_name(out, "e4", a.model)
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    rows = e4_rows(evs, texts)
    pod = M.Pod()
    pod.ensure(a.model)
    t0 = time.time()

    def work(r):
        return parse_open(pod.chat(a.model, r["prompt"], 48), r["names"])

    res = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for n, (r, ans) in enumerate(zip(rows, ex.map(work, rows)), 1):
            res.append(dict(id=r["id"], event=r["event"], kind=r["kind"], arm=r["arm"], answer=ans, identity=r["identity"], truth=r["truth"]))
            if n % 400 == 0:
                print(f"{a.model} e4 {n}/{len(rows)} {time.time() - t0:.0f}s", flush=True)
    path.write_text(json.dumps(dict(model=a.model, set=a.tag, rows=res, wall_seconds=round(time.time() - t0, 1)), indent=1))
    print("wrote", path, len(rows), "calls", flush=True)


# ---------------------------------------------------------------- E5
def toks(s: str) -> set[str]:
    return {t for t in re.findall(r"\b[A-Z][a-z]{2,}\b", s)}


def e5_events(evs, texts):
    """Up to E5_N test events whose identity tokens are absent from the 10,000-character input (addendum 3), seeded order."""
    ok = []
    for ev in sorted((e for e in evs if e.get("split") == "test"), key=lambda e: e["id"]):
        text = PD.load_text(texts, ev["gutenberg"])
        cut = PD.locate(ev, text)["cut"]
        inp = text[max(0, cut - E5_CHARS):cut]
        if not any(re.search(r"\b" + re.escape(t) + r"\b", inp) for t in toks(ev["identity"])):
            ok.append((ev, inp))
    random.Random(E5_SEED).shuffle(ok)
    return ok[:E5_N]


def cmd_e5(a):
    evs, texts, out = setup(a)
    path = save_name(out, "e5", a.model)
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    sel = e5_events(evs, texts)
    books = {ev["gutenberg"]: PD.load_text(texts, ev["gutenberg"]) for ev, _ in sel}
    maps, _ = V5.build_maps([e for e in evs if e["gutenberg"] in books], books)
    rn = V3.renamers_for(books)
    jobs = []
    for ev, inp in sel:
        gid = ev["gutenberg"]
        b3 = V5.make_b3(rn[gid][0], maps[gid])
        for task, key, mx in (("recap", "e5_recap", 450), ("profile", "e5_profile", 200)):
            for cond, tf, pref in (("O", lambda x: x, ""), ("P1", lambda x: x, PLAIN), ("P2", b3, "")):
                x = tf(inp)
                prompt = pref + L1.fill(PROMPTS[key], PREFIX=x, ALIAS=tf(ev["alias"][0]))
                jobs.append(dict(event=ev["id"], task=task, cond=cond, prompt=prompt, max_tokens=mx, inp=x, id_tokens=sorted(toks(tf(ev["identity"])))))
    pod = M.Pod()
    pod.ensure(a.model)
    t0 = time.time()

    def work(j):
        return pod.chat(a.model, j["prompt"], j["max_tokens"])

    rows = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for n, (j, o) in enumerate(zip(jobs, ex.map(work, jobs)), 1):
            spoiler = bool((set(j["id_tokens"]) & toks(o)) - toks(j["inp"]))
            rows.append(dict(event=j["event"], task=j["task"], cond=j["cond"], output=o, spoiler=spoiler, id_tokens=j["id_tokens"]))
            if n % 50 == 0:
                print(f"{a.model} e5 {n}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    path.write_text(json.dumps(dict(model=a.model, set=a.tag, events=len(sel), rows=rows, wall_seconds=round(time.time() - t0, 1)), indent=1))
    print("wrote", path, len(rows), "outputs; events", len(sel), flush=True)


def cmd_e5judge(a):
    evs, texts, out = setup(a)
    src = json.loads(save_name(out, "e5", a.of).read_text())
    path = out / f"e5judge_{a.model}_of_{a.of}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists")
    sel = {ev["id"]: (ev, inp) for ev, inp in e5_events(evs, texts)}
    books = {ev["gutenberg"]: PD.load_text(texts, ev["gutenberg"]) for ev, _ in sel.values()}
    maps, _ = V5.build_maps([e for e in evs if e["gutenberg"] in books], books)
    rn = V3.renamers_for(books)
    pod = M.Pod()
    pod.ensure(a.model)
    schema = {"type": "object", "properties": {"supported": {"type": "integer"}, "unsupported": {"type": "integer"}}, "required": ["supported", "unsupported"]}

    def work(r):
        ev, inp = sel[r["event"]]
        b3 = V5.make_b3(rn[ev["gutenberg"]][0], maps[ev["gutenberg"]])
        x = b3(inp) if r["cond"] == "P2" else inp
        m = M.parse_json(pod.chat(a.model, L1.fill(PROMPTS["faithfulness_judge"], PREFIX=x, RECAP=r["output"]), 60, schema)) or {}
        return m.get("supported"), m.get("unsupported")

    with ThreadPoolExecutor(WORKERS) as ex:
        res = list(ex.map(work, src["rows"]))
    rows = [dict(event=r["event"], task=r["task"], cond=r["cond"], supported=s, unsupported=u) for r, (s, u) in zip(src["rows"], res)]
    path.write_text(json.dumps(dict(judge=a.model, of=a.of, rows=rows), indent=1))
    print("wrote", path, len(rows), flush=True)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("e1", "e4", "e5", "e5judge"):
        s = sp.add_parser(n)
        s.add_argument("--model", required=True)
        s.add_argument("--events", default=str(EVENTS))
        s.add_argument("--texts", default=str(TEXTS))
        s.add_argument("--tag", default="main")
        if n == "e5judge":
            s.add_argument("--of", required=True)
    a = ap.parse_args()
    dict(e1=cmd_e1, e4=cmd_e4, e5=cmd_e5, e5judge=cmd_e5judge)[a.cmd](a)


if __name__ == "__main__":
    main()
