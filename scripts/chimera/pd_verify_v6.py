"""Verify the fourth, fully fresh public-domain reveal event set (PD_events_v6_additions.json) against local Gutenberg texts.

Same checks as pd_verify_v3.py (which verified the third set), extended in two ways: the "used" sets now cover v1, v2 AND
v3 (ids, Gutenberg numbers, book titles), and the author named in the book string's last parenthesis is compared with
the authors of every earlier set (an author with a book in v1, v2 or v3 is a FAIL; the owner asked for authors with no
book in the earlier sets). The event-count bounds are arguments (default 14..18, the brief for this set) so a shorter
file can still be checked event by event with --min-events 1. It reuses pd_reveal_benchmark's text loader, `locate`,
`surfaces_for`, `sentence_end` by import and re-implements the v2 control selection locally. It changes nothing, reads
no API key, uses no network or GPU, and writes no novel text: the only novel text it prints is the sentences it flags
for a human to read (to stdout, never to the repository).

Checks per event (a failing check is FAIL and the script exits non-zero):
  - schema keys equal v1's; event id and Gutenberg id not used in v1, v2 or v3 and unique within the file; book title
    not matching a used title; author not among the earlier authors
  - 7 to 9 cast names, identity in the cast, no duplicate cast name
  - reveal sentence found by whitespace-insensitive exact search, exactly once in the book body
  - cutoff anchor found before the reveal and strictly before it
  - at least 3 pre-cutoff alias occurrences (whole sentence ends before the cutoff)
  - controls: the v2 control selector yields 8 items (two cast names with >= 4 usable pre-cutoff mentions each), and
    the non-identity cast names have >= 8 pre-cutoff mentions in total
  - every non-identity cast name has >= 1 pre-cutoff mention by some surface
  - identity vs alias: no prefix sentence contains an alias AND the full identity name (FAIL unless --cleared names the
    event after a human read it); sentences containing an alias and only a token of the identity are counted and, with
    --show-token-sentences, printed for reading
  - WARN only: no post-reveal alias occurrence; control surface also a surface of another cast name; anchor longer than
    140 characters; translation flag consistency is NOT checked (it is in the notes file)

    python scripts/chimera/pd_verify_v6.py --events docs/research/preregistrations/PD_events_v6_additions.json \
        --texts data/raw/pd_gutenberg_v6 [--min-events 1] [--cleared ID,ID] [--show-token-sentences]
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
P = Path("docs/research/preregistrations")
V2_FILE = P / "PD_events_v2_additions.json"
V3_FILE = P / "PD_events_v3_additions.json"
# surnames of the authors with a book in v1, v2 or v3 (lower case, accents folded); a new event by one of them FAILS.
USED_AUTHORS = {"leroux", "orczy", "dickens", "doyle", "bronte", "dumas", "hugo", "stevenson", "scott", "verne", "christie",
                "webster", "cervantes", "collins", "haggard", "goldsmith", "braddon", "walpole", "fitzgerald", "balzac",
                "lewis", "wells", "grey", "wood", "hawthorne"}
# A different Gutenberg number can be the same book (e.g. the catalog holds several copies of one title), so the book
# title is also compared with the 19 used titles below (first two significant words).
ALT_EDITIONS: set[int] = set()
CTRL_NAMES, CTRL_PER_NAME = 2, 4
# v6 change: a full stop after a title or initial ("Mrs.", "Dr.", "M.") does not end a sentence. v3's splitter cut there, which
# hid alias+identity pairs in the same sentence (e.g. "... for Mrs. Beaumont ..." was split after "Mrs."; found while checking GP).
_ABBR = "|".join(rf"(?<=\b{a})\." for a in ("Mr", "Mrs", "Messrs", "Dr", "M", "MM", "Mme", "Mlle", "St", "Col", "Capt", "Gen", "Lt", "Hon", "Rev"))
SENT = re.compile(rf"(?:[^.!?]|{_ABBR})*[.!?]+")


def v2_controls(ev: dict, text: str, cut: int):
    """Copy of pd_v2.controls: two non-identity cast names with the most prefix mentions, four evenly spaced each."""
    cands = []
    for nm in ev["cast"]:
        if nm == ev["identity"]:
            continue
        best = None
        for sf in PD.surfaces_for(nm):
            ms = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\b" + re.escape(sf) + r"\b", text[:cut])]
            ms = [m for m in ms if PD.sentence_end(text, m[1]) <= cut]
            if best is None or len(ms) > len(best[1]):
                best = (sf, ms)
        cands.append((nm, best[0], best[1]))
    cands.sort(key=lambda c: -len(c[2]))
    out = []
    for nm, sf, ms in cands[:CTRL_NAMES]:
        out += [(nm, sf, ms[i]) for i in PD.spaced(len(ms), CTRL_PER_NAME)]
    return out, cands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--min-events", type=int, default=14)
    ap.add_argument("--max-events", type=int, default=18)
    ap.add_argument("--show-token-sentences", action="store_true", help="print the alias+identity-token sentences")
    ap.add_argument("--cleared", default="", help="comma-separated event ids whose prefix alias+full-identity sentences were "
                    "read by hand and are not an equation (they are then reported CLEARED, not FAIL); the sentences are "
                    "still printed. Stating an id here is a human judgement and must be recorded in the notes file.")
    args = ap.parse_args()
    texts = Path(args.texts)
    cleared = {c.strip() for c in args.cleared.split(",") if c.strip()}
    doc = json.loads(Path(args.events).read_text(encoding="utf-8"))
    v1 = json.loads(PD.EVENTS.read_text(encoding="utf-8"))["events"]
    v2 = json.loads(V2_FILE.read_text(encoding="utf-8"))["events"]
    v3 = json.loads(V3_FILE.read_text(encoding="utf-8"))["events"]
    earlier = v1 + v2 + v3
    used_ids = {e["id"] for e in earlier}
    used_books = {e["gutenberg"] for e in earlier} | ALT_EDITIONS
    events = doc["events"]
    fails, warns = 0, 0
    seen_ids, seen_books = set(), set()
    print(f"provenance: {doc.get('provenance')!r}; {len(events)} events; used v1+v2+v3 books: {len({e['gutenberg'] for e in earlier})}")

    def fail(ev, msg):
        nonlocal fails
        fails += 1
        print(f"  FAIL {ev['id']}: {msg}")

    def warn(ev, msg):
        nonlocal warns
        warns += 1
        print(f"  WARN {ev['id']}: {msg}")

    if not args.min_events <= len(events) <= args.max_events:
        fails += 1
        print(f"  FAIL file: {len(events)} events, need {args.min_events}..{args.max_events}")

    cache = {}
    totals = []
    for ev in events:
        print(f"{ev['id']}  {ev['book']} (pg{ev['gutenberg']})")
        if set(ev) != V1_KEYS:
            fail(ev, f"schema keys differ from v1: {sorted(set(ev) ^ V1_KEYS)}")
        if ev["id"] in used_ids or ev["id"] in seen_ids:
            fail(ev, "duplicate id")
        if ev["gutenberg"] in used_books or ev["gutenberg"] in seen_books:
            fail(ev, "Gutenberg id already used (v1, v2, a known alternate edition, or earlier in this file)")
        head = " ".join(re.sub(r"[^a-z ]", "", ev["book"].lower()).split()[:3])
        for u in earlier:
            uh = " ".join(re.sub(r"[^a-z ]", "", u["book"].lower()).split()[:3])
            if head == uh:
                fail(ev, f"book title matches used book {u['id']} ({u['book']!r})")
        paren = re.findall(r"\(([^()]*)\)", ev["book"])
        author = paren[-1].split(",")[0].strip().split()[-1].lower() if paren else ""
        author = author.replace("\u00eb", "e").replace("\u00e9", "e")
        if not author:
            fail(ev, "book string has no (Author) parenthesis")
        elif author in USED_AUTHORS:
            fail(ev, f"author {author!r} already has a book in v1, v2 or v3")
        seen_ids.add(ev["id"])
        seen_books.add(ev["gutenberg"])
        cast = ev["cast"]
        if not 7 <= len(cast) <= 9:
            fail(ev, f"cast size {len(cast)} not in 7..9")
        if ev["identity"] not in cast:
            fail(ev, "identity not in cast")
        if len(set(cast)) != len(cast):
            fail(ev, "duplicate cast name")
        if len(ev["reveal_sentence"]) > 140:
            warn(ev, f"anchor is {len(ev['reveal_sentence'])} characters (v2 anchors are short fragments)")
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
              f"pre-alias {npre} post-alias {npost} | identity token in prefix: {loc['identity_in_prefix']}")
        if npre < 3:
            fail(ev, f"only {npre} pre-cutoff alias occurrences (need >= 3)")
        if npost == 0:
            warn(ev, "no post-reveal alias occurrence (post items will be empty)")
        if loc["reveal_start"] <= cut:
            fail(ev, "reveal before cutoff")

        # per-name pre-cutoff counts
        counts = {}
        for nm in cast:
            best = (0, None)
            for sf in PD.surfaces_for(nm):
                ms = [m for m in re.finditer(r"\b" + re.escape(sf) + r"\b", text[:cut])
                      if PD.sentence_end(text, m.end()) <= cut]
                if len(ms) > best[0]:
                    best = (len(ms), sf)
            counts[nm] = best
        print("  pre-cutoff mentions (best surface): " + "; ".join(f"{k}={v[0]}[{v[1]}]" for k, v in counts.items()))
        nonid = {k: v for k, v in counts.items() if k != ev["identity"]}
        missing = [k for k, v in nonid.items() if v[0] == 0]
        if missing:
            fail(ev, f"cast names with zero pre-cutoff mentions: {missing}")
        total_nonid = sum(v[0] for v in nonid.values())
        items, cands = v2_controls(ev, text, cut)
        if len(items) < 8:
            fail(ev, f"v2 control selector yields {len(items)} items (need 8: two names with >= 4 mentions each)")
        if total_nonid < 8:
            fail(ev, f"only {total_nonid} non-identity cast-name mentions before the cutoff (need >= 8)")
        top2 = [c[0] for c in cands[:CTRL_NAMES]]
        for nm, sf, ms in cands[:CTRL_NAMES]:
            others = [n for n in cast if n != nm and sf in PD.surfaces_for(n)[1:] + [n]]
            if others:
                warn(ev, f"control surface {sf!r} (name {nm!r}) is also a surface of {others}: label-noise risk")
        print(f"  controls: {len(items)} items from {top2} via {[c[1] for c in cands[:CTRL_NAMES]]}")
        n_pre, n_post = len(PD.spaced(npre, 8)), len(PD.spaced(npost, 2))
        totals.append((ev["id"], n_pre, n_post, len(items)))
        print(f"  item counts the v2 builder would produce: pre {n_pre} post {n_post} ctrl {len(items)}")

        # identity vs alias co-occurrence in the prefix
        ident_full = re.compile(r"\b" + re.escape(ev["identity"]) + r"\b")
        ident_tok = [t for t in PD.TOKEN.findall(ev["identity"]) if t[:1].isupper() and t not in {"Sir", "Mr", "Abel"}]
        full_hits, tok_hits = [], []
        for m in SENT.finditer(text[:cut]):
            s = m.group(0)
            if not loc["alias_re"].search(s):
                continue
            if ident_full.search(s):
                full_hits.append(s)
            elif any(re.search(r"\b" + re.escape(t) + r"\b", s) for t in ident_tok):
                tok_hits.append(s)
        if full_hits:
            if ev["id"] in cleared:
                print(f"  CLEARED {ev['id']}: {len(full_hits)} prefix sentence(s) with alias AND full identity name, read by hand, "
                      "not an equation:")
            else:
                fail(ev, f"{len(full_hits)} prefix sentence(s) contain an alias AND the full identity name: read them")
            for s in full_hits[:3]:
                print("    >>", " ".join(s.split())[:300])
        print(f"  alias+identity-token sentences before cutoff (to read): {len(tok_hits)}")
        # looser check: alias and the full identity name within 200 characters of each other anywhere in the prefix
        near = 0
        for am in loc["alias_re"].finditer(text[:cut]):
            if ident_full.search(text[max(0, am.start() - 200): am.end() + 200]):
                near += 1
        print(f"  alias occurrences with the full identity name within 200 chars (prefix): {near}")
        # first sentence in the whole book where an alias and the full identity name co-occur (reported, not a test)
        first = None
        for m in SENT.finditer(text):
            if loc["alias_re"].search(m.group(0)) and ident_full.search(m.group(0)):
                first = m.start()
                break
        print(f"  first alias+full-identity sentence in the book: "
              + ("none" if first is None else f"@{first} ({'before' if first < cut else 'after'} cutoff, "
                 f"{first - loc['reveal_start']:+d} chars from reveal)"))
        if args.show_token_sentences:
            for s in tok_hits[:8]:
                print("    >>", " ".join(s.split())[:300])

    print(f"TOTAL items (pre/post/ctrl, same selection rule as pd_v2.build_items): "
          f"{sum(t[1] for t in totals)}/{sum(t[2] for t in totals)}/{sum(t[3] for t in totals)} = {sum(sum(t[1:]) for t in totals)}")
    print(f"TOTAL events {len(events)}; FAIL {fails}; WARN {warns}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
