"""Passages-only reading of the cases the first author ruled on, by a local open model (MODEL-GENERATED).

Why this exists: VALIDATION_PROTOCOL.md asked a third author to adjudicate from the passages alone, which has not happened. The
first-author rulings drew on knowledge of the books, so this gives a reading that cannot (a model sees only the sheet) and is
not of the Claude family that wrote annotator 1 and the other passages-only reading. It is a sensitivity result, not a human label.

Inputs : scripts/review/disclosure_validation_app/cases.json (gitignored), data/eval/validation/disclosure_labels/adjudicated.json
Output : data/eval/validation/disclosure_labels/adjudication_model_<tag>.json
Run    : python scripts/review/model_passages_only_reading.py llama3.1:8b llama31_8b
Needs  : a running ollama daemon with the model pulled. Temperature 0, one case per call, no book context.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

LAB = Path("data/eval/validation/disclosure_labels")
CASES = Path("scripts/review/disclosure_validation_app/cases.json")

PROMPT = """You are labelling a character from short passages. Use ONLY the passages. Do not use anything you know about the book.
Character: {name}
Passages (all from before a cut point):
{passages}

Q1. Do the passages establish the character's gender? Answer male, female or undetermined. Say male or female only if a pronoun,
title or explicit statement in the passages refers to this character. A name alone is not enough.
Q3. {q3}
Reply as JSON only: {{"q1": "...", "q3": "..."}}"""
Q3_SERVED = "The system served the value '{v}'. Do the passages support it? Answer supported, unsupported (passages do not settle it) or contradicted."
Q3_NONE = "No value was served. Do the passages settle a gender? Answer settled or not_settled."


def ask(model: str, prompt: str) -> dict:
    body = json.dumps(dict(model=model, prompt=prompt, stream=False, format="json", options=dict(temperature=0, num_ctx=4096))).encode()
    r = urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"}), timeout=300)
    return json.loads(json.loads(r.read())["response"])


def main(model: str, tag: str) -> None:
    adj = json.load(open(LAB / "adjudicated.json"))["adjudicated"]
    cases = {c["case"]: c for c in json.load(open(CASES))["cases"]}
    rul = sorted(k for k, v in adj.items() if v["basis"] != "agreement" and not k.startswith("R"))
    out = {}
    for k in rul:
        c = cases[k]
        q3 = Q3_SERVED.format(v=c["served"]) if c["served"] else Q3_NONE
        passages = "\n".join(f"- {p['text']}" for p in c["passages"])
        a = ask(model, PROMPT.format(name=c["name"], passages=passages, q3=q3))
        q1 = a.get("q1") if a.get("q1") in ("male", "female", "undetermined") else "undetermined"
        q3v = a.get("q3")
        ok = ("supported", "unsupported", "contradicted") if c["served"] else ("settled", "not_settled")
        out[k] = {"q1": q1, "q3": q3v if q3v in ok else None}
        print(k, out[k])
    json.dump({"adjudicator": f"MODEL-GENERATED passages-only reading by {model} via ollama, temperature 0", "labels": out},
              open(LAB / f"adjudication_model_{tag}.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
