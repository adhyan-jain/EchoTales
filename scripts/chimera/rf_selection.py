"""RF-E2E addendum 13 (PREREG_RF_E2E_addendum_13_selection_leak.md): a selection leak with no suffix content in the input.

Callers: run by hand.
  freeze                     write MANIFEST_RF_SELECTION.json
  resolve                    index-time resolver (qwen2.5:7b) on each selected event's reveal window -> selection_resolver.json
  run --model M              M_ren card per selected event (prefix-only passages of the alias and of the identity) -> selection_<model>.json
  judge --of M               qwen3:8b judge on M_ren -> judge_qwen3_8b_of_<model>_selection.json
  analyze                    H13.1/H13.2 against the stored P_ren cards and labels of addendum 6 -> selection_analysis.json
Why: a whole-volume index can decide which prefix passages belong to the alias using the reveal, so every served passage is
before the cut and the answer still spoils. Content tests (canaries) cannot see this; truncate-and-rebuild can.
Label provenance: MODEL-JUDGED (qwen3:8b); resolver is a model; events model-selected; no human labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_reveal_benchmark as PD  # noqa: E402
import pd_rf_e2e as R  # noqa: E402
import pd_v3 as V3  # noqa: E402

PREREG, MAN = R.P / "PREREG_RF_E2E_addendum_13_selection_leak.md", R.P / "MANIFEST_RF_SELECTION.json"
OUT = R.OUT
RESOLVER = "qwen2.5:7b"
RES_PROMPT = ("Here is a passage from a novel.\n\n{PASSAGE}\n\nIn this passage, are the character called \"{ALIAS}\" and the character "
              "called \"{IDENTITY}\" the same person? Reply as JSON: {{\"same\": true}} or {{\"same\": false}}.")
LABS = {"EXPLICIT", "IMPLIED"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cmd_freeze(_a):
    if MAN.exists():
        sys.exit(f"REFUSING: {MAN} exists")
    MAN.write_text(json.dumps(dict(written="2026-10-17", files_sha256={PREREG.name: sha(PREREG), R.EVENTS.name: sha(R.EVENTS)},
                                   script_sha256_at_freeze=sha(Path(__file__))), indent=1))
    print("wrote", MAN)


def check_frozen():
    m = json.loads(MAN.read_text())["files_sha256"]
    if sha(PREREG) != m[PREREG.name] or sha(R.EVENTS) != m[R.EVENTS.name]:
        sys.exit("REFUSING: pre-registration or events changed since the freeze")


def selected():
    """Measurable EXPLICIT/IMPLIED events whose identity is named in a sentence that ends before the cut."""
    evs = json.loads(R.EVENTS.read_text())["events"]
    books, rows = R.prepare(evs)
    rn = V3.renamers_for(books)
    out = []
    for r in rows:
        ev, text, cut = r["ev"], r["text"], r["cut"]
        if not r["measurable"] or ev["audit"] not in LABS:
            continue
        pat = re.compile("|".join(r"\b" + re.escape(s) + r"\b" for s in sorted(PD.surfaces_for(ev["identity"]), key=len, reverse=True)))
        id_m = [(m.start(), m.end(), m.group(0)) for m in pat.finditer(text[:cut]) if PD.sentence_end(text, m.end()) <= cut]
        if id_m:
            out.append((r, id_m, rn[ev["gutenberg"]][0]))
    return out


def chat(cl, model, prompt, opts, fmt=None, think=None):
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 0.8:
            sys.exit("stopping: available RAM below 0.8 GiB")
    body = dict(model=model, stream=False, options=opts, messages=[dict(role="user", content=prompt)])
    if fmt:
        body["format"] = fmt
    if think is not None:
        body["think"] = think
    r = cl.post(f"{R.HOST}/api/chat", json=body)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def cmd_resolve(_a):
    import httpx

    check_frozen()
    path = OUT / "selection_resolver.json"
    done = json.loads(path.read_text()) if path.exists() else dict(model=RESOLVER, prompt=RES_PROMPT, labels={})
    schema = {"type": "object", "properties": {"same": {"type": "boolean"}}, "required": ["same"]}
    with httpx.Client(timeout=300.0) as cl:
        for r, _id_m, rn in selected():
            ev, text = r["ev"], r["text"]
            if ev["id"] in done["labels"]:
                continue
            loc = PD.locate(ev, text)
            win = rn.rename(text[max(0, loc["reveal_start"] - 1500): loc["reveal_end"] + 500])
            out = chat(cl, RESOLVER, RES_PROMPT.format(PASSAGE=win, ALIAS=rn.rename(ev["alias"][0]), IDENTITY=rn.rename(ev["identity"])),
                       {"temperature": 0, "seed": 20261016, "num_predict": 20, "num_ctx": 4096}, fmt=schema)
            try:
                done["labels"][ev["id"]] = bool(json.loads(out)["same"])
            except (ValueError, KeyError):
                done["labels"][ev["id"]] = None
            path.write_text(json.dumps(done, indent=1))
    print("wrote", path, sum(1 for v in done["labels"].values() if v), "merged of", len(done["labels"]))


def cmd_run(a):
    import httpx

    check_frozen()
    path = OUT / f"selection_{a.model.replace(':', '_')}.json"
    done = json.loads(path.read_text()) if path.exists() else dict(model=a.model, options=R.OPTS, prompt=R.PROMPT, cards={}, status="PARTIAL")
    sel = selected()
    t0 = time.time()
    with httpx.Client(timeout=300.0) as cl:
        for n, (r, id_m, rn) in enumerate(sel, 1):
            ev, text, cut = r["ev"], r["text"], r["cut"]
            if ev["id"] in done["cards"]:
                continue
            picked = R.pick(sorted(set(r["pre_m"]) | set(id_m)))
            # the design's defining property: every passage starts before the reader's position and is clipped at it
            assert all(s < cut for s, _e, _ in picked)
            ps = R.passages(text, picked, cut)
            card = chat(cl, a.model, R.PROMPT.format(ALIAS=rn.rename(ev["alias"][0]), PASSAGES=rn.rename(ps)), R.OPTS)
            n_id = sum(1 for m in picked if m in set(id_m))
            done["cards"][ev["id"]] = dict(alias_ren=rn.rename(ev["alias"][0]), identity_ren=rn.rename(ev["identity"]), n_passages=len(picked),
                                           n_identity_passages=n_id, cells=dict(M_ren=dict(card=card, words=len(card.split()))))
            path.write_text(json.dumps(done, indent=1))
            print(f"{a.model} {n}/{len(sel)} {ev['id']} {time.time() - t0:.0f}s", flush=True)
    done["status"] = "COMPLETE" if len(done["cards"]) == len(sel) else "PARTIAL"
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, done["status"])


def cmd_judge(a):
    import httpx

    src = json.loads((OUT / f"selection_{a.of.replace(':', '_')}.json").read_text())
    path = OUT / f"judge_qwen3_8b_of_{a.of.replace(':', '_')}_selection.json"
    done = json.loads(path.read_text()) if path.exists() else dict(judge=R.JUDGE, of=a.of, prompt=R.JUDGE_PROMPT, labels={})
    schema = {"type": "object", "properties": {"identifies": {"type": "boolean"}}, "required": ["identifies"]}
    with httpx.Client(timeout=300.0) as cl:
        for eid, rec in src["cards"].items():
            if eid in done["labels"]:
                continue
            out = chat(cl, R.JUDGE, R.JUDGE_PROMPT.format(CARD=rec["cells"]["M_ren"]["card"], ALIAS=rec["alias_ren"], IDENTITY=rec["identity_ren"]),
                       {"temperature": 0, "seed": 20261016, "num_predict": 20}, fmt=schema, think=False)
            try:
                done["labels"][eid] = {"M_ren": bool(json.loads(out)["identifies"])}
            except (ValueError, KeyError):
                done["labels"][eid] = {"M_ren": None}
            path.write_text(json.dumps(done, indent=1))
    done["status"] = "COMPLETE" if len(done["labels"]) == len(src["cards"]) else "PARTIAL"
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, done["status"])


def cmd_analyze(_a):
    res_lab = json.loads((OUT / "selection_resolver.json").read_text())["labels"]
    per = {}
    for f in sorted(OUT.glob("judge_qwen3_8b_of_*_selection.json")):
        d = json.loads(f.read_text())
        m = d["of"]
        old = json.loads((OUT / f"judge_qwen3_8b_of_{m.replace(':', '_')}.json").read_text())["labels"]
        per[m] = {i: dict(M=d["labels"][i]["M_ren"], P=old[i]["P_ren"]) for i in d["labels"] if i in old}
    models = sorted(per)
    ids_all = sorted(set.intersection(*[{i for i, v in per[m].items() if v["M"] is not None and v["P"] is not None} for m in models]))
    out = dict(label_provenance="MODEL-JUDGED (qwen3:8b); resolver qwen2.5:7b; events model-selected; no human labels", models=models,
               selected_events=len(ids_all), resolver_merged=sum(1 for i in ids_all if res_lab.get(i)),
               resolver_unparsed=sum(1 for i in ids_all if res_lab.get(i) is None))
    for name, ids in (("H13_1_resolver_merged", [i for i in ids_all if res_lab.get(i)]), ("H13_2_ideal_merge", ids_all)):
        if not ids:
            out[name] = dict(events=0)
            continue
        pe = {i: dict(M=sum(float(per[m][i]["M"]) for m in models) / len(models), P=sum(float(per[m][i]["P"]) for m in models) / len(models)) for i in ids}
        pt, lo, hi = R.boot(pe, lambda xs: sum(x["M"] - x["P"] for x in xs) / len(xs))
        pm = {}
        for m in models:
            pos = sum(1 for i in ids if per[m][i]["M"] and not per[m][i]["P"])
            neg = sum(1 for i in ids if per[m][i]["P"] and not per[m][i]["M"])
            rm, rp = sum(per[m][i]["M"] for i in ids) / len(ids), sum(per[m][i]["P"] for i in ids) / len(ids)
            pm[m] = dict(M_rate=rm, P_rate=rp, diff=rm - rp, events_pos=pos, events_neg=neg, sign_p_one_sided=R.sign_p(pos, neg))
        npos = sum(1 for v in pm.values() if v["diff"] > 0)
        out[name] = dict(events=len(ids), M_rate=sum(v["M"] for v in pe.values()) / len(ids), P_rate=sum(v["P"] for v in pe.values()) / len(ids),
                         estimate=pt, ci=[lo, hi], models_positive=npos, per_model=pm, passes=bool(pt >= 0.10 and lo > 0 and npos >= min(2, len(models))))
        print(name, out[name]["events"], f"M {out[name]['M_rate']:.3f} P {out[name]['P_rate']:.3f} diff {pt:+.3f} [{lo:+.3f},{hi:+.3f}]",
              "PASS" if out[name]["passes"] else "not passed")
    cards = {m: json.loads((OUT / f"selection_{m.replace(':', '_')}.json").read_text())["cards"] for m in models}
    out["identity_passage_share"] = sum(cards[models[0]][i]["n_identity_passages"] / cards[models[0]][i]["n_passages"] for i in ids_all) / max(1, len(ids_all))
    (OUT / "selection_analysis.json").write_text(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("freeze")
    sp.add_parser("resolve")
    r = sp.add_parser("run")
    r.add_argument("--model", required=True)
    j = sp.add_parser("judge")
    j.add_argument("--of", required=True)
    sp.add_parser("analyze")
    a = ap.parse_args()
    dict(freeze=cmd_freeze, resolve=cmd_resolve, run=cmd_run, judge=cmd_judge, analyze=cmd_analyze)[a.cmd](a)


if __name__ == "__main__":
    main()
