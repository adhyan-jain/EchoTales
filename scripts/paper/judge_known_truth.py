"""Known-truth test of the card judge (review round 3, "Model-judge reliability").

The paper's judge rule (and the selection-leak result built on it) asks a model whether a character card "states or
clearly implies" that an alias and an identity are the same person. It was validated against a deterministic rule only
on the 19 events where that rule applies. This script tests the judge where the answer is fixed by construction: short
synthetic cards with invented names, written from templates, so the truth label is known without any annotator and the
set can be shared (no copyrighted text). It uses the paper's judge prompt, model and decoding settings unchanged.

Strata: positive-explicit, positive-implied, hard negative (both names present but different people, including a
resemblance decoy), easy negative (only one name present). Output: data/eval/judge_known_truth.json.

Run: python scripts/paper/judge_known_truth.py [--judges qwen3:8b,gemma2:9b]   (needs a local ollama)
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "eval" / "judge_known_truth.json"
HOST = "http://localhost:11434"
SEED = 20261031
# Same prompt, model and decoding as the paper's judge rule (scripts/chimera/pd_rf_e2e.py JUDGE_PROMPT, rf_selection.py).
JUDGE, JUDGE_PROMPT = "qwen3:8b", ("A reading assistant wrote this character card.\nCard: {CARD}\n\nDoes the card state or clearly imply that the character "
                                    "called \"{ALIAS}\" is the same person as \"{IDENTITY}\"? Reply as JSON: {{\"identifies\": true}} or {{\"identifies\": false}}.")
OPTS = {"temperature": 0, "seed": 20261016, "num_predict": 20}
SCHEMA = {"type": "object", "properties": {"identifies": {"type": "boolean"}}, "required": ["identifies"]}

A_FIRST = ["Veldra", "Orsin", "Maret", "Tobren", "Ilsa", "Kaldor", "Nesta", "Brannic", "Yorra", "Peltin", "Dessa", "Harlo"]
A_LAST = ["Marn", "Quill", "Thorne", "Vask", "Ember", "Lorne", "Skarra", "Wick", "Dray", "Fenn", "Corvane", "Ashby"]
FILLER = ["The harbour district knows them well.", "They keep a ledger of small debts.", "Few have seen them without a cloak.",
          "They speak slowly and answer questions with questions.", "A scar runs across one hand.",
          "They are said to be good with locks.", "They rarely leave the lower town.", "They carry a brass compass everywhere."]

# {A} is the alias named in the question, {B} the identity, {C} a third, unrelated name.
POS_EXPLICIT = [
    "{A}, a figure known around the docks, is in fact {B} living under a false name.",
    "Though everyone calls them {A}, the truth is that {A} and {B} are the same person.",
    "{A} was revealed to be {B}, who had hidden their past for years.",
    "{B} lives as {A}, a name taken to escape the guild's notice.",
    "Behind the name {A} stands {B}; the two names belong to one person.",
]
POS_IMPLIED = [
    "Once called {B}, {A} left the capital after the fire and has not used the old name since.",
    "{A} used to go by the name {B} before the trial, and answers to it only when startled.",
    "When {A} arrived in town the name {B} was quietly dropped, and nobody has used it since.",
    "{A} signs letters with the old initials of {B} and wears the same ring {B} once wore.",
    "The name {B} was shed on the night {A} first appeared in the lower town.",
]
NEG_HARD = [
    "{A} works as a clerk in the harbour office, and {B}, the magistrate, often visits that office.",
    "{A} fears {B}, a rival who has hunted them since the fire.",
    "{A} is the younger sibling of {B}; the two rarely speak.",
    "{B} hired {A} as a guide, because {A} knows the mountain roads.",
    "{A} and {B} are partners in a trading house and argue about its accounts.",
    "{A} bears a striking resemblance to {B}, though the two have never met.",
]
NEG_EASY = [
    "{A} is a cheerful baker who opens the shop before dawn.",
    "{A} teaches letters to the children of the lower town.",
    "{A} is a ferry keeper who has never left the river.",
    "{A} repairs clocks and trades in old maps; {C} is a customer who owes them money.",
]
NEG_EASY_B = ["{B} is a cheerful baker who opens the shop before dawn.", "{B} repairs clocks and trades in old maps."]


def name(rng: random.Random, used: set[str]) -> str:
    while True:
        n = f"{rng.choice(A_FIRST)} {rng.choice(A_LAST)}"
        if n not in used:
            used.add(n)
            return n


def build(per_stratum: int = 30) -> list[dict]:
    rng = random.Random(SEED)
    used: set[str] = set()
    cards = []
    spec = [("positive", "explicit", POS_EXPLICIT), ("positive", "implied", POS_IMPLIED),
            ("negative", "hard", NEG_HARD), ("negative", "easy", NEG_EASY)]
    for truth, sub, templates in spec:
        for i in range(per_stratum):
            used = set()  # distinct within a card only: 3 names x 120 cards exceeds the 144 first/last combinations and name() would spin forever
            a, b, c = name(rng, used), name(rng, used), name(rng, used)
            t = templates[i % len(templates)]
            if sub == "easy" and i % 5 == 4:  # the identity named alone, alias absent from the card text
                t = NEG_EASY_B[i % len(NEG_EASY_B)]
            body = " ".join([t.format(A=a, B=b, C=c)] + rng.sample(FILLER, 2))
            cards.append(dict(id=f"{truth[:3]}-{sub}-{i:02d}", card=body, alias=a, identity=b,
                              truth=(truth == "positive"), subtype=sub, words=len(body.split())))
    rng.shuffle(cards)
    return cards


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def ask(cl, model: str, c: dict) -> bool | None:
    body = dict(model=model, stream=False, options=OPTS, format=SCHEMA, think=False,
                messages=[dict(role="user", content=JUDGE_PROMPT.format(CARD=c["card"], ALIAS=c["alias"], IDENTITY=c["identity"]))])
    r = cl.post(f"{HOST}/api/chat", json=body)
    r.raise_for_status()
    try:
        return bool(json.loads(r.json()["message"]["content"])["identifies"])
    except (ValueError, KeyError):
        return None


def metrics(cards: list[dict], pred: dict) -> dict:
    def rate(sel, want):
        k = sum(1 for c in sel if pred.get(c["id"]) is want)
        return dict(k=k, n=len(sel), pct=round(100 * k / len(sel), 1) if sel else None, wilson=wilson(k, len(sel)))
    pos, neg = [c for c in cards if c["truth"]], [c for c in cards if not c["truth"]]
    out = dict(sensitivity=rate(pos, True), specificity=rate(neg, False),
               sens_explicit=rate([c for c in pos if c["subtype"] == "explicit"], True),
               sens_implied=rate([c for c in pos if c["subtype"] == "implied"], True),
               spec_hard=rate([c for c in neg if c["subtype"] == "hard"], False),
               spec_easy=rate([c for c in neg if c["subtype"] == "easy"], False),
               unparsed=sum(1 for c in cards if pred.get(c["id"]) is None))
    right = out["sensitivity"]["k"] + out["specificity"]["k"]
    out["accuracy"] = dict(k=right, n=len(cards), pct=round(100 * right / len(cards), 1), wilson=wilson(right, len(cards)))
    return out


def main() -> None:
    import httpx

    ap = argparse.ArgumentParser()
    ap.add_argument("--judges", default=JUDGE)
    ap.add_argument("--per-stratum", type=int, default=30)
    a = ap.parse_args()
    cards = build(a.per_stratum)
    res = dict(provenance="SYNTHETIC templates, invented names; truth fixed by construction; no annotator, no copyrighted text",
               prompt=JUDGE_PROMPT, decoding=OPTS, seed=SEED, cards=cards, judges={}, metrics={})
    with httpx.Client(timeout=300.0) as cl:
        for m in a.judges.split(","):
            pred = {c["id"]: ask(cl, m, c) for c in cards}
            res["judges"][m] = pred
            res["metrics"][m] = metrics(cards, pred)
            mt = res["metrics"][m]
            print(m, "sens", mt["sensitivity"]["pct"], "(explicit", mt["sens_explicit"]["pct"], "implied", mt["sens_implied"]["pct"],
                  ") spec", mt["specificity"]["pct"], "(hard", mt["spec_hard"]["pct"], "easy", mt["spec_easy"]["pct"], ")",
                  "acc", mt["accuracy"]["pct"], "unparsed", mt["unparsed"], flush=True)
    names = list(res["judges"])
    if len(names) == 2:
        x, y = (res["judges"][n] for n in names)
        both = [c["id"] for c in cards if x[c["id"]] is not None and y[c["id"]] is not None]
        res["agreement_between_judges"] = dict(k=sum(x[i] == y[i] for i in both), n=len(both))
    OUT.write_text(json.dumps(res, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
