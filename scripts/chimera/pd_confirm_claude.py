"""Claude Sonnet 5.5 arm of the confirmatory study (PREREG_PD_CONFIRM_v2_L40S.md section 1: closed model via the owner's subscription, E1 and M2 only).

Callers: run by hand after the events file is frozen; uses pd_confirm_run.setup/build_items so the items, arms and prompts are exactly those of the
open-model runs. Only TEST-split events; arms A, B, B3 on pre/post/control items plus the three M2 arms; the alias-only closed book and B2 are not run
for this model. Each call is `claude -p --model sonnet --tools "" --system-prompt <fixed text> --output-format json --no-session-persistence
--strict-mcp-config --disable-slash-commands` from an empty temporary directory; the canonical model id is read from `modelUsage` on every call. No
temperature or seed control exists in this mode, so the run is not reproducible bit for bit; each item is asked once. Throttling or an empty reply
stops the arm (logged); the arm can be cut to the first N items with --max-items (reported). Quota, not dollars. Terms of use for bulk programmatic
use of a subscription are UNVERIFIED (owner approved the arm).
Output: data/eval/chimera/confirm/<tag>/e1_claude-sonnet-5-5.json (same layout as the open-model files).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_confirm_run as R  # noqa: E402
import pd_v6 as V6  # noqa: E402

SYSTEM = "You answer multiple-choice reading questions. Reply with exactly the JSON object requested and nothing else."
MODEL_ID = "claude-sonnet-5-5"


def ask(prompt: str):
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(["claude", "-p", "--model", "sonnet", "--tools", "", "--system-prompt", SYSTEM, "--output-format", "json",
                            "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"], input=prompt, capture_output=True, text=True,
                           cwd=td, timeout=180)
    try:
        j = json.loads(r.stdout)
    except ValueError:
        return None, None, r.stderr[-200:]
    used = list((j.get("modelUsage") or {}).keys())
    return j.get("result", ""), used, "" if not j.get("is_error") else str(j.get("result"))[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=str(R.EVENTS))
    ap.add_argument("--texts", default=str(R.TEXTS))
    ap.add_argument("--tag", default="main")
    ap.add_argument("--max-items", type=int, default=100000)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    evs, texts, out = R.setup(a)
    path = out / f"e1_{MODEL_ID}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists")
    test_ids = {e["id"] for e in evs if e.get("split") == "test"}
    real, _cb, m2, _ = V6.prompts(texts)
    js = [("real", p["id"], arm, p[arm], p["cands"]) for p in real if p["event"] in test_ids for arm in ("A", "B", "B3")]
    js += [("m2", p["event"], arm, p[arm], p["cands"]) for p in m2 if p["event"] in test_ids for arm in V6.M2_ARMS]
    js = js[:a.max_items]
    t0, models_seen, stop = time.time(), set(), [False]
    res = dict(model=MODEL_ID, set=a.tag, real={}, closed={}, m2={}, status="COMPLETE", calls=len(js), scope="test split; arms A,B,B3 and M2")

    def work(j):
        if stop[0]:
            return "STOPPED"
        txt, used, err = ask(j[3])
        if txt is None or err or not txt:
            stop[0] = True
            res["status"] = f"STOPPED: {err or 'empty reply'}"
            return "STOPPED"
        models_seen.update(used or [])
        return V6.parse(txt, j[4])

    with ThreadPoolExecutor(a.workers) as ex:
        for n, (j, ans) in enumerate(zip(js, ex.map(work, js)), 1):
            if ans != "STOPPED":
                res[j[0]].setdefault(j[1], {})[j[2]] = ans
            if n % 100 == 0:
                print(f"claude {n}/{len(js)} {time.time() - t0:.0f}s status {res['status']}", flush=True)
    res["wall_seconds"] = round(time.time() - t0, 1)
    res["model_ids_seen"] = sorted(models_seen)
    done_ids = set(res["real"])
    res["truth"] = {p["id"]: dict(truth_letter=p["truth_letter"], identity_letter=p["identity_letter"], kind=p["kind"], event=p["event"],
                                  distance=p["distance"], baseline_letter=p["baseline_letter"]) for p in real if p["id"] in done_ids}
    res["closed_truth"] = {}
    res["m2_truth"] = {p["event"]: p["identity_letter"] for p in m2 if p["event"] in res["m2"]}
    for d in res["real"].values():  # the analysis expects a B2 key; this arm does not run it
        d.setdefault("B2", d.get("B"))
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "status", res["status"], "models", res["model_ids_seen"], "wall", res["wall_seconds"])


if __name__ == "__main__":
    main()
