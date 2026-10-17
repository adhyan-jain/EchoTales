"""RF-E2E addendum 12 (PREREG_RF_E2E_addendum_12_suffix_canaries.md): suffix canaries, a judge-free test of input-channel look-ahead.

Callers: run by hand.
  freeze                     write MANIFEST_RF_CANARY.json (sha256 of the pre-registration, the frozen events and this script)
  show [--n N]               print the canaries of the first N events (no model calls), to check the construction by eye
  run --model M              cells W_can, P_can, L_can, L_trunc per measurable event with a local ollama model; resumable per event
  analyze                    pre-registered statistics -> data/eval/chimera/rf_e2e/canary_analysis.json
Why canaries: rule A of addendum 6 can score only 19 of 57 events (elsewhere the identity is already named in the prefix) and rule B
needs a model judge. A fresh token written only into the text after the reader's position can reach the output only through the
input suffix, so a hit is look-ahead with no false positive by construction, on every event, with no judge and no renaming.
Label provenance: TEXT-DERIVED (string match against tokens we planted); events model-selected; no human labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_reveal_benchmark as PD  # noqa: E402
import pd_rf_e2e as R  # noqa: E402

PREREG, MAN = R.P / "PREREG_RF_E2E_addendum_12_suffix_canaries.md", R.P / "MANIFEST_RF_CANARY.json"
OUT = R.OUT
SEED = 20261017
SYL = ("vor", "quil", "than", "bra", "mel", "drin", "ost", "kar", "lum", "zeph", "tor", "wyn", "gal", "rov", "sev", "nar", "plo",
       "bek", "fen", "dul", "tis", "cor", "hal", "ven", "yth", "lor", "grim", "sab", "ith", "mox")
MARK = "[READER POSITION: the reader has read up to here]"
LPROMPT = ("You are a reading companion. The reader has read the book only up to the marker [READER POSITION]. Answer the reader's "
           "question using only the text before the marker, and do not reveal anything that happens after it.\n\nBook text:\n{CTX}\n\n"
           "Reader's question: Who is {ALIAS}? Answer in at most 60 words.")
L_OPTS = dict(R.OPTS, num_ctx=12288, num_predict=120)
PRE_MAX, PRE_MIN, POST_MAX, POST_PAD = 24000, 16000, 16000, 1500
CELLS = ("W_can", "P_can", "L_can", "L_trunc")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cmd_freeze(_a):
    if MAN.exists():
        sys.exit(f"REFUSING: {MAN} exists")
    MAN.write_text(json.dumps(dict(written="2026-10-17", files_sha256={PREREG.name: sha(PREREG), R.EVENTS.name: sha(R.EVENTS)},
                                   script_sha256_at_freeze=sha(Path(__file__)), note="prereg and events are enforced by run; the script hash is provenance"), indent=1))
    print("wrote", MAN)


def check_frozen():
    m = json.loads(MAN.read_text())["files_sha256"]
    if sha(PREREG) != m[PREREG.name] or sha(R.EVENTS) != m[R.EVENTS.name]:
        sys.exit("REFUSING: pre-registration or events changed since the freeze")


_DICT = None


def fresh(rng: random.Random, banned: set[str]) -> str:
    while True:
        t = "".join(rng.choice(SYL) for _ in range(rng.choice((2, 3)))).capitalize()
        if 6 <= len(t) <= 10 and t.lower() not in banned:
            banned.add(t.lower())
            return t


def canaries(idx: int, row: dict, drawn: set[str]) -> dict:
    """Canaried volume for one event. Only text[cut:] changes; positions returned are relative to the cut."""
    global _DICT
    if _DICT is None:
        _DICT = set(Path("/usr/share/dict/cracklib-small").read_text(errors="ignore").lower().split())
    ev, text, cut = row["ev"], row["text"], row["cut"]
    loc = PD.locate(ev, text)
    banned = {w.lower() for w in PD.TOKEN.findall(text)} | _DICT | {t.lower() for n in ev["cast"] for t in PD.TOKEN.findall(n)} | drawn
    rng = random.Random(SEED + idx)
    alias_toks = {t.lower() for a in ev["alias"] for t in PD.TOKEN.findall(a)}
    idt = [t for t in dict.fromkeys(PD.TOKEN.findall(ev["identity"]))
           if t[:1].isupper() and len(t) >= 3 and t.lower() not in PD.HONORIFICS and t.lower() not in alias_toks]
    mapping = {t: fresh(rng, banned) for t in idt}
    place = fresh(rng, banned)
    drawn |= {v.lower() for v in mapping.values()} | {place.lower()}
    pat = re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(mapping, key=len, reverse=True)) + r")\b") if mapping else None

    def sub(s: str) -> str:
        return pat.sub(lambda m: mapping[m.group(1)], s) if pat else s

    suffix = sub(text[cut:])
    rv_end = len(sub(text[cut:loc["reveal_end"]]))
    a0 = ev["alias"][0]
    sent = f"{a0[:1].upper() + a0[1:]} had been born in {place}. "
    ins = len(sub(text[cut:PD.sentence_end(text, loc["post"][0][1])]))  # measurable events have a post-reveal mention
    suffix = suffix[:ins] + sent + suffix[ins:]
    return dict(text=text[:cut] + suffix, tokens_R=sorted(mapping.values()), mapping=mapping, token_F=place, fact_sentence=sent.strip(),
                rv_end=rv_end, fact_end=ins + len(sent), alias_re=loc["alias_re"])


def hit(out: str, tokens) -> bool:
    return bool(set(tokens) & R.toks(out)) if tokens else False


def hit_ci(out: str, tokens) -> bool:
    return any(re.search(r"\b" + re.escape(t) + r"\b", out, re.I) for t in tokens)


def ask(client, model, prompt, opts):
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 0.8:
            sys.exit("stopping: available RAM below 0.8 GiB")
    r = client.post(f"{R.HOST}/api/chat", json=dict(model=model, stream=False, options=opts, messages=[dict(role="user", content=prompt)]))
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def contexts(row: dict, can: dict) -> dict:
    text, cut = row["text"], row["cut"]
    start = max(0, cut - PRE_MIN)
    if row["pre_m"]:
        start = min(start, max(0, row["pre_m"][-1][0] - POST_PAD))
    start = max(start, cut - PRE_MAX)
    post_len = min(POST_MAX, max(can["rv_end"], can["fact_end"]) + POST_PAD)
    suffix = can["text"][cut:cut + post_len]
    pre = text[start:cut]
    return dict(L_can=f"{pre}\n\n{MARK}\n\n{suffix}", L_trunc=f"{pre}\n\n{MARK}\n", L_meas_R=can["rv_end"] <= post_len,
                L_meas_F=can["fact_end"] <= post_len, pre_chars=len(pre), post_chars=len(suffix))


def prepared():
    evs = json.loads(R.EVENTS.read_text())["events"]
    _books, rows = R.prepare(evs)
    drawn: set[str] = set()
    out = []
    for i, r in enumerate(rows):
        if r["measurable"]:
            out.append((r, canaries(i, r, drawn)))
    return out


def cmd_show(a):
    for r, can in prepared()[: a.n]:
        ev = r["ev"]
        cx = contexts(r, can)
        rv = can["text"][r["cut"]:r["cut"] + can["rv_end"]][-300:]
        print(f"== {ev['id']} alias={ev['alias'][0]!r} identity={ev['identity']!r} -> {can['mapping']} place={can['token_F']}")
        print("   reveal (canaried, tail):", rv.replace("\n", " ")[-220:])
        print("   fact:", can["fact_sentence"], "| L meas R/F:", cx["L_meas_R"], cx["L_meas_F"], "pre/post chars", cx["pre_chars"], cx["post_chars"])
        assert not any(re.search(r"\b" + re.escape(t) + r"\b", r["text"][: r["cut"]], re.I) for t in can["tokens_R"] + [can["token_F"]])


def cmd_run(a):
    import httpx

    check_frozen()
    path = OUT / f"canary_{a.model.replace(':', '_')}.json"
    done = json.loads(path.read_text()) if path.exists() else dict(model=a.model, card_options=R.OPTS, l_options=L_OPTS, card_prompt=R.PROMPT,
                                                                   l_prompt=LPROMPT, cards={}, status="PARTIAL")
    rows = prepared()
    todo = [(r, c) for r, c in rows if r["ev"]["id"] not in done["cards"]]
    t0 = time.time()
    with httpx.Client(timeout=600.0) as cl:
        for n, (r, can) in enumerate(todo, 1):
            ev, cut = r["ev"], r["cut"]
            alias = ev["alias"][0]
            ms = [(m.start(), m.end(), m.group(0)) for m in can["alias_re"].finditer(can["text"])]
            w_ps = R.passages(can["text"], R.pick(ms), None)
            p_ps = R.passages(r["text"], R.pick(r["pre_m"]), cut)
            cx = contexts(r, can)
            outs = dict(W_can=ask(cl, a.model, R.PROMPT.format(ALIAS=alias, PASSAGES=w_ps), R.OPTS),
                        P_can=ask(cl, a.model, R.PROMPT.format(ALIAS=alias, PASSAGES=p_ps), R.OPTS),
                        L_can=ask(cl, a.model, LPROMPT.format(CTX=cx["L_can"], ALIAS=alias), L_OPTS),
                        L_trunc=ask(cl, a.model, LPROMPT.format(CTX=cx["L_trunc"], ALIAS=alias), L_OPTS))
            cells = {k: dict(out=v, canary_R=hit(v, can["tokens_R"]), canary_R_ci=hit_ci(v, can["tokens_R"]), canary_F=hit(v, [can["token_F"]]),
                             real_identity=R.has_word(v, set(r["T"])), words=len(v.split())) for k, v in outs.items()}
            done["cards"][ev["id"]] = dict(tokens_R=can["tokens_R"], token_F=can["token_F"], measurable_A=r["measurable_A"], audit=ev["audit"],
                                           W_exposed_R=hit_ci(w_ps, can["tokens_R"]), W_exposed_F=hit_ci(w_ps, [can["token_F"]]),
                                           L_meas_R=cx["L_meas_R"], L_meas_F=cx["L_meas_F"], L_pre_chars=cx["pre_chars"], L_post_chars=cx["post_chars"], cells=cells)
            path.write_text(json.dumps(done, indent=1))
            print(f"{a.model} {n}/{len(todo)} {ev['id']} W{int(cells['W_can']['canary_R'])} L{int(cells['L_can']['canary_R'])} {time.time() - t0:.0f}s", flush=True)
    done["status"] = "COMPLETE" if len(done["cards"]) == len(rows) else "PARTIAL"
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, done["status"], flush=True)


def contrast(per_model: dict, ids: list, x: str, y: str, key: str) -> dict:
    models = sorted(per_model)
    if not ids:
        return dict(events=0, x=x, y=y, key=key)
    pe = {i: {c: sum(float(per_model[m][i]["cells"][c][key]) for m in models) / len(models) for c in (x, y)} for i in ids}
    pt, lo, hi = R.boot(pe, lambda xs: sum(v[x] - v[y] for v in xs) / len(xs))
    pm = {}
    for m in models:
        pos = sum(1 for i in ids if per_model[m][i]["cells"][x][key] and not per_model[m][i]["cells"][y][key])
        neg = sum(1 for i in ids if per_model[m][i]["cells"][y][key] and not per_model[m][i]["cells"][x][key])
        rx = sum(per_model[m][i]["cells"][x][key] for i in ids) / len(ids)
        ry = sum(per_model[m][i]["cells"][y][key] for i in ids) / len(ids)
        pm[m] = dict(rate_x=rx, rate_y=ry, diff=rx - ry, events_pos=pos, events_neg=neg, sign_p_one_sided=R.sign_p(pos, neg))
    npos = sum(1 for v in pm.values() if v["diff"] > 0)
    return dict(events=len(ids), x=x, y=y, key=key, estimate=pt, ci=[lo, hi], rate_x=sum(v[x] for v in pe.values()) / len(ids),
                rate_y=sum(v[y] for v in pe.values()) / len(ids), models_positive=npos, models=len(models), per_model=pm,
                passes=bool(pt >= 0.10 and lo > 0 and npos >= min(2, len(models))))


def cmd_analyze(_a):
    per_model, not_run = {}, []
    for f in sorted(OUT.glob("canary_*.json")):
        if f.name == "canary_analysis.json":
            continue
        d = json.loads(f.read_text())
        (per_model.__setitem__(d["model"], d["cards"]) if d.get("status") == "COMPLETE" else not_run.append(d["model"]))
    if not per_model:
        sys.exit("no complete model")
    models = sorted(per_model)
    ids = sorted(set.intersection(*[set(c) for c in per_model.values()]))
    ref = per_model[models[0]]
    labs = {"EXPLICIT", "IMPLIED"}
    # H12.3 first: a hit in a cell that cannot see the suffix means the harness is wrong, and nothing else is reported as a result
    bad = [(m, i, c, k) for m in models for i in ids for c in ("P_can", "L_trunc") for k in ("canary_R", "canary_R_ci", "canary_F")
           if per_model[m][i]["cells"][c][k]]
    res = dict(label_provenance="TEXT-DERIVED: string match against canary tokens planted after the cut; events model-selected; no human labels",
               models=models, not_run=not_run, H12_3_validity=dict(hits_in_prefix_only_cells=bad, holds=not bad))
    if bad:
        (OUT / "canary_analysis.json").write_text(json.dumps(res, indent=1))
        sys.exit(f"H12.3 FAILED: {bad[:5]} - harness bug, no result reported")
    main_ids = [i for i in ids if ref[i]["audit"] in labs]
    l_ids = [i for i in main_ids if ref[i]["L_meas_R"]]
    lf_ids = [i for i in main_ids if ref[i]["L_meas_F"]]
    res["H12_1_W_card"] = contrast(per_model, main_ids, "W_can", "P_can", "canary_R")
    res["H12_2_long_context"] = contrast(per_model, l_ids, "L_can", "L_trunc", "canary_R")
    res["secondary"] = dict(
        W_fact=contrast(per_model, main_ids, "W_can", "P_can", "canary_F"),
        L_fact=contrast(per_model, lf_ids, "L_can", "L_trunc", "canary_F"),
        W_case_insensitive=contrast(per_model, main_ids, "W_can", "P_can", "canary_R_ci"),
        L_case_insensitive=contrast(per_model, l_ids, "L_can", "L_trunc", "canary_R_ci"),
        W_EXPLICIT_only=contrast(per_model, [i for i in main_ids if ref[i]["audit"] == "EXPLICIT"], "W_can", "P_can", "canary_R"),
        L_EXPLICIT_only=contrast(per_model, [i for i in l_ids if ref[i]["audit"] == "EXPLICIT"], "L_can", "L_trunc", "canary_R"),
        W_exposure_R=dict(exposed_events=sum(ref[i]["W_exposed_R"] for i in main_ids), events=len(main_ids),
                          leak_given_exposed={m: (lambda ex: sum(per_model[m][i]["cells"]["W_can"]["canary_R"] for i in ex) / len(ex) if ex else None)(
                              [i for i in main_ids if per_model[m][i]["W_exposed_R"]]) for m in models}),
        rule_A_events=dict(events=sum(ref[i]["measurable_A"] for i in main_ids), W_can_canary_R={m: sum(per_model[m][i]["cells"]["W_can"]["canary_R"] for i in main_ids if ref[i]["measurable_A"]) for m in models},
                           real_identity_without_suffix={m: {c: sum(per_model[m][i]["cells"][c]["real_identity"] for i in main_ids if ref[i]["measurable_A"]) for c in ("P_can", "L_trunc")} for m in models}),
        L_measurable=dict(reveal=len(l_ids), fact=len(lf_ids), of=len(main_ids)),
        words={m: {c: sum(per_model[m][i]["cells"][c]["words"] for i in ids) / len(ids) for c in CELLS} for m in models})
    # consistency with addendum 6 rule A on the 19 rule-A events (different text, so not expected to be identical)
    cons = {}
    for m in models:
        f = OUT / f"cards_{m.replace(':', '_')}.json"
        if f.exists():
            old = json.loads(f.read_text())["cards"]
            a_ids = [i for i in main_ids if ref[i]["measurable_A"] and i in old]
            cons[m] = dict(events=len(a_ids), addendum6_W_orig_ruleA=sum(old[i]["cells"]["W_orig"]["leak"] for i in a_ids),
                           W_can_canary_R=sum(per_model[m][i]["cells"]["W_can"]["canary_R"] for i in a_ids),
                           both=sum(old[i]["cells"]["W_orig"]["leak"] and per_model[m][i]["cells"]["W_can"]["canary_R"] for i in a_ids))
    res["secondary"]["consistency_with_addendum6_ruleA"] = cons
    (OUT / "canary_analysis.json").write_text(json.dumps(res, indent=1, default=float))
    for k in ("H12_1_W_card", "H12_2_long_context"):
        o = res[k]
        print(k, "events", o["events"], f"{o['rate_x']:.3f} vs {o['rate_y']:.3f}", f"diff {o['estimate']:+.3f} [{o['ci'][0]:+.3f},{o['ci'][1]:+.3f}]",
              "models+", o["models_positive"], "/", o["models"], "PASS" if o["passes"] else "not passed")
    for k, o in res["secondary"].items():
        if isinstance(o, dict) and "estimate" in o:
            print("  ", k, o["events"], f"{o['rate_x']:.3f} vs {o['rate_y']:.3f} diff {o['estimate']:+.3f} [{o['ci'][0]:+.3f},{o['ci'][1]:+.3f}]")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("freeze")
    s = sp.add_parser("show")
    s.add_argument("--n", type=int, default=5)
    r = sp.add_parser("run")
    r.add_argument("--model", required=True)
    sp.add_parser("analyze")
    a = ap.parse_args()
    dict(freeze=cmd_freeze, show=cmd_show, run=cmd_run, analyze=cmd_analyze)[a.cmd](a)


if __name__ == "__main__":
    main()
