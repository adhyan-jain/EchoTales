"""POST HOC (not pre-registered): of the addendum-12 outputs that quote a reveal canary, how many equate the alias with it?

Callers: run by hand after rf_canary.py analyze. A canary hit proves suffix content reached the output (the contract); this asks
the addendum-6 judge (qwen3:8b, same prompt and JSON schema) whether the output states or clearly implies that the alias is the
canary-named identity, i.e. the spoiler itself. Only cells with canary_R = true are judged. Writes posthoc_canary_judge.json.
Label provenance: MODEL-JUDGED, post hoc, descriptive only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_rf_e2e as R  # noqa: E402
import rf_canary as RC  # noqa: E402

OUT = R.OUT
SCHEMA = {"type": "object", "properties": {"identifies": {"type": "boolean"}}, "required": ["identifies"]}


def main():
    # the identity as the canaried book spells it (honorifics kept, name tokens replaced), recomputed deterministically
    canaried = {}
    for r, can in RC.prepared():
        ident = r["ev"]["identity"]
        for t, c in can["mapping"].items():
            ident = re.sub(r"\b" + re.escape(t) + r"\b", c, ident)
        canaried[r["ev"]["id"]] = (r["ev"]["alias"][0], ident)
    path = OUT / "posthoc_canary_judge.json"
    done = json.loads(path.read_text()) if path.exists() else dict(judge=R.JUDGE, prompt=R.JUDGE_PROMPT, note="POST HOC", labels={})
    with httpx.Client(timeout=300.0) as cl:
        for f in sorted(OUT.glob("canary_*.json")):
            if f.name in ("canary_analysis.json", path.name):
                continue
            d = json.loads(f.read_text())
            for eid, rec in d["cards"].items():
                alias, ident = canaried[eid]
                for cell in ("W_can", "L_can"):
                    key = f"{d['model']}|{eid}|{cell}"
                    if not rec["cells"][cell]["canary_R"] or key in done["labels"]:
                        continue
                    r = cl.post(f"{R.HOST}/api/chat", json=dict(model=R.JUDGE, stream=False, think=False, format=SCHEMA,
                                                               options={"temperature": 0, "seed": 20261016, "num_predict": 20},
                                                               messages=[dict(role="user", content=R.JUDGE_PROMPT.format(CARD=rec["cells"][cell]["out"], ALIAS=alias, IDENTITY=ident))]))
                    r.raise_for_status()
                    try:
                        done["labels"][key] = bool(json.loads(r.json()["message"]["content"])["identifies"])
                    except (ValueError, KeyError):
                        done["labels"][key] = None
                    path.write_text(json.dumps(done, indent=1))
    summ = {}
    for key, v in done["labels"].items():
        m, _e, cell = key.split("|")
        s = summ.setdefault(f"{m}|{cell}", dict(hits=0, equates=0, unparsed=0))
        s["hits"] += 1
        s["equates"] += bool(v)
        s["unparsed"] += v is None
    done["summary"] = summ
    done["total"] = {c: dict(hits=sum(v["hits"] for k, v in summ.items() if k.endswith(c)), equates=sum(v["equates"] for k, v in summ.items() if k.endswith(c)))
                     for c in ("W_can", "L_can")}
    path.write_text(json.dumps(done, indent=1))
    print(json.dumps(done["total"]), json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
