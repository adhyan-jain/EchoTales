"""Run an existing PD item set (v6 or v7) against an OpenAI-compatible endpoint (vLLM on a RunPod pod) and summarise it.

EXPLORATORY: the model (Qwen2.5-32B-Instruct-AWQ) was not in the PD v6/v7 pre-registrations, so nothing here changes their verdicts or
pooled files. Output goes to data/eval/chimera/remote/<set>/ only; the item builders, arms, prompts and answer parsing are the frozen
v6/v7 ones (imported, not copied), so the numbers are comparable to the local-model runs. Same T=0 JSON-enum decoding as the ollama runs
(guided JSON schema whose enum is the candidate letters plus UNDETERMINED), seed 20261016, max 32 new tokens.

Commands:
  run     --set v2|v3|v6|v7 --texts DIR --served-name qwen32b [--workers 12] [--max-minutes 40]
  analyze --set v2|v3|v6|v7 --served-name qwen32b
Endpoint and key come from RUNPOD_BASE_URL / RUNPOD_VLLM_KEY in the environment (source .env in a subshell; never printed).
Spend: wall time x the pod's hourly rate (1.13 USD/h for L40S incl. disks) is written to the run file; the pod is billed by the hour, not per call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

POD_RATE_USD_PER_H = 1.13


def load(set_name: str):
    if set_name == "v7":
        import pd_v7 as V7  # noqa: F401  (patches pd_v6 globals to the v7 files and arms)
        import pd_v6 as V6
    else:
        import pd_v6 as V6
    if set_name == "v3":  # pd_v6 import re-points pd_v3's globals at the v6 files; put them back
        V6.V3.EVENT_FILES = [V6.P / "PD_events_v3_additions.json"]
        V6.V3.MANIFEST = V6.P / "MANIFEST_PD_v3.json"
        V6.V3.OUT = Path("data/eval/chimera/pd_v3")
    return V6


def build(set_name: str, V6, texts: Path):
    """-> real, closed-book, m2, job list. v2 and v3 have A/B/B2 arms and the alias-only closed book, no title probe and no B3 here."""
    if set_name in ("v2", "v3"):
        import pd_v2 as PV2
        mod = PV2 if set_name == "v2" else V6.V3
        real, cb = mod.prompts(texts)
        js = [("real", p["id"], a, p[a], p["cands"]) for p in real for a in ("A", "B", "B2")]
        js += [("closed", p["event"], a, p[a], p["cands"]) for p in cb for a in V6.CLOSED_ARMS]
        return real, cb, [], js
    real, cb, m2, _ = V6.prompts(texts)
    return real, cb, m2, V6.jobs(real, cb, m2)


def out_dir(set_name: str) -> Path:
    d = Path("data/eval/chimera/remote") / set_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def call(client, base, key, model, prompt, cands, retries=3):
    allowed = [L for L, _n, _i in cands] + ["UNDETERMINED"]
    body = dict(model=model, messages=[dict(role="user", content=prompt)], temperature=0, seed=20261016, max_tokens=32,
                response_format=dict(type="json_schema", json_schema=dict(
                    name="answer", schema={"type": "object", "properties": {"answer": {"type": "string", "enum": allowed}},
                                           "required": ["answer"]})))
    last = None
    k = 0
    while k < retries:
        t0 = time.time()
        try:
            r = client.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 503 and "loading" in r.text:  # pod_router is swapping models; not a failure, wait and retry
                time.sleep(10)
                continue
            if r.status_code in (401, 403):
                sys.exit(f"stopping: endpoint refused the key (HTTP {r.status_code})")
            r.raise_for_status()
            j = r.json()
            txt = j["choices"][0]["message"]["content"] or ""
            try:
                a = json.loads(txt).get("answer", "")
            except ValueError:
                a = "INVALID"
            return (a if a in allowed else "INVALID"), time.time() - t0, j.get("usage", {})
        except Exception as e:  # network or 5xx: back off and retry, never silently drop
            last = e
            k += 1
            time.sleep(2 * k)
    return "ERROR:" + type(last).__name__, 0.0, {}


def ensure_model(client, base, key, model, max_wait_s=1500):
    """Block until the pod router has `model` loaded (it answers 503 while swapping); stops if the router reports a load error."""
    t0 = time.time()
    probe = dict(model=model, messages=[dict(role="user", content="Say OK.")], max_tokens=3, temperature=0)
    while time.time() - t0 < max_wait_s:
        r = client.post(f"{base}/chat/completions", json=probe, headers={"Authorization": f"Bearer {key}"})
        if r.status_code == 200:
            return round(time.time() - t0, 1)
        if r.status_code in (401, 403):
            sys.exit("stopping: endpoint refused the key")
        if r.status_code == 503 and '"detail":"' in r.text.replace(" ", ""):
            sys.exit(f"stopping: model failed to load: {r.text[:200]}")
        time.sleep(10)
    sys.exit(f"stopping: {model} not ready after {max_wait_s} s")


def cmd_run(a):
    import httpx

    V6 = load(a.set)
    base, key = os.environ["RUNPOD_BASE_URL"].rstrip("/"), os.environ["RUNPOD_VLLM_KEY"]
    real, cb, m2, js = build(a.set, V6, Path(a.texts))
    path = out_dir(a.set) / f"run_{a.served_name}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    deadline = time.time() + a.max_minutes * 60
    res = dict(model=a.served_name, exploratory=True, real={}, closed={}, m2={}, status="COMPLETE", calls=len(js),
               decoding="T=0 seed 20261016 guided JSON enum max_tokens 32 (vLLM)")
    lat, tok_in, tok_out, done = [], 0, 0, 0
    t_start = time.time()
    with httpx.Client(timeout=120.0, limits=httpx.Limits(max_connections=a.workers)) as c, ThreadPoolExecutor(a.workers) as pool:
        futs = []
        for sec, kid, arm, prompt, cands in js:
            futs.append((sec, kid, arm, pool.submit(call, c, base, key, a.served_name, prompt, cands)))
        for sec, kid, arm, f in futs:
            ans, dt, usage = f.result()
            res[sec].setdefault(kid, {})[arm] = ans
            lat.append(dt)
            tok_in += usage.get("prompt_tokens", 0)
            tok_out += usage.get("completion_tokens", 0)
            done += 1
            if done % 100 == 0:
                print(f"{done}/{len(js)} calls, {time.time() - t_start:.0f}s", flush=True)
            if time.time() > deadline:
                res["status"] = "STOPPED_AT_TIME_LIMIT"
                for _s, _k, _a, g in futs:
                    g.cancel()
                break
    wall = time.time() - t_start
    res.update(wall_seconds=round(wall, 1), calls_done=done, tok_in=tok_in, tok_out=tok_out,
               mean_latency_s=round(sum(lat) / max(1, len(lat)), 3), workers=a.workers,
               est_pod_cost_usd=round(wall / 3600 * POD_RATE_USD_PER_H, 3), errors=sum(1 for x in lat if x == 0.0))
    res["truth"] = {p["id"]: dict(truth_letter=p["truth_letter"], identity_letter=p["identity_letter"], kind=p["kind"], event=p["event"],
                                  distance=p["distance"], baseline_letter=p["baseline_letter"]) for p in real}
    res["closed_truth"] = {p["event"]: p["identity_letter"] for p in cb}
    res["m2_truth"] = {p["event"]: p["identity_letter"] for p in m2}
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "| status", res["status"], "| wall s", res["wall_seconds"], "| calls/s", round(done / wall, 2),
          "| est pod cost USD", res["est_pod_cost_usd"])


def cmd_analyze(a):
    V6 = load(a.set)
    r = json.loads((out_dir(a.set) / f"run_{a.served_name}.json").read_text())
    T, arms = r["truth"], (("A", "B", "B2") if a.set in ("v2", "v3") else V6.REAL_ARMS)
    pre = [i for i, t in T.items() if t["kind"] == "pre"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
    g2a = sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl)
    rows = {}
    for i in pre:
        h = {arm: int(r["real"][i][arm] == T[i]["identity_letter"]) for arm in arms}
        h["B"] = (h["B"] + int(r["real"][i]["B2"] == T[i]["identity_letter"])) / 2
        h.setdefault("B3", h["B"])  # v7 has no B3 arm; unused there
        rows.setdefault(T[i]["event"], []).append(h)
    n_ev = len({t["event"] for t in T.values()})
    k = V6.binom_k(n_ev)
    m2c = {x: sum(r["m2"][e][x] == r["m2_truth"][e] for e in r["m2_truth"]) for x in V6.M2_ARMS} if r["m2_truth"] else {"M2_orig": 0}
    cbc = {x: sum(r["closed"][e][x] == r["closed_truth"][e] for e in r["closed_truth"]) for x in V6.CLOSED_ARMS}
    acc = {x: round(sum(r["real"][i][x] == T[i]["truth_letter"] for i in ctrl) / len(ctrl), 4) for x in arms}
    out = dict(exploratory=True, set=a.set, model=a.served_name, label_provenance="TEXT-DERIVED oracle; model-selected; no human labels",
               G2a_B_eq_B2_plain_controls=round(g2a, 4), G2b="not run for this model (needs the PD v3 synthetic items)",
               events=n_ev, M2=m2c, M2_k_needed=k, M2_memory_present=m2c["M2_orig"] >= k, alias_only_closed_book=cbc, ctrl_acc=acc,
               cluster=V6.cluster(rows), invalid=sum(v == "INVALID" for d in r["real"].values() for v in d.values()),
               wall_seconds=r["wall_seconds"], calls=r["calls_done"], est_pod_cost_usd=r["est_pod_cost_usd"])
    (out_dir(a.set) / f"analysis_{a.served_name}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("run", "analyze"):
        s = sp.add_parser(n)
        s.add_argument("--set", choices=("v2", "v3", "v6", "v7"), required=True)
        s.add_argument("--served-name", default="qwen32b")
        if n == "run":
            s.add_argument("--texts", required=True)
            s.add_argument("--workers", type=int, default=12)
            s.add_argument("--max-minutes", type=float, default=40)
    a = ap.parse_args()
    dict(run=cmd_run, analyze=cmd_analyze)[a.cmd](a)


if __name__ == "__main__":
    main()
