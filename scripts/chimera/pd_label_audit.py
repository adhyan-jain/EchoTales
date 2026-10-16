"""Independent-model audit of the PD event labels (not a human check; labels stay "model-selected, model-audited").

For each event the passage around the located reveal sentence (the sentence plus the two sentences before it) is shown to
an auditing model together with the alias expression and the claimed identity, and the model says whether the passage
EXPLICITLY states the alias is the identity, only IMPLIES it, or does NOT. This flags weak oracles (spoken or implied
reveals) so the leakage analyses can be re-run without them. Public-domain text only; the passage is sent to the API
and is not written to any repository file. Budget-guarded; the key is read from the environment inside a subshell only.

Commands: estimate | run --budget-usd X [--local MODEL]. Output: data/eval/chimera/pd_label_audit.json
(event id, verdict, nothing else from the text).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_llm_leakage as L1  # noqa: E402
import pd_reveal_benchmark as PD  # noqa: E402

P = Path("docs/research/preregistrations")
FILES = [P / "PD_events_v1.json", P / "PD_events_v2_additions.json", P / "PD_events_v3_additions.json"]
OUT = Path("data/eval/chimera/pd_label_audit.json")
PROMPT = ("Below is a passage from a novel, then a claim.\n\nPASSAGE:\n<<<\n{PASSAGE}\n>>>\n\nCLAIM: the character referred to as "
          "{ALIAS} in the book is the same person as {IDENTITY}.\n\nDoes the passage itself EXPLICITLY state this (the text "
          "directly equates the two, in narration or in a speaker's words), only IMPLY it, or NOT support it? Reply with a JSON "
          "object {{\"answer\": X}} where X is exactly one of EXPLICIT, IMPLIED, NOT_SUPPORTED.")


def passage(ev, text):
    loc = PD.locate(ev, text)
    start = loc["reveal_start"]
    back = text[max(0, start - 600): start]
    m = list(re.finditer(r"[.!?][”\"’')]*\s", back))
    if len(m) >= 2:
        start = max(0, start - 600) + m[-2].end()
    return text[start: loc["reveal_end"] + 40].strip()


def jobs(texts: Path):
    out = []
    for f in FILES:
        for ev in json.loads(f.read_text())["events"]:
            text = PD.load_text(texts, ev["gutenberg"])
            out.append((ev["id"], PROMPT.format(PASSAGE=passage(ev, text), ALIAS=" / ".join(f'"{a}"' for a in ev["alias"][:2]),
                                                IDENTITY=f'"{ev["identity"]}"')))
    return out


def cmd_estimate(args):
    js = jobs(Path(args.texts))
    est_in = sum(L1.est_tokens(p) for _, p in js)
    print(json.dumps(dict(calls=len(js), expected_usd=round(est_in * 0.8958 * L1.PRICE_IN + len(js) * 10 * L1.PRICE_OUT, 5),
                          worst_usd=round(est_in * 1.3 * L1.PRICE_IN + len(js) * 32 * L1.PRICE_OUT, 5))))


def cmd_run(args):
    import httpx

    js = jobs(Path(args.texts))
    res = {}
    spent = dict(calls=0, tok_in=0, tok_out=0, usd=0.0)
    if args.local:
        host = "http://127.0.0.1:11434"
        schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": ["EXPLICIT", "IMPLIED", "NOT_SUPPORTED"]}},
                  "required": ["answer"]}
        with httpx.Client(timeout=240.0) as c:
            for ev, p in js:
                x = c.post(f"{host}/api/chat", json=dict(model=args.local, stream=False, format=schema,
                                                          options={"temperature": 0, "seed": 20261016, "num_predict": 24, "num_ctx": 4096},
                                                          messages=[dict(role="user", content=p)]))
                x.raise_for_status()
                try:
                    res[ev] = json.loads(x.json()["message"]["content"]).get("answer", "INVALID")
                except ValueError:
                    res[ev] = "INVALID"
            c.post(f"{host}/api/generate", json=dict(model=args.local, keep_alive=0, prompt=""))
        who = args.local
    else:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            sys.exit("OPENAI_API_KEY is not set in the environment")
        budget = L1.Budget(args.budget_usd)
        with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as c:
            del key
            for ev, p in js:
                if not budget.can(L1.est_tokens(p), 32):
                    res[ev] = "STOPPED_AT_BUDGET"
                    continue
                r = L1.call_model(c, p, 32)
                budget.calls += 1
                budget.tok_in += r["tok_in"]
                budget.tok_out += r["tok_out"]
                budget.actual += r["tok_in"] * L1.PRICE_IN + r["tok_out"] * L1.PRICE_OUT
                m = re.search(r'"answer"\s*:\s*"([A-Z_]+)"', r["text"])
                res[ev] = m.group(1) if m and m.group(1) in ("EXPLICIT", "IMPLIED", "NOT_SUPPORTED") else "INVALID"
        spent = dict(calls=budget.calls, tok_in=budget.tok_in, tok_out=budget.tok_out, usd=budget.actual)
        who = L1.MODEL
    allres = json.loads(OUT.read_text()) if OUT.exists() else {}
    allres[who] = dict(verdicts=res, spent=spent)
    OUT.write_text(json.dumps(allres, indent=1))
    from collections import Counter
    print(who, dict(Counter(res.values())), "spent", round(spent["usd"], 4))
    print("not EXPLICIT:", sorted(e for e, v in res.items() if v != "EXPLICIT"))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("estimate", "run"):
        s = sp.add_parser(n)
        s.add_argument("--texts", required=True)
        if n == "run":
            s.add_argument("--budget-usd", type=float, default=0.0)
            s.add_argument("--local", default=None)
    a = ap.parse_args()
    dict(estimate=cmd_estimate, run=cmd_run)[a.cmd](a)


if __name__ == "__main__":
    main()
