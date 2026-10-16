"""Confirmatory study, step 2: mine, verify and audit alias-reveal events (PD_CONFIRM_event_mining_rules_v1.md sections 3 to 7, with the
amendments of PREREG_PD_CONFIRM_v2_L40S.md and the deviations logged in PD_CONFIRM_deviations.md).

Callers: run by hand after pd_confirm_select.py. Reads PD_confirm_books_v1.json and data/raw/pd_confirm/texts/; talks to the pod router
(RUNPOD_BASE_URL / RUNPOD_VLLM_KEY from the environment, never printed). Outputs under data/scratch/confirm/ (disposable) and, at `freeze`,
docs/research/preregistrations/PD_confirm_events_v1.json in the same schema as the PD v1-v7 event files (id, book, gutenberg, alias,
identity, cast, reveal_sentence, cut, caveat) plus fame/split/audit fields, so pd_v3 / pd_v6 builders can run it unchanged.

  mine    [--max-per-book 60]   qwen32b: miner on candidate sentences, deterministic verification, person filter for the cast list
  audit                         mistral24: EXPLICIT / IMPLIED / NOT_SUPPORTED on the reveal passage
  freeze                        select <= 5 events per book in draw order up to 150, write the events file and its hash
Label provenance: TEXT-DERIVED oracle, model-selected events; no human verification exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_reveal_benchmark as PD  # noqa: E402

P = Path("docs/research/preregistrations")
RAW = Path("data/raw/pd_confirm/texts")
SCR = Path("data/scratch/confirm")
TARGET = 75  # PREREG_PD_CONFIRM_v2_addendum_2.md (halved scope)
PROMPTS = json.loads((P / "PD_confirm_prompts_v1.json").read_text())
CUES = ["was none other than", "was in reality", "was in fact", "was really", "in reality", "the real ", "disguised as", "in disguise",
        "under the name", "under the assumed name", "assumed the name", "alias", "otherwise known as", "known to the world as",
        "threw off his disguise", "threw off her disguise", "unmasked", "revealed himself", "revealed herself", "you are the",
        "it was he who", "it was she who"]
# efficiency prefilter for the large rounds (addendum 4): only the cues that name a person right after them
PREFILTER = re.compile(r"(none other than|was really|was in reality|was in fact|alias|otherwise known as|known to the world as|under the (?:assumed )?name|"
                       r"assumed the name|disguised as|you are the)[^.]{0,80}\b[A-Z][a-z]{2,}", re.S)
ABBR = r"(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bSt)(?<!\bMme)(?<!\bCol)(?<!\bCapt)(?<!\bMlle)(?<![A-Z])"
SENT = re.compile(r".*?" + ABBR + r"[.!?]+[”\"’')]*(?=\s|$)", re.S)
CHAPTER = re.compile(r"^[ \t]*((?:CHAPTER|Chapter|BOOK|Book|PART|Part)\b[^\n]{0,50}|[IVXL]{1,6}\.?)[ \t]*$", re.M)
HONOR = {"Mr", "Mrs", "Miss", "Sir", "Lady", "Lord", "Dr", "Madame", "Mademoiselle", "Monsieur", "Captain", "Colonel", "General"}
STOP_PROPER = {"God", "Lord", "Heaven", "Christmas", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"}


def strip_gutenberg(t: str) -> str:
    a = t.find("*** START")
    a = t.find("\n", a) + 1 if a >= 0 else 0
    b = t.find("*** END")
    return t[a:b] if b > a else t[a:]


def sentences(text: str):
    return [(m.start(), m.end()) for m in SENT.finditer(text)]


def candidates(text: str, gid: int, cap: int):
    ss = sentences(text)
    out = []
    for i, (a, b) in enumerate(ss):
        s = text[a:b]
        low = s.lower()
        if i < 2 or len(s) > 600 or not any(c in low for c in CUES):
            continue
        pa = ss[i - 2][0]
        passage = text[pa:b]
        if len(set(re.findall(r"\b[A-Z][a-z]{2,}\b", passage))) < 2:
            continue
        out.append(dict(gid=gid, sent_start=a, sent_end=b, passage=" ".join(passage.split()), cue_sentence=" ".join(s.split())))
    rng = random.Random(20261101 + gid)
    if len(out) > cap:
        out = sorted(rng.sample(out, cap), key=lambda c: c["sent_start"])
    return out


# ---------------------------------------------------------------- model calls through the pod router
class Pod:
    def __init__(self):
        self.base = os.environ["RUNPOD_BASE_URL"].rstrip("/")
        self.key = os.environ["RUNPOD_VLLM_KEY"]
        self.c = httpx.Client(timeout=180.0, limits=httpx.Limits(max_connections=16))
        self.calls = 0

    def chat(self, model, prompt, max_tokens, schema=None):
        body = dict(model=model, messages=[dict(role="user", content=prompt)], temperature=0, seed=20261016, max_tokens=max_tokens)
        if schema:
            body["response_format"] = dict(type="json_schema", json_schema=dict(name="a", schema=schema))
        for k in range(6):
            try:
                r = self.c.post(f"{self.base}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.key}"})
                if r.status_code == 503:
                    time.sleep(10)
                    continue
                if r.status_code in (401, 403):
                    sys.exit("stopping: endpoint refused the key")
                r.raise_for_status()
                self.calls += 1
                return r.json()["choices"][0]["message"]["content"] or ""
            except httpx.HTTPError:
                time.sleep(2 * (k + 1))
        return ""

    def ensure(self, model, max_wait=1500):
        t0 = time.time()
        while time.time() - t0 < max_wait:
            try:
                r = self.c.post(f"{self.base}/chat/completions", headers={"Authorization": f"Bearer {self.key}"},
                                json=dict(model=model, messages=[dict(role="user", content="Say OK.")], max_tokens=3, temperature=0))
            except httpx.HTTPError:
                time.sleep(10)
                continue
            if r.status_code == 200:
                print(f"{model} ready after {time.time() - t0:.0f}s", flush=True)
                return
            if r.status_code in (401, 403):
                sys.exit("stopping: endpoint refused the key")
            time.sleep(10)
        sys.exit(f"stopping: {model} not ready")


def parse_json(txt: str):
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


# ---------------------------------------------------------------- deterministic verification
def toks(s: str):
    return [t for t in re.findall(r"[A-Z][a-z]+", s) if t not in HONOR and len(t) >= 3]


def verify(text: str, book: dict, c: dict, mined: dict):
    """Rules section 5, steps 1 to 5 (the cast list, step 6, is built after the person filter). Returns (event_core, None) or (None, reason)."""
    alias = [a for a in mined.get("alias_surfaces", []) if isinstance(a, str) and a.strip()]
    ident = mined.get("identity_name")
    rev = mined.get("reveal_sentence")
    if not alias or not isinstance(ident, str) or not isinstance(rev, str) or " ".join(rev.split()) not in c["passage"]:
        return None, "miner output unusable or not verbatim"
    if not toks(ident):
        return None, "identity has no capitalised name token"
    if set(toks(ident)) & {t for a in alias for t in toks(a)}:
        return None, "identity shares a capitalised token with an alias"
    if len(PD.ws_regex(rev).findall(text)) != 1:
        return None, "reveal sentence not found exactly once"
    rv = PD.ws_regex(rev).search(text)
    heads = [m for m in CHAPTER.finditer(text) if m.start() < rv.start()]
    cands = []
    if heads:
        h = heads[-1]
        cands.append((h.start(), dict(regex=" ".join(re.escape(w) for w in h.group(1).split()), back=0), "chapter heading"))
    p = max(0, rv.start() - 200)
    p = text.rfind("\n\n", 0, p)
    p = p + 2 if p >= 0 else max(0, rv.start() - 200)
    phrase = " ".join(text[p:p + 120].split()[:6])
    if phrase:
        cands.append((p, dict(regex=" ".join(re.escape(w) for w in phrase.split()), back=0), "phrase"))
    ev = dict(id="tmp", book=book["title"], gutenberg=book["id"], alias=alias, identity=ident, cast=[], reveal_sentence=" ".join(rev.split()), caveat="")
    reason = "no cutoff gave >= 3 alias mentions"
    for cutpos, cut, kind in cands:
        if cutpos >= rv.start():
            continue
        ev["cut"] = cut
        try:
            loc = PD.locate(ev, text)
        except AssertionError:
            continue
        if loc["cut"] != cutpos:
            reason = "cut anchor not unique"
            continue
        pre = loc["pre"]
        if len(pre) < 3:
            continue
        it = toks(ident)
        near = any(re.search("|".join(r"\b" + re.escape(t) + r"\b" for t in it), text[max(0, m[0] - 200):m[1] + 200]) for m in pre)
        if near or loc["prefix_sentences_with_alias_and_identity_token"] > 0:
            reason = "identity token near an alias before the cutoff"
            continue
        return dict(ev=ev, cutpos=cutpos, cut_kind=kind, n_pre=len(pre), n_post=len(loc["post"]), identity_in_prefix=loc["identity_in_prefix"]), None
    return None, reason


def cast_candidates(text: str, core: dict):
    """Frequent proper-name surfaces in the prefix (rules 5.6): capitalised, >= 3 letters, never seen lower-case in the book."""
    cut = core["cutpos"]
    allt = re.findall(r"\b[A-Za-z]{3,}\b", text)
    lower = {t for t in allt if t[0].islower()}
    skip = set(toks(core["ev"]["identity"])) | {t for a in core["ev"]["alias"] for t in toks(a)} | STOP_PROPER
    cnt = Counter(t for t in re.findall(r"\b[A-Z][a-z]{2,}\b", text[:cut]) if t.lower() not in lower and t not in skip and t not in HONOR)
    return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:16]


def cmd_mine(a):
    books = json.loads((P / "PD_confirm_books_v1.json").read_text())["books"]
    if a.rounds:
        keep = {int(x) for x in a.rounds.split(",")}
        books = [b for b in books if b.get("round", 1) in keep]  # rounds 4+ are mined separately (addendum 4)
    SCR.mkdir(parents=True, exist_ok=True)
    done_ids = set()  # books already processed by an earlier run of this stage (resumable)
    for f in SCR.glob("verified_events*.json"):
        done_ids |= set(json.loads(f.read_text()).get("processed", []))
    books = [b for b in books if b["id"] not in done_ids]
    pod = Pod()
    pod.ensure("qwen32b")
    t_start = time.time()
    jobs, processed = [], []
    stats = dict(books_seen=0, books_skipped=0, candidates=0)
    texts = {}
    for b in books:
        f = RAW / f"pg{b['id']}.txt"
        if not f.exists():
            stats["books_skipped"] += 1
            continue
        t = strip_gutenberg(f.read_text(encoding="utf-8", errors="replace"))
        nw = len(t.split())
        if not (40000 <= nw <= 400000):
            stats["books_skipped"] += 1
            continue
        texts[b["id"]] = t
        processed.append(b["id"])
        stats["books_seen"] += 1
        for c in candidates(t, b["id"], a.max_per_book):
            if a.prefilter and not PREFILTER.search(c["cue_sentence"]):
                continue
            jobs.append((b, c))
    stats["candidates"] = len(jobs)
    print(stats, flush=True)

    def work(j):
        b, c = j
        out = pod.chat("qwen32b", PROMPTS["miner"].replace("{PASSAGE}", c["passage"]), 260)
        return b, c, parse_json(out)

    kept, reasons = [], Counter()
    with ThreadPoolExecutor(14) as ex:
        for n, (b, c, m) in enumerate(ex.map(work, jobs), 1):
            if n % 300 == 0:
                print(f"{n}/{len(jobs)} miner calls, {time.time() - t_start:.0f}s, kept {len(kept)}", flush=True)
            if not m or m.get("none"):
                reasons["miner: none"] += 1
                continue
            core, why = verify(texts[b["id"]], b, c, m)
            if core is None:
                reasons[why] += 1
                continue
            kept.append((b, c, core))
    print("verified before cast:", len(kept), dict(reasons), flush=True)
    seen, uniq = set(), []
    for b, c, core in kept:  # one event per (book, identity)
        k = (b["id"], tuple(sorted(toks(core["ev"]["identity"]))))
        if k not in seen:
            seen.add(k)
            uniq.append((b, c, core))

    def cast_job(x):
        b, c, core = x
        cc = cast_candidates(texts[b["id"]], core)
        if len(cc) < 7:
            return x, None, cc
        lst = ", ".join(t for t, _ in cc)
        out = pod.chat("qwen32b", f"From this list of capitalised words taken from a novel, return the ones that are the first names or surnames of individual PEOPLE (characters), not places, titles, nations, months or common words. List: {lst}\nReply with a JSON object {{\"people\": [..]}}.", 120)
        m = parse_json(out) or {}
        return x, [t for t in m.get("people", []) if t in dict(cc)], cc

    final = []
    with ThreadPoolExecutor(14) as ex:
        for (b, c, core), people, cc in ex.map(cast_job, uniq):
            if people is None or len(people) < 7:
                reasons["cast: fewer than 7 person names"] += 1
                continue
            freq = dict(cc)
            cast = sorted(people, key=lambda t: (-freq[t], t))[:9]
            if sum(freq[t] for t in cast) < 8:
                reasons["cast: fewer than 8 mentions"] += 1
                continue
            core["ev"]["cast"] = cast + [core["ev"]["identity"]]
            final.append(dict(book=b, gid=b["id"], passage=c["passage"], ev=core["ev"], cutpos=core["cutpos"], cut_kind=core["cut_kind"],
                              n_pre=core["n_pre"], n_post=core["n_post"], identity_in_prefix=core["identity_in_prefix"]))
    (SCR / a.out_name).write_text(json.dumps(dict(stats=stats, reasons=reasons, events=final, processed=processed), indent=1))
    print("events after cast filter:", len(final), "books with events:", len({e["gid"] for e in final}), "reasons", dict(reasons),
          f"wall {time.time() - t_start:.0f}s", flush=True)


def cmd_audit(a):
    d = dict(events=[])
    for f in sorted(SCR.glob("verified_events*.json")):
        d["events"] += json.loads(f.read_text())["events"]
    pod = Pod()
    pod.ensure("mistral24")
    schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": ["EXPLICIT", "IMPLIED", "NOT_SUPPORTED"]}}, "required": ["answer"]}

    def work(e):
        ev = e["ev"]
        txt = PROMPTS["auditor"].replace("{PASSAGE}", e["passage"]).replace("{ALIAS}", ev["alias"][0]).replace("{IDENTITY}", ev["identity"])
        m = parse_json(pod.chat("mistral24", txt, 20, schema)) or {}
        return m.get("answer", "MISSING")

    with ThreadPoolExecutor(14) as ex:
        labels = list(ex.map(work, d["events"]))
    for e, l in zip(d["events"], labels):
        e["audit"] = l
    d["audit_counts"] = dict(Counter(labels))
    (SCR / "audited_events.json").write_text(json.dumps(d, indent=1))
    print("audit:", d["audit_counts"])


def cmd_freeze(a):
    d = json.loads((SCR / "audited_events.json").read_text())
    order = {b["id"]: b["order"] for b in json.loads((P / "PD_confirm_books_v1.json").read_text())["books"]}
    by_book = {}
    for e in d["events"]:
        by_book.setdefault(e["gid"], []).append(e)
    chosen = []
    for gid in sorted(by_book, key=lambda g: order[g]):
        evs = sorted(by_book[gid], key=lambda e: e["cutpos"])
        random.Random(20261101 + gid).shuffle(evs)
        chosen += evs[:5]
        if len(chosen) >= TARGET:
            chosen = chosen[:TARGET]
            break
    out = []
    for e in sorted(chosen, key=lambda e: (e["gid"], e["cutpos"])):
        ev = dict(e["ev"])
        ev["id"] = f"C{e['gid']}_{len([x for x in out if x['gutenberg'] == e['gid']]) + 1}"
        ev.update(W=e["book"]["W"], band=e["book"]["band"], split=e["book"]["split"], audit=e["audit"], cut_kind=e["cut_kind"],
                  identity_in_prefix=e["identity_in_prefix"], n_pre_alias=e["n_pre"], n_post_alias=e["n_post"], caveat="model-mined; text-derived oracle; no human check")
        out.append(ev)
    f = P / "PD_confirm_events_v1.json"
    if f.exists():
        sys.exit("REFUSING: events file exists (frozen); a change is a new version")
    f.write_text(json.dumps(dict(provenance="TEXT-DERIVED oracle; events mined by qwen32b and audited by mistral24; no human verification", events=out), indent=1))
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    man = P / "MANIFEST_PD_CONFIRM_v2.json"
    m = json.loads(man.read_text())
    m["files_sha256"]["PD_confirm_events_v1.json"] = h
    m["status"] = "FROZEN; events file hashed at CP-L, before any confirmatory model call"
    man.write_text(json.dumps(m, indent=1))
    print("frozen", len(out), "events from", len({e["gutenberg"] for e in out}), "books;", dict(Counter(e["audit"] for e in out)),
          dict(Counter(e["split"] for e in out)), dict(Counter(e["band"] for e in out)), "sha", h[:12])


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("mine")
    m.add_argument("--max-per-book", type=int, default=60)
    m.add_argument("--rounds", default="")
    m.add_argument("--out-name", default="verified_events.json")
    m.add_argument("--prefilter", action="store_true")
    sp.add_parser("audit")
    sp.add_parser("freeze")
    a = ap.parse_args()
    dict(mine=cmd_mine, audit=cmd_audit, freeze=cmd_freeze)[a.cmd](a)


if __name__ == "__main__":
    main()
