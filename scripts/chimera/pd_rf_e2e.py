"""RF-E2E (PREREG_RF_E2E_addendum_6.md): does a whole-volume, first-mention-stamped LLM character card leak the reveal, and how much of
the leak needs the input versus the model's memory?

Callers: run by hand and by scripts/chimera/run_rf_e2e.sh.
  freeze                 write MANIFEST_RF_E2E.json (sha256 of the pre-registration, the frozen events file and this script)
  run --model M [--limit N]   build cards (W, P) x (orig, ren) per measurable event with a local ollama model; resumable per event
  analyze                pre-registered statistics from data/eval/chimera/rf_e2e/cards_*.json -> analysis.json
Reads the frozen events (docs/research/preregistrations/PD_confirm_events_v1.json; fields id, gutenberg, alias (list), identity, reveal_sentence,
cut{regex, back}, audit, split) and the local Gutenberg texts (data/raw/pd_confirm/texts, git-ignored). Writes only under data/eval/chimera/rf_e2e/.
Cards are model-generated text from public-domain books. Label provenance: TEXT-DERIVED oracle, model-selected events, no human labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_reveal_benchmark as PD  # noqa: E402
import pd_v3 as V3  # noqa: E402

P = Path("docs/research/preregistrations")
EVENTS, PREREG, MAN = P / "PD_confirm_events_v1.json", P / "PREREG_RF_E2E_addendum_6.md", P / "MANIFEST_RF_E2E.json"
TEXTS, OUT = Path("data/raw/pd_confirm/texts"), Path("data/eval/chimera/rf_e2e")
K, BEFORE, AFTER = 12, 500, 700
HOST = "http://127.0.0.1:11434"
OPTS = {"temperature": 0, "seed": 20261016, "num_predict": 160, "num_ctx": 8192}
PROMPT = "Write a character card of at most 80 words for the character referred to as {ALIAS}, using these passages from the book. Passages:\n{PASSAGES}\nCard:"
SEED_BOOT, NB = 20261101, 10000


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def toks(s: str) -> set[str]:
    return set(re.findall(r"\b[A-Z][a-z]{2,}\b", s))


def pick(ms):
    return list(ms) if len(ms) <= K else [ms[i] for i in PD.spaced(len(ms), K)]


def passages(text, ms, clip):
    out = []
    for s, e, _ in ms:
        a, b = max(0, s - BEFORE), min(len(text), e + AFTER)
        if clip is not None:
            b = min(b, clip)
        out.append(text[a:b].strip())
    return "\n---\n".join(f"[{i + 1}] {p}" for i, p in enumerate(out))


def has_word(card: str, word_set: set[str]) -> bool:
    return bool(word_set & toks(card))


def cmd_freeze(_a):
    if MAN.exists():
        sys.exit(f"REFUSING: {MAN} exists")
    MAN.write_text(json.dumps(dict(written="2026-10-16", files_sha256={PREREG.name: sha(PREREG), EVENTS.name: sha(EVENTS)},
                                   script_sha256_at_freeze=sha(Path(__file__)), note="prereg and events are enforced by run; the script hash is provenance"), indent=1))
    print("wrote", MAN)


def check_frozen():
    m = json.loads(MAN.read_text())["files_sha256"]
    if sha(PREREG) != m[PREREG.name] or sha(EVENTS) != m[EVENTS.name]:
        sys.exit("REFUSING: pre-registration or events changed since the freeze")


def prepare(evs):
    """Per event: measurability, evidence for W and P, and the renamed variants. No model calls."""
    books, rows = {}, []
    for ev in evs:
        text = books.setdefault(ev["gutenberg"], PD.load_text(TEXTS, ev["gutenberg"]))
        loc = PD.locate(ev, text)
        cut = loc["cut"]
        pre_text = text[:cut]
        T = {t for t in toks(ev["identity"]) if t.lower() not in PD.HONORIFICS and not re.search(r"\b" + re.escape(t) + r"\b", pre_text)}
        all_m = [(m.start(), m.end(), m.group(0)) for m in loc["alias_re"].finditer(text)]
        # rule B needs only alias mentions on both sides of the reveal; rule A also needs an identity token the prefix never shows
        # (in 38 of 68 events the identity is already a named character, so a name match cannot tell disclosure from mention)
        meas = len(loc["post"]) >= 1 and len(loc["pre"]) >= 1
        rows.append(dict(ev=ev, text=text, cut=cut, T=T, all_m=all_m, pre_m=loc["pre"], n_post=len(loc["post"]), measurable=meas,
                         measurable_A=meas and bool(T)))
    return books, rows


LARGE = {"qwen32b", "mistral24", "olmo32b"}  # pod models (addendum 8), analysed as a separate stratum


def ask(client, model, prompt):
    if model in LARGE:  # pod router via pd_confirm_mine.Pod; empty string on endpoint error (counted, addendum 8)
        return client.chat(model, prompt, OPTS["num_predict"]).strip()
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 0.8:
            sys.exit("stopping: available RAM below 0.8 GiB")
    r = client.post(f"{HOST}/api/chat", json=dict(model=model, stream=False, options=OPTS, messages=[dict(role="user", content=prompt)]))
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def client_for(model):
    import httpx

    if model in LARGE:
        import pd_confirm_mine as M

        pod = M.Pod()
        pod.ensure(model)
        return pod
    return httpx.Client(timeout=300.0)


def run_events(model, fn, todo):
    """Local ollama: one event at a time (one 8 GB GPU). Pod: 8 events in parallel so vLLM batches them."""
    if model not in LARGE:
        for r in todo:
            yield fn(r)
        return
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as ex:
        yield from ex.map(fn, todo)


def cmd_run(a):
    check_frozen()
    evs = json.loads(EVENTS.read_text())["events"]
    books, rows = prepare(evs)
    rn = V3.renamers_for(books)
    path = OUT / f"cards_{a.model.replace(':', '_')}.json"
    OUT.mkdir(parents=True, exist_ok=True)
    done = json.loads(path.read_text()) if path.exists() else dict(model=a.model, options=OPTS, prompt=PROMPT, cards={}, status="PARTIAL")
    todo = [r for r in rows if r["measurable"] and r["ev"]["id"] not in done["cards"]][: a.limit]
    t0 = time.time()
    c = client_for(a.model)

    def one(r):
        if True:
            ev, text, cut = r["ev"], r["text"], r["cut"]
            r1 = rn[ev["gutenberg"]][0]
            w_ms, p_ms = pick(r["all_m"]), pick(r["pre_m"])
            ev_pass = dict(W=passages(text, w_ms, None), P=passages(text, p_ms, cut))
            alias = ev["alias"][0]
            cell = {}
            for build in ("W", "P"):
                for arm in ("orig", "ren"):
                    ps = ev_pass[build] if arm == "orig" else r1.rename(ev_pass[build])
                    al = alias if arm == "orig" else r1.rename(alias)
                    card = ask(c, a.model, PROMPT.format(ALIAS=al, PASSAGES=ps))
                    T = r["T"] if arm == "orig" else toks(r1.rename(" ".join(sorted(r["T"]))))
                    cell[f"{build}_{arm}"] = dict(card=card, leak=has_word(card, T), has_alias=al.lower() in card.lower(), words=len(card.split()),
                                                  n_evidence=len(w_ms) if build == "W" else len(p_ms))
            return ev["id"], dict(T=sorted(r["T"]), n_post=r["n_post"], measurable_A=r["measurable_A"], alias_ren=r1.rename(alias),
                                  identity_ren=r1.rename(ev["identity"]), cells=cell)

    for n, (eid, rec) in enumerate(run_events(a.model, one, todo), 1):
        done["cards"][eid] = rec
        path.write_text(json.dumps(done, indent=1))
        print(f"{a.model} {n}/{len(todo)} {eid} {time.time() - t0:.0f}s", flush=True)
    if len([r for r in rows if r["measurable"]]) == len(done["cards"]):
        done["status"] = "COMPLETE"
    done["wall_seconds"] = round(time.time() - t0, 1)
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, "status", done["status"], flush=True)


def cmd_mitigate(a):
    """Addendum 7, fix 2: prefix card from cue-preserving pseudonyms (E4 arm P2 maps), mapped back to original names, scored as P-orig."""
    import pd_v5_cuepres as V5C

    check_frozen()
    evs = json.loads(EVENTS.read_text())["events"]
    books, rows = prepare(evs)
    rn = V3.renamers_for(books)
    maps, _ = V5C.build_maps([e for e in evs if e["gutenberg"] in books], books)
    path = OUT / f"mitig_{a.model.replace(':', '_')}.json"
    done = json.loads(path.read_text()) if path.exists() else dict(model=a.model, options=OPTS, prompt=PROMPT, cards={}, status="PARTIAL")
    todo = [r for r in rows if r["measurable"] and r["ev"]["id"] not in done["cards"]]
    t0 = time.time()
    c = client_for(a.model)

    def one(r):
        if True:
            ev, text, cut = r["ev"], r["text"], r["cut"]
            b3 = V5C.make_b3(rn[ev["gutenberg"]][0], maps[ev["gutenberg"]])
            ps = passages(text, pick(r["pre_m"]), cut)
            alias = ev["alias"][0]
            inv = {}
            for t in sorted(set(re.findall(r"\b[A-Z][A-Za-z]+\b", ps + " " + ev["identity"] + " " + alias + " " + " ".join(ev["cast"])))):
                rt = b3(t)
                if rt != t:
                    inv.setdefault(rt, t)
            card = ask(c, a.model, PROMPT.format(ALIAS=b3(alias), PASSAGES=b3(ps)))
            back = re.sub(r"\b[A-Z][A-Za-z]+\b", lambda m: inv.get(m.group(0), m.group(0)), card)
            return ev["id"], dict(T=sorted(r["T"]), measurable_A=r["measurable_A"], cells={"P_pseudo": dict(
                card=back, card_raw=card, leak=has_word(back, r["T"]), has_alias=alias.lower() in back.lower(), words=len(back.split()))})

    for n, (eid, rec) in enumerate(run_events(a.model, one, todo), 1):
        done["cards"][eid] = rec
        path.write_text(json.dumps(done, indent=1))
        if n % 10 == 0:
            print(f"{a.model} mitig {n}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    done["status"] = "COMPLETE" if len(done["cards"]) == len([r for r in rows if r["measurable"]]) else "PARTIAL"
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, done["status"], flush=True)


def naming(rec, k, ev):
    """Alias and identity in the naming arm of cell k: original, first cipher (_ren) or second cipher (_ren2, addendum 10)."""
    if "ren2" in k:
        return rec["alias_ren2"], rec["identity_ren2"]
    if "_ren" in k:
        return rec.get("alias_ren"), rec.get("identity_ren")
    return ev["alias"][0], ev["identity"]


NOSPOIL = "Avoid spoilers: do not reveal secret identities, disguises or plot twists. "


def cmd_robust(a):
    """Addendum 10: don't-spoil instruction on W (both arms) and a second cipher on W and P."""
    check_frozen()
    evs = json.loads(EVENTS.read_text())["events"]
    books, rows = prepare(evs)
    rn = V3.renamers_for(books)
    path = OUT / f"robust_{a.model.replace(':', '_')}.json"
    done = json.loads(path.read_text()) if path.exists() else dict(model=a.model, options=OPTS, prompt=PROMPT, nospoil=NOSPOIL, cards={}, status="PARTIAL")
    todo = [r for r in rows if r["measurable"] and r["ev"]["id"] not in done["cards"]]
    t0 = time.time()
    c = client_for(a.model)

    def one(r):
        ev, text, cut = r["ev"], r["text"], r["cut"]
        r1, r2 = rn[ev["gutenberg"]]
        w, pfx = passages(text, pick(r["all_m"]), None), passages(text, pick(r["pre_m"]), cut)
        alias = ev["alias"][0]
        cells = {}
        for k, pre, ps, al, tset in (("W_orig_nospoil", NOSPOIL, w, alias, r["T"]),
                                     ("W_ren_nospoil", NOSPOIL, r1.rename(w), r1.rename(alias), toks(r1.rename(" ".join(sorted(r["T"]))))),
                                     ("W_ren2", "", r2.rename(w), r2.rename(alias), toks(r2.rename(" ".join(sorted(r["T"]))))),
                                     ("P_ren2", "", r2.rename(pfx), r2.rename(alias), toks(r2.rename(" ".join(sorted(r["T"])))))):
            card = ask(c, a.model, pre + PROMPT.format(ALIAS=al, PASSAGES=ps))
            cells[k] = dict(card=card, leak=has_word(card, tset), has_alias=al.lower() in card.lower(), words=len(card.split()))
        return ev["id"], dict(T=sorted(r["T"]), measurable_A=r["measurable_A"], alias_ren=r1.rename(alias), identity_ren=r1.rename(ev["identity"]),
                              alias_ren2=r2.rename(alias), identity_ren2=r2.rename(ev["identity"]), cells=cells)

    for n, (eid, rec) in enumerate(run_events(a.model, one, todo), 1):
        done["cards"][eid] = rec
        path.write_text(json.dumps(done, indent=1))
        if n % 10 == 0:
            print(f"{a.model} robust {n}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    done["status"] = "COMPLETE" if len(done["cards"]) == len([r for r in rows if r["measurable"]]) else "PARTIAL"
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, done["status"], flush=True)


PROMPT2 = "Describe who the character called {ALIAS} is in this story, in at most 80 words, using only these passages. Passages:\n{PASSAGES}\nDescription:"


def cmd_extra(a):
    """Addendum 11: versioned card at 50% and 75% of the pre-cut alias mentions, and a second prompt for W and P (cipher names)."""
    check_frozen()
    evs = json.loads(EVENTS.read_text())["events"]
    books, rows = prepare(evs)
    rn = V3.renamers_for(books)
    path = OUT / f"extra_{a.model.replace(':', '_')}.json"
    done = json.loads(path.read_text()) if path.exists() else dict(model=a.model, options=OPTS, prompt2=PROMPT2, cards={}, status="PARTIAL")
    todo = [r for r in rows if r["measurable"] and r["ev"]["id"] not in done["cards"]]
    t0 = time.time()
    c = client_for(a.model)

    def one(r):
        ev, text, cut = r["ev"], r["text"], r["cut"]
        r1 = rn[ev["gutenberg"]][0]
        alias, pre = ev["alias"][0], r["pre_m"]
        tset = toks(r1.rename(" ".join(sorted(r["T"]))))
        cells = {}
        for k, frac in (("P_ren_pos50", 0.5), ("P_ren_pos75", 0.75)):
            n = max(1, int(round(frac * len(pre))))
            pos = PD.sentence_end(text, pre[n - 1][1])
            ps = r1.rename(passages(text, pick(pre[:n]), pos))
            card = ask(c, a.model, PROMPT.format(ALIAS=r1.rename(alias), PASSAGES=ps))
            cells[k] = dict(card=card, leak=has_word(card, tset), has_alias=r1.rename(alias).lower() in card.lower(), words=len(card.split()), position=pos)
        for k, ps in (("W_ren_p2", passages(text, pick(r["all_m"]), None)), ("P_ren_p2", passages(text, pick(pre), cut))):
            card = ask(c, a.model, PROMPT2.format(ALIAS=r1.rename(alias), PASSAGES=r1.rename(ps)))
            cells[k] = dict(card=card, leak=has_word(card, tset), has_alias=r1.rename(alias).lower() in card.lower(), words=len(card.split()))
        return ev["id"], dict(T=sorted(r["T"]), measurable_A=r["measurable_A"], alias_ren=r1.rename(alias), identity_ren=r1.rename(ev["identity"]), cells=cells)

    for n, (eid, rec) in enumerate(run_events(a.model, one, todo), 1):
        done["cards"][eid] = rec
        path.write_text(json.dumps(done, indent=1))
        if n % 10 == 0:
            print(f"{a.model} extra {n}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    done["status"] = "COMPLETE" if len(done["cards"]) == len([r for r in rows if r["measurable"]]) else "PARTIAL"
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, done["status"], flush=True)


JUDGE, JUDGE_PROMPT = "qwen3:8b", ("A reading assistant wrote this character card.\nCard: {CARD}\n\nDoes the card state or clearly imply that the character "
                                    "called \"{ALIAS}\" is the same person as \"{IDENTITY}\"? Reply as JSON: {{\"identifies\": true}} or {{\"identifies\": false}}.")


def cmd_judge(a):
    """Rule B: a fixed judge outside the generator set reads only the card, the alias and the identity (in the arm's naming)."""
    import httpx

    evs = {e["id"]: e for e in json.loads(EVENTS.read_text())["events"]}
    judge = a.judge or JUDGE
    kind = {"main": "cards", "mitig": "mitig", "robust": "robust", "extra": "extra"}[a.cells]
    src = json.loads((OUT / f"{kind}_{a.of.replace(':', '_')}.json").read_text())
    path = OUT / f"judge_{judge.replace(':', '_')}_of_{a.of.replace(':', '_')}{'' if a.cells == 'main' else '_' + a.cells}.json"
    done = json.loads(path.read_text()) if path.exists() else dict(judge=judge, of=a.of, prompt=JUDGE_PROMPT, labels={})
    schema = {"type": "object", "properties": {"identifies": {"type": "boolean"}}, "required": ["identifies"]}
    t0 = time.time()
    if judge in LARGE:  # addendum 9: second judge on the pod, same prompt and JSON answer, events in parallel
        from concurrent.futures import ThreadPoolExecutor

        pod = client_for(judge)

        def lab_one(item):
            eid, rec = item
            ev, lab = evs[eid], {}
            for k, cell in rec["cells"].items():
                al, ide = naming(rec, k, ev)
                prompt = JUDGE_PROMPT.format(CARD=cell["card"], ALIAS=al, IDENTITY=ide)
                try:
                    lab[k] = bool(json.loads(pod.chat(judge, prompt, 20, schema))["identifies"])
                except (ValueError, KeyError, TypeError):
                    lab[k] = None
            return eid, lab

        with ThreadPoolExecutor(8) as ex:
            for eid, lab in ex.map(lab_one, [it for it in src["cards"].items() if it[0] not in done["labels"]]):
                done["labels"][eid] = lab
        path.write_text(json.dumps(done, indent=1))
    with httpx.Client(timeout=300.0) as c:
        for eid, rec in src["cards"].items():
            if eid in done["labels"]:
                continue
            ev, lab = evs[eid], {}
            for k, cell in rec["cells"].items():
                al, ide = naming(rec, k, ev)
                prompt = JUDGE_PROMPT.format(CARD=cell["card"], ALIAS=al, IDENTITY=ide)
                r = c.post(f"{HOST}/api/chat", json=dict(model=JUDGE, stream=False, think=False, format=schema, options={"temperature": 0, "seed": 20261016, "num_predict": 20},
                                                         messages=[dict(role="user", content=prompt)]))
                r.raise_for_status()
                try:
                    lab[k] = bool(json.loads(r.json()["message"]["content"])["identifies"])
                except (ValueError, KeyError):
                    lab[k] = None
            done["labels"][eid] = lab
            path.write_text(json.dumps(done, indent=1))
    done["status"] = "COMPLETE" if len(done["labels"]) == len(src["cards"]) else "PARTIAL"
    path.write_text(json.dumps(done, indent=1))
    print("wrote", path, len(done["labels"]), f"{time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------ analysis
def boot(per_event: dict, stat, n=NB, seed=SEED_BOOT):
    evs = sorted(per_event)
    rng = random.Random(seed)
    pt = stat([per_event[e] for e in evs])
    bs = sorted(stat([per_event[rng.choice(evs)] for _ in evs]) for _ in range(n))
    return pt, bs[int(0.025 * n)], bs[int(0.975 * n)]


def sign_p(pos, neg):
    n = pos + neg
    return 1.0 if n == 0 else sum(math.comb(n, k) for k in range(pos, n + 1)) / 2 ** n


KEYS = ("W_orig", "W_ren", "P_orig", "P_ren")


def summarise(leak: dict, ids: list, models: list) -> dict:
    """leak[m][event][cell] -> 0/1 (None excluded per model). Pooled per-event value = mean over models with a label."""
    def val(m, i, k):
        v = leak[m].get(i, {}).get(k)
        return None if v is None else float(v)

    ids = [i for i in ids if all(val(m, i, k) is not None for m in models for k in KEYS)]
    out = dict(events=len(ids), per_model={}, pooled={})
    if not ids:
        return out
    for m in models:
        pm = {i: {k: val(m, i, k) for k in KEYS} for i in ids}
        row = {k: sum(pm[i][k] for i in ids) / len(ids) for k in KEYS}
        pos = sum(1 for i in ids if pm[i]["W_ren"] > pm[i]["P_ren"])
        neg = sum(1 for i in ids if pm[i]["W_ren"] < pm[i]["P_ren"])
        row.update(input_channel=row["W_ren"] - row["P_ren"], input_ci=list(boot(pm, lambda xs: sum(x["W_ren"] - x["P_ren"] for x in xs) / len(xs))[1:]),
                   memory_channel=row["P_orig"] - row["P_ren"], memory_ci=list(boot(pm, lambda xs: sum(x["P_orig"] - x["P_ren"] for x in xs) / len(xs))[1:]),
                   both_W_orig_minus_P_orig=row["W_orig"] - row["P_orig"], events_pos=pos, events_neg=neg, sign_p_one_sided=sign_p(pos, neg))
        out["per_model"][m] = row
    pooled = {i: {k: sum(val(m, i, k) for m in models) / len(models) for k in KEYS} for i in ids}
    pt, lo, hi = boot(pooled, lambda xs: sum(x["W_ren"] - x["P_ren"] for x in xs) / len(xs))
    pm_, mlo, mhi = boot(pooled, lambda xs: sum(x["P_orig"] - x["P_ren"] for x in xs) / len(xs))
    pb, blo, bhi = boot(pooled, lambda xs: sum(x["W_orig"] - x["P_orig"] for x in xs) / len(xs))
    npos = sum(1 for r in out["per_model"].values() if r["input_channel"] > 0)
    rates = {k: sum(pooled[i][k] for i in ids) / len(ids) for k in KEYS}
    out["pooled"] = dict(rates=rates, RF1_input_channel=dict(estimate=pt, ci=[lo, hi], models_positive=npos, models=len(models),
                                                               passes=bool(pt >= 0.10 and lo > 0 and npos >= min(2, len(models)))),
                         RF2_P_ren_rate=rates["P_ren"], RF2_valid=bool(rates["P_ren"] <= 0.05),
                         RF3_memory_channel=dict(estimate=pm_, ci=[mlo, mhi]), RF4_W_orig_minus_P_orig=dict(estimate=pb, ci=[blo, bhi]))
    return out


def fixes(cards, judged, A_ids, common, evs, models, res):
    """Addendum 7. Fix 1 = versioned card (W minus P in both arms); fix 2 = pseudonymise and map back (P-orig minus P-pseudo)."""
    labs = {"EXPLICIT", "IMPLIED"}
    out = {}
    for rule, src, ids in (("A", {m: {i: {k: cards[m][i]["cells"][k]["leak"] for k in KEYS} for i in common} for m in models}, [i for i in A_ids if evs[i]["audit"] in labs]),
                           ("B", judged, [i for i in common if evs[i]["audit"] in labs])):
        ms = sorted(src)
        if not ms or not ids:
            continue
        ids = [i for i in ids if all(src[m].get(i, {}).get(k) is not None for m in ms for k in KEYS)]
        pe = {i: {k: sum(float(src[m][i][k]) for m in ms) / len(ms) for k in KEYS} for i in ids}
        f1 = {}
        for arm in ("orig", "ren"):
            pt, lo, hi = boot(pe, lambda xs, arm=arm: sum(x[f"W_{arm}"] - x[f"P_{arm}"] for x in xs) / len(xs))
            f1[arm] = dict(leak_removed=pt, ci=[lo, hi], W_rate=sum(pe[i][f"W_{arm}"] for i in ids) / len(ids), P_residual=sum(pe[i][f"P_{arm}"] for i in ids) / len(ids))
        f1["cost"] = "one extra card build per event at this reader position (one build per distinct evidence horizon in general)"
        f1["content"] = {m: dict(words_W=sum(cards[m][i]["cells"]["W_orig"]["words"] for i in ids) / len(ids), words_P=sum(cards[m][i]["cells"]["P_orig"]["words"] for i in ids) / len(ids),
                                 alias_W=sum(cards[m][i]["cells"]["W_orig"]["has_alias"] for i in ids) / len(ids), alias_P=sum(cards[m][i]["cells"]["P_orig"]["has_alias"] for i in ids) / len(ids)) for m in models}
        out[f"fix1_versioned_rule{rule}"] = dict(events=len(ids), models=ms, **f1)
    # fix 2
    mit, mitj = {}, {}
    for m in models:
        f = OUT / f"mitig_{m.replace(':', '_')}.json"
        if f.exists() and json.loads(f.read_text()).get("status") == "COMPLETE":
            mit[m] = json.loads(f.read_text())["cards"]
        jf = OUT / f"judge_{JUDGE.replace(':', '_')}_of_{m.replace(':', '_')}_mitig.json"
        if jf.exists() and json.loads(jf.read_text()).get("status") == "COMPLETE":
            mitj[m] = json.loads(jf.read_text())["labels"]
    mem = res.get("B_EXPLICIT_IMPLIED", {}).get("pooled", {}).get("RF3_memory_channel", {})
    gate = bool(mem and mem["ci"][0] > 0)
    for rule, ms in (("A", sorted(mit)), ("B", sorted(set(mitj) & set(judged)))):
        if not ms:
            continue
        if rule == "A":
            ids = [i for i in A_ids if evs[i]["audit"] in labs and all(i in mit[m] for m in ms)]
            get = lambda m, i: (float(cards[m][i]["cells"]["P_orig"]["leak"]), float(mit[m][i]["cells"]["P_pseudo"]["leak"]))  # noqa: E731
        else:
            ids = [i for i in common if evs[i]["audit"] in labs and all(judged[m].get(i, {}).get("P_orig") is not None and mitj[m].get(i, {}).get("P_pseudo") is not None for m in ms)]
            get = lambda m, i: (float(judged[m][i]["P_orig"]), float(mitj[m][i]["P_pseudo"]))  # noqa: E731
        if not ids:
            continue
        pe = {i: dict(o=sum(get(m, i)[0] for m in ms) / len(ms), p=sum(get(m, i)[1] for m in ms) / len(ms)) for i in ids}
        pt, lo, hi = boot(pe, lambda xs: sum(x["o"] - x["p"] for x in xs) / len(xs))
        alias_o = sum(cards[m][i]["cells"]["P_orig"]["has_alias"] for m in ms for i in ids) / (len(ms) * len(ids))
        alias_p = sum(mit[m][i]["cells"]["P_pseudo"]["has_alias"] for m in ms for i in ids) / (len(ms) * len(ids))
        out[f"fix2_pseudonymise_rule{rule}"] = dict(events=len(ids), models=ms, P_orig=sum(x["o"] for x in pe.values()) / len(ids), P_pseudo=sum(x["p"] for x in pe.values()) / len(ids),
                                                     reduction=pt, ci=[lo, hi], alias_share_P_orig=alias_o, alias_share_P_pseudo=alias_p,
                                                     RF5_evaluated=gate, RF5_passes=bool(gate and rule == "B" and lo > 0 and alias_o - alias_p <= 0.10) if rule == "B" else None)
    return out


def robust(cards, judged, A_ids, common, evs, models):
    """Addendum 10: don't-spoil instruction on W and a second cipher, against the main W and P cells, per rule."""
    rb, rbj = {}, {}
    for m in models:
        f = OUT / f"robust_{m.replace(':', '_')}.json"
        if f.exists() and json.loads(f.read_text()).get("status") == "COMPLETE":
            rb[m] = json.loads(f.read_text())["cards"]
        jf = OUT / f"judge_{JUDGE.replace(':', '_')}_of_{m.replace(':', '_')}_robust.json"
        if jf.exists() and json.loads(jf.read_text()).get("status") == "COMPLETE":
            rbj[m] = json.loads(jf.read_text())["labels"]
    if not rb:
        return None
    labs = {"EXPLICIT", "IMPLIED"}
    out = dict(models=sorted(rb))
    for rule in ("A", "B"):
        ms = sorted(rb) if rule == "A" else sorted(set(rbj) & set(judged))
        if not ms:
            continue
        ids = [i for i in (A_ids if rule == "A" else common) if evs[i]["audit"] in labs and all(i in rb[m] for m in ms)]

        def g(m, i, k):
            if rule == "A":
                return float((cards[m][i]["cells"].get(k) or rb[m][i]["cells"][k])["leak"])
            v = judged[m][i].get(k) if k in KEYS else rbj[m].get(i, {}).get(k)
            return None if v is None else float(v)

        ks = ("W_ren", "P_ren", "W_orig", "W_ren_nospoil", "W_orig_nospoil", "W_ren2", "P_ren2")
        ids = [i for i in ids if all(g(m, i, k) is not None for m in ms for k in ks)]
        if not ids:
            continue
        pe = {i: {k: sum(g(m, i, k) for m in ms) / len(ms) for k in ks} for i in ids}
        rates = {k: sum(pe[i][k] for i in ids) / len(ids) for k in ks}
        con = {}
        for name, x, y in (("nospoil_vs_versioned_ren", "W_ren_nospoil", "P_ren"), ("instruction_effect_ren", "W_ren", "W_ren_nospoil"),
                           ("instruction_effect_orig", "W_orig", "W_orig_nospoil"), ("input_channel_cipher2", "W_ren2", "P_ren2")):
            pt, lo, hi = boot(pe, lambda xs, x=x, y=y: sum(v[x] - v[y] for v in xs) / len(xs))
            con[name] = dict(estimate=pt, ci=[lo, hi])
        out[f"rule{rule}"] = dict(events=len(ids), models=ms, rates=rates, contrasts=con,
                                  prompting_does_not_remove_leak=bool(con["nospoil_vs_versioned_ren"]["ci"][0] > 0),
                                  robust_to_cipher=bool(con["input_channel_cipher2"]["ci"][0] > 0))
    return out


def extra(cards, judged, A_ids, common, evs, models):
    """Addendum 11: versioned card at earlier positions and a second prompt, against the main W_ren."""
    ex, exj = {}, {}
    for m in models:
        f = OUT / f"extra_{m.replace(':', '_')}.json"
        if f.exists() and json.loads(f.read_text()).get("status") == "COMPLETE":
            ex[m] = json.loads(f.read_text())["cards"]
        jf = OUT / f"judge_{JUDGE.replace(':', '_')}_of_{m.replace(':', '_')}_extra.json"
        if jf.exists() and json.loads(jf.read_text()).get("status") == "COMPLETE":
            exj[m] = json.loads(jf.read_text())["labels"]
    if not ex:
        return None
    labs = {"EXPLICIT", "IMPLIED"}
    out = dict(models=sorted(ex))
    ks = ("W_ren", "P_ren", "P_ren_pos50", "P_ren_pos75", "W_ren_p2", "P_ren_p2")
    for rule in ("A", "B"):
        ms = sorted(ex) if rule == "A" else sorted(set(exj) & set(judged))
        if not ms:
            continue
        ids = [i for i in (A_ids if rule == "A" else common) if evs[i]["audit"] in labs and all(i in ex[m] for m in ms)]

        def g(m, i, k):
            if rule == "A":
                return float((cards[m][i]["cells"].get(k) or ex[m][i]["cells"][k])["leak"])
            v = judged[m][i].get(k) if k in KEYS else exj[m].get(i, {}).get(k)
            return None if v is None else float(v)

        ids = [i for i in ids if all(g(m, i, k) is not None for m in ms for k in ks)]
        if not ids:
            continue
        pe = {i: {k: sum(g(m, i, k) for m in ms) / len(ms) for k in ks} for i in ids}
        rates = {k: sum(pe[i][k] for i in ids) / len(ids) for k in ks}
        con = {}
        for name, x, y in (("W_minus_P_pos50", "W_ren", "P_ren_pos50"), ("W_minus_P_pos75", "W_ren", "P_ren_pos75"), ("prompt2_input_channel", "W_ren_p2", "P_ren_p2")):
            pt, lo, hi = boot(pe, lambda xs, x=x, y=y: sum(v[x] - v[y] for v in xs) / len(xs))
            con[name] = dict(estimate=pt, ci=[lo, hi])
        out[f"rule{rule}"] = dict(events=len(ids), models=ms, rates=rates, contrasts=con, robust_to_prompt=bool(con["prompt2_input_channel"]["ci"][0] > 0))
    return out


def cmd_analyze(_a):
    small = analyse(lambda m: m not in LARGE)
    large = analyse(lambda m: m in LARGE, quiet=False)
    if large:
        small["larger"] = large
    (OUT / "analysis.json").write_text(json.dumps(small, indent=1, default=float))


def analyse(keep, quiet=False):
    evs = {e["id"]: e for e in json.loads(EVENTS.read_text())["events"]}
    cards, judged, not_run = {}, {}, []
    for f in sorted(OUT.glob("cards_*.json")):
        d = json.loads(f.read_text())
        if not keep(d["model"]):
            continue
        (cards.__setitem__(d["model"], d["cards"]) if d.get("status") == "COMPLETE" else not_run.append(d["model"]))
    for m in cards:
        jf = OUT / f"judge_{JUDGE.replace(':', '_')}_of_{m.replace(':', '_')}.json"
        if jf.exists() and json.loads(jf.read_text()).get("status") == "COMPLETE":
            judged[m] = json.loads(jf.read_text())["labels"]
    if not cards:
        return None
    models = sorted(cards)
    common = sorted(set.intersection(*[set(c) for c in cards.values()]))
    rule_a = {m: {i: {k: cards[m][i]["cells"][k]["leak"] for k in KEYS} for i in common} for m in models}
    ok = lambda i, labs: evs[i].get("audit") in labs  # noqa: E731
    A_ids = [i for i in common if cards[models[0]][i]["measurable_A"]]
    res = dict(label_provenance="rule A TEXT-DERIVED; rule B labelled by a judge model (qwen3:8b); events model-selected; no human labels",
               models=models, not_run=not_run, judged_models=sorted(judged))
    res["A_primary_EXPLICIT_IMPLIED"] = summarise(rule_a, [i for i in A_ids if ok(i, {"EXPLICIT", "IMPLIED"})], models)
    res["A_EXPLICIT_only"] = summarise(rule_a, [i for i in A_ids if ok(i, {"EXPLICIT"})], models)
    if judged:
        jm = sorted(judged)
        res["B_EXPLICIT_IMPLIED"] = summarise(judged, [i for i in common if ok(i, {"EXPLICIT", "IMPLIED"})], jm)
        res["B_EXPLICIT_only"] = summarise(judged, [i for i in common if ok(i, {"EXPLICIT"})], jm)
    j2 = {}
    for m in cards:  # addendum 9: second judge, reported beside rule B only
        jf = OUT / f"judge_olmo32b_of_{m.replace(':', '_')}.json"
        if jf.exists() and json.loads(jf.read_text()).get("status") == "COMPLETE":
            j2[m] = json.loads(jf.read_text())["labels"]
    if j2:
        res["B2_second_judge_olmo32b"] = summarise(j2, [i for i in common if ok(i, {"EXPLICIT", "IMPLIED"})], sorted(j2))
        pairs = [(judged[m][i][k], j2[m][i][k]) for m in j2 if m in judged for i in common for k in KEYS
                 if judged[m].get(i, {}).get(k) is not None and j2[m].get(i, {}).get(k) is not None]
        if pairs:
            n = len(pairs)
            po = sum(x == y for x, y in pairs) / n
            p1, p2 = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
            pe = p1 * p2 + (1 - p1) * (1 - p2)
            res["judge_agreement"] = dict(labels=n, identical=po, kappa=(po - pe) / (1 - pe) if pe < 1 else None, rate_judge1=p1, rate_judge2=p2)
    res["robust"] = robust(cards, judged, A_ids, common, evs, models)
    res["extra"] = extra(cards, judged, A_ids, common, evs, models)
    res["utility"] = {m: dict(alias_in_card_share={k: sum(cards[m][i]["cells"][k]["has_alias"] for i in common) / len(common) for k in KEYS},
                              mean_words={k: sum(cards[m][i]["cells"][k]["words"] for i in common) / len(common) for k in KEYS}) for m in models}
    res["fixes"] = fixes(cards, judged, A_ids, common, evs, models, res)
    res["empty_cards"] = {m: sum(1 for i in common for k in KEYS if not cards[m][i]["cells"][k]["card"]) for m in models}
    print("fixes", json.dumps(res["fixes"], default=float)[:1500])
    print("== stratum", models)
    for sn in [k for k in res if k[:2] in ("A_", "B_")]:
        o = res[sn]
        print(sn, "events", o["events"], json.dumps(o.get("pooled"), default=float)[:700])
        for m, r in o["per_model"].items():
            print("  ", m, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k in KEYS or k in ("input_channel", "memory_channel", "events_pos", "events_neg", "sign_p_one_sided")})
    return res


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("freeze")
    r = sp.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--limit", type=int, default=10**6)
    sp.add_parser("analyze")
    j = sp.add_parser("judge")
    j.add_argument("--of", required=True)
    j.add_argument("--cells", choices=("main", "mitig", "robust", "extra"), default="main")
    j.add_argument("--judge", default=None, help="addendum 9: olmo32b as a second judge (pod)")
    mg = sp.add_parser("mitigate")
    mg.add_argument("--model", required=True)
    rb = sp.add_parser("robust")
    rb.add_argument("--model", required=True)
    ex = sp.add_parser("extra")
    ex.add_argument("--model", required=True)
    a = ap.parse_args()
    dict(freeze=cmd_freeze, run=cmd_run, analyze=cmd_analyze, judge=cmd_judge, mitigate=cmd_mitigate, robust=cmd_robust, extra=cmd_extra)[a.cmd](a)


if __name__ == "__main__":
    main()
