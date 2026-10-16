"""L1: LLM leakage and evidence-gated linking on the 72-item pilot (implements PREREG_L1_llm_leakage.md v1).

LABEL PROVENANCE: all reference labels are SILVER (model-drafted gold for gold-sourced items; the system's own link
for system-sourced items). Reveal chapters come ONLY from repo structured data (alias_binding learned chapters of the
title-holder pass, and `observation` rows), never from a model. Nothing here is a human label.

Modes
  --dry-run   builds every prompt locally, derives reveal chapters, estimates tokens and cost. No key, no network.
  --run       calls the model. Requires --budget-usd and OPENAI_API_KEY in the environment (never printed). Stops
              before any call that could push the running worst-case cost over the budget. Run each arm once.

Prompts are loaded from docs/research/preregistrations/L1_prompts_v1.json and refused unless their SHA-256 matches
MANIFEST_L1.json. Prompt text and model quotations (novel text) are NEVER written to disk: only hashes, lengths,
letters and span offsets.
"""

from __future__ import annotations

import argparse
import csv
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

from t4_renaming import TOKEN, build_pi  # noqa: E402

from echotales.core.store import Store  # noqa: E402

NOVEL = "reverend-insanity"
SHEET = "data/eval/human_review_chimera_pilot.csv"
KEY = "data/eval/human_review_chimera_pilot_key.csv"
PROMPTS = "docs/research/preregistrations/L1_prompts_v1.json"
MANIFEST = "docs/research/preregistrations/MANIFEST_L1.json"

MODEL = "gpt-5.6-luna"
PRICE_IN = 0.20 / 1e6    # USD per input token, Standard, <=272K context (OpenAI pricing page, 2026-10-15)
PRICE_OUT = 1.20 / 1e6   # USD per output token
WINDOW_CHARS = 1200
CHARS_PER_TOKEN = 3.5    # conservative (English is ~4); no tokenizer installed. Estimate, not a measurement.
OVERHEAD_TOK = 15        # per-call message framing allowance
CAPS = {"A": 150, "B": 150, "C": 150, "D1": 300, "D2": 50}  # max_completion_tokens per call (bounds worst case)
SEED_BOOT = 20261016


# ------------------------------------------------------------------ stats
def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, (c - r) / d), min(1.0, (c + r) / d)]


def row(k: int, n: int) -> dict:
    return dict(k=k, n=n, rate=(k / n if n else None), wilson95=wilson(k, n))


def binom_tail_ge(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def paired_bootstrap(a: list[int], b: list[int], reps: int = 10000) -> dict:
    n = len(a)
    if n == 0:
        return dict(n=0)
    rng = random.Random(SEED_BOOT)
    diffs = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    return dict(n=n, mean_diff=sum(x - y for x, y in zip(a, b)) / n, ci95=[diffs[int(0.025 * reps)], diffs[int(0.975 * reps)]])


# ------------------------------------------------------------------ items
def norm(s: str) -> str:
    return re.sub(r"[^a-z ]", "", s.lower().split(" (")[0]).strip()


def parse_cands(s: str) -> list[tuple[str, str, str]]:
    out = []
    for part in s.split(" | "):
        m = re.match(r"([A-Z])\.\s+(.*?)\s+\[([0-9a-f]{4})\]\s*$", part.strip())
        if m:
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def load_items(store: Store) -> list[dict]:
    sheet = {r["item_id"]: r for r in csv.DictReader(open(SHEET, encoding="utf-8"))}
    key = {r["item_id"]: r for r in csv.DictReader(open(KEY, encoding="utf-8"))}
    con = store.conn
    labels = dict(con.execute("select id, canonical_label from self_entity where novel_id=?", (NOVEL,)).fetchall())
    by_label: dict[str, list[str]] = defaultdict(list)
    for i, lab in labels.items():
        by_label[norm(lab)].append(i)
    items = []
    for iid, k in key.items():
        if k["category"] == "not_entity_control":
            continue
        s = sheet[iid]
        c = float(s["chapter"])
        cands = parse_cands(s["candidates"])
        if k["source"] == "system":
            truth_ids = [k["system_target"]]
        else:
            truth_ids = by_label.get(norm(k["gold_identity"]), [])
        truth_letter, truth_id = None, None
        for L, _n, i4 in cands:
            hit = next((t for t in truth_ids if t.endswith(i4)), None)
            if hit:
                truth_letter, truth_id = L, hit
                break
        # repo-derived reveal chapter (never from a model)
        reveal = None
        if k["category"] == "clan_head_prereveal":
            r = con.execute(
                "select min(learned_chapter) from alias_binding where novel_id=? and target_id=? "
                "and alias_norm like '%clan head%' and learned_chapter>?", (NOVEL, k["system_target"], c)).fetchone()[0]
            reveal = ("alias_binding(title-holder pass)", r) if r else None
        elif truth_id:
            r = con.execute(
                "select min(learned_chapter) from observation where fact_ref like ? and learned_chapter>?",
                (f"alias:{truth_id}:%", c)).fetchone()[0]
            reveal = ("observation", r) if r else None
        surf = s["mention_surface"]
        cand_tokens = {t.lower() for _L, n, _i in cands for t in TOKEN.findall(n)}
        trivial = any(t.lower() in cand_tokens for t in TOKEN.findall(surf) if t[:1].isupper())
        items.append(dict(
            id=iid, tier=k["tier"], category=k["category"], source=k["source"], chapter=c,
            offset=int(s["mention_offset"]), surface=surf, cands=cands, truth_letter=truth_letter,
            reveal_chapter=(reveal[1] if reveal else None), reveal_source=(reveal[0] if reveal else None),
            string_trivial=trivial,
        ))
    return items


def sentence_end(text: str, pos: int) -> int:
    m = re.compile(r"[.!?…][\"”’')\]]*(?:\s|$)").search(text, pos)
    return m.end() if m else len(text)


def build_window(chapters: dict[float, str], item: dict) -> tuple[str, int]:
    """Prefix window (<= WINDOW_CHARS chars) ending at the end of the mention's sentence; mention marked [[ ]]."""
    text = chapters[item["chapter"]]
    off, surf = item["offset"], item["surface"]
    assert text[off:off + len(surf)].lower() == surf.lower(), (item["id"], text[off:off + len(surf)], surf)
    end = sentence_end(text, off + len(surf))
    pre = text[:end]
    prev = item["chapter"] - 1
    while len(pre) < WINDOW_CHARS and prev in chapters:  # still prefix-only: earlier chapters
        pre = chapters[prev] + "\n\n" + pre
        off += len(chapters[prev]) + 2
        prev -= 1
    start = max(0, len(pre) - WINDOW_CHARS)
    window = pre[start:]
    off -= start
    assert off >= 0, "mention fell outside the window"
    return window[:off] + "[[" + window[off:off + len(surf)] + "]]" + window[off + len(surf):], start


# ------------------------------------------------------------------ prompts
def load_prompts() -> dict:
    raw = Path(PROMPTS).read_bytes()
    man = json.loads(Path(MANIFEST).read_text()) if Path(MANIFEST).exists() else {}
    want = man.get("prompts_file_sha256")
    if want is None or hashlib.sha256(raw).hexdigest() != want:
        sys.exit("REFUSING: prompts file hash does not match MANIFEST_L1.json (frozen prompts were changed or not frozen)")
    d = json.loads(raw)
    for name, h in man["template_sha256"].items():
        if hashlib.sha256(d[name].encode()).hexdigest() != h:
            sys.exit(f"REFUSING: template {name} hash mismatch")
    return d


def fill(tpl: str, **kw: str) -> str:
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", v)
    return tpl


def cand_block(cands, rename=None) -> str:
    return "\n".join(f"{L}. {rename(n) if rename else n}" for L, n, _i in cands)


def mask_text(text: str, vocab: set[str], mp: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        t = m.group(0)
        if t not in vocab:
            return t
        if t not in mp:
            mp[t] = f"[N{len(mp) + 1}]"
        return mp[t]

    return TOKEN.sub(sub, text)


def build_prompts(items, chapters, pi, tpl):
    out = []
    for it in items:
        win, start = build_window(chapters, it)
        cands = it["cands"]
        d = dict(item=it, window_start=start, window_len=len(win))
        d["A"] = fill(tpl["A_B_prefix"], WINDOW=win, SURFACE=it["surface"], CANDIDATES=cand_block(cands))
        d["B"] = fill(tpl["A_B_prefix"], WINDOW=pi.rename(win), SURFACE=pi.rename(it["surface"]),
                      CANDIDATES=cand_block(cands, pi.rename))
        d["C_orig"] = fill(tpl["C_closed_book"], SURFACE=it["surface"], CHAPTER=str(int(it["chapter"])),
                           CANDIDATES=cand_block(cands))
        d["C_ren"] = fill(tpl["C_closed_book"], SURFACE=pi.rename(it["surface"]), CHAPTER=str(int(it["chapter"])),
                          CANDIDATES=cand_block(cands, pi.rename))
        d["D1"] = fill(tpl["D1_gated_call1"], WINDOW=win, SURFACE=it["surface"], CANDIDATES=cand_block(cands))
        d["_window"] = win
        out.append(d)
    return out


def est_tokens(s: str) -> int:
    return math.ceil(len(s) / CHARS_PER_TOKEN) + OVERHEAD_TOK


def d2_prompt(tpl, surface, claimed_name, spans, vocab):
    """None means automatic NOT_ENTAILED: the claimed individual's name never appears in the cited spans."""
    claimed_tokens = [t for t in TOKEN.findall(claimed_name) if t in vocab]
    joined = " ".join(spans)
    if not claimed_tokens or not any(t in TOKEN.findall(joined) for t in claimed_tokens):
        return None
    mp: dict[str, str] = {}
    ms = mask_text(" || ".join(spans), vocab, mp)
    msurf = mask_text(surface, vocab, mp)
    mclaimed = mask_text(claimed_name, vocab, mp)
    return fill(tpl["D2_entailment_call2"], MASKED_SPANS=ms, MASKED_SURFACE=msurf, MASKED_CLAIMED=mclaimed)


# ------------------------------------------------------------------ sets / dry run
def sets(items):
    prim = [i for i in items if i["tier"] == "P" and i["reveal_chapter"] is not None and i["truth_letter"]]
    ctrl = [i for i in items if i["category"] == "plain_control" and i["truth_letter"]]
    other_p = [i for i in items if i["tier"] == "P" and i not in prim]
    cb = [i for i in items if not i["string_trivial"] and i["truth_letter"]]
    return prim, ctrl, other_p, cb


def dry_run(args, items, chapters, pi, tpl):
    prompts = build_prompts(items, chapters, pi, tpl)
    prim, ctrl, other_p, cb = sets(items)
    cb_ids = {i["id"] for i in cb}
    calls, toks_in, toks_cap = Counter(), Counter(), Counter()
    for d in prompts:
        it = d["item"]
        for arm in ("A", "B", "D1"):
            calls[arm] += 1
            toks_in[arm] += est_tokens(d[arm])
            toks_cap[arm] += CAPS[arm]
        if it["id"] in cb_ids:
            for key in ("C_orig", "C_ren"):
                calls["C"] += 1
                toks_in["C"] += est_tokens(d[key])
                toks_cap["C"] += CAPS["C"]
    n = len(prompts)
    d2_in = n * (est_tokens(tpl["D2_entailment_call2"]) + math.ceil(2 * 400 / CHARS_PER_TOKEN))
    calls["D2_max"], toks_in["D2_max"], toks_cap["D2_max"] = n, d2_in, n * CAPS["D2"]
    exp_in = sum(toks_in.values())
    exp_out = (calls["A"] + calls["B"] + calls["C"]) * 3 + calls["D1"] * 70 + calls["D2_max"] * 4
    worst_in, worst_out = exp_in * 1.3, sum(toks_cap.values())
    res = dict(
        mode="dry-run (no network, no key)", model=MODEL,
        prices_usd_per_1M=dict(input=0.20, output=1.20,
                               source="OpenAI pricing page and model page, fetched 2026-10-15 via a summarising fetch tool"),
        token_estimate_method=f"chars/{CHARS_PER_TOKEN} + {OVERHEAD_TOK} per call; no tokenizer installed; ESTIMATE",
        n_items=len(items), n_primary=len(prim), n_plain_controls=len(ctrl), n_other_pre_reveal=len(other_p),
        n_closed_book_items=len(cb),
        primary=[dict(id=i["id"], chapter=i["chapter"], reveal_chapter=i["reveal_chapter"],
                      reveal_source=i["reveal_source"], distance=i["reveal_chapter"] - i["chapter"]) for i in prim],
        dropped_pre_reveal_no_repo_reveal=[i["id"] for i in other_p],
        items_without_truth_letter=[i["id"] for i in items if not i["truth_letter"]],
        calls=dict(calls), est_input_tokens=dict(toks_in), output_caps_tokens=dict(toks_cap),
        expected=dict(input_tokens=exp_in, output_tokens=exp_out, usd=exp_in * PRICE_IN + exp_out * PRICE_OUT),
        worst_case=dict(input_tokens=int(worst_in), output_tokens=worst_out,
                        usd=worst_in * PRICE_IN + worst_out * PRICE_OUT,
                        assumption="every call hits its max_completion_tokens cap (hidden reasoning tokens, if billed, "
                                   "cannot exceed it) and input is 1.3x the estimate"),
        window_chars=WINDOW_CHARS,
        prompt_hashes={d["item"]["id"]: {k: hashlib.sha256(d[k].encode()).hexdigest()[:16]
                                         for k in ("A", "B", "C_orig", "C_ren", "D1")} for d in prompts},
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "prompt_hashes"}, indent=2, default=str))


# ------------------------------------------------------------------ live run
class Budget:
    def __init__(self, usd: float):
        self.cap, self.actual, self.calls, self.tok_in, self.tok_out = usd, 0.0, 0, 0, 0

    def can(self, est_in: int, cap_out: int) -> bool:
        return self.actual + est_in * PRICE_IN * 1.3 + cap_out * PRICE_OUT <= self.cap


def call_model(client, prompt: str, cap_out: int) -> dict:
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
               "max_completion_tokens": cap_out, "reasoning_effort": "none"}
    r = client.post("https://api.openai.com/v1/chat/completions", json=payload)
    if r.status_code == 401:
        sys.exit("API auth error (401); stopping. The key was not printed.")
    if r.status_code != 200:
        msg = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-REDACTED", r.text[:300])
        sys.exit(f"API error {r.status_code}: {msg}")
    j = r.json()
    u = j.get("usage", {})
    return dict(text=(j["choices"][0]["message"].get("content") or "").strip(),
                tok_in=u.get("prompt_tokens", 0), tok_out=u.get("completion_tokens", 0))


def parse_letter(text: str, cands) -> str:
    t = text.strip().strip(".")
    return t if (t in {L for L, _n, _i in cands} or t == "UNDETERMINED") else "INVALID"


def live_run(args, items, chapters, pi, tpl):
    import httpx

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set in the environment")
    budget = Budget(args.budget_usd)
    prompts = build_prompts(items, chapters, pi, tpl)
    _prim, _ctrl, _other, cb = sets(items)
    cb_ids = {d["id"] for d in cb}
    vocab = set(pi.mapping)
    results: dict[str, dict] = {d["item"]["id"]: {} for d in prompts}
    log: list[dict] = []
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as client:
        del key

        def go(arm_key: str, cap_arm: str, prompt: str, item_id: str) -> dict:
            if not budget.can(est_tokens(prompt), CAPS[cap_arm]):
                Path(args.out).write_text(json.dumps(dict(status="STOPPED_AT_BUDGET", spent_usd=budget.actual,
                                                          results=results, log=log), indent=2))
                sys.exit(f"stopping: next call could exceed the approved budget (spent ${budget.actual:.4f})")
            r = call_model(client, prompt, CAPS[cap_arm])
            budget.calls += 1
            budget.tok_in += r["tok_in"]
            budget.tok_out += r["tok_out"]
            budget.actual += r["tok_in"] * PRICE_IN + r["tok_out"] * PRICE_OUT
            log.append(dict(item=item_id, arm=arm_key, tok_in=r["tok_in"], tok_out=r["tok_out"],
                            prompt_sha=hashlib.sha256(prompt.encode()).hexdigest()[:16]))
            return r

        for arm_key in ("A", "B"):
            for d in prompts:
                it = d["item"]
                results[it["id"]][arm_key] = parse_letter(go(arm_key, arm_key, d[arm_key], it["id"])["text"], it["cands"])
        for arm_key in ("C_orig", "C_ren"):
            for d in prompts:
                it = d["item"]
                if it["id"] in cb_ids:
                    results[it["id"]][arm_key] = parse_letter(go(arm_key, "C", d[arm_key], it["id"])["text"], it["cands"])
        for d in prompts:
            it = d["item"]
            r = go("D1", "D1", d["D1"], it["id"])
            m = re.match(r"\s*ANSWER:\s*([A-Z]|UNDETERMINED)\b.*?\n\s*SPANS:\s*(.*)", r["text"], re.S)
            ans, spans_raw = (m.group(1), m.group(2).strip()) if m else ("INVALID", "")
            letters = {L for L, _n, _i in it["cands"]}
            if ans not in letters and ans != "UNDETERMINED":
                ans = "INVALID"
            spans = [s.strip().strip('"') for s in spans_raw.split(" || ")] if spans_raw and spans_raw != "NONE" else []
            win = d["_window"].replace("[[", "").replace("]]", "")
            valid = [s for s in spans if s and s in win]
            entailed, why = False, "abstained_or_no_valid_spans"
            if ans in letters and valid and len(valid) == len(spans):
                claimed = next(n for L, n, _i in it["cands"] if L == ans)
                p2 = d2_prompt(tpl, it["surface"], claimed, valid, vocab)
                if p2 is None:
                    why = "claimed_name_not_in_spans"
                else:
                    entailed = go("D2", "D2", p2, it["id"])["text"].strip() == "ENTAILED"
                    why = "entailed" if entailed else "not_entailed"
            results[it["id"]]["D"] = dict(raw_answer=ans, accepted=entailed, gate=why, n_spans=len(spans),
                                          n_valid_spans=len(valid), span_offsets=[win.find(s) for s in valid])
    out = dict(status="COMPLETE", spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in,
               tok_out=budget.tok_out, results=results, log=log)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"complete. calls={budget.calls} tokens_in={budget.tok_in} tokens_out={budget.tok_out} "
          f"spent=${budget.actual:.4f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="SCRATCH copy of the RI database (read only)")
    ap.add_argument("--out", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--budget-usd", type=float, default=0.0)
    args = ap.parse_args()
    if args.run and args.budget_usd <= 0:
        sys.exit("--run needs an explicit --budget-usd (the amount the owner approved)")

    tpl = load_prompts()
    store = Store(args.db)
    items = load_items(store)
    need = {it["chapter"] - k for it in items for k in range(0, 4)}
    chapters = {c.number: c.story_text for c in store.iter_chapters(NOVEL) if c.number in need}
    pi = build_pi(args.db)[0]
    (dry_run if args.dry_run else live_run)(args, items, chapters, pi, tpl)


if __name__ == "__main__":
    main()
