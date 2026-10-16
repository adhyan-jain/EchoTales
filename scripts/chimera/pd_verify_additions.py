"""Verify a PD reveal-benchmark additions file (e.g. PD_events_v2_additions.json) against local Gutenberg texts.

pd_reveal_benchmark.py `verify` can only read the frozen v1 event list (it hash-checks PD_events_v1.json against
MANIFEST_PD.json and has no path argument), so this separate checker reuses that module's functions by import
(load_text, locate, control_mentions, surfaces_for, build_items) and applies them to another file. It changes nothing
and writes no novel text; it prints counts only.

Checks per event (a failing check is reported as FAIL and the script exits non-zero):
  - schema keys equal v1's; id unique and not in v1; Gutenberg id not used by v1 and unique within the file
  - 7 to 9 cast names, identity in the cast, no duplicate cast name
  - reveal sentence found by whitespace-insensitive exact search, exactly once in the book body
  - cut anchor found before the reveal (builder's `locate` assertions); cutoff strictly before the reveal sentence
  - at least 3 pre-cutoff alias occurrences (whole sentence ends before the cutoff) and at least 3 post-reveal occurrence
    counts reported (builder takes up to 2; 0 is allowed but reported)
  - control: the best non-identity cast surface has at least 3 pre-cutoff mentions
  - every non-identity cast name has at least 1 pre-cutoff mention by some surface (the decoys are really in the prefix;
    the identity may be absent, as with Oliver Twist's Leeford, which is a feature of the event)
  - ambiguity flag: the chosen control surface is also a token of another cast name (label-noise risk; WARN only)
  - builder dry run: PD.build_items with this file's events yields pre/post/ctrl items

    python scripts/chimera/pd_verify_additions.py --events docs/research/preregistrations/PD_events_v2_additions.json \
        --texts <dir with pgNNN.txt>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_reveal_benchmark as PD  # noqa: E402

V1_KEYS = {"id", "book", "gutenberg", "alias", "identity", "cast", "reveal_sentence", "cut", "caveat"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--texts", required=True)
    args = ap.parse_args()
    texts = Path(args.texts)
    doc = json.loads(Path(args.events).read_text(encoding="utf-8"))
    v1 = json.loads(PD.EVENTS.read_text(encoding="utf-8"))["events"]
    v1_ids = {e["id"] for e in v1}
    v1_books = {e["gutenberg"] for e in v1}
    events = doc["events"]
    fails, warns = 0, 0
    seen_ids, seen_books = set(), set()
    print(f"provenance: {doc.get('provenance')!r}; {len(events)} events")

    def fail(ev, msg):
        nonlocal fails
        fails += 1
        print(f"  FAIL {ev['id']}: {msg}")

    def warn(ev, msg):
        nonlocal warns
        warns += 1
        print(f"  WARN {ev['id']}: {msg}")

    cache = {}
    for ev in events:
        print(f"{ev['id']}  {ev['book']} (pg{ev['gutenberg']})")
        if set(ev) != V1_KEYS:
            fail(ev, f"schema keys differ from v1: {sorted(set(ev) ^ V1_KEYS)}")
        if ev["id"] in v1_ids or ev["id"] in seen_ids:
            fail(ev, "duplicate id")
        if ev["gutenberg"] in v1_books or ev["gutenberg"] in seen_books:
            fail(ev, "Gutenberg id already used (v1 or earlier in this file): books must differ")
        seen_ids.add(ev["id"])
        seen_books.add(ev["gutenberg"])
        cast = ev["cast"]
        if not 7 <= len(cast) <= 9:
            fail(ev, f"cast size {len(cast)} not in 7..9")
        if ev["identity"] not in cast:
            fail(ev, "identity not in cast")
        if len(set(cast)) != len(cast):
            fail(ev, "duplicate cast name")
        text = cache.setdefault(ev["gutenberg"], PD.load_text(texts, ev["gutenberg"]))
        n_rev = len(list(PD.ws_regex(ev["reveal_sentence"]).finditer(text)))
        if n_rev != 1:
            fail(ev, f"reveal sentence occurs {n_rev} times (need exactly 1)")
            continue
        try:
            loc = PD.locate(ev, text)
        except AssertionError as e:
            fail(ev, f"locate assertion: {e}")
            continue
        cut, npre, npost = loc["cut"], len(loc["pre"]), len(loc["post"])
        print(f"  reveal@{loc['reveal_start']} cut@{cut} (cut-to-reveal {loc['reveal_start'] - cut} chars) "
              f"pre-alias {npre} post-alias {npost} | identity token in prefix: {loc['identity_in_prefix']} | "
              f"prefix sentences with alias AND identity token: {loc['prefix_sentences_with_alias_and_identity_token']}")
        if npre < 3:
            fail(ev, f"only {npre} pre-cutoff alias occurrences (need >= 3)")
        if npost == 0:
            warn(ev, "no post-reveal alias occurrence (post items will be empty)")
        try:
            cname, cms = PD.control_mentions(ev, text, cut)
        except TypeError:
            fail(ev, "no non-identity cast surface occurs before the cutoff")
            cname, cms = None, []
        # per-name pre-cutoff counts and ambiguity
        counts = {}
        for nm in cast:
            best = (0, None)
            for sf in PD.surfaces_for(nm):
                ms = [m for m in re.finditer(r"\b" + re.escape(sf) + r"\b", text[:cut])
                      if PD.sentence_end(text, m.end()) <= cut]
                if len(ms) > best[0]:
                    best = (len(ms), sf)
            counts[nm] = best
        nonid = {k: v for k, v in counts.items() if k != ev["identity"]}
        print("  pre-cutoff mentions (best surface): " + "; ".join(f"{k}={v[0]}[{v[1]}]" for k, v in counts.items()))
        missing = [k for k, v in counts.items() if v[0] == 0 and k != ev["identity"]]
        if missing:
            fail(ev, f"cast names with zero pre-cutoff mentions: {missing}")
        if cname:
            best_n = max(v[0] for v in nonid.values())
            if best_n < 3 or len(cms) < 3:
                fail(ev, f"control name {cname!r} has {best_n} pre-cutoff mentions / {len(cms)} usable (need >= 3)")
            sf = counts[cname][1]
            others = [n for n in cast if n != cname and sf in PD.surfaces_for(n)[1:] + [n]]
            if others:
                warn(ev, f"control surface {sf!r} (name {cname!r}) is also a surface of {others}: label-noise risk")
            print(f"  control: {cname!r} via {sf!r}, {len(cms)} items")
        # reveal sentence must not occur in the prefix and must follow the cutoff
        if loc["reveal_start"] <= cut:
            fail(ev, "reveal before cutoff")

    # builder dry run on these events
    PD.load_events = lambda: events
    items, _ = PD.build_items(texts)
    from collections import Counter
    c = Counter((i["event"], i["kind"]) for i in items)
    print("builder dry run item counts:")
    for ev in events:
        print(f"  {ev['id']}: pre {c[(ev['id'], 'pre')]} post {c[(ev['id'], 'post')]} ctrl {c[(ev['id'], 'ctrl')]}")
    print(f"TOTAL items {len(items)}; FAIL {fails}; WARN {warns}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
