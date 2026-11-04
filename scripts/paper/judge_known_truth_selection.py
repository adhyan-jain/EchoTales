"""Known-truth test of the judge in the selection-leak setting (review round 4, Priority 2: "independent human-validated
or known-truth test for the selection-leak judge, preferably using synthetic or public-domain material").

Why a second set: the round-3 test (judge_known_truth.py) used one-sentence cards. The selection experiment is the case
where the judge is least validated, because alias-merged retrieval feeds the generator passages about BOTH the alias and
the identity (37.8% of served passages were identity passages, selection_analysis.json), so its cards routinely name both
people. A judge that answers "same person" whenever two names co-occur would inflate the 19.4% merged-index rate. This set
reproduces that shape: card-length text in the generators' "**Character Card for X**" format, on cipher-like invented
names like the renamed books, where both names appear. Truth is fixed by construction.

Strata (30 each): co-mention negatives (both people interact, clearly distinct), two-portrait negatives (the card
describes both people separately, as a merged-retrieval card often does), explicit positives and implied positives, each
embedded in the same card scaffold. Prompt, model and decoding are the paper's judge rule, unchanged.

Run: python scripts/paper/judge_known_truth_selection.py [--judges qwen3:8b,gemma2:9b]   (needs a local ollama)
Output: data/eval/judge_known_truth_selection.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_known_truth as KT  # noqa: E402  same prompt, decoding, schema, Wilson interval

OUT = KT.ROOT / "data" / "eval" / "judge_known_truth_selection.json"
SEED = 20261104

CONS, VOW = "bcdfghklmnprstvwxz", "aeiouy"

# Scaffold sentences about the alias only; two are sampled into every card so length and style match real cards.
ALIAS_ONLY = [
    "{A} keeps to the edges of every gathering and watches more than speaks.",
    "{A} is known in the town for a sharp tongue and a habit of settling debts in cash.",
    "Neighbours describe {A} as restless, often seen walking the river road at night.",
    "{A} shows a quick temper when questioned about the past.",
    "{A} is careful with money and suspicious of strangers.",
    "{A} spends long hours in the garden and guards it jealously.",
]
COMENTION_NEG = [
    "{A} works for {B}, who owns the mill, and the two often quarrel over wages. {B} once dismissed {A} and then hired them back.",
    "{A} envies {B}, a wealthy neighbour, and spies on {B}'s house from across the lane. {B} has no idea {A} is watching.",
    "{A} and {B} meet at the inn, where {B} warns {A} to stay away from the harbour. {A} ignores the warning.",
    "{B} is {A}'s guardian, and {A} resents the strict rules {B} sets. They argue whenever {B} visits.",
    "{A} travels with {B} to the capital; {B} pays for the journey, and {A} repays the favour with a lie.",
    "{A} is accused of a theft that {B} reported, and {A} swears revenge on {B}.",
]
TWO_PORTRAIT_NEG = [
    "{B}, mentioned in the same passages, is an elderly merchant with a failing shop and a son abroad.",
    "The passages also describe {B}, a magistrate who lives on the hill and rarely leaves the court.",
    "{B} appears as well: a sailor recently returned from the south, loud and generous.",
    "Another figure, {B}, is a widow who runs the bakery and knows everyone's business.",
    "{B}, a schoolmaster, is described in other passages as patient and short-sighted.",
    "Separately, {B} is a soldier stationed at the fort, admired for his discipline.",
]
POS_EXPLICIT = [
    "It is revealed that {A} is in fact {B}, living under an assumed name.",
    "{A} and {B} are the same person; {B} took the name {A} to hide from the law.",
    "The passages make clear that {A} is really {B} in disguise.",
    "{A} turns out to be {B}, who vanished from the town years earlier.",
    "Behind the name {A} is {B}; the two names belong to one man.",
]
POS_IMPLIED = [
    "{A} answers to the name {B} when startled, a name {A} has not used since leaving the capital.",
    "{A} carries the signet ring of {B} and knows details of {B}'s childhood that no stranger could know.",
    "Before arriving in town, {A} went by {B}; the old name was dropped after the trial.",
    "{A} signs one letter with {B}'s initials before hastily crossing them out.",
    "The name {B} disappears from the records in the same month that {A} first appears.",
]


def cipher_name(rng: random.Random, parts: int) -> str:
    # Cipher-like tokens (e.g. "Dclox", "Isccl Xopbtk") so the judge sees what it saw on the renamed books.
    def word() -> str:
        n = rng.randint(4, 7)
        return "".join(rng.choice(CONS if i % 2 == 0 or rng.random() < 0.3 else VOW) for i in range(n)).capitalize()
    return " ".join(word() for _ in range(parts))


def build(per_stratum: int = 30) -> list[dict]:
    rng = random.Random(SEED)
    spec = [("negative", "comention", COMENTION_NEG), ("negative", "two_portrait", TWO_PORTRAIT_NEG),
            ("positive", "explicit", POS_EXPLICIT), ("positive", "implied", POS_IMPLIED)]
    cards = []
    for truth, sub, templates in spec:
        for i in range(per_stratum):
            a = cipher_name(rng, 1)
            b = cipher_name(rng, 2)
            while b.split()[0] == a:
                b = cipher_name(rng, 2)
            core = templates[i % len(templates)].format(A=a, B=b)
            pre = [s.format(A=a) for s in rng.sample(ALIAS_ONLY, 2)]
            # The positive/negative sentence sits in the middle, as in a generated card, not first.
            body = f"**Character Card for {a}**\n\n{pre[0]} {core} {pre[1]}"
            cards.append(dict(id=f"{truth[:3]}-{sub}-{i:02d}", card=body, alias=a, identity=b,
                              truth=(truth == "positive"), subtype=sub, words=len(body.split()),
                              identity_mentions=body.count(b)))
    rng.shuffle(cards)
    return cards


def metrics(cards: list[dict], pred: dict) -> dict:
    def rate(sel, want):
        k = sum(1 for c in sel if pred.get(c["id"]) is want)
        return dict(k=k, n=len(sel), pct=round(100 * k / len(sel), 1) if sel else None, wilson=KT.wilson(k, len(sel)))
    pos, neg = [c for c in cards if c["truth"]], [c for c in cards if not c["truth"]]
    out = dict(sensitivity=rate(pos, True), specificity=rate(neg, False),
               sens_explicit=rate([c for c in pos if c["subtype"] == "explicit"], True),
               sens_implied=rate([c for c in pos if c["subtype"] == "implied"], True),
               spec_comention=rate([c for c in neg if c["subtype"] == "comention"], False),
               spec_two_portrait=rate([c for c in neg if c["subtype"] == "two_portrait"], False),
               unparsed=sum(1 for c in cards if pred.get(c["id"]) is None))
    right = out["sensitivity"]["k"] + out["specificity"]["k"]
    out["accuracy"] = dict(k=right, n=len(cards), pct=round(100 * right / len(cards), 1), wilson=KT.wilson(right, len(cards)))
    return out


def main() -> None:
    import httpx

    ap = argparse.ArgumentParser()
    ap.add_argument("--judges", default=KT.JUDGE)
    ap.add_argument("--per-stratum", type=int, default=30)
    a = ap.parse_args()
    cards = build(a.per_stratum)
    res = dict(provenance="SYNTHETIC selection-style cards, cipher-like invented names; truth fixed by construction; "
                          "no annotator, no copyrighted text",
               prompt=KT.JUDGE_PROMPT, decoding=KT.OPTS, seed=SEED, cards=cards, judges={}, metrics={})
    with httpx.Client(timeout=300.0) as cl:
        for m in a.judges.split(","):
            pred = {c["id"]: KT.ask(cl, m, c) for c in cards}
            res["judges"][m] = pred
            res["metrics"][m] = metrics(cards, pred)
            mt = res["metrics"][m]
            print(m, "sens", mt["sensitivity"]["pct"], "(explicit", mt["sens_explicit"]["pct"], "implied",
                  mt["sens_implied"]["pct"], ") spec", mt["specificity"]["pct"], "(comention", mt["spec_comention"]["pct"],
                  "two-portrait", mt["spec_two_portrait"]["pct"], ") acc", mt["accuracy"]["pct"], "unparsed", mt["unparsed"],
                  flush=True)
    names = list(res["judges"])
    if len(names) == 2:
        x, y = (res["judges"][n] for n in names)
        both = [c["id"] for c in cards if x[c["id"]] is not None and y[c["id"]] is not None]
        res["agreement_between_judges"] = dict(k=sum(x[i] == y[i] for i in both), n=len(both))
    OUT.write_text(json.dumps(res, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
