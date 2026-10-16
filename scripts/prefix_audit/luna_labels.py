"""Second annotator for the gender labels: gpt-5.6-luna (docs/research/PREFIX_FAITHFULNESS/PREREG_LABELS.md, Addendum 2).

    python -I scripts/prefix_audit/luna_labels.py estimate
    python -I scripts/prefix_audit/luna_labels.py run --budget-usd 0.25 [--limit N]

`estimate` makes no call. `run` stops before any call that could exceed --budget-usd. The key is read in-process from the
environment or the project .env and is never printed. Prompts hold passages from the source novels, so they are rebuilt in
memory each time and never written to disk; only the model's label and a quote of at most 15 words are stored.
LABELS: MODEL-GENERATED (second model annotator).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import label_sheets as LS  # noqa: E402

MODEL = "gpt-5.6-luna"
PRICE_IN, PRICE_OUT = 0.20 / 1e6, 1.20 / 1e6  # USD per token, as in the earlier Luna scripts (OpenAI pricing page, 2026-10-15)
CHARS_PER_TOKEN, OVERHEAD_TOK, CAP_OUT, EXPECTED_OUT = 3.5, 15, 120, 55
N_PASSAGES, BEFORE, AFTER = 24, 150, 350
ENV_FILE = Path("/home/adhyan/Desktop/EchoTales/.env")
OUT = LS.OUT / "luna_labels.jsonl"

PROMPT = """You are annotating a translated web novel. Below are numbered passages, each tagged with its chapter, that mention a character called "{name}"{aliases}.

Decide this character's gender using ONLY the passages below. Accepted evidence: a gendered pronoun that refers to the character, a gendered title or kinship term (Mr, Lady, uncle, granddaughter), or an explicit statement. If the passages do not support an answer, say undetermined. Do not use anything you know about the novel from outside these passages. Use non-person if the name is clearly not a person (an object, a card, a place, a sound, a month).

Reply with JSON only: {{"gender": "male" | "female" | "undetermined" | "non-person", "passage": <number of the passage that shows it, or 0>, "quote": "<at most 15 words copied exactly from that passage, or empty>"}}

Passages:
{passages}
"""
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:16]
#: Addendum 3 of PREREG_LABELS.md: the same prompt with only the instruction relaxed.
PROMPT_PERMISSIVE = PROMPT.replace(
    "Accepted evidence: a gendered pronoun that refers to the character, a gendered title or kinship term (Mr, Lady, uncle, "
    "granddaughter), or an explicit statement. If the passages do not support an answer, say undetermined.",
    "Answer male or female whenever a reasonable reader would infer it from any passage: a single gendered pronoun, title, "
    "kinship term, form of address or description is enough. Answer undetermined only if no passage points either way.",
)
assert PROMPT_PERMISSIVE != PROMPT
TEMPLATE, KINDS = PROMPT, ("truth", "prefix")


def configure(variant: str, kinds: tuple[str, ...]) -> None:
    global TEMPLATE, KINDS, OUT, PROMPT_HASH
    TEMPLATE, KINDS = (PROMPT_PERMISSIVE if variant == "permissive" else PROMPT), kinds
    OUT = LS.OUT / ("luna_labels_permissive.jsonl" if variant == "permissive" else "luna_labels.jsonl")
    PROMPT_HASH = hashlib.sha256(TEMPLATE.encode()).hexdigest()[:16]


def passages_for(c, nid: str, eid: str, upto: float | None) -> list[tuple[float, str]]:
    q = "select chapter, block_index, offset from mention where novel_id=? and target_id=?"
    ms = c.execute(q + (" and chapter<=?" if upto is not None else "") + " order by chapter, offset",
                   (nid, eid) + ((upto,) if upto is not None else ())).fetchall()
    first: dict[float, tuple] = {}
    for ch, block, off in ms:
        first.setdefault(ch, (block, off))
    chapters = sorted(first)
    if len(chapters) > N_PASSAGES:
        chapters = [chapters[round(i * (len(chapters) - 1) / (N_PASSAGES - 1))] for i in range(N_PASSAGES)]
        chapters = list(dict.fromkeys(chapters))
    out = []
    for ch in chapters:
        block, off = first[ch]
        body = LS.block_text(c, nid, ch, block)
        out.append((ch, re.sub(r"\s+", " ", body[max(0, off - BEFORE): off + AFTER]).strip()))
    return out


def build_prompt(c, nid: str, eid: str, upto: float | None) -> tuple[str, list[str]]:
    name = c.execute("select canonical_label from self_entity where id=?", (eid,)).fetchone()
    aliases = [a for (a,) in c.execute("select distinct alias from alias_binding where novel_id=? and target_id=? limit 6", (nid, eid))]
    ps = passages_for(c, nid, eid, upto)
    texts = [t for _ch, t in ps]
    body = "\n".join(f"[{i + 1}] (chapter {ch:g}) {t}" for i, (ch, t) in enumerate(ps)) or "(no passages)"
    alias_s = f' (also written: {", ".join(aliases)})' if aliases else ""
    return TEMPLATE.format(name=name[0] if name else "?", aliases=alias_s, passages=body), texts


def jobs() -> list[dict]:
    truth: dict[str, str] = {}
    pairs: set[tuple[str, str, float]] = set()
    for f in sorted(glob.glob(str(LS.AUD / "audit_repair-off_*.json")) + glob.glob(str(LS.AUD / "audit_dense-off_*.json"))):
        d = json.load(open(f))
        for r in d["rows"]:
            if r["key"] != "gender":
                continue
            truth[r["entity"]] = d["novel"]
            if r["exposed"]:
                pairs.add((d["novel"], r["entity"], float(r["k"])))
    out = [dict(id=f"T|{e}", kind="truth", novel=n, entity=e, k=None) for e, n in sorted(truth.items())]
    out += [dict(id=f"P|{e}|{k:g}", kind="prefix", novel=n, entity=e, k=k) for n, e, k in sorted(pairs)]
    return [j for j in out if j["kind"] in KINDS]


def est_in(prompt: str) -> int:
    return math.ceil(len(prompt) / CHARS_PER_TOKEN) + OVERHEAD_TOK


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')).strip().lower()


def parse(text: str, texts: list[str]) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        j = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        j = {}
    g = j.get("gender") if j.get("gender") in ("male", "female", "undetermined", "non-person") else "invalid"
    p, q = j.get("passage"), str(j.get("quote") or "")
    p = p if isinstance(p, int) else 0
    cited = texts[p - 1] if 1 <= p <= len(texts) else ""
    strict = bool(q) and norm(q) in norm(cited)
    verified = bool(q) and loose_ok(q, cited)
    verified_any = bool(q) and any(loose_ok(q, t) for t in texts)
    primary = g if g not in ("male", "female") or verified else "undetermined"
    return dict(gender=g, passage=p, quote=q[:200], verified=verified, verified_strict=strict, verified_any=verified_any, label=primary)


def loose_ok(quote: str, passage: str, need: float = 0.8) -> bool:
    """At least `need` of the quote's words appear, in order, in the passage (Addendum 2a: the strict substring rule rejected a
    correct, near-verbatim quote that only added a trailing word; copying from the provided text is still required)."""
    qt, pt = re.findall(r"[a-z0-9']+", norm(quote)), re.findall(r"[a-z0-9']+", norm(passage))
    i = matched = 0
    for t in qt:
        try:
            i = pt.index(t, i) + 1
            matched += 1
        except ValueError:
            continue
    return len(qt) >= 2 and matched / len(qt) >= need


def load_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        sys.exit("OPENAI_API_KEY not found in the environment or the project .env")
    return key


def all_prompts(js: list[dict]) -> list[tuple[dict, str, list[str]]]:
    conns: dict = {}
    out = []
    for j in js:
        c = conns.setdefault(j["novel"], LS.conn(j["novel"]))
        p, texts = build_prompt(c, j["novel"], j["entity"], j["k"])
        out.append((j, p, texts))
    return out


def cmd_estimate(_a) -> None:
    ps = all_prompts(jobs())
    tin = sum(est_in(p) for _j, p, _t in ps)
    n = len(ps)
    print(json.dumps(dict(model=MODEL, prompt_hash=PROMPT_HASH, calls=n, truth_calls=sum(j["kind"] == "truth" for j, _p, _t in ps),
                          prefix_calls=sum(j["kind"] == "prefix" for j, _p, _t in ps),
                          expected=dict(input_tokens=tin, output_tokens=n * EXPECTED_OUT, usd=round(tin * PRICE_IN + n * EXPECTED_OUT * PRICE_OUT, 4)),
                          worst_case=dict(input_tokens=tin, output_tokens=n * CAP_OUT, usd=round(tin * PRICE_IN + n * CAP_OUT * PRICE_OUT, 4)),
                          prices_per_million=dict(input=0.20, output=1.20)), indent=1))


def cmd_run(a) -> None:
    import httpx

    done = {json.loads(line)["id"] for line in OUT.read_text().splitlines()} if OUT.exists() else set()
    todo = [x for x in all_prompts(jobs()) if x[0]["id"] not in done]
    if a.limit:
        todo = todo[: a.limit]
    spent, calls, tin_total, tout_total = 0.0, 0, 0, 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"Authorization": f"Bearer {load_key()}"}, timeout=60.0) as client, open(OUT, "a") as fh:
        for j, prompt, texts in todo:
            if spent + est_in(prompt) * PRICE_IN * 1.3 + CAP_OUT * PRICE_OUT > a.budget_usd:
                print("budget would be exceeded; stopping before call", calls + 1)
                break
            r = client.post("https://api.openai.com/v1/chat/completions", json={
                "model": MODEL, "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": CAP_OUT, "reasoning_effort": "none"})
            if r.status_code != 200:
                msg = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-REDACTED", r.text[:300])
                sys.exit(f"API error {r.status_code}: {msg}")
            body = r.json()
            u = body.get("usage", {})
            tin, tout = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
            spent += tin * PRICE_IN + tout * PRICE_OUT
            calls, tin_total, tout_total = calls + 1, tin_total + tin, tout_total + tout
            res = parse((body["choices"][0]["message"].get("content") or "").strip(), texts)
            fh.write(json.dumps(dict(id=j["id"], kind=j["kind"], novel=j["novel"], entity=j["entity"], k=j["k"], prompt_hash=PROMPT_HASH,
                                     n_passages=len(texts), tok_in=tin, tok_out=tout, **res)) + "\n")
            fh.flush()
    print(json.dumps(dict(calls=calls, tok_in=tin_total, tok_out=tout_total, spent_usd=round(spent, 5), budget_usd=a.budget_usd, remaining_jobs=len(todo) - calls)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=("strict", "permissive"), default="strict")
    ap.add_argument("--kinds", default="truth,prefix", help="comma-separated subset of truth,prefix")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate").set_defaults(fn=cmd_estimate)
    r = sub.add_parser("run")
    r.add_argument("--budget-usd", type=float, required=True)
    r.add_argument("--limit", type=int, default=0)
    r.set_defaults(fn=cmd_run)
    a = ap.parse_args()
    configure(a.variant, tuple(a.kinds.split(",")))
    a.fn(a)


if __name__ == "__main__":
    main()
