"""Build the human reveal-validation set (journal Revision 1, major issue 5).

Why this exists: the reviewer's strongest objection to the reveal oracle is that every event was model-proposed and
model-audited and no person ever checked one. Exact matching of the reveal sentence fixes *where* the book states the
identity, but not (a) that the sentence really is an explicit identification, (b) that it is the first disclosure
rather than a reminder, or (c) that a reader could not already name the identity from earlier clues. Those three are
human judgments, so this script draws a stratified, seeded subset of public-domain events and writes the material
the annotation app shows: the same 1,200-character windows the models saw (PD.window_for), and the reveal sentence
in context. No model label (audit verdict, model answers) is written, so the annotators are blind to them.

Selection (seed 20261025): 18 exploratory events stratified by dataset (v2 9, v3 6, v6 3 of 19/12/7) and 18
confirmatory primary events (test split, audit EXPLICIT: the single high-fame and all six mid-fame events plus 11 of
25 low-fame). Each event goes to two of three annotators in a balanced rotation, 24 events each.

Only Project Gutenberg text is written. The copyrighted web-novel cuts of the pipeline audit are deliberately absent.
Run: python scripts/review/build_reveal_validation_set.py
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chimera"))
import pd_reveal_benchmark as PD  # noqa: E402

P = Path("docs/research/preregistrations")
EXPLORATORY = {
    "v2": [P / "PD_events_v1.json", P / "PD_events_v2_additions.json"],
    "v3": [P / "PD_events_v3_additions.json"],
    "v6": [P / "PD_events_v6_additions.json"],
}
CONFIRM = P / "PD_confirm_events_v1.json"
TEXT_DIRS = [Path("data/raw/pd_gutenberg"), Path("data/raw/pd_gutenberg/texts"), Path("data/raw/pd_gutenberg_v6"),
             Path("data/raw/pd_gutenberg_v7"), Path("data/raw/pd_confirm/texts")]
OUT = Path("scripts/review/reveal_validation_app/events.json")
SEED = 20261025
PER_DATASET = {"v2": 9, "v3": 6, "v6": 3}
CONFIRM_LOW = 11
ANNOTATORS = ["Adhyan", "Atharva", "Aryan"]
REVEAL_CONTEXT = 750  # characters each side of the reveal sentence


def find_text_dir(gid: int) -> Path:
    for d in TEXT_DIRS:
        if (d / f"pg{gid}.txt").exists():
            return d
    sys.exit(f"REFUSING: pg{gid}.txt not found under data/raw; download the Gutenberg text first")


def events_of(files):
    out = []
    for f in files:
        out += json.loads(f.read_text())["events"]
    return out


def pick():
    rng = random.Random(SEED)
    chosen = []
    for ds, files in EXPLORATORY.items():
        evs = sorted(events_of(files), key=lambda e: e["id"])
        for ev in rng.sample(evs, PER_DATASET[ds]):
            chosen.append((f"exploratory-{ds}", ev))
    prim = sorted((e for e in json.loads(CONFIRM.read_text())["events"]
                   if e["split"] == "test" and e["audit"] == "EXPLICIT"), key=lambda e: e["id"])
    keep = [e for e in prim if e["band"] in ("high", "mid")]
    keep += rng.sample([e for e in prim if e["band"] == "low"], CONFIRM_LOW)
    chosen += [(f"confirmatory-{e['band']}", e) for e in keep]
    return chosen


def marked(text: str, start: int, end: int, a: int, b: int) -> str:
    w = text[start:end]
    return w[: a - start] + "[[" + w[a - start: b - start] + "]]" + w[b - start:]


def pre_windows(ev, text, loc, confirmatory: bool):
    """The pre-reveal items the models answered: confirmatory runs sampled 4 evenly spaced mentions, exploratory runs 8;
    for the exploratory events every second of the 8 is shown (it keeps the latest one, nearest the cutoff, where
    inference clues are densest) so each event costs the annotator the same reading."""
    pre = loc["pre"]
    if confirmatory:
        idx = [len(pre) // 2] if len(pre) == 1 else PD.spaced(len(pre), 4)
    else:
        idx = PD.spaced(len(pre), 8)[1::2]
    out = []
    for i in idx:
        s, e, surf = pre[i]
        out.append(dict(window=PD.window_for(text, dict(start=s, end=e)),
                        chars_before_cutoff=loc["cut"] - PD.sentence_end(text, e)))
    return out


def main():
    rows = []
    for stratum, ev in pick():
        text = PD.load_text(find_text_dir(ev["gutenberg"]), ev["gutenberg"])
        loc = PD.locate(ev, text)
        rs, re_ = loc["reveal_start"], loc["reveal_end"]
        rows.append(dict(
            event_id=ev["id"], stratum=stratum, book=ev["book"], gutenberg=ev["gutenberg"],
            alias=ev["alias"], identity=ev["identity"],
            reveal=marked(text, max(0, rs - REVEAL_CONTEXT), min(len(text), re_ + REVEAL_CONTEXT), rs, re_),
            pre=pre_windows(ev, text, loc, stratum.startswith("confirmatory")),
        ))
    rng = random.Random(SEED + 1)
    rng.shuffle(rows)  # mixes strata so no annotator sees all exploratory events first
    pairs = [(0, 1), (1, 2), (0, 2)]
    for k, r in enumerate(rows):
        r["key"] = f"E{k + 1:02d}"
        r["annotators"] = [ANNOTATORS[i] for i in pairs[k % 3]]
    load = {a: sum(a in r["annotators"] for r in rows) for a in ANNOTATORS}
    assert len(set(load.values())) == 1, load
    payload = dict(version="reveal-validation-v1", seed=SEED, annotators=ANNOTATORS, events=rows)
    blob = json.dumps(payload, ensure_ascii=False, indent=1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(blob)
    print(f"wrote {OUT}: {len(rows)} events, per annotator {load}, sha256 {hashlib.sha256(blob.encode()).hexdigest()[:12]}")


if __name__ == "__main__":
    main()
